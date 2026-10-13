"""The shape of a plan follows the kind of date."""
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import campaign_plan as cp  # noqa: E402
from _lib.plan_profiles import PROFILES, classify, rows_for  # noqa: E402

TODAY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def kinds(items):
    return [i["kind"] for i in items]


# ── choosing a shape ──

@pytest.mark.parametrize("meta,name,want", [
    ({"shopping_moment": True, "tier": "A-PIN"}, "Black Friday", "retail_push"),
    ({"shopping_moment": True, "tier": "B-PIN"}, "Valentine's Day", "retail_push"),
    ({"shopping_moment": True, "tier": "C-PIN"}, "Singles Day", "light"),
    ({"category": "SA sport", "tier": "B-PIN"}, "Italy v Springboks", "sport_event"),
    ({"tier": "A-PIN"}, "Investec South African Open", "sport_event"),
    ({"duration_days": 77, "tier": "A-PIN", "category": "always-on-arc"}, "Pre-Season / Start Fitted", "season"),
    ({"category": "sustained-arc", "shopping_moment": True, "duration_days": 36}, "New Year New Bag", "season"),
    ({"shopping_moment": True, "tier": "A-PIN", "duration_days": 50}, "Black Friday + Cyber Monday", "retail_push"),
    ({"duration_days": 40, "tier": "B-PIN"}, "Winelands summer golf", "season"),
    ({"duration_days": 14, "tier": "B-PIN"}, "School holidays", "season"),
    ({"category": "sa-cultural", "tier": "B-PIN", "pillars": {"coaching": "x", "fitting": "y"}}, "Women's Day", "service_push"),
    ({"pillars": ["stick-fitting"]}, "Fitting week", "service_push"),
    ({"pillars": {"stick-coaching": "x"}}, "Coaching push", "service_push"),
    ({"tier": "C-PIN"}, "Heritage Day", "light"),
    ({"lead_time_class": "major_retail"}, "Anything", "retail_push"),
    ({"lead_time_class": "content_moment"}, "Anything", "light"),
    ({"tier": "B-PIN"}, "Open day", "sport_event"),   # "open" as a word
    ({"tier": "B-PIN"}, "Openings sale", "standard"),  # but not inside another word
    ({}, "Something else", "standard"),
])
def test_classify(meta, name, want):
    got, reason = classify(meta, name)
    assert got == want and reason


def test_a_shopping_moment_stays_a_retail_push_however_long_it_runs():
    assert classify({"duration_days": 50, "shopping_moment": True, "tier": "A-PIN"}, "Festive")[0] == "retail_push"


def test_every_profile_has_a_label():
    assert all(p["label"] for p in PROFILES.values())


# ── the shapes ──

@pytest.mark.parametrize("profile", list(PROFILES))
def test_every_shape_is_sorted_has_a_post_and_obeys_the_video_rule(profile):
    items = cp.build_items(date(2027, 3, 1), TODAY, profile, duration_days=28)
    assert [i["due"] for i in items] == sorted(i["due"] for i in items)
    assert "post" in kinds(items)
    if "boost" in kinds(items):
        assert any(i["kind"] == "shoot" and i["needs_real_video"] for i in items)


def test_retail_push_starts_early_and_has_a_longer_runway_than_standard():
    ev = date(2026, 11, 27)
    retail = cp.build_items(ev, TODAY, "retail_push")
    standard = cp.build_items(ev, TODAY, "standard")
    assert min(i["days_before_event"] for i in retail) < 0
    assert max(i["days_before_event"] for i in retail) > max(i["days_before_event"] for i in standard)
    review = next(i for i in retail if i["kind"] == "review")
    assert review["days_before_event"] == 21          # house rule: major retail deadline T-21
    assert kinds(retail).count("post") >= 5 and kinds(retail).count("story") >= 3


def test_sport_event_has_a_reaction_post_after_the_day():
    items = cp.build_items(date(2026, 11, 7), TODAY, "sport_event")
    after = [i for i in items if i["days_before_event"] < 0]
    assert any("Reaction" in i["title"] for i in after)
    review = next(i for i in items if i["kind"] == "review")
    assert review["days_before_event"] == 14          # house rule: major sporting event T-14


def test_light_touch_is_short_and_never_boosts():
    items = cp.build_items(date(2027, 3, 1), TODAY, "light")
    assert len(items) <= 6 and "boost" not in kinds(items) and "shoot" not in kinds(items)


