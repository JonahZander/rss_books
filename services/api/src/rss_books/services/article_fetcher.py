"""Shared article retrieval, the one mechanism Preview and Compile both use.

`fetch_article_content` is the full ladder: a browser-impersonating direct fetch
(curl_cffi, defeats JA3/JA4 TLS fingerprinting), trafilatura extraction, and a
configured reader fallback (Tavily/Jina) when the site blocks us or yields
nothing. `fetch_many` runs a batch politely: different hosts in parallel, but
same-host requests spaced by a jittered delay so a compile doesn't hammer one
domain.
"""

from __future__ import annotations

import asyncio
import random
from urllib.parse import urljoin, urlsplit

from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import HTTPError, RequestException

from rss_books.config import get_settings
from rss_books.models import AppSettings
from rss_books.services.content_extractor import extract_html
from rss_books.services.net_guard import SSRFBlockedError, check_target, guard_config_from_settings
from rss_books.services.readers import ReaderError, build_reader
from rss_books.services.sanitizer import sanitize_or_none

# Politeness window between two requests to the SAME host during a batch compile.
# Jitter (uniform 0..JITTER) avoids a lockstep cadence a WAF could pattern-match.
SAME_HOST_DELAY_SECONDS = 2.0
SAME_HOST_JITTER_SECONDS = 1.0

REDIRECT_STATUS_CODES = (301, 302, 303, 307, 308)
# curl_cffi has no transport-level hook to re-check each redirect hop like
# httpx's, so redirects are followed manually (allow_redirects=False) with
# the SSRF guard re-run before every hop, capped against redirect loops.
MAX_REDIRECTS = 5


async def fetch_url_bytes(url: str) -> bytes:
    """Fetch a URL, following redirects one hop at a time so the SSRF guard
    sees (and can block) every hop, not just the first request."""
    cfg = guard_config_from_settings(get_settings())
    # Modern WAFs fingerprint the TLS handshake (JA3/JA4) and reject any
    # non-browser client regardless of User-Agent, so we impersonate Chrome
    # at the transport layer rather than just spoofing the UA header.
    async with AsyncSession() as session:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            await check_target(current, cfg)
            r = await session.get(
                current, impersonate="chrome", timeout=20, allow_redirects=False
            )
            location = r.headers.get("location")
            if r.status_code in REDIRECT_STATUS_CODES and location:
                current = urljoin(current, location)
                continue
            r.raise_for_status()
            return r.content
    # RequestException so callers degrade the same way curl_cffi's own
    # redirect cap did: summary fallback / 502, never a failed compile.
    raise RequestException(f"too many redirects (> {MAX_REDIRECTS} hops): {url}")


async def fetch_article_content(url: str, settings: AppSettings) -> str | None:
    """Browser-impersonating fetch → extract → reader fallback. None if all fail."""
    content: str | None = None
    try:
        raw = await fetch_url_bytes(url)
        content = extract_html(raw, url=url)
    except (HTTPError, RequestException, SSRFBlockedError):
        content = None
    if not content:
        reader = build_reader(settings)
        if reader is not None:
            try:
                extracted = await reader.fetch_html(url)
            except ReaderError:
                extracted = None
            if extracted:
                content = sanitize_or_none(extracted)
    return content


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


async def fetch_many(urls: list[str], settings: AppSettings) -> dict[str, str | None]:
    """Politely fetch a batch, returning {url: content-or-None}.

    Requests to different hosts run concurrently; requests sharing a host run
    sequentially with a jittered delay between them (no leading delay on the
    first of each host). Duplicate urls are fetched once.
    """
    by_host: dict[str, list[str]] = {}
    for url in dict.fromkeys(urls):  # de-dupe, preserve order
        by_host.setdefault(_host(url), []).append(url)

    results: dict[str, str | None] = {}

    async def drain_host(host_urls: list[str]) -> None:
        for i, url in enumerate(host_urls):
            if i:
                await asyncio.sleep(
                    SAME_HOST_DELAY_SECONDS + random.uniform(0, SAME_HOST_JITTER_SECONDS)
                )
            results[url] = await fetch_article_content(url, settings)

    await asyncio.gather(*(drain_host(group) for group in by_host.values()))
    return results
