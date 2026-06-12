from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from ebooklib import epub

from rss_kindle.services.image_pipeline import DigestImage


@dataclass
class DigestArticle:
    title: str
    source: str
    url: str
    html: str
    published_at: str | None = None
    author: str | None = None
    is_summary_fallback: bool = False


# Tuned for 6-7" greyscale e-ink: generic serif stack (no embedded fonts —
# the reader's typeface wins and files stay small), wrapped monospace, and
# hard page breaks between articles.
STYLESHEET = """\
body { font-family: Georgia, "Times New Roman", serif; line-height: 1.55; margin: 0 2%; color: #000; }
h1, h2, h3, h4, h5, h6 { line-height: 1.25; page-break-after: avoid; }
.chapter { page-break-before: always; }
h1.article-title { font-size: 1.45em; margin: 0.4em 0 0.25em; }
.byline { font-size: 0.78em; letter-spacing: 0.04em; text-transform: uppercase; color: #333; margin: 0 0 0.8em; }
.fallback-note { font-size: 0.85em; color: #333; }
hr.rule { border: 0; border-top: 1px solid #000; margin: 1em 0; }
p { margin: 0.5em 0; }
blockquote { margin: 1em 1.2em; padding-left: 0.7em; border-left: 2px solid #000; font-style: italic; }
pre { font-family: "Courier New", monospace; font-size: 0.75em; white-space: pre-wrap; word-wrap: break-word; border: 1px solid #888; padding: 0.6em; margin: 0.8em 0; }
code { font-family: "Courier New", monospace; font-size: 0.85em; }
pre code { font-size: 1em; }
img { max-width: 100%; }
figure { margin: 1em 0; }
figcaption { font-size: 0.8em; color: #333; }
table { border-collapse: collapse; font-size: 0.85em; margin: 0.8em 0; }
th, td { border: 1px solid #666; padding: 0.3em 0.5em; text-align: left; }
ul, ol { margin: 0.6em 0 0.6em 1.4em; padding: 0; }
a { color: inherit; }
.article-footer { font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.04em; color: #333; }
.titlepage { text-align: center; margin-top: 18%; }
.titlepage h1 { font-size: 2.4em; margin: 0.3em 0; }
.eyebrow { font-size: 0.7em; letter-spacing: 0.18em; text-transform: uppercase; }
.edition-meta { font-size: 0.9em; }
.sources { list-style: none; margin: 1.2em 0; padding: 0; font-size: 0.9em; }
.sources li { margin: 0.2em 0; }
.colophon { margin-top: 25%; font-size: 0.85em; color: #222; }
.colophon ul { list-style: none; padding: 0; }
"""


def _reading_minutes(html_text: str) -> int:
    words = len(re.sub(r"<[^>]+>", " ", html_text).split())
    return max(1, round(words / 230))


def _chapter_body(article: DigestArticle, index: int, total: int) -> str:
    esc = html_lib.escape
    host = urlparse(article.url).hostname or article.url
    byline_bits = [esc(article.source)]
    if article.author:
        byline_bits.append(esc(article.author))
    if article.published_at:
        byline_bits.append(esc(str(article.published_at)[:10]))
    byline_bits.append(f"{_reading_minutes(article.html)} min read")

    parts = [
        '<div class="chapter">',
        f'<h1 class="article-title">{esc(article.title)}</h1>',
        f'<p class="byline">{" · ".join(byline_bits)}</p>',
        '<hr class="rule"/>',
    ]
    if article.is_summary_fallback:
        parts.append(
            '<p class="fallback-note"><em>Full text could not be fetched &#8212; '
            f'the feed summary follows.</em> <a href="{esc(article.url)}">Read online.</a></p>'
        )
    parts.append(article.html)
    parts.append('<hr class="rule"/>')
    parts.append(
        f'<p class="article-footer">No. {index:02d}/{total:02d} &#183; '
        f'<a href="{esc(article.url)}">Read the original at {esc(host)}</a></p>'
    )
    parts.append("</div>")
    return "\n".join(parts)


def build_digest_epub(
    *,
    title: str,
    articles: list[DigestArticle],
    output_path: Path,
    images: dict[str, DigestImage] | None = None,
    cover_png: bytes | None = None,
    identifier: str | None = None,
) -> Path:
    esc = html_lib.escape
    book = epub.EpubBook()
    book.set_identifier(identifier or f"urn:rss-kindle-selector:digest:{title}")
    book.set_title(f"{title} — Pressed Edition")
    book.set_language("en")

    css = epub.EpubItem(
        uid="style_digest",
        file_name="style/digest.css",
        media_type="text/css",
        content=STYLESHEET.encode("utf-8"),
    )
    book.add_item(css)

    if cover_png:
        book.set_cover("cover.png", cover_png)

    sources = list(dict.fromkeys(a.source for a in articles))
    total = len(articles)

    source_items = "".join(f"<li>{esc(s)}</li>" for s in sources)
    article_word = "article" if total == 1 else "articles"
    source_word = "source" if len(sources) == 1 else "sources"
    title_page = epub.EpubHtml(title="Edition", file_name="title.xhtml", lang="en")
    title_page.set_content(
        '<section class="titlepage">'
        '<p class="eyebrow">RSS / KINDLE SELECTOR &#8212; PRESSED EDITION</p>'
        f"<h1>{esc(title)}</h1>"
        f'<p class="edition-meta">{total} {article_word} &#183; '
        f"{len(sources)} {source_word}</p>"
        '<hr class="rule"/>'
        f'<ul class="sources">{source_items}</ul>'
        "</section>"
    )
    title_page.add_item(css)
    book.add_item(title_page)

    chapters: list[tuple[str, epub.EpubHtml]] = []
    for i, art in enumerate(articles, start=1):
        chap = epub.EpubHtml(title=art.title, file_name=f"chap_{i:03d}.xhtml", lang="en")
        chap.set_content(_chapter_body(art, i, total))
        chap.add_item(css)
        book.add_item(chap)
        chapters.append((art.source, chap))

    for n, image in enumerate((images or {}).values(), start=1):
        book.add_item(
            epub.EpubItem(
                uid=f"img_{n:03d}",
                file_name=image.filename,
                media_type=image.media_type,
                content=image.data,
            )
        )

    feed_items = "".join(f"<li>{esc(s)}</li>" for s in sources)
    colophon = epub.EpubHtml(title="Colophon", file_name="colophon.xhtml", lang="en")
    colophon.set_content(
        '<section class="colophon">'
        '<p class="eyebrow">COLOPHON</p>'
        "<p>This edition was pressed by "
        '<a href="https://github.com/JonahZander/rss_kindle_selector">rss-kindle-selector</a>, '
        "the self-hosted news desk for your e-reader. Every article was picked by hand.</p>"
        f"<ul>{feed_items}</ul>"
        "</section>"
    )
    colophon.add_item(css)
    book.add_item(colophon)

    # Sectioned TOC grouped by feed, sections in first-appearance (queue) order.
    book.toc = [
        (epub.Section(source), [c for s, c in chapters if s == source]) for source in sources
    ]
    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav()
    nav.add_item(css)
    book.add_item(nav)

    spine: list[object] = []
    if cover_png:
        spine.append("cover")
    spine.extend([title_page, "nav", *(c for _, c in chapters), colophon])
    book.spine = spine

    output_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book, {"epub3_pages": False})
    return output_path
