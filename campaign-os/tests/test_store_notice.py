"""Stick product captions carry a 'Shopify store coming soon' line until the store is live."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import store_notice as sn


def test_stick_caption_gets_the_line_before_the_sign_off():
    cap = "Vice Pro Air available at Stick.\nDM us for price and details.\nBetter begins here."
    out = sn.add_store_notice(cap, "stick")
    lines = out.split("\n")
    assert "Shopify store coming soon." in lines
    assert lines[-1] == "Better begins here."
    assert lines.index("Shopify store coming soon.") == len(lines) - 2


def test_caption_without_sign_off_gets_it_at_the_end():
    out = sn.add_store_notice("Takomo irons at Stick.", "stick")
    assert out.endswith("\nShopify store coming soon.")


def test_not_added_twice():
    once = sn.add_store_notice("Takomo irons at Stick.", "stick")
    assert sn.add_store_notice(once, "stick") == once


def test_other_brands_untouched():
    cap = "Titleist T250 at Swing Shack."
    assert sn.add_store_notice(cap, "swing-shack") == cap
    assert sn.add_store_notice(cap, "bag-drop") == cap


def test_empty_caption_stays_empty():
    assert sn.add_store_notice(None, "stick") is None
    assert sn.add_store_notice("", "stick") == ""
