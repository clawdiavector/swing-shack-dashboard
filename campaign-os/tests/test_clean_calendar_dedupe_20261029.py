"""An approved idea shows once on the clean calendar (2026-10-29).

Approving a suggestion keeps the suggestion's own record and books a calendar
event beside it, both approved, same title and day. The clean calendar is read
by Herman cold, so one post must be one entry: keep the one furthest along.
"""
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _row(cid, state, title="Italy v Springboks", day="2026-11-07"):
    return ({"calendar_id": cid, "state": state, "title": title, "go_live_date": day}, None)


def test_the_same_post_twice_shows_once_keeping_the_one_furthest_along():
    from _lib.clean_calendar import dedupe_rows

    rows = [_row("a", "booked"), _row("b", "draft_ready"), _row("c", "booked", title="Other")]
    kept = [r["calendar_id"] for r, _ in dedupe_rows(rows)]
    assert kept == ["b", "c"]


def test_same_title_on_different_days_are_different_posts():
    from _lib.clean_calendar import dedupe_rows

    rows = [_row("a", "scheduled", day="2026-11-07"), _row("b", "scheduled", day="2026-11-14")]
    assert len(dedupe_rows(rows)) == 2


def test_titles_match_whatever_the_case_or_spacing():
    from _lib.clean_calendar import dedupe_rows

    rows = [_row("a", "booked", title="Italy v Springboks"), _row("b", "booked", title=" italy V springboks ")]
    assert [r["calendar_id"] for r, _ in dedupe_rows(rows)] == ["a"]
