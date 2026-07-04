"""SSRF guard: pure check_target unit tests, the resolve_host seam, and the
two wiring points (make_http_client's transport, article_fetcher's manual
curl_cffi redirect loop)."""

import ipaddress

import httpx
import pytest
from curl_cffi.requests import Response

from rss_kindle.config import Settings, make_http_client
from rss_kindle.services import article_fetcher, net_guard
from rss_kindle.services.net_guard import (
    GuardConfig,
    SSRFBlockedError,
    check_target,
    guard_config_from_settings,
)

DEFAULT_CFG = GuardConfig(enabled=True, allowed_hosts=frozenset(), allowed_networks=())
DISABLED_CFG = GuardConfig(enabled=False, allowed_hosts=frozenset(), allowed_networks=())


async def test_rejects_non_http_scheme() -> None:
    with pytest.raises(SSRFBlockedError, match="scheme"):
        await check_target("ftp://example.com/x", DEFAULT_CFG)


async def test_rejects_missing_host() -> None:
    with pytest.raises(SSRFBlockedError, match="no host"):
        await check_target("http:///path", DEFAULT_CFG)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "192.168.1.1",
        "172.16.0.5",
        "169.254.169.254",  # cloud metadata endpoint
        "::1",
        "fe80::1",
        "fc00::1",
    ],
)
async def test_literal_private_addresses_blocked(ip: str) -> None:
    host = f"[{ip}]" if ":" in ip else ip
    with pytest.raises(SSRFBlockedError, match="SSRF_ALLOWED_HOSTS"):
        await check_target(f"http://{host}/x", DEFAULT_CFG)


async def test_literal_public_address_allowed() -> None:
    await check_target("http://8.8.8.8/x", DEFAULT_CFG)  # must not raise


async def test_disabled_guard_allows_private_literal() -> None:
    await check_target("http://127.0.0.1/x", DISABLED_CFG)  # must not raise


async def test_scheme_and_host_checks_apply_even_when_disabled() -> None:
    with pytest.raises(SSRFBlockedError, match="scheme"):
        await check_target("ftp://x/y", DISABLED_CFG)


async def test_allowlisted_hostname_skips_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    async def fake_resolve(host: str) -> list[net_guard.IPAddress]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(net_guard, "resolve_host", fake_resolve)
    cfg = GuardConfig(enabled=True, allowed_hosts=frozenset({"nas.lan"}), allowed_networks=())
    await check_target("http://nas.lan/x", cfg)
    assert called is False


async def test_allowed_network_permits_literal_ip() -> None:
    cfg = GuardConfig(
        enabled=True,
        allowed_hosts=frozenset(),
        allowed_networks=(ipaddress.ip_network("192.168.1.0/24"),),
    )
    await check_target("http://192.168.1.50/x", cfg)  # must not raise


async def test_resolved_private_address_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str) -> list[net_guard.IPAddress]:
        return [ipaddress.ip_address("10.0.0.5")]

    monkeypatch.setattr(net_guard, "resolve_host", fake_resolve)
    with pytest.raises(SSRFBlockedError, match="SSRF_ALLOWED_HOSTS"):
        await check_target("http://internal.example/x", DEFAULT_CFG)


async def test_resolved_public_address_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str) -> list[net_guard.IPAddress]:
        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr(net_guard, "resolve_host", fake_resolve)
    await check_target("http://public.example/x", DEFAULT_CFG)  # must not raise


async def test_resolution_failure_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str) -> list[net_guard.IPAddress]:
        raise OSError("nodename nor servname provided")

    monkeypatch.setattr(net_guard, "resolve_host", fake_resolve)
    with pytest.raises(SSRFBlockedError, match="DNS resolution failed"):
        await check_target("http://broken.example/x", DEFAULT_CFG)


async def test_no_addresses_resolved_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str) -> list[net_guard.IPAddress]:
        return []

    monkeypatch.setattr(net_guard, "resolve_host", fake_resolve)
    with pytest.raises(SSRFBlockedError, match="no addresses resolved"):
        await check_target("http://empty.example/x", DEFAULT_CFG)


