"""Real prod data (swing-shack, Oct 2026) sat on a ~140/day plateau for two
weeks and then fell to 60-95/day. Against ONE overall median the plateau looked
like a string of spikes. Each day must be compared with its own neighbours, and
the in-progress day (today) must not be pulled at all.
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from _lib import insights_correlator as ic  # noqa: E402
from _lib.jobs.layer1 import ga4_report  # noqa: E402

PROD_SERIES = [140, 144, 168, 141, 117, 133, 141, 120, 136, 139, 141, 106, 141, 151,
               101, 85, 69, 79, 66, 58, 63, 79, 97, 91, 65, 54, 51, 95, 82, 83]


def _days(start: str, counts: list[int]) -> list[dict]:
    d0 = date.fromisoformat(start)
    return [{"date": (d0 + timedelta(days=i)).isoformat(), "sessions": n} for i, n in enumerate(counts)]


def _post(day: str, pid: str = "p") -> dict:
    return {"id": pid, "timestamp": f"{day}T08:00:00+0000", "caption": "c", "permalink": "u", "engagementRate": 3}


class LocalBaselineTests(unittest.TestCase):
    def test_a_high_plateau_then_a_drop_is_not_a_string_of_spikes(self):
        daily = _days("2026-10-06", PROD_SERIES)
        posts = [_post(d["date"], d["date"]) for d in daily]  # a post every day
        out = ic._correlate_posts_with_daily(posts, daily)
        self.assertEqual(out["matches"], [])
        self.assertEqual(out["unmatched_spikes"], [])

    def test_a_real_jump_inside_a_plateau_is_still_found(self):
        counts = [140] * 10 + [260] + [140] * 10
        out = ic._correlate_posts_with_daily([_post("2026-10-11")], _days("2026-10-01", counts))
        self.assertEqual(len(out["matches"]), 1)
        self.assertEqual(out["matches"][0]["ga4_sessions_baseline"], 140)

    def test_a_jump_after_a_level_drop_uses_the_new_level(self):
        counts = [140] * 12 + [60] * 8 + [140] + [60] * 4  # 140 is a jump only vs the local 60s
        daily = _days("2026-10-01", counts)
        out = ic._correlate_posts_with_daily([_post("2026-10-21")], daily)
        self.assertEqual(len(out["matches"]), 1)
        self.assertEqual(out["matches"][0]["ga4_sessions_baseline"], 60)


class DailyPullTests(unittest.TestCase):
    def test_daily_pull_stops_at_yesterday(self):
        seen = {}

        def fake(prop, bearer, body):
            seen.update(body)
            return {"rows": []}

        payload: dict = {}
        with mock.patch.object(ga4_report, "_run_ga4_report", fake):
            ga4_report._add_daily(payload, "123", "tok")
        end = seen["dateRanges"][0]["endDate"]
        self.assertEqual(end, (date.today() - timedelta(days=1)).isoformat())


if __name__ == "__main__":
    unittest.main()
