import time
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


def test_queue_add_list_remove(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        assert client.get("/api/queue").json() == []

        r = client.post(f"/api/queue/{ids[1]}")
        assert r.status_code == 200
        r = client.post(f"/api/queue/{ids[0]}")
        assert [a["id"] for a in r.json()] == [ids[1], ids[0]]
        # the queue endpoint reports the derived lifecycle state too
        assert all(a["state"] == "queued" for a in r.json())

        # idempotent re-add keeps position
        r = client.post(f"/api/queue/{ids[1]}")
        assert [a["id"] for a in r.json()] == [ids[1], ids[0]]

        r = client.delete(f"/api/queue/{ids[1]}")
        assert [a["id"] for a in r.json()] == [ids[0]]


def test_queue_add_unknown_article_404(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        assert client.post("/api/queue/9999").status_code == 404


def test_queue_replace_for_reorder(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        client.post(f"/api/queue/{ids[0]}")
        client.post(f"/api/queue/{ids[1]}")
        r = client.put("/api/queue", json={"article_ids": [ids[1], ids[0]]})
        assert r.status_code == 200
        assert [a["id"] for a in r.json()] == [ids[1], ids[0]]

        r = client.put("/api/queue", json={"article_ids": []})
        assert r.json() == []


def test_queue_survives_restart_of_app(tmp_path):
    db_path = tmp_path / "t.db"
    app = create_app(db_path=db_path)
    with TestClient(app) as client:
        ids = _seed(client)
        client.post(f"/api/queue/{ids[0]}")
    app2 = create_app(db_path=db_path)
    with TestClient(app2) as client:
        assert [a["id"] for a in client.get("/api/queue").json()] == [ids[0]]


def test_digest_from_queue_clears_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        client.post(f"/api/queue/{ids[1]}")
        client.post(f"/api/queue/{ids[0]}")

        r = client.post("/api/digests", json={})
        assert r.status_code == 201
        digest_id = r.json()[0]["id"]

        assert client.get("/api/queue").json() == []

        for _ in range(30):
            d = client.get(f"/api/digests/{digest_id}").json()
            if d["status"] in {"ready", "failed"}:
                break
            time.sleep(0.1)
        assert d["status"] == "ready"
        assert d["size_bytes"] > 0


def test_queue_add_arbitrary_link(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        url = "https://example.com/some-great-article"
        r = client.post("/api/queue/link", json={"url": url})
        assert r.status_code == 200
        queue = r.json()
        assert [a["url"] for a in queue] == [url]
        assert queue[0]["state"] == "queued"
        # a derived, legible title when none is supplied
        assert queue[0]["title"] == "some great article"

        # re-adding the same URL is idempotent (one queue entry, one article)
        r = client.post("/api/queue/link", json={"url": url})
        assert [a["url"] for a in r.json()] == [url]

        # an explicit title wins
        r = client.post(
            "/api/queue/link", json={"url": "https://example.org/x", "title": "My pick"}
        )
        assert {a["title"] for a in r.json()} == {"some great article", "My pick"}

        # the hidden saved-links feed never surfaces in the sidebar
        assert client.get("/api/feeds").json() == []


def test_derive_title_strips_extension():
    from rss_books.services.saved_links import derive_title

    assert (
        derive_title(
            "https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck.html"
        )
        == "understanding is the new bottleneck"
    )
    assert derive_title("https://example.com/post.aspx") == "post"
    assert derive_title("https://example.com/no-extension") == "no extension"
    # no path at all still falls back to the hostname
    assert derive_title("https://www.example.com/") == "example.com"


def test_queue_link_rejects_non_url(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        assert client.post("/api/queue/link", json={"url": "not a url"}).status_code == 422


def test_digest_from_empty_queue_400(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        assert client.post("/api/digests", json={}).status_code == 400
