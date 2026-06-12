import zipfile
from pathlib import Path

from rss_kindle.services.cover import render_cover
from rss_kindle.services.epub_builder import DigestArticle, _reading_minutes, build_digest_epub
from rss_kindle.services.image_pipeline import DigestImage


def _build(tmp_path: Path, with_cover: bool = True) -> Path:
    articles = [
        DigestArticle(
            title="Quantum Doughnuts Explained",
            source="Feed One",
            url="https://one.example/qd",
            html=(
                "<p>Hello <strong>world</strong>, this is prose with enough words.</p>"
                "<table><tbody><tr><td>cell</td></tr></tbody></table>"
                "<pre><code>x = 1</code></pre>"
                '<img src="images/img_001.jpg" alt="pic"/>'
            ),
            published_at="2026-06-10T08:00:00+00:00",
        ),
        DigestArticle(
            title="Second Piece",
            source="Feed One",
            url="https://one.example/sp",
            html="<p>More prose here.</p>",
        ),
        DigestArticle(
            title="Other Voice",
            source="Feed Two",
            url="https://two.example/ov",
            html="<p>Summary only.</p>",
            is_summary_fallback=True,
        ),
    ]
    images = {
        "https://one.example/i.png": DigestImage(
            filename="images/img_001.jpg",
            media_type="image/jpeg",
            data=b"\xff\xd8\xff fake-jpeg-bytes",
        )
    }
    cover = None
    if with_cover:
        cover = render_cover(
            title="2026-06-11",
            date_str="2026-06-11",
            article_count=3,
            sources=["Feed One", "Feed Two"],
        )
        assert cover is not None and cover[:8] == b"\x89PNG\r\n\x1a\n"
    return build_digest_epub(
        title="2026-06-11",
        articles=articles,
        images=images,
        cover_png=cover,
        output_path=tmp_path / "d.epub",
    )


def test_epub_structure(tmp_path: Path) -> None:
    out = _build(tmp_path)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "mimetype" in names
        assert z.read("mimetype") == b"application/epub+zip"
        assert any(n.endswith("nav.xhtml") for n in names)
        assert "EPUB/style/digest.css" in names
        assert "EPUB/images/img_001.jpg" in names
        assert "EPUB/cover.png" in names
        assert "EPUB/title.xhtml" in names
        assert "EPUB/colophon.xhtml" in names

        chap1 = z.read("EPUB/chap_001.xhtml")
        head = chap1[:150].decode("utf-8", errors="replace").lower()
        assert "encoding" in head and "utf-8" in head

        body = chap1.decode("utf-8")
        assert "<table>" in body
        assert "img_001.jpg" in body
        assert "min read" in body
        assert "Feed One" in body
        assert "one.example" in body  # footer link to the original

        title_page = z.read("EPUB/title.xhtml").decode("utf-8")
        assert "Feed One" in title_page and "Feed Two" in title_page
        assert "3 articles" in title_page

        chap3 = z.read("EPUB/chap_003.xhtml").decode("utf-8")
        assert "feed summary" in chap3.lower()

        colophon = z.read("EPUB/colophon.xhtml").decode("utf-8")
        assert "rss-kindle-selector" in colophon

        css = z.read("EPUB/style/digest.css").decode("utf-8")
        assert "max-width: 100%" in css
        assert "page-break-before" in css


def test_epub_without_cover_still_builds(tmp_path: Path) -> None:
    out = _build(tmp_path, with_cover=False)
    with zipfile.ZipFile(out) as z:
        assert "EPUB/cover.png" not in z.namelist()
        assert "EPUB/chap_001.xhtml" in z.namelist()


def test_reading_minutes() -> None:
    assert _reading_minutes("<p>" + "word " * 460 + "</p>") == 2
    assert _reading_minutes("<p>short</p>") == 1


def test_toc_sections_by_group_when_articles_carry_groups(tmp_path: Path) -> None:
    articles = [
        DigestArticle(title="One", source="Feed W", url="https://w.example/1", html="<p>w</p>",
                      group="AI"),
        DigestArticle(title="Two", source="Feed X", url="https://x.example/2", html="<p>x</p>",
                      group="AI"),
        DigestArticle(title="Loose", source="Feed Y", url="https://y.example/3", html="<p>y</p>"),
        DigestArticle(title="Four", source="Feed Z", url="https://z.example/4", html="<p>z</p>",
                      group="Gaming"),
    ]
    out = build_digest_epub(title="t", articles=articles, output_path=tmp_path / "g.epub")
    with zipfile.ZipFile(out) as z:
        nav = z.read("EPUB/nav.xhtml").decode("utf-8")
        # groups in first-appearance order; the Ungrouped section always last,
        # even though the loose article sits third in queue order
        assert nav.index("AI") < nav.index("Gaming") < nav.index("Ungrouped")
        assert "Feed W" not in nav  # feeds are no longer section heads…
        chap1 = z.read("EPUB/chap_001.xhtml").decode("utf-8")
        assert "Feed W" in chap1  # …but stay in the byline


def test_toc_sections_by_feed_when_no_groups(tmp_path: Path) -> None:
    out = _build(tmp_path)
    with zipfile.ZipFile(out) as z:
        nav = z.read("EPUB/nav.xhtml").decode("utf-8")
        assert nav.index("Feed One") < nav.index("Feed Two")  # the 1.0 shape
        assert "Ungrouped" not in nav
