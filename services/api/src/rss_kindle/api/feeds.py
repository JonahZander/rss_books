from __future__ import annotations

import sqlite3

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status

from rss_kindle.models import Feed, FeedCreate
from rss_kindle.services.feed_poller import poll_feed_content

router = APIRouter(prefix="/api/feeds", tags=["feeds"])


async def fetch_feed_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


@router.get("", response_model=list[Feed])
async def list_feeds(request: Request) -> list[Feed]:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT id, url, title, site_url, last_polled, created_at "
            "FROM feeds ORDER BY created_at DESC"
        )
        rows = await cur.fetchall()
    return [Feed.model_validate(dict(r)) for r in rows]


@router.post("", response_model=Feed, status_code=status.HTTP_201_CREATED)
async def create_feed(payload: FeedCreate, request: Request) -> Feed:
    db = request.app.state.db
    try:
        async with db.connect() as conn:
            cur = await conn.execute(
                "INSERT INTO feeds (url, title) VALUES (?, ?)",
                (str(payload.url), payload.title),
            )
            feed_id = cur.lastrowid
            await conn.commit()
            cur = await conn.execute(
                "SELECT id, url, title, site_url, last_polled, created_at "
                "FROM feeds WHERE id = ?",
                (feed_id,),
            )
            row = await cur.fetchone()
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail="feed with this url already exists") from e
    assert row is not None
    return Feed.model_validate(dict(row))


@router.delete("/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feed(feed_id: int, request: Request) -> Response:
    db = request.app.state.db
    async with db.connect() as conn:
        await conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
        await conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{feed_id}/refresh")
async def refresh_feed(feed_id: int, request: Request) -> dict[str, int]:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute("SELECT url FROM feeds WHERE id = ?", (feed_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="feed not found")
    content = await fetch_feed_bytes(row["url"])
    inserted = await poll_feed_content(db, feed_id, content)
    return {"inserted": inserted}


@router.post("/refresh")
async def refresh_all_feeds(request: Request) -> dict[str, int]:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute("SELECT id, url FROM feeds")
        rows = await cur.fetchall()
    total = 0
    for row in rows:
        try:
            content = await fetch_feed_bytes(row["url"])
            total += await poll_feed_content(db, row["id"], content)
        except Exception:
            continue
    return {"inserted": total}