def test_season_posts_every_week_for_its_length():
    items = cp.build_items(date(2027, 1, 4), TODAY, "season", duration_days=77)
    weekly = [i for i in items if i["title"].startswith("Week ")]
    assert len(weekly) == 8                                   # capped
    assert [i["days_before_event"] for i in weekly] == [-7 * k for k in range(1, 9)]
    short = cp.build_items(date(2027, 1, 4), TODAY, "season", duration_days=15)
    assert len([i for i in short if i["title"].startswith("Week ")]) == 2
    assert any(i["title"] == "Wrap-up post" for i in short)


def test_a_boost_needs_enough_lead_time_for_its_shape():
    # retail needs 42 days; the same date 30 days out gets no boost, 60 days out does
    assert "boost" not in kinds(cp.build_items(date(2026, 11, 12), TODAY, "retail_push"))
    assert "boost" in kinds(cp.build_items(date(2026, 12, 12), TODAY, "retail_push"))
    assert rows_for("nonsense", 30) == rows_for("standard", 30)


# ── in a stored plan ──

def brief(name="Black Friday", d="2026-12-12", **src):
    return {"brief_id": "brf-test0001", "status": "approved",
            "source_opportunity": {"name": name, "date": d, **src}}


def test_plan_records_its_shape_and_why():
    p = cp.propose_plan("stick", brief(), today=TODAY,
                        event_meta={"shopping_moment": True, "tier": "A-PIN"})["plan"]
    assert p["profile"] == "retail_push" and p["profile_label"] == "Retail push"
    assert "shopping" in p["profile_reason"].lower()


def test_operator_choice_wins_and_start_again_can_reshape():
    first = cp.propose_plan("stick", brief(), today=TODAY,
                            event_meta={"shopping_moment": True, "tier": "A-PIN"})["plan"]
    again = cp.propose_plan("stick", brief(), today=TODAY, force=True, profile="light",
                            event_meta={"shopping_moment": True, "tier": "A-PIN"})["plan"]
    assert again["plan_id"] != first["plan_id"] and again["profile"] == "light"
    assert again["profile_reason"] == "Chosen by you."
    assert len(again["items"]) < len(first["items"])


def test_duration_from_the_brief_is_used_for_a_season():
    p = cp.propose_plan("stick", brief("Pre-Season", "2027-01-04", duration_days=77),
                        today=TODAY, event_meta={"category": "always-on-arc"})["plan"]
    assert p["profile"] == "season"
    assert len([i for i in p["items"] if i["title"].startswith("Week ")]) == 8


# ── the type of an entry, for its icon ──

def test_event_kind_reads_an_entrys_own_fields():
    from _lib.plan_profiles import event_kind
    assert event_kind({"name": "Black Friday", "tier": "A-PIN", "shopping_moment": True,
                       "start": "2027-10-11", "end": "2027-11-29"}) == "retail_push"
    assert event_kind({"name": "Masters Week", "tier": "A-PIN", "category": "golf-moment"}) == "sport_event"
    assert event_kind({"name": "Pre-Season", "category": "always-on-arc",
                       "start": "2027-01-04", "end": "2027-03-21"}) == "season"
    assert event_kind({"name": "Heritage Day", "tier": "C-PIN", "category": "sa-cultural"}) == "light"
    assert event_kind({"title": "Fitting week", "pillars": {"fitting": "x"}}) == "service_push"
    assert event_kind({}) == "standard"
    # a bad date does not break it, and the default lead-time class is not a choice
    assert event_kind({"name": "X", "start": "nope", "end": "2027-01-01",
                       "lead_time_class": "normal_campaign"}) == "standard"


def test_suggestions_and_alerts_carry_a_kind():
    from _lib import calendar_suggestions as cs
    from _lib.calendar_alerts import find_alerts
    out = cs.month_items(
        "stick", "2026-11", [], lambda r: True,
        [{"event_name": "Italy v Springboks", "start_date": "2026-11-07", "event_type": "SA_SPORT",
          "notes": "Rugby. Tier B."}],
        {}, [], TODAY)
    assert out[0]["kind"] == "sport_event"
    a = find_alerts("stick", [{"id": "k", "name": "Heritage Day", "start": "2026-10-20",
                               "tier": "A-PIN", "kind": "light"}], {}, {}, [], TODAY)
    assert a[0]["kind"] == "light"
    b = find_alerts("stick", [{"id": "k", "name": "X", "start": "2026-10-20", "tier": "A-PIN"}],
                    {}, {}, [], TODAY)
    assert b[0]["kind"] == "standard"
