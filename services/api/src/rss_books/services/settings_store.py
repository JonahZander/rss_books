from __future__ import annotations

import json
from typing import Literal, cast

from rss_books.config import Settings, get_settings
from rss_books.db import Database
from rss_books.models import AppSettings


async def get_app_settings(db: Database, env: Settings | None = None) -> AppSettings:
    """Settings rows merged over model defaults, with env-var SMTP overrides on top."""
    async with db.connect() as conn:
        cur = await conn.execute("SELECT key, value FROM settings")
        rows = await cur.fetchall()
    stored = {
        r["key"]: json.loads(r["value"])
        for r in rows
        if r["key"] in AppSettings.model_fields
    }
    settings = AppSettings.model_validate(stored)

    env = env or get_settings()
    if env.smtp_host is not None:
        settings.smtp_host = env.smtp_host
    if env.smtp_port is not None:
        settings.smtp_port = env.smtp_port
    if env.smtp_username is not None:
        settings.smtp_username = env.smtp_username
    if env.smtp_password is not None:
        settings.smtp_password = env.smtp_password
    if env.smtp_from is not None:
        settings.smtp_from = env.smtp_from
    if env.tavily_api_key is not None:
        settings.tavily_api_key = env.tavily_api_key
    if env.reader_fallback in ("none", "tavily", "jina"):
        settings.reader_fallback = cast(Literal["none", "tavily", "jina"], env.reader_fallback)
    return settings


async def save_app_settings(db: Database, settings: AppSettings) -> None:
    async with db.connect() as conn:
        for key, value in settings.model_dump().items():
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )
        await conn.commit()


async def get_value(db: Database, key: str) -> str | None:
    """Raw access for internal bookkeeping keys (prefixed with '_')."""
    async with db.connect() as conn:
        cur = await conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cur.fetchone()
    return str(row["value"]) if row else None


async def set_value(db: Database, key: str, value: str) -> None:
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await conn.commit()
