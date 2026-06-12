from pathlib import Path

from fastapi.testclient import TestClient

from rss_kindle.api.main import create_app


def _fake_export(root: Path) -> Path:
    out = root / "out"
    (out / "_next" / "static").mkdir(parents=True)
    (out / "index.html").write_text("<html><body>TRIAGE-PAGE</body></html>")
    (out / "editions.html").write_text("<html><body>EDITIONS-PAGE</body></html>")
    (out / "_next" / "static" / "app.css").write_text("body{}")
    return out


def test_spa_serving_and_fallback(tmp_path, monkeypatch):
    out = _fake_export(tmp_path)
    monkeypatch.setenv("STATIC_DIR", str(out))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200 and "TRIAGE-PAGE" in r.text

        r = client.get("/editions")
        assert r.status_code == 200 and "EDITIONS-PAGE" in r.text

        r = client.get("/_next/static/app.css")
        assert r.status_code == 200 and "body{}" in r.text

        # unknown route falls back to the SPA shell
        r = client.get("/no/such/route")
        assert r.status_code == 200 and "TRIAGE-PAGE" in r.text

        # traversal is constrained to the export dir
        r = client.get("/../../etc/passwd")
        assert r.status_code == 200 and "TRIAGE-PAGE" in r.text

        # Next's router prefetches with HEAD
        assert client.head("/editions").status_code == 200

        # API routes still win over the catch-all
        assert client.get("/api/feeds").json() == []
        assert client.get("/health").json()["db"] == "ok"


def test_no_static_dir_means_api_only(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        assert client.get("/no/such/route").status_code == 404
