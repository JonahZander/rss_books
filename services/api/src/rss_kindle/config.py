from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: Path = Field(default=Path("./data/rss_kindle.db"))
    epub_dir: Path = Field(default=Path("./data/epubs"))


def get_settings() -> Settings:
    return Settings()
