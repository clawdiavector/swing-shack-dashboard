"""After an awareness ad has run a few days, the next leads or messages ad is aimed at the people who watched it."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_11_13_ad_suggestions as t  # noqa: E402
import test_v2026_11_13_ad_suggestions_types as ty  # noqa: E402
import test_v2026_11_13_ads_learn as lt  # noqa: E402
from _lib import ads_learn, ads_suggest  # noqa: E402


def _awareness_log(start, today):
    log = ads_learn.remember([], lt._doc([ty.STAR_REEL] + ty.AVERAGE), dt.date(2026, 11, 1))
    assert log[0]["ad_type"] == "awareness"
    return ads_learn.match(log, [lt._ad(log[0]["campaign_name"], start=start, spend=90, views=800)], today)


def _with(audiences):
    outcomes, media = t._split([t.FITTING_REEL, t.COACH_REEL])
    return ads_suggest.build("stick", outcomes=outcomes, media=media, running=None,
                             settings={"monthly_budget": 1500, "budget_period": "week"}, figures=t._figures(),
                             brief=t._brief((), 40), today=lt.DAY, audiences=audiences)


def test_a_watched_audience_is_ready_after_three_days_and_for_thirty():
    assert ads_learn.audiences(_awareness_log("2026-11-02", lt.DAY), lt.DAY)[0]["name"].endswith("_watched50")
    assert ads_learn.audiences(_awareness_log("2026-11-12", lt.DAY), lt.DAY) == []
    assert ads_learn.audiences(_awareness_log("2026-10-01", lt.DAY), lt.DAY) == []


def test_the_top_offer_ad_is_aimed_at_the_watched_audience_and_says_so():
    aud = ads_learn.audiences(_awareness_log("2026-11-02", lt.DAY), lt.DAY)
    doc = _with(aud)
    first, second = doc["suggestions"][0], doc["suggestions"][1]
    assert first["audience"] == aud[0]["name"]
    rows = dict(next(sec for sec in first["setup"] if sec["title"] == "Ad set")["rows"])
    assert aud[0]["name"] in rows["Audience"]
    assert "watched" in first["type_reason"].lower()
    assert any("100" in c for c in first["checks"])
    assert second.get("audience") is None


def test_no_awareness_ad_no_follow_up():
    assert all(s.get("audience") is None for s in _with([])["suggestions"])
