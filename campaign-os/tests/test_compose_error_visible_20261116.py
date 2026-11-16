"""A poster that fails to build must say why (G4 test, 2026-11-16).

Approved Stick and Bag Drop items got a caption and then sat at
compose_post = pending with no note, while the run reported OK.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

from _lib.jobs.layer5 import draft_assets as da  # noqa: E402

ITEM = "calendar_candidate:stick:cal-stick-mom-1"


def test_hard_error_keeps_row_pending_with_a_reason():
    row = {"action": "compose_post", "status": "pending"}
    errors: list[str] = []
    da._note_compose_failure(row, ITEM, "missing asset images/tagline-light.png", errors)
    assert row["status"] == "pending"
    assert row["note"] == "compose: missing asset images/tagline-light.png"
    assert errors == [f"{ITEM}: missing asset images/tagline-light.png"]


def test_soft_error_still_parks_the_row():
    row = {"action": "compose_post", "status": "pending"}
    errors: list[str] = []
    da._note_compose_failure(row, ITEM, "compose-only archetype requires caption draft first", errors)
    assert row["status"] == "skipped"
    assert row["note"] == "compose-only archetype requires caption draft first"
    assert errors == []


def test_long_reason_is_cut_to_fit():
    row = {"action": "compose_post", "status": "pending"}
    errors: list[str] = []
    da._note_compose_failure(row, ITEM, "x" * 900, errors)
    assert len(row["note"]) == 240
    assert len(errors[0]) == 300


def test_run_reports_compose_errors_key():
    # The run adds compose_errors to its result; keep the name stable for ops readers.
    src = Path(da.__file__).read_text()
    assert 'out["compose_errors"]' in src
