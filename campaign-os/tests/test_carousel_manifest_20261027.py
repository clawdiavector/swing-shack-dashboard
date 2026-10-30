"""Carousel manifest (Christelle's carousel design guide, 2026-10-27): until multi-image posting
(wiki T18) is built, a carousel is numbered slide files plus one ordered manifest, and the order
must never depend on how file names happen to sort."""
import importlib.util
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "carousel_check", ROOT / "plugins/campaign-os/skills/campaign-os-carousel/scripts/carousel_check.py")
carousel_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(carousel_check)


def make(tmp_path, names):
    paths = []
    for name in names:
        p = tmp_path / name
        Image.new("RGB", (1080, 1350), (30, 60, 90)).save(p)
        paths.append(p)
    return paths


def test_numbered_names_in_order_pass(tmp_path):
    assert carousel_check.problems(make(tmp_path, ["01_hero.png", "02_detail.png", "03_cta.png"])) == []


def test_name_number_out_of_order_is_flagged(tmp_path):
    out = carousel_check.problems(make(tmp_path, ["01_hero.png", "03_cta.png", "02_detail.png"]))
    assert any("slide 2" in p and "03_cta.png" in p for p in out)


def test_unnumbered_name_is_flagged(tmp_path):
    out = carousel_check.problems(make(tmp_path, ["01_hero.png", "detail.png"]))
    assert any("detail.png" in p for p in out)


def test_main_writes_ordered_manifest(tmp_path):
    paths = make(tmp_path, ["01_hero.png", "02_detail.png", "03_cta.png"])
    out = tmp_path / "out"
    assert carousel_check.main([*map(str, paths), "--out", str(out)]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert [s["slide"] for s in manifest["slides"]] == [1, 2, 3]
    assert [Path(s["file"]).name for s in manifest["slides"]] == ["01_hero.png", "02_detail.png", "03_cta.png"]
    assert Path(manifest["gbp_cover"]).name == "gbp-slide-1.jpg"
