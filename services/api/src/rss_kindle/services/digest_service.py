from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import httpx

from rss_kindle.db import Database
from rss_kindle.services.cover import render_cover
from rss_kindle.services.emailer import send_digest_and_record
from rss_kindle.services.epub_builder import DigestArticle, build_digest_epub
from rss_kindle.services.image_pipeline import prepare_images
from rss_kindle.services.sanitizer import sanitize
from rss_kindle.services.settings_store import get_app_settings

logger = logging.getLogger(__name__)


async def create_digest_record(
    db: Database, article_ids: list[int] | None, title: str | None
) -> int:
    """Create the digest row and its members.

    With no explicit article ids, the server-side queue is snapshotted in
    order and then cleared. Raises ValueError when there is nothing to compile.
    """
    async with db.connect() as conn:
        ids = list(article_ids or [])
        from_queue = not ids
        if from_queue:
            cur = await conn.execute("SELECT article_id FROM digest_queue ORDER BY position ASC")
            ids = [r["article_id"] for r in await cur.fetchall()]
        if not ids:
            raise ValueError("nothing to compile: no articles selected and the queue is empty")

        cur = await conn.execute(
            "INSERT INTO digests (title, status) VALUES (?, 'pending')",
            (title or date.today().isoformat(),),
        )
        digest_id = cur.lastrowid
        if digest_id is None:
            raise RuntimeError("digest insert returned no row id")
        for position, article_id in enumerate(ids):
            await conn.execute(
                "INSERT INTO digest_articles (digest_id, article_id, position) VALUES (?, ?, ?)",
                (digest_id, article_id, position),
            )
        # compiling an edition always counts as having read its articles
        marks = ", ".join("?" for _ in ids)
        await conn.execute(
            f"UPDATE articles SET read_at = CURRENT_TIMESTAMP "
            f"WHERE id IN ({marks}) AND read_at IS NULL",
            ids,
        )
        if from_queue:
            await conn.execute("DELETE FROM digest_queue")
        await conn.commit()
    return digest_id


async def generate_digest(db: Database, digest_id: int, epub_dir: Path) -> None:
    """Build the EPUB for a digest; lands in status 'ready' or 'failed'."""
    try:
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE digests SET status = 'generating' WHERE id = ?", (digest_id,)
            )
            await conn.commit()

            cur = await conn.execute("SELECT title FROM digests WHERE id = ?", (digest_id,))
            d = await cur.fetchone()
            if d is None:
                raise RuntimeError(f"digest {digest_id} vanished before generation")

            cur = await conn.execute(
                "SELECT a.title, a.url, a.summary, a.full_content, a.published_at, "
                "f.title AS source "
                "FROM digest_articles da "
                "JOIN articles a ON a.id = da.article_id "
                "JOIN feeds f ON f.id = a.feed_id "
                "WHERE da.digest_id = ? ORDER BY da.position ASC",
                (digest_id,),
            )
            rows = await cur.fetchall()

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
                )
            )

        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "rss-kindle-selector/1.0"},
        ) as client:
            rewritten, images = await prepare_images([(a.html, a.url) for a in articles], client)
        for art, new_html in zip(articles, rewritten, strict=True):
            art.html = new_html

        sources = list(dict.fromkeys(a.source for a in articles))
        cover_png = render_cover(
            title=d["title"],
            date_str=date.today().isoformat(),
            article_count=len(articles),
            sources=sources,
        )

        output = epub_dir / f"digest-{digest_id}-{d['title']}.epub"
        build_digest_epub(
            title=d["title"],
            articles=articles,
            output_path=output,
            images=images,
            cover_png=cover_png,
            identifier=f"urn:rss-kindle-selector:digest:{digest_id}",
        )

        size_bytes = output.stat().st_size
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE digests SET epub_path = ?, status = 'ready', size_bytes = ? WHERE id = ?",
                (str(output), size_bytes, digest_id),
            )
            await conn.commit()
        logger.info(
            "digest %d ready: %s (%d articles, %d bytes)",
            digest_id,
            output.name,
            len(articles),
            size_bytes,
        )

        app_settings = await get_app_settings(db)
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
