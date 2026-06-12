from pathlib import Path

import aiosqlite

from rss_kindle.db import MIGRATIONS, SCHEMA_V1, Database


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
