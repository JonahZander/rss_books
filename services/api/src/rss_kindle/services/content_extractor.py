from __future__ import annotations

import trafilatura

from rss_kindle.services.sanitizer import sanitize


def extract_html(raw: bytes, url: str) -> str | None:
    """Extract the readable article from a page as sanitized HTML."""
    extracted = trafilatura.extract(
        raw.decode("utf-8", errors="replace"),
        url=url,
        output_format="html",
        include_links=True,
        include_images=True,
        favor_recall=True,
    )
    if not extracted:
        return None
    cleaned = sanitize(extracted).strip()
    return cleaned or None
