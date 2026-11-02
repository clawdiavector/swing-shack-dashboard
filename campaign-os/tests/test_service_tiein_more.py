import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import service_tiein as st


def test_confirmed_pairings_name_the_service_and_the_shop():
    cases = {
        "Odyssey White Hot Putter": "putter fitting",
        "Titleist Vokey SM10 Wedge": "wedge gapping",
        "Golf Pride Tour Velvet Grip": "re-grip",
        "Titleist TSR3 Driver": "club fitting",
        "Fujikura Speeder Shaft": "club fitting",
    }
    for name, service in cases.items():
        for brand, shop in (("swing-shack", "Swing Shack"), ("stick", "Stick")):
            line = st.service_tiein_line(name, brand)
            assert line and service in line.lower(), (name, line)
            assert shop in line
            assert not any(ch.isdigit() for ch in line)


def test_gloves_and_unlisted_products_stay_plain():
    assert st.service_tiein_line("Footjoy Weathersof Glove", "stick") is None
    assert st.service_tiein_line("Ping Golf Bag", "stick") is None
