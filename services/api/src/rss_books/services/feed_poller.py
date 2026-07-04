from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from time import struct_time
from typing import cast
from urllib.parse import urlparse

import feedparser

from rss_books.db import Database
from rss_books.services.sanitizer import sanitize


def placeholder_title(url: str) -> str:
    """Default title for imports that carry no titles (JSON feed lists):
    the hostname. The first successful poll replaces it with the feed's own
    <title>, unless the user renamed the feed first."""
    host = (urlparse(url).hostname or "").removeprefix("www.")
    return host or url


@dataclass
class ParsedEntry:
    guid: str
    title: str
    url: str
    summary: str
    published_at: datetime | None
    # Full article HTML when the feed embeds it (<content:encoded> / Atom
    # <content>). Lets us skip the on-demand page fetch entirely.
    content: str | None = None


def _longest_content(entry: object) -> str | None:
    """feedparser exposes entry.content as a list of {'value', 'type', ...}
    dicts; pick the one with the longest value (some feeds carry both a teaser
    and the full body). Returns None when no content is present."""
    items = entry.get("content")  # type: ignore[attr-defined]
    if not items:
        return None
    best = max((c.get("value", "") for c in items), key=len, default="")
    return best or None


@dataclass
class ParsedFeed:
    title: str
    site_url: str | None
    entries: list[ParsedEntry]


def _struct_to_dt(st: struct_time | None) -> datetime | None:
    if st is None:
        return None
    return datetime(*st[:6], tzinfo=UTC)


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
                content=_longest_content(e),
            )
        )
    return ParsedFeed(title=title, site_url=site_url, entries=entries)


async def poll_feed_content(db: Database, feed_id: int, content: bytes) -> int:
    parsed = parse_feed(content)
    inserted = 0
    async with db.connect() as conn:
        if parsed.title and parsed.title != "Untitled":
            # adopt the feed's self-reported title while the stored title is
            # still the import placeholder (a manual rename breaks the match)
            cur = await conn.execute("SELECT url, title FROM feeds WHERE id = ?", (feed_id,))
            row = await cur.fetchone()
            if row is not None and row["title"] == placeholder_title(row["url"]):
                await conn.execute(
                    "UPDATE feeds SET title = ? WHERE id = ?", (parsed.title, feed_id)
                )
        for entry in parsed.entries:
            # Many feeds embed the whole article (<content:encoded> / Atom
            # <content>); when it's meaningfully fuller than the summary we
            # sanitize and store it now so the article is readable without an
            # on-demand page fetch (which modern WAFs often 403). The length
            # guard rejects teaser-only content:encoded. We only sanitize,
            # never running trafilatura, since feed content is already article
            # HTML, and the nh3 allowlist is the contract for all stored HTML.
            full_content: str | None = None
            if (
                entry.content
                and len(entry.content) > len(entry.summary)
                and len(entry.content) > 200
            ):
                full_content = sanitize(entry.content)
            try:
                await conn.execute(
                    "INSERT INTO articles "
                    "(feed_id, guid, title, url, summary, full_content, published_at, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, "
                    "CASE WHEN ? IS NOT NULL THEN CURRENT_TIMESTAMP END)",
                    (
                        feed_id,
                        entry.guid,
                        entry.title,
                        entry.url,
                        entry.summary,
                        full_content,
                        entry.published_at.isoformat() if entry.published_at else None,
                        full_content,
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
