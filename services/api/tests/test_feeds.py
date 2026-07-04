import sqlite3
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import httpx
from fastapi.testclient import TestClient

from conftest import feed_http_client, feed_http_client_error
from rss_kindle.api.main import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"


def test_create_list_delete_feed(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
        assert r.status_code == 201
        feed = r.json()
        assert feed["url"] == "https://example.com/rss"
        assert feed["title"] == "Example"
        assert "id" in feed

        r = client.get("/api/feeds")
        assert r.status_code == 200
        assert len(r.json()) == 1

        r = client.delete(f"/api/feeds/{feed['id']}")
        assert r.status_code == 204

        r = client.get("/api/feeds")
        assert r.json() == []


def test_duplicate_feed_url_returns_409(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
        r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Again"})
        assert r.status_code == 409


def test_refresh_feed_fetches_and_stores(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
        feed_id = r.json()["id"]

        with patch(
            "rss_kindle.api.feeds.make_http_client", new=feed_http_client(FIXTURE.read_bytes())
        ):
            r = client.post(f"/api/feeds/{feed_id}/refresh")
            assert r.status_code == 200
            assert r.json()["inserted"] == 2


def _feed_health_row(db_path: Path, feed_id: int) -> sqlite3.Row:
    """etag/last_modified/last_error/last_polled aren't in the Feed API model
    (they're poller-internal health bookkeeping), so tests read them straight
    from the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT etag, last_modified, last_error, last_polled FROM feeds WHERE id = ?",
        (feed_id,),
    ).fetchone()
    conn.close()
    return row


def test_refresh_feed_sends_conditional_headers_and_handles_304(tmp_path):
    """Manual refresh now goes through the same conditional-GET poller as the
    scheduler: it stores etag/last_modified on first fetch, sends them back as
    If-None-Match/If-Modified-Since next time, and a 304 clears error state
    and advances last_polled without inserting anything or touching etag."""
    db_path = tmp_path / "t.db"
    app = create_app(db_path=db_path)
    with TestClient(app) as client:
        r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
        feed_id = r.json()["id"]

        with patch(
            "rss_kindle.api.feeds.make_http_client",
            new=feed_http_client(
                FIXTURE.read_bytes(),
                headers={"ETag": 'W/"v1"', "Last-Modified": "Tue, 01 Jan 2030 00:00:00 GMT"},
            ),
        ):
            r = client.post(f"/api/feeds/{feed_id}/refresh")
        assert r.json()["inserted"] == 2
        health = _feed_health_row(db_path, feed_id)
        assert health["etag"] == 'W/"v1"'
        assert health["last_polled"] is not None

        captured: dict[str, str | None] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["if_none_match"] = request.headers.get("if-none-match")
            captured["if_modified_since"] = request.headers.get("if-modified-since")
            return httpx.Response(304)

        def fake_client(**overrides: object) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        with patch("rss_kindle.api.feeds.make_http_client", new=fake_client):
            r = client.post(f"/api/feeds/{feed_id}/refresh")
        assert r.status_code == 200
        assert r.json() == {"inserted": 0}
        assert captured["if_none_match"] == 'W/"v1"'
        assert captured["if_modified_since"] == "Tue, 01 Jan 2030 00:00:00 GMT"

        health = _feed_health_row(db_path, feed_id)
        assert health["etag"] == 'W/"v1"'  # untouched by the 304
        assert health["last_error"] is None


def test_patch_feed(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
        feed_id = r.json()["id"]

        r = client.patch(f"/api/feeds/{feed_id}", json={"title": "Renamed"})
        assert r.status_code == 200
        assert r.json()["title"] == "Renamed"
        assert r.json()["poll_interval_minutes"] == 30

        r = client.patch(f"/api/feeds/{feed_id}", json={"poll_interval_minutes": 120})
        assert r.json()["poll_interval_minutes"] == 120

        assert client.patch("/api/feeds/999", json={"title": "x"}).status_code == 404
        r = client.patch(f"/api/feeds/{feed_id}", json={"poll_interval_minutes": 0})
        assert r.status_code == 422


def test_assign_feed_to_group_and_clear(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        group = client.post("/api/groups", json={"name": "AI"}).json()
        r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
        feed_id = r.json()["id"]
        assert r.json()["group_id"] is None

        r = client.patch(f"/api/feeds/{feed_id}", json={"group_id": group["id"]})
        assert r.status_code == 200
        assert r.json()["group_id"] == group["id"]
        assert client.get("/api/feeds").json()[0]["group_id"] == group["id"]

        # explicit null moves the feed back to Ungrouped
        r = client.patch(f"/api/feeds/{feed_id}", json={"group_id": None})
        assert r.status_code == 200
        assert r.json()["group_id"] is None

        # nonexistent group
        r = client.patch(f"/api/feeds/{feed_id}", json={"group_id": 9999})
        assert r.status_code == 404
        assert "group" in r.json()["detail"]

        # NOT NULL columns reject explicit null
        assert client.patch(f"/api/feeds/{feed_id}", json={"title": None}).status_code == 422

        # deleting the group ungroups its feeds
        client.patch(f"/api/feeds/{feed_id}", json={"group_id": group["id"]})
        assert client.delete(f"/api/groups/{group['id']}").status_code == 204
        assert client.get("/api/feeds").json()[0]["group_id"] is None


def test_articles_group_filter(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        group = client.post("/api/groups", json={"name": "AI"}).json()
        a = client.post("/api/feeds", json={"url": "https://a.example/rss", "title": "A"}).json()
        b = client.post("/api/feeds", json={"url": "https://b.example/rss", "title": "B"}).json()
        client.patch(f"/api/feeds/{a['id']}", json={"group_id": group["id"]})

        with patch(
            "rss_kindle.api.feeds.make_http_client", new=feed_http_client(FIXTURE.read_bytes())
        ):
            client.post(f"/api/feeds/{a['id']}/refresh")
        other_content = FIXTURE.read_bytes().replace(b"urn:example:", b"urn:other:")
        with patch("rss_kindle.api.feeds.make_http_client", new=feed_http_client(other_content)):
            client.post(f"/api/feeds/{b['id']}/refresh")
        assert len(client.get("/api/articles").json()) == 4

        grouped = client.get("/api/articles", params={"group_id": group["id"]}).json()
        assert {x["feed_id"] for x in grouped} == {a["id"]}

        # group_id=0 selects articles of ungrouped feeds
        ungrouped = client.get("/api/articles", params={"group_id": 0}).json()
        assert {x["feed_id"] for x in ungrouped} == {b["id"]}


def test_manual_refresh_failure_recorded_and_cleared(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
        feed_id = r.json()["id"]

        with patch(
            "rss_kindle.api.feeds.make_http_client",
            new=feed_http_client_error(RuntimeError("dns exploded")),
        ):
            r = client.post(f"/api/feeds/{feed_id}/refresh")
        assert r.status_code == 502
        feed = client.get("/api/feeds").json()[0]
        assert "dns exploded" in feed["last_error"]
        assert feed["consecutive_failures"] == 1

        with patch(
            "rss_kindle.api.feeds.make_http_client", new=feed_http_client(FIXTURE.read_bytes())
        ):
            r = client.post(f"/api/feeds/{feed_id}/refresh")
        assert r.status_code == 200
        feed = client.get("/api/feeds").json()[0]
        assert feed["last_error"] is None
        assert feed["consecutive_failures"] == 0


OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>t</title></head>
  <body>
    <outline text="One" title="One" type="rss" xmlUrl="https://one.example/rss" htmlUrl="https://one.example"/>
    <outline text="folder">
      <outline text="Two" type="rss" xmlUrl="https://two.example/rss"/>
    </outline>
    <outline text="no-url-outline"/>
  </body>
</opml>"""


def test_opml_import_dedupes_and_export_roundtrips(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.post(
            "/api/feeds/import", files={"file": ("feeds.opml", OPML, "text/xml")}
        )
        assert r.status_code == 200
        assert r.json() == {"added": 2, "skipped": 0, "regrouped": 0}

        r = client.post(
            "/api/feeds/import", files={"file": ("feeds.opml", OPML, "text/xml")}
        )
        assert r.json() == {"added": 0, "skipped": 2, "regrouped": 0}

        feeds = client.get("/api/feeds").json()
        assert {f["title"] for f in feeds} == {"One", "Two"}

        r = client.get("/api/feeds/export.opml")
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]
        assert 'xmlUrl="https://one.example/rss"' in r.text
        assert 'xmlUrl="https://two.example/rss"' in r.text

        r = client.post("/api/feeds/import", files={"file": ("x.opml", "<not-xml", "text/xml")})
        assert r.status_code == 400


OPML_WITH_FOLDERS = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>subs</title></head>
  <body>
    <outline text="AI" title="AI">
      <outline text="Feed A" type="rss" xmlUrl="https://a.example/rss"/>
      <outline text="Sub">
        <outline text="Feed B" type="rss" xmlUrl="https://b.example/rss"/>
      </outline>
    </outline>
    <outline text="Feed C" type="rss" xmlUrl="https://c.example/rss"/>
  </body>
</opml>"""


def _import_opml(client: TestClient, body: str) -> dict:
    r = client.post(
        "/api/feeds/import", files={"file": ("subs.opml", body, "text/xml")}
    )
    assert r.status_code == 200
    return r.json()


def test_opml_import_folders_become_groups(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        assert _import_opml(client, OPML_WITH_FOLDERS) == {
            "added": 3,
            "skipped": 0,
            "regrouped": 0,
        }
        groups = client.get("/api/groups").json()
        assert [g["name"] for g in groups] == ["AI"]
        feeds = {f["url"]: f for f in client.get("/api/feeds").json()}
        ai_id = groups[0]["id"]
        assert feeds["https://a.example/rss"]["group_id"] == ai_id
        # nesting deeper than one level flattens into the top folder
        assert feeds["https://b.example/rss"]["group_id"] == ai_id
        assert feeds["https://c.example/rss"]["group_id"] is None


def test_opml_reimport_adopts_only_ungrouped(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _import_opml(client, OPML_WITH_FOLDERS)
        other = client.post("/api/groups", json={"name": "Other"}).json()
        feeds = {f["url"]: f for f in client.get("/api/feeds").json()}
        client.patch(
            f"/api/feeds/{feeds['https://b.example/rss']['id']}",
            json={"group_id": other["id"]},
        )
        client.patch(f"/api/feeds/{feeds['https://a.example/rss']['id']}", json={"group_id": None})

        # A (now ungrouped) adopts the file's folder; B's manual choice survives
        assert _import_opml(client, OPML_WITH_FOLDERS) == {
            "added": 0,
            "skipped": 3,
            "regrouped": 1,
        }
        feeds = {f["url"]: f for f in client.get("/api/feeds").json()}
        ai_id = next(g["id"] for g in client.get("/api/groups").json() if g["name"] == "AI")
        assert feeds["https://a.example/rss"]["group_id"] == ai_id
        assert feeds["https://b.example/rss"]["group_id"] == other["id"]


def test_opml_export_nests_groups_and_roundtrips(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ai = client.post("/api/groups", json={"name": "AI"}).json()
        a = client.post("/api/feeds", json={"url": "https://a.example/rss", "title": "Feed A"})
        client.patch(f"/api/feeds/{a.json()['id']}", json={"group_id": ai["id"]})
        client.post("/api/feeds", json={"url": "https://c.example/rss", "title": "Feed C"})

        body = client.get("/api/feeds/export.opml").text
        root = ET.fromstring(body)
        opml_body = root.find("body")
        assert opml_body is not None
        folders = [o for o in opml_body if not o.get("xmlUrl")]
        assert [f.get("text") for f in folders] == ["AI"]
        assert [c.get("xmlUrl") for c in folders[0]] == ["https://a.example/rss"]
        top_level = [o.get("xmlUrl") for o in opml_body if o.get("xmlUrl")]
        assert top_level == ["https://c.example/rss"]

    app2 = create_app(db_path=tmp_path / "t2.db")
    with TestClient(app2) as client2:
        assert _import_opml(client2, body)["added"] == 2
        groups2 = client2.get("/api/groups").json()
        assert [g["name"] for g in groups2] == ["AI"]
        feeds2 = {f["url"]: f for f in client2.get("/api/feeds").json()}
        assert feeds2["https://a.example/rss"]["group_id"] == groups2[0]["id"]
        assert feeds2["https://c.example/rss"]["group_id"] is None


FEEDS_JSON = """{
  "ai": ["https://a.example/rss", "https://b.example/rss"],
  "gaming": ["https://g.example/rss"],
  "ungrouped": ["https://c.example/rss"]
}"""


def _import_json(client: TestClient, body: str):
    return client.post(
        "/api/feeds/import-json",
        files={"file": ("feeds.json", body, "application/json")},
    )


def test_json_import_groups_and_placeholder_titles(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = _import_json(client, FEEDS_JSON)
        assert r.status_code == 200
        assert r.json() == {"added": 4, "skipped": 0, "regrouped": 0}

        groups = client.get("/api/groups").json()
        assert [g["name"] for g in groups] == ["ai", "gaming"]  # key order; no "ungrouped" group

        feeds = {f["url"]: f for f in client.get("/api/feeds").json()}
        by_name = {g["name"]: g["id"] for g in groups}
        assert feeds["https://a.example/rss"]["group_id"] == by_name["ai"]
        assert feeds["https://b.example/rss"]["group_id"] == by_name["ai"]
        assert feeds["https://g.example/rss"]["group_id"] == by_name["gaming"]
        assert feeds["https://c.example/rss"]["group_id"] is None
        # no titles in this format → hostname placeholders
        assert feeds["https://a.example/rss"]["title"] == "a.example"


def test_json_import_validation(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        assert _import_json(client, "[1, 2]").status_code == 400
        assert _import_json(client, '{"ai": "https://a.example"}').status_code == 400
        assert _import_json(client, '{"ai": [42]}').status_code == 400
        assert _import_json(client, '{"ai": ["ftp://a.example"]}').status_code == 400
        assert _import_json(client, '{"": ["https://a.example"]}').status_code == 400
        assert _import_json(client, "{nope").status_code == 400
        assert client.get("/api/feeds").json() == []


def test_json_reimport_adopts_only_ungrouped(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _import_json(client, FEEDS_JSON)
        feeds = {f["url"]: f for f in client.get("/api/feeds").json()}
        client.patch(f"/api/feeds/{feeds['https://a.example/rss']['id']}", json={"group_id": None})

        r = _import_json(client, FEEDS_JSON)
        assert r.json() == {"added": 0, "skipped": 4, "regrouped": 1}
        feeds = {f["url"]: f for f in client.get("/api/feeds").json()}
        ai_id = next(g["id"] for g in client.get("/api/groups").json() if g["name"] == "ai")
        assert feeds["https://a.example/rss"]["group_id"] == ai_id


def test_json_export_roundtrips(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _import_json(client, FEEDS_JSON)
        r = client.get("/api/feeds/export.json")
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]
        data = r.json()
        assert sorted(data["ai"]) == ["https://a.example/rss", "https://b.example/rss"]
        assert data["gaming"] == ["https://g.example/rss"]
        assert data["ungrouped"] == ["https://c.example/rss"]

    app2 = create_app(db_path=tmp_path / "t2.db")
    with TestClient(app2) as client2:
        assert _import_json(client2, r.text).json()["added"] == 4
        feeds2 = {f["url"]: f for f in client2.get("/api/feeds").json()}
        assert feeds2["https://c.example/rss"]["group_id"] is None
        assert [g["name"] for g in client2.get("/api/groups").json()] == ["ai", "gaming"]


def test_poll_adopts_placeholder_title_until_renamed(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _import_json(client, '{"ungrouped": ["https://example.com/rss"]}')
        feed = client.get("/api/feeds").json()[0]
        assert feed["title"] == "example.com"

        with patch(
            "rss_kindle.api.feeds.make_http_client", new=feed_http_client(FIXTURE.read_bytes())
        ):
            client.post(f"/api/feeds/{feed['id']}/refresh")
        # the placeholder adopted the feed's self-reported title
        assert client.get("/api/feeds").json()[0]["title"] == "Example Feed"

        client.patch(f"/api/feeds/{feed['id']}", json={"title": "Mine"})
        with patch(
            "rss_kindle.api.feeds.make_http_client", new=feed_http_client(FIXTURE.read_bytes())
        ):
            client.post(f"/api/feeds/{feed['id']}/refresh")
        # a manual rename is never overwritten
        assert client.get("/api/feeds").json()[0]["title"] == "Mine"


def test_refresh_all_reports_errors(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        client.post("/api/feeds", json={"url": "https://ok.example.com/rss", "title": "OK"})
        client.post("/api/feeds", json={"url": "https://bad.example.com/rss", "title": "Bad"})

        def handler(request: httpx.Request) -> httpx.Response:
            if "bad" in request.url.host:
                raise RuntimeError("connection refused")
            return httpx.Response(200, content=FIXTURE.read_bytes())

        def fake_client(**overrides: object) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        with patch("rss_kindle.api.feeds.make_http_client", new=fake_client):
            r = client.post("/api/feeds/refresh")
        assert r.status_code == 200
        assert r.json() == {"inserted": 2, "errors": 1}
