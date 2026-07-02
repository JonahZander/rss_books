from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

PAPER = (242, 241, 236)
INK = (14, 15, 17)
INK_SOFT = (85, 85, 79)
AMBER = (201, 122, 30)

WIDTH, HEIGHT = 1600, 2560
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


def render_cover(
    *,
    title: str,
    date_str: str,
    article_count: int,
    sources: list[str],
) -> bytes | None:
    """Raster cover in the masthead aesthetic: paper background, ink type,
    amber accent. Returns PNG bytes, or None if rendering is unavailable."""
    try:
        font_eyebrow = ImageFont.load_default(size=46)
        font_title = ImageFont.load_default(size=200)
        font_meta = ImageFont.load_default(size=56)
        font_source = ImageFont.load_default(size=44)
    except Exception:
        logger.exception("cover fonts unavailable; edition ships without a cover")
        return None

    try:
        img = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
        draw = ImageDraw.Draw(img)
        inner = WIDTH - 2 * MARGIN

        # registration marks
        for x, y in ((MARGIN // 2, MARGIN // 2), (WIDTH - MARGIN // 2, MARGIN // 2)):
            draw.line([(x - 18, y), (x + 18, y)], fill=INK, width=4)
            draw.line([(x, y - 18), (x, y + 18)], fill=INK, width=4)

        y = 300
        draw.text((MARGIN, y), "RSS BOOKS", font=font_eyebrow, fill=INK)
        draw.text(
            (MARGIN, y + 70), "A   P R E S S E D   E D I T I O N", font=font_eyebrow, fill=INK_SOFT
        )
        y += 190
        draw.rectangle([MARGIN, y, WIDTH - MARGIN, y + 10], fill=INK)

        y += 110
        for line in _wrap(draw, title, font_title, inner)[:5]:
            draw.text((MARGIN, y), line, font=font_title, fill=INK)
            y += 230

        y += 40
        draw.rectangle([MARGIN, y, MARGIN + 320, y + 8], fill=AMBER)
        y += 70
        plural = "article" if article_count == 1 else "articles"
        draw.text((MARGIN, y), f"{date_str}  ·  {article_count} {plural}", font=font_meta, fill=INK)

        # source list anchored to the lower rule
        rule_y = HEIGHT - 460
        draw.rectangle([MARGIN, rule_y, WIDTH - MARGIN, rule_y + 6], fill=INK)
        sy = rule_y + 60
        draw.text((MARGIN, sy), "FROM", font=font_source, fill=INK_SOFT)
        sy += 70
        for source in sources[:5]:
            draw.text((MARGIN, sy), source.upper(), font=font_source, fill=INK)
            sy += 62
        if len(sources) > 5:
            draw.text((MARGIN, sy), f"+ {len(sources) - 5} MORE", font=font_source, fill=INK_SOFT)

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        logger.exception("cover render failed; edition ships without a cover")
        return None
