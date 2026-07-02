"""Pre-render HTML tables to images for readers with no CSS table support.

Budget e-ink readers (the Xteink X4 among them) collapse ``<table>`` markup
into a useless vertical stack of cell texts. For those devices an edition can
ship each sizeable table as a PNG instead — drawn with Pillow in the same
spirit as cover.py (no browser or weasyprint dependency) — optionally rotated
90° so a wide table reads down a narrow portrait screen.

Trivial tables (two columns of short text) reflow fine as text everywhere and
stay native even in image mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

from lxml import html as lxml_html
from PIL import Image, ImageDraw, ImageFont

from rss_kindle.services.image_pipeline import DigestImage

logger = logging.getLogger(__name__)

# Match the image pipeline's downscale ceiling so table images are no heavier
# than photos (pre-rotation width).
MAX_WIDTH = 1200
_FONT_SIZE = 26
_HEADER_FONT_SIZE = 26
_PAD_X = 14
_PAD_Y = 10
_LINE_GAP = 6
_MIN_COL = 90

WHITE = 255
INK = 0
GRID = 120

# A table this small reads fine as reflowed text on any device — converting it
# to a fixed image would only hurt.
_SIMPLE_MAX_COLS = 2
_SIMPLE_MAX_CELL_CHARS = 60


@dataclass
class _Cell:
    text: str
    header: bool


def _extract_rows(table: lxml_html.HtmlElement) -> list[list[_Cell]]:
    rows: list[list[_Cell]] = []
    for tr in table.findall(".//tr"):
        cells = [
            _Cell(" ".join(td.text_content().split()), td.tag == "th")
            for td in tr.iterchildren()
            if td.tag in ("td", "th")
        ]
        if cells:
            rows.append(cells)
    return rows


def is_simple_table(table: lxml_html.HtmlElement) -> bool:
    rows = _extract_rows(table)
    if not rows:
        return True  # nothing to draw; leave it alone
    return max(len(r) for r in rows) <= _SIMPLE_MAX_COLS and all(
        len(c.text) <= _SIMPLE_MAX_CELL_CHARS for r in rows for c in r
    )


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = text.split() or [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current or not lines:
        lines.append(current)
    return lines


def _aspect_ratio(aspect: str) -> float | None:
    """Max height per unit width from a "W:H" option ("auto" = unlimited)."""
    if aspect == "auto":
        return None
    w, _, h = aspect.partition(":")
    try:
        return int(h) / int(w)
    except (ValueError, ZeroDivisionError):
        return None


def _chunk_rows(
    rows: list[list[_Cell]], heights: list[int], max_height: int | None
) -> list[list[int]]:
    """Partition row indices so each chunk (plus the repeated header) stays
    under max_height — the printed-book way of continuing a long table. A row
    that alone exceeds the budget still ships whole, oversized."""
    header_idx = [i for i, r in enumerate(rows) if all(c.header for c in r) and i == 0]
    body_idx = [i for i in range(len(rows)) if i not in header_idx]
    if max_height is None:
        return [header_idx + body_idx]
    header_h = sum(heights[i] for i in header_idx)
    chunks: list[list[int]] = []
    current: list[int] = []
    used = header_h
    for i in body_idx:
        if current and used + heights[i] > max_height:
            chunks.append(header_idx + current)
            current, used = [], header_h
        current.append(i)
        used += heights[i]
    if current:
        chunks.append(header_idx + current)
    return chunks or [header_idx]


def render_table_pngs(
    table: lxml_html.HtmlElement,
    *,
    rotate: bool = False,
    aspect: str = "auto",
) -> list[bytes]:
    """Draw a table as one or more 8-bit greyscale PNG grids. With an aspect
    cap, tables taller than width × H/W are split by rows, each part repeating
    the header. Returns [] when the table has no rows or rendering fails —
    callers keep the native markup then."""
    rows = _extract_rows(table)
    if not rows:
        return []
    try:
        font = ImageFont.load_default(size=_FONT_SIZE)
        ncols = max(len(r) for r in rows)

        probe = ImageDraw.Draw(Image.new("L", (1, 1), WHITE))
        # Column widths proportional to each column's longest cell, clamped so
        # the grid always fits MAX_WIDTH.
        natural = [
            max(
                (int(probe.textlength(r[c].text, font=font)) + 2 * _PAD_X)
                for r in rows
                if len(r) > c
            )
            for c in range(ncols)
        ]
        natural = [max(w, _MIN_COL) for w in natural]
        total = sum(natural)
        if total > MAX_WIDTH:
            scale = (MAX_WIDTH - ncols * _MIN_COL) / max(1, total - ncols * _MIN_COL)
            widths = [_MIN_COL + int((w - _MIN_COL) * scale) for w in natural]
        else:
            widths = natural
        width = sum(widths) + 1

        line_height = _FONT_SIZE + _LINE_GAP
        wrapped: list[list[list[str]]] = []
        heights: list[int] = []
        for r in rows:
            row_lines = [
                _wrap(probe, r[c].text if len(r) > c else "", font, widths[c] - 2 * _PAD_X)
                for c in range(ncols)
            ]
            wrapped.append(row_lines)
            heights.append(max(len(ls) for ls in row_lines) * line_height + 2 * _PAD_Y)

        ratio = _aspect_ratio(aspect)
        max_height = int(width * ratio) if ratio else None
        pngs: list[bytes] = []
        for chunk in _chunk_rows(rows, heights, max_height):
            img = Image.new("L", (width, sum(heights[i] for i in chunk) + 1), WHITE)
            draw = ImageDraw.Draw(img)
            y = 0
            for i in chunk:
                row, row_lines, row_h = rows[i], wrapped[i], heights[i]
                x = 0
                for c in range(ncols):
                    draw.rectangle([x, y, x + widths[c], y + row_h], outline=GRID, width=1)
                    header = len(row) > c and row[c].header
                    ty = y + _PAD_Y
                    for line in row_lines[c]:
                        draw.text((x + _PAD_X, ty), line, font=font, fill=INK)
                        if header:  # faux bold for header cells
                            draw.text((x + _PAD_X + 1, ty), line, font=font, fill=INK)
                        ty += line_height
                    x += widths[c]
                y += row_h

            if rotate:
                img = img.transpose(Image.Transpose.ROTATE_90)
            buf = BytesIO()
            img.save(buf, format="PNG", optimize=True)
            pngs.append(buf.getvalue())
        return pngs
    except Exception:
        logger.exception("table render failed; keeping native markup")
        return []


def tables_to_images(
    html_text: str,
    *,
    rotate: bool,
    aspect: str = "auto",
    start_index: int = 1,
) -> tuple[str, dict[str, DigestImage]]:
    """Replace sizeable ``<table>`` elements in sanitized chapter HTML with
    ``<img>`` references to freshly drawn PNGs (several per table when the
    aspect cap splits it). Returns the rewritten HTML and the images keyed by
    their in-EPUB filename (``tables/tbl_NNNN.png``), ready to merge into the
    digest's image set. Simple tables stay native."""
    if "<table" not in html_text:
        return html_text, {}
    frag = lxml_html.fragment_fromstring(html_text, create_parent="tbl-wrap")
    images: dict[str, DigestImage] = {}
    index = start_index
    for table in frag.findall(".//table"):
        if is_simple_table(table):
            continue
        pngs = render_table_pngs(table, rotate=rotate, aspect=aspect)
        if not pngs:
            continue
        tags = []
        for png in pngs:
            filename = f"tables/tbl_{index:04d}.png"
            index += 1
            images[filename] = DigestImage(
                filename=filename, media_type="image/png", data=png
            )
            tags.append(f'<img class="table-image" src="{filename}" alt="table"/>')
        replacement = lxml_html.fragment_fromstring(
            f"<span>{''.join(tags)}</span>"
        )
        replacement.tail = table.tail
        table.getparent().replace(table, replacement)
    if not images:
        return html_text, {}
    rewritten = (frag.text or "") + "".join(
        lxml_html.tostring(child, encoding="unicode") for child in frag
    )
    return rewritten, images
