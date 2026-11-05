"""iPhone HEIC photos are filed as JPEG (Christelle, 5 Nov).

The live server could not open HEIC at all, so 350 Shot List photos were stored but
unscanned, unusable in posts and blank in the browser. The ingest now converts them on
the way in, and convert_existing_heic() fixes the ones already on disk."""
import importlib.util
import io
import json
from pathlib import Path

import pytest

pillow_heif = pytest.importorskip("pillow_heif")
from PIL import Image  # noqa: E402

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
SCRIPT = CAMPAIGN_OS / "scripts" / "ingest_public_drive_folder.py"


def _mod():
    spec = importlib.util.spec_from_file_location("_ingest_heic", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _heic_bytes():
    pillow_heif.register_heif_opener()
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (0, 61, 84)).save(buf, format="HEIF")
    return buf.getvalue()


def test_the_live_image_installs_the_heic_reader():
    reqs = (CAMPAIGN_OS / "requirements.txt").read_text().lower()
    assert "pillow-heif" in reqs or "pillow_heif" in reqs


def test_a_heic_from_drive_is_filed_as_jpeg(tmp_path, monkeypatch):
    mod = _mod()
    listing = [{"id": "h1", "name": "IMG_1.HEIC", "mime": "image/heif", "folder": "Putters"}]
    monkeypatch.setattr(mod.gd, "list_public_folder", lambda fid: listing)

    def fake_download(fid, dest, session=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_heic_bytes())
        return dest

    seen = []
    monkeypatch.setattr(mod.gd, "download_public_file", fake_download)
    monkeypatch.setattr(mod, "dissect", lambda p, bible: seen.append(Path(p).name) or {})
    monkeypatch.setattr(mod, "tag_directory", lambda brand, base_dir=None: {})
    got = mod.run_ingest("stick", "x", data_dir=tmp_path, folder_prefix="Shot List")

    folder = tmp_path / "brand-directory" / "stick" / "images" / "Shot List" / "Putters"
    jpg = folder / "IMG_1.jpg"
    assert got["downloaded"] == 1
    assert not (folder / "IMG_1.HEIC").exists()
    with Image.open(jpg) as im:
        assert (im.format, im.size) == ("JPEG", (64, 48))
    assert seen == ["IMG_1.jpg"]
    manifest = json.loads((tmp_path / "brand-directory" / "stick" / "ingest-manifest.json").read_text())
    row = manifest["images"]["Shot List/Putters/IMG_1.jpg"]
    assert row["drive_id"] == "h1" and row["converted_from"] == "IMG_1.HEIC"
    assert "Shot List/Putters/IMG_1.HEIC" not in manifest["images"]


def test_heic_already_on_disk_is_converted_and_rescanned(tmp_path, monkeypatch):
    mod = _mod()
    brand_dir = tmp_path / "brand-directory" / "stick"
    folder = brand_dir / "images" / "Shot List" / "Stick Towel"
    folder.mkdir(parents=True)
    (folder / "IMG_9.HEIC").write_bytes(_heic_bytes())
    (folder / "IMG_9.visual-dna.json").write_text('{"error": "cannot identify image file"}')
    (brand_dir / "ingest-manifest.json").write_text(json.dumps({"images": {
        "Shot List/Stick Towel/IMG_9.HEIC": {"drive_id": "h9", "md5": "abc", "folder": "Shot List/Stick Towel"}}}))
    monkeypatch.setattr(mod, "dissect", lambda p, bible: {"ok": Path(p).name})
    monkeypatch.setattr(mod, "tag_directory", lambda brand, base_dir=None: {})

    got = mod.convert_existing_heic("stick", data_dir=tmp_path)

    assert got["converted"] == ["Shot List/Stick Towel/IMG_9.jpg"] and got["errors"] == []
    assert not (folder / "IMG_9.HEIC").exists()
    assert json.loads((folder / "IMG_9.visual-dna.json").read_text()) == {"ok": "IMG_9.jpg"}
    manifest = json.loads((brand_dir / "ingest-manifest.json").read_text())["images"]
    assert manifest["Shot List/Stick Towel/IMG_9.jpg"]["drive_id"] == "h9"
    assert "Shot List/Stick Towel/IMG_9.HEIC" not in manifest
