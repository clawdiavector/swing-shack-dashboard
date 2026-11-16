"""Ad suggestions: a price in the caption is checked, and an empty list says why."""
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_11_13_ad_suggestions as t  # noqa: E402
from _lib import ads_suggest  # noqa: E402


def test_a_rand_price_in_the_caption_must_be_checked_as_current():
    p = t._post("m1", "Membership for only R399/pm. Join the club at Swing Shack.")
    s = t._by_post(t._build([p], brand="swing-shack"))["m1"]
    assert any("price" in c.lower() and "current" in c.lower() for c in s["checks"])


def test_reels_with_no_reach_are_named_as_the_reason_for_an_empty_list():
    out = t._build([t._post("n1", "Book a fitting at Stick.", reach=0), t._post("n2", "Book a lesson.", reach=0)])
    assert out["counts"] == {"posts": 2, "reels": 2, "reels_with_reach": 0}
    html = ads_suggest.render_html([out])
    assert "no reach" in html.lower()
