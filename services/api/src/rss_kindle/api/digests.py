from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import FileResponse

from rss_kindle.db import Database
from rss_kindle.models import Digest, DigestCreate
from rss_kindle.services.epub_builder import DigestArticle, build_digest_epub

router = APIRouter(prefix="/api/digests", tags=["digests"])

logger = logging.getLogger(__name__)

DIGEST_COLUMNS = "id, title, epub_path, status, error, created_at"


async def _generate_digest(db: Database, digest_id: int, epub_dir: Path) -> None:
    try:
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE digests SET status = 'generating' WHERE id = ?", (digest_id,)
            )
            await conn.commit()

            cur = await conn.execute("SELECT title FROM digests WHERE id = ?", (digest_id,))
            d = await cur.fetchone()
            if d is None:
                raise RuntimeError(f"digest {digest_id} vanished before generation")

            cur = await conn.execute(
                "SELECT a.title, a.url, a.summary, a.full_content, f.title AS source "
                "FROM digest_articles da "
                "JOIN articles a ON a.id = da.article_id "
                "JOIN feeds f ON f.id = a.feed_id "
                "WHERE da.digest_id = ? ORDER BY da.position ASC",
                (digest_id,),
            )
            rows = await cur.fetchall()

        articles = [
            DigestArticle(
                title=r["title"],
                source=r["source"],
                url=r["url"],
                markdown=(r["full_content"] or r["summary"] or ""),
            )
            for r in rows
        ]

        output = epub_dir / f"digest-{digest_id}-{d['title']}.epub"
        build_digest_epub(title=d["title"], articles=articles, output_path=output)

        async with db.connect() as conn:
            await conn.execute(
                "UPDATE digests SET epub_path = ?, status = 'ready' WHERE id = ?",
                (str(output), digest_id),
            )
            await conn.commit()
        logger.info("digest %d ready: %s (%d articles)", digest_id, output.name, len(articles))
    except Exception as exc:
        logger.exception("digest %d build failed", digest_id)
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE digests SET status = 'failed', error = ? WHERE id = ?",
                (str(exc), digest_id),
            )
            await conn.commit()


@router.get("", response_model=list[Digest])
async def list_digests(request: Request) -> list[Digest]:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {DIGEST_COLUMNS} FROM digests ORDER BY created_at DESC, id DESC"
        )
        rows = await cur.fetchall()
    return [Digest.model_validate(dict(r)) for r in rows]


@router.get("/{digest_id}", response_model=Digest)
async def get_digest(digest_id: int, request: Request) -> Digest:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {DIGEST_COLUMNS} FROM digests WHERE id = ?",
            (digest_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="digest not found")
    return Digest.model_validate(dict(row))


@router.post("", response_model=Digest, status_code=status.HTTP_201_CREATED)
async def create_digest(
    payload: DigestCreate,
    request: Request,
    background: BackgroundTasks,
) -> Digest:
    if not payload.article_ids:
        raise HTTPException(status_code=400, detail="no articles selected")

    db: Database = request.app.state.db
    epub_dir: Path = request.app.state.settings.epub_dir
    title = payload.title or date.today().isoformat()

    async with db.connect() as conn:
        cur = await conn.execute(
            "INSERT INTO digests (title, status) VALUES (?, 'pending')",
            (title,),
        )
        digest_id = cur.lastrowid
        if digest_id is None:
            raise RuntimeError("digest insert returned no row id")
        for position, article_id in enumerate(payload.article_ids):
            await conn.execute(
                "INSERT INTO digest_articles (digest_id, article_id, position) VALUES (?, ?, ?)",
                (digest_id, article_id, position),
            )
        await conn.commit()
        cur = await conn.execute(
            f"SELECT {DIGEST_COLUMNS} FROM digests WHERE id = ?",
            (digest_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError(f"digest {digest_id} not found after insert")

    background.add_task(_generate_digest, db, digest_id, epub_dir)
    return Digest.model_validate(dict(row))


@router.get("/{digest_id}/download")
async def download_digest(digest_id: int, request: Request) -> FileResponse:
    db = request.app.state.db
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
