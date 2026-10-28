import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import service_tiein as st


def test_ball_post_points_to_ball_fitting_at_both_brands():
    for brand, shop in (("swing-shack", "Swing Shack"), ("stick", "Stick")):
        line = st.service_tiein_line("Titleist Pro V1 Dozen", brand)
        assert "ball fitting" in line.lower()
        assert shop in line


def test_not_every_product_gets_a_service_line():
    assert st.service_tiein_line("Ping Golf Bag", "stick") is None
    assert st.service_tiein_line("Footjoy Weathersof Glove", "swing-shack") is None


def test_brand_without_the_service_gets_nothing():
    assert st.service_tiein_line("Titleist Pro V1 Dozen", "bag-drop") is None


def test_tiein_has_no_numbers_or_claims():
    line = st.service_tiein_line("Srixon Z-Star Dozen", "swing-shack")
    assert not any(ch.isdigit() for ch in line)


def test_add_tiein_goes_after_the_availability_line_and_only_once():
    cap = "Pro V1 in stock.\nAvailable at Stick."
    once = st.add_service_tiein(cap, "Titleist Pro V1 Dozen", "stick")
    lines = once.split("\n")
    assert lines[:2] == cap.split("\n")
    assert "ball fitting" in lines[2].lower()
    assert st.add_service_tiein(once, "Titleist Pro V1 Dozen", "stick") == once


def test_empty_caption_stays_empty():
    assert st.add_service_tiein(None, "Titleist Pro V1 Dozen", "stick") is None