def test_guard_config_from_settings_parses_hosts_and_networks() -> None:
    settings = Settings(ssrf_allowed_hosts="nas.lan, 192.168.1.50, 10.0.0.0/8")
    cfg = guard_config_from_settings(settings)
    assert cfg.allowed_hosts == {"nas.lan"}
    assert any(ipaddress.ip_address("192.168.1.50") in n for n in cfg.allowed_networks)
    assert any(ipaddress.ip_address("10.5.5.5") in n for n in cfg.allowed_networks)


# --- make_http_client wiring --------------------------------------------------


async def test_make_http_client_blocks_before_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SSRF_ALLOWED_HOSTS", raising=False)
    async with make_http_client() as client:
        with pytest.raises(SSRFBlockedError):
            # a closed local port: if this ever actually dialed out, it would
            # raise a connection error instead - the guard must pre-empt that.
            await client.get("http://127.0.0.1:1/x")


async def test_make_http_client_honors_ssrf_allowed_hosts_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SSRF_ALLOWED_HOSTS", "127.0.0.1")
    async with make_http_client() as client:
        # allowed through the guard; fails at the real (loopback-only) connect
        # instead, proving the guard - not a network fluke - was what blocked it above.
        with pytest.raises(httpx.ConnectError):
            await client.get("http://127.0.0.1:1/x")


async def test_make_http_client_guard_disabled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSRF_GUARD_ENABLED", "false")
    async with make_http_client() as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("http://127.0.0.1:1/x")


# --- article_fetcher (curl_cffi) redirect wiring ------------------------------


class _FakeAsyncSession:
    def __init__(self, responses: list[Response]) -> None:
        self._responses = list(responses)
        self.requested_urls: list[str] = []

    async def __aenter__(self) -> "_FakeAsyncSession":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def get(self, url: str, **kwargs: object) -> Response:
        self.requested_urls.append(url)
        return self._responses.pop(0)


def _fake_response(
    status_code: int, *, location: str | None = None, content: bytes = b""
) -> Response:
    r = Response()
    r.status_code = status_code
    r.headers = {"location": location} if location else {}
    r.content = content
    return r


@pytest.fixture(autouse=True)
def _resolve_to_public_address(monkeypatch: pytest.MonkeyPatch) -> None:
    """article_fetcher tests exercise real hostnames (one.example, two.example);
    they must resolve to something public so the guard doesn't reject them."""

    async def fake_resolve(host: str) -> list[net_guard.IPAddress]:
        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr(net_guard, "resolve_host", fake_resolve)


async def test_fetch_url_bytes_checks_every_redirect_hop(monkeypatch: pytest.MonkeyPatch) -> None:
    checked: list[str] = []
    real_check_target = net_guard.check_target

    async def spy_check_target(url: str, cfg: GuardConfig) -> None:
        checked.append(url)
        await real_check_target(url, cfg)

    monkeypatch.setattr(article_fetcher, "check_target", spy_check_target)

    session = _FakeAsyncSession(
        [
            _fake_response(302, location="https://two.example/final"),
            _fake_response(200, content=b"final body"),
        ]
    )
    monkeypatch.setattr(article_fetcher, "AsyncSession", lambda: session)

    body = await article_fetcher.fetch_url_bytes("https://one.example/start")

    assert body == b"final body"
    assert checked == ["https://one.example/start", "https://two.example/final"]
    assert session.requested_urls == checked


async def test_fetch_url_bytes_blocks_malicious_redirect_hop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeAsyncSession([_fake_response(302, location="http://127.0.0.1/admin")])
    monkeypatch.setattr(article_fetcher, "AsyncSession", lambda: session)

    with pytest.raises(SSRFBlockedError):
        await article_fetcher.fetch_url_bytes("https://one.example/start")

    # the malicious hop was never actually requested
    assert session.requested_urls == ["https://one.example/start"]


async def test_fetch_url_bytes_redirect_loop_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _fake_response(302, location="https://loop.example/x")
        for _ in range(article_fetcher.MAX_REDIRECTS + 2)
    ]
    session = _FakeAsyncSession(responses)
    monkeypatch.setattr(article_fetcher, "AsyncSession", lambda: session)

    with pytest.raises(RuntimeError, match="too many redirects"):
        await article_fetcher.fetch_url_bytes("https://loop.example/start")
