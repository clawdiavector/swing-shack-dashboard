"""resolve_template_id does not reload the calendar for the post it was given (17 Nov 2026).

It used to call _moment_context and select_archetype without the record, and both
reloaded the whole calendar to find it: twice per post, ~6 s of the calendar month on
live. The record is handed over only when the inbox id points at that same record.
"""
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import archetypes as ar  # noqa: E402
from _lib import marketing_calendar as mc  # noqa: E402
from _lib import template_catalog as tc  # noqa: E402

BRAND = "swing-shack"
RECORD = {"calendar_id": "c1", "post_type": "photo", "pillars": ["coaching"], "subject": "Lessons"}


def _loads(monkeypatch, records):
    calls = []
    monkeypatch.setattr(mc, "canonical_records", lambda b, status_filter=None: calls.append(b) or [dict(r) for r in records])
    return calls


def test_own_post_needs_no_calendar_load(monkeypatch):
    calls = _loads(monkeypatch, [RECORD])
    monkeypatch.setattr(ar, "select_archetype", lambda b, iid, record=None: {"id": "t-photo" if record else "t-lookup"})
    tid = tc.resolve_template_id(BRAND, record=RECORD, source_inbox_item_id=f"calendar_candidate:{BRAND}:c1")
    assert tid == "t-photo"
    assert calls == []


def test_another_posts_id_is_still_looked_up(monkeypatch):
    calls = _loads(monkeypatch, [RECORD, {**RECORD, "calendar_id": "c2", "template_id": "pinned"}])
    tid = tc.resolve_template_id(BRAND, record=RECORD, source_inbox_item_id=f"calendar_candidate:{BRAND}:c2")
    assert tid == "pinned"
    assert calls == [BRAND]


def test_same_answer_with_and_without_the_record(monkeypatch):
    _loads(monkeypatch, [RECORD])
    doc = {"selection": {"default": "a", "rules": [{"when": {"pillar_in": ["coaching"]}, "use": "b"}]},
           "archetypes": [{"id": "a"}, {"id": "b"}]}
    monkeypatch.setattr(ar, "load_archetypes_doc", lambda b: doc)
    iid = f"calendar_candidate:{BRAND}:c1"
    looked_up = str(ar.select_archetype(BRAND, iid).get("id"))
    assert tc.resolve_template_id(BRAND, record=RECORD, source_inbox_item_id=iid) == looked_up


def test_own_moment_match_is_exact():
    assert tc._is_own_moment(BRAND, f"calendar_candidate:{BRAND}:c1", RECORD)
    assert not tc._is_own_moment(BRAND, f"calendar_candidate:stick:c1", RECORD)
    assert not tc._is_own_moment(BRAND, f"calendar_candidate:{BRAND}:c10", RECORD)
    assert not tc._is_own_moment(BRAND, "draft_asset:x:c1", RECORD)
    assert not tc._is_own_moment(BRAND, f"calendar_candidate:{BRAND}:c1", None)
