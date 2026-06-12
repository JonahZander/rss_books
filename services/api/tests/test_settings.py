from fastapi.testclient import TestClient

from rss_kindle.api.main import create_app


def test_defaults_when_unset(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.get("/api/settings")
        assert r.status_code == 200
        s = r.json()
        assert s["smtp_port"] == 587
        assert s["smtp_security"] == "starttls"
        assert s["poll_enabled"] is True
        assert s["retention_days"] == 90
        assert s["send_to"] == []


def test_put_roundtrip(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        s = client.get("/api/settings").json()
        s["smtp_host"] = "smtp.fastmail.com"
        s["send_to"] = ["someone@kindle.com"]
        s["email_on_ready"] = True
        s["deadline_time"] = "07:15"
        r = client.put("/api/settings", json=s)
        assert r.status_code == 200

        again = client.get("/api/settings").json()
        assert again["smtp_host"] == "smtp.fastmail.com"
        assert again["send_to"] == ["someone@kindle.com"]
        assert again["email_on_ready"] is True
        assert again["deadline_time"] == "07:15"


def test_invalid_deadline_time_rejected(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        s = client.get("/api/settings").json()
        s["deadline_time"] = "25:99"
        assert client.put("/api/settings", json=s).status_code == 422


def test_env_overrides_win(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.env.example")
    monkeypatch.setenv("SMTP_FROM", "env@example.com")
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        s = client.get("/api/settings").json()
        assert s["smtp_host"] == "smtp.env.example"
        assert s["smtp_from"] == "env@example.com"

        # stored values persist but the env keeps winning on read
        s["smtp_host"] = "smtp.db.example"
        s = client.put("/api/settings", json=s).json()
        assert s["smtp_host"] == "smtp.env.example"


def test_deadline_split_roundtrip(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        s = client.get("/api/settings").json()
        assert s["deadline_split"] == "combined"
        s["deadline_split"] = "per_group"
        assert client.put("/api/settings", json=s).status_code == 200
        assert client.get("/api/settings").json()["deadline_split"] == "per_group"
