"""Each day gets a lead category (services, off the rack, accessories, apparel) that rotates,
never the same two days running, with stuck or heavy stock leading first."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import clean_calendar as cc  # noqa: E402
from _lib import daily_target as dt  # noqa: E402
from _lib.stock_pulse import categorise  # noqa: E402


def test_apparel_and_irons_have_their_own_stock_category():
    for name in ("Kingston Pique Polo", "Dale Graphic Tee", "Denis Sport Cap",
                 "Nicholson PB Bunny Graphic Baseball Cap", "Psycho Bunny Samos swim trunk"):
        assert categorise(name) == "apparel", name
    for name in ("Takomo 101U irons", "Srixon ZX5 Iron"):
        assert categorise(name) == "iron", name
    assert categorise("Pride Professional Tees") != "apparel"
    assert categorise("Vice Tour White Sleeve") == "ball"


def test_stock_categories_fold_into_four_groups():
    assert dt.group_of("iron") == dt.group_of("putter") == dt.group_of("driver-wood") == "off_the_rack"
    assert dt.group_of("ball") == dt.group_of("grip") == dt.group_of("bag") == "accessories"
    assert dt.group_of("other") == "accessories"
    assert dt.group_of("apparel") == "apparel"
    assert set(dt.GROUP_LABELS) == {"services", "off_the_rack", "accessories", "apparel"}


def test_split_counts_add_up_to_the_target():
    assert dt.split_counts(20) == [8, 6, 3, 3]
    assert sum(dt.split_counts(50)) == 50
    assert dt.split_counts(50)[0] == 20


def test_every_group_leads_once_in_four_days_and_never_twice_running():
    boost = {"apparel": 5, "accessories": 2}
    start = date(2026, 11, 2)
    leads = [dt.day_order(start + timedelta(days=i), boost)[0] for i in range(12)]
    for i in range(1, len(leads)):
        assert leads[i] != leads[i - 1], leads
    # aligned four-day blocks contain each group once
    first = next(i for i in range(4) if (start + timedelta(days=i)).toordinal() % 4 == 0)
    block = leads[first:first + 4]
    assert sorted(block) == sorted(dt.GROUP_LABELS)
    # the most stuck or heavy stock leads first in the block
    assert block[0] == "apparel" and block[1] == "accessories"


def test_day_order_is_the_same_whatever_month_is_viewed():
    boost = {"off_the_rack": 3}
    d = date(2026, 11, 30)
    assert dt.day_order(d, boost) == dt.day_order(d, dict(boost))
    assert sorted(dt.day_order(d, boost)) == sorted(dt.GROUP_LABELS)


def test_month_view_carries_the_lead_and_what_to_push(monkeypatch):
    monkeypatch.setattr(cc, "post_rows", lambda brand, month: [])
    monkeypatch.setattr(cc, "comments_by_key", lambda brand: {})
    stock = [{"name": "Kingston Pique Polo", "category": "apparel", "status": "stuck"},
             {"name": "Mens Classic Polo", "category": "apparel", "status": "heavy"},
             {"name": "Vice Tour White Sleeve", "category": "ball", "status": "heavy"}]
    monkeypatch.setattr(dt, "_stock_candidates", lambda brand: stock)
    view = cc.month_view("stick", "2026-11", [], [])
    days = view["targets"]
    leads = {d: t["lead"]["order"][0]["group"] for d, t in days.items()}
    apparel_day = next(d for d, g in leads.items() if g == "apparel")
    lead = days[apparel_day]["lead"]
    assert [g["count"] for g in lead["order"]] == [8, 6, 3, 3]
    assert lead["order"][0]["label"] == "Apparel"
    assert lead["push"] == ["Kingston Pique Polo", "Mens Classic Polo"]
    services_day = next(d for d, g in leads.items() if g == "services")
    assert "Club fitting" in days[services_day]["lead"]["push"]
