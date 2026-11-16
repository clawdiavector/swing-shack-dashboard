"""Herman's voice rules (email, 31 Oct 2026) are enforced, not just written down.

- Swing Shack's closing line has always been "Keep Swinging".
- Neither Stick nor Swing Shack is ever called a "golf shop".
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))

import caption_lint as L  # noqa: E402
from _lib import retail_campaign as rc  # noqa: E402

LANES = ["product-arrival", "fitting-education", "coaching", "membership",
         "competition", "events", "new-team-member"]


def codes(res, level=None):
    return {f["code"] for f in res["findings"] if level is None or f["level"] == level}


def test_swing_shack_bible_sets_keep_swinging_as_required_signoff():
    rules = L.load_rules("swing-shack")
    assert rules["signoff"] == "Keep Swinging"
    assert rules["signoff_required"] is True
    for lane in LANES:
        assert rules["lanes"][lane]["signoff_required"] is True, lane


@pytest.mark.parametrize("lane", [None, "coaching"])
def test_swing_shack_caption_without_keep_swinging_is_flagged(lane):
    res = L.lint("swing-shack", "Your coach is in.\nBook your coaching session.", cross_brand=False, lane=lane)
    assert "signoff-missing" in codes(res)


def test_swing_shack_caption_ending_keep_swinging_passes_signoff():
    res = L.lint("swing-shack", "Your coach is in.\nBook your coaching session.\nKeep Swinging", cross_brand=False)
    assert not codes(res) & {"signoff-missing", "signoff-variant", "signoff-place"}


@pytest.mark.parametrize("brand,caption", [
    ("stick", "Paarl's favourite golf shop.\nBook a fitting at Stick.\nBetter begins here."),
    ("swing-shack", "The best golf shop in Joburg.\nBook your coaching session.\nKeep Swinging"),
])
def test_golf_shop_is_banned_for_both_brands(brand, caption):
    res = L.lint(brand, caption, cross_brand=False)
    assert "banned-brand" in codes(res, L.HARD)


def test_swing_shack_retail_caption_closes_with_keep_swinging():
    cap = rc.build_caption("swing-shack", "Herschel Retreat bag")
    assert cap.rstrip().split("\n")[-1] == "Keep Swinging"


def test_stick_retail_caption_still_closes_with_better_begins_here():
    cap = rc.build_caption("stick", "Herschel Retreat bag")
    assert cap.rstrip().split("\n")[-1] == "Better begins here."
