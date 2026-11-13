"""Ad suggestions: a test can be paid for by leftover room plus weak ad sets, or partly, with an ask for the rest."""
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_11_13_ad_suggestions as t  # noqa: E402

SETS = [("a", "stick_leads_coaching_may26_set", 20), ("b", "stick_leads_putter_may26_set", 20)]
ADS = [("coaching_video_v1", "stick_leads_coaching_may26", 140, 0), ("putter_video_v1", "stick_leads_putter_may26", 120, 0)]


def test_room_plus_two_weak_sets_cover_one_test():
    # 40 a day committed (280 a week) of 350: 70 room = 10 a day, plus 20 from the first weak set = 30.
    s = t._by_post(t._build([t.FITTING_REEL], budget=350, sets=SETS, ads=ADS))["f1"]
    assert s["funding"]["source"] == "move"
    assert s["funding"]["moves"] == ["stick_leads_coaching_may26_set"]
    assert "unused room" in s["funding"]["text"]


def test_short_money_names_what_can_move_and_asks_for_the_rest():
    s = t._by_post(t._build([t.FITTING_REEL], budget=140, sets=SETS[:1], ads=ADS[:1]))["f1"]
    assert s["funding"]["source"] == "extra"
    assert s["funding"]["moves"] == ["stick_leads_coaching_may26_set"]
    assert "R70" in s["funding"]["text"]  # 210 needed, 140 from the weak set
