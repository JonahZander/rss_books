"""Pluggable full-text reader fallbacks — the provider contract.

When the direct, browser-impersonating fetch (`articles.fetch_url_bytes`) is
blocked or yields nothing, the article fetcher can hand the URL to an external
extraction service. Each service is a small provider with a single method,
selected by name from settings, so adding another is one class plus one entry
in the registry (see `__init__.py`).

The provider-registry shape here — name-keyed providers chosen from config with
a graceful fall-through when unconfigured — is adapted from NousResearch's
hermes-agent `tools/web_tools.py` (MIT, Copyright (c) 2025 Nous Research):
https://github.com/NousResearch/hermes-agent
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from markdown_it import MarkdownIt


class ReaderError(Exception):
    """A reader provider could not return usable content for a URL.

    Raised for transport/credential failures so the caller can fall back to the
    original fetch error instead of surfacing a provider-specific crash.
    """


@runtime_checkable
class ReaderProvider(Protocol):
    """One external extraction service. `name` doubles as its registry key."""

    name: str

    async def fetch_html(self, url: str) -> str | None:
        """Return article HTML for `url`, or None when nothing was extracted."""
        ...


# Reader services return clean markdown/text, not structured HTML; we render it
# and the caller sanitizes the result (the nh3 allowlist is the contract for all
# stored HTML). `html: True` lets any inline HTML through to that sanitizer.
_MD = MarkdownIt("commonmark", {"html": True})


def markdown_to_html(markdown: str) -> str:
    """Render provider markdown to HTML (unsanitized — the caller sanitizes)."""
    return _MD.render(markdown)
