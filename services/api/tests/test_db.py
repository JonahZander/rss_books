import asyncio
from pathlib import Path

import aiosqlite

from rss_books.db import MIGRATIONS, SCHEMA_V1, Database


async def _user_version(db: Database) -> int:
    async with db.connect() as conn:
        cur = await conn.execute("PRAGMA user_version")
        row = await cur.fetchone()
        assert row is not None
        return int(row[0])


async def test_fresh_init_reaches_head(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    await db.init()
    async with db.connect() as conn:
        cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        rows = await cur.fetchall()
    names = {r[0] for r in rows}
    assert {"feeds", "articles", "digests", "digest_articles"}.issubset(names)
    assert await _user_version(db) == len(MIGRATIONS)


async def test_legacy_v01_db_upgrades_in_place(tmp_path: Path) -> None:
    """A pre-migration 0.1 database (tables exist, user_version=0) is adopted, not wiped."""
    path = tmp_path / "legacy.db"
    conn = await aiosqlite.connect(path)
    await conn.executescript(SCHEMA_V1)
    await conn.execute(
        "INSERT INTO feeds (url, title) VALUES ('https://example.com/rss', 'Example')"
    )
    await conn.commit()
    await conn.close()

    db = Database(path)
    await db.init()

    assert await _user_version(db) == len(MIGRATIONS)
    async with db.connect() as conn2:
        cur = await conn2.execute("SELECT title FROM feeds")
        row = await cur.fetchone()
    assert row is not None and row["title"] == "Example"


async def test_init_is_idempotent(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    await db.init()
    await db.init()
    assert await _user_version(db) == len(MIGRATIONS)


async def test_concurrent_init_on_fresh_db(tmp_path: Path) -> None:
    """In production two server lifespans call init() on the same instance
    concurrently (see api/serve.py); the ladder must not double-apply."""
    db = Database(tmp_path / "test.db")
    await asyncio.gather(db.init(), db.init(), db.init())
    assert await _user_version(db) == len(MIGRATIONS)


async def test_migration_7_feed_groups(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    await db.init()
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='groups'"
        )
        assert await cur.fetchone() is not None
        cur = await conn.execute("PRAGMA table_info(feeds)")
        feed_cols = {r["name"] for r in await cur.fetchall()}
        assert "group_id" in feed_cols
        cur = await conn.execute("PRAGMA table_info(digests)")
        digest_cols = {r["name"] for r in await cur.fetchall()}
        assert "group_name" in digest_cols


async def test_deleting_group_ungroups_feeds(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    await db.init()
    async with db.connect() as conn:
        await conn.execute("INSERT INTO groups (name, position) VALUES ('AI', 1)")
        await conn.execute(
            "INSERT INTO feeds (url, title, group_id) VALUES ('https://a.example/rss', 'A', 1)"
        )
        await conn.commit()
        await conn.execute("DELETE FROM groups WHERE id = 1")
        await conn.commit()
        cur = await conn.execute("SELECT group_id FROM feeds WHERE url = 'https://a.example/rss'")
        row = await cur.fetchone()
    assert row is not None and row["group_id"] is None
