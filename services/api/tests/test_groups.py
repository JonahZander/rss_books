from fastapi.testclient import TestClient

from rss_kindle.api.main import create_app


def test_create_and_list_groups_ordered_by_position(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.post("/api/groups", json={"name": "AI"})
        assert r.status_code == 201
        ai = r.json()
        assert ai["name"] == "AI"
        assert ai["position"] == 1

        r = client.post("/api/groups", json={"name": "Gaming"})
        assert r.status_code == 201
        assert r.json()["position"] == 2

        r = client.get("/api/groups")
        assert r.status_code == 200
        assert [g["name"] for g in r.json()] == ["AI", "Gaming"]


def test_duplicate_group_name_is_case_insensitive_409(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        assert client.post("/api/groups", json={"name": "AI"}).status_code == 201
        r = client.post("/api/groups", json={"name": "ai"})
        assert r.status_code == 409


def test_blank_group_name_rejected(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.post("/api/groups", json={"name": "   "})
        assert r.status_code == 422


def test_rename_and_reposition_group(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ai = client.post("/api/groups", json={"name": "AI"}).json()
        gaming = client.post("/api/groups", json={"name": "Gaming"}).json()

        r = client.patch(f"/api/groups/{ai['id']}", json={"name": "Artificial"})
        assert r.status_code == 200
        assert r.json()["name"] == "Artificial"

        r = client.patch(f"/api/groups/{ai['id']}", json={"name": "gaming"})
        assert r.status_code == 409

        r = client.patch(f"/api/groups/{gaming['id']}", json={"position": 0})
        assert r.status_code == 200
        r = client.get("/api/groups")
        assert [g["name"] for g in r.json()] == ["Gaming", "Artificial"]


def test_patch_unknown_group_404(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.patch("/api/groups/999", json={"name": "X"})
        assert r.status_code == 404


def test_delete_group(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ai = client.post("/api/groups", json={"name": "AI"}).json()
        assert client.delete(f"/api/groups/{ai['id']}").status_code == 204
        assert client.get("/api/groups").json() == []
