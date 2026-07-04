from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from conftest import feed_http_client
from rss_books.api.main import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"


def _seed(client: TestClient) -> list[int]:
    r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
    feed_id = r.json()["id"]
    with patch("rss_books.api.feeds.make_http_client", new=feed_http_client(FIXTURE.read_bytes())):
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


def _seed_two_feeds(client: TestClient) -> tuple[dict, dict]:
    a = client.post("/api/feeds", json={"url": "https://a.example/rss", "title": "A"}).json()
    b = client.post("/api/feeds", json={"url": "https://b.example/rss", "title": "B"}).json()
    with patch("rss_books.api.feeds.make_http_client", new=feed_http_client(FIXTURE.read_bytes())):
        client.post(f"/api/feeds/{a['id']}/refresh")
    other_content = FIXTURE.read_bytes().replace(b"urn:example:", b"urn:other:")
    with patch("rss_books.api.feeds.make_http_client", new=feed_http_client(other_content)):
        client.post(f"/api/feeds/{b['id']}/refresh")
    return a, b


def test_mark_all_read_scoped_to_feed(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        a, b = _seed_two_feeds(client)

        r = client.post("/api/articles/mark-all-read", params={"feed_id": a["id"]})
        assert r.status_code == 200
        assert r.json()["updated"] == 2

        unread = client.get("/api/articles", params={"unread": True}).json()
        assert {x["feed_id"] for x in unread} == {b["id"]}


def test_mark_all_read_scoped_to_group(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        group = client.post("/api/groups", json={"name": "AI"}).json()
        a, b = _seed_two_feeds(client)
        client.patch(f"/api/feeds/{a['id']}", json={"group_id": group["id"]})

        r = client.post("/api/articles/mark-all-read", params={"group_id": group["id"]})
        assert r.json()["updated"] == 2
        unread = client.get("/api/articles", params={"unread": True}).json()
        assert {x["feed_id"] for x in unread} == {b["id"]}

        # group_id=0 is the "ungrouped feeds" sentinel
        r = client.post("/api/articles/mark-all-read", params={"group_id": 0})
        assert r.json()["updated"] == 2
        assert client.get("/api/articles", params={"unread": True}).json() == []


def test_mark_all_read_no_filter_hits_everything(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)

        r = client.post("/api/articles/mark-all-read")
        assert r.json()["updated"] == len(ids)
        assert client.get("/api/articles", params={"unread": True}).json() == []

        # nothing left unread: idempotent, not an error
        assert client.post("/api/articles/mark-all-read").json()["updated"] == 0
