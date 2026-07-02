from pathlib import Path
from unittest.mock import patch

from curl_cffi.requests import Response
from curl_cffi.requests.exceptions import ConnectTimeout, HTTPError
from fastapi.testclient import TestClient

from rss_kindle.api.main import create_app
from rss_kindle.config import USER_AGENT

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"


def _seed_feed_with_articles(client: TestClient) -> int:
    r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
    feed_id = r.json()["id"]
    with patch("rss_kindle.api.feeds.fetch_feed_bytes") as mock_fetch:
        mock_fetch.return_value = FIXTURE.read_bytes()
        client.post(f"/api/feeds/{feed_id}/refresh")
    return feed_id


def test_list_articles_by_feed(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        feed_id = _seed_feed_with_articles(client)
        r = client.get("/api/articles", params={"feed_id": feed_id})
        assert r.status_code == 200
        articles = r.json()
        assert len(articles) == 2
        assert articles[0]["published_at"] >= articles[1]["published_at"]
        assert articles[0]["has_full_content"] is False


def test_get_article_detail(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _seed_feed_with_articles(client)
        r = client.get("/api/articles")
        article_id = r.json()[0]["id"]
        r = client.get(f"/api/articles/{article_id}")
        assert r.status_code == 200
        assert r.json()["full_content"] is None


def test_fetch_article_full_content(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _seed_feed_with_articles(client)
        article_id = client.get("/api/articles").json()[0]["id"]

        html = (
            b"<html><body><article><h1>T</h1><p>Hello world. "
            b"This paragraph is long enough for trafilatura to extract, "
            b"we need sufficient prose to pass boilerplate filters here.</p>"
            b"</article></body></html>"
        )
        with patch("rss_kindle.api.articles.fetch_url_bytes") as mock_fetch:
            mock_fetch.return_value = html
            r = client.post(f"/api/articles/{article_id}/fetch")
            assert r.status_code == 200
            assert "Hello world" in r.json()["full_content"]

        r = client.get(f"/api/articles/{article_id}")
        assert r.json()["has_full_content"] is True


def test_fetch_blocked_site_returns_502_not_500(tmp_path):
    """Bot-walled sites (e.g. openai.com → 403) must surface as a clear 502,
    not an unhandled exception — even through curl_cffi's exception types."""
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _seed_feed_with_articles(client)
        article_id = client.get("/api/articles").json()[0]["id"]

        # curl_cffi's raise_for_status() raises HTTPError carrying the response;
        # the handler reads e.response.status_code.
        resp = Response()
        resp.status_code = 403
        err = HTTPError("HTTP Error 403: Forbidden", 0, resp)
        with patch("rss_kindle.api.articles.fetch_url_bytes", side_effect=err):
            r = client.post(f"/api/articles/{article_id}/fetch")
        assert r.status_code == 502
        assert "403" in r.json()["detail"]

        # transport failures (timeouts, DNS, TLS) map to a generic 502
        timeout = ConnectTimeout("timed out")
        with patch("rss_kindle.api.articles.fetch_url_bytes", side_effect=timeout):
            r = client.post(f"/api/articles/{article_id}/fetch")
        assert r.status_code == 502


def test_user_agent_is_browser_shaped_and_shared():
    from rss_kindle.services import poller

    assert USER_AGENT.startswith("Mozilla/5.0")
    assert "rss-books" in USER_AGENT
    assert poller.USER_AGENT == USER_AGENT


FULL_CONTENT_FIXTURE = Path(__file__).parent / "fixtures" / "full_content.rss"


def _seed_feed_with_full_content(client: TestClient) -> int:
    r = client.post("/api/feeds", json={"url": "https://full.example/rss", "title": "Full"})
    feed_id = r.json()["id"]
    with patch("rss_kindle.api.feeds.fetch_feed_bytes") as mock_fetch:
        mock_fetch.return_value = FULL_CONTENT_FIXTURE.read_bytes()
        client.post(f"/api/feeds/{feed_id}/refresh")
    return feed_id


def test_feed_content_encoded_populates_full_content_without_fetch(tmp_path):
    """An entry whose <content:encoded> is fuller than its summary is stored as
    full_content at poll time — has_full_content is true with NO page fetch,
    and the stored HTML is sanitized (script/onclick scrubbed)."""
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        # if any page fetch is attempted, fail loudly — polling must not fetch
        with patch(
            "rss_kindle.api.articles.fetch_url_bytes",
            side_effect=AssertionError("must not fetch the page when feed embeds content"),
        ):
            _seed_feed_with_full_content(client)

            articles = client.get("/api/articles").json()
            by_title = {a["title"]: a for a in articles}

            embedded = by_title["Embedded Article"]
            assert embedded["has_full_content"] is True

            detail = client.get(f"/api/articles/{embedded['id']}").json()
            html = detail["full_content"]
            assert "full article body" in html
            assert "<script>" not in html  # sanitizer scrubbed the script tag
            assert "onclick" not in html  # and the event handler attribute

            # Teaser-only content:encoded (shorter than the summary) is rejected;
            # the article falls back to on-demand fetch.
            teaser = by_title["Teaser Only Article"]
            assert teaser["has_full_content"] is False


def test_article_state_lifecycle(tmp_path):
    """state walks new -> seen (read) -> queued -> in_edition with the documented
    precedence, derived in SQL for both the list and detail endpoints."""
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _seed_feed_with_articles(client)
        article_id = client.get("/api/articles").json()[0]["id"]

        def state_in_list() -> str:
            row = next(a for a in client.get("/api/articles").json() if a["id"] == article_id)
            return row["state"]

        def state_in_detail() -> str:
            return client.get(f"/api/articles/{article_id}").json()["state"]

        # new
        assert state_in_list() == "new"
        assert state_in_detail() == "new"

        # seen: read_at set
        client.post(f"/api/articles/{article_id}/read")
        assert state_in_list() == "seen"
        assert state_in_detail() == "seen"
        # the /read response itself carries the recomputed state
        assert client.post(f"/api/articles/{article_id}/read").json()["state"] == "seen"

        # queued: outranks seen
        queued = client.post(f"/api/queue/{article_id}").json()
        assert queued[0]["state"] == "queued"
        assert state_in_list() == "queued"
        assert state_in_detail() == "queued"

        # in_edition: outranks queued (compiling clears the queue but the
        # digest_articles membership keeps state at in_edition)
        r = client.post("/api/digests", json={"article_ids": [article_id]})
        assert r.status_code == 201
        assert state_in_list() == "in_edition"
        assert state_in_detail() == "in_edition"


def test_article_state_unread_reverts_to_new(tmp_path):
    """Clearing read_at on an otherwise-unreferenced article drops it back to new."""
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        _seed_feed_with_articles(client)
        article_id = client.get("/api/articles").json()[0]["id"]

        assert client.post(f"/api/articles/{article_id}/read").json()["state"] == "seen"
        assert client.post(f"/api/articles/{article_id}/unread").json()["state"] == "new"
