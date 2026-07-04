from collections.abc import Callable

import httpx
import pytest


def feed_http_client(
    content: bytes, *, status_code: int = 200, headers: dict[str, str] | None = None
) -> Callable[..., httpx.AsyncClient]:
    """A make_http_client()-shaped replacement that answers every request with
    one fixed response - the common case when a test just needs a feed poll
    (manual refresh, scheduled tick) to "fetch" known bytes. Patch it over
    rss_books.api.feeds.make_http_client (manual refresh) or
    rss_books.services.scheduler.make_http_client (scheduled tick)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=content, headers=headers or {})

    def factory(**overrides: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return factory


def feed_http_client_error(exc: BaseException) -> Callable[..., httpx.AsyncClient]:
    """Same shape as feed_http_client, but every request raises `exc` -
    simulates a transport-level failure (DNS, connect, TLS) for feed-refresh
    error-path tests."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    def factory(**overrides: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return factory


@pytest.fixture(autouse=True)
def _no_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests hermetic: httpx honors proxy env vars (trust_env), which
    would otherwise leak the host's proxy configuration into test clients."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv(var.lower(), raising=False)


@pytest.fixture(autouse=True)
def _no_background_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    """TestClient apps must not start the polling loop; scheduler tests
    drive Scheduler.tick() directly with an injected clock and client."""
    monkeypatch.setenv("SCHEDULER_ENABLED", "0")
