from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from rss_kindle.api.main import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"


def _seed(client: TestClient) -> list[int]:
    r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
    feed_id = r.json()["id"]
    with patch("rss_kindle.api.feeds.fetch_feed_bytes") as m:
        m.return_value = FIXTURE.read_bytes()
        client.post(f"/api/feeds/{feed_id}/refresh")
    return [a["id"] for a in client.get("/api/articles").json()]


def test_read_unread_transitions_and_filter(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)

        r = client.post(f"/api/articles/{ids[0]}/read")
        assert r.status_code == 200
        assert r.json()["read_at"] is not None

        unread = client.get("/api/articles", params={"unread": True}).json()
        assert [a["id"] for a in unread] == ids[1:]

        r = client.post(f"/api/articles/{ids[0]}/unread")
        assert r.json()["read_at"] is None
        assert len(client.get("/api/articles", params={"unread": True}).json()) == len(ids)

        assert client.post("/api/articles/9999/read").status_code == 404


def test_feed_unread_count(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        assert client.get("/api/feeds").json()[0]["unread_count"] == len(ids)
        client.post(f"/api/articles/{ids[0]}/read")
        assert client.get("/api/feeds").json()[0]["unread_count"] == len(ids) - 1


def test_search_filter(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _seed(client)
        titles = [a["title"] for a in client.get("/api/articles").json()]
        needle = titles[0].split()[0]
        hits = client.get("/api/articles", params={"q": needle}).json()
        assert hits and all(
            needle.lower() in (a["title"] + (a["summary"] or "")).lower() for a in hits
        )
        assert client.get("/api/articles", params={"q": "zzz-no-such"}).json() == []


def test_offset_pagination(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        page1 = client.get("/api/articles", params={"limit": 1, "offset": 0}).json()
        page2 = client.get("/api/articles", params={"limit": 1, "offset": 1}).json()
        assert [page1[0]["id"], page2[0]["id"]] == ids[:2]


def test_compiling_marks_articles_read(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        client.post("/api/digests", json={"article_ids": ids})
        assert client.get("/api/articles", params={"unread": True}).json() == []
