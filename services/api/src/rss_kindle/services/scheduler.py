from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from rss_kindle.db import Database
from rss_kindle.models import AppSettings
from rss_kindle.services.digest_service import create_digest_record, generate_digest
from rss_kindle.services.poller import USER_AGENT, poll_feed
from rss_kindle.services.settings_store import get_app_settings, get_value, set_value

logger = logging.getLogger(__name__)

TICK_SECONDS = 60
POLL_CONCURRENCY = 5
BACKOFF_CAP = timedelta(hours=24)


def parse_db_datetime(value: str | None) -> datetime | None:
    """SQLite CURRENT_TIMESTAMP is naive UTC ('YYYY-MM-DD HH:MM:SS');
    feed entries are stored as ISO strings that may carry an offset."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("T", " "))
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def feed_due(feed: Mapping[str, Any], now: datetime) -> bool:
    last = parse_db_datetime(feed["last_polled"])
    if last is None:
        return True
    interval = timedelta(minutes=feed["poll_interval_minutes"] or 30)
    failures = min(int(feed["consecutive_failures"] or 0), 10)
    wait = min(interval * (2**failures), BACKOFF_CAP)
    return now >= last + wait


def last_scheduled_occurrence(settings: AppSettings, now: datetime) -> datetime:
    """The most recent press-deadline occurrence at or before `now` (same tz)."""
    hour, minute = (int(part) for part in settings.deadline_time.split(":"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if settings.deadline_type == "weekly":
        days_back = (now.weekday() - settings.deadline_weekday) % 7
        candidate -= timedelta(days=days_back)
        if candidate > now:
            candidate -= timedelta(days=7)
    elif candidate > now:
        candidate -= timedelta(days=1)
    return candidate


class Scheduler:
    """In-process loop: due-feed polling with backoff, the press deadline,
    and daily retention. Pure logic lives in tick() so tests can drive it
    with an injected clock and HTTP client — no sleeping."""

    def __init__(
        self,
        db: Database,
        epub_dir: Path,
        *,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self.epub_dir = epub_dir
        self.now_fn = now_fn or (lambda: datetime.now().astimezone())

    async def tick(self, client: httpx.AsyncClient | None = None) -> None:
        settings = await get_app_settings(self.db)
        if settings.poll_enabled:
            if client is None:
                async with httpx.AsyncClient(
                    timeout=20.0,
                    follow_redirects=True,
                    headers={"User-Agent": USER_AGENT},
                ) as own_client:
                    await self._poll_due_feeds(own_client)
            else:
                await self._poll_due_feeds(client)
        await self._press_deadline(settings)
        await self._retention(settings)

    async def _poll_due_feeds(self, client: httpx.AsyncClient) -> None:
        now = self.now_fn()
        async with self.db.connect() as conn:
            cur = await conn.execute(
                "SELECT id, url, etag, last_modified, last_polled, "
                "poll_interval_minutes, consecutive_failures FROM feeds"
            )
            rows = await cur.fetchall()
        due = [dict(r) for r in rows if feed_due(r, now)]
        if not due:
            return

        semaphore = asyncio.Semaphore(POLL_CONCURRENCY)

        async def bounded(feed: dict[str, Any]) -> Any:
            async with semaphore:
                return await poll_feed(self.db, client, feed)

        results = await asyncio.gather(*(bounded(feed) for feed in due))
        new_articles = sum(r.inserted for r in results)
        errors = sum(1 for r in results if r.error)
        logger.info(
            "polled %d/%d feeds: %d new articles, %d errors",
            len(due),
            len(rows),
            new_articles,
            errors,
        )

    async def _press_deadline(self, settings: AppSettings) -> None:
        if not settings.deadline_enabled:
            return
        now = self.now_fn()
        occurrence = last_scheduled_occurrence(settings, now)
        last_run = parse_db_datetime(await get_value(self.db, "_last_deadline_run"))
        if last_run is not None and last_run >= occurrence:
            return
        await set_value(self.db, "_last_deadline_run", occurrence.isoformat())
        try:
            digest_id = await create_digest_record(
                self.db, None, now.date().isoformat()
            )
        except ValueError:
            logger.info("press deadline: queue empty, skipping edition")
            return
        logger.info("press deadline: compiling edition %d", digest_id)
        await generate_digest(self.db, digest_id, self.epub_dir)

    async def _retention(self, settings: AppSettings) -> None:
        if not settings.retention_enabled:
            return
        today = self.now_fn().date().isoformat()
        if await get_value(self.db, "_last_retention_run") == today:
            return
        await set_value(self.db, "_last_retention_run", today)
        async with self.db.connect() as conn:
            cur = await conn.execute(
                "DELETE FROM articles WHERE created_at < datetime('now', ?) "
                "AND id NOT IN (SELECT article_id FROM digest_queue) "
                "AND id NOT IN (SELECT article_id FROM digest_articles)",
                (f"-{settings.retention_days} days",),
            )
            await conn.commit()
            deleted = cur.rowcount
        if deleted:
            logger.info(
                "retention: deleted %d articles older than %d days",
                deleted,
                settings.retention_days,
            )

    async def run(self, stop: asyncio.Event) -> None:
        # startup jitter so several instances (or quick restarts) don't
        # hammer every feed at the same instant
        try:
            await asyncio.wait_for(stop.wait(), timeout=random.uniform(0, 5))
            return
        except TimeoutError:
            pass
        logger.info("scheduler started (tick every %ds)", TICK_SECONDS)
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=TICK_SECONDS)
            except TimeoutError:
                continue
