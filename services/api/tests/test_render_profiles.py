"""Device rendering profiles: QR PNG format, table pre-rendering, per-profile
compiles, and the per-profile OPDS folders."""

import io
import struct
import time
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient
from lxml import html as lxml_html
from PIL import Image

from conftest import feed_http_client
from rss_kindle.api.main import create_app
from rss_kindle.services.qr import make_qr_png
from rss_kindle.services.table_renderer import render_table_pngs, tables_to_images

FIXTURE = Path(__file__).parent / "fixtures" / "sample.atom"
NS = {"atom": "http://www.w3.org/2005/Atom"}

_COMPLEX_TABLE = (
    "<table><tr><th>Feature</th><th>Details</th><th>Notes</th></tr>"
    "<tr><td>Display</td><td>4.3-inch e-ink, 220 PPI, no front light</td><td>ok</td></tr>"
    "<tr><td>Storage</td><td>16GB microSD card included, expandable to 256GB</td>"
    "<td>fine</td></tr></table>"
)


def _ihdr(png: bytes) -> tuple[int, int, int, int]:
    w, h, bitdepth, colortype = struct.unpack(">IIBB", png[16:26])
    return w, h, bitdepth, colortype


# --- QR format ---------------------------------------------------------------


def test_qr_png_is_8bit() -> None:
    # segno's native output is a 1-bit PNG, which budget reader decoders
    # (Xteink X4) render squashed with a black band; we must ship plain 8-bit.
    _, _, bitdepth, _ = _ihdr(make_qr_png("https://example.com/some/article"))
    assert bitdepth == 8


# --- Table renderer ----------------------------------------------------------


_SCREEN = (480, 800)  # Xteink X4

_TALL_TABLE = (
    "<table><tr><th>A</th><th>B</th><th>C</th></tr>"
    + "".join(
        f"<tr><td>row {i}</td><td>some considerably longer cell text {i}</td>"
        f"<td>more {i}</td></tr>"
        for i in range(40)
    )
    + "</table>"
)


def test_complex_table_becomes_8bit_png() -> None:
    rewritten, images = tables_to_images(f"<p>intro</p>{_COMPLEX_TABLE}")
    assert "<table" not in rewritten
    assert 'class="table-image"' in rewritten
    assert list(images) == ["tables/tbl_0001.png"]
    img = Image.open(io.BytesIO(images["tables/tbl_0001.png"].data))
    assert img.mode == "L"
    _, _, bitdepth, _ = _ihdr(images["tables/tbl_0001.png"].data)
    assert bitdepth == 8


def test_wide_table_auto_rotates_for_screen() -> None:
    # a table wider than the portrait budget (2x screen width) turns 90° to
    # use the long screen edge instead of shrinking the type
    wide = lxml_html.fragment_fromstring(
        "<table><tr>"
        + "".join(f"<th>column heading {i}</th>" for i in range(8))
        + "</tr><tr>"
        + "".join(f"<td>some cell content number {i}</td>" for i in range(8))
        + "</tr></table>"
    )
    (png,) = render_table_pngs(wide, screen=_SCREEN)
    img = Image.open(io.BytesIO(png))
    # rotated: line direction runs down the tall axis
    assert img.height > img.width
    assert img.height <= 2 * _SCREEN[1]


def test_narrow_table_stays_portrait() -> None:
    table = lxml_html.fragment_fromstring(_COMPLEX_TABLE)
    parts = render_table_pngs(table, screen=_SCREEN)
    for part in parts:
        img = Image.open(io.BytesIO(part))
        assert img.width <= 2 * _SCREEN[0]


def test_tall_table_splits_into_screen_shaped_chunks() -> None:
    table = lxml_html.fragment_fromstring(_TALL_TABLE)
    parts = render_table_pngs(table, screen=_SCREEN)
    assert len(parts) >= 2
    for part in parts:
        img = Image.open(io.BytesIO(part))
        # each chunk is no taller than the screen shape allows for its width
        assert img.height <= img.width * _SCREEN[1] / _SCREEN[0] + 2
    # every chunk repeats the header: total height across chunks exceeds the
    # unsplit render (no screen = no cap) by at least one header row
    (whole,) = render_table_pngs(table)
    whole_h = Image.open(io.BytesIO(whole)).height
    assert sum(Image.open(io.BytesIO(p)).height for p in parts) > whole_h


