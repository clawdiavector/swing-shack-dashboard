"""The Pause button needs the ad id; the brief's _slim used to drop it."""
import datetime as dt

from _lib import ads_brief as ab


def test_brief_top_actions_carry_ad_ids():
    f = {"rule": "open_ended_non_lead", "severity": "medium", "level": "ad", "what": "w",
         "action": "Set a decision date.", "evidence": {}, "status": "DECISION_DATE",
         "ad_id": "555", "ad_name": "Putter ad", "campaign_name": "C"}
    slim = ab._slim(f, "2026-10-08", dt.date(2026, 10, 20))
    assert slim["ad_id"] == "555"
    top = ab.top_actions([slim])
    assert top and top[0]["ad_ids"] == ["555"]
