from rss_kindle.services.content_extractor import extract_html

ARTICLE = (
    b"<html><body><article><h1>Hi</h1><p>Hello world. "
    b"This is a sufficiently long paragraph for extraction to succeed, "
    b"and it contains enough prose to survive boilerplate filters.</p>"
    b"<table><tr><th>lang</th><th>year</th></tr>"
    b"<tr><td>python</td><td>1991</td></tr></table>"
    b"<pre><code>print('hi')</code></pre>"
    b"</article></body></html>"
)


def test_extract_html_keeps_structure() -> None:
    html = extract_html(ARTICLE, url="https://example.com/post")
    assert html is not None
    assert "Hello world" in html
    assert "<p>" in html
    assert "<table>" in html
    assert "<code>" in html or "<pre>" in html


def test_extract_html_is_sanitized() -> None:
    dirty = ARTICLE.replace(b"</article>", b"<script>alert(1)</script></article>")
    html = extract_html(dirty, url="https://example.com/post")
    assert html is not None
    assert "<script" not in html


def test_extract_returns_none_on_junk() -> None:
    html = extract_html(b"<html><body></body></html>", url="https://x/")
    assert html is None or html.strip() == ""
