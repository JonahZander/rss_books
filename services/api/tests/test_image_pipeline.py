import os
import time
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from rss_kindle.services.image_pipeline import prepare_images, prune_image_cache


def _png(width: int, height: int, mode: str = "RGB") -> bytes:
    img = Image.new(mode, (width, height), (200, 30, 30) if mode == "RGB" else (200, 30, 30, 120))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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


async def test_per_article_budget_drops_overflow() -> None:
    html = '<img src="https://site.example/big.png" alt="too big">'
    async with _client() as client:
        rewritten, images = await prepare_images(
            [(html, "https://site.example/post")], client, per_article_budget=10
        )
    assert images == {}
    assert "<img" not in rewritten[0]
