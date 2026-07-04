from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from rss_kindle.config import make_http_client
from rss_kindle.db import Database, placeholders
from rss_kindle.models import AppSettings, FetchStatus, RenderProfile
from rss_kindle.services.article_fetcher import fetch_many
from rss_kindle.services.cover import render_cover
from rss_kindle.services.emailer import send_digest_and_record
from rss_kindle.services.epub_builder import DigestArticle, LinkQr, build_digest_epub
from rss_kindle.services.image_pipeline import DigestImage, image_cache_dir, prepare_images
from rss_kindle.services.sanitizer import sanitize
from rss_kindle.services.settings_store import get_app_settings
from rss_kindle.services.table_renderer import (
    SUPERSAMPLE,
    pre_to_br,
    pre_to_images,
    tables_to_images,
)

logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    """Collapse path-hostile characters so titles (and group suffixes) can't
    escape EPUB_DIR or produce unopenable filenames."""
    cleaned = re.sub(r"[^\w\s.-]+", "-", name).strip(" .")
    return cleaned or "edition"


async def create_digest_records(
    db: Database,
    article_ids: list[int] | None,
    title: str | None,
    split: str = "combined",
    profiles: list[str] | None = None,
) -> list[int]:
    """Create one digest (combined) or one per feed group (per_group), crossed
    with one variant per render profile when `profiles` is given: the same
    articles pressed once per device.

    With no explicit article ids, the server-side queue is snapshotted in
    order and then cleared once, regardless of how many editions result.
    Raises ValueError when there is nothing to compile.
    """
    async with db.connect() as conn:
        ids = list(article_ids or [])
        from_queue = not ids
        if from_queue:
            cur = await conn.execute("SELECT article_id FROM digest_queue ORDER BY position ASC")
            ids = [r["article_id"] for r in await cur.fetchall()]
        if not ids:
            raise ValueError("nothing to compile: no articles selected and the queue is empty")

        base = title or date.today().isoformat()
        if title is None:
            # A second press on the same day gets "… No. 2" so editions never
            # collide by name. Explicit titles are the user's own business.
            # Matches the bare base and any group/profile-suffixed variant.
            cur = await conn.execute(
                "SELECT title FROM digests WHERE title LIKE ?", (f"{base}%",)
            )
            pattern = re.compile(rf"^{re.escape(base)}(?: No\. (\d+))?(?:$| - | · )")
            highest = 0
            for row in await cur.fetchall():
                m = pattern.match(row["title"])
                if m:
                    highest = max(highest, int(m.group(1) or 1))
            if highest:
                base = f"{base} No. {highest + 1}"
        editions: list[tuple[str, str | None, list[int]]] = []
        if split == "per_group":
            marks = placeholders(len(ids))
            cur = await conn.execute(
                f"SELECT a.id, g.name AS group_name FROM articles a "
                f"JOIN feeds f ON f.id = a.feed_id "
                f"LEFT JOIN groups g ON g.id = f.group_id "
                f"WHERE a.id IN ({marks})",
                ids,
            )
            name_by_id = {r["id"]: r["group_name"] for r in await cur.fetchall()}
            # buckets in first-appearance (queue) order, Ungrouped always last;
            # the suffix is applied even for a single bucket; predictability
            # beats cleverness.
            buckets: dict[str, list[int]] = {}
            ungrouped: list[int] = []
            for article_id in ids:
                name = name_by_id.get(article_id)
                if name is None:
                    ungrouped.append(article_id)
                else:
                    buckets.setdefault(name, []).append(article_id)
            for group_name, bucket in buckets.items():
                editions.append((f"{base} - {group_name}", group_name, bucket))
            if ungrouped:
                editions.append((f"{base} - Ungrouped", "Ungrouped", ungrouped))
        else:
            editions.append((base, None, ids))

        # One variant per profile; the suffix is applied only when several
        # profiles are pressed at once, so single-profile titles stay clean.
        variant_profiles: list[str | None] = list(profiles) if profiles else [None]
        suffix_profiles = len(variant_profiles) > 1

        digest_ids: list[int] = []
        for edition_title, edition_group, member_ids in editions:
            for profile in variant_profiles:
                variant_title = (
                    f"{edition_title} · {profile}" if profile and suffix_profiles else edition_title
                )
                cur = await conn.execute(
                    "INSERT INTO digests (title, status, group_name, profile) "
                    "VALUES (?, 'pending', ?, ?)",
                    (variant_title, edition_group, profile),
                )
                digest_id = cur.lastrowid
                if digest_id is None:
                    raise RuntimeError("digest insert returned no row id")
                for position, article_id in enumerate(member_ids):
                    await conn.execute(
                        "INSERT INTO digest_articles (digest_id, article_id, position) "
                        "VALUES (?, ?, ?)",
                        (digest_id, article_id, position),
                    )
                digest_ids.append(digest_id)

        # compiling an edition always counts as having read its articles
        marks = placeholders(len(ids))
        await conn.execute(
            f"UPDATE articles SET read_at = CURRENT_TIMESTAMP "
            f"WHERE id IN ({marks}) AND read_at IS NULL",
            ids,
        )
        if from_queue:
            await conn.execute("DELETE FROM digest_queue")
        await conn.commit()
    return digest_ids


