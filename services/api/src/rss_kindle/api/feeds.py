from __future__ import annotations

import json
import logging
import sqlite3
from xml.etree import ElementTree as ET
from xml.sax.saxutils import quoteattr

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, status

from rss_kindle.config import make_http_client
from rss_kindle.db import Database
from rss_kindle.models import Feed, FeedCreate, FeedUpdate
from rss_kindle.services.feed_poller import placeholder_title
from rss_kindle.services.poller import poll_feed
from rss_kindle.services.saved_links import NOT_SAVED_LINKS

router = APIRouter(prefix="/api/feeds", tags=["feeds"])

logger = logging.getLogger(__name__)

FEED_COLUMNS = (
    "id, url, title, site_url, last_polled, created_at, group_id, "
    "poll_interval_minutes, last_error, last_error_at, consecutive_failures, "
    "(SELECT COUNT(*) FROM articles a WHERE a.feed_id = feeds.id AND a.read_at IS NULL) "
    "AS unread_count"
)


@router.get("", response_model=list[Feed])
async def list_feeds(request: Request) -> list[Feed]:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT {FEED_COLUMNS} FROM feeds WHERE {NOT_SAVED_LINKS} "
            "ORDER BY created_at DESC, id DESC"
        )
        rows = await cur.fetchall()
    return [Feed.model_validate(dict(r)) for r in rows]


@router.post("", response_model=Feed, status_code=status.HTTP_201_CREATED)
async def create_feed(payload: FeedCreate, request: Request) -> Feed:
    db = request.app.state.db
    try:
        async with db.connect() as conn:
            cur = await conn.execute(
                "INSERT INTO feeds (url, title) VALUES (?, ?)",
                (str(payload.url), payload.title),
            )
            feed_id = cur.lastrowid
            await conn.commit()
            cur = await conn.execute(
                f"SELECT {FEED_COLUMNS} FROM feeds WHERE id = ?",
                (feed_id,),
            )
            row = await cur.fetchone()
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail="feed with this url already exists") from e
    if row is None:
        raise RuntimeError(f"feed {feed_id} not found after insert")
    return Feed.model_validate(dict(row))


async def _group_id_for(
    conn: aiosqlite.Connection, name: str, cache: dict[str, int]
) -> int:
    """Resolve a group by name (the column's NOCASE collation makes the match
    case-insensitive), creating it at the end of the order when missing."""
    key = name.casefold()
    if key in cache:
        return cache[key]
    cur = await conn.execute("SELECT id FROM groups WHERE name = ?", (name,))
    row = await cur.fetchone()
    if row is None:
        cur = await conn.execute(
            "INSERT INTO groups (name, position) VALUES "
            "(?, (SELECT COALESCE(MAX(position), 0) + 1 FROM groups))",
            (name,),
        )
        if cur.lastrowid is None:
            raise RuntimeError("group insert returned no row id")
        group_id = cur.lastrowid
    else:
        group_id = int(row["id"])
    cache[key] = group_id
    return group_id


async def _import_feed_rows(
    db: Database, entries: list[tuple[str, str, str | None, str | None]]
) -> dict[str, int]:
    """Insert (url, title, site_url, group_name) rows. Existing feeds are
    skipped, but they adopt the file's group when they are currently ungrouped,
    so re-importing a subscription file is the upgrade path to grouping."""
    added = 0
    skipped = 0
    regrouped = 0
    async with db.connect() as conn:
        cache: dict[str, int] = {}
        for url, title, site_url, group_name in entries:
            gid = await _group_id_for(conn, group_name, cache) if group_name else None
            try:
                await conn.execute(
                    "INSERT INTO feeds (url, title, site_url, group_id) VALUES (?, ?, ?, ?)",
                    (url, title, site_url, gid),
                )
                added += 1
            except sqlite3.IntegrityError:
                skipped += 1
                if gid is not None:
                    cur = await conn.execute(
                        "UPDATE feeds SET group_id = ? WHERE url = ? AND group_id IS NULL",
                        (gid, url),
                    )
                    regrouped += cur.rowcount
        await conn.commit()
    return {"added": added, "skipped": skipped, "regrouped": regrouped}


