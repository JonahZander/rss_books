from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request, Response, status

from rss_kindle.models import Feed, FeedCreate

router = APIRouter(prefix="/api/feeds", tags=["feeds"])


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
