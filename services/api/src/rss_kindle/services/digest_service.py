from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from rss_kindle.config import make_http_client
from rss_kindle.db import Database, placeholders
from rss_kindle.models import FetchStatus
from rss_kindle.services.article_fetcher import fetch_many
from rss_kindle.services.cover import render_cover
from rss_kindle.services.emailer import send_digest_and_record
from rss_kindle.services.epub_builder import DigestArticle, build_digest_epub
from rss_kindle.services.image_pipeline import DigestImage, prepare_images
from rss_kindle.services.sanitizer import sanitize
from rss_kindle.services.settings_store import get_app_settings
from rss_kindle.services.table_renderer import tables_to_images

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
    with one variant per render profile when `profiles` is given — the same
    articles pressed once per device.

    With no explicit article ids, the server-side queue is snapshotted in
    order and then cleared — once, regardless of how many editions result.
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
            pattern = re.compile(rf"^{re.escape(base)}(?: No\. (\d+))?(?:$| — | · )")
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
            # the suffix is applied even for a single bucket — predictability
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
                editions.append((f"{base} — {group_name}", group_name, bucket))
            if ungrouped:
                editions.append((f"{base} — Ungrouped", "Ungrouped", ungrouped))
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


async def load_digest_preview(db: Database, digest_id: int) -> tuple[str, list[DigestArticle]]:
    """Title + ordered members of an edition built from already-stored content
    (no network, no image rewriting) — for the in-app HTML preview. Raises
    LookupError if the edition is missing or has no members."""
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT title, group_name FROM digests WHERE id = ?", (digest_id,)
        )
        d = await cur.fetchone()
        if d is None:
            raise LookupError("digest not found")
        cur = await conn.execute(
            "SELECT a.title, a.url, a.summary, a.full_content, a.published_at, "
            "f.title AS source, g.name AS group_name "
            "FROM digest_articles da "
            "JOIN articles a ON a.id = da.article_id "
            "JOIN feeds f ON f.id = a.feed_id "
            "LEFT JOIN groups g ON g.id = f.group_id "
            "WHERE da.digest_id = ? ORDER BY da.position ASC",
            (digest_id,),
        )
        rows = await cur.fetchall()
    if not rows:
        raise LookupError("edition is empty")

    combined = d["group_name"] is None
    articles: list[DigestArticle] = []
    for r in rows:
        if r["full_content"]:
            body, fallback = r["full_content"], False
        else:
            summary = sanitize(r["summary"] or "").strip()
            body = summary or "<p><em>No content available.</em></p>"
            fallback = True
        articles.append(
            DigestArticle(
                title=r["title"],
                source=r["source"],
                url=r["url"],
                html=body,
                published_at=r["published_at"],
                is_summary_fallback=fallback,
                group=r["group_name"] if combined else None,
            )
        )
    return d["title"], articles


async def generate_digest(db: Database, digest_id: int, epub_dir: Path) -> None:
    """Build the EPUB for a digest; lands in status 'ready' or 'failed'."""
    try:
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

            cur = await conn.execute(
                "SELECT a.id AS article_id, a.title, a.url, a.summary, a.full_content, "
                "a.published_at, f.title AS source, g.name AS group_name "
                "FROM digest_articles da "
                "JOIN articles a ON a.id = da.article_id "
                "JOIN feeds f ON f.id = a.feed_id "
                "LEFT JOIN groups g ON g.id = f.group_id "
                "WHERE da.digest_id = ? ORDER BY da.position ASC",
                (digest_id,),
            )
            rows = await cur.fetchall()

        # Compile is the second retrieval path: articles enqueued without a
        # preview have no stored full_content, so fetch the missing ones here
        # with the same impersonation + reader fallback Preview uses — politely,
        # one host at a time. (Done with the DB connection closed; reopened below
        # to persist.) See docs/.../guide on the two paths.
        app_settings = await get_app_settings(db)
        missing_urls = [r["url"] for r in rows if not r["full_content"]]
        fetched = await fetch_many(missing_urls, app_settings) if missing_urls else {}

        # A combined edition (group_name NULL) sections its TOC by group; a
        # per-group edition is the group, so it keeps per-feed sections inside.
        combined = d["group_name"] is None
        articles: list[DigestArticle] = []
        # (article_id, fetch_status, freshly_fetched_content_or_None) per member,
        # written back after the EPUB is built.
        member_outcomes: list[tuple[int, FetchStatus, str | None]] = []
        for r in rows:
            fresh: str | None = None
            content = r["full_content"] or fetched.get(r["url"])
            fetch_status: FetchStatus
            if content:
                body, fallback = content, False
                fetch_status = "full"
                if not r["full_content"]:
                    fresh = content  # newly retrieved — cache it on the article
            else:
                summary = sanitize(r["summary"] or "").strip()
                body = summary or "<p><em>No content available.</em></p>"
                fallback = True
                fetch_status = "summary" if summary else "empty"
            member_outcomes.append((r["article_id"], fetch_status, fresh))
            articles.append(
                DigestArticle(
                    title=r["title"],
                    source=r["source"],
                    url=r["url"],
                    html=body,
                    published_at=r["published_at"],
                    is_summary_fallback=fallback,
                    group=r["group_name"] if combined else None,
                )
            )

        # Resolve the snapshotted render profile; a renamed/deleted profile
        # falls back to the legacy global settings rather than failing.
        profile = next(
            (p for p in app_settings.profiles if p.name == d["profile"]),
            None,
        )
        link_qr = profile.link_qr if profile else app_settings.link_qr
        table_mode = profile.table_mode if profile else "native"

        async with make_http_client() as client:
            rewritten, images = await prepare_images([(a.html, a.url) for a in articles], client)
        for art, new_html in zip(articles, rewritten, strict=True):
            art.html = new_html

        # Table pre-rendering runs after the image pipeline so the injected
        # tables/… img references are never mistaken for remote URLs to fetch.
        if table_mode in ("image", "image_rotated"):
            rotate = table_mode == "image_rotated"
            table_images: dict[str, DigestImage] = {}
            for art in articles:
                art.html, new_images = tables_to_images(
                    art.html,
                    rotate=rotate,
                    aspect=profile.table_aspect if profile else "auto",
                    start_index=len(table_images) + 1,
                )
                table_images.update(new_images)
            images.update(table_images)

        sources = list(dict.fromkeys(a.source for a in articles))
        cover_png = render_cover(
            title=d["title"],
            date_str=date.today().isoformat(),
            article_count=len(articles),
            sources=sources,
        )

        output = epub_dir / f"digest-{digest_id}-{_safe_filename(d['title'])}.epub"
        build_digest_epub(
            title=d["title"],
            articles=articles,
            output_path=output,
            images=images,
            cover_png=cover_png,
            identifier=f"urn:rss-books:digest:{digest_id}",
            link_qr=link_qr,
        )

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
    except Exception as exc:
        logger.exception("digest %d build failed", digest_id)
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE digests SET status = 'failed', error = ? WHERE id = ?",
                (str(exc), digest_id),
            )
            await conn.commit()
