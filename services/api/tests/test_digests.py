import time
from datetime import date
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


def _add_feed_with_articles(
    client: TestClient, url: str, title: str, guid_prefix: bytes, group_id: int | None = None
) -> list[int]:
    feed = client.post("/api/feeds", json={"url": url, "title": title}).json()
    if group_id is not None:
        client.patch(f"/api/feeds/{feed['id']}", json={"group_id": group_id})
    with patch("rss_kindle.api.feeds.fetch_feed_bytes") as m:
        m.return_value = FIXTURE.read_bytes().replace(b"urn:example:", guid_prefix)
        client.post(f"/api/feeds/{feed['id']}/refresh")
    arts = client.get("/api/articles", params={"feed_id": feed["id"]}).json()
    return sorted(a["id"] for a in arts)


def _wait_settled(client: TestClient, digest_id: int) -> dict:
    digest = {}
    for _ in range(50):
        digest = client.get(f"/api/digests/{digest_id}").json()
        if digest["status"] in {"ready", "failed"}:
            return digest
        time.sleep(0.1)
    return digest


def test_create_digest_generates_epub(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        r = client.post("/api/digests", json={"article_ids": ids, "title": "2026-04-16"})
        assert r.status_code == 201
        created = r.json()
        assert isinstance(created, list) and len(created) == 1
        digest = created[0]
        assert digest["status"] in {"pending", "generating", "ready"}
        assert digest["group_name"] is None

        digest_id = digest["id"]
        assert _wait_settled(client, digest_id)["status"] == "ready"

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
            "rss_kindle.services.digest_service.build_digest_epub",
            side_effect=RuntimeError("boom: disk full"),
        ):
            r = client.post("/api/digests", json={"article_ids": ids})
            assert r.status_code == 201
            digest_id = r.json()[0]["id"]

        digest = _wait_settled(client, digest_id)
        assert digest["status"] == "failed"
        assert "boom: disk full" in digest["error"]

        r = client.get(f"/api/digests/{digest_id}/download")
        assert r.status_code == 409


def test_per_group_compile_partitions_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ai = client.post("/api/groups", json={"name": "AI"}).json()
        gaming = client.post("/api/groups", json={"name": "Gaming"}).json()
        a_ids = _add_feed_with_articles(
            client, "https://a.example/rss", "A", b"urn:a:", ai["id"]
        )
        b_ids = _add_feed_with_articles(
            client, "https://b.example/rss", "B", b"urn:b:", gaming["id"]
        )
        c_ids = _add_feed_with_articles(client, "https://c.example/rss", "C", b"urn:c:")

        # queue order: A1, B1, A2, C1 → buckets AI[2], Gaming[1], Ungrouped[1] last
        for article_id in (a_ids[0], b_ids[0], a_ids[1], c_ids[0]):
            assert client.post(f"/api/queue/{article_id}").status_code == 200

        r = client.post("/api/digests", json={"split": "per_group"})
        assert r.status_code == 201
        created = r.json()
        today = date.today().isoformat()
        assert [d["title"] for d in created] == [
            f"{today} — AI",
            f"{today} — Gaming",
            f"{today} — Ungrouped",
        ]
        assert [d["group_name"] for d in created] == ["AI", "Gaming", "Ungrouped"]
        assert [d["article_count"] for d in created] == [2, 1, 1]

        # the queue cleared once, all queued articles marked read
        assert client.get("/api/queue").json() == []
        unread_ids = {a["id"] for a in client.get("/api/articles", params={"unread": True}).json()}
        assert unread_ids.isdisjoint({a_ids[0], a_ids[1], b_ids[0], c_ids[0]})

        for d in created:
            assert _wait_settled(client, d["id"])["status"] == "ready"


