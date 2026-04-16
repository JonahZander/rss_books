from __future__ import annotations

import trafilatura


def extract_markdown(html: bytes, url: str) -> str | None:
    text = trafilatura.extract(
        html.decode("utf-8", errors="replace"),
        url=url,
        output_format="markdown",
        include_links=True,
        include_images=False,
        favor_recall=True,
    )
    return text
