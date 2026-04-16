from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from time import struct_time
from typing import cast

import feedparser

from rss_kindle.db import Database


@dataclass
class ParsedEntry:
    guid: str
    title: str
    url: str
    summary: str
    published_at: datetime | None


@dataclass
class ParsedFeed:
    title: str
    site_url: str | None
    entries: list[ParsedEntry]


def _struct_to_dt(st: struct_time | None) -> datetime | None:
    if st is None:
        return None
    return datetime(*st[:6], tzinfo=timezone.utc)


def parse_feed(content: bytes) -> ParsedFeed:
    parsed = feedparser.parse(content)
    site_url = parsed.feed.get("link") if hasattr(parsed, "feed") else None
    title = parsed.feed.get("title", "Untitled") if hasattr(parsed, "feed") else "Untitled"
    entries: list[ParsedEntry] = []
    for e in parsed.entries:
        guid = e.get("id") or e.get("guid") or e.get("link") or ""
        if not guid:
            continue
        url = e.get("link", "")
        entries.append(
            ParsedEntry(
                guid=guid,
                title=e.get("title", "Untitled"),
                url=url,
                summary=e.get("summary", ""),
                published_at=_struct_to_dt(
                    cast(struct_time | None, e.get("published_parsed"))
                    or cast(struct_time | None, e.get("updated_parsed"))
                ),
            )
        )
    return ParsedFeed(title=title, site_url=site_url, entries=entries)


async def poll_feed_content(db: Database, feed_id: int, content: bytes) -> int:
    parsed = parse_feed(content)
    inserted = 0
    async with db.connect() as conn:
        for entry in parsed.entries:
            try:
                await conn.execute(
                    "INSERT INTO articles (feed_id, guid, title, url, summary, published_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        feed_id,
                        entry.guid,
                        entry.title,
                        entry.url,
                        entry.summary,
                        entry.published_at.isoformat() if entry.published_at else None,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                continue
        await conn.execute(
            "UPDATE feeds SET last_polled = CURRENT_TIMESTAMP WHERE id = ?",
            (feed_id,),
        )
        await conn.commit()
    return inserted