def test_split_emits_multiple_images_in_html() -> None:
    rewritten, images = tables_to_images(_TALL_TABLE, screen=_SCREEN)
    assert len(images) >= 2
    assert rewritten.count("table-image") == len(images)


def test_no_screen_renders_single_unrotated_image() -> None:
    table = lxml_html.fragment_fromstring(_TALL_TABLE)
    parts = render_table_pngs(table)
    assert len(parts) == 1
    img = Image.open(io.BytesIO(parts[0]))
    assert img.width <= 1200


def test_wrap_hard_breaks_oversized_words() -> None:
    # long unbreakable tokens (model names, URLs) used to overflow their
    # column and paint over the neighbour
    from PIL import Image as PILImage
    from PIL import ImageDraw, ImageFont

    from rss_kindle.services.table_renderer import _wrap

    draw = ImageDraw.Draw(PILImage.new("L", (1, 1)))
    font = ImageFont.load_default(size=26)
    max_w = 90
    lines = _wrap(draw, "Gemini-3.1-coarse-grained minimalist", font, max_w)
    assert lines
    assert all(draw.textlength(line, font=font) <= max_w for line in lines)
    # everything survives the break, just split up
    assert "".join(lines).replace(" ", "") == "Gemini-3.1-coarse-grainedminimalist"


def test_simple_table_stays_native() -> None:
    html = "<table><tr><th>K</th><th>V</th></tr><tr><td>a</td><td>b</td></tr></table>"
    rewritten, images = tables_to_images(html)
    assert rewritten == html
    assert images == {}


# --- Code blocks as <br/> lines ----------------------------------------------


def test_pre_to_br_preserves_line_structure() -> None:
    from rss_kindle.services.table_renderer import pre_to_br

    html = (
        "<p>before</p>"
        "<pre><code>flowchart TD\n    a --&gt; b\nend</code></pre>"
        "<p>after</p>"
    )
    out = pre_to_br(html)
    assert "before" in out and "after" in out
    assert out.count("<br") == 2
    # indentation survives as non-breaking spaces
    assert "    a" in out or "&#160;&#160;&#160;&#160;a" in out
    assert "flowchart TD" in out


def test_pre_to_br_leaves_html_without_pre_untouched() -> None:
    from rss_kindle.services.table_renderer import pre_to_br

    html = "<p>plain &amp; simple</p>"
    assert pre_to_br(html) == html


# --- Code blocks as images ----------------------------------------------------


def test_pre_blocks_become_images() -> None:
    from rss_kindle.services.table_renderer import pre_to_images

    html = "<p>before</p><pre><code>flowchart TD\n    a --&gt; b</code></pre><p>after</p>"
    rewritten, images = pre_to_images(html)
    assert "<pre" not in rewritten
    assert 'class="code-image"' in rewritten
    assert "before" in rewritten and "after" in rewritten
    assert list(images) == ["code/code_0001.png"]
    img = Image.open(io.BytesIO(images["code/code_0001.png"].data))
    assert img.mode == "L"
    # natural width: a short block must NOT be padded out to the full
    # pipeline width, or the device scales the text down to nothing
    assert img.width < 700


def test_pre_image_wraps_long_lines_to_max_width() -> None:
    from rss_kindle.services.table_renderer import MAX_WIDTH, pre_to_images

    html = f"<pre><code>{'x' * 400}</code></pre>"
    _, images = pre_to_images(html)
    for img in images.values():
        assert Image.open(io.BytesIO(img.data)).width <= MAX_WIDTH


def test_pre_to_images_without_pre_untouched() -> None:
    from rss_kindle.services.table_renderer import pre_to_images

    html = "<p>plain &amp; simple</p>"
    rewritten, images = pre_to_images(html)
    assert rewritten == html
    assert images == {}


def test_pre_inside_table_stays_for_table_renderer() -> None:
    from rss_kindle.services.table_renderer import pre_to_images, tables_to_images

    html = (
        "<table><tr><th>Flag</th><th>Meaning</th></tr>"
        "<tr><td>Resetting <pre>search_attempts</pre> and <pre>llm_calls</pre> flags</td>"
        "<td>bookkeeping that spans enough characters to fail the simple-table"
        " threshold so the table is rasterized rather than left native</td></tr></table>"
    )
    rewritten, images = pre_to_images(html, screen=_SCREEN)
    assert images == {}  # in-table code stays put for the table pass
    assert rewritten == html
    _, table_images = tables_to_images(rewritten, screen=_SCREEN)
    assert table_images  # the cell text (incl. code) ends up in the table PNG


