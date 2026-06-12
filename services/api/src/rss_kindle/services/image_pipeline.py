from __future__ import annotations

import html as html_lib
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urljoin

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

IMG_TAG_RE = re.compile(r"<img\b[^>]*/?>", re.IGNORECASE)
SRC_RE = re.compile(r'\bsrc="([^"]*)"', re.IGNORECASE)
ALT_RE = re.compile(r'\balt="([^"]*)"', re.IGNORECASE)


@dataclass
class DigestImage:
    filename: str
    media_type: str
    data: bytes


def _recompress(data: bytes, *, max_width: int, jpeg_quality: int) -> tuple[bytes, str, str]:
    """Downscale and recompress; returns (bytes, extension, media type).

    JPEG for opaque images, PNG only when transparency would be lost.
    Raises on undecodable input.
    """
    img = Image.open(BytesIO(data))
    img.load()
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    if img.width > max_width:
        new_height = max(1, round(img.height * max_width / img.width))
        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
    buf = BytesIO()
    if has_alpha:
        img.convert("RGBA").save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "png", "image/png"
    img.convert("RGB").save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    return buf.getvalue(), "jpg", "image/jpeg"


async def prepare_images(
    articles: list[tuple[str, str]],
    client: httpx.AsyncClient,
    *,
    max_width: int = 1200,
    jpeg_quality: int = 75,
    per_article_budget: int = 10 * 2**20,
) -> tuple[list[str], dict[str, DigestImage]]:
    """Download, downscale and pack the images referenced by digest articles.

    Takes (sanitized_html, article_url) pairs; returns the HTML with image
    sources rewritten to packed `images/img_NNN.*` paths, plus the images
    keyed by resolved source URL. Images that fail to fetch/decode or blow
    the per-article byte budget are dropped (their tags removed).
    """
    fetched: dict[str, tuple[bytes, str, str] | None] = {}
    packed: dict[str, DigestImage] = {}
    rewritten: list[str] = []

    async def fetch(url: str) -> tuple[bytes, str, str] | None:
        if url in fetched:
            return fetched[url]
        result: tuple[bytes, str, str] | None = None
        try:
            r = await client.get(url)
            r.raise_for_status()
            result = _recompress(r.content, max_width=max_width, jpeg_quality=jpeg_quality)
        except Exception as exc:
            logger.warning("image dropped (%s): %s", url, exc)
        fetched[url] = result
        return result

    for html, base_url in articles:
        budget = per_article_budget
        parts: list[str] = []
        cursor = 0
        for m in IMG_TAG_RE.finditer(html):
            parts.append(html[cursor : m.start()])
            cursor = m.end()
            tag = m.group(0)

            src_match = SRC_RE.search(tag)
            if src_match is None:
                continue
            resolved = urljoin(base_url, html_lib.unescape(src_match.group(1)))
            if not resolved.startswith(("http://", "https://")):
                continue
            result = await fetch(resolved)
            if result is None:
                continue
            data, ext, media_type = result
            if len(data) > budget:
                logger.warning(
                    "image dropped (%s): over per-article budget (%d > %d remaining)",
                    resolved,
                    len(data),
                    budget,
                )
                continue
            budget -= len(data)
            if resolved not in packed:
                packed[resolved] = DigestImage(
                    filename=f"images/img_{len(packed) + 1:03d}.{ext}",
                    media_type=media_type,
                    data=data,
                )
            alt_match = ALT_RE.search(tag)
            alt = alt_match.group(1) if alt_match else ""
            parts.append(f'<img src="{packed[resolved].filename}" alt="{alt}"/>')
        parts.append(html[cursor:])
        rewritten.append("".join(parts))

    return rewritten, packed
