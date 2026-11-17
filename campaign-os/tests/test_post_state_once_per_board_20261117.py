"""post_state is worked out once per post inside a read-only board build (17 Nov 2026).

The calendar month built the same posts two or three times (~6 s of ~7 s on live).
Each caller still gets its own copy, and outside a board nothing is shared.
"""
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import unified_inbox as ui  # noqa: E402
from _lib.board_cache import board_cache  # noqa: E402

RECORD = {"calendar_id": "c1", "status": "scheduled", "go_live_date": "2026-11-20"}


def _counting(monkeypatch):
    calls = []

    def fake(record, *, index, now=None):
        calls.append(record["calendar_id"])
        return {"calendar_id": record["calendar_id"], "flags": ["a"], "receipts": [{"x": 1}]}

    monkeypatch.setattr(ui, "_post_state", fake)
    return calls


def test_once_per_post_inside_a_board(monkeypatch):
    calls = _counting(monkeypatch)
    other, idx = _Index(), _Index()
    with board_cache():
        a = ui.post_state(dict(RECORD), index=other)
        ui.post_state(dict(RECORD), index=idx)
        ui.post_state(dict(RECORD), index=idx)
        ui.post_state({**RECORD, "calendar_id": "c2"}, index=idx)
    assert calls == ["c1", "c1", "c2"]  # a different index object is a different build
    assert a["flags"] == ["a"]


def test_each_caller_gets_its_own_copy(monkeypatch):
    _counting(monkeypatch)
    idx = _Index()
    with board_cache():
        first = ui.post_state(dict(RECORD), index=idx)
        first["flags"].append("changed")
        first["receipts"][0]["x"] = 99
        second = ui.post_state(dict(RECORD), index=idx)
    assert second["flags"] == ["a"]
    assert second["receipts"] == [{"x": 1}]


def test_a_changed_record_is_worked_out_again(monkeypatch):
    calls = _counting(monkeypatch)
    idx = _Index()
    with board_cache():
        ui.post_state(dict(RECORD), index=idx)
        ui.post_state({**RECORD, "status": "posted"}, index=idx)
    assert calls == ["c1", "c1"]


def test_outside_a_board_it_is_fresh_every_time(monkeypatch):
    calls = _counting(monkeypatch)
    idx = _Index()
    ui.post_state(dict(RECORD), index=idx)
    ui.post_state(dict(RECORD), index=idx)
    assert calls == ["c1", "c1"]


class _Index:
    brand_id = "swing-shack"
