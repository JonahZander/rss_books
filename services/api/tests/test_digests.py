import time
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from conftest import feed_http_client
from rss_books.api.main import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"


def _seed(client: TestClient) -> list[int]:
    r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
    feed_id = r.json()["id"]
    with patch("rss_books.api.feeds.make_http_client", new=feed_http_client(FIXTURE.read_bytes())):
        client.post(f"/api/feeds/{feed_id}/refresh")
    return [a["id"] for a in client.get("/api/articles").json()]


def _add_feed_with_articles(
    client: TestClient, url: str, title: str, guid_prefix: bytes, group_id: int | None = None
) -> list[int]:
    feed = client.post("/api/feeds", json={"url": url, "title": title}).json()
    if group_id is not None:
        client.patch(f"/api/feeds/{feed['id']}", json={"group_id": group_id})
    content = FIXTURE.read_bytes().replace(b"urn:example:", guid_prefix)
    with patch("rss_books.api.feeds.make_http_client", new=feed_http_client(content)):
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


def test_link_qr_setting_embeds_codes_in_epub(tmp_path, monkeypatch):
    import io
    import zipfile

    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        s = client.get("/api/settings").json()
        s["link_qr"] = "articles"
        assert client.put("/api/settings", json=s).status_code == 200

        r = client.post("/api/digests", json={"article_ids": ids})
        digest_id = r.json()[0]["id"]
        assert _wait_settled(client, digest_id)["status"] == "ready"

        epub_bytes = client.get(f"/api/digests/{digest_id}/download").content
        with zipfile.ZipFile(io.BytesIO(epub_bytes)) as z:
            assert any(n.startswith("EPUB/qr/") for n in z.namelist())


async def test_build_epub_runs_off_event_loop(tmp_path):
    """Best-effort timing test: while the (deliberately slowed) EPUB build
    blocks synchronously in a worker thread, a concurrent async task keeps
    advancing - proof asyncio.to_thread actually takes _build_epub off the
    loop rather than freezing every other request for its duration."""
    import asyncio
    import time

    from rss_books.db import Database
    from rss_books.services import digest_service

    db = Database(tmp_path / "t.db")
    await db.init()
    async with db.connect() as conn:
        await conn.execute("INSERT INTO feeds (url, title) VALUES ('https://f.example/rss', 'F')")
        await conn.execute(
            "INSERT INTO articles (feed_id, guid, title, url, summary, full_content) "
            "VALUES (1, 'g1', 'T', 'https://f.example/a', '<p>s</p>', '<p>full</p>')"
        )
        await conn.execute("INSERT INTO digests (title, status) VALUES ('D', 'pending')")
        await conn.execute(
            "INSERT INTO digest_articles (digest_id, article_id, position) VALUES (1, 1, 0)"
        )
        await conn.commit()

    original_build = digest_service._build_epub

    def slow_build(*args, **kwargs):
        time.sleep(0.2)
        return original_build(*args, **kwargs)

    counter = {"n": 0}

    async def tick() -> None:
        for _ in range(40):
            await asyncio.sleep(0.01)
            counter["n"] += 1

    with patch.object(digest_service, "_build_epub", slow_build):
        ok, _ = await asyncio.gather(
            digest_service.generate_digest(db, 1, tmp_path / "epubs"),
            tick(),
        )
    assert ok is True
    # 0.2s of blocking build work must not have stalled the 10ms-interval counter
    assert counter["n"] >= 15