@router.post("/import")
async def import_opml(file: UploadFile, request: Request) -> dict[str, int]:
    content = await file.read()
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"not valid OPML: {e}") from e

    # OPML folders (outlines without xmlUrl) map to groups; nesting deeper
    # than one level flattens into the topmost folder.
    parent_of = {child: parent for parent in root.iter() for child in parent}

    def top_folder_name(node: ET.Element) -> str | None:
        name: str | None = None
        current = parent_of.get(node)
        while current is not None:
            if current.tag == "outline" and not current.get("xmlUrl"):
                label = (current.get("title") or current.get("text") or "").strip()
                if label:
                    name = label
            current = parent_of.get(current)
        return name

    entries: list[tuple[str, str, str | None, str | None]] = []
    for outline in root.iter("outline"):
        url = outline.get("xmlUrl")
        if not url:
            continue
        title = outline.get("title") or outline.get("text") or url
        entries.append((url, title, outline.get("htmlUrl"), top_folder_name(outline)))

    counts = await _import_feed_rows(request.app.state.db, entries)
    logger.info(
        "opml import: %d added, %d skipped, %d regrouped",
        counts["added"],
        counts["skipped"],
        counts["regrouped"],
    )
    return counts


@router.post("/import-json")
async def import_feeds_json(file: UploadFile, request: Request) -> dict[str, int]:
    """Import a JSON feed list: {"group name": ["feed url", …]}.

    The key "ungrouped" (case-insensitive) means no group. URLs carry no
    titles, so feeds start with hostname placeholders that the poller
    replaces with each feed's own <title> on first refresh."""
    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=400,
            detail='expected an object like {"group name": ["feed url", …]}',
        )

    entries: list[tuple[str, str, str | None, str | None]] = []
    for group_key, urls in data.items():
        name = group_key.strip()
        if not name:
            raise HTTPException(status_code=400, detail="group names must not be empty")
        if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
            raise HTTPException(
                status_code=400, detail=f'"{name}" must be a list of feed URL strings'
            )
        group_name = None if name.casefold() == "ungrouped" else name
        for url in urls:
            if not url.startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail=f"not a feed URL: {url!r}")
            entries.append((url, placeholder_title(url), None, group_name))

    counts = await _import_feed_rows(request.app.state.db, entries)
    logger.info(
        "json import: %d added, %d skipped, %d regrouped",
        counts["added"],
        counts["skipped"],
        counts["regrouped"],
    )
    return counts


@router.get("/export.json")
async def export_feeds_json(request: Request) -> Response:
    """Export the JSON feed list (the import format, round-trippable)."""
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT f.url, g.name AS group_name "
            "FROM feeds f LEFT JOIN groups g ON g.id = f.group_id "
            "ORDER BY g.position IS NULL, g.position, f.title"
        )
        rows = await cur.fetchall()
    data: dict[str, list[str]] = {}
    for r in rows:
        data.setdefault(r["group_name"] or "ungrouped", []).append(r["url"])
    return Response(
        content=json.dumps(data, indent=2) + "\n",
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="feeds.json"'},
    )


