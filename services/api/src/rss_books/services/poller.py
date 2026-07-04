from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from rss_books.config import USER_AGENT
from rss_books.db import Database
from rss_books.services.feed_poller import poll_feed_content

__all__ = ["USER_AGENT", "PollResult", "poll_feed"]

logger = logging.getLogger(__name__)


@dataclass
class PollResult:
    feed_id: int
    inserted: int = 0
    not_modified: bool = False
    error: str | None = None


async def poll_feed(db: Database, client: httpx.AsyncClient, feed: Any) -> PollResult:
    """One scheduled poll: conditional GET, ingest on 200, health bookkeeping.

    `feed` is a row with id, url, etag, last_modified.
    """
    headers: dict[str, str] = {}
    if feed["etag"]:
        headers["If-None-Match"] = feed["etag"]
    if feed["last_modified"]:
        headers["If-Modified-Since"] = feed["last_modified"]

    try:
        r = await client.get(feed["url"], headers=headers)
        if r.status_code == 304:
            async with db.connect() as conn:
                await conn.execute(
                    "UPDATE feeds SET last_polled = CURRENT_TIMESTAMP, last_error = NULL, "
                    "last_error_at = NULL, consecutive_failures = 0 WHERE id = ?",
                    (feed["id"],),
                )
                await conn.commit()
            return PollResult(feed["id"], not_modified=True)
        r.raise_for_status()
        inserted = await poll_feed_content(db, feed["id"], r.content)
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE feeds SET etag = ?, last_modified = ?, last_error = NULL, "
                "last_error_at = NULL, consecutive_failures = 0 WHERE id = ?",
                (r.headers.get("etag"), r.headers.get("last-modified"), feed["id"]),
            )
            await conn.commit()
        return PollResult(feed["id"], inserted=inserted)
    except Exception as exc:
        logger.warning("poll failed for feed %d (%s): %s", feed["id"], feed["url"], exc)
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE feeds SET last_error = ?, last_error_at = CURRENT_TIMESTAMP, "
                "consecutive_failures = consecutive_failures + 1 WHERE id = ?",
                (str(exc), feed["id"]),
            )
            await conn.commit()
        return PollResult(feed["id"], error=str(exc))
