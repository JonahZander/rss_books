from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from rss_kindle.api.main import create_app
from rss_kindle.config import USER_AGENT

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"


def _seed_feed_with_articles(client: TestClient) -> int:
    r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
    feed_id = r.json()["id"]
    with patch("rss_kindle.api.feeds.fetch_feed_bytes") as mock_fetch:
        mock_fetch.return_value = FIXTURE.read_bytes()
        client.post(f"/api/feeds/{feed_id}/refresh")
    return feed_id


def test_list_articles_by_feed(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        feed_id = _seed_feed_with_articles(client)
        r = client.get("/api/articles", params={"feed_id": feed_id})
        assert r.status_code == 200
        articles = r.json()
        assert len(articles) == 2
        assert articles[0]["published_at"] >= articles[1]["published_at"]
        assert articles[0]["has_full_content"] is False


def test_get_article_detail(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _seed_feed_with_articles(client)
        r = client.get("/api/articles")
        article_id = r.json()[0]["id"]
        r = client.get(f"/api/articles/{article_id}")
        assert r.status_code == 200
        assert r.json()["full_content"] is None


def test_fetch_article_full_content(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _seed_feed_with_articles(client)
        article_id = client.get("/api/articles").json()[0]["id"]

        html = (
            b"<html><body><article><h1>T</h1><p>Hello world. "
            b"This paragraph is long enough for trafilatura to extract, "
            b"we need sufficient prose to pass boilerplate filters here.</p>"
            b"</article></body></html>"
        )
        with patch("rss_kindle.api.articles.fetch_url_bytes") as mock_fetch:
            mock_fetch.return_value = html
            r = client.post(f"/api/articles/{article_id}/fetch")
            assert r.status_code == 200
            assert "Hello world" in r.json()["full_content"]

        r = client.get(f"/api/articles/{article_id}")
        assert r.json()["has_full_content"] is True


def test_fetch_blocked_site_returns_502_not_500(tmp_path):
    """Bot-walled sites (e.g. openai.com → 403) must surface as a clear 502,
    not an unhandled exception."""
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _seed_feed_with_articles(client)
        article_id = client.get("/api/articles").json()[0]["id"]

        req = httpx.Request("GET", "https://blocked.example/a")
        err = httpx.HTTPStatusError(
            "403", request=req, response=httpx.Response(403, request=req)
        )
        with patch("rss_kindle.api.articles.fetch_url_bytes", side_effect=err):
            r = client.post(f"/api/articles/{article_id}/fetch")
        assert r.status_code == 502
        assert "403" in r.json()["detail"]

        timeout = httpx.ConnectTimeout("timed out", request=req)
        with patch("rss_kindle.api.articles.fetch_url_bytes", side_effect=timeout):
            r = client.post(f"/api/articles/{article_id}/fetch")
        assert r.status_code == 502


def test_user_agent_is_browser_shaped_and_shared():
    from rss_kindle.services import poller

    assert USER_AGENT.startswith("Mozilla/5.0")
    assert "rss-kindle-selector" in USER_AGENT
    assert poller.USER_AGENT == USER_AGENT
