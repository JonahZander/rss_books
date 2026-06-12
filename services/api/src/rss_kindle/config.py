from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: Path = Field(default=Path("./data/rss_kindle.db"))
    epub_dir: Path = Field(default=Path("./data/epubs"))
    scheduler_enabled: bool = True
    # Directory holding the static-exported web app; when set, the API
    # serves the UI same-origin with an SPA fallback (single container).
    static_dir: Path | None = None

    # Optional overrides for users who keep SMTP credentials outside the DB.
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None


def get_settings() -> Settings:
    return Settings()
