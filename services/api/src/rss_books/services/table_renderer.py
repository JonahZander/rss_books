"""Pre-render HTML tables and code blocks to images for readers with no CSS
support.

Budget e-ink readers (the Xteink X4 among them) collapse ``<table>`` markup
into a useless vertical stack of cell texts, ignore all font/size CSS and
legacy size tags, and clip oversized unbreakable tokens instead of wrapping
them (verified on-device). For those devices an edition can ship each
sizeable table and each ``<pre>`` block as a PNG instead, drawn with Pillow
in the same spirit as cover.py (no browser or weasyprint dependency).

Layout is fitted to the device screen when the render profile provides its
pixel dimensions: images are drawn at SUPERSAMPLE× the screen size (so the
reader's downscale stays crisp), blocks wider than the portrait budget
rotate 90° to use the long screen edge, and blocks taller than the screen
shape split into screen-shaped chunks. Without screen dimensions the legacy
behaviour applies: portrait, capped at MAX_WIDTH, never split.

Trivial tables (two columns of short text) reflow fine as text everywhere
and stay native even in image mode.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from lxml import html as lxml_html
from PIL import Image, ImageDraw, ImageFont

from rss_books.services.image_pipeline import DigestImage

logger = logging.getLogger(__name__)

# Legacy ceiling (no screen dims): match the image pipeline's downscale cap so
# table/code images are no heavier than photos.
MAX_WIDTH = 1200
# With screen dims, canvases are drawn at 2x the screen pixels: the reader
# scales them to its content area (slightly under the full screen), and a 2:1
# downscale keeps small glyphs crisp where a 1:1 render would alias.
SUPERSAMPLE = 2

_FONT_SIZE = 26
_PAD_X = 14
_PAD_Y = 10
_LINE_GAP = 6
_MIN_COL = 90

_CODE_FONT_SIZE = 32
_CODE_PAD = 16
_CODE_LINE_GAP = 8
# Rotation ergonomics: turning the device (or your head) is only worth it for
# a substantial block where most lines would otherwise wrap. Small or mostly
# short blocks wrap upright instead of becoming a sideways sliver.
_ROTATE_MIN_LINES = 8
_ROTATE_MIN_LONG_FRACTION = 0.5

# Compact monospace for code blocks (Ubuntu Font Licence, see assets/UFL.txt);
# Pillow's default face is proportional, which mangles code alignment.
_CODE_FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "UbuntuMono-Regular.ttf"


def _code_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(_CODE_FONT_PATH), size)
    except OSError:
        logger.warning("bundled code font missing (%s); using default", _CODE_FONT_PATH)
        return ImageFont.load_default(size=size)

WHITE = 255
INK = 0
GRID = 120

# A table this small reads fine as reflowed text on any device; converting it
# to a fixed image would only hurt.
_SIMPLE_MAX_COLS = 2
_SIMPLE_MAX_CELL_CHARS = 60

Screen = tuple[int, int]


@dataclass
class _Fit:
    """Canvas budget for one block: how wide lines may run, when to split,
    and whether the finished image turns 90° for a portrait screen."""

    width: int
    max_height: int | None
    rotate: bool


def _fit_block(
    screen: Screen | None, natural_width: int, *, allow_rotate: bool = True
) -> _Fit:
    """Fit a block of `natural_width` canvas pixels to the device screen.

    Portrait if it fits the portrait budget (SUPERSAMPLE × screen width),
    else rotated (budget = long edge); content wider than even the rotated
    budget is clamped there and must wrap. With `allow_rotate=False` the
    block stays portrait and wraps instead. Chunk height keeps each image
    display-filling: the screen's shape for portrait, its inverse for
    rotated (pre-rotation width becomes on-screen height)."""
    if screen is None:
        return _Fit(width=min(natural_width, MAX_WIDTH), max_height=None, rotate=False)
    screen_w, screen_h = screen
    portrait_budget = SUPERSAMPLE * screen_w
    rotated_budget = SUPERSAMPLE * screen_h
    if natural_width <= portrait_budget or not allow_rotate:
        width = min(natural_width, portrait_budget)
        return _Fit(
            width=width,
            max_height=width * screen_h // screen_w,
            rotate=False,
        )
    width = min(natural_width, rotated_budget)
    return _Fit(width=width, max_height=width * screen_w // screen_h, rotate=True)


def _finish_png(img: Image.Image, rotate: bool) -> bytes:
    if rotate:
        # 90° clockwise: the block's first line lands at the right edge, so
        # tilting the device left starts reading at the beginning
        img = img.transpose(Image.Transpose.ROTATE_270)
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


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


def _break_word(
    draw: ImageDraw.ImageDraw,
    word: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """Split a single overlong token into pieces that each fit max_width, so
    it can never paint across the column boundary."""
    pieces: list[str] = []
    current = ""
    for ch in word:
        if current and draw.textlength(current + ch, font=font) > max_width:
            pieces.append(current)
            current = ch
        else:
            current += ch
    if current:
        pieces.append(current)
    return pieces or [""]


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = [
        piece
        for word in (text.split() or [""])
        for piece in (
            [word]
            if draw.textlength(word, font=font) <= max_width
            else _break_word(draw, word, font, max_width)
        )
    ]
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


def _chunk_rows(
    rows: list[list[_Cell]], heights: list[int], max_height: int | None
) -> list[list[int]]:
    """Partition row indices so each chunk (plus the repeated header) stays
    under max_height, the printed-book way of continuing a long table. A row
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
    screen: Screen | None = None,
) -> list[bytes]:
    """Draw a table as one or more 8-bit greyscale PNG grids, fitted to the
    device screen (auto-rotating wide tables, splitting tall ones into
    screen-shaped chunks that each repeat the header). Returns [] when the
    table has no rows or rendering fails - callers keep the native markup."""
    rows = _extract_rows(table)
    if not rows:
        return []
    try:
        font = ImageFont.load_default(size=_FONT_SIZE)
        ncols = max(len(r) for r in rows)

        probe = ImageDraw.Draw(Image.new("L", (1, 1), WHITE))
        # Column widths proportional to each column's longest cell, clamped so
        # the grid always fits the canvas budget.
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
        fit = _fit_block(screen, total)
        if total > fit.width - 1:  # -1: the grid's closing border pixel
            scale = (fit.width - 1 - ncols * _MIN_COL) / max(1, total - ncols * _MIN_COL)
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

        pngs: list[bytes] = []
        for chunk in _chunk_rows(rows, heights, fit.max_height):
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
            pngs.append(_finish_png(img, fit.rotate))
        return pngs
    except Exception:
        logger.exception("table render failed; keeping native markup")
        return []


