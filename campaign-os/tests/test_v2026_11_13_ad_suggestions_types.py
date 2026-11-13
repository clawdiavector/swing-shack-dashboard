"""Ad suggestions pick the ad type per post (leads, messages, traffic, awareness), say why, and name the others."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_11_13_ad_suggestions as t  # noqa: E402
from _lib import ads_suggest  # noqa: E402

WEBSITE_REEL = t._post("w1", "Driver fitting at Swing Shack. Book online through the link in bio.")
DM_SERVICE_REEL = t._post("m1", "Not sure your irons suit you? DM us and we will set up a fitting.")
STAR_REEL = t._post("st1", "Sunrise session. The sound of a pure strike.", reach=4000, score=200, saves=60, shares=40)
AVERAGE = [t._post(f"av{i}", "Range day at the club.", reach=500, score=20) for i in range(4)]


def _setup_rows(s, title):
    return dict(next(sec for sec in s["setup"] if sec["title"] == title)["rows"])


def test_a_post_that_points_to_the_website_becomes_a_traffic_ad():
    s = t._by_post(t._build([WEBSITE_REEL], brand="swing-shack"))["w1"]
    assert s["ad_type"] == "traffic"
    assert s["objective"] == "OUTCOME_TRAFFIC"
    assert s["names"]["campaign"].startswith("ss_traffic_fitting_")
    adset = _setup_rows(s, "Ad set")
    assert adset["Conversion location"] == "Website"
    assert "landing page views" in adset["Performance goal"].lower()
    ad = _setup_rows(s, "Ad")
    assert ad["Website URL"] == s["landing_url"]
    assert ad["Website URL"].startswith("https://swingshack.co.za/")
    assert any("landing page" in c.lower() for c in s["checks"])


def test_a_service_post_that_asks_for_a_dm_becomes_a_messages_ad():
    s = t._by_post(t._build([DM_SERVICE_REEL]))["m1"]
    assert s["ad_type"] == "messages"
    assert s["theme"] == "fitting"


def test_a_standout_reel_with_nothing_to_sell_becomes_an_awareness_ad_that_builds_an_audience():
    out = t._build([STAR_REEL] + AVERAGE)
    s = t._by_post(out)["st1"]
    assert s["ad_type"] == "awareness"
    assert s["objective"] == "OUTCOME_AWARENESS"
    assert "thruplay" in _setup_rows(s, "Ad set")["Performance goal"].lower()
    follow = repr(s["setup"]).lower()
    assert "custom audience" in follow and "watched" in follow
    # the average no-offer reels stay organic
    assert not any(p.startswith("av") for p in t._by_post(out))


def test_every_runnable_suggestion_says_why_this_type_and_why_not_the_others():
    out = t._build([t.FITTING_REEL, WEBSITE_REEL, DM_SERVICE_REEL, STAR_REEL] + AVERAGE)
    kinds = set()
    for s in out["suggestions"]:
        if s["ad_type"] == "animated_still":
            continue
        kinds.add(s["ad_type"])
        assert s["type_reason"]
        alts = {a["ad_type"] for a in s["alternatives"]}
        assert s["ad_type"] not in alts
        assert alts <= set(ads_suggest.AD_TYPES)
        assert all(a["why_not"] for a in s["alternatives"])
    assert len(kinds) >= 2


def test_known_cost_per_chat_and_per_visit_give_expected_results():
    outcomes, media = t._split([t._post("r2", "New in: Vessel bags, available at Stick. DM us."), WEBSITE_REEL])
    brief = {"numbers_7d": {"current": {"cost_per_lead": None}, "ads": [
        {"ad_name": "bags_video_v1", "campaign_name": "stick_messages_bags_oct26", "spend": 100, "leads": 0,
         "messages": 10, "landing_page_views": 0},
        {"ad_name": "fit_video_v1", "campaign_name": "stick_traffic_fitting_oct26", "spend": 100, "leads": 0,
         "messages": 0, "landing_page_views": 50}]}}
    out = ads_suggest.build("stick", outcomes=outcomes, media=media, running={"bodies": [], "post_ids": []},
                            settings={"monthly_budget": 1500, "budget_period": "week"}, figures=t._figures(),
                            brief=brief, today=dt.date(2026, 11, 13))
    by = t._by_post(out)
    assert "chat" in by["r2"]["spend"]["expected_text"] and by["r2"]["spend"]["expected_results"]
    assert "visit" in by["w1"]["spend"]["expected_text"] and by["w1"]["spend"]["expected_results"]


def test_page_shows_why_this_type_and_the_other_types():
    out = t._build([WEBSITE_REEL], brand="swing-shack")
    html = ads_suggest.render_html([out])
    assert "Why this type" in html
    assert "Other types" in html