def test_per_group_single_bucket_still_suffixed(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ai = client.post("/api/groups", json={"name": "AI"}).json()
        a_ids = _add_feed_with_articles(
            client, "https://a.example/rss", "A", b"urn:a:", ai["id"]
        )
        r = client.post("/api/digests", json={"article_ids": a_ids, "split": "per_group"})
        created = r.json()
        assert len(created) == 1
        assert created[0]["title"].endswith(" — AI")
        assert created[0]["group_name"] == "AI"


def test_epub_filename_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        r = client.post("/api/digests", json={"article_ids": ids, "title": "a/b: c"})
        digest = _wait_settled(client, r.json()[0]["id"])
        assert digest["status"] == "ready"
        name = Path(digest["epub_path"]).name
        assert "/" not in name and ":" not in name
        assert Path(digest["epub_path"]).is_file()


def test_list_digests(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        client.post("/api/digests", json={"article_ids": ids})
        r = client.get("/api/digests")
        assert r.status_code == 200
        assert len(r.json()) == 1


def _patched_fetch(mapping: dict[str, str | None]):
    """Replacement for digest_service.fetch_many: returns canned content per url
    so compile-time retrieval is deterministic and never hits the network."""

    async def fake(urls, settings):
        return {u: mapping.get(u) for u in urls}

    return fake


def test_compile_fetches_missing_content_and_caches_it(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        # seeded articles are summary-only (no full_content) — exactly the
        # enqueue-without-preview case that used to ship empty.
        arts = client.get("/api/articles").json()
        assert all(not a["has_full_content"] for a in arts)
        urls = {a["id"]: a["url"] for a in arts}
        body = "<p>The complete article body, fetched at compile time.</p>"
        mapping = {u: body for u in urls.values()}

        with patch(
            "rss_kindle.services.digest_service.fetch_many",
            new=_patched_fetch(mapping),
        ):
            r = client.post("/api/digests", json={"article_ids": ids, "title": "edition"})
            digest_id = r.json()[0]["id"]
            assert _wait_settled(client, digest_id)["status"] == "ready"

        entries = client.get(f"/api/digests/{digest_id}/articles").json()
        assert entries and all(e["fetch_status"] == "full" for e in entries)
        # content was persisted back onto the articles for re-compiles / preview
        for article_id in ids:
            detail = client.get(f"/api/articles/{article_id}").json()
            assert detail["full_content"] == body
            assert detail["has_full_content"] is True


def test_compile_blocked_fetch_falls_back_to_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        urls = [a["url"] for a in client.get("/api/articles").json()]
        with patch(
            "rss_kindle.services.digest_service.fetch_many",
            new=_patched_fetch({u: None for u in urls}),  # every fetch blocked
        ):
            r = client.post("/api/digests", json={"article_ids": ids})
            digest_id = r.json()[0]["id"]
            assert _wait_settled(client, digest_id)["status"] == "ready"

        entries = client.get(f"/api/digests/{digest_id}/articles").json()
        # sample.atom entries carry summaries, so the fallback is 'summary'
        assert entries and all(e["fetch_status"] == "summary" for e in entries)


def test_remove_article_rebuilds_and_empty_edition_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        assert len(ids) == 2
        urls = [a["url"] for a in client.get("/api/articles").json()]
        fake = _patched_fetch({u: "<p>body</p>" for u in urls})
        with patch("rss_kindle.services.digest_service.fetch_many", new=fake):
            digest_id = client.post(
                "/api/digests", json={"article_ids": ids, "title": "edit-me"}
            ).json()[0]["id"]
            assert _wait_settled(client, digest_id)["status"] == "ready"

            # drop one member → rebuilds with one fewer article
            r = client.delete(f"/api/digests/{digest_id}/articles/{ids[0]}")
            assert r.status_code == 200
            assert r.json()["article_count"] == 1
            assert _wait_settled(client, digest_id)["status"] == "ready"
            remaining = client.get(f"/api/digests/{digest_id}/articles").json()
            assert [e["article_id"] for e in remaining] == [ids[1]]

            # removing the article state must NOT mark it unread
            assert client.get(f"/api/articles/{ids[0]}").json()["read_at"] is not None

            # drop the last member → empty edition is 'failed', not an empty book
            r = client.delete(f"/api/digests/{digest_id}/articles/{ids[1]}")
            assert r.status_code == 200
            assert r.json()["status"] == "failed"
            assert "empty" in r.json()["error"]

        # 404s for unknown members / digests
        assert client.delete(f"/api/digests/{digest_id}/articles/99999").status_code == 404
        assert client.delete("/api/digests/99999/articles/1").status_code == 404
