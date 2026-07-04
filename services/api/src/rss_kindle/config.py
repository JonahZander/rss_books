from __future__ import annotations

from pathlib import Path

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from rss_kindle.services.net_guard import GuardedAsyncTransport, guard_config_from_settings

# One UA for everything we fetch from the public web (feeds, articles,
# images). Browser-shaped so naive bot filters pass us (plenty of sites 403
# bare tool UAs), with our name kept at the end so site owners can still
# identify the traffic. Determined bot walls (TLS fingerprinting, JS
# challenges) will 403 regardless; those map to a 502 and the feed-summary
# fallback rather than an error page.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 rss-books/1.1"
)


def make_http_client(**overrides: object) -> httpx.AsyncClient:
    """The standard async client for fetching feeds/articles/images: our UA,
    redirects followed, a 20s timeout, and the SSRF guard on the transport
    (checks the target - and, since httpx re-invokes the transport per hop,
    every redirect - before connecting). One place so every fetch path agrees."""
    kwargs: dict[str, object] = {
        "timeout": 20.0,
        "follow_redirects": True,
        "headers": {"User-Agent": USER_AGENT},
    }
    kwargs.update(overrides)
    kwargs.setdefault(
        "transport", GuardedAsyncTransport(guard_config_from_settings(get_settings()))
    )
    return httpx.AsyncClient(**kwargs)  # type: ignore[arg-type]


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

    # Optional reader-fallback config for headless/Docker setups without the UI.
    tavily_api_key: str | None = None
    reader_fallback: str | None = None

    # SSRF guard on every outbound fetch of a user-supplied URL (feeds,
    # articles, images): blocks private/loopback/link-local/reserved/
    # multicast addresses. Env-only (not a DB/UI toggle) because the API has
    # no auth - a remotely-toggleable setting would let any LAN client
    # disable the one thing standing between "app reachable" and "LAN/cloud-
    # metadata reachable". Enabled by default; homelab users polling
    # LAN-hosted feeds should add them to ssrf_allowed_hosts rather than
    # disabling the guard outright.
    ssrf_guard_enabled: bool = True
    # Comma-separated hostnames, bare IPs, or CIDR ranges exempted from the
    # guard (e.g. "192.168.1.50,nas.lan,10.0.0.0/8").
    ssrf_allowed_hosts: str = ""

    # Serving: plain HTTP for the same-origin UI, plus an optional HTTPS
    # listener for clients that only speak TLS (e.g. the Crosspoint e-reader,
    # whose OPDS client forces https://). Both run in one process sharing one
    # app, so the scheduler/poller still run exactly once.
    http_port: int = 8765
    https_port: int = 8443
    tls_enabled: bool = True
    tls_cert_file: Path = Field(default=Path("./data/certs/server.crt"))
    tls_key_file: Path = Field(default=Path("./data/certs/server.key"))
    # Extra IPs to embed as SAN entries in the auto-generated self-signed cert,
    # comma-separated (e.g. "192.168.0.138"). Only matters for clients that
    # verify the hostname; clients that skip verification ignore this.
    tls_san_ips: str = ""


def get_settings() -> Settings:
    return Settings()
