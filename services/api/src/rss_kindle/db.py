from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    site_url TEXT,
    last_polled DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
    guid TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    summary TEXT,
    full_content TEXT,
    published_at DATETIME,
    fetched_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_articles_feed ON articles(feed_id, published_at DESC);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    epub_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS digest_articles (
    digest_id INTEGER NOT NULL REFERENCES digests(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (digest_id, article_id)
);
"""

def placeholders(count: int) -> str:
    """`?, ?, …` for a SQL `IN (...)` clause of `count` bound parameters."""
    return ", ".join("?" for _ in range(count))


Migration = Callable[[aiosqlite.Connection], Awaitable[None]]


async def _m1_baseline(conn: aiosqlite.Connection) -> None:
    await conn.executescript(SCHEMA_V1)


# Every schema change ships as a new migration appended here. Migrations run in
# order inside Database.init(); the applied version is tracked in PRAGMA user_version.
async def _m2_digest_failure(conn: aiosqlite.Connection) -> None:
    await conn.execute("ALTER TABLE digests ADD COLUMN error TEXT")


async def _m3_html_content(conn: aiosqlite.Connection) -> None:
    # Content storage switched from markdown to sanitized HTML; cached
    # extractions are invalidated and re-fetched on demand.
    await conn.execute("UPDATE articles SET full_content = NULL, fetched_at = NULL")


async def _m4_queue_delivery_settings(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS digest_queue (
            article_id INTEGER PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            queued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            digest_id INTEGER NOT NULL REFERENCES digests(id) ON DELETE CASCADE,
            channel TEXT NOT NULL,
            target TEXT,
            status TEXT NOT NULL,
            error TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    await conn.execute("ALTER TABLE digests ADD COLUMN delivered_at DATETIME")
    await conn.execute("ALTER TABLE digests ADD COLUMN size_bytes INTEGER")


async def _m5_feed_health(conn: aiosqlite.Connection) -> None:
    await conn.execute("ALTER TABLE feeds ADD COLUMN etag TEXT")
    await conn.execute("ALTER TABLE feeds ADD COLUMN last_modified TEXT")
    await conn.execute(
        "ALTER TABLE feeds ADD COLUMN poll_interval_minutes INTEGER NOT NULL DEFAULT 30"
    )
    await conn.execute("ALTER TABLE feeds ADD COLUMN last_error TEXT")
    await conn.execute("ALTER TABLE feeds ADD COLUMN last_error_at DATETIME")
    await conn.execute(
        "ALTER TABLE feeds ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0"
    )


async def _m6_read_state(conn: aiosqlite.Connection) -> None:
    await conn.execute("ALTER TABLE articles ADD COLUMN read_at DATETIME")


async def _m7_feed_groups(conn: aiosqlite.Connection) -> None:
    # Folder-style groups: a feed belongs to at most one group. digests.group_name
    # snapshots the group at press time (NULL = combined edition) so the EPUB
    # builder can pick the right TOC shape and renames can't rewrite history.
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            position INTEGER NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    await conn.execute(
        "ALTER TABLE feeds ADD COLUMN group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL"
    )
    await conn.execute("ALTER TABLE digests ADD COLUMN group_name TEXT")


async def _m8_hot_path_indexes(conn: aiosqlite.Connection) -> None:
    # Cover the article-list filters (unread default-on, retention sweep) and the
    # per-article digest-membership lookup, which can't use digest_articles'
    # (digest_id, article_id) PK because article_id isn't its leading column.
    await conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_articles_read ON articles(read_at);
        CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at);
        CREATE INDEX IF NOT EXISTS idx_digest_articles_article ON digest_articles(article_id);
        """
    )


async def _m9_digest_article_fetch_status(conn: aiosqlite.Connection) -> None:
    # Per-member outcome of compile-time content retrieval: 'full' (real body,
    # stored or freshly fetched), 'summary' (fell back to the RSS summary), or
    # 'empty' (nothing available). NULL until the edition is generated. Lets the
    # Editions UI report "N of M links fetched" and list the ones that failed.
    await conn.execute("ALTER TABLE digest_articles ADD COLUMN fetch_status TEXT")


async def _m10_digest_render_profile(conn: aiosqlite.Connection) -> None:
    # Render-profile name snapshotted at press time (mirrors group_name): NULL =
    # compiled with the legacy global settings. Profile renames/deletions never
    # rewrite what an existing edition was built with.
    await conn.execute("ALTER TABLE digests ADD COLUMN profile TEXT")


MIGRATIONS: list[tuple[str, Migration]] = [
    ("baseline", _m1_baseline),
    ("digest failure state", _m2_digest_failure),
    ("html content reset", _m3_html_content),
    ("queue, deliveries, settings", _m4_queue_delivery_settings),
    ("feed health and conditional GET", _m5_feed_health),
    ("read state", _m6_read_state),
    ("feed groups", _m7_feed_groups),
    ("hot-path indexes", _m8_hot_path_indexes),
    ("digest article fetch status", _m9_digest_article_fetch_status),
    ("digest render profile", _m10_digest_render_profile),
]


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    async def init(self) -> None:
        async with self.connect() as conn:
            cur = await conn.execute("PRAGMA user_version")
            row = await cur.fetchone()
            version = int(row[0]) if row else 0

            if version == 0:
                # Distinguish a fresh database from a 0.1-era database that
                # predates the migration mechanism (tables exist, version 0).
                cur = await conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='feeds'"
                )
                if await cur.fetchone() is not None:
                    version = 1
                    await conn.execute("PRAGMA user_version = 1")
                    await conn.commit()

            for number, (name, migrate) in enumerate(MIGRATIONS, start=1):
                if number <= version:
                    continue
                await migrate(conn)
                await conn.execute(f"PRAGMA user_version = {number}")
                await conn.commit()
                logger.info("applied migration %d (%s)", number, name)

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        # WAL lets readers run during a write and serializes writers behind a
        # bounded wait instead of failing immediately — without it the scheduler
        # polling several feeds concurrently (each its own connection) hits
        # "database is locked". WAL is persistent; busy_timeout is per-connection.
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
        finally:
            await conn.close()
