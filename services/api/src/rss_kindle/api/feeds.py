from __future__ import annotations

import logging
import sqlite3

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status

from rss_kindle.db import Database
from rss_kindle.models import Feed, FeedCreate, FeedUpdate
from rss_kindle.services.feed_poller import poll_feed_content

router = APIRouter(prefix="/api/feeds", tags=["feeds"])

logger = logging.getLogger(__name__)

FEED_COLUMNS = (
    "id, url, title, site_url, last_polled, created_at, "
    "poll_interval_minutes, last_error, last_error_at, consecutive_failures"
)


async def fetch_feed_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        headers={"User-Agent": "rss-kindle-selector/1.0"},
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


async def _record_poll_outcome(db: Database, feed_id: int, error: str | None) -> None:
    async with db.connect() as conn:
        if error is None:
            await conn.execute(
                "UPDATE feeds SET last_error = NULL, last_error_at = NULL, "
                "consecutive_failures = 0 WHERE id = ?",
                (feed_id,),
            )
        else:
            await conn.execute(
                "UPDATE feeds SET last_error = ?, last_error_at = CURRENT_TIMESTAMP, "
                "consecutive_failures = consecutive_failures + 1 WHERE id = ?",
                (error, feed_id),
            )
        await conn.commit()


@router.get("", response_model=list[Feed])
async def list_feeds(request: Request) -> list[Feed]:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {FEED_COLUMNS} FROM feeds ORDER BY created_at DESC, id DESC"
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
                f"SELECT {FEED_COLUMNS} FROM feeds WHERE id = ?",
                (feed_id,),
            )
            row = await cur.fetchone()
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail="feed with this url already exists") from e
    if row is None:
        raise RuntimeError(f"feed {feed_id} not found after insert")
    return Feed.model_validate(dict(row))


@router.patch("/{feed_id}", response_model=Feed)
async def update_feed(feed_id: int, payload: FeedUpdate, request: Request) -> Feed:
    db = request.app.state.db
    fields = payload.model_dump(exclude_none=True)
    async with db.connect() as conn:
        if fields:
            sets = ", ".join(f"{name} = ?" for name in fields)
            cur = await conn.execute(
                f"UPDATE feeds SET {sets} WHERE id = ?",  # noqa: S608 — keys from the model
                (*fields.values(), feed_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="feed not found")
            await conn.commit()
        cur = await conn.execute(f"SELECT {FEED_COLUMNS} FROM feeds WHERE id = ?", (feed_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="feed not found")
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
    try:
        content = await fetch_feed_bytes(row["url"])
        inserted = await poll_feed_content(db, feed_id, content)
    except Exception as exc:
        await _record_poll_outcome(db, feed_id, str(exc))
        logger.warning("manual refresh failed for feed %d (%s): %s", feed_id, row["url"], exc)
        raise HTTPException(status_code=502, detail=f"feed fetch failed: {exc}") from exc
    await _record_poll_outcome(db, feed_id, None)
    return {"inserted": inserted}


@router.post("/refresh")
async def refresh_all_feeds(request: Request) -> dict[str, int]:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute("SELECT id, url FROM feeds")
        rows = await cur.fetchall()
    total = 0
    errors = 0
    for row in rows:
        try:
            content = await fetch_feed_bytes(row["url"])
            total += await poll_feed_content(db, row["id"], content)
            await _record_poll_outcome(db, row["id"], None)
        except Exception as exc:
            errors += 1
            await _record_poll_outcome(db, row["id"], str(exc))
            logger.warning("refresh failed for feed %d (%s): %s", row["id"], row["url"], exc)
    logger.info("refreshed %d feeds: %d new articles, %d errors", len(rows), total, errors)
    return {"inserted": total, "errors": errors}
