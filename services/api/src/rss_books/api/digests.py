from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse

from rss_books.db import Database, placeholders
from rss_books.models import (
    Delivery,
    Digest,
    DigestArticleEntry,
    DigestArticlesRemove,
    DigestCreate,
)
from rss_books.services.digest_service import (
    create_digest_records,
    generate_digest,
    load_digest_preview,
)
from rss_books.services.emailer import EmailError, send_digest_and_record
from rss_books.services.epub_builder import render_preview_html
from rss_books.services.settings_store import get_app_settings

router = APIRouter(prefix="/api/digests", tags=["digests"])

DIGEST_COLUMNS = (
    "id, title, group_name, profile, epub_path, status, error, size_bytes, delivered_at, "
    "created_at, "
    "(SELECT COUNT(*) FROM digest_articles da WHERE da.digest_id = digests.id) AS article_count"
)
DELIVERY_COLUMNS = "id, digest_id, channel, target, status, error, created_at"


async def _load_digests_with_deliveries(
    db: Database, digest_id: int | None = None
) -> list[Digest]:
    """Digests (all, or one by id) with their deliveries attached, newest first."""
    digest_where = "" if digest_id is None else "WHERE id = ? "
    delivery_where = "" if digest_id is None else "WHERE digest_id = ? "
    params: tuple[int, ...] = () if digest_id is None else (digest_id,)
    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {DIGEST_COLUMNS} FROM digests {digest_where}"
            "ORDER BY created_at DESC, id DESC",
            params,
        )
        rows = await cur.fetchall()
        cur = await conn.execute(
            f"SELECT {DELIVERY_COLUMNS} FROM deliveries {delivery_where}"
            "ORDER BY created_at DESC, id DESC",
            params,
        )
        delivery_rows = await cur.fetchall()

    by_digest: dict[int, list[Delivery]] = {}
    for d in delivery_rows:
        by_digest.setdefault(d["digest_id"], []).append(Delivery.model_validate(dict(d)))
    return [
        Digest.model_validate({**dict(r), "deliveries": by_digest.get(r["id"], [])})
        for r in rows
    ]


@router.get("", response_model=list[Digest])
async def list_digests(request: Request) -> list[Digest]:
    db = request.app.state.db
    return await _load_digests_with_deliveries(db)


@router.get("/{digest_id}", response_model=Digest)
async def get_digest(digest_id: int, request: Request) -> Digest:
    db = request.app.state.db
    digests = await _load_digests_with_deliveries(db, digest_id)
    if not digests:
        raise HTTPException(status_code=404, detail="digest not found")
    return digests[0]


@router.get("/{digest_id}/articles", response_model=list[DigestArticleEntry])
async def list_digest_articles(digest_id: int, request: Request) -> list[DigestArticleEntry]:
    """The ordered members of an edition, with each one's compile-time fetch
    outcome. It powers the Editions preview, the "N of M fetched" summary, and the
    per-article remove buttons."""
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute("SELECT 1 FROM digests WHERE id = ?", (digest_id,))
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="digest not found")
        cur = await conn.execute(
            "SELECT a.id AS article_id, da.position, a.title, a.url, "
            "(a.full_content IS NOT NULL) AS has_full_content, da.fetch_status, "
            "f.title AS source, g.name AS group_name "
            "FROM digest_articles da "
            "JOIN articles a ON a.id = da.article_id "
            "JOIN feeds f ON f.id = a.feed_id "
            "LEFT JOIN groups g ON g.id = f.group_id "
            "WHERE da.digest_id = ? ORDER BY da.position ASC",
            (digest_id,),
        )
        rows = await cur.fetchall()
    return [
        DigestArticleEntry.model_validate(
            {**dict(r), "has_full_content": bool(r["has_full_content"])}
        )
        for r in rows
    ]


