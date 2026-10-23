"""Swing Shack product post templates: layouts, cut-out, rotation, claim guard."""
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import product_post_templates as pt  # noqa: E402


def _box(tmp_path, name="box.jpg", colour=(30, 60, 160)):
    im = Image.new("RGB", (400, 400), "white")
    ImageDraw.Draw(im).rectangle((60, 100, 340, 300), fill=colour)
    ImageDraw.Draw(im).rectangle((150, 150, 250, 250), fill="white")  # white inside the product
    p = tmp_path / name
    im.save(p)
    return str(p)


def _post(tmp_path, layout, n=3):
    return {"layout": layout, "brand": "Acme", "headline": ["TEST", "RANGE."],
            "models": [{"label": "M%d" % i, "image": _box(tmp_path, "b%d.jpg" % i)} for i in range(n)]}


def test_cutout_keeps_white_inside_and_drops_outside(tmp_path):
    cut = pt.cutout(_box(tmp_path))
    assert cut.getpixel((5, 5))[3] == 0          # outside the box: transparent
    assert cut.getpixel((200, 200))[3] == 255    # white centre inside the box: kept
    assert cut.getpixel((100, 120))[3] == 255


@pytest.mark.parametrize("layout,n", [("type-hero", 3), ("type-hero", 1), ("type-hero", 2), ("pick-yours", 3), ("pick-yours", 1), ("one-hero", 1)])
def test_every_layout_renders_at_canvas_size(tmp_path, layout, n):
    img = pt.render(_post(tmp_path, layout, n))
    assert img.size == (1080, 1350) and img.mode == "RGB"


def test_one_hero_needs_exactly_one_product(tmp_path):
    with pytest.raises(ValueError):
        pt.render(_post(tmp_path, "one-hero", 2))


def test_claims_and_long_lines_are_refused(tmp_path):
    p = _post(tmp_path, "type-hero")
    p["headline"] = ["THE LONGEST", "BALL."]
    assert any("longest" in m for m in pt.check_post(p))
    p["headline"] = ["A VERY LONG HEADLINE LINE", "X"]
    assert any("14" in m for m in pt.check_post(p))


def test_rotation_never_repeats_within_two_posts():
    hist = []
    for _ in range(12):
        nxt = pt.next_layout(hist)
        assert nxt not in hist[-2:]
        hist.append(nxt)
    assert set(hist) == set(pt.LAYOUTS)


def test_multi_product_posts_never_get_one_hero():
    hist = ["type-hero", "pick-yours"]
    assert pt.next_layout(hist) == "one-hero"
    assert pt.layout_for(3, hist) != "one-hero"
    assert pt.layout_for(1, hist) == "one-hero"
