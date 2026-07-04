from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from rss_kindle.db import Database
from rss_kindle.models import AppSettings
from rss_kindle.services.scheduler import (
    Scheduler,
    feed_due,
    last_scheduled_occurrence,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"
NOW = datetime(2026, 6, 12, 8, 0, tzinfo=UTC)


def _feed(last_polled: str | None, interval: int = 30, failures: int = 0) -> dict:
    return {
        "last_polled": last_polled,
        "poll_interval_minutes": interval,
        "consecutive_failures": failures,
    }


def test_feed_due_math() -> None:
    assert feed_due(_feed(None), NOW) is True
    assert feed_due(_feed("2026-06-12 07:45:00"), NOW) is False  # 15 min ago, 30 min interval
    assert feed_due(_feed("2026-06-12 07:25:00"), NOW) is True  # 35 min ago
    # one failure doubles the wait: 35 min ago < 60 min backoff
    assert feed_due(_feed("2026-06-12 07:25:00", failures=1), NOW) is False
    # backoff caps at 24 h even with absurd failure counts
    assert feed_due(_feed("2026-06-10 07:00:00", failures=30), NOW) is True
    assert feed_due(_feed("2026-06-11 09:00:00", failures=30), NOW) is False  # 23 h ago


def test_last_scheduled_occurrence_daily_and_weekly() -> None:
    s = AppSettings(deadline_time="06:30")
    occ = last_scheduled_occurrence(s, NOW)
    assert occ == NOW.replace(hour=6, minute=30)
    occ = last_scheduled_occurrence(s, NOW.replace(hour=5))
    assert occ == NOW.replace(hour=6, minute=30) - timedelta(days=1)

    # weekly on Friday (4); 2026-06-12 is a Friday
    s = AppSettings(deadline_type="weekly", deadline_weekday=4, deadline_time="06:30")
    assert last_scheduled_occurrence(s, NOW) == NOW.replace(hour=6, minute=30)
    s = AppSettings(deadline_type="weekly", deadline_weekday=0, deadline_time="06:30")
    monday = NOW.replace(day=8, hour=6, minute=30)
    assert last_scheduled_occurrence(s, NOW) == monday


async def _seed_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "t.db")
    await db.init()
    return db


async def _add_feed(db: Database, url: str, **cols: object) -> int:
    fields = {"url": url, "title": url, **cols}
    names = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    async with db.connect() as conn:
        cur = await conn.execute(
            f"INSERT INTO feeds ({names}) VALUES ({marks})", tuple(fields.values())
        )
        await conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid


def _transport(state: dict) -> httpx.MockTransport:
    atom = FIXTURE.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        state.setdefault("requests", []).append(request)
        if request.url.host == "fresh.example":
            return httpx.Response(200, content=atom, headers={"ETag": 'W/"v1"'})
        if request.url.host == "cached.example":
            assert request.headers.get("If-None-Match") == 'W/"v1"'
            return httpx.Response(304)
        return httpx.Response(500)

    return httpx.MockTransport(handler)


async def test_tick_polls_due_feeds_with_conditional_get(tmp_path: Path) -> None:
    db = await _seed_db(tmp_path)
    fresh = await _add_feed(db, "https://fresh.example/rss")
    cached = await _add_feed(db, "https://cached.example/rss", etag='W/"v1"')
    not_due = await _add_feed(db, "https://fresh.example/other")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE feeds SET last_polled = ? WHERE id = ?",
            (NOW.strftime("%Y-%m-%d %H:%M:%S"), not_due),
        )
        await conn.commit()

    state: dict = {}
    sched = Scheduler(db, tmp_path / "epubs", now_fn=lambda: NOW + timedelta(minutes=1))
    async with httpx.AsyncClient(transport=_transport(state)) as client:
        await sched.tick(client)

    assert len(state["requests"]) == 2  # not_due skipped

    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT id, etag, last_polled, consecutive_failures FROM feeds"
        )
        feeds = {r["id"]: dict(r) for r in await cur.fetchall()}
        cur = await conn.execute("SELECT COUNT(*) AS n FROM articles")
        row = await cur.fetchone()
        assert row is not None and row["n"] == 2  # fixture has 2 entries, 304 added none

    assert feeds[fresh]["etag"] == 'W/"v1"'
    assert feeds[fresh]["last_polled"] is not None
    assert feeds[cached]["last_polled"] is not None
    assert feeds[cached]["consecutive_failures"] == 0


