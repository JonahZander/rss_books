from rss_books.services.content_extractor import extract_html

ARTICLE = (
    b"<html><body><article><h1>Hi</h1><p>Hello world. "
    b"This is a sufficiently long paragraph for extraction to succeed, "
    b"and it contains enough prose to survive boilerplate filters. "
    b'It links to <a href="https://example.com/else">another piece</a> too.</p>'
    b"<table><tr><th>lang</th><th>year</th></tr>"
    b"<tr><td>python</td><td>1991</td></tr></table>"
    b"<pre><code>print('hi')</code></pre>"
    b'<p>And an image: <img src="https://example.com/i.png" alt="pic"></p>'
    b"<ul><li>first item of the list</li><li>second item of the list</li></ul>"
    b"</article></body></html>"
)


def test_extract_html_keeps_structure() -> None:
    html = extract_html(ARTICLE, url="https://example.com/post")
    assert html is not None
    assert "Hello world" in html
    assert "<p>" in html
    # real HTML table markup, not trafilatura's TEI row/cell vocabulary
    assert "<table>" in html
    assert "<tr>" in html
    assert "<th>" in html
    assert "<td>python</td>" in html
    assert "<pre>" in html and "<code>" in html
    assert '<img src="https://example.com/i.png"' in html
    assert "<li>" in html
    assert 'href="https://example.com/else"' in html


def test_extract_html_is_sanitized() -> None:
    dirty = ARTICLE.replace(b"</article>", b"<script>alert(1)</script></article>")
    html = extract_html(dirty, url="https://example.com/post")
    assert html is not None
    assert "<script" not in html


def test_extract_returns_none_on_junk() -> None:
    html = extract_html(b"<html><body></body></html>", url="https://x/")
    assert html is None or html.strip() == ""
