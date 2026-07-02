from __future__ import annotations

import base64
import io

import segno
from PIL import Image

# Tuned for 6-7" greyscale e-ink. Render at 6px per module so the PNG is crisp
# and is displayed at its NATIVE pixel size (see img.link-qr in the EPUB CSS) —
# never resized by the reader. A fractional resize (the old 96px box did this)
# smears module edges and breaks scanning, the worse the longer the URL. The
# quiet zone (border) is the QR-spec minimum of 4 modules — too small and
# scanners struggle.
_SCALE = 6
_BORDER = 4


def make_qr_png(data: str) -> bytes:
    """Black-on-white PNG of a QR code encoding `data`.

    segno writes 1-bit bilevel PNGs; some budget e-reader decoders (Xteink X4)
    mangle bit-packed rows into a squashed image with a black band. Every other
    image in an edition ships as 8-bit, so re-encode through Pillow to plain
    8-bit greyscale — same pixels, boring format.
    """
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=_SCALE, border=_BORDER)
    out = io.BytesIO()
    Image.open(buf).convert("L").save(out, format="PNG", optimize=True)
    return out.getvalue()


def make_qr_data_uri(data: str) -> str:
    """A `data:` URI for the same PNG — used by the in-app HTML preview, which
    has no EPUB image-item machinery to reference a file."""
    encoded = base64.b64encode(make_qr_png(data)).decode("ascii")
    return f"data:image/png;base64,{encoded}"
