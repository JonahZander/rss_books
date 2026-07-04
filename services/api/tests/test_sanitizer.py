from rss_books.services.sanitizer import sanitize


def test_script_and_event_handlers_stripped() -> None:
    out = sanitize('<p onclick="evil()">hi</p><script>alert(1)</script>')
    assert "<script" not in out
    assert "onclick" not in out
    assert "alert(1)" not in out
    assert "hi" in out


def test_document_structure_preserved() -> None:
    html = (
        "<h2>Title</h2>"
        "<table><thead><tr><th>a</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>"
        "<pre><code>x = 1</code></pre>"
        "<blockquote><p>quote</p></blockquote>"
        "<ul><li>item</li></ul>"
        "<figure><img src=\"https://x.com/i.png\" alt=\"pic\"><figcaption>cap</figcaption></figure>"
    )
    out = sanitize(html)
    for tag in (
        "<h2>",
        "<table>",
        "<thead>",
        "<th>",
        "<td>",
        "<pre>",
        "<code>",
        "<blockquote>",
        "<ul>",
        "<li>",
        "<figure>",
        "<figcaption>",
    ):
        assert tag in out, f"{tag} missing from {out!r}"
    assert 'src="https://x.com/i.png"' in out
    assert 'alt="pic"' in out


def test_link_attrs_filtered_and_rel_added() -> None:
    out = sanitize('<a href="https://x.com/a" target="_blank" style="color:red">go</a>')
    assert 'href="https://x.com/a"' in out
    assert "noopener" in out
    assert "style=" not in out
    assert "target=" not in out


def test_javascript_href_dropped() -> None:
    out = sanitize('<a href="javascript:alert(1)">x</a>')
    assert "javascript:" not in out


def test_disallowed_wrappers_unwrapped_but_text_kept() -> None:
    out = sanitize("<div><span>kept text</span></div><iframe src='https://x'></iframe>")
    assert "kept text" in out
    assert "<div" not in out
    assert "<iframe" not in out
