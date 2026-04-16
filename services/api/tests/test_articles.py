from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from rss_kindle.api.main import create_app

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
