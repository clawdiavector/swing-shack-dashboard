"""With the shop open, a Stick shop-angle caption's ask is the shop line itself, so it never has two asks
(the caption checker hard-fails "DM us" plus "Shop online", and the weekly generator then drops the post)."""
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))

from _lib import retail_campaign as rc  # noqa: E402
from _lib.store_notice import NOTICES  # noqa: E402


def test_shop_angle_caption_has_one_ask_and_passes_the_checker():
    cap = rc.build_caption("stick", "Takomo 101U irons", "", "", "shopify")
    lines = cap.splitlines()
    assert NOTICES["stick"] in lines
    assert not any(l.startswith("DM us") for l in lines)
    assert lines[-1] == "Better begins here."
    assert rc.caption_hard_fails("stick", cap) == []


def test_other_angles_still_pass_the_checker():
    for angle in ("product", "service"):
        cap = rc.build_caption("stick", "Vice Pro Air White Sleeve", "", "", angle)
        assert rc.caption_hard_fails("stick", cap) == [], (angle, cap)
