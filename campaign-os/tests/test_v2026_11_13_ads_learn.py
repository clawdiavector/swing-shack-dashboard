"""Learning from results: remember each suggestion, notice when it runs, judge it after 7 days, use what it cost."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_11_13_ad_suggestions as t  # noqa: E402
import test_v2026_11_13_ad_suggestions_types as ty  # noqa: E402
from _lib import ads_learn, ads_suggest  # noqa: E402

DAY = dt.date(2026, 11, 13)


def _doc(posts, cpl=40, brand="stick", learned=None):
    outcomes, media = t._split(posts)
    return ads_suggest.build(brand, outcomes=outcomes, media=media, running={"bodies": [], "post_ids": []},
                             settings={"monthly_budget": 1500, "budget_period": "week"}, figures=t._figures(),
                             brief=t._brief((), cpl), today=DAY, learned=learned)


def _ad(campaign, *, start, spend, leads=0, messages=0, lpv=0, views=0, body=None, ad_id="a1"):
    return {"ad_id": ad_id, "ad_name": "x", "campaign": {"name": campaign},
            "adset": {"start_time": f"{start}T00:00:00+0200"}, "creative": {"body": body},
            "current": {"spend": spend, "leads": leads, "messages": messages, "landing_page_views": lpv,
                        "video_views": views}}


def _logged(posts=(t.FITTING_REEL,), cpl=40):
    return ads_learn.remember([], _doc(list(posts), cpl=cpl), DAY)


def test_each_runnable_suggestion_is_remembered_once_with_its_prediction():
    log = _logged((t.FITTING_REEL, t.RETAIL_IMAGE))
    assert [e["post_id"] for e in log] == ["f1"]  # the animated-still job is not an ad yet
    e = log[0]
    assert e["status"] == "SUGGESTED" and e["campaign_name"] == "stick_leads_fitting_nov26"
    assert e["expected"]["cost_per_result"] == 40 and e["expected"]["unit"] == "lead"
    again = ads_learn.remember(log, _doc([t.FITTING_REEL]), DAY + dt.timedelta(days=1))
    assert len(again) == 1 and again[0]["suggested_on"] == DAY.isoformat()


def test_an_ad_with_the_suggested_campaign_name_is_matched_and_running():
    log = ads_learn.match(_logged(), [_ad("stick_leads_fitting_nov26", start="2026-11-14", spend=60, leads=2)],
                          DAY + dt.timedelta(days=2))
    e = log[0]
    assert e["status"] == "RUNNING" and e["ad_ids"] == ["a1"] and e["started"] == "2026-11-14"
    assert e["actual"] == {"spend": 60, "results": 2, "cost_per_result": 30.0}


def test_an_existing_post_ad_is_matched_by_its_caption_whatever_its_name():
    body = t.FITTING_REEL["_media"]["caption_preview"]
    log = ads_learn.match(_logged(), [_ad("my own name", start="2026-11-14", spend=10, body=body)], DAY)
    assert log[0]["status"] == "RUNNING"


def test_after_seven_days_it_is_judged_against_the_prediction():
    def judged(spend, leads):
        return ads_learn.match(_logged(), [_ad("stick_leads_fitting_nov26", start="2026-11-14", spend=spend,
                                               leads=leads)], dt.date(2026, 11, 21))[0]
    beat, matched, missed, nothing = judged(210, 7), judged(210, 5), judged(210, 3), judged(210, 0)
    assert beat["status"] == "DONE" and beat["verdict"] == "BEAT"        # R30 vs R40
    assert matched["verdict"] == "MATCHED"                                # R42 vs R40
    assert missed["verdict"] == "MISSED"                                  # R70 vs R40
    assert nothing["verdict"] == "NO_RESULT"


def test_a_suggestion_nobody_ran_expires_after_30_days():
    log = ads_learn.match(_logged(), [], DAY + dt.timedelta(days=31))
    assert log[0]["status"] == "EXPIRED"


def test_learned_costs_come_from_finished_tests_per_type_and_subject():
    log = ads_learn.match(_logged(), [_ad("stick_leads_fitting_nov26", start="2026-11-14", spend=200, leads=8)],
                          dt.date(2026, 11, 21))
    learned = ads_learn.learned(log)
    assert learned["by_type"]["lead_form"]["cost_per_result"] == 25.0
    assert learned["by_type"]["lead_form"]["tests"] == 1
    assert learned["by_type_theme"]["lead_form:fitting"]["beat"] == 1


def test_suggestions_use_the_learned_cost_and_say_where_it_came_from():
    log = ads_learn.match(_logged(), [_ad("stick_leads_fitting_nov26", start="2026-11-14", spend=200, leads=8)],
                          dt.date(2026, 11, 21))
    doc = _doc([t.COACH_REEL], cpl=40, learned=ads_learn.learned(log))
    sp = t._by_post(doc)["c1"]["spend"]
    assert "R25" in sp["expected_text"] and "suggested" in sp["expected_text"]


def test_a_type_that_keeps_missing_on_a_subject_loses_to_the_next_best():
    log = []
    for i, start in enumerate(("2026-10-01", "2026-10-10")):
        e = dict(ads_learn.remember([], _doc([ty.DM_SERVICE_REEL], cpl=None), dt.date.fromisoformat(start))[0])
        e["key"] += str(i)
        log.append(e)
    # both fitting messages ads ran and got nothing
    log = ads_learn.match(log, [_ad(log[0]["campaign_name"], start="2026-10-02", spend=210)], dt.date(2026, 11, 1))
    assert all(e["verdict"] == "NO_RESULT" for e in log)
    doc = _doc([ty.DM_SERVICE_REEL], cpl=40, learned=ads_learn.learned(log))
    s = t._by_post(doc)["m1"]
    assert s["ad_type"] == "lead_form"
    assert "track record" in s["type_reason"].lower()


def test_page_shows_past_suggestions_and_how_they_did():
    log = ads_learn.match(_logged(), [_ad("stick_leads_fitting_nov26", start="2026-11-14", spend=210, leads=7)],
                          dt.date(2026, 11, 21))
    doc = _doc([t.COACH_REEL], learned=ads_learn.learned(log))
    doc["log"] = log
    html = ads_suggest.render_html([doc])
    assert "How past suggestions did" in html
    assert "Beat the estimate" in html