@router.post("/{digest_id}/send", response_model=Delivery)
async def send_digest(digest_id: int, request: Request) -> Delivery:
    db = request.app.state.db
    app_settings = await get_app_settings(db)
    try:
        return await send_digest_and_record(db, app_settings, digest_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except EmailError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("", response_model=list[Digest], status_code=status.HTTP_201_CREATED)
async def create_digest(
    payload: DigestCreate,
    request: Request,
    background: BackgroundTasks,
) -> list[Digest]:
    """Create edition(s) from the selection or queue: one digest in combined
    mode, one per feed group in per_group mode (creation order preserved),
    crossed with one variant per selected render profile."""
    db: Database = request.app.state.db
    epub_dir: Path = request.app.state.settings.epub_dir

    if payload.profiles:
        app_settings = await get_app_settings(db)
        known = {p.name for p in app_settings.profiles}
        unknown = [name for name in payload.profiles if name not in known]
        if unknown:
            raise HTTPException(
                status_code=400, detail=f"unknown render profile(s): {', '.join(unknown)}"
            )

    try:
        digest_ids = await create_digest_records(
            db, payload.article_ids, payload.title, payload.split, payload.profiles
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    marks = placeholders(len(digest_ids))
    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {DIGEST_COLUMNS} FROM digests WHERE id IN ({marks})",
            digest_ids,
        )
        rows = {r["id"]: r for r in await cur.fetchall()}
    if len(rows) != len(digest_ids):
        raise RuntimeError("digest rows not found after insert")

    for digest_id in digest_ids:
        background.add_task(generate_digest, db, digest_id, epub_dir)
    return [Digest.model_validate(dict(rows[digest_id])) for digest_id in digest_ids]


@router.delete("/{digest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_digest(digest_id: int, request: Request) -> None:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT epub_path FROM digests WHERE id = ?",
            (digest_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="digest not found")
        await conn.execute("DELETE FROM digests WHERE id = ?", (digest_id,))
        await conn.commit()
    if row["epub_path"]:
        Path(row["epub_path"]).unlink(missing_ok=True)


async def _remove_articles_and_rebuild(
    db: Database,
    epub_dir: Path,
    digest_id: int,
    article_ids: list[int],
    background: BackgroundTasks,
) -> int:
    """Drop the given members from an edition in one transaction; queue a single
    rebuild if any remain, else mark the edition 'failed' (empty). Returns the
    number actually removed. Raises HTTPException(404) when nothing matched."""
    async with db.connect() as conn:
        marks = placeholders(len(article_ids))
        cur = await conn.execute(
            f"DELETE FROM digest_articles WHERE digest_id = ? AND article_id IN ({marks})",
            (digest_id, *article_ids),
        )
        removed = cur.rowcount
        if removed == 0:
            cur = await conn.execute("SELECT 1 FROM digests WHERE id = ?", (digest_id,))
            detail = "digest not found" if await cur.fetchone() is None else "article not in digest"
            raise HTTPException(status_code=404, detail=detail)
        cur = await conn.execute(
            "SELECT COUNT(*) AS n FROM digest_articles WHERE digest_id = ?",
            (digest_id,),
        )
        count_row = await cur.fetchone()
        remaining = count_row["n"] if count_row else 0
        if remaining:
            await conn.execute(
                "UPDATE digests SET status = 'pending', error = NULL WHERE id = ?",
                (digest_id,),
            )
        else:
            await conn.execute(
                "UPDATE digests SET status = 'failed', "
                "error = 'edition is empty, every article was removed' WHERE id = ?",
                (digest_id,),
            )
        await conn.commit()
    if remaining:
        background.add_task(generate_digest, db, digest_id, epub_dir)
    return removed


@router.delete("/{digest_id}/articles/{article_id}", response_model=Digest)
async def remove_digest_article(
    digest_id: int,
    article_id: int,
    request: Request,
    background: BackgroundTasks,
) -> Digest:
    """Drop one article from an edition and rebuild its EPUB in the background.
    Removing the last member leaves the edition 'failed' (nothing to compile)
    rather than building an empty book; the article's read state is untouched."""
    db: Database = request.app.state.db
    epub_dir: Path = request.app.state.settings.epub_dir
    await _remove_articles_and_rebuild(db, epub_dir, digest_id, [article_id], background)
    return await get_digest(digest_id, request)


@router.post("/{digest_id}/articles/remove", response_model=Digest)
async def remove_digest_articles(
    digest_id: int,
    payload: DigestArticlesRemove,
    request: Request,
    background: BackgroundTasks,
) -> Digest:
    """Batch-drop several members at once: one transaction, one rebuild. Powers
    the Editions review panel's staged 'Apply removals' so culling N articles
    costs one EPUB build instead of N."""
    if not payload.article_ids:
        raise HTTPException(status_code=400, detail="no articles to remove")
    db: Database = request.app.state.db
    epub_dir: Path = request.app.state.settings.epub_dir
    await _remove_articles_and_rebuild(
        db, epub_dir, digest_id, payload.article_ids, background
    )
    return await get_digest(digest_id, request)


@router.get("/{digest_id}/preview", response_class=HTMLResponse)
async def preview_digest(digest_id: int, request: Request) -> HTMLResponse:
    """A standalone HTML rendition of the edition (title page, sectioned
    contents and the same chapter bodies the EPUB ships) for the in-app preview
    drawer. Built from stored content, so it works before/independently of the
    EPUB build and even for 'failed' editions that still have members."""
    db: Database = request.app.state.db
    try:
        title, articles = await load_digest_preview(db, digest_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    settings = await get_app_settings(db)
    return HTMLResponse(
        render_preview_html(title=title, articles=articles, link_qr=settings.link_qr)
    )


async def load_ready_epub_response(db: Database, digest_id: int) -> FileResponse:
    """Shared by the (auth-free) /api download and the OPDS-authenticated
    download: look up a ready digest's EPUB and build its FileResponse,
    404/409 semantics identical either way."""
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT title, epub_path, status FROM digests WHERE id = ?",
            (digest_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="digest not found")
    if row["status"] != "ready" or not row["epub_path"]:
        raise HTTPException(status_code=409, detail="digest not ready")
    return FileResponse(
        row["epub_path"],
        media_type="application/epub+zip",
        filename=f"digest-{row['title']}.epub",
    )


@router.get("/{digest_id}/download")
async def download_digest(digest_id: int, request: Request) -> FileResponse:
    return await load_ready_epub_response(request.app.state.db, digest_id)
