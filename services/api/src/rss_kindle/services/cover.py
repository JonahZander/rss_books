from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

PAPER = (242, 244, 247)
INK = (16, 24, 40)
INK_SOFT = (71, 84, 103)
PINK = (255, 77, 157)
BLUE = (61, 139, 255)

WIDTH, HEIGHT = 1600, 2560
OUT_WIDTH, OUT_HEIGHT = 1200, 1920
MARGIN = 140


AnyFont = ImageFont.FreeTypeFont | ImageFont.ImageFont


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: AnyFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _gradient_bar(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int) -> None:
    """The signature pink→blue gradient, rasterized column by column."""
    for i in range(width):
        t = i / max(width - 1, 1)
        color = tuple(round(p + (b - p) * t) for p, b in zip(PINK, BLUE, strict=True))
        draw.rectangle([x + i, y, x + i + 1, y + height], fill=color)


def render_cover(
    *,
    title: str,
    date_str: str,
    article_count: int,
    sources: list[str],
) -> bytes | None:
    """Raster cover in the masthead aesthetic: cool paper background, ink type,
    pink→blue signature gradient accent. Returns PNG bytes, or None if
    rendering is unavailable."""
    try:
        # Sizes and every dependent spacing constant below were bumped and
        # re-derived together (see docstring at module scope in the plan doc);
        # do not change one without recomputing the worst-case y-positions
        # against HEIGHT and rule_y (test_cover.py has the arithmetic checks).
        font_eyebrow = ImageFont.load_default(size=46)
        font_title = ImageFont.load_default(size=260)
        font_meta = ImageFont.load_default(size=62)
        font_source = ImageFont.load_default(size=58)
    except Exception:
        logger.exception("cover fonts unavailable; edition ships without a cover")
        return None

    try:
        img = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
        draw = ImageDraw.Draw(img)
        inner = WIDTH - 2 * MARGIN

        y = 300
        draw.text((MARGIN, y), "RSS BOOKS", font=font_eyebrow, fill=INK)
        draw.text(
            (MARGIN, y + 70), "A   P R E S S E D   E D I T I O N", font=font_eyebrow, fill=INK_SOFT
        )
        y += 190
        draw.rectangle([MARGIN, y, WIDTH - MARGIN, y + 10], fill=INK)

        # Title: capped at 4 wrapped lines (was 5) to make room for the
        # bumped 260pt font; advance scaled in lock-step (230 -> 300).
        # Worst case: y=600 + 4*300 = 1800, well clear of rule_y (2040).
        y += 110
        for line in _wrap(draw, title, font_title, inner)[:4]:
            draw.text((MARGIN, y), line, font=font_title, fill=INK)
            y += 300

        y += 40
        _gradient_bar(draw, MARGIN, y, 320, 8)
        y += 70
        plural = "article" if article_count == 1 else "articles"
        draw.text((MARGIN, y), f"{date_str}  ·  {article_count} {plural}", font=font_meta, fill=INK)
        # Worst case (4-line title): meta drawn at y=1910, measured glyph
        # bottom ~1972 at 62pt - clears rule_y (2040) with ~70px to spare.

        # Source list anchored to the lower rule. rule_y is intentionally
        # NOT moved (kept at HEIGHT - 520 = 2040): the title block above
        # already uses nearly its full budget, and moving rule_y up would
        # collide with the bumped meta line.
        rule_y = HEIGHT - 520
        draw.rectangle([MARGIN, rule_y, WIDTH - MARGIN, rule_y + 6], fill=INK)
        sy = rule_y + 60
        draw.text((MARGIN, sy), "FROM", font=font_source, fill=INK_SOFT)
        sy += 90
        # Capped at 4 TOTAL lines after "FROM": when there are more than 4
        # sources, the "+N MORE" line occupies the 4th slot (never appended
        # as a 5th) - 3 real sources + 1 MORE line, never more.
        # Worst case last-line (the MORE line) top = sy(2190) + 3*80 = 2430;
        # measured glyph bottom ~2488 at 58pt, ~72px under HEIGHT (2560).
        overflow = len(sources) > 4
        shown = sources[:3] if overflow else sources[:4]
        for source in shown:
            draw.text((MARGIN, sy), source.upper(), font=font_source, fill=INK)
            sy += 80
        if overflow:
            draw.text((MARGIN, sy), f"+ {len(sources) - 3} MORE", font=font_source, fill=INK_SOFT)

        # Drawn at 1600x2560 for crisp type, shipped at 1200x1920 JPEG: budget
        # e-ink decoders (Xteink X4) silently drop the full-size PNG, and JPEG
        # matches every other image in the book. Kindle's cover ceiling is
        # 1600x2560, so the smaller size is safe everywhere.
        img = img.resize((OUT_WIDTH, OUT_HEIGHT), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()
    except Exception:
        logger.exception("cover render failed; edition ships without a cover")
        return None
