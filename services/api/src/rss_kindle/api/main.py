from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rss_kindle.config import get_settings
from rss_kindle.db import Database


def create_app(db_path: Path | None = None) -> FastAPI:
    settings = get_settings()
    db = Database(db_path or settings.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.path.parent.mkdir(parents=True, exist_ok=True)
        settings.epub_dir.mkdir(parents=True, exist_ok=True)
        await db.init()
        yield

    app = FastAPI(title="RSS Kindle Selector", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3737"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.db = db
    app.state.settings = settings

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    from rss_kindle.api.feeds import router as feeds_router

    app.include_router(feeds_router)

    return app


app = create_app()
