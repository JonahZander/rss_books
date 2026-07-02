from __future__ import annotations

import asyncio
import importlib.metadata
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

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
        # TRIPWIRE: in production we run two uvicorn servers (HTTP + HTTPS) over
        # this one app (see api/serve.py), so this lifespan executes TWICE per
        # process. Any startup work added here must be idempotent or guarded
        # (see the scheduler guard below); otherwise it runs twice.
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

    app = FastAPI(title="RSS Books", lifespan=lifespan)
    app.state.db = db
    app.state.settings = settings

    @app.get("/health")
    async def health() -> dict[str, str]:
        try:
            async with db.connect() as conn:
                await conn.execute("SELECT 1")
            db_status = "ok"
        except Exception as exc:
            db_status = f"error: {exc}"
        try:
            version = importlib.metadata.version("rss-books-api")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
        return {
            "status": "ok" if db_status == "ok" else "degraded",
            "version": version,
            "db": db_status,
        }

    from rss_kindle.api.articles import router as articles_router
    from rss_kindle.api.digests import router as digests_router
    from rss_kindle.api.feeds import router as feeds_router
    from rss_kindle.api.groups import router as groups_router
    from rss_kindle.api.opds import router as opds_router
    from rss_kindle.api.queue import router as queue_router
    from rss_kindle.api.settings import router as settings_router

    app.include_router(feeds_router)
    app.include_router(groups_router)
    app.include_router(articles_router)
    app.include_router(queue_router)
    app.include_router(digests_router)
    app.include_router(settings_router)
    app.include_router(opds_router)

    static_dir = settings.static_dir
    if static_dir is not None and static_dir.is_dir():
        static_root = static_dir.resolve()

        # Next prefetches routes with HEAD, so register both methods
        @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            index = static_root / "index.html"
            if not path:
                return FileResponse(index)
            candidate = (static_root / path).resolve()
            if not candidate.is_relative_to(static_root):
                return FileResponse(index)
            if candidate.is_file():
                return FileResponse(candidate)
            with_html = static_root / f"{path}.html"
            if with_html.is_file():
                return FileResponse(with_html)
            nested_index = candidate / "index.html"
            if nested_index.is_file():
                return FileResponse(nested_index)
            return FileResponse(index)

        logger = logging.getLogger(__name__)
        logger.info("serving static web app from %s", static_root)

    return app


app = create_app()
