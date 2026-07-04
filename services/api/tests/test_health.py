from fastapi.testclient import TestClient

from rss_books.api.main import create_app


def test_health_reports_version_and_db(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"
        assert body["version"]
