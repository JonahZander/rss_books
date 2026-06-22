from __future__ import annotations

from urllib.parse import urlsplit

import aiosqlite

# A single hidden, non-polled feed holds every ad-hoc link the user drops into
# the queue. Its URL uses a non-http scheme so the scheduler/refresh selects
# (which filter on this prefix) skip it and it never shows in the sidebar.
SAVED_LINKS_URL = "manual:saved-links"
SAVED_LINKS_TITLE = "Saved links"

# SQL fragment to exclude the synthetic feed from feed listings and polling.
NOT_SAVED_LINKS = f"url != '{SAVED_LINKS_URL}'"


def derive_title(url: str) -> str:
    """A readable default title for a bare link: the last path segment, else
    the hostname. The real <title> isn't known until the page is fetched at
    compile time, so this keeps the queue legible in the meantime."""
    parts = urlsplit(url)
    last = parts.path.rstrip("/").rsplit("/", 1)[-1]
    if last:
        return last.replace("-", " ").replace("_", " ").strip()
    return (parts.hostname or url).removeprefix("www.")


async def get_or_create_saved_links_feed(conn: aiosqlite.Connection) -> int:
    """Row id of the hidden Saved-links feed, created on first use."""
    cur = await conn.execute("SELECT id FROM feeds WHERE url = ?", (SAVED_LINKS_URL,))
    row = await cur.fetchone()
    if row is not None:
        return int(row["id"])
    cur = await conn.execute(
        "INSERT INTO feeds (url, title) VALUES (?, ?)",
        (SAVED_LINKS_URL, SAVED_LINKS_TITLE),
    )
    feed_id = cur.lastrowid
    if feed_id is None:
        raise RuntimeError("saved-links feed insert returned no row id")
    return int(feed_id)


async def add_saved_link(conn: aiosqlite.Connection, url: str, title: str | None) -> int:
    """Insert (or reuse) an article for a bare link in the Saved-links feed and
    return its id. The guid is the URL, so re-adding the same link is idempotent.
    full_content stays NULL — the body is fetched at compile time like any other
    enqueued article that was never previewed."""
    feed_id = await get_or_create_saved_links_feed(conn)
    cur = await conn.execute("SELECT id FROM articles WHERE guid = ?", (url,))
    row = await cur.fetchone()
    if row is not None:
        return int(row["id"])
    cur = await conn.execute(
        "INSERT INTO articles (feed_id, guid, title, url, published_at) "
        "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (feed_id, url, title or derive_title(url), url),
    )
    article_id = cur.lastrowid
    if article_id is None:
        raise RuntimeError("saved-link article insert returned no row id")
    return int(article_id)
