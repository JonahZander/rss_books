import logging
from unittest.mock import patch

from curl_cffi.requests.exceptions import RequestException

from rss_books.models import AppSettings
from rss_books.services import article_fetcher


async def _no_op_fetch(url: str, settings: AppSettings) -> str | None:
    return f"<p>{url}</p>"


async def test_fetch_many_spaces_same_host_but_not_distinct_hosts():
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    urls = [
        "https://one.example/a",
        "https://one.example/b",  # same host as the first → one spacing delay
        "https://two.example/a",  # different host → no delay
    ]
    with (
        patch.object(article_fetcher, "fetch_article_content", new=_no_op_fetch),
        patch.object(article_fetcher.asyncio, "sleep", new=fake_sleep),
    ):
        results = await article_fetcher.fetch_many(urls, AppSettings())

    assert set(results) == set(urls)
    assert all(results[u] for u in urls)
    # exactly one same-host gap; each gap is at least the base politeness window
    assert len(sleeps) == 1
    assert sleeps[0] >= article_fetcher.SAME_HOST_DELAY_SECONDS


async def test_fetch_failure_is_logged(caplog):
    """A refused fetch degrades to None as before, but the reason must land
    in the log - an edition quietly missing its content is undebuggable
    otherwise."""

    async def refuse(url: str) -> bytes:
        raise RequestException("HTTP Error 403")

    with (
        patch.object(article_fetcher, "fetch_url_bytes", new=refuse),
        caplog.at_level(logging.WARNING, logger="rss_books.services.article_fetcher"),
    ):
        content = await article_fetcher.fetch_article_content(
            "https://walled.example/post", AppSettings()
        )

    assert content is None
    assert any(
        "article fetch failed" in r.getMessage() and "walled.example" in r.getMessage()
        for r in caplog.records
    )


async def test_fetch_many_dedupes_urls():
    calls: list[str] = []

    async def counting_fetch(url: str, settings: AppSettings) -> str | None:
        calls.append(url)
        return "x"

    async def fake_sleep(seconds: float) -> None:
        pass

    with (
        patch.object(article_fetcher, "fetch_article_content", new=counting_fetch),
        patch.object(article_fetcher.asyncio, "sleep", new=fake_sleep),
    ):
        await article_fetcher.fetch_many(
            ["https://x.example/a", "https://x.example/a"], AppSettings()
        )

    assert calls == ["https://x.example/a"]
