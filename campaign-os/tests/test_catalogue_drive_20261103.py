"""The shared catalogue's pictures live on Drive (2026-11-03).

Drive folder `Catalogue/<maker>/<file>` mirrors `_shared/catalogue/images/<maker>/<file>`.
Any machine (or live, into its volume) pulls it down; a picture the scout saved locally
waits on a "to upload" list until it has a drive_id.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from _lib import image_library as il


def _fake_listing():
    return [
        {"id": "a1", "name": "chrome-tour__1.png", "folder": "callaway", "mime": "image/png"},
        {"id": "b2", "name": "notes.txt", "folder": "callaway", "mime": "text/plain"},
        {"id": "c3", "name": "evil.png", "folder": "../../escape", "mime": "image/png"},
    ]


def _fake_download(file_id: str, dest: Path, session=None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"png-bytes-" + file_id.encode())


def test_catalogue_drive_folder_is_its_own_root():
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "scripts" / "ingest_public_drive_folder.py"
    spec = importlib.util.spec_from_file_location("_ingest_for_catalogue", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    BRAND_PUBLIC_ROOTS = mod.BRAND_PUBLIC_ROOTS
    assert il.CATALOGUE_DRIVE_ID == "1Aj6BzbUFVvpmG3g-fpQuHc0l-xBxIX9R"
    assert il.CATALOGUE_DRIVE_ID not in BRAND_PUBLIC_ROOTS.values()


def test_pull_mirrors_drive_into_the_catalogue(tmp_path: Path):
    got = il.pull_catalogue(data_dir=tmp_path, lister=lambda fid: _fake_listing(), downloader=_fake_download)
    dest = tmp_path / "brand-directory" / "_shared" / "catalogue" / "images" / "callaway" / "chrome-tour__1.png"
    assert dest.read_bytes() == b"png-bytes-a1"
    assert got["downloaded"] == ["callaway/chrome-tour__1.png"]
    assert got["skipped_existing"] == []
    assert [e["file"] for e in got["errors"]] == ["../../escape/evil.png"]
    assert not (tmp_path / "brand-directory" / "escape").exists()

    again = il.pull_catalogue(data_dir=tmp_path, lister=lambda fid: _fake_listing(), downloader=_fake_download)
    assert again["downloaded"] == []
    assert again["skipped_existing"] == ["callaway/chrome-tour__1.png"]


def test_pictures_are_read_from_the_volume_when_the_repo_has_none(tmp_path: Path, monkeypatch):
    repo_cat = tmp_path / "repo-catalogue"
    monkeypatch.setattr(il, "CATALOGUE", repo_cat)
    vol = tmp_path / "volume"
    pic = vol / "brand-directory" / "_shared" / "catalogue" / "images" / "callaway" / "chrome-tour__1.png"
    pic.parent.mkdir(parents=True)
    pic.write_bytes(b"from-volume")
    monkeypatch.setenv("DATA_DIR", str(vol))
    assert il.catalogue_bytes({"file": "images/callaway/chrome-tour__1.png"}) == b"from-volume"


def test_to_upload_until_marked_on_drive(tmp_path: Path):
    il.add_to_catalogue("Vessel", "Player V", "https://vesselgolf.com/p", "https://vesselgolf.com/x.png",
                        b"x" * 50, ".png", root=tmp_path)
    todo = il.to_upload(root=tmp_path)
    assert [r["file"] for r in todo] == ["images/vessel/player-v__1.png"]
    assert todo[0]["drive_folder"] == "vessel"
    assert il.mark_on_drive("images/vessel/player-v__1.png", "drive-id-1", root=tmp_path)
    assert il.to_upload(root=tmp_path) == []
    assert il.load_catalogue(tmp_path)[0]["drive_id"] == "drive-id-1"
    with pytest.raises(KeyError):
        il.mark_on_drive("images/nope.png", "x", root=tmp_path)
