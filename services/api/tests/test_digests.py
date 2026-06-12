import time
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


def test_create_digest_generates_epub(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        r = client.post("/api/digests", json={"article_ids": ids, "title": "2026-04-16"})
        assert r.status_code == 201
        digest = r.json()
        assert digest["status"] in {"pending", "generating", "ready"}

        digest_id = digest["id"]
        for _ in range(30):
            r = client.get(f"/api/digests/{digest_id}")
            if r.json()["status"] == "ready":
                break
            time.sleep(0.1)
        assert client.get(f"/api/digests/{digest_id}").json()["status"] == "ready"

        r = client.get(f"/api/digests/{digest_id}/download")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/epub")
        assert len(r.content) > 1000


def test_digest_build_failure_sets_failed_status(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        with patch(
            "rss_kindle.api.digests.build_digest_epub",
            side_effect=RuntimeError("boom: disk full"),
        ):
            r = client.post("/api/digests", json={"article_ids": ids})
            assert r.status_code == 201
            digest_id = r.json()["id"]

        digest = {}
        for _ in range(30):
            digest = client.get(f"/api/digests/{digest_id}").json()
            if digest["status"] in {"ready", "failed"}:
                break
            time.sleep(0.1)
        assert digest["status"] == "failed"
        assert "boom: disk full" in digest["error"]

        r = client.get(f"/api/digests/{digest_id}/download")
        assert r.status_code == 409


def test_list_digests(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        client.post("/api/digests", json={"article_ids": ids})
        r = client.get("/api/digests")
        assert r.status_code == 200
        assert len(r.json()) == 1