def test_digest_build_failure_sets_failed_status(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        with patch(
            "rss_books.services.digest_service.build_digest_epub",
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
            f"{today} - AI",
            f"{today} - Gaming",
            f"{today} - Ungrouped",
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
        assert created[0]["title"].endswith(" - AI")
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
        # seeded articles are summary-only (no full_content), exactly the
        # enqueue-without-preview case that used to ship empty.
        arts = client.get("/api/articles").json()
        assert all(not a["has_full_content"] for a in arts)
        urls = {a["id"]: a["url"] for a in arts}
        body = "<p>The complete article body, fetched at compile time.</p>"
        mapping = {u: body for u in urls.values()}

        with patch(
            "rss_books.services.digest_service.fetch_many",
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
            "rss_books.services.digest_service.fetch_many",
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
        with patch("rss_books.services.digest_service.fetch_many", new=fake):
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


def test_batch_remove_articles_rebuilds_once(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        a_ids = _add_feed_with_articles(client, "https://a.example/rss", "A", b"urn:a:")
        b_ids = _add_feed_with_articles(client, "https://b.example/rss", "B", b"urn:b:")
        ids = a_ids + b_ids
        assert len(ids) == 4
        urls = [a["url"] for a in client.get("/api/articles").json()]
        fake = _patched_fetch({u: "<p>body</p>" for u in urls})
        with patch("rss_books.services.digest_service.fetch_many", new=fake):
            digest_id = client.post(
                "/api/digests", json={"article_ids": ids, "title": "cull-me"}
            ).json()[0]["id"]
            assert _wait_settled(client, digest_id)["status"] == "ready"

            # drop two members in one call
            r = client.post(
                f"/api/digests/{digest_id}/articles/remove",
                json={"article_ids": [ids[0], ids[2]]},
            )
            assert r.status_code == 200
            assert r.json()["article_count"] == 2
            assert _wait_settled(client, digest_id)["status"] == "ready"
            remaining = client.get(f"/api/digests/{digest_id}/articles").json()
            assert sorted(e["article_id"] for e in remaining) == sorted([ids[1], ids[3]])

        # empty body → 400; unknown ids → 404; removing all leaves it 'failed'
        assert (
            client.post(
                f"/api/digests/{digest_id}/articles/remove", json={"article_ids": []}
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/digests/{digest_id}/articles/remove", json={"article_ids": [99999]}
            ).status_code
            == 404
        )
        r = client.post(
            f"/api/digests/{digest_id}/articles/remove",
            json={"article_ids": [ids[1], ids[3]]},
        )
        assert r.json()["status"] == "failed"


def test_compile_writes_image_cache(tmp_path, monkeypatch):
    from io import BytesIO

    import httpx
    from PIL import Image

    epub_dir = tmp_path / "epubs"
    monkeypatch.setenv("EPUB_DIR", str(epub_dir))

    buf = BytesIO()
    Image.new("RGB", (40, 20), (10, 20, 30)).save(buf, format="PNG")
    png = buf.getvalue()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=png, headers={"content-type": "image/png"})

    def fake_client(**overrides):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        urls = [a["url"] for a in client.get("/api/articles").json()]
        body = '<p>text</p><img src="https://img.example/pic.png" alt="">'
        with (
            patch(
                "rss_books.services.digest_service.fetch_many",
                new=_patched_fetch({u: body for u in urls}),
            ),
            patch("rss_books.services.digest_service.make_http_client", new=fake_client),
        ):
            digest_id = client.post("/api/digests", json={"article_ids": ids}).json()[0]["id"]
            assert _wait_settled(client, digest_id)["status"] == "ready"

        cache_dir = epub_dir / ".image_cache"
        cached = list(cache_dir.iterdir())
        assert len(cached) == 1
        assert cached[0].read_bytes() == png


def test_preview_renders_edition_html(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        urls = [a["url"] for a in client.get("/api/articles").json()]
        body = "<p>The body that should appear in the preview.</p>"
        with patch(
            "rss_books.services.digest_service.fetch_many",
            new=_patched_fetch({u: body for u in urls}),
        ):
            digest_id = client.post(
                "/api/digests", json={"article_ids": ids, "title": "Preview Me"}
            ).json()[0]["id"]
            assert _wait_settled(client, digest_id)["status"] == "ready"

        r = client.get(f"/api/digests/{digest_id}/preview")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        html = r.text
        # title page, the source link this edition now leads with, and chapter body
        assert "Preview Me" in html
        assert "Read the original at" in html
        assert "should appear in the preview" in html
        titles = [a["title"] for a in client.get("/api/articles").json()]
        for t in titles:
            assert t in html

        assert client.get("/api/digests/99999/preview").status_code == 404