# Ordered members of an edition, joined with their article/feed/group context -
# shared by the HTML preview and the EPUB build.
_MEMBER_ROWS_SQL = (
    "SELECT a.id AS article_id, a.title, a.url, a.summary, a.full_content, "
    "a.published_at, f.title AS source, g.name AS group_name "
    "FROM digest_articles da "
    "JOIN articles a ON a.id = da.article_id "
    "JOIN feeds f ON f.id = a.feed_id "
    "LEFT JOIN groups g ON g.id = f.group_id "
    "WHERE da.digest_id = ? ORDER BY da.position ASC"
)


def _member_to_article(
    row: Any, content: str | None, combined: bool
) -> tuple[DigestArticle, FetchStatus]:
    """Turn one member row (plus its resolved full content, if any) into a
    DigestArticle, falling back to the sanitized summary when content is missing.
    `combined` editions carry the group name so the TOC can section by group."""
    fetch_status: FetchStatus
    if content:
        body = content
        fetch_status = "full"
    else:
        summary = sanitize(row["summary"] or "").strip()
        body = summary or "<p><em>No content available.</em></p>"
        fetch_status = "summary" if summary else "empty"
    article = DigestArticle(
        title=row["title"],
        source=row["source"],
        url=row["url"],
        html=body,
        published_at=row["published_at"],
        is_summary_fallback=fetch_status != "full",
        group=row["group_name"] if combined else None,
    )
    return article, fetch_status


async def load_digest_preview(db: Database, digest_id: int) -> tuple[str, list[DigestArticle]]:
    """Title + ordered members of an edition built from already-stored content
    (no network, no image rewriting), for the in-app HTML preview. Raises
    LookupError if the edition is missing or has no members."""
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT title, group_name FROM digests WHERE id = ?", (digest_id,)
        )
        d = await cur.fetchone()
        if d is None:
            raise LookupError("digest not found")
        cur = await conn.execute(_MEMBER_ROWS_SQL, (digest_id,))
        rows = await cur.fetchall()
    if not rows:
        raise LookupError("edition is empty")

    # A combined edition (group_name NULL) sections its TOC by group; a
    # per-group edition is the group, so it keeps per-feed sections inside.
    combined = d["group_name"] is None
    articles = [_member_to_article(r, r["full_content"], combined)[0] for r in rows]
    return d["title"], articles


async def _mark_generating_and_load(db: Database, digest_id: int) -> tuple[Any, list[Any]]:
    """Flip the digest to 'generating' and return its row + ordered member rows."""
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE digests SET status = 'generating' WHERE id = ?", (digest_id,)
        )
        await conn.commit()

        cur = await conn.execute(
            "SELECT title, group_name, profile FROM digests WHERE id = ?", (digest_id,)
        )
        d = await cur.fetchone()
        if d is None:
            raise RuntimeError(f"digest {digest_id} vanished before generation")

        cur = await conn.execute(_MEMBER_ROWS_SQL, (digest_id,))
        rows = list(await cur.fetchall())
    return d, rows


async def _fetch_missing_content(
    rows: list[Any], app_settings: AppSettings
) -> dict[str, str | None]:
    """Compile is the second retrieval path: articles enqueued without a
    preview have no stored full_content, so fetch the missing ones here
    with the same impersonation + reader fallback Preview uses, politely,
    one host at a time. (Done with the DB connection closed; reopened later
    to persist.) See docs/.../guide on the two paths."""
    missing_urls = [r["url"] for r in rows if not r["full_content"]]
    return await fetch_many(missing_urls, app_settings) if missing_urls else {}


def _assemble_members(
    rows: list[Any], fetched: dict[str, str | None], combined: bool
) -> tuple[list[DigestArticle], list[tuple[int, FetchStatus, str | None]]]:
    """Build the DigestArticles plus, per member, (article_id, fetch_status,
    freshly_fetched_content_or_None), written back after the EPUB is built."""
    articles: list[DigestArticle] = []
    member_outcomes: list[tuple[int, FetchStatus, str | None]] = []
    for r in rows:
        content = r["full_content"] or fetched.get(r["url"])
        article, fetch_status = _member_to_article(r, content, combined)
        # newly retrieved, so cache it on the article
        fresh = content if content and not r["full_content"] else None
        member_outcomes.append((r["article_id"], fetch_status, fresh))
        articles.append(article)
    return articles, member_outcomes


def _resolve_profile(app_settings: AppSettings, name: str | None) -> RenderProfile | None:
    """Resolve the snapshotted render profile; a renamed/deleted profile
    falls back to the legacy global settings rather than failing."""
    profile = next((p for p in app_settings.profiles if p.name == name), None)
    if name is not None and profile is None:
        logger.warning(
            "render profile %r no longer exists; falling back to legacy settings", name
        )
    return profile


