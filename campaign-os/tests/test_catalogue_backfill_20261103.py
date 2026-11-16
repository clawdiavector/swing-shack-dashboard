"""Filing the images the scout already saved into the shared catalogue, and noticing
when they reach Drive (2026-11-03).

The 140 maker images saved before the catalogue existed sit in each brand's
images/Products/ with their source on the photo map. backfill_from_photo_map() files
each one once (the same image for both shops counts once). After a person drags the
maker folders into Drive's Catalogue, link_drive_ids() finds them by path and records
their Drive ids, so nobody types ids by hand.
"""
from __future__ import annotations

import json
from pathlib import Path

from _lib import image_library as il


def _brand(tmp: Path, brand: str, entries: list[dict], files: dict[str, bytes]) -> Path:
    images = tmp / brand / "images"
    for rel, data in files.items():
        (images / rel).parent.mkdir(parents=True, exist_ok=True)
        (images / rel).write_bytes(data)
    (tmp / brand / "photo-map.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return images


def _entry(file: str, product: str, page: str, image: str, source: str = "official-site") -> dict:
    return {"file": file, "sku": "X", "product": product, "view": "front", "source": source,
            "status": "approved", "source_url": page, "image_url": image}


def test_backfill_files_each_image_once(tmp_path: Path):
    cat = tmp_path / "cat"
    ball = b"chrome-tour-bytes" * 100
    stick_images = _brand(tmp_path, "stick", [
        _entry("Products/CT__front.jpg", "Callaway Chrome Tour", "https://www.callawaygolf.com/chrome-tour",
               "https://prd-sfcc.callawaygolf.com/ct.jpg"),
        _entry("Products/OWN__front.jpg", "Our photo", "", "", source="instore"),
        _entry("Products/GONE__front.jpg", "Missing file", "https://vesselgolf.com/p", "https://vesselgolf.com/x.png"),
    ], {"Products/CT__front.jpg": ball, "Products/OWN__front.jpg": b"own"})
    ss_images = _brand(tmp_path, "swing-shack", [
        _entry("Products/SSCT__front.jpg", "Chrome Tour", "https://www.callawaygolf.com/chrome-tour",
               "https://prd-sfcc.callawaygolf.com/ct.jpg"),
    ], {"Products/SSCT__front.jpg": ball})

    a = il.backfill_from_photo_map("stick", images=stick_images, entries=json.loads(
        (tmp_path / "stick" / "photo-map.json").read_text())["entries"], root=cat)
    b = il.backfill_from_photo_map("swing-shack", images=ss_images, entries=json.loads(
        (tmp_path / "swing-shack" / "photo-map.json").read_text())["entries"], root=cat)

    assert a == {"added": 1, "already": 0, "missing": ["Products/GONE__front.jpg"]}
    assert b == {"added": 0, "already": 1, "missing": []}
    rows = il.load_catalogue(cat)
    assert len(rows) == 1
    assert rows[0]["maker"] == "Callaway"
    assert rows[0]["file"] == "images/callaway/callaway-chrome-tour__1.jpg"
    assert sorted(rows[0]["used_by"]) == ["stick:Products/CT__front.jpg", "swing-shack:Products/SSCT__front.jpg"]


def test_link_drive_ids_matches_by_path(tmp_path: Path):
    il.add_to_catalogue("Vessel", "Player V", "https://vesselgolf.com/p", "https://vesselgolf.com/x.png",
                        b"x" * 50, ".png", root=tmp_path)
    il.add_to_catalogue("Takomo", "101", "https://takomogolf.com/p", "https://takomogolf.com/y.png",
                        b"y" * 50, ".png", root=tmp_path)
    listing = [{"id": "d-vessel", "name": "player-v__1.png", "folder": "vessel", "mime": "image/png"},
               {"id": "d-other", "name": "stray.png", "folder": "vessel", "mime": "image/png"}]
    got = il.link_drive_ids(root=tmp_path, lister=lambda fid: listing)
    assert got == {"linked": 1, "still_to_upload": 1}
    assert [r["file"] for r in il.to_upload(root=tmp_path)] == ["images/takomo/101__1.png"]
