"""Catalog layout (Kyle 9 Nov feedback): aligned pictures, readable strip in dark mode."""
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def test_cards_line_up_and_strip_days_are_readable():
    """Kyle 9 Nov: pictures start at the same height across a row; strip day numbers use the ink colour."""
    from _lib import review_pack as rp

    html = rp.render_page({"pack": {"title": "T", "items": []}, "decisions": {}, "comments": [],
                           "uploads": [], "done": [], "staff": False}, token="tok")
    assert "grid-template-rows:subgrid" in html and 'el("div","c-media")' in html
    assert ".day-dot{font:inherit;color:var(--ink)" in html
