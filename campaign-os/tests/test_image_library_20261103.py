"""One home for logos, maker logos and sourced (catalogue) images (2026-11-03).

- Each brand's own logos live in <brand>/logos/ and are listed in logos/logos.json.
- Maker logos (Callaway, Vice, ...) live ONCE in _shared/maker-logos/, for every brand.
- Official images found on a maker's site go into one shared catalogue
  (_shared/catalogue/catalogue.json + images/<maker>/), with where they came from.
- A sourced photo cannot be approved until that maker's image rights are recorded as
  cleared in _system/image-sources.json (Christelle's rule, 2026-10-28).
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from _lib import image_library as il
from _lib import image_scout
from _lib import photo_map as pm
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id, load_archetypes_doc

ROOT = Path(__file__).resolve().parents[2]
BD = ROOT / "data" / "brand-directory"
SHARED = BD / "_shared"
MAKERS = ["callaway", "ripit", "takomo", "vice"]
REGISTER_FIELDS = {"file", "what", "background", "source", "status"}


def _fresh():
    """The modules the code under test will import right now.

    Some older tests purge _lib.* from sys.modules mid-run, so the copies imported at the top of
    this file can be stale: patching them would leave the real code pointing at the real data/."""
    import importlib

    return (importlib.import_module("_lib.image_library"), importlib.import_module("_lib.image_scout"),
            importlib.import_module("_lib.photo_map"))


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _png(w: int = 1200, h: int = 1200) -> bytes:
    """Noise, so the file is as heavy as a real product shot and passes the scout's size gate."""
    buf = io.BytesIO()
    Image.effect_noise((w, h), 64).convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


# --- maker logos: one shared set -------------------------------------------------------------

@pytest.mark.parametrize("slug", MAKERS)
def test_maker_logo_in_shared_folder(slug: str):
    p = SHARED / "maker-logos" / f"{slug}.png"
    assert p.is_file()
    assert Image.open(p).mode == "RGBA"


@pytest.mark.parametrize("brand", ["stick", "swing-shack", "bag-drop"])
def test_every_brand_finds_the_shared_maker_logo(brand: str):
    p = il.maker_logo_path(brand, "Callaway")
    assert p is not None and p.name == "callaway.png"


def test_brand_copies_of_maker_logos_match_the_shared_one():
    """Stick still has copies (an older test pins them); they may not drift from the shared file."""
    for p in (BD / "stick" / "logos" / "vendors").glob("*.png"):
        assert _md5(p) == _md5(SHARED / "maker-logos" / p.name), p.name


def test_unknown_maker_has_no_logo():
    assert il.maker_logo_path("swing-shack", "Not A Real Maker") is None


# --- brand logo registers ---------------------------------------------------------------------

@pytest.mark.parametrize("folder", ["stick/logos", "swing-shack/logos", "_shared/maker-logos"])
def test_logo_register_lists_every_file(folder: str):
    d = BD / folder
    reg = json.loads((d / "logos.json").read_text(encoding="utf-8"))
    listed = {row["file"] for row in reg["logos"]}
    on_disk = {p.name for p in d.glob("*.png")}
    assert listed == on_disk, (listed ^ on_disk)
    for row in reg["logos"]:
        assert REGISTER_FIELDS <= set(row), row
        assert row["status"] in il.LOGO_STATUSES, row


# --- Swing Shack templates use the one official logo ------------------------------------------

def test_swing_shack_templates_use_the_official_logo():
    doc = load_archetypes_doc("swing-shack")
    bad = []

    def walk(node):
        if isinstance(node, dict):
            a = node.get("asset")
            if isinstance(a, str) and "logo" in a and a != "logos/swing-shack-logo-white.png":
                bad.append(a)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    assert not bad, sorted(set(bad))


# --- catalogue of sourced images --------------------------------------------------------------

def test_catalogue_index_is_valid():
    doc = json.loads((SHARED / "catalogue" / "catalogue.json").read_text(encoding="utf-8"))
    assert isinstance(doc["images"], list)
    for row in doc["images"]:
        assert {"file", "maker", "product", "page_url", "image_url", "sha256", "added"} <= set(row)


