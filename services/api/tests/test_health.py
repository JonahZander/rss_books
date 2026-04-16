from fastapi.testclient import TestClient

from rss_kindle.api.main import create_app


def test_health_returns_ok(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