async def test_tick_records_failures_and_recovery(tmp_path: Path) -> None:
    db = await _seed_db(tmp_path)
    feed_id = await _add_feed(db, "https://broken.example/rss")
    sched = Scheduler(db, tmp_path / "epubs", now_fn=lambda: NOW)

    state: dict = {}
    async with httpx.AsyncClient(transport=_transport(state)) as client:
        await sched.tick(client)
    async with db.connect() as conn:
        cur = await conn.execute("SELECT last_error, consecutive_failures FROM feeds")
        row = await cur.fetchone()
    assert row is not None
    assert row["consecutive_failures"] == 1
    assert "500" in row["last_error"]

    # recovery: same feed now answers 200
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE feeds SET url = 'https://fresh.example/rss', last_polled = NULL "
            "WHERE id = ?",
            (feed_id,),
        )
        await conn.commit()
    async with httpx.AsyncClient(transport=_transport(state)) as client:
        await sched.tick(client)
    async with db.connect() as conn:
        cur = await conn.execute("SELECT last_error, consecutive_failures FROM feeds")
        row = await cur.fetchone()
    assert row is not None
    assert row["last_error"] is None
    assert row["consecutive_failures"] == 0


async def _queue_article(db: Database) -> int:
    feed_id = await _add_feed(db, "https://feed.example/rss")
    async with db.connect() as conn:
        cur = await conn.execute(
            "INSERT INTO articles (feed_id, guid, title, url, summary) "
            "VALUES (?, 'g1', 'T', 'https://feed.example/a', '<p>s</p>')",
            (feed_id,),
        )
        article_id = cur.lastrowid
        assert article_id is not None
        await conn.execute(
            "INSERT INTO digest_queue (article_id, position) VALUES (?, 0)", (article_id,)
        )
        await conn.commit()
        return article_id


async def test_press_deadline_fires_once_then_skips(tmp_path: Path) -> None:
    db = await _seed_db(tmp_path)
    await _queue_article(db)
    settings = AppSettings(deadline_enabled=True, deadline_time="06:30")
    sched = Scheduler(db, tmp_path / "epubs", now_fn=lambda: NOW)

    await sched._press_deadline(settings)
    async with db.connect() as conn:
        cur = await conn.execute("SELECT status FROM digests")
        digests = [r["status"] for r in await cur.fetchall()]
        cur = await conn.execute("SELECT COUNT(*) AS n FROM digest_queue")
        row = await cur.fetchone()
    assert digests == ["ready"]
    assert row is not None and row["n"] == 0  # queue cleared

    # same occurrence: no second edition
    await sched._press_deadline(settings)
    async with db.connect() as conn:
        cur = await conn.execute("SELECT COUNT(*) AS n FROM digests")
        row = await cur.fetchone()
    assert row is not None and row["n"] == 1

    # next day fires again, but the queue is empty, so it skips silently
    next_day = Scheduler(db, tmp_path / "epubs", now_fn=lambda: NOW + timedelta(days=1))
    await next_day._press_deadline(settings)
    async with db.connect() as conn:
        cur = await conn.execute("SELECT COUNT(*) AS n FROM digests")
        row = await cur.fetchone()
    assert row is not None and row["n"] == 1


async def test_press_deadline_split_per_group(tmp_path: Path) -> None:
    db = await _seed_db(tmp_path)
    async with db.connect() as conn:
        await conn.execute("INSERT INTO groups (name, position) VALUES ('AI', 1)")
        await conn.execute("INSERT INTO groups (name, position) VALUES ('Gaming', 2)")
        await conn.commit()
    ai_feed = await _add_feed(db, "https://ai.example/rss", group_id=1)
    gaming_feed = await _add_feed(db, "https://gaming.example/rss", group_id=2)
    async with db.connect() as conn:
        for position, (feed_id, guid) in enumerate(((ai_feed, "g1"), (gaming_feed, "g2"))):
            cur = await conn.execute(
                "INSERT INTO articles (feed_id, guid, title, url, summary) "
                "VALUES (?, ?, 'T', 'https://x', '<p>s</p>')",
                (feed_id, guid),
            )
            await conn.execute(
                "INSERT INTO digest_queue (article_id, position) VALUES (?, ?)",
                (cur.lastrowid, position),
            )
        await conn.commit()

    settings = AppSettings(
        deadline_enabled=True, deadline_time="06:30", deadline_split="per_group"
    )
    sched = Scheduler(db, tmp_path / "epubs", now_fn=lambda: NOW)
    await sched._press_deadline(settings)

    async with db.connect() as conn:
        cur = await conn.execute("SELECT title, status, group_name FROM digests ORDER BY id")
        digests = [dict(r) for r in await cur.fetchall()]
        cur = await conn.execute("SELECT COUNT(*) AS n FROM digest_queue")
        row = await cur.fetchone()
    assert [d["group_name"] for d in digests] == ["AI", "Gaming"]
    assert all(d["status"] == "ready" for d in digests)
    assert all(" - " in d["title"] for d in digests)
    assert row is not None and row["n"] == 0


