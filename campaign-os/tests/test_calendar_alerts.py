"""Approved dates that are close and not ready."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib.calendar_alerts import find_alerts  # noqa: E402

TODAY = date(2026, 10, 13)


def ev(key, name, start, tier="A-PIN"):
    return {"id": key, "name": name, "start": start, "tier": tier}


def run(events, briefs=None, plans=None, content=()):
    return find_alerts("stick", events, briefs or {}, plans or {}, content, TODAY)


def test_close_event_with_no_plan_screams():
    a = run([ev("x", "Heritage Day", "2026-10-20")])
    assert len(a) == 1 and a[0]["level"] == "scream" and a[0]["state"] == "no_plan"
    assert a[0]["days"] == 7 and "in 7 days" in a[0]["message"] and "has no plan" in a[0]["message"]


def test_further_out_only_warns_and_far_out_is_quiet():
    assert run([ev("x", "Masters", "2026-11-05")])[0]["level"] == "warn"      # 23 days, A
    assert run([ev("x", "Masters", "2026-12-25")]) == []                       # 73 days


def test_b_tier_has_shorter_runway_and_c_is_never_flagged():
    assert run([ev("x", "Father's Day", "2026-11-03", "B-PIN")]) [0]["level"] == "warn"   # 21 days
    assert run([ev("x", "Father's Day", "2026-11-20", "B-PIN")]) == []                    # 38 days
    assert run([ev("x", "Goodwill", "2026-10-14", "C-PIN")]) == []


def test_untiered_counts_as_b():
    a = run([{"event_key": "k", "name": "Open day", "start": "2026-10-20", "tier": None}])
    assert a and a[0]["tier"] == "B-PIN" and a[0]["level"] == "scream"


def test_plan_states():
    briefs = {"x": "brf-1"}
    draft = {"brf-1": {"plan_id": "p", "status": "proposed"}}
    approved = {"brf-1": {"plan_id": "p", "status": "approved"}}
    placed = {"brf-1": {"plan_id": "p", "status": "approved", "placed_at": "now"}}
    e = [ev("x", "Heritage Day", "2026-10-20")]
    assert run(e, briefs, draft)[0]["state"] == "plan_draft"
    assert run(e, briefs, approved)[0]["state"] == "plan_approved"
    assert run(e, briefs, placed) == []
    assert run(e, briefs)[0]["state"] == "no_plan"  # brief but no plan yet


def test_content_already_booked_in_the_run_up_covers_it():
    e = [ev("x", "Heritage Day", "2026-10-20")]
    assert run(e, content=["2026-10-15"]) == []
    assert len(run(e, content=["2026-09-01"])) == 1


def test_past_events_and_repeats_are_dropped_and_order_is_urgency():
    out = run([
        ev("a", "Past", "2026-10-01"),
        ev("b", "Later", "2026-11-05"),
        ev("c", "Sooner", "2026-10-15"),
        ev("d", "Sooner", "2026-10-15"),
    ])
    assert [a["name"] for a in out] == ["Sooner", "Later"]


def test_today_and_tomorrow_wording():
    assert "is today" in run([ev("x", "Big day", "2026-10-13")])[0]["message"]
    assert "is tomorrow" in run([ev("x", "Big day", "2026-10-14")])[0]["message"]
