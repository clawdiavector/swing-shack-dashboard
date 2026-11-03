"""Carousel check (Christelle, 2026-10-27): the slides of one carousel are checked together
before anyone sees them: 2 to 10 slides, every slide 1080x1350 (Instagram crops the whole
set to slide 1's shape), a numbered contact sheet to review, and slide 1 as a 4:3 for
Google Business, which takes one image."""
import importlib.util
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "carousel_check", ROOT / "plugins/campaign-os/skills/campaign-os-carousel/scripts/carousel_check.py")
carousel_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(carousel_check)


def slides(tmp_path, sizes):
    paths = []
    for n, size in enumerate(sizes, 1):
        p = tmp_path / f"{n:02d}.png"
        Image.new("RGB", size, (20 * n, 40, 80)).save(p)
        paths.append(p)
    return paths


def test_good_set_has_no_problems(tmp_path):
    assert carousel_check.problems(slides(tmp_path, [(1080, 1350)] * 4)) == []


def test_one_slide_is_not_a_carousel(tmp_path):
    out = carousel_check.problems(slides(tmp_path, [(1080, 1350)]))
    assert any("2 to 10" in p for p in out)


def test_eleven_slides_is_too_many(tmp_path):
    out = carousel_check.problems(slides(tmp_path, [(1080, 1350)] * 11))
    assert any("2 to 10" in p for p in out)


def test_odd_slide_out_is_named(tmp_path):
    out = carousel_check.problems(slides(tmp_path, [(1080, 1350), (1080, 1080), (1080, 1350)]))
    assert len(out) == 1
    assert "slide 2" in out[0] and "1080x1080" in out[0]


def test_whole_set_in_wrong_shape_is_flagged(tmp_path):
    out = carousel_check.problems(slides(tmp_path, [(1080, 1080)] * 3))
    assert out and all("1080x1350" in p for p in out)


def test_contact_sheet_shows_every_slide_in_one_row(tmp_path):
    ims = [Image.open(p) for p in slides(tmp_path, [(1080, 1350)] * 5)]
    sheet = carousel_check.contact_sheet(ims)
    assert sheet.width > sheet.height
    assert sheet.width >= 5 * carousel_check.THUMB[0]


def test_google_business_cover_is_4_by_3_from_slide_1(tmp_path):
    cover = carousel_check.gbp_cover(Image.open(slides(tmp_path, [(1080, 1350)])[0]))
    assert cover.size == (1200, 900)


def test_main_writes_sheet_and_cover_and_fails_on_problems(tmp_path):
    good = slides(tmp_path, [(1080, 1350)] * 3)
    out = tmp_path / "out"
    assert carousel_check.main([*map(str, good), "--out", str(out)]) == 0
    assert (out / "contact-sheet.jpg").is_file()
    assert (out / "gbp-slide-1.jpg").is_file()
    assert carousel_check.main([str(good[0]), "--out", str(out)]) == 1
