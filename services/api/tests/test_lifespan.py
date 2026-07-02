import asyncio
from pathlib import Path

from rss_kindle.api.main import create_app
from rss_kindle.db import MIGRATIONS


async def test_concurrent_lifespans_on_fresh_db(tmp_path: Path) -> None:
    """api/serve.py runs HTTP and HTTPS uvicorn servers over one app, so the
    lifespan executes twice concurrently; on a fresh database both startups
    used to race the migration ladder and the loser crashed on migration 2."""
    app = create_app(db_path=tmp_path / "t.db")

    async def startup_cycle() -> None:
        async with app.router.lifespan_context(app):
            pass

    await asyncio.gather(startup_cycle(), startup_cycle())

    async with app.state.db.connect() as conn:
        cur = await conn.execute("PRAGMA user_version")
        row = await cur.fetchone()
    assert row is not None and int(row[0]) == len(MIGRATIONS)