def test_wide_code_block_auto_rotates_for_screen() -> None:
    from rss_kindle.services.table_renderer import pre_to_images

    # substantial block, most lines wider than the portrait budget -> rotate
    long_line = "planner --> " + " --> ".join(f"node_{i}[label {i}]" for i in range(12))
    code = "\n".join(f"{long_line} %% step {i}" for i in range(10))
    html = f"<pre><code>{code}</code></pre>"
    _, images = pre_to_images(html, screen=_SCREEN)
    im = Image.open(io.BytesIO(next(iter(images.values())).data))
    assert im.height > im.width  # rotated
    assert im.height <= 2 * _SCREEN[1]


def test_small_wide_code_block_wraps_portrait() -> None:
    # two long lines don't justify turning the device sideways: wrap upright
    from rss_kindle.services.table_renderer import pre_to_images

    long_line = "SELECT feeds.title, COUNT(articles.id) AS n FROM feeds JOIN articles" * 2
    html = f"<pre><code>{long_line}\nORDER BY n DESC;</code></pre>"
    _, images = pre_to_images(html, screen=_SCREEN)
    (img,) = images.values()
    im = Image.open(io.BytesIO(img.data))
    assert im.width <= 2 * _SCREEN[0]
    # a few wrapped lines upright, not a sideways sliver
    assert im.width > im.height


def test_short_code_block_stays_portrait_on_screen() -> None:
    from rss_kindle.services.table_renderer import pre_to_images

    html = "<pre><code>flowchart TD\n    a --&gt; b</code></pre>"
    _, images = pre_to_images(html, screen=_SCREEN)
    (img,) = images.values()
    im = Image.open(io.BytesIO(img.data))
    assert im.width <= 2 * _SCREEN[0]
    assert im.width > im.height  # two short lines: wider than tall, unrotated


def test_tall_code_block_splits_into_screen_shaped_chunks() -> None:
    from rss_kindle.services.table_renderer import pre_to_images

    code = "\n".join(f"step_{i} --&gt; step_{i + 1}" for i in range(120))
    html = f"<pre><code>{code}</code></pre>"
    rewritten, images = pre_to_images(html, screen=_SCREEN)
    assert len(images) >= 2
    assert rewritten.count("code-image") == len(images)
    for img in images.values():
        im = Image.open(io.BytesIO(img.data))
        assert im.height <= im.width * _SCREEN[1] / _SCREEN[0] + 2


# --- Profile model migration ---------------------------------------------------


def test_legacy_image_rotated_coerces_to_image() -> None:
    # stored profiles predate auto-rotation; "image_rotated" must keep loading
    from rss_kindle.models import RenderProfile

    p = RenderProfile(name="old", table_mode="image_rotated")  # type: ignore[arg-type]
    assert p.table_mode == "image"


def test_legacy_table_aspect_field_ignored() -> None:
    from rss_kindle.models import RenderProfile

    p = RenderProfile.model_validate(
        {"name": "old", "table_mode": "image", "table_aspect": "3:5"}
    )
    assert p.table_mode == "image"
    assert not hasattr(p, "table_aspect")


def test_code_font_is_compact_monospace() -> None:
    # code must render in a monospace face (bundled Ubuntu Mono), not the
    # proportional Pillow default
    from PIL import Image as PILImage
    from PIL import ImageDraw

    from rss_kindle.services.table_renderer import _code_font

    font = _code_font(32)
    probe = ImageDraw.Draw(PILImage.new("L", (1, 1)))
    assert probe.textlength("iiiiiiiiii", font=font) == probe.textlength(
        "MMMMMMMMMM", font=font
    )


def test_rotated_blocks_read_clockwise() -> None:
    # the first line must end up at the RIGHT edge (90° clockwise), so the
    # table/code begins where the tilted page begins
    from rss_kindle.services.table_renderer import pre_to_images

    lines = ["M" * 90] + ["M" * 70] * 8 + [""]  # dense start, empty end
    html = "<pre><code>" + "\n".join(lines) + "</code></pre>"
    _, images = pre_to_images(html, screen=_SCREEN)
    im = Image.open(io.BytesIO(next(iter(images.values())).data))
    assert im.height > im.width  # sanity: it rotated
    band = 40
    left = im.crop((0, 0, band, im.height))
    right = im.crop((im.width - band, 0, im.width, im.height))

    def mean(region: Image.Image) -> float:
        from PIL import ImageStat

        return ImageStat.Stat(region).mean[0]

    # ink is dark (0): the dense first line must sit right, the blank last
    # line left
    assert mean(right) < mean(left)


