import zipfile
from pathlib import Path

from rss_kindle.services.cover import render_cover
from rss_kindle.services.epub_builder import (
    DigestArticle,
    _reading_minutes,
    build_digest_epub,
    render_preview_html,
)
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
        assert cover is not None and cover[:2] == b"\xff\xd8"  # JPEG
    return build_digest_epub(
        title="2026-06-11",
        articles=articles,
        images=images,
        cover_image=cover,
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
        assert "EPUB/cover.jpg" in names
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
        assert "RSS Books" in colophon

        css = z.read("EPUB/style/digest.css").decode("utf-8")
        assert "max-width: 100%" in css
        assert "page-break-before" in css


def test_epub_without_cover_still_builds(tmp_path: Path) -> None:
    out = _build(tmp_path, with_cover=False)
    with zipfile.ZipFile(out) as z:
        assert "EPUB/cover.jpg" not in z.namelist()
        assert "EPUB/chap_001.xhtml" in z.namelist()


def test_cover_is_low_res_jpeg() -> None:
    # budget e-ink decoders (Xteink X4) silently drop the old 1600x2560 PNG;
    # ship the same shape at decoder-friendly resolution, JPEG like every
    # other image in the book
    import io

    from PIL import Image

    cover = render_cover(
        title="2026-06-11", date_str="2026-06-11", article_count=3, sources=["A", "B"]
    )
    assert cover is not None
    assert cover[:2] == b"\xff\xd8"
    img = Image.open(io.BytesIO(cover))
    assert img.size == (1200, 1920)


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


_QR_ARTICLES = [
    DigestArticle(
        title="With links",
        source="Feed One",
        url="https://one.example/post",
        html='<p>See <a href="https://ref.example/a">this</a> and '
        '<a href="https://ref.example/b">that</a>.</p>',
    )
]


def test_no_qr_by_default(tmp_path: Path) -> None:
    out = build_digest_epub(
        title="t", articles=_QR_ARTICLES, output_path=tmp_path / "off.epub"
    )
    with zipfile.ZipFile(out) as z:
        assert not any(n.startswith("EPUB/qr/") for n in z.namelist())
        chap = z.read("EPUB/chap_001.xhtml").decode("utf-8")
        assert "link-qr" not in chap


def test_qr_articles_codes_only_the_source_link(tmp_path: Path) -> None:
    out = build_digest_epub(
        title="t", articles=_QR_ARTICLES, output_path=tmp_path / "art.epub", link_qr="articles"
    )
    with zipfile.ZipFile(out) as z:
        qr_files = [n for n in z.namelist() if n.startswith("EPUB/qr/")]
        # exactly one QR: the chapter source link, not the two body links
        assert len(qr_files) == 1
        chap = z.read("EPUB/chap_001.xhtml").decode("utf-8")
        assert chap.count("link-qr") == 1
        assert z.read(qr_files[0])[:8] == b"\x89PNG\r\n\x1a\n"


def test_qr_all_codes_every_link(tmp_path: Path) -> None:
    out = build_digest_epub(
        title="t", articles=_QR_ARTICLES, output_path=tmp_path / "all.epub", link_qr="all"
    )
    with zipfile.ZipFile(out) as z:
        qr_files = [n for n in z.namelist() if n.startswith("EPUB/qr/")]
        # source link + the two body links = three distinct codes
        assert len(qr_files) == 3
        chap = z.read("EPUB/chap_001.xhtml").decode("utf-8")
        assert chap.count("link-qr") == 3
        # the body anchors survive alongside their QR
        assert 'href="https://ref.example/a"' in chap


def test_preview_inlines_qr_data_uris(tmp_path: Path) -> None:
    html = render_preview_html(title="t", articles=_QR_ARTICLES, link_qr="all")
    assert html.count('class="link-qr"') == 3
    assert "data:image/png;base64," in html


def test_toc_sections_by_feed_when_no_groups(tmp_path: Path) -> None:
    out = _build(tmp_path)
    with zipfile.ZipFile(out) as z:
        nav = z.read("EPUB/nav.xhtml").decode("utf-8")
        assert nav.index("Feed One") < nav.index("Feed Two")  # the 1.0 shape
        assert "Ungrouped" not in nav
