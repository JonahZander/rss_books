from __future__ import annotations

import base64
import io

import segno

# Tuned for 6-7" greyscale e-ink: a small fixed module scale keeps the code
# scannable from a phone held to the screen without dominating the page. The
# quiet zone (border) is the QR-spec minimum of 4 modules — too small and
# scanners struggle.
_SCALE = 3
_BORDER = 4


def make_qr_png(data: str) -> bytes:
    """Black-on-white PNG of a QR code encoding `data`."""
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=_SCALE, border=_BORDER)
    return buf.getvalue()


def make_qr_data_uri(data: str) -> str:
    """A `data:` URI for the same PNG — used by the in-app HTML preview, which
    has no EPUB image-item machinery to reference a file."""
    encoded = base64.b64encode(make_qr_png(data)).decode("ascii")
    return f"data:image/png;base64,{encoded}"
