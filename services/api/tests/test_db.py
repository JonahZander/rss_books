from pathlib import Path

from rss_kindle.db import Database


async def test_init_creates_tables(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    await db.init()
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cur.fetchall()
    names = {r[0] for r in rows}
    assert {"feeds", "articles", "digests", "digest_articles"}.issubset(names)
