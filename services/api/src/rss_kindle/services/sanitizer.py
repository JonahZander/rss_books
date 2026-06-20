from __future__ import annotations

import nh3

# The shared HTML vocabulary for everything we store and render: the web UI
# injects this markup directly and the EPUB builder embeds it, so the
# allowlist is the contract between extraction and both consumers.
ALLOWED_TAGS = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "em",
    "strong",
    "a",
    "img",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "figure",
    "figcaption",
    "hr",
    "br",
}

ALLOWED_ATTRIBUTES = {
    "a": {"href"},
    "img": {"src", "alt"},
}


def sanitize(html: str) -> str:
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https"},
        link_rel="noopener noreferrer",
    )


def sanitize_or_none(html: str) -> str | None:
    """Sanitize, then collapse an empty result to None — the shape extraction
    paths want when "nothing usable was left" must be distinguishable from "".
    """
    return sanitize(html).strip() or None
