"""Reader fallback registry.

`build_reader(settings)` returns the provider chosen by `settings.reader_fallback`,
or None when disabled/unconfigured. To add a service: write a provider class with
a `name`, an async `fetch_html(url)`, and a `from_settings(settings)` factory (see
`tavily.py`), then add one line to `_REGISTRY`.

See `base.py` for the provider contract and the attribution for this pattern.
"""

from __future__ import annotations

from collections.abc import Callable

from rss_books.models import AppSettings
from rss_books.services.readers.base import (
    ReaderError,
    ReaderProvider,
    markdown_to_html,
)
from rss_books.services.readers.jina import JinaReader
from rss_books.services.readers.tavily import TavilyReader

# name -> factory(settings) -> provider | None (None = selected but unconfigured)
_REGISTRY: dict[str, Callable[[AppSettings], ReaderProvider | None]] = {
    TavilyReader.name: TavilyReader.from_settings,
    JinaReader.name: JinaReader.from_settings,
}


def build_reader(settings: AppSettings) -> ReaderProvider | None:
    """The configured reader fallback, or None when disabled/unconfigured."""
    factory = _REGISTRY.get(settings.reader_fallback)
    return factory(settings) if factory is not None else None


def provider_names() -> list[str]:
    """Registered provider names (excludes the "none" sentinel)."""
    return list(_REGISTRY)


__all__ = [
    "ReaderError",
    "ReaderProvider",
    "build_reader",
    "markdown_to_html",
    "provider_names",
]
