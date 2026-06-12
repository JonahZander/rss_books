from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import FileResponse

from rss_kindle.db import Database
from rss_kindle.models import Delivery, Digest, DigestCreate
from rss_kindle.services.digest_service import create_digest_records, generate_digest
from rss_kindle.services.emailer import EmailError, send_digest_and_record
from rss_kindle.services.settings_store import get_app_settings

router = APIRouter(prefix="/api/digests", tags=["digests"])

DIGEST_COLUMNS = (
    "id, title, group_name, epub_path, status, error, size_bytes, delivered_at, created_at, "
    "(SELECT COUNT(*) FROM digest_articles da WHERE da.digest_id = digests.id) AS article_count"
)
DELIVERY_COLUMNS = "id, digest_id, channel, target, status, error, created_at"


@router.get("", response_model=list[Digest])
async def list_digests(request: Request) -> list[Digest]:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {DIGEST_COLUMNS} FROM digests ORDER BY created_at DESC, id DESC"
        )
        rows = await cur.fetchall()
        cur = await conn.execute(
            f"SELECT {DELIVERY_COLUMNS} FROM deliveries ORDER BY created_at DESC, id DESC"
        )
        delivery_rows = await cur.fetchall()

    by_digest: dict[int, list[Delivery]] = {}
    for d in delivery_rows:
        by_digest.setdefault(d["digest_id"], []).append(Delivery.model_validate(dict(d)))
    return [
        Digest.model_validate({**dict(r), "deliveries": by_digest.get(r["id"], [])})
        for r in rows
    ]


@router.get("/{digest_id}", response_model=Digest)
async def get_digest(digest_id: int, request: Request) -> Digest:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {DIGEST_COLUMNS} FROM digests WHERE id = ?",
            (digest_id,),
        )
        row = await cur.fetchone()
        cur = await conn.execute(
            f"SELECT {DELIVERY_COLUMNS} FROM deliveries WHERE digest_id = ? "
            "ORDER BY created_at DESC, id DESC",
            (digest_id,),
        )
        delivery_rows = await cur.fetchall()
    if row is None:
        raise HTTPException(status_code=404, detail="digest not found")
    deliveries = [Delivery.model_validate(dict(d)) for d in delivery_rows]
    return Digest.model_validate({**dict(row), "deliveries": deliveries})


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
    """Create edition(s) from the selection or queue — one digest in combined
    mode, one per feed group in per_group mode (creation order preserved)."""
    db: Database = request.app.state.db
    epub_dir: Path = request.app.state.settings.epub_dir

    try:
        digest_ids = await create_digest_records(
            db, payload.article_ids, payload.title, payload.split
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    marks = ", ".join("?" for _ in digest_ids)
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