@router.get("/export.opml")
async def export_opml(request: Request) -> Response:
    db = request.app.state.db
    async with db.connect() as conn:
        # grouped feeds first (group position order), then ungrouped at top level
        cur = await conn.execute(
            "SELECT f.url, f.title, f.site_url, g.name AS group_name "
            "FROM feeds f LEFT JOIN groups g ON g.id = f.group_id "
            "ORDER BY g.position IS NULL, g.position, f.title"
        )
        rows = await cur.fetchall()

    def feed_outline(r: aiosqlite.Row) -> str:
        return (
            f"<outline text={quoteattr(r['title'])} title={quoteattr(r['title'])} "
            f'type="rss" xmlUrl={quoteattr(r["url"])}'
            + (f" htmlUrl={quoteattr(r['site_url'])}" if r["site_url"] else "")
            + "/>"
        )

    chunks: list[str] = []
    open_group: str | None = None
    for r in rows:
        if r["group_name"] != open_group:
            if open_group is not None:
                chunks.append("    </outline>")
            open_group = r["group_name"]
            if open_group is not None:
                chunks.append(
                    f"    <outline text={quoteattr(open_group)} "
                    f"title={quoteattr(open_group)}>"
                )
        chunks.append(("      " if open_group else "    ") + feed_outline(r))
    if open_group is not None:
        chunks.append("    </outline>")
    outlines = "\n".join(chunks)

    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<opml version="2.0">\n'
        "  <head>\n    <title>RSS Books feeds</title>\n  </head>\n"
        f"  <body>\n{outlines}\n  </body>\n"
        "</opml>\n"
    )
    return Response(
        content=body,
        media_type="text/x-opml",
        headers={"Content-Disposition": 'attachment; filename="feeds.opml"'},
    )


@router.patch("/{feed_id}", response_model=Feed)
async def update_feed(feed_id: int, payload: FeedUpdate, request: Request) -> Feed:
    db = request.app.state.db
    # exclude_unset so an explicit {"group_id": null} moves the feed to Ungrouped
    fields = payload.model_dump(exclude_unset=True)
    for required in ("title", "poll_interval_minutes"):
        if required in fields and fields[required] is None:
            raise HTTPException(status_code=422, detail=f"{required} cannot be null")
    try:
        async with db.connect() as conn:
            if fields:
                sets = ", ".join(f"{name} = ?" for name in fields)
                cur = await conn.execute(
                    f"UPDATE feeds SET {sets} WHERE id = ?",  # noqa: S608 (keys from the model)
                    (*fields.values(), feed_id),
                )
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="feed not found")
                await conn.commit()
            cur = await conn.execute(
                f"SELECT {FEED_COLUMNS} FROM feeds WHERE id = ?", (feed_id,)
            )
            row = await cur.fetchone()
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=404, detail="group not found") from e
    if row is None:
        raise HTTPException(status_code=404, detail="feed not found")
    return Feed.model_validate(dict(row))


@router.delete("/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feed(feed_id: int, request: Request) -> Response:
    db = request.app.state.db
    async with db.connect() as conn:
        await conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
        await conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{feed_id}/refresh")
async def refresh_feed(feed_id: int, request: Request) -> dict[str, int]:
    """Manual refresh reuses the scheduled poller: same conditional GET (a
    304 right after a scheduled poll is expected, not a bug), same health
    bookkeeping. A blocked or failing fetch surfaces as 502 with the poller's
    error string, which is what the UI toasts."""
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT id, url, etag, last_modified FROM feeds WHERE id = ?", (feed_id,)
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="feed not found")
    async with make_http_client() as client:
        result = await poll_feed(db, client, row)
    if result.error is not None:
        raise HTTPException(status_code=502, detail=f"feed fetch failed: {result.error}")
    return {"inserted": result.inserted}


@router.post("/refresh")
async def refresh_all_feeds(request: Request) -> dict[str, int]:
    db = request.app.state.db
    async with db.connect() as conn:
        cur = await conn.execute(
            f"SELECT id, url, etag, last_modified FROM feeds WHERE {NOT_SAVED_LINKS}"
        )
        rows = await cur.fetchall()
    total = 0
    errors = 0
    async with make_http_client() as client:
        for row in rows:
            result = await poll_feed(db, client, row)
            total += result.inserted
            if result.error is not None:
                errors += 1
    logger.info("refreshed %d feeds: %d new articles, %d errors", len(rows), total, errors)
    return {"inserted": total, "errors": errors}
