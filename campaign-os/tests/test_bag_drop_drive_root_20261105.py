"""Bag Drop reads its own Drive folder, without the web images (Christelle, 5 Nov).

The Bagdrop folder holds Bag Drop's own club cut-outs ("webp edits") and logo
("New Logo"), plus "Generic Bagdrop": images saved from other websites, which are
not cleared to use. That folder is never ingested."""
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ingest_public_drive_folder.py"
BAGDROP_ID = "1bBToPcp6xKchcATcyrmIEpbXnUVVaOnc"


def _mod():
    spec = importlib.util.spec_from_file_location("_ingest_bag_drop", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bag_drop_has_its_own_root():
    mod = _mod()
    assert mod.brand_sources("bag-drop") == [("", BAGDROP_ID)]
    assert BAGDROP_ID not in {v for k, v in mod.BRAND_PUBLIC_ROOTS.items() if k != "bag-drop"}


def test_generic_web_images_are_never_ingested(tmp_path, monkeypatch):
    mod = _mod()
    listing = [
        {"id": "c1", "name": "bagdrop141.webp", "mime": "image/webp", "folder": "webp edits/qi35 max 10.5"},
        {"id": "l1", "name": "bagdrop_logo2.webp", "mime": "image/webp", "folder": "New Logo"},
        {"id": "g1", "name": "fwoods-2025-elyte___1.jpg", "mime": "image/jpeg", "folder": "Generic Bagdrop/Used"},
        {"id": "g2", "name": "hybrids.jpg", "mime": "image/jpeg", "folder": "Generic Bagdrop"},
    ]
    monkeypatch.setattr(mod.gd, "list_public_folder", lambda fid: listing)

    def fake_download(fid, dest, session=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"img-" + fid.encode())
        return dest

    monkeypatch.setattr(mod.gd, "download_public_file", fake_download)
    monkeypatch.setattr(mod, "dissect", lambda p, bible: {})
    monkeypatch.setattr(mod, "tag_directory", lambda brand, base_dir=None: {})
    got = mod.run_ingest("bag-drop", BAGDROP_ID, data_dir=tmp_path)

    images = tmp_path / "brand-directory" / "bag-drop" / "images"
    assert (images / "webp edits" / "qi35 max 10.5" / "bagdrop141.webp").exists()
    assert (images / "New Logo" / "bagdrop_logo2.webp").exists()
    assert not (images / "Generic Bagdrop").exists()
    assert got["downloaded"] == 2 and got["skipped_folder"] == 2
    manifest = json.loads((tmp_path / "brand-directory" / "bag-drop" / "ingest-manifest.json").read_text())
    assert not any(k.startswith("Generic Bagdrop") for k in manifest["images"])


def test_other_brands_skip_nothing():
    mod = _mod()
    assert mod.skipped_folders("stick") == () and mod.skipped_folders("swing-shack") == ()