def render_code_pngs(code: str, *, screen: Screen | None = None) -> list[bytes]:
    """Draw a code block as one or more 8-bit greyscale PNGs at natural width
    (so short blocks stay large on screen), fitted to the device screen the
    same way tables are: wide blocks rotate, tall blocks split into
    screen-shaped chunks, overlong lines hard-wrap. Returns [] on failure."""
    try:
        font = _code_font(_CODE_FONT_SIZE)
        probe = ImageDraw.Draw(Image.new("L", (1, 1), WHITE))
        raw_widths = [
            (raw, int(probe.textlength(raw, font=font))) for raw in code.split("\n")
        ]
        portrait_text_budget = (
            SUPERSAMPLE * screen[0] - 2 * _CODE_PAD if screen else MAX_WIDTH - 2 * _CODE_PAD
        )
        long_lines = sum(1 for _, w in raw_widths if w > portrait_text_budget)
        allow_rotate = (
            len(raw_widths) >= _ROTATE_MIN_LINES
            and long_lines >= len(raw_widths) * _ROTATE_MIN_LONG_FRACTION
        )
        fit = _fit_block(
            screen, max(w for _, w in raw_widths) + 2 * _CODE_PAD, allow_rotate=allow_rotate
        )
        max_text_width = fit.width - 2 * _CODE_PAD

        lines: list[tuple[str, int]] = []  # (text, pixel width)
        for raw, raw_width in raw_widths:
            if raw_width <= max_text_width:
                lines.append((raw, raw_width))
            else:
                lines.extend(
                    (piece, int(probe.textlength(piece, font=font)))
                    for piece in _break_word(probe, raw, font, max_text_width)
                )

        line_h = _CODE_FONT_SIZE + _CODE_LINE_GAP
        width = max(w for _, w in lines) + 2 * _CODE_PAD

        if fit.max_height is None:
            per_chunk = len(lines)
        else:
            per_chunk = max(1, (fit.max_height - 2 * _CODE_PAD) // line_h)
        pngs: list[bytes] = []
        for start in range(0, len(lines), per_chunk):
            chunk = lines[start : start + per_chunk]
            img = Image.new("L", (width, line_h * len(chunk) + 2 * _CODE_PAD), WHITE)
            draw = ImageDraw.Draw(img)
            for i, (line, _) in enumerate(chunk):
                draw.text((_CODE_PAD, _CODE_PAD + i * line_h), line, font=font, fill=INK)
            pngs.append(_finish_png(img, fit.rotate))
        return pngs
    except Exception:
        logger.exception("code render failed; keeping native markup")
        return []


def serialize_fragment(frag: lxml_html.HtmlElement) -> str:
    """Children of a synthetic wrapper element back to an HTML string."""
    return (frag.text or "") + "".join(
        lxml_html.tostring(child, encoding="unicode") for child in frag
    )


def _blocks_to_images(
    html_text: str,
    *,
    tag: str,
    render: Callable[[lxml_html.HtmlElement], list[bytes]],
    prefix: str,
    css_class: str,
    alt: str,
    start_index: int,
) -> tuple[str, dict[str, DigestImage]]:
    """Replace every rendered `tag` element in sanitized chapter HTML with
    ``<img>`` references to freshly drawn PNGs (several per block when a tall
    one splits). Blocks whose renderer returns [] keep their native markup."""
    if f"<{tag}" not in html_text:
        return html_text, {}
    frag = lxml_html.fragment_fromstring(html_text, create_parent="block-wrap")
    images: dict[str, DigestImage] = {}
    index = start_index
    for element in frag.findall(f".//{tag}"):
        if any(a.tag == "table" for a in element.iterancestors()):
            # a block inside a table cell belongs to the table pass, which
            # flattens it into the cell text — rasterizing it here would
            # delete the text from the eventual table image
            continue
        pngs = render(element)
        if not pngs:
            continue
        tags = []
        for png in pngs:
            filename = f"{prefix}_{index:04d}.png"
            index += 1
            images[filename] = DigestImage(
                filename=filename, media_type="image/png", data=png
            )
            tags.append(f'<img class="{css_class}" src="{filename}" alt="{alt}"/>')
        replacement = lxml_html.fragment_fromstring(f"<span>{''.join(tags)}</span>")
        replacement.tail = element.tail
        element.getparent().replace(element, replacement)
    if not images:
        return html_text, {}
    return serialize_fragment(frag), images


def tables_to_images(
    html_text: str,
    *,
    screen: Screen | None = None,
    start_index: int = 1,
) -> tuple[str, dict[str, DigestImage]]:
    """Sizeable ``<table>`` elements to ``tables/tbl_NNNN.png`` images,
    fitted to the screen. Simple tables stay native."""
    return _blocks_to_images(
        html_text,
        tag="table",
        render=lambda t: [] if is_simple_table(t) else render_table_pngs(t, screen=screen),
        prefix="tables/tbl",
        css_class="table-image",
        alt="table",
        start_index=start_index,
    )


def pre_to_images(
    html_text: str,
    *,
    screen: Screen | None = None,
    start_index: int = 1,
) -> tuple[str, dict[str, DigestImage]]:
    """``<pre>`` blocks to ``code/code_NNNN.png`` images, for reader engines
    that ignore CSS, collapse <pre> whitespace and clip oversized tokens
    (the Xteink X4)."""
    return _blocks_to_images(
        html_text,
        tag="pre",
        render=lambda p: render_code_pngs(p.text_content(), screen=screen),
        prefix="code/code",
        css_class="code-image",
        alt="code block",
        start_index=start_index,
    )


def pre_to_br(html_text: str) -> str:
    """Bake code-block line structure into the markup: every <pre>'s text
    becomes <br/>-separated lines with leading spaces as non-breaking spaces.
    A lighter alternative to pre_to_images for engines that collapse <pre>
    whitespace but do honour <br/> and render text at a sane size."""
    if "<pre" not in html_text:
        return html_text
    frag = lxml_html.fragment_fromstring(html_text, create_parent="pre-wrap")
    for pre in frag.findall(".//pre"):
        lines = pre.text_content().split("\n")

        def hard_indent(line: str) -> str:
            stripped = line.lstrip(" ")
            return "\xa0" * (len(line) - len(stripped)) + stripped

        for child in list(pre):
            pre.remove(child)
        code = lxml_html.Element("code")
        code.text = hard_indent(lines[0])
        for line in lines[1:]:
            br = lxml_html.Element("br")
            br.tail = hard_indent(line)
            code.append(br)
        pre.text = None
        pre.append(code)
    return serialize_fragment(frag)
