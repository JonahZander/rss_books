import os
import struct
import time
import zlib
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import httpx
from PIL import Image

from rss_books.services.image_pipeline import (
    MAX_DECODE_PIXELS,
    MAX_IMAGE_DOWNLOAD_BYTES,
    prepare_images,
    prune_image_cache,
)


def _png(width: int, height: int, mode: str = "RGB") -> bytes:
    img = Image.new(mode, (width, height), (200, 30, 30) if mode == "RGB" else (200, 30, 30, 120))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))


def _png_huge_declared_dims(width: int, height: int) -> bytes:
    """A structurally valid PNG (signature + IHDR + IEND) that declares
    absurd dimensions but carries no pixel data - Image.open() parses the
    header fine (so the size is known), but any real decode would explode.
    Exercises the pixel-count guard, which must trip before .load()."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IEND", b"")


def _client() -> httpx.AsyncClient:
    big = _png(2400, 1200)
    alpha = _png(100, 50, mode="RGBA")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/big.png":
            return httpx.Response(200, content=big, headers={"content-type": "image/png"})
        if path == "/alpha.png":
            return httpx.Response(200, content=alpha, headers={"content-type": "image/png"})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_downscales_and_recompresses_to_jpeg() -> None:
    html = '<p>x</p><img src="https://site.example/big.png" alt="wide">'
    async with _client() as client:
        rewritten, images = await prepare_images([(html, "https://site.example/post")], client)
    assert len(images) == 1
    img = next(iter(images.values()))
    assert img.filename == "images/img_001.jpg"
    assert img.media_type == "image/jpeg"
    out = Image.open(BytesIO(img.data))
    assert out.size == (1200, 600)
    assert f'<img src="{img.filename}" alt="wide"/>' in rewritten[0]
    assert "big.png" not in rewritten[0]


async def test_alpha_stays_png() -> None:
    html = '<img src="/alpha.png" alt="">'
    async with _client() as client:
        rewritten, images = await prepare_images([(html, "https://site.example/post")], client)
    img = next(iter(images.values()))
    assert img.media_type == "image/png"
    assert img.filename.endswith(".png")
    assert Image.open(BytesIO(img.data)).size == (100, 50)
    # relative src resolved against the article URL
    assert f'<img src="{img.filename}"' in rewritten[0]


async def test_failed_fetch_strips_tag() -> None:
    html = '<p>before</p><img src="https://site.example/missing.png" alt="gone"><p>after</p>'
    async with _client() as client:
        rewritten, images = await prepare_images([(html, "https://site.example/post")], client)
    assert images == {}
    assert "<img" not in rewritten[0]
    assert "before" in rewritten[0] and "after" in rewritten[0]


async def test_dedup_across_articles() -> None:
    a = '<img src="https://site.example/big.png" alt="a">'
    b = '<img src="https://site.example/big.png" alt="b">'
    async with _client() as client:
        rewritten, images = await prepare_images(
            [(a, "https://site.example/1"), (b, "https://site.example/2")], client
        )
    assert len(images) == 1
    assert 'src="images/img_001.jpg"' in rewritten[0]
    assert 'src="images/img_001.jpg"' in rewritten[1]


def _counting_client(counter: dict[str, int]) -> httpx.AsyncClient:
    big = _png(2400, 1200)

    def handler(request: httpx.Request) -> httpx.Response:
        counter[request.url.path] = counter.get(request.url.path, 0) + 1
        if request.url.path == "/big.png":
            return httpx.Response(200, content=big, headers={"content-type": "image/png"})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_cache_hit_skips_network(tmp_path: Path) -> None:
    html = '<img src="https://site.example/big.png" alt="wide">'
    counter: dict[str, int] = {}
    async with _counting_client(counter) as client:
        await prepare_images([(html, "https://site.example/post")], client, cache_dir=tmp_path)
    assert counter["/big.png"] == 1

    # second compile: even a dead network still yields the image from cache
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as client:
        rewritten, images = await prepare_images(
            [(html, "https://site.example/post")], client, cache_dir=tmp_path
        )
    assert len(images) == 1
    img = next(iter(images.values()))
    assert Image.open(BytesIO(img.data)).size == (1200, 600)
    assert f'<img src="{img.filename}"' in rewritten[0]


async def test_failed_fetch_not_cached(tmp_path: Path) -> None:
    html = '<img src="https://site.example/missing.png" alt="">'
    counter: dict[str, int] = {}
    async with _counting_client(counter) as client:
        _, images = await prepare_images(
            [(html, "https://site.example/post")], client, cache_dir=tmp_path
        )
    assert images == {}
    assert list(tmp_path.iterdir()) == []


async def test_cache_hit_refreshes_mtime(tmp_path: Path) -> None:
    html = '<img src="https://site.example/big.png" alt="">'
    counter: dict[str, int] = {}
    async with _counting_client(counter) as client:
        await prepare_images([(html, "https://site.example/post")], client, cache_dir=tmp_path)
        (cached,) = tmp_path.iterdir()
        stale = time.time() - 90 * 86400
        os.utime(cached, (stale, stale))
        await prepare_images([(html, "https://site.example/post")], client, cache_dir=tmp_path)
    assert counter["/big.png"] == 1
    assert cached.stat().st_mtime > time.time() - 60


def test_prune_image_cache_removes_old_files(tmp_path: Path) -> None:
    old = tmp_path / "old.bin"
    fresh = tmp_path / "fresh.bin"
    old.write_bytes(b"x")
    fresh.write_bytes(b"y")
    stale = time.time() - 90 * 86400
    os.utime(old, (stale, stale))
    removed = prune_image_cache(tmp_path, max_age_days=30)
    assert removed == 1
    assert not old.exists()
    assert fresh.exists()


def test_prune_image_cache_missing_dir(tmp_path: Path) -> None:
    assert prune_image_cache(tmp_path / "nope", max_age_days=30) == 0


async def test_recompress_runs_off_event_loop() -> None:
    """Best-effort timing test: while the (deliberately slowed) recompress
    blocks synchronously in a worker thread, a concurrent async task keeps
    advancing - proof asyncio.to_thread actually takes _recompress off the
    loop rather than freezing every other request for its duration."""
    import asyncio

    from rss_books.services import image_pipeline

    original_recompress = image_pipeline._recompress

    def slow_recompress(*args, **kwargs):
        time.sleep(0.2)
        return original_recompress(*args, **kwargs)

    counter = {"n": 0}

    async def tick() -> None:
        for _ in range(40):
            await asyncio.sleep(0.01)
            counter["n"] += 1

    html = '<img src="https://site.example/big.png" alt="wide">'
    with patch.object(image_pipeline, "_recompress", slow_recompress):
        async with _client() as client:
            (_, images), _ = await asyncio.gather(
                prepare_images([(html, "https://site.example/post")], client), tick()
            )
    assert len(images) == 1
    assert counter["n"] >= 15


async def test_huge_declared_dimensions_dropped() -> None:
    """A PNG whose IHDR claims dimensions past MAX_DECODE_PIXELS is dropped
    like any other undecodable image; no exception escapes prepare_images."""
    side = int(MAX_DECODE_PIXELS**0.5) + 1000
    bomb = _png_huge_declared_dims(side, side)  # comfortably past the pixel cap

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=bomb, headers={"content-type": "image/png"})

    html = '<img src="https://site.example/bomb.png" alt="bomb">'
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rewritten, images = await prepare_images([(html, "https://site.example/post")], client)
    assert images == {}
    assert "<img" not in rewritten[0]


async def test_over_download_cap_dropped_and_not_cached(tmp_path: Path) -> None:
    """A body that exceeds the byte cap is aborted mid-stream and dropped,
    even though Content-Length (absent here) can't be trusted upfront."""
    oversized = b"\x00" * (MAX_IMAGE_DOWNLOAD_BYTES + 1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=oversized, headers={"content-type": "image/png"})

    html = '<img src="https://site.example/huge.png" alt="huge">'
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rewritten, images = await prepare_images(
            [(html, "https://site.example/post")], client, cache_dir=tmp_path
        )
    assert images == {}
    assert "<img" not in rewritten[0]
    assert list(tmp_path.iterdir()) == []


async def test_per_article_budget_drops_overflow() -> None:
    html = '<img src="https://site.example/big.png" alt="too big">'
    async with _client() as client:
        rewritten, images = await prepare_images(
            [(html, "https://site.example/post")], client, per_article_budget=10
        )
    assert images == {}
    assert "<img" not in rewritten[0]
