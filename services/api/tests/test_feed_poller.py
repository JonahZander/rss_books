from pathlib import Path

from rss_kindle.db import Database
from rss_kindle.services.feed_poller import parse_feed, poll_feed_content

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"


def test_parse_feed_extracts_entries():
    content = FIXTURE.read_bytes()
    result = parse_feed(content)
    assert result.title == "Example Feed"
    assert len(result.entries) == 2
    assert result.entries[0].guid == "urn:example:first"
    assert result.entries[0].title == "First Post"
    assert result.entries[0].url == "https://example.com/first"
    assert "first post" in result.entries[0].summary.lower()


async def test_poll_feed_content_persists_new_articles(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    await db.init()
    async with db.connect() as conn:
        cur = await conn.execute(
            "INSERT INTO feeds (url, title) VALUES (?, ?)",
            ("https://example.com/rss", "Example"),
        )
        feed_id = cur.lastrowid
        await conn.commit()

    content = FIXTURE.read_bytes()
    count = await poll_feed_content(db, feed_id, content)
    assert count == 2

    count = await poll_feed_content(db, feed_id, content)
    assert count == 0

    async with db.connect() as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM articles")
        row = await cur.fetchone()
    assert row[0] == 2
