import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import service_tiein as st


def test_irons_point_to_club_fitting_at_both_brands():
    for name in ("Titleist T250 Iron Set", "Mizuno Pro 245 Irons", "Srixon ZX5 MkII Iron"):
        for brand, shop in (("swing-shack", "Swing Shack"), ("stick", "Stick")):
            line = st.service_tiein_line(name, brand)
            assert line and "club fitting" in line.lower() and shop in line, (name, line)


def test_iron_word_inside_another_word_does_not_match():
    assert st.service_tiein_line("Environment Towel", "stick") is None
