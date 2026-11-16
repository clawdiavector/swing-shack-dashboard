"""Stick's Shot List is read where it lives, as a second Stick photo source (Christelle, 5 Nov).

The folder belongs to info@stickgolf.co.za, not to the Five Friday Stick root, so it is
listed on its own and filed under images/Shot List/<line>/ instead of being copied into Drive."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ingest_public_drive_folder.py"
SHOT_LIST_ID = "11VFWJOrRi6B3MYjCB78Qew4QXe1D7NSx"


def _mod():
    spec = importlib.util.spec_from_file_location("_ingest_shot_list", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_stick_reads_its_root_then_the_shot_list():
    mod = _mod()
    assert mod.brand_sources("stick") == [("", mod.BRAND_PUBLIC_ROOTS["stick"]), ("Shot List", SHOT_LIST_ID)]
    assert mod.brand_sources("swing-shack") == [("", mod.BRAND_PUBLIC_ROOTS["swing-shack"])]
    assert mod.brand_sources("nobody") == []


def test_extra_sources_are_never_a_brand_root():
    mod = _mod()
    roots = set(mod.BRAND_PUBLIC_ROOTS.values())
    for extras in mod.BRAND_EXTRA_SOURCES.values():
        assert not roots & set(extras.values())


def test_shot_list_files_land_under_their_own_folder(tmp_path, monkeypatch):
    mod = _mod()
    listing = [
        {"id": "p1", "name": "IMG_1.HEIC", "mime": "image/heif", "folder": "Putters/LAB VZN1"},
        {"id": "v1", "name": "clip.mp4", "mime": "video/mp4", "folder": "Avoda"},
    ]
    monkeypatch.setattr(mod.gd, "list_public_folder", lambda fid: listing if fid == SHOT_LIST_ID else [])

    def fake_download(fid, dest, session=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"photo-" + fid.encode())
        return dest

    monkeypatch.setattr(mod.gd, "download_public_file", fake_download)
    monkeypatch.setattr(mod, "dissect", lambda p, bible: {})
    monkeypatch.setattr(mod, "tag_directory", lambda brand, base_dir=None: {})
    got = mod.run_ingest("stick", SHOT_LIST_ID, data_dir=tmp_path, folder_prefix="Shot List")
    images = tmp_path / "brand-directory" / "stick" / "images"
    assert (images / "Shot List" / "Putters" / "LAB VZN1" / "IMG_1.HEIC").read_bytes() == b"photo-p1"
    assert got["downloaded"] == 1 and got["skipped_non_image"] == 1
    import json
    manifest = json.loads((tmp_path / "brand-directory" / "stick" / "ingest-manifest.json").read_text())
    assert "Shot List/Putters/LAB VZN1/IMG_1.HEIC" in manifest["images"]
