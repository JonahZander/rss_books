from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import FileResponse

from rss_kindle.db import Database
from rss_kindle.models import Digest, DigestCreate
from rss_kindle.services.digest_service import create_digest_record, generate_digest

router = APIRouter(prefix="/api/digests", tags=["digests"])

DIGEST_COLUMNS = "id, title, epub_path, status, error, size_bytes, delivered_at, created_at"


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
    db: Database = request.app.state.db
    epub_dir: Path = request.app.state.settings.epub_dir

    try:
        digest_id = await create_digest_record(db, payload.article_ids, payload.title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {DIGEST_COLUMNS} FROM digests WHERE id = ?",
            (digest_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError(f"digest {digest_id} not found after insert")

    background.add_task(generate_digest, db, digest_id, epub_dir)
    return Digest.model_validate(dict(row))


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
