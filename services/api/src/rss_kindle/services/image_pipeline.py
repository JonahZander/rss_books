from __future__ import annotations

import asyncio
import hashlib
import html as html_lib
import logging
import os
import re
import stat
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

IMG_TAG_RE = re.compile(r"<img\b[^>]*/?>", re.IGNORECASE)
SRC_RE = re.compile(r'\bsrc="([^"]*)"', re.IGNORECASE)
ALT_RE = re.compile(r'\balt="([^"]*)"', re.IGNORECASE)

# Decompression-bomb guards: an image tag can point at anything, so both the
# download and the decode are capped regardless of what Content-Length claims.
MAX_IMAGE_DOWNLOAD_BYTES = 25 * 2**20
MAX_DECODE_PIXELS = 40_000_000
# Belt-and-suspenders for multi-frame formats (GIF/WEBP) where the explicit
# width*height check below only sees the first frame; the primary guard is
# still the check before .load(), which raises before any decode work.
Image.MAX_IMAGE_PIXELS = MAX_DECODE_PIXELS


@dataclass
class DigestImage:
    filename: str
    media_type: str
    data: bytes


def image_cache_dir(epub_dir: Path) -> Path:
    """The on-disk image cache lives beside the EPUBs it feeds; the dot name
    keeps it out of anything that globs the directory for editions."""
    return epub_dir / ".image_cache"


def _cache_path(cache_dir: Path, url: str) -> Path:
    return cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".bin")


def prune_image_cache(cache_dir: Path, *, max_age_days: int) -> int:
    """Delete cached images untouched for more than `max_age_days`; returns
    the number removed. Cache hits refresh mtime, so in-use images survive."""
    if not cache_dir.is_dir():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for path in cache_dir.iterdir():
        try:
            st = path.stat()
            if stat.S_ISREG(st.st_mode) and st.st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def _recompress(data: bytes, *, max_width: int, jpeg_quality: int) -> tuple[bytes, str, str]:
    """Downscale and recompress; returns (bytes, extension, media type).

    JPEG for opaque images, PNG only when transparency would be lost.
    Raises on undecodable input.
    """
    img: Image.Image = Image.open(BytesIO(data))
    # Image.open only reads the header; check declared dimensions before the
    # decode that .load() triggers, so a hostile IHDR can't burn CPU/memory.
    if img.width * img.height > MAX_DECODE_PIXELS:
        raise ValueError(
            f"image too large to decode: {img.width}x{img.height} "
            f"exceeds {MAX_DECODE_PIXELS} pixels"
        )
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


async def _download_capped(client: httpx.AsyncClient, url: str) -> bytes:
    """Stream the body, aborting once it exceeds the byte cap - a hostile or
    misconfigured server can lie about Content-Length, so the cap is enforced
    on bytes actually received rather than trusted upfront."""
    async with client.stream("GET", url) as r:
        r.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        async for chunk in r.aiter_bytes():
            total += len(chunk)
            if total > MAX_IMAGE_DOWNLOAD_BYTES:
                raise ValueError(
                    f"image over {MAX_IMAGE_DOWNLOAD_BYTES} byte download cap: {url}"
                )
            chunks.append(chunk)
        return b"".join(chunks)


async def prepare_images(
    articles: list[tuple[str, str]],
    client: httpx.AsyncClient,
    *,
    max_width: int = 1200,
    jpeg_quality: int = 75,
    per_article_budget: int = 10 * 2**20,
    cache_dir: Path | None = None,
) -> tuple[list[str], dict[str, DigestImage]]:
    """Download, downscale and pack the images referenced by digest articles.

    Takes (sanitized_html, article_url) pairs; returns the HTML with image
    sources rewritten to packed `images/img_NNN.*` paths, plus the images
    keyed by resolved source URL. Images that fail to fetch/decode or blow
    the per-article byte budget are dropped (their tags removed).

    With `cache_dir`, original image bytes are cached on disk keyed by URL,
    so recompiling an edition needs no network. Cache hits refresh the file
    mtime; `prune_image_cache` evicts by age. Failures are never cached.
    """
    fetched: dict[str, tuple[bytes, str, str] | None] = {}
    packed: dict[str, DigestImage] = {}
    rewritten: list[str] = []

    def read_cache(url: str) -> bytes | None:
        if cache_dir is None:
            return None
        path = _cache_path(cache_dir, url)
        try:
            data = path.read_bytes()
            os.utime(path)
            return data
        except OSError:
            return None

    cache_dir_ready = False

    def write_cache(url: str, data: bytes) -> None:
        nonlocal cache_dir_ready
        if cache_dir is None:
            return
        try:
            if not cache_dir_ready:
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache_dir_ready = True
            _cache_path(cache_dir, url).write_bytes(data)
        except OSError as exc:
            logger.warning("image cache write failed (%s): %s", url, exc)

    async def fetch(url: str) -> tuple[bytes, str, str] | None:
        if url in fetched:
            return fetched[url]
        result: tuple[bytes, str, str] | None = None
        try:
            original = read_cache(url)
            downloaded = original is None
            if original is None:
                original = await _download_capped(client, url)
            # Decode/resize/re-encode is CPU-bound; off the event loop so a
            # compile with many images doesn't stall polling and other requests.
            result = await asyncio.to_thread(
                _recompress, original, max_width=max_width, jpeg_quality=jpeg_quality
            )
            if downloaded:
                # only after _recompress proved the bytes decodable
                write_cache(url, original)
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
