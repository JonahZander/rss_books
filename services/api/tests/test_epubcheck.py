"""epubcheck conformance gate.

Builds a fixture edition covering the structural surfaces most likely to
break EPUB conformance - a table, a code block, an embedded image, and a
unicode-heavy paragraph (accents, CJK, curly quotes, emoji) - plus a cover,
then validates the result against the real epubcheck tool.

Self-skipping: the epubcheck test needs a Java runtime and the epubcheck jar
(EPUBCHECK_JAR env var), neither of which is required for a normal local
test run. CI wires both up via actions/setup-java and a checksum-pinned
download (.github/workflows/ci.yml).
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from rss_books.services.cover import render_cover
from rss_books.services.epub_builder import DigestArticle, build_digest_epub
from rss_books.services.image_pipeline import DigestImage

pytestmark = pytest.mark.epubcheck

EPUBCHECK_JAR = os.environ.get("EPUBCHECK_JAR")

# Accents, an em dash, curly quotes, CJK, and emoji (astral plane) - the
# encoding edge cases most likely to trip up EPUB's UTF-8/XML requirements.
_UNICODE_PARAGRAPH = (
    "<p>Café naïve résumé — “curly quotes” and "
    "an em dash; 中文段落测试; "
    "\U0001f4da\U0001f4e1 emoji too.</p>"
)


def _tiny_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (120, 140, 160)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _build_fixture_edition(tmp_path: Path) -> Path:
    """An edition exercising table/code/image/unicode structure, built with
    default native table/code modes - epubcheck validates structural
    correctness; rasterized table/code variants have their own coverage in
    test_render_profiles.py."""
    articles = [
        DigestArticle(
            title="Structural Surfaces",
            source="Fixture Feed",
            url="https://fixture.example/structural-surfaces",
            html=(
                "<p>Intro paragraph with enough words to be a real paragraph "
                "for reading-time estimation.</p>"
                "<table><thead><tr><th>Col A</th><th>Col B</th></tr></thead>"
                "<tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
                "<pre><code>def f(x):\n    return x + 1\n</code></pre>"
                '<img src="images/img_001.jpg" alt="a photograph"/>'
                f"{_UNICODE_PARAGRAPH}"
            ),
            published_at="2026-07-01T09:00:00+00:00",
        ),
    ]
    images = {
        "https://fixture.example/photo.jpg": DigestImage(
            filename="images/img_001.jpg",
            media_type="image/jpeg",
            data=_tiny_jpeg(),
        )
    }
    cover = render_cover(
        title="Structural Surfaces Fixture",
        date_str="2026-07-01",
        article_count=1,
        sources=["Fixture Feed"],
    )
    return build_digest_epub(
        title="Structural Surfaces Fixture",
        articles=articles,
        output_path=tmp_path / "fixture.epub",
        images=images,
        cover_image=cover,
        identifier="urn:rss-books:test:epubcheck-fixture",
        link_qr="articles",
    )


def test_fixture_edition_is_a_well_formed_zip(tmp_path: Path) -> None:
    # Always-on and Java-free: catches fixture-builder breakage on its own,
    # independent of whether epubcheck is available in this environment.
    epub_path = _build_fixture_edition(tmp_path)
    with zipfile.ZipFile(epub_path) as z:
        assert z.testzip() is None
        names = z.namelist()
        assert names[0] == "mimetype"  # EPUB requires this be the first entry
        assert z.read("mimetype") == b"application/epub+zip"
        assert any(n.endswith("nav.xhtml") for n in names)


@pytest.mark.skipif(
    not EPUBCHECK_JAR or not os.path.isfile(EPUBCHECK_JAR) or not shutil.which("java"),
    reason="epubcheck gate needs EPUBCHECK_JAR (path to epubcheck.jar) and java on PATH",
)
def test_fixture_edition_passes_epubcheck(tmp_path: Path) -> None:
    epub_path = _build_fixture_edition(tmp_path)
    result = subprocess.run(
        ["java", "-jar", EPUBCHECK_JAR, str(epub_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    # epubcheck exits non-zero on errors; warnings are printed but don't fail
    # the gate (--failonwarnings is a deliberate follow-up, not enabled here).
    assert result.returncode == 0, output
