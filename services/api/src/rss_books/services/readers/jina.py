"""Jina Reader (https://jina.ai/reader).

GETs `https://r.jina.ai/<url>` and renders the returned markdown to HTML. Free
and keyless on the public tier (rate-limited), so selecting it is enough, with no
API key to configure.
"""

from __future__ import annotations

import httpx

from rss_books.models import AppSettings
from rss_books.services.readers.base import ReaderError, markdown_to_html

_ENDPOINT = "https://r.jina.ai/"
_TIMEOUT = 30.0


class JinaReader:
    name = "jina"

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # `transport` is a test seam (inject httpx.MockTransport); None = network.
        self._transport = transport

    @classmethod
    def from_settings(cls, settings: AppSettings) -> JinaReader | None:
        return cls()

    async def fetch_html(self, url: str) -> str | None:
        headers = {"Accept": "application/json", "X-Return-Format": "markdown"}
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT, transport=self._transport, follow_redirects=True
            ) as client:
                r = await client.get(f"{_ENDPOINT}{url}", headers=headers)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as e:
            raise ReaderError(f"jina: {e}") from e
        content = (data.get("data") or {}).get("content")
        if not content or not content.strip():
            return None
        return markdown_to_html(content)