async def test_press_deadline_records_run_even_when_compile_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """The queue is drained by create_digest_records regardless of compile
    outcome, so a build failure must not leave _last_deadline_run unset -
    that would retry every tick against an already-empty queue. The failed
    digest itself is left for the Editions page to re-press."""
    import rss_kindle.services.scheduler as scheduler_module

    async def failing_generate(db: Database, digest_id: int, epub_dir: Path) -> bool:
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE digests SET status = 'failed', error = 'boom' WHERE id = ?",
                (digest_id,),
            )
            await conn.commit()
        return False

    monkeypatch.setattr(scheduler_module, "generate_digest", failing_generate)

    db = await _seed_db(tmp_path)
    await _queue_article(db)
    settings = AppSettings(deadline_enabled=True, deadline_time="06:30")
    sched = Scheduler(db, tmp_path / "epubs", now_fn=lambda: NOW)

    await sched._press_deadline(settings)

    async with db.connect() as conn:
        cur = await conn.execute("SELECT status FROM digests")
        digests = [r["status"] for r in await cur.fetchall()]
    assert digests == ["failed"]
    from rss_kindle.services.settings_store import get_value

    assert await get_value(db, "_last_deadline_run") is not None

    # same occurrence: no retry against the (already-empty) queue
    await sched._press_deadline(settings)
    async with db.connect() as conn:
        cur = await conn.execute("SELECT COUNT(*) AS n FROM digests")
        row = await cur.fetchone()
    assert row is not None and row["n"] == 1


async def test_press_deadline_records_run_on_empty_queue(tmp_path: Path) -> None:
    db = await _seed_db(tmp_path)
    settings = AppSettings(deadline_enabled=True, deadline_time="06:30")
    sched = Scheduler(db, tmp_path / "epubs", now_fn=lambda: NOW)

    await sched._press_deadline(settings)

    from rss_kindle.services.settings_store import get_value

    assert await get_value(db, "_last_deadline_run") is not None


async def test_retention_preserves_queued_and_digested(tmp_path: Path) -> None:
    db = await _seed_db(tmp_path)
    feed_id = await _add_feed(db, "https://feed.example/rss")
    async with db.connect() as conn:
        for guid in ("old-loose", "old-queued", "old-digested", "new-loose"):
            age = "-200 days" if guid.startswith("old") else "-1 days"
            await conn.execute(
                "INSERT INTO articles (feed_id, guid, title, url, created_at) "
                "VALUES (?, ?, ?, 'https://x', datetime('now', ?))",
                (feed_id, guid, guid, age),
            )
        cur = await conn.execute("SELECT id, guid FROM articles")
        by_guid = {r["guid"]: r["id"] for r in await cur.fetchall()}
        await conn.execute(
            "INSERT INTO digest_queue (article_id, position) VALUES (?, 0)",
            (by_guid["old-queued"],),
        )
        await conn.execute("INSERT INTO digests (title, status) VALUES ('d', 'ready')")
        await conn.execute(
            "INSERT INTO digest_articles (digest_id, article_id, position) VALUES (1, ?, 0)",
            (by_guid["old-digested"],),
        )
        await conn.commit()

    sched = Scheduler(db, tmp_path / "epubs", now_fn=lambda: NOW)
    await sched._retention(AppSettings(retention_days=90))

    async with db.connect() as conn:
        cur = await conn.execute("SELECT guid FROM articles ORDER BY guid")
        remaining = {r["guid"] for r in await cur.fetchall()}
    assert remaining == {"old-queued", "old-digested", "new-loose"}

    # runs at most once per day
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO articles (feed_id, guid, title, url, created_at) "
            "VALUES (?, 'old-again', 'x', 'https://x', datetime('now', '-200 days'))",
            (feed_id,),
        )
        await conn.commit()
    await sched._retention(AppSettings(retention_days=90))
    async with db.connect() as conn:
        cur = await conn.execute("SELECT COUNT(*) AS n FROM articles WHERE guid = 'old-again'")
        row = await cur.fetchone()
    assert row is not None and row["n"] == 1


async def test_retention_prunes_image_cache(tmp_path: Path) -> None:
    import os
    import time

    db = await _seed_db(tmp_path)
    cache = tmp_path / "epubs" / ".image_cache"
    cache.mkdir(parents=True)
    old = cache / "old.bin"
    fresh = cache / "fresh.bin"
    old.write_bytes(b"x")
    fresh.write_bytes(b"y")
    stale = time.time() - 200 * 86400
    os.utime(old, (stale, stale))

    sched = Scheduler(db, tmp_path / "epubs", now_fn=lambda: NOW)
    await sched._retention(AppSettings(retention_days=90))

    assert not old.exists()
    assert fresh.exists()
