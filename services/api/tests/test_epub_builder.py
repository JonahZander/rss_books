from pathlib import Path
from zipfile import ZipFile

from rss_kindle.services.epub_builder import DigestArticle, build_digest_epub


def test_build_digest_epub_writes_valid_zip(tmp_path: Path):
    articles = [
        DigestArticle(
            title="First",
            source="example.com",
            url="https://example.com/1",
            markdown="# Heading\n\nHello **world**.",
        ),
        DigestArticle(
            title="Second",
            source="example.com",
            url="https://example.com/2",
            markdown="Some other content.",
        ),
    ]
    out = tmp_path / "digest.epub"
    build_digest_epub(title="2026-04-16", articles=articles, output_path=out)
    assert out.exists()
    with ZipFile(out) as z:
        names = z.namelist()
        assert "mimetype" in names
        assert "META-INF/container.xml" in names
        content = "\n".join(
            z.read(n).decode("utf-8", "replace") for n in names if n.endswith(".xhtml")
        )
        assert "First" in content
        assert "Second" in content
        assert "Hello" in content
