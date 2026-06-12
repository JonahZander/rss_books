from io import BytesIO

import httpx
from PIL import Image

from rss_kindle.services.image_pipeline import prepare_images


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


async def test_per_article_budget_drops_overflow() -> None:
    html = '<img src="https://site.example/big.png" alt="too big">'
    async with _client() as client:
        rewritten, images = await prepare_images(
            [(html, "https://site.example/post")], client, per_article_budget=10
        )
    assert images == {}
    assert "<img" not in rewritten[0]
