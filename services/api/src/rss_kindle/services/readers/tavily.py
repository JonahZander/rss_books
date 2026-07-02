"""Tavily Extract reader (https://tavily.com).

POSTs the URL to Tavily's `/extract` endpoint and renders the returned markdown
to HTML. `extract_depth="advanced"` keeps more structure (tables/code) at the
cost of more credits, worth it for the EPUB. Needs an API key.
"""

from __future__ import annotations

import httpx

from rss_kindle.models import AppSettings
from rss_kindle.services.readers.base import ReaderError, markdown_to_html

_ENDPOINT = "https://api.tavily.com/extract"
_TIMEOUT = 30.0


class TavilyReader:
    name = "tavily"

    def __init__(
        self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._api_key = api_key
        # `transport` is a test seam (inject httpx.MockTransport); None = network.
        self._transport = transport

    @classmethod
    def from_settings(cls, settings: AppSettings) -> TavilyReader | None:
        key = settings.tavily_api_key.strip()
        return cls(key) if key else None

    async def fetch_html(self, url: str) -> str | None:
        payload = {"urls": [url], "extract_depth": "advanced", "format": "markdown"}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT, transport=self._transport
            ) as client:
                r = await client.post(_ENDPOINT, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as e:
            raise ReaderError(f"tavily: {e}") from e
        results = data.get("results") or []
        if not results:
            return None
        raw = (results[0] or {}).get("raw_content")
        if not raw or not raw.strip():
            return None
        return markdown_to_html(raw)
