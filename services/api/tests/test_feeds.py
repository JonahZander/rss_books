from fastapi.testclient import TestClient

from rss_kindle.api.main import create_app


def test_create_list_delete_feed(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
        assert r.status_code == 201
        feed = r.json()
        assert feed["url"] == "https://example.com/rss"
        assert feed["title"] == "Example"
        assert "id" in feed

        r = client.get("/api/feeds")
        assert r.status_code == 200
        assert len(r.json()) == 1

        r = client.delete(f"/api/feeds/{feed['id']}")
        assert r.status_code == 204

        r = client.get("/api/feeds")
        assert r.json() == []


def test_duplicate_feed_url_returns_409(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
        r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Again"})
        assert r.status_code == 409