def test_add_to_catalogue_saves_once(tmp_path: Path):
    data = _png()
    a = il.add_to_catalogue("Callaway", "Chrome Tour", "https://www.callawaygolf.com/p",
                            "https://prd-sfcc.callawaygolf.com/x.png", data, ".png", root=tmp_path)
    b = il.add_to_catalogue("Callaway", "Chrome Tour", "https://www.callawaygolf.com/p",
                            "https://prd-sfcc.callawaygolf.com/x.png", data, ".png", root=tmp_path)
    assert a["file"] == b["file"] == "images/callaway/chrome-tour__1.png"
    assert (tmp_path / a["file"]).read_bytes() == data
    assert len(il.load_catalogue(tmp_path)) == 1
    assert il.find_in_catalogue("https://prd-sfcc.callawaygolf.com/x.png", root=tmp_path)["file"] == a["file"]


def test_scout_fetch_files_the_image_in_the_catalogue(tmp_path: Path, monkeypatch):
    il, image_scout, pm = _fresh()
    cat, images, products = tmp_path / "cat", tmp_path / "images", tmp_path / "products"
    products.mkdir()
    monkeypatch.setattr(il, "CATALOGUE", cat)
    monkeypatch.setattr(pm, "_map_path", lambda b: products / "photo-map.json")
    calls = []

    def fake_get(url, referer=""):
        calls.append(url)
        return {"data": _png(), "type": "image/png"}

    monkeypatch.setattr(image_scout, "_get", fake_get)
    row = {"sku": "CW001", "product": "Chrome Tour", "view": "front",
           "page_url": "https://www.callawaygolf.com/p", "image_url": "https://prd-sfcc.callawaygolf.com/x.png"}
    qc = image_scout.fetch("stick", row, images=images)
    assert qc["ok"], qc
    assert (images / "Products" / "CW001__front.png").is_file()
    assert il.find_in_catalogue(row["image_url"])["maker"] == "Callaway"

    # The other shop stocks the same ball: no second download, same bytes.
    qc2 = image_scout.fetch("swing-shack", dict(row, sku="SS-CT"), images=tmp_path / "ss-images")
    assert qc2["ok"], qc2
    assert len(calls) == 1
    assert len(il.load_catalogue()) == 1


# --- image rights -----------------------------------------------------------------------------

def test_every_image_source_records_rights():
    doc = json.loads((BD / "_system" / "image-sources.json").read_text(encoding="utf-8"))
    for name, src in doc["brands"].items():
        if name == "Not scouted yet":
            continue
        r = src.get("rights")
        assert isinstance(r, dict) and r.get("status") in il.RIGHTS_STATUSES, name


def test_maker_found_from_image_address():
    assert il.maker_for_url("https://prd-sfcc.callawaygolf.com/dw/image/x.jpg") == "Callaway"
    assert il.maker_for_url("https://vesselgolf.com/cdn/shop/x.png") == "Vessel"
    assert il.maker_for_url("https://example.org/x.png") == ""


def test_sourced_photo_waits_for_cleared_rights(tmp_path: Path, monkeypatch):
    il, _, pm = _fresh()
    monkeypatch.setattr(pm, "_map_path", lambda b: tmp_path / "photo-map.json")
    monkeypatch.setattr(il, "rights_for", lambda maker: {"Vessel": "cleared"}.get(maker, "unknown"))
    pm.add_entry("stick", "Products/CW001__front.png", "CW001", "Chrome Tour", "front", source="official-site",
                 image_url="https://prd-sfcc.callawaygolf.com/x.png")
    pm.add_entry("stick", "Products/VS001__front.png", "VS001", "Vessel Player V", "front", source="official-site",
                 image_url="https://vesselgolf.com/cdn/x.png")
    pm.add_entry("stick", "Products/TS001__front.jpg", "TS001", "Takomo 101", "front", source="instore")

    with pytest.raises(il.RightsNotCleared):
        pm.set_status("stick", "Products/CW001__front.png", "approved")
    assert pm.set_status("stick", "Products/CW001__front.png", "rejected")      # rejecting is always fine
    assert pm.set_status("stick", "Products/VS001__front.png", "approved")      # maker cleared
    assert pm.set_status("stick", "Products/TS001__front.jpg", "approved")      # our own photo


# --- the maker-stack template still renders with the shared logo ------------------------------

def test_stick_product_post_renders_with_shared_maker_logo():
    arch = archetype_by_id("stick", "stick-product-post")
    buf = io.BytesIO()
    Image.new("RGBA", (600, 1100), (150, 150, 150, 255)).save(buf, format="PNG")
    fields = {"vendor_name": "Callaway", "product_name": "CHROME TOUR", "cta": "DM US FOR DETAILS"}
    out = compose_post_for_channels(brand_id="stick", archetype=arch, channels=["instagram"],
                                    fields=fields, photo_bytes=buf.getvalue())
    assert out["instagram"]
