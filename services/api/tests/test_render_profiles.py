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


def test_complex_table_becomes_8bit_png() -> None:
    rewritten, images = tables_to_images(f"<p>intro</p>{_COMPLEX_TABLE}", rotate=False)
    assert "<table" not in rewritten
    assert 'class="table-image"' in rewritten
    assert list(images) == ["tables/tbl_0001.png"]
    img = Image.open(io.BytesIO(images["tables/tbl_0001.png"].data))
    assert img.mode == "L"
    _, _, bitdepth, _ = _ihdr(images["tables/tbl_0001.png"].data)
    assert bitdepth == 8


def test_rotated_table_swaps_dimensions() -> None:
    table = lxml_html.fragment_fromstring(_COMPLEX_TABLE)
    (flat,) = render_table_pngs(table, rotate=False)
    (turned,) = render_table_pngs(table, rotate=True)
    flat_img = Image.open(io.BytesIO(flat))
    turned_img = Image.open(io.BytesIO(turned))
    assert (turned_img.width, turned_img.height) == (flat_img.height, flat_img.width)


def test_aspect_cap_splits_tall_table_and_repeats_header() -> None:
    rows = "".join(
        f"<tr><td>row {i}</td><td>some considerably longer cell text {i}</td>"
        f"<td>more {i}</td></tr>"
        for i in range(40)
    )
    table = lxml_html.fragment_fromstring(
        f"<table><tr><th>A</th><th>B</th><th>C</th></tr>{rows}</table>"
    )
    parts = render_table_pngs(table, rotate=False, aspect="1:1")
    assert len(parts) >= 2
    for part in parts:
        img = Image.open(io.BytesIO(part))
        # each chunk respects the cap (header + rows never exceed width)
        assert img.height <= img.width
    # every chunk carries the header: chunks must be taller than a header-less
    # split of the same rows would need — cheap proxy: total height of all
    # chunks exceeds the unsplit table's height by at least one header row.
    (whole,) = render_table_pngs(table, rotate=False, aspect="auto")
    whole_h = Image.open(io.BytesIO(whole)).height
    total_h = sum(Image.open(io.BytesIO(p)).height for p in parts)
    assert total_h > whole_h


def test_aspect_split_emits_multiple_images_in_html() -> None:
    rows = "".join(
        f"<tr><td>row {i}</td><td>some considerably longer cell text {i}</td>"
        f"<td>more {i}</td></tr>"
        for i in range(40)
    )
    html = f"<table><tr><th>A</th><th>B</th><th>C</th></tr>{rows}</table>"
    rewritten, images = tables_to_images(html, rotate=False, aspect="1:1")
    assert len(images) >= 2
    assert rewritten.count("table-image") == len(images)


def test_simple_table_stays_native() -> None:
    html = "<table><tr><th>K</th><th>V</th></tr><tr><td>a</td><td>b</td></tr></table>"
    rewritten, images = tables_to_images(html, rotate=False)
    assert rewritten == html
    assert images == {}


# --- Per-profile compiles ----------------------------------------------------


def _seed(client: TestClient) -> list[int]:
    r = client.post("/api/feeds", json={"url": "https://example.com/rss", "title": "Example"})
    feed_id = r.json()["id"]
    with patch("rss_kindle.api.feeds.fetch_feed_bytes") as m:
        m.return_value = FIXTURE.read_bytes()
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
        assert s["profiles"][1]["table_mode"] == "image_rotated"
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
