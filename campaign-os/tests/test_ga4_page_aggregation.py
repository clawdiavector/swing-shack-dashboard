"""Regression test for GA4 page aggregation in performance_view().

History: fetch_ga4.js historically returned top-10 raw rows from a
(pagePath, sessionSource) GA4 query — so the homepage appeared 5+ times
with different engagement rates. performance_view() now collapses duplicates
by path before returning.

This test monkey-patches intelligence._read_json so each test can inject
the ga4-metrics.json shape it wants to exercise without touching disk.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch

# Repo root + campaign-os/ on path so we can import the intelligence module.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "campaign-os"))

from _lib import intelligence  # noqa: E402
from _lib.intelligence import performance_view  # noqa: E402


def _ga4_payload(pages: list[dict]) -> dict:
    return {
        "updated": "2026-08-08T00:00:00Z",
        "fetched_at": "2026-08-08T00:00:00Z",
        "data_window": "test window",
        "total_sessions": sum(p["sessions"] for p in pages),
        "pages": pages,
        "sources": [],
        "insights": {"recommendations": []},
    }


class _FakeFs(dict):
    """Maps ga4-metrics.json → payload, everything else → empty dict."""
    def __init__(self, ga4):
        super().__init__()
        self._ga4 = ga4

    def __call__(self, path):
        if path.endswith("ga4-metrics.json"):
            return self._ga4
        return {}


class TestGa4PageAggregation(unittest.TestCase):
    def _view(self, pages):
        fake = _FakeFs(_ga4_payload(pages))
        with patch.object(intelligence, "_read_json", side_effect=fake):
            return performance_view()

    def test_collapses_homepage_duplicates(self):
        pages = [
            {"path": "/", "sessions": 100, "engRate": "80.0%"},
            {"path": "/", "sessions": 50,  "engRate": "20.0%"},
            {"path": "/", "sessions": 25,  "engRate": "0.0%"},
            {"path": "/bookings/", "sessions": 40, "engRate": "60.0%"},
            {"path": "/club-fitting/", "sessions": 15, "engRate": "73.0%"},
        ]
        out = self._view(pages)["ga4"]["pages"]
        paths = [p["path"] for p in out]
        self.assertEqual(len(paths), len(set(paths)),
                         f"duplicate paths in response: {paths}")
        self.assertEqual(paths[0], "/")

    def test_session_weighted_engagement_rate(self):
        # Two equal-session rows: arithmetic mean of displayed ER == 50%.
        pages = [
            {"path": "/", "sessions": 100, "engRate": "80.0%"},
            {"path": "/", "sessions": 50,  "engRate": "20.0%"},
        ]
        out = self._view(pages)["ga4"]["pages"]
        self.assertEqual(len(out), 1)
        er = out[0]["engagementRate"]
        self.assertAlmostEqual(er, 50.0, places=1,
            msg=f"ER should be ~50.0% (mean of 80% + 20%), got {er}")

    def test_caps_at_ten_unique_pages(self):
        pages = [{"path": f"/p{i}/", "sessions": 100 - i, "engRate": "50.0%"}
                 for i in range(15)]
        out = self._view(pages)["ga4"]["pages"]
        self.assertLessEqual(len(out), 10)
        self.assertEqual(len(out), 10)

    def test_empty_pages_does_not_break(self):
        out = self._view([])["ga4"]["pages"]
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
