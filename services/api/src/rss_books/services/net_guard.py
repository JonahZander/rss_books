"""SSRF guard for every outbound fetch the app makes on a user-supplied URL
(feed URLs, article pages, embedded images). Without it, an unauthenticated
API (there is no auth on /api/*) that fetches whatever URL a feed/article
happens to contain is an open proxy onto the LAN and cloud metadata
endpoints (169.254.169.254) the moment it's reachable from outside a trusted
network - which is exactly the deployment homelab users reach for (reverse
proxied to the internet).

Accepted residual risk (see the senior review this shipped under): this is
resolve-then-verify, not connection-pinned. httpx/curl_cffi re-resolve the
host at actual connect time, so a TTL-0 DNS-rebinding attacker who controls
both a subscribed feed/article host and its DNS could pass this check and
still connect to a private address on the real request. Pinning the
resolved IP would require a custom connection pool / resolver hook, and is
effectively impossible under curl_cffi's Chrome TLS impersonation without
breaking SNI. The payoff for an attacker is a blind GET (bytes land in the
victim's own EPUB), which doesn't justify that cost for a homelab tool.
Per-request, per-redirect-hop re-checking (what the transport wiring below
gives) is the accepted cut line. Do not cache `resolve_host` results across
requests - that would only widen the rebinding window this already accepts.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx

if TYPE_CHECKING:
    from rss_books.config import Settings

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class SSRFBlockedError(RuntimeError):
    """Raised when a target URL resolves to (or names) a disallowed address."""


def _is_blocked_ip(ip: IPAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _literal_ip(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


async def resolve_host(host: str) -> list[IPAddress]:
    """The patchable test seam: every A/AAAA address a hostname resolves to,
    deduplicated. Real work happens in a thread since getaddrinfo blocks."""
    infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    seen: dict[IPAddress, None] = {}
    for _family, _type, _proto, _canon, sockaddr in infos:
        try:
            seen.setdefault(ipaddress.ip_address(sockaddr[0]), None)
        except ValueError:
            continue
    return list(seen)


@dataclass(frozen=True)
class GuardConfig:
    enabled: bool
    allowed_hosts: frozenset[str]
    allowed_networks: tuple[IPNetwork, ...]


def _parse_allowed_hosts(raw: str) -> tuple[frozenset[str], tuple[IPNetwork, ...]]:
    """Split the comma-separated SSRF_ALLOWED_HOSTS env value into bare
    hostnames (matched by exact, case-insensitive name) and IP/CIDR entries
    (matched by containment, so a bare IP works via its /32 or /128)."""
    hosts: set[str] = set()
    networks: list[IPNetwork] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            hosts.add(entry.lower())
    return frozenset(hosts), tuple(networks)


def guard_config_from_settings(settings: Settings) -> GuardConfig:
    hosts, networks = _parse_allowed_hosts(settings.ssrf_allowed_hosts)
    return GuardConfig(
        enabled=settings.ssrf_guard_enabled, allowed_hosts=hosts, allowed_networks=networks
    )


def _allowed_by_network(ip: IPAddress, cfg: GuardConfig) -> bool:
    return any(ip in net for net in cfg.allowed_networks)


def _blocked_message(host: str, ip: IPAddress | None = None) -> str:
    target = host if ip is None or str(ip) == host else f"{host} -> {ip}"
    return (
        f"blocked private/internal address {target} (SSRF guard); "
        "allow it via SSRF_ALLOWED_HOSTS"
    )


async def check_target(url: str, cfg: GuardConfig) -> None:
    """Raise SSRFBlockedError if `url` must not be fetched. Scheme and host
    sanity checks always apply (they're not really "SSRF", just malformed
    fetch targets); everything else is a no-op when the guard is disabled."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlockedError(f"blocked non-http(s) scheme {parsed.scheme!r}: {url}")
    host = parsed.hostname
    if not host:
        raise SSRFBlockedError(f"blocked request with no host: {url}")
    if not cfg.enabled:
        return
    if host.lower() in cfg.allowed_hosts:
        return

    literal = _literal_ip(host)
    if literal is not None:
        if _allowed_by_network(literal, cfg):
            return
        if _is_blocked_ip(literal):
            raise SSRFBlockedError(_blocked_message(host))
        return

    # Not a literal IP and not on the allowlist: resolve and verify every
    # address, failing closed (DNS failure or any blocked address blocks the
    # whole request - a hostname can round-robin across several addresses).
    try:
        addresses = await resolve_host(host)
    except OSError as exc:
        raise SSRFBlockedError(
            f"blocked {host!r} (SSRF guard): DNS resolution failed ({exc}); "
            "allow it via SSRF_ALLOWED_HOSTS"
        ) from exc
    if not addresses:
        raise SSRFBlockedError(
            f"blocked {host!r} (SSRF guard): no addresses resolved; "
            "allow it via SSRF_ALLOWED_HOSTS"
        )
    for address in addresses:
        if _allowed_by_network(address, cfg):
            continue
        if _is_blocked_ip(address):
            raise SSRFBlockedError(_blocked_message(host, address))


class GuardedAsyncTransport(httpx.AsyncHTTPTransport):
    """An AsyncHTTPTransport that checks every request (including each hop of
    a redirect chain - httpx re-invokes the transport per hop) before letting
    it through. This is the one wiring point for every httpx-based fetch
    (feeds, articles-without-full-content, images); see make_http_client()."""

    def __init__(self, cfg: GuardConfig, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._cfg = cfg

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await check_target(str(request.url), self._cfg)
        return await super().handle_async_request(request)
