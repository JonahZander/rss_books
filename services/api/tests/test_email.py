import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosmtplib
from fastapi.testclient import TestClient

from rss_kindle.api.main import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"


def _seed_ready_digest(client: TestClient) -> int:
    r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
    feed_id = r.json()["id"]
    with patch("rss_kindle.api.feeds.fetch_feed_bytes") as m:
        m.return_value = FIXTURE.read_bytes()
        client.post(f"/api/feeds/{feed_id}/refresh")
    ids = [a["id"] for a in client.get("/api/articles").json()]
    digest_id = client.post("/api/digests", json={"article_ids": ids}).json()[0]["id"]
    for _ in range(50):
        if client.get(f"/api/digests/{digest_id}").json()["status"] in {"ready", "failed"}:
            break
        time.sleep(0.1)
    assert client.get(f"/api/digests/{digest_id}").json()["status"] == "ready"
    return digest_id


def _configure_email(client: TestClient) -> None:
    s = client.get("/api/settings").json()
    s.update(
        smtp_host="smtp.example.com",
        smtp_from="news@example.com",
        send_to=["reader@kindle.com"],
    )
    assert client.put("/api/settings", json=s).status_code == 200


def test_send_digest_records_delivery(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        digest_id = _seed_ready_digest(client)
        _configure_email(client)
        with patch("rss_kindle.services.emailer.aiosmtplib.send", new=AsyncMock()) as sent:
            r = client.post(f"/api/digests/{digest_id}/send")
        assert r.status_code == 200
        delivery = r.json()
        assert delivery["status"] == "sent"
        assert delivery["channel"] == "email"
        assert "reader@kindle.com" in delivery["target"]
        assert sent.await_count == 1

        d = client.get(f"/api/digests/{digest_id}").json()
        assert d["delivered_at"] is not None
        assert d["deliveries"][0]["status"] == "sent"


def test_smtp_failure_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        digest_id = _seed_ready_digest(client)
        _configure_email(client)
        with patch(
            "rss_kindle.services.emailer.aiosmtplib.send",
            new=AsyncMock(side_effect=aiosmtplib.SMTPException("relay refused")),
        ):
            r = client.post(f"/api/digests/{digest_id}/send")
        assert r.status_code == 200
        assert r.json()["status"] == "failed"
        assert "relay refused" in r.json()["error"]

        d = client.get(f"/api/digests/{digest_id}").json()
        assert d["delivered_at"] is None


def test_send_unconfigured_409_and_no_record(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        digest_id = _seed_ready_digest(client)
        r = client.post(f"/api/digests/{digest_id}/send")
        assert r.status_code == 409
        assert "not configured" in r.json()["detail"]
        assert client.get(f"/api/digests/{digest_id}").json()["deliveries"] == []


def test_size_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        digest_id = _seed_ready_digest(client)
        _configure_email(client)
        with (
            patch("rss_kindle.services.emailer.MAX_ATTACHMENT_BYTES", 10),
            patch("rss_kindle.services.emailer.aiosmtplib.send", new=AsyncMock()) as sent,
        ):
            r = client.post(f"/api/digests/{digest_id}/send")
        assert r.status_code == 200
        assert r.json()["status"] == "failed"
        assert "over the" in r.json()["error"]
        assert sent.await_count == 0


def test_email_on_ready_auto_sends(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
        feed_id = r.json()["id"]
        with patch("rss_kindle.api.feeds.fetch_feed_bytes") as m:
            m.return_value = FIXTURE.read_bytes()
            client.post(f"/api/feeds/{feed_id}/refresh")
        ids = [a["id"] for a in client.get("/api/articles").json()]

        _configure_email(client)
        s = client.get("/api/settings").json()
        s["email_on_ready"] = True
        client.put("/api/settings", json=s)

        with patch("rss_kindle.services.emailer.aiosmtplib.send", new=AsyncMock()) as sent:
            digest_id = client.post("/api/digests", json={"article_ids": ids}).json()[0]["id"]
            for _ in range(50):
                d = client.get(f"/api/digests/{digest_id}").json()
                if d["status"] in {"ready", "failed"} and d["deliveries"]:
                    break
                time.sleep(0.1)
        assert sent.await_count == 1
        assert d["deliveries"][0]["status"] == "sent"


def test_test_email_endpoint(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.post("/api/settings/test-email", json={})
        assert r.status_code == 502  # unconfigured

        _configure_email(client)
        with patch("rss_kindle.services.emailer.aiosmtplib.send", new=AsyncMock()):
            r = client.post("/api/settings/test-email", json={})
        assert r.status_code == 200
        assert r.json() == {"sent_to": ["reader@kindle.com"]}
