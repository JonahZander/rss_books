from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# One UA for everything we fetch from the public web (feeds, articles,
# images). Browser-shaped so naive bot filters pass us — plenty of sites 403
# bare tool UAs — with our name kept at the end so site owners can still
# identify the traffic. Determined bot walls (TLS fingerprinting, JS
# challenges) will 403 regardless; those map to a 502 and the feed-summary
# fallback rather than an error page.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 rss-kindle-selector/1.1"
)


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
