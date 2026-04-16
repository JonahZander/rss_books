from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from ebooklib import epub


@dataclass
class DigestArticle:
    title: str
    source: str
    url: str
    markdown: str


def _inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
    return text


def _markdown_to_xhtml(md: str) -> str:
    escaped = html.escape(md)
    lines = escaped.split("\n")
    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            text = " ".join(buf).strip()
            if text:
                out.append(f"<p>{_inline(text)}</p>")
            buf.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        h = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if h:
            flush()
            level = len(h.group(1))
            out.append(f"<h{level}>{_inline(h.group(2))}</h{level}>")
            continue
        buf.append(stripped)
    flush()
    return "\n".join(out)


def build_digest_epub(
    *,
    title: str,
    articles: list[DigestArticle],
    output_path: Path,
) -> Path:
    book = epub.EpubBook()
    book.set_identifier(f"rss-kindle-digest-{title}")
    book.set_title(f"Digest {title}")
    book.set_language("en")

    chapters: list[epub.EpubHtml] = []
    for i, art in enumerate(articles, start=1):
        body = _markdown_to_xhtml(art.markdown or art.title)
        content = (
            f"<h1>{html.escape(art.title)}</h1>"
            f'<p><em>{html.escape(art.source)} &mdash; '
            f'<a href="{html.escape(art.url)}">{html.escape(art.url)}</a></em></p>'
            f"<hr/>{body}"
        )
        chap = epub.EpubHtml(
            title=art.title,
            file_name=f"chap_{i:03d}.xhtml",
            lang="en",
        )
        chap.set_content(f"<html><body>{content}</body></html>")
        book.add_item(chap)
        chapters.append(chap)

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *chapters]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book, {"epub3_pages": False})
    return output_path
