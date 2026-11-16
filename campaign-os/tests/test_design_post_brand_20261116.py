"""Design page: posts filed under the wrong brand, and animation pictures with no brand (16 Nov 2026)."""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import design_taxonomy as dt  # noqa: E402


def _row(brand, title, caption="", campaign=""):
    return {"id": "x", "brand": brand, "title": title, "caption": caption, "campaign": campaign}


def test_stick_voice_post_under_bag_drop_moves_to_stick():
    assert dt.correct_post_brand(_row("bag-drop", "Takomo 101U driving iron, available at Stick."))["brand"] == "stick"
    assert dt.correct_post_brand(_row("bag-drop", "Welcome to Stick Paarl: clubs"))["brand"] == "stick"


def test_swing_shack_voice_post_under_bag_drop_moves_to_swing_shack():
    row = _row("bag-drop", "Srixon Z-Star XV on the shelf", "It's on the shelf at Swing Shack. DM us")
    assert dt.correct_post_brand(row)["brand"] == "swing-shack"


def test_real_bag_drop_posts_stay():
    assert dt.correct_post_brand(_row("bag-drop", "Upgrade your short game, 20% off all putters online"))["brand"] == "bag-drop"
    # names both shops: not plain evidence, leave it
    both = _row("bag-drop", "Fit at Stick, then buy at Swing Shack")
    assert dt.correct_post_brand(both)["brand"] == "bag-drop"


def test_other_brands_are_never_touched():
    assert dt.correct_post_brand(_row("stick", "Come to Swing Shack at Swing Shack"))["brand"] == "stick"


def test_animation_experiments_get_a_brand_from_the_file_name():
    c = "Post animation experiments (wiki)"
    assert dt.correct_post_brand(_row("", "retail takomo", campaign=c))["brand"] == "stick"
    assert dt.correct_post_brand(_row("", "seedance bay living photo", campaign=c))["brand"] == "swing-shack"
    assert dt.correct_post_brand(_row("", "mystery", campaign=c))["brand"] == ""
    assert dt.correct_post_brand(_row("", "retail takomo", campaign="Other"))["brand"] == ""


def test_page_data_has_no_brandless_posts_and_no_stick_posts_under_bag_drop():
    posts = dt.build_taxonomy()["posts"]
    assert not [p["id"] for p in posts if not p.get("brand")]
    wrong = [p["id"] for p in posts if p.get("brand") == "bag-drop"
             and ("at Stick" in (p.get("title") or "") + (p.get("caption") or "")
                  or "at Swing Shack" in (p.get("title") or "") + (p.get("caption") or ""))]
    assert wrong == []