# --- Per-profile compiles ----------------------------------------------------


def _seed(client: TestClient) -> list[int]:
    r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
    feed_id = r.json()["id"]
    with patch("rss_kindle.api.feeds.make_http_client", new=feed_http_client(FIXTURE.read_bytes())):
        client.post(f"/api/feeds/{feed_id}/refresh")
    return [a["id"] for a in client.get("/api/articles").json()]


def _wait_settled(client: TestClient, digest_id: int) -> dict:
    digest = {}
    for _ in range(50):
        digest = client.get(f"/api/digests/{digest_id}").json()
        if digest["status"] in {"ready", "failed"}:
            return digest
        time.sleep(0.1)
    return digest


def test_default_profiles_present(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        s = client.get("/api/settings").json()
        assert [p["name"] for p in s["profiles"]] == ["Kindle", "Xteink X4"]
        assert s["profiles"][1]["table_mode"] == "image"
        # the Xteink engine ignores CSS and legacy size tags and clips
        # oversized tokens, so code ships as images there; Kindle keeps native
        assert s["profiles"][1]["code_mode"] == "image"
        assert s["profiles"][1]["screen_width"] == 480
        assert s["profiles"][1]["screen_height"] == 800
        assert s["profiles"][0]["code_mode"] == "native"
        assert s["profiles"][0]["screen_width"] is None
        # round-trip survives an edit
        s["profiles"][0]["link_qr"] = "all"
        assert client.put("/api/settings", json=s).status_code == 200
        assert client.get("/api/settings").json()["profiles"][0]["link_qr"] == "all"


def test_compile_with_profiles_creates_one_edition_each(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        r = client.post(
            "/api/digests",
            json={"article_ids": ids, "title": "ed", "profiles": ["Kindle", "Xteink X4"]},
        )
        assert r.status_code == 201
        created = r.json()
        assert [d["profile"] for d in created] == ["Kindle", "Xteink X4"]
        assert [d["title"] for d in created] == ["ed · Kindle", "ed · Xteink X4"]
        for d in created:
            assert _wait_settled(client, d["id"])["status"] == "ready"


def test_single_profile_keeps_title_unsuffixed(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        r = client.post("/api/digests", json={"article_ids": ids, "title": "ed",
                                              "profiles": ["Kindle"]})
        created = r.json()
        assert len(created) == 1
        assert created[0]["title"] == "ed"
        assert created[0]["profile"] == "Kindle"


def test_unknown_profile_rejected(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.post("/api/digests", json={"article_ids": [1], "profiles": ["Nope"]})
        assert r.status_code == 400
        assert "Nope" in r.json()["detail"]


def test_profile_table_mode_embeds_table_images(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        # give the article a complex table so the Xteink profile converts it
        import sqlite3

        with sqlite3.connect(tmp_path / "t.db") as conn:
            conn.execute(
                "UPDATE articles SET full_content = ? WHERE id = ?",
                (f"<p>body</p>{_COMPLEX_TABLE}", ids[0]),
            )
            conn.commit()

        r = client.post(
            "/api/digests", json={"article_ids": [ids[0]], "profiles": ["Xteink X4"]}
        )
        digest_id = r.json()[0]["id"]
        assert _wait_settled(client, digest_id)["status"] == "ready"
        epub_bytes = client.get(f"/api/digests/{digest_id}/download").content
        with zipfile.ZipFile(io.BytesIO(epub_bytes)) as z:
            table_files = [n for n in z.namelist() if n.startswith("EPUB/tables/")]
            assert len(table_files) == 1
            chap = z.read("EPUB/chap_001.xhtml").decode()
            assert "table-image" in chap
            assert "<table" not in chap


def test_xteink_profile_converts_pre_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        import sqlite3

        with sqlite3.connect(tmp_path / "t.db") as conn:
            conn.execute(
                "UPDATE articles SET full_content = ? WHERE id = ?",
                ("<p>body</p><pre><code>flowchart TD\n    a --&gt; b</code></pre>", ids[0]),
            )
            conn.commit()

        created = client.post(
            "/api/digests",
            json={"article_ids": [ids[0]], "profiles": ["Kindle", "Xteink X4"]},
        ).json()
        by_profile = {d["profile"]: d for d in created}
        for d in created:
            assert _wait_settled(client, d["id"])["status"] == "ready"

        def chapter(digest_id: int) -> str:
            epub = client.get(f"/api/digests/{digest_id}/download").content
            with zipfile.ZipFile(io.BytesIO(epub)) as z:
                return z.read("EPUB/chap_001.xhtml").decode()

        # Xteink: the code block ships as a PNG; Kindle: native <pre> intact
        xteink = chapter(by_profile["Xteink X4"]["id"])
        assert "code-image" in xteink
        assert "<pre" not in xteink
        kindle = chapter(by_profile["Kindle"]["id"])
        assert "flowchart TD\n" in kindle


def test_profile_screen_caps_photo_width(tmp_path, monkeypatch):
    # a device profile with screen dims recompresses photos to 2x screen
    # width instead of the global 1200px ceiling
    from io import BytesIO

    import httpx
    from PIL import Image as PILImage

    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))

    buf = BytesIO()
    PILImage.new("RGB", (2400, 1200), (10, 20, 30)).save(buf, format="PNG")
    png = buf.getvalue()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=png, headers={"content-type": "image/png"})

    def fake_client(**overrides):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        import sqlite3

        with sqlite3.connect(tmp_path / "t.db") as conn:
            conn.execute(
                "UPDATE articles SET full_content = ? WHERE id = ?",
                ('<p>x</p><img src="https://img.example/wide.png" alt=""/>', ids[0]),
            )
            conn.commit()

        with patch(
            "rss_kindle.services.digest_service.make_http_client", new=fake_client
        ):
            created = client.post(
                "/api/digests", json={"article_ids": [ids[0]], "profiles": ["Xteink X4"]}
            ).json()
            assert _wait_settled(client, created[0]["id"])["status"] == "ready"

        epub_bytes = client.get(f"/api/digests/{created[0]['id']}/download").content
        with zipfile.ZipFile(io.BytesIO(epub_bytes)) as z:
            (name,) = [n for n in z.namelist() if n.startswith("EPUB/images/")]
            img = Image.open(io.BytesIO(z.read(name)))
            assert img.width <= 960


def test_same_day_compiles_get_numbered_titles(tmp_path, monkeypatch):
    from datetime import date

    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        today = date.today().isoformat()
        first = client.post("/api/digests", json={"article_ids": ids}).json()
        assert first[0]["title"] == today
        second = client.post("/api/digests", json={"article_ids": ids}).json()
        assert second[0]["title"] == f"{today} No. 2"
        third = client.post(
            "/api/digests", json={"article_ids": ids, "profiles": ["Kindle", "Xteink X4"]}
        ).json()
        assert [d["title"] for d in third] == [
            f"{today} No. 3 · Kindle",
            f"{today} No. 3 · Xteink X4",
        ]
        # explicit titles are left alone
        named = client.post("/api/digests", json={"article_ids": ids, "title": today}).json()
        assert named[0]["title"] == today


# --- OPDS folders ------------------------------------------------------------


def test_opds_root_lists_profile_folders(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        r = client.get("/opds")
        assert r.status_code == 200
        root = ET.fromstring(r.content)
        hrefs = [
            link.get("href", "") for link in root.findall("atom:entry/atom:link", NS)
        ]
        assert any(h.endswith("/opds/profiles/Kindle") for h in hrefs)
        assert any(h.endswith("/opds/profiles/Xteink%20X4") for h in hrefs)


def test_opds_profile_feed_filters_by_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("EPUB_DIR", str(tmp_path / "epubs"))
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        ids = _seed(client)
        created = client.post(
            "/api/digests",
            json={"article_ids": ids, "title": "ed", "profiles": ["Kindle", "Xteink X4"]},
        ).json()
        for d in created:
            assert _wait_settled(client, d["id"])["status"] == "ready"

        r = client.get("/opds/profiles/Kindle")
        assert r.status_code == 200
        root = ET.fromstring(r.content)
        titles = [e.findtext("atom:title", "", NS) for e in root.findall("atom:entry", NS)]
        assert titles == ["Edition ed · Kindle"]

        assert client.get("/opds/profiles/Nope").status_code == 404
