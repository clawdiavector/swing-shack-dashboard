"""Weekly report: the Advertising section carries the month's budget, per-ad performance, tracking and changes."""
from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import weekly_report_v3 as wr  # noqa: E402

LIVE = {"paid_media_v24": {"data_status": "LIVE", "per_campaign": []}}
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _ad(name, spend, kind="WEBSITE", sessions=100, engaged=25.0, keys=0, leads=0, cpl=None):
    web = kind == "WEBSITE"
    return {"ad_id": name, "ad_name": name, "campaign": "Camp", "destination": kind, "spend": spend,
            "ga_sessions": sessions if web else 0, "ga_engaged": 0, "ga_key_events": keys,
            "perf": {"leads": leads, "messages": 0, "cost_per_lead": cpl, "cost_per_message": None,
                     "cost_per_session": 2.0 if web else None, "engaged_pct": engaged if web else None,
                     "key_events": keys if web else None, "click_to_session_pct": 90.0 if web else None}}


def _extras(**over):
    x = {"tracking": {"date": datetime.date.today().isoformat(), "brand_id": "stick",
                      "summary": {"website_ads": 2, "website_with_complete_utm": 0, "ga_paid_sessions": 1000,
                                  "ga_matched": 990, "never_reach_site": 1},
                      "totals": {"spend": 500.0, "leads": 8, "cost_per_lead": 30.0, "ga_sessions": 100,
                                 "ga_engaged_pct": 25.0, "ga_key_events": 0, "cost_per_session": 2.0},
                      "ads": [_ad("fitting_video_v1", 300.0), _ad("coaching_video_v1", 200.0, kind="LEAD_FORM", leads=8, cpl=25.0)]},
         "budget": {"headline": "The month's budget of R1,500 is already spent (R2,390).", "status": "OVER", "budget": 1500,
                    "mtd_spend": 2390.0, "projected_total": 3170.0, "left": -890.0},
         "changes": [{"kind": "pause_adset", "ad_name": "Local Golfers", "at": NOW, "before": "ACTIVE", "after": "PAUSED"},
                     {"kind": "rename_ad", "ad_name": "fitting_video_v1", "at": NOW, "before": "Old", "after": "fitting_video_v1",
                      "undone_at": None}],
         "guard_on": True, "paused_now": 1}
    x.update(over)
    return x


