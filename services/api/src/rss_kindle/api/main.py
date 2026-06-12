from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from rss_kindle.config import get_settings
from rss_kindle.db import Database
from rss_kindle.services.scheduler import Scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def create_app(db_path: Path | None = None) -> FastAPI:
    settings = get_settings()
    db = Database(db_path or settings.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.path.parent.mkdir(parents=True, exist_ok=True)
        settings.epub_dir.mkdir(parents=True, exist_ok=True)
        await db.init()

        scheduler_task: asyncio.Task[None] | None = None
        scheduler_stop = asyncio.Event()
        # guard against double-start (e.g. the module imported twice under --reload)
        if settings.scheduler_enabled and getattr(app.state, "scheduler_task", None) is None:
            scheduler = Scheduler(db, settings.epub_dir)
            scheduler_task = asyncio.create_task(scheduler.run(scheduler_stop))
            app.state.scheduler_task = scheduler_task

        yield

        if scheduler_task is not None:
            scheduler_stop.set()
            await scheduler_task
            app.state.scheduler_task = None

    app = FastAPI(title="RSS Kindle Selector", lifespan=lifespan)
    app.state.db = db
    app.state.settings = settings

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    from rss_kindle.api.articles import router as articles_router
    from rss_kindle.api.digests import router as digests_router
    from rss_kindle.api.feeds import router as feeds_router
    from rss_kindle.api.opds import router as opds_router
    from rss_kindle.api.queue import router as queue_router
    from rss_kindle.api.settings import router as settings_router

    app.include_router(feeds_router)
    app.include_router(articles_router)
    app.include_router(queue_router)
    app.include_router(digests_router)
    app.include_router(settings_router)
    app.include_router(opds_router)

    return app


app = create_app()
