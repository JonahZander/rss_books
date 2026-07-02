from __future__ import annotations

import secrets
from base64 import b64decode
from datetime import UTC, datetime
from urllib.parse import quote
from xml.etree import ElementTree as ET

from fastapi import APIRouter, HTTPException, Request, Response

from rss_kindle.services.settings_store import get_app_settings

router = APIRouter(tags=["opds"])

ATOM_NS = "http://www.w3.org/2005/Atom"
NAV_TYPE = "application/atom+xml;profile=opds-catalog;kind=navigation"
ACQ_TYPE = "application/atom+xml;profile=opds-catalog;kind=acquisition"
ACQ_REL = "http://opds-spec.org/acquisition"

ET.register_namespace("", ATOM_NS)


def _el(parent: ET.Element | None, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    qtag = f"{{{ATOM_NS}}}{tag}"
    el = ET.Element(qtag, attrs) if parent is None else ET.SubElement(parent, qtag, attrs)
    if text is not None:
        el.text = text
    return el


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_iso(value: str | None) -> str:
    if not value:
        return _now_iso()
    text = str(value).replace(" ", "T")
    return text if text.endswith("Z") or "+" in text else f"{text}Z"


def _xml_response(feed: ET.Element, media_type: str) -> Response:
    payload = ET.tostring(feed, encoding="utf-8", xml_declaration=True)
    return Response(content=payload, media_type=media_type)


async def _check_auth(request: Request) -> None:
    settings = await get_app_settings(request.app.state.db)
    if not settings.opds_auth_enabled:
        return
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            decoded = b64decode(header[6:]).decode("utf-8")
        except Exception:
            decoded = ""
        username, _, password = decoded.partition(":")
        if secrets.compare_digest(username, settings.opds_username) and secrets.compare_digest(
            password, settings.opds_password
        ):
            return
    raise HTTPException(
        status_code=401,
        detail="authentication required",
        headers={"WWW-Authenticate": 'Basic realm="rss-kindle-selector"'},
    )


@router.get("/opds")
async def opds_root(request: Request) -> Response:
    await _check_auth(request)
    base = str(request.base_url).rstrip("/")

    feed = _el(None, "feed")
    _el(feed, "id", "urn:rss-kindle-selector:opds")
    _el(feed, "title", "RSS Books")
    _el(feed, "updated", _now_iso())
    _el(feed, "link", rel="self", href=f"{base}/opds", type=NAV_TYPE)
    _el(feed, "link", rel="start", href=f"{base}/opds", type=NAV_TYPE)

    entry = _el(feed, "entry")
    _el(entry, "title", "Editions")
    _el(entry, "id", "urn:rss-kindle-selector:opds:digests")
    _el(entry, "updated", _now_iso())
    _el(entry, "content", "Hand-pressed editions, newest first.", type="text")
    _el(entry, "link", rel="subsection", href=f"{base}/opds/digests", type=ACQ_TYPE)

    # One folder per render profile, so each device browses only the editions
    # pressed for it.
    settings = await get_app_settings(request.app.state.db)
    for p in settings.profiles:
        entry = _el(feed, "entry")
        _el(entry, "title", f"Editions — {p.name}")
        _el(entry, "id", f"urn:rss-kindle-selector:opds:profile:{p.name}")
        _el(entry, "updated", _now_iso())
        _el(entry, "content", f"Editions pressed for {p.name}.", type="text")
        _el(
            entry,
            "link",
            rel="subsection",
            href=f"{base}/opds/profiles/{quote(p.name, safe='')}",
            type=ACQ_TYPE,
        )

    return _xml_response(feed, NAV_TYPE)


async def _acquisition_feed(
    request: Request,
    *,
    feed_id: str,
    title: str,
    self_path: str,
    profile: str | None,
) -> Response:
    base = str(request.base_url).rstrip("/")
    db = request.app.state.db

    where = "status = 'ready'"
    params: tuple[str, ...] = ()
    if profile is not None:
        where += " AND profile = ?"
        params = (profile,)
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT id, title, size_bytes, created_at, "
            "(SELECT COUNT(*) FROM digest_articles da WHERE da.digest_id = digests.id) "
            f"AS article_count FROM digests WHERE {where} "
            "ORDER BY created_at DESC, id DESC",
            params,
        )
        rows = await cur.fetchall()

    feed = _el(None, "feed")
    _el(feed, "id", feed_id)
    _el(feed, "title", title)
    _el(feed, "updated", _row_iso(rows[0]["created_at"]) if rows else _now_iso())
    _el(feed, "link", rel="self", href=f"{base}{self_path}", type=ACQ_TYPE)
    _el(feed, "link", rel="start", href=f"{base}/opds", type=NAV_TYPE)

    for row in rows:
        entry = _el(feed, "entry")
        _el(entry, "title", f"Edition {row['title']}")
        _el(entry, "id", f"urn:rss-kindle-selector:digest:{row['id']}")
        _el(entry, "updated", _row_iso(row["created_at"]))
        author = _el(entry, "author")
        _el(author, "name", "RSS Books")
        count = row["article_count"]
        size_mb = (row["size_bytes"] or 0) / 2**20
        plural = "article" if count == 1 else "articles"
        _el(entry, "content", f"{count} {plural} · {size_mb:.1f} MB", type="text")
        _el(
            entry,
            "link",
            rel=ACQ_REL,
            href=f"{base}/api/digests/{row['id']}/download",
            type="application/epub+zip",
        )

    return _xml_response(feed, ACQ_TYPE)


@router.get("/opds/digests")
async def opds_digests(request: Request) -> Response:
    await _check_auth(request)
    return await _acquisition_feed(
        request,
        feed_id="urn:rss-kindle-selector:opds:digests",
        title="Editions",
        self_path="/opds/digests",
        profile=None,
    )


@router.get("/opds/profiles/{name}")
async def opds_profile(name: str, request: Request) -> Response:
    """Editions pressed with a given render profile — one OPDS folder per
    device, so a reader subscribes only to books built for it."""
    await _check_auth(request)
    settings = await get_app_settings(request.app.state.db)
    if not any(p.name == name for p in settings.profiles):
        raise HTTPException(status_code=404, detail="unknown render profile")
    return await _acquisition_feed(
        request,
        feed_id=f"urn:rss-kindle-selector:opds:profile:{name}",
        title=f"Editions — {name}",
        self_path=f"/opds/profiles/{quote(name, safe='')}",
        profile=name,
    )