async def _render_bodies(
    articles: list[DigestArticle], profile: RenderProfile | None, epub_dir: Path
) -> dict[str, DigestImage]:
    """Rewrite article HTML through the image pipeline (and table/code
    pre-rendering, when the profile asks for it); returns the images to embed
    in the EPUB. A profile with screen dimensions gets photos recompressed to
    2x its screen width and table/code images fitted to its screen."""
    screen = profile.screen if profile else None
    max_width = SUPERSAMPLE * screen[0] if screen else 1200
    async with make_http_client() as client:
        rewritten, images = await prepare_images(
            [(a.html, a.url) for a in articles],
            client,
            max_width=max_width,
            cache_dir=image_cache_dir(epub_dir),
        )
    for art, new_html in zip(articles, rewritten, strict=True):
        art.html = new_html

    def rasterize_blocks(
        renderer: Callable[..., tuple[str, dict[str, DigestImage]]],
    ) -> None:
        rendered: dict[str, DigestImage] = {}
        for art in articles:
            art.html, new_images = renderer(
                art.html, screen=screen, start_index=len(rendered) + 1
            )
            rendered.update(new_images)
        images.update(rendered)

    if profile and profile.code_mode == "br":
        for art in articles:
            art.html = pre_to_br(art.html)
    elif profile and profile.code_mode == "image":
        rasterize_blocks(pre_to_images)

    # Table pre-rendering runs after the image pipeline so the injected
    # tables/… img references are never mistaken for remote URLs to fetch.
    if profile and profile.table_mode == "image":
        rasterize_blocks(tables_to_images)
    return images


def _build_epub(
    digest_id: int,
    title: str,
    articles: list[DigestArticle],
    images: dict[str, DigestImage],
    epub_dir: Path,
    link_qr: LinkQr,
) -> Path:
    """Render the cover and write the EPUB file; returns its path."""
    sources = list(dict.fromkeys(a.source for a in articles))
    cover_image = render_cover(
        title=title,
        date_str=date.today().isoformat(),
        article_count=len(articles),
        sources=sources,
    )
    output = epub_dir / f"digest-{digest_id}-{_safe_filename(title)}.epub"
    build_digest_epub(
        title=title,
        articles=articles,
        output_path=output,
        images=images,
        cover_image=cover_image,
        identifier=f"urn:rss-books:digest:{digest_id}",
        link_qr=link_qr,
    )
    return output


async def _persist_ready(
    db: Database,
    digest_id: int,
    output: Path,
    member_outcomes: list[tuple[int, FetchStatus, str | None]],
) -> int:
    """Record the built EPUB and per-member fetch outcomes; returns the size."""
    size_bytes = output.stat().st_size
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE digests SET epub_path = ?, status = 'ready', size_bytes = ? WHERE id = ?",
            (str(output), size_bytes, digest_id),
        )
        for article_id, fetch_status, fresh in member_outcomes:
            await conn.execute(
                "UPDATE digest_articles SET fetch_status = ? "
                "WHERE digest_id = ? AND article_id = ?",
                (fetch_status, digest_id, article_id),
            )
            if fresh is not None:
                await conn.execute(
                    "UPDATE articles SET full_content = ?, "
                    "fetched_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (fresh, article_id),
                )
        await conn.commit()
    return size_bytes


async def _mark_failed(db: Database, digest_id: int, exc: Exception) -> None:
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE digests SET status = 'failed', error = ? WHERE id = ?",
            (str(exc), digest_id),
        )
        await conn.commit()


async def generate_digest(db: Database, digest_id: int, epub_dir: Path) -> bool:
    """Build the EPUB for a digest; lands in status 'ready' or 'failed'.
    Returns whether it succeeded (BackgroundTasks callers may discard this;
    the scheduler's press deadline uses it only to log, never to retry)."""
    try:
        d, rows = await _mark_generating_and_load(db, digest_id)

        app_settings = await get_app_settings(db)
        fetched = await _fetch_missing_content(rows, app_settings)

        # A combined edition (group_name NULL) sections its TOC by group; a
        # per-group edition is the group, so it keeps per-feed sections inside.
        combined = d["group_name"] is None
        articles, member_outcomes = _assemble_members(rows, fetched, combined)

        profile = _resolve_profile(app_settings, d["profile"])
        link_qr = profile.link_qr if profile else app_settings.link_qr

        images = await _render_bodies(articles, profile, epub_dir)
        # Cover rendering and EPUB assembly are CPU/disk-bound; off the event
        # loop so a large compile doesn't stall polling and other requests.
        output = await asyncio.to_thread(
            _build_epub, digest_id, d["title"], articles, images, epub_dir, link_qr
        )

        size_bytes = await _persist_ready(db, digest_id, output, member_outcomes)
        logger.info(
            "digest %d ready: %s (%d articles, %d bytes)",
            digest_id,
            output.name,
            len(articles),
            size_bytes,
        )

        if app_settings.email_on_ready and app_settings.send_to:
            try:
                await send_digest_and_record(db, app_settings, digest_id)
            except Exception:
                logger.exception("auto-email for digest %d failed", digest_id)
        return True
    except Exception as exc:
        logger.exception("digest %d build failed", digest_id)
        await _mark_failed(db, digest_id, exc)
        return False