class Render(unittest.TestCase):
    def test_html_has_the_budget_each_ad_the_tracking_line_and_the_changes(self):
        html = wr._render_advertising(LIVE, "#000", "#111", ads_extras=_extras())
        self.assertIn("The month's ad budget", html)
        self.assertIn("already spent", html)
        self.assertIn("Hard stop is ON", html)
        self.assertIn("1 ad set(s) are paused by it right now", html)
        self.assertIn("How each ad performed", html)
        self.assertIn("fitting_video_v1", html)
        self.assertIn("Only 25% of visitors stayed", html)
        self.assertIn("8 leads at R25", html)
        self.assertIn("990", html)
        self.assertIn("Changes made to the ads this week", html)
        self.assertIn("Paused ad set: Local Golfers", html)
        self.assertIn("Renamed ad: fitting_video_v1 (Old → fitting_video_v1)", html)

    def test_no_extras_leaves_the_section_as_it_was(self):
        html = wr._render_advertising(LIVE, "#000", "#111", ads_extras=None)
        self.assertNotIn("How each ad performed", html)
        self.assertNotIn("The month's ad budget", html)

    def test_undone_changes_say_so_and_html_is_escaped(self):
        x = _extras(changes=[{"kind": "rename_ad", "ad_name": "<b>x</b>", "at": NOW, "before": "a", "after": "b", "undone_at": NOW}])
        html = wr._render_advertising(LIVE, "#000", "#111", ads_extras=x)
        self.assertIn("(undone)", html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
        self.assertNotIn("<b>x</b>", html)

    def test_hard_stop_off_and_no_budget(self):
        x = _extras(guard_on=False, paused_now=0, budget={"headline": "No monthly budget set yet.", "status": "NO_BUDGET",
                                                           "budget": None, "mtd_spend": 100.0, "projected_total": 200.0, "left": None})
        html = wr._render_advertising(LIVE, "#000", "#111", ads_extras=x)
        self.assertIn("Hard stop is OFF", html)
        self.assertIn("not set", html)

    def test_markdown(self):
        md = "\n".join(wr._ads_extras_markdown(_extras()))
        self.assertIn("### The month's ad budget", md)
        self.assertIn("### How each ad performed", md)
        self.assertIn("**fitting_video_v1** (Camp): Spent R300", md)
        self.assertIn("### Changes made to the ads this week", md)
        self.assertEqual(wr._ads_extras_markdown(None), [])

    def test_notes_follow_the_same_rules_as_the_trends_page(self):
        self.assertIn("likely problem", wr._ad_note(_ad("a", 1, engaged=20.0), None))
        self.assertIn("holds people", wr._ad_note(_ad("a", 1, engaged=70.0), None))
        self.assertIn("counting started", wr._ad_note(_ad("a", 1, engaged=40.0), None))
        self.assertEqual(wr._ad_note(_ad("a", 1, sessions=10, engaged=40.0), None), "")
        self.assertIn("Cheaper", wr._ad_note(_ad("a", 1, kind="LEAD_FORM", leads=9, cpl=20.0), 30.0))
        self.assertIn("Dearer", wr._ad_note(_ad("a", 1, kind="LEAD_FORM", leads=9, cpl=40.0), 30.0))


class Read(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = self.tmp.name
        self.lane = Path(self.tmp.name) / "brands" / "stick"

    def tearDown(self):
        if self._old is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._old
        self.tmp.cleanup()

    def write(self, rel, obj):
        p = self.lane / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj), encoding="utf-8")

    def test_reads_tracking_budget_and_the_last_weeks_changes_only(self):
        t = _extras()["tracking"]
        self.write("ads-tracking/latest.json", t)
        self.write("ads-budget/settings.json", {"monthly_budget": 1500, "auto_pause": True})
        self.write("ads-budget/figures.json", {"mtd_spend": 2390.0, "complete": True, "daily_run_rate": 0,
                                               "expected_rest_of_month": 0, "worst_case_rest_of_month": 0,
                                               "days_left_after_today": 5, "sets": []})
        old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=20)).isoformat()
        self.write("ads-actions/log.json", {"entries": [
            {"id": "1", "kind": "rename_ad", "at": old, "ad_name": "old"},
            {"id": "2", "kind": "pause_adset", "at": NOW, "ad_name": "recent", "by": "budget guard"}]})
        x = wr._read_ads_extras("stick")
        self.assertEqual(x["budget"]["status"], "OVER")
        self.assertEqual([c["id"] for c in x["changes"]], ["2"])
        self.assertTrue(x["guard_on"])
        self.assertEqual(x["paused_now"], 1)
        self.assertEqual(len(x["tracking"]["ads"]), 2)

    def test_nothing_on_file_stale_tracking_other_brand_and_history(self):
        self.assertIsNone(wr._read_ads_extras("stick"))
        old = (datetime.date.today() - datetime.timedelta(days=9)).isoformat()
        self.write("ads-tracking/latest.json", dict(_extras()["tracking"], date=old))
        self.assertIsNone(wr._read_ads_extras("stick"))
        self.write("ads-tracking/latest.json", dict(_extras()["tracking"], brand_id="swing-shack"))
        self.assertIsNone(wr._read_ads_extras("stick"))
        self.write("ads-tracking/latest.json", _extras()["tracking"])
        self.assertIsNone(wr._read_ads_extras("stick", as_of="2026-09-01"))


if __name__ == "__main__":
    unittest.main()
