import time
from base64 import b64encode
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

from rss_kindle.api.main import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"
NS = {"atom": "http://www.w3.org/2005/Atom"}


def _seed_ready_digest(client: TestClient) -> int:
    r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
    feed_id = r.json()["id"]
    with patch("rss_kindle.api.feeds.fetch_feed_bytes") as m:
        m.return_value = FIXTURE.read_bytes()
        client.post(f"/api/feeds/{feed_id}/refresh")
    ids = [a["id"] for a in client.get("/api/articles").json()]
    digest_id = client.post("/api/digests", json={"article_ids": ids}).json()["id"]
    for _ in range(50):
        if client.get(f"/api/digests/{digest_id}").json()["status"] == "ready":
            return digest_id
        time.sleep(0.1)
    raise AssertionError("digest never became ready")


def test_navigation_feed(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.get("/opds")
        assert r.status_code == 200
        assert "kind=navigation" in r.headers["content-type"]
        root = ET.fromstring(r.content)
        links = root.findall("atom:entry/atom:link", NS)
        assert any(link.get("href", "").endswith("/opds/digests") for link in links)


def test_acquisition_feed_lists_ready_digests(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        digest_id = _seed_ready_digest(client)
        # an unfinished digest must not appear
        with patch(
            "rss_kindle.services.digest_service.build_digest_epub",
            side_effect=RuntimeError("broken"),
        ):
            failed_id = client.post(
                "/api/digests", json={"article_ids": [1], "title": "broken"}
            ).json()["id"]
            for _ in range(50):
                if client.get(f"/api/digests/{failed_id}").json()["status"] == "failed":
                    break
                time.sleep(0.1)

        r = client.get("/opds/digests")
        assert r.status_code == 200
        assert "kind=acquisition" in r.headers["content-type"]
        root = ET.fromstring(r.content)
        entries = root.findall("atom:entry", NS)
        assert len(entries) == 1
        link = entries[0].find("atom:link", NS)
        assert link is not None
        assert link.get("type") == "application/epub+zip"
        href = link.get("href", "")
        assert href.startswith("http") and href.endswith(f"/api/digests/{digest_id}/download")

        # the advertised link actually downloads
        dl = client.get(f"/api/digests/{digest_id}/download")
        assert dl.status_code == 200


def test_opds_basic_auth(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        s = client.get("/api/settings").json()
        s.update(opds_auth_enabled=True, opds_username="reader", opds_password="hunter2")
        client.put("/api/settings", json=s)

        r = client.get("/opds")
        assert r.status_code == 401
        assert r.headers["www-authenticate"].startswith("Basic")

        bad = b64encode(b"reader:wrong").decode()
        assert client.get("/opds", headers={"Authorization": f"Basic {bad}"}).status_code == 401

        good = b64encode(b"reader:hunter2").decode()
        assert client.get("/opds", headers={"Authorization": f"Basic {good}"}).status_code == 200
        assert (
            client.get("/opds/digests", headers={"Authorization": f"Basic {good}"}).status_code
            == 200
        )
