"""Daily GA4 sessions + the post-to-traffic match built on them.

The Results > What worked Traffic tab was always empty because the correlator
returned matches=[] ("GA4 daily time-series not yet wired"). These tests pin:
  1. ga4_report parses a GA4 `date` report into a sorted daily series.
  2. The correlator turns that series + IG post timestamps into matches and
     unmatched spikes, and says nothing when there is no evidence.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from _lib import insights_correlator as ic  # noqa: E402
from _lib.jobs.layer1 import ga4_report  # noqa: E402


def _days(start: str, counts: list[int]) -> list[dict]:
    from datetime import date, timedelta

    d0 = date.fromisoformat(start)
    return [{"date": (d0 + timedelta(days=i)).isoformat(), "sessions": n} for i, n in enumerate(counts)]


def _post(ts: str, pid="p1", er=3.0) -> dict:
    return {
        "id": pid,
        "timestamp": ts,
        "caption": "A caption",
        "permalink": f"https://instagram.com/p/{pid}/",
        "engagementRate": er,
    }


class ParseDailyTests(unittest.TestCase):
    def test_parses_and_sorts_ga4_date_rows(self):
        report = {
            "rows": [
                {"dimensionValues": [{"value": "20261103"}], "metricValues": [{"value": "120"}]},
                {"dimensionValues": [{"value": "20261101"}], "metricValues": [{"value": "40"}]},
            ]
        }
        self.assertEqual(
            ga4_report._parse_daily(report),
            [{"date": "2026-11-01", "sessions": 40}, {"date": "2026-11-03", "sessions": 120}],
        )

    def test_empty_report_gives_empty_list(self):
        self.assertEqual(ga4_report._parse_daily({}), [])


class CorrelateTests(unittest.TestCase):
    def test_post_followed_by_a_spike_is_a_match(self):
        daily = _days("2026-10-01", [40] * 14 + [120] + [40] * 15)  # spike on 15 Oct
        out = ic._correlate_posts_with_daily([_post("2026-10-15T08:00:00+0000")], daily)
        self.assertEqual(len(out["matches"]), 1)
        m = out["matches"][0]
        self.assertEqual(m["date"], "2026-10-15")
        self.assertEqual(m["ga4_sessions_on_day"], 120)
        self.assertEqual(m["ga4_sessions_baseline"], 40)
        self.assertEqual(m["lift_pct"], 200.0)
        self.assertEqual(m["verdict"], "likely content drove spike")
        self.assertEqual(out["unmatched_spikes"], [])

    def test_spike_the_day_after_the_post_still_counts(self):
        daily = _days("2026-10-01", [40] * 15 + [110] + [40] * 14)  # spike 16 Oct
        out = ic._correlate_posts_with_daily([_post("2026-10-15T08:00:00+0000")], daily)
        self.assertEqual(out["matches"][0]["ga4_sessions_on_day"], 110)

    def test_spike_with_no_post_is_unmatched(self):
        daily = _days("2026-10-01", [40] * 14 + [120] + [40] * 15)
        out = ic._correlate_posts_with_daily([_post("2026-10-03T08:00:00+0000")], daily)
        self.assertEqual(out["matches"], [])
        self.assertEqual(len(out["unmatched_spikes"]), 1)
        self.assertEqual(out["unmatched_spikes"][0]["date"], "2026-10-15")
        self.assertEqual(out["unmatched_spikes"][0]["verdict"], "spike not explained by content")

    def test_ordinary_days_are_no_match(self):
        daily = _days("2026-10-01", [40, 44, 38, 41, 45, 39, 42] * 4)
        out = ic._correlate_posts_with_daily([_post("2026-10-10T08:00:00+0000")], daily)
        self.assertEqual(out["matches"], [])
        self.assertEqual(out["unmatched_spikes"], [])

    def test_two_posts_in_the_window_cap_confidence_at_medium(self):
        daily = _days("2026-10-01", [40] * 14 + [160] + [40] * 15)
        posts = [_post("2026-10-15T07:00:00+0000", "a"), _post("2026-10-15T16:00:00+0000", "b")]
        out = ic._correlate_posts_with_daily(posts, daily)
        self.assertTrue(out["matches"])
        self.assertNotIn("high", {m["confidence"] for m in out["matches"]})

    def test_one_clear_post_with_a_big_lift_is_high_confidence(self):
        daily = _days("2026-10-01", [40] * 14 + [160] + [40] * 15)
        out = ic._correlate_posts_with_daily([_post("2026-10-15T08:00:00+0000")], daily)
        self.assertEqual(out["matches"][0]["confidence"], "high")

    def test_too_little_data_says_so_and_claims_nothing(self):
        out = ic._correlate_posts_with_daily([_post("2026-10-03T08:00:00+0000")], _days("2026-10-01", [40, 90, 40]))
        self.assertEqual(out["matches"], [])
        self.assertEqual(out["unmatched_spikes"], [])
        self.assertIn("days", out["reason"])

    def test_tiny_numbers_are_not_a_spike(self):
        daily = _days("2026-10-01", [2] * 14 + [6] + [2] * 15)  # +200% but only 4 extra visits
        out = ic._correlate_posts_with_daily([_post("2026-10-15T08:00:00+0000")], daily)
        self.assertEqual(out["matches"], [])

    def test_post_late_in_the_evening_utc_lands_on_the_next_sast_day(self):
        # 22:30 UTC on the 14th is 00:30 SAST on the 15th.
        daily = _days("2026-10-01", [40] * 14 + [120] + [40] * 15)
        out = ic._correlate_posts_with_daily([_post("2026-10-14T22:30:00+0000")], daily)
        self.assertEqual(out["matches"][0]["date"], "2026-10-15")


if __name__ == "__main__":
    unittest.main()
