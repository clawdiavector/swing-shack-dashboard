"""Weekly report: 'changes made to the ads this week' is a short summary by kind plus the latest few,
not the last twelve log lines (which hid the guard's pauses and the campaign renames)."""
from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import weekly_report_v3 as wr  # noqa: E402

LIVE = {"paid_media_v24": {"data_status": "LIVE", "per_campaign": []}}
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def e(kind, name, **kw):
    return dict({"kind": kind, "ad_name": name, "at": NOW, "before": "a", "after": "b"}, **kw)


CHANGES = ([e("rename_campaign", f"c{i}") for i in range(6)] + [e("rename_adset", f"s{i}") for i in range(6)]
           + [e("rename_ad", f"a{i}") for i in range(6)]
           + [e("pause_adset", "Local Golfers", by="budget guard"), e("pause_adset", "Dave Shafts", by="budget guard")]
           + [e("set_end_date", "Welcome David"), e("set_adset_budget", "FitFacts", before=35.0, after=37.0, undone_at=NOW)])


def extras():
    return {"tracking": None, "budget": None, "guard_on": False, "paused_now": 0, "changes": CHANGES}


class Summary(unittest.TestCase):
    def test_counts_by_kind_in_one_line_each(self):
        d = wr._ads_extras_lines(extras())
        s = " | ".join(d["changes_summary"])
        self.assertIn("18 renames (6 campaigns, 6 ad sets, 6 ads)", s)
        self.assertIn("2 ad sets paused by the hard stop", s)
        self.assertIn("1 end date set", s)
        self.assertIn("1 daily budget change (1 undone)", s)

    def test_only_the_latest_few_are_listed(self):
        d = wr._ads_extras_lines(extras())
        self.assertEqual(len(d["changes"]), 5)
        self.assertIn("Changed daily budget: FitFacts (35.0 → 37.0) (undone)", d["changes"][-1])
        self.assertEqual(d["changes_total"], len(CHANGES))

    def test_html_has_the_summary_then_the_latest_few(self):
        html = wr._render_advertising(LIVE, "#000", "#111", ads_extras=extras())
        self.assertIn("18 renames (6 campaigns, 6 ad sets, 6 ads)", html)
        self.assertIn("2 ad sets paused by the hard stop", html)
        self.assertIn("Latest", html)
        self.assertNotIn("Renamed campaign: c0", html)  # old lines are summarised, not listed

    def test_markdown_matches(self):
        md = "\n".join(wr._ads_extras_markdown(extras()))
        self.assertIn("18 renames (6 campaigns, 6 ad sets, 6 ads)", md)
        self.assertIn("Latest", md)
        self.assertNotIn("Renamed campaign: c0", md)

    def test_a_single_change_reads_naturally(self):
        d = wr._ads_extras_lines(dict(extras(), changes=[e("pause_adset", "Local Golfers")]))
        self.assertEqual(d["changes_summary"], ["1 ad set paused by the hard stop"])
        self.assertEqual(len(d["changes"]), 1)


if __name__ == "__main__":
    unittest.main()
