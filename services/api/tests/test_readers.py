from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from curl_cffi.requests.exceptions import RequestException
from fastapi.testclient import TestClient

from conftest import feed_http_client
from rss_kindle.api.main import create_app
from rss_kindle.models import AppSettings
from rss_kindle.services.readers import ReaderError, build_reader
from rss_kindle.services.readers.jina import JinaReader
from rss_kindle.services.readers.tavily import TavilyReader

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"


def _transport(handler: object) -> httpx.MockTransport:
    return httpx.MockTransport(handler)  # type: ignore[arg-type]


def test_build_reader_selects_provider_by_name() -> None:
    assert build_reader(AppSettings(reader_fallback="none")) is None
    # tavily needs a key; selected but unconfigured stays disabled
    assert build_reader(AppSettings(reader_fallback="tavily")) is None
    tavily = build_reader(AppSettings(reader_fallback="tavily", tavily_api_key="tvly-x"))
    assert isinstance(tavily, TavilyReader)
    assert isinstance(build_reader(AppSettings(reader_fallback="jina")), JinaReader)
    # an unknown name never resolves to a provider
    assert build_reader(AppSettings.model_construct(reader_fallback="nope")) is None


async def test_tavily_renders_markdown_to_html() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer tvly-x"
        return httpx.Response(
            200, json={"results": [{"url": "u", "raw_content": "# Hi\n\nBody **bold**"}]}
        )

    reader = TavilyReader("tvly-x", transport=_transport(handler))
    html = await reader.fetch_html("https://example.com/a")
    assert html is not None
    assert "<h1>Hi</h1>" in html
    assert "<strong>bold</strong>" in html


async def test_tavily_empty_results_is_none() -> None:
    reader = TavilyReader(
        "k", transport=_transport(lambda req: httpx.Response(200, json={"results": []}))
    )
    assert await reader.fetch_html("https://x") is None


async def test_tavily_http_error_raises_reader_error() -> None:
    reader = TavilyReader(
        "k", transport=_transport(lambda req: httpx.Response(401, json={}))
    )
    with pytest.raises(ReaderError):
        await reader.fetch_html("https://x")


async def test_jina_parses_json_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "r.jina.ai"
        return httpx.Response(200, json={"data": {"title": "T", "content": "## Sub\n\ntext"}})

    reader = JinaReader(transport=_transport(handler))
    html = await reader.fetch_html("https://example.com/a")
    assert html is not None
    assert "<h2>Sub</h2>" in html


class _StubReader:
    name = "stub"

    async def fetch_html(self, url: str) -> str | None:
        return "<p>recovered by reader</p><script>evil()</script>"


def _seed_article(client: TestClient) -> int:
    feed_id = client.post(
        "/api/feeds", json={"url": "https://example.com/rss", "title": "Example"}
    ).json()["id"]
    with patch("rss_kindle.api.feeds.make_http_client", new=feed_http_client(FIXTURE.read_bytes())):
        client.post(f"/api/feeds/{feed_id}/refresh")
    return int(client.get("/api/articles").json()[0]["id"])


def test_blocked_fetch_falls_back_to_reader(tmp_path: Path) -> None:
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        s = client.get("/api/settings").json()
        s.update(reader_fallback="tavily", tavily_api_key="tvly-x")
        client.put("/api/settings", json=s)
        article_id = _seed_article(client)

        with (
            patch(
                "rss_kindle.api.articles.fetch_url_bytes",
                side_effect=RequestException("blocked"),
            ),
            patch("rss_kindle.api.articles.build_reader", return_value=_StubReader()),
        ):
            r = client.post(f"/api/articles/{article_id}/fetch")
        assert r.status_code == 200
        body = r.json()
        assert "recovered by reader" in body["full_content"]
        # the reader's output is sanitized like everything else we store
        assert "<script>" not in body["full_content"]
        assert body["has_full_content"] is True


def test_blocked_fetch_without_reader_still_502(tmp_path: Path) -> None:
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        article_id = _seed_article(client)  # default settings: reader_fallback="none"
        with patch(
            "rss_kindle.api.articles.fetch_url_bytes",
            side_effect=RequestException("blocked"),
        ):
            r = client.post(f"/api/articles/{article_id}/fetch")
        assert r.status_code == 502
