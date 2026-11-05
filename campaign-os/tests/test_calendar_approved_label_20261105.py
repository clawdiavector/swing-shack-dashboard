"""Herman's share page uses the same name as the calendar box: Approved, not Scheduled (5 Nov 2026)."""

from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import clean_calendar as cc  # noqa: E402


def test_share_page_names_the_approved_list_approved():
    labels = {view_id: label for view_id, label, _hint in cc._VIEWS}
    assert labels["scheduled"] == "Approved"
    assert "Scheduled" not in labels.values()
