"""The daily ads brief scores "is this ad still running?" as of the day it is run for.

Until 2026-11-02 the job passed ``today`` to the fetch but not to scoring, so
scoring used the wall clock. From 1 Nov an ad set ending 31 Oct counted as
finished in a run for 8 Oct, and its findings were reported as resolved.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import test_v2026_10_08_ads_brain as fx  # noqa: E402
import test_v2026_10_08_ads_brief as brief_tests  # noqa: E402


class ScoresAsOfToday(brief_tests._JobCase):
    def _open_rules(self):
        return {f["rule"] for f in self.read("latest.json")["open"]}

    def test_an_ad_ending_after_today_is_still_running(self):
        # Ends 20 Oct: after the run's day (8 Oct), before any real date this test runs on.
        ending = dict(fx.STICK, ads=[
            dict(s, adset=dict(s["adset"], end_time="2026-10-20T23:59:00+0200")) if s["id"] == "rush" else s
            for s in fx.STICK["ads"]])
        self.run_job(fx.STICK, brief_tests.DAY)
        baseline = self._open_rules()
        self.run_job(ending, brief_tests.DAY)
        self.assertIn("home_page_destination", baseline)
        self.assertIn("home_page_destination", self._open_rules())
        # Only the "no end date" finding clears; nothing else reads the ad as finished.
        self.assertEqual([f["rule"] for f in self.read("latest.json")["resolved"]], ["open_ended_non_lead"])


if __name__ == "__main__":
    unittest.main()
