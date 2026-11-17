"""The week board's _go_live note does not stop the calendar reusing its posts (17 Nov 2026)."""
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import unified_inbox as ui  # noqa: E402
from _lib.board_cache import board_cache  # noqa: E402


class _Index:
    brand_id = "swing-shack"


def test_week_board_record_and_calendar_record_share_one_build(monkeypatch):
    calls = []
    monkeypatch.setattr(ui, "_post_state", lambda record, *, index, now=None: calls.append(1) or {"calendar_id": "c1"})
    record = {"calendar_id": "c1", "status": "scheduled"}
    idx = _Index()
    with board_cache():
        ui.post_state({**record, "_go_live": "2026-11-20"}, index=idx)
        ui.post_state(dict(record), index=idx)
    assert calls == [1]
