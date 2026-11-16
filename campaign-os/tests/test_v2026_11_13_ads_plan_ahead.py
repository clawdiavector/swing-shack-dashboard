"""Ads a week ahead: planned posts to boost when they land, plan boost steps, and stock with no post planned."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_11_13_ad_suggestions as t  # noqa: E402
from _lib import ads_plan, ads_suggest  # noqa: E402

DAY = dt.date(2026, 11, 13)


def _post(key, date, fmt, caption, plan_id=None, title=None):
    return {"key": key, "date": date, "format": fmt, "caption": caption, "title": title or caption[:30],
            "plan_id": plan_id, "state": "approved"}


POSTS = [
    _post("c1", "2026-11-16", "reel", "New Psycho Bunny polos just landed at Stick. DM us for sizes."),
    _post("c2", "2026-11-17", "reel", "Book a fitting at Stick before the season starts."),
    _post("c3", "2026-11-18", "story", "Book a fitting at Stick."),
    _post("c4", "2026-11-19", "feed", "Vessel bags available at Stick."),
    _post("c5", "2026-11-19", "feed", "Book a lesson with our coach."),
    _post("c6", "2026-11-30", "reel", "Book a fitting, last call."),
    _post("c7", "2026-11-12", "reel", "Book a fitting, yesterday."),
]
STEPS = [{"key": "s1", "plan_id": "pln-1", "item_id": "i9", "title": "Boost the fitting reel", "step": "boost",
          "date": "2026-11-18", "event_name": "Summer fitting week"},
         {"key": "s2", "plan_id": "pln-1", "item_id": "i8", "title": "Shoot", "step": "shoot",
          "date": "2026-11-15", "event_name": "Summer fitting week"}]
CAMPAIGNS = [{"campaign_id": "bf26", "name": "Black Friday", "start_date": "2026-11-23", "end_date": "2026-11-30"},
             {"campaign_id": "summer", "name": "Summer fitting week", "start_date": "2026-11-14",
              "end_date": "2026-11-21"}]
STOCK = [{"name": "Psycho Bunny polo", "status": "new", "qty": 24},
         {"name": "Sausage putter", "status": "back", "qty": 6},
         {"name": "Old tees", "status": "steady", "qty": 100}]


def _plan(**kw):
    args = dict(posts=POSTS, boost_steps=STEPS, campaigns=CAMPAIGNS, stock=STOCK,
                settings={"monthly_budget": 1500, "budget_period": "week"}, figures=t._figures(),
                brief=t._brief((), 40), learned=None, today=DAY)
    args.update(kw)
    return ads_plan.upcoming("stick", **args)


def _by(out):
    return {i["key"]: i for i in out["items"]}


def test_only_the_next_seven_days_and_only_reels_with_an_offer_become_ads():
    items = _by(_plan())
    assert {"c1", "c2"} <= set(items)
    assert not {"c3", "c5", "c6", "c7"} & set(items)  # story, service still, past the week, already past


def test_a_product_photo_coming_up_becomes_an_animated_still_job():
    assert _by(_plan())["c4"]["ad_type"] == "animated_still"


def test_each_coming_post_gets_a_type_a_start_day_after_it_lands_and_money_to_set_aside():
    c1, c2 = _by(_plan())["c1"], _by(_plan())["c2"]
    assert c1["ad_type"] == "messages" and c2["ad_type"] == "lead_form"
    assert c1["start"] == "2026-11-17"
    assert c2["spend"]["total"] == c2["spend"]["daily"] * 7
    assert "set aside" in c2["money"].lower()


def test_campaign_and_plan_context_is_named():
    c2 = _by(_plan())["c2"]
    assert "Summer fitting week" in c2["why"]
    boost = _by(_plan())["s1"]
    assert boost["source"] == "plan_boost" and "Summer fitting week" in boost["why"]


def test_new_or_back_stock_with_no_post_planned_is_flagged_to_film():
    gaps = _plan()["stock_gaps"]
    names = [g["name"] for g in gaps]
    assert "Sausage putter" in names
    assert "Psycho Bunny polo" not in names  # c1 already covers it
    assert "Old tees" not in names


def test_page_shows_coming_up():
    doc = t._build([t.FITTING_REEL])
    doc["ahead"] = _plan()
    html = ads_suggest.render_html([doc])
    assert "Coming up" in html and "Sausage putter" in html
