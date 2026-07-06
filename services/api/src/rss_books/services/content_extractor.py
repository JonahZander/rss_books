from __future__ import annotations

import trafilatura
from lxml import html as lxml_html

from rss_books.services.sanitizer import sanitize_or_none


def _tei_to_html(markup: str) -> str:
    """Normalize trafilatura's TEI-flavored 'html' output into real HTML.

    trafilatura 2.x serializes its internal vocabulary: <graphic> for images,
    <row>/<cell> for table rows, <list>/<item>, <ref target=...> for links,
    nested <pre><pre> for code blocks. Left as-is, the sanitizer would strip
    them; convert tags in place so tables, images, lists, links and code
    survive into the stored HTML.
    """
    root = lxml_html.fromstring(markup)
    for el in root.iter():
        tag = el.tag
        if not isinstance(tag, str):
            continue
        if tag == "graphic":
            el.tag = "img"
        elif tag == "row":
            el.tag = "tr"
            el.attrib.pop("span", None)
        elif tag == "cell":
            el.tag = "th" if el.get("role") == "head" else "td"
            el.attrib.pop("role", None)
            el.attrib.pop("span", None)
        elif tag == "list":
            el.tag = "ol" if el.get("rend") == "ol" else "ul"
            el.attrib.pop("rend", None)
        elif tag == "item":
            el.tag = "li"
        elif tag == "lb":
            el.tag = "br"
        elif tag == "quote":
            el.tag = "blockquote"
        elif tag == "ref":
            el.tag = "a"
            target = el.attrib.pop("target", None)
            if target:
                el.set("href", target)
        elif tag == "pre":
            parent = el.getparent()
            if parent is not None and parent.tag == "pre":
                el.tag = "code"
        elif tag == "hi":
            rend = el.attrib.pop("rend", "")
            el.tag = "strong" if "#b" in rend else "em"
    return lxml_html.tostring(root, encoding="unicode", method="html")


def extract_html(raw: bytes, url: str) -> str | None:
    """Extract the readable article from a page as sanitized HTML.

    Default (precision-leaning) extraction first: on boilerplate-heavy news
    pages, favor_recall can latch onto a dense "most popular" link rail
    instead of the article body. Recall mode is kept only as the rescue pass
    for sparse pages where the default finds nothing.
    """
    text = raw.decode("utf-8", errors="replace")

    def run(favor_recall: bool) -> str | None:
        return trafilatura.extract(
            text,
            url=url,
            output_format="html",
            include_links=True,
            include_images=True,
            favor_recall=favor_recall,
        )

    extracted = run(favor_recall=False) or run(favor_recall=True)
    if not extracted:
        return None
    return sanitize_or_none(_tei_to_html(extracted))
