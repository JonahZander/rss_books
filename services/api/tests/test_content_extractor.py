from rss_kindle.services.content_extractor import extract_markdown


def test_extract_markdown_from_html():
    html = (
        b"<html><body><article><h1>Hi</h1><p>Hello world. "
        b"This is a sufficiently long paragraph for extraction to succeed, "
        b"and it contains enough prose to survive boilerplate filters.</p>"
        b"</article></body></html>"
    )
    md = extract_markdown(html, url="https://example.com/post")
    assert md is not None
    assert "Hello world" in md


def test_extract_returns_none_on_junk():
    md = extract_markdown(b"<html><body></body></html>", url="https://x/")
    assert md is None or md.strip() == ""
