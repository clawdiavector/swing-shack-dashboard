"""Regression test for the 2026-08-10 nightshift fix: GA4 page aggregation
ER is now session-weighted (sum(ER_i * sessions_i) / sum(sessions_i)),
matching the upstream `fetch_ga4.js` aggregation. Previously the code
computed an arithmetic mean of the row ERs, which understated the
homepage's true ER by 4.1 percentage points on the live swing-shack data
(38.4% reported vs 42.5% actual).

Why this matters: the relative-tone top-pages card (built on 2026-08-10
in commit 2c7ea21) compares each page's ER to the in-list average and
colors it red/yellow/green. If the homepage is reported as 38.4% when it
is actually 42.5%, the card shows the highest-traffic page as "below
average" when it is in fact the most engaged page on the list.

Run:
    .venv/bin/python -m pytest campaign-os/tests/test_v2026_08_10_ga4_session_weighted_er.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "campaign-os"))

from _lib import intelligence  # noqa: E402
from _lib.intelligence import performance_view  # noqa: E402


def _ga4_payload(pages):
    return {
        "updated": "2026-08-10T00:00:00Z",
        "fetched_at": "2026-08-10T00:00:00Z",
        "data_window": "test window",
        "total_sessions": sum(p["sessions"] for p in pages),
        "pages": pages,
        "sources": [],
        "insights": {"recommendations": []},
    }


class _FakeFs(dict):
    """Maps ga4-metrics.json -> payload, everything else -> empty dict."""
    def __init__(self, ga4):
        super().__init__()
        self._ga4 = ga4

    def __call__(self, path):
        if path.endswith("ga4-metrics.json"):
            return self._ga4
        return {}


class TestGa4SessionWeightedEr(unittest.TestCase):
    def _view(self, pages):
        fake = _FakeFs(_ga4_payload(pages))
        with patch.object(intelligence, "_read_json", side_effect=fake):
            return performance_view()["ga4"]["pages"]

    def test_unequal_sessions_uses_session_weighted(self):
        # The homepage appears 3 times with different session counts.
        # Old (arithmetic mean): (80 + 20 + 0) / 3 = 33.33
        # New (session-weighted): (80*100 + 20*50 + 0*25) / (100+50+25) = 9000/175 = 51.43
        pages = [
            {"path": "/", "sessions": 100, "engRate": "80.0%"},
            {"path": "/", "sessions": 50,  "engRate": "20.0%"},
            {"path": "/", "sessions": 25,  "engRate": "0.0%"},
        ]
        out = self._view(pages)
        self.assertEqual(len(out), 1)
        er = out[0]["engagementRate"]
        self.assertAlmostEqual(er, 51.43, places=1,
            msg=f"ER should be ~51.43% (session-weighted), got {er}")

    def test_single_row_path_unchanged(self):
        # Pages with one source row keep the row ER exactly.
        pages = [{"path": "/x/", "sessions": 10, "engRate": "42.5%"}]
        out = self._view(pages)
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0]["engagementRate"], 42.5, places=1)

    def test_zero_sessions_row_does_not_break(self):
        # A row with sessions=0 contributes 0 to the weighted sum and 0
        # to the divisor (since we add 0 to total_sessions).
        pages = [
            {"path": "/", "sessions": 100, "engRate": "60.0%"},
            {"path": "/", "sessions": 0,   "engRate": "99.0%"},
        ]
        out = self._view(pages)
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0]["engagementRate"], 60.0, places=1)

    def test_no_arithmetic_mean_regression(self):
        # Old code computed arithmetic mean which would give 45.0 here.
        # Session-weighted: (90*200 + 0*1) / (200+1) = 18000/201 = 89.55.
        pages = [
            {"path": "/", "sessions": 200, "engRate": "90.0%"},
            {"path": "/", "sessions": 1,   "engRate": "0.0%"},
        ]
        out = self._view(pages)
        er = out[0]["engagementRate"]
        self.assertFalse(abs(er - 45.0) < 0.1,
            msg=f"ER {er} looks like arithmetic mean (45.0), not session-weighted")
        self.assertAlmostEqual(er, 89.55, places=1,
            msg=f"ER should be ~89.55% (session-weighted), got {er}")

    def test_engRate_format_string(self):
        # The engRate field is the display string "X.X%". Downstream
        # HTML parses the leading number, so the format must stay "X.X%".
        pages = [{"path": "/x/", "sessions": 10, "engRate": "42.5%"}]
        out = self._view(pages)
        self.assertEqual(out[0]["engRate"], "42.5%")


if __name__ == "__main__":
    unittest.main()
