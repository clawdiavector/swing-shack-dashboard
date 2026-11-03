"""A post whose day has passed without it being made says so (2026-10-29).

On live, 2 and 3 October still read "Being made" weeks later. Christelle asked
for it to be fixed: a past day with nothing made is missed, not in progress,
and a past plan step that is not done is overdue.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

TODAY = date(2026, 10, 29)


def _entry(state, day, **row):
    from _lib.clean_calendar import post_entry

    return post_entry({"calendar_id": "c", "state": state, "go_live_date": day, "title": "Coaching", **row},
                      "stick", caption="", today=TODAY)


def test_a_past_day_with_nothing_made_is_missed_not_being_made():
    e = _entry("booked", "2026-10-02")
    assert e["missed"] is True
    assert e["making"] is False
    assert e["status"] == "Missed. It was never made."
    assert e["view"] == "approval"
    assert e["actions"] == ["comment"]


def test_today_and_later_are_still_being_made():
    for day in ("2026-10-29", "2026-11-05"):
        e = _entry("drafting", day)
        assert e["making"] is True, day
        assert e["missed"] is False, day


def test_a_ready_or_sent_post_is_never_missed():
    assert _entry("draft_ready", "2026-10-02")["missed"] is False
    assert _entry("posted", "2026-10-02")["missed"] is False


def test_a_past_plan_step_not_done_is_overdue():
    e = _entry("booked", "2026-10-20", plan_item_kind="shoot")
    assert e["view"] == "todo"
    assert e["status"] == "Overdue since Tue 20 Oct"
    assert _entry("booked", "2026-11-06", plan_item_kind="shoot")["status"] == "Due Fri 6 Nov"


def test_missed_posts_are_not_counted_as_waiting_for_a_yes():
    from _lib.clean_calendar import count_views

    entries = [_entry("booked", "2026-10-02"), _entry("draft_ready", "2026-10-30"), _entry("drafting", "2026-11-02")]
    assert count_views(entries)["approval"] == 1
