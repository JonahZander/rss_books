from __future__ import annotations

import sqlite3

import aiosqlite
from fastapi import APIRouter, HTTPException, Request

from rss_books.api.articles import article_state_sql
from rss_books.models import Article, QueueLink, QueueUpdate
from rss_books.services.saved_links import add_saved_link

router = APIRouter(prefix="/api/queue", tags=["queue"])

QUEUE_SELECT = (
    "SELECT a.id, a.feed_id, a.title, a.url, a.summary, a.published_at, a.read_at, "
    "(a.full_content IS NOT NULL) AS has_full_content, " + article_state_sql("a.") + " "
    "FROM digest_queue q JOIN articles a ON a.id = q.article_id "
    "ORDER BY q.position ASC"
)


async def _queue(conn: aiosqlite.Connection) -> list[Article]:
    cur = await conn.execute(QUEUE_SELECT)
    rows = await cur.fetchall()
    return [
        Article.model_validate({**dict(r), "has_full_content": bool(r["has_full_content"])})
        for r in rows
    ]


@router.get("", response_model=list[Article])
async def get_queue(request: Request) -> list[Article]:
    db = request.app.state.db
    async with db.connect() as conn:
        return await _queue(conn)


@router.put("", response_model=list[Article])
async def replace_queue(payload: QueueUpdate, request: Request) -> list[Article]:
    db = request.app.state.db
    try:
        async with db.connect() as conn:
            await conn.execute("DELETE FROM digest_queue")
            for position, article_id in enumerate(payload.article_ids):
                await conn.execute(
                    "INSERT INTO digest_queue (article_id, position) VALUES (?, ?)",
                    (article_id, position),
                )
            await conn.commit()
            return await _queue(conn)
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=404, detail="article not found") from e


@router.post("/link", response_model=list[Article])
async def add_link_to_queue(payload: QueueLink, request: Request) -> list[Article]:
    """Enqueue an arbitrary URL. Stored as an article in the hidden Saved-links
    feed (idempotent by URL) and appended to the queue; its body is fetched when
    the edition is compiled."""
    db = request.app.state.db
    async with db.connect() as conn:
        article_id = await add_saved_link(conn, str(payload.url), payload.title)
        await conn.execute(
            "INSERT OR IGNORE INTO digest_queue (article_id, position) "
            "SELECT ?, COALESCE(MAX(position) + 1, 0) FROM digest_queue",
            (article_id,),
        )
        await conn.commit()
        return await _queue(conn)


@router.post("/{article_id}", response_model=list[Article])
async def add_to_queue(article_id: int, request: Request) -> list[Article]:
    db = request.app.state.db
    try:
        async with db.connect() as conn:
            # OR IGNORE swallows the duplicate-add conflict but still raises
            # on foreign-key violations (unknown article).
            await conn.execute(
                "INSERT OR IGNORE INTO digest_queue (article_id, position) "
                "SELECT ?, COALESCE(MAX(position) + 1, 0) FROM digest_queue",
                (article_id,),
            )
            await conn.commit()
            return await _queue(conn)
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=404, detail="article not found") from e


@router.delete("/{article_id}", response_model=list[Article])
async def remove_from_queue(article_id: int, request: Request) -> list[Article]:
    db = request.app.state.db
    async with db.connect() as conn:
        await conn.execute("DELETE FROM digest_queue WHERE article_id = ?", (article_id,))
        await conn.commit()
        return await _queue(conn)
