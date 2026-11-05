"""The campaign picker shows when the campaign's posts run, not the plan's anchor date.

Audit 3 Nov 2026: "One campaign: Black Friday + Cyber Monday (Mon 12 Oct)" while its
posts run 13 to 30 Nov.
"""

from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import clean_calendar as cc  # noqa: E402


def _plan(items, event_date="2026-10-12"):
    return {"plan_id": "pln-bf", "event_name": "Black Friday + Cyber Monday", "event_date": event_date,
            "status": "approved", "items": items}


def test_when_spans_the_first_to_last_post_or_story():
    plan = _plan([
        {"kind": "shoot", "due": "2026-10-25", "status": "done"},
        {"kind": "post", "due": "2026-11-13", "status": "todo"},
        {"kind": "story", "due": "2026-11-30", "status": "todo"},
        {"kind": "post", "due": "2026-11-20", "status": "todo"},
    ])
    assert cc.campaign_list([plan])[0]["when"] == "Fri 13 Nov to Mon 30 Nov"


def test_removed_steps_do_not_stretch_the_span():
    plan = _plan([
        {"kind": "post", "due": "2026-11-13", "status": "todo"},
        {"kind": "post", "due": "2026-12-20", "status": "removed"},
    ])
    assert cc.campaign_list([plan])[0]["when"] == "Fri 13 Nov"


def test_falls_back_to_the_event_date_without_posts():
    plan = _plan([{"kind": "decide", "due": "2026-09-28", "status": "done"}], event_date="2026-11-27")
    assert cc.campaign_list([plan])[0]["when"] == "Fri 27 Nov"
