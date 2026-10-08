"""Weekly report: the Advertising section carries the ads brief's actions."""
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

LIVE = {"paid_media_v24": {"data_status": "LIVE", "per_campaign": [
    {"campaign_name": "FitFacts", "objective": "OUTCOME_LEADS",
     "current": {"spend": 120.0, "impressions": 2000, "reach": 1500, "clicks": 60},
     "previous": {"spend": 118.0, "impressions": 2100, "reach": 1600, "clicks": 58},
     "primary_result": {"primary_metric_label": "Meta-reported leads", "primary_value": 4,
                        "primary_cost_per_unit": 30.0}}]}}


def _brief(date=None, **over):
    b = {"brand_id": "swing-shack", "date": date or datetime.date.today().isoformat(),
         "headline": {"actions": 8, "new": 0, "resolved": 0, "open": 13},
         "top_actions": [
             {"rule": "spend_mix", "severity": "medium", "ads": [], "days_open": 0,
              "action": "Move budget from traffic and awareness to the lead ads.",
              "why": "34% of R2,993 went to ads that produced a lead."},
             {"rule": "below_average_ranking", "severity": "medium", "days_open": 5,
              "ads": ["Welcome David", "Putter <b>"],
              "action": "Check the landing page, the offer and the objective.",
              "why": "Meta ranks this ad below average for conversion rate."}]}
    b.update(over)
    return b


class Block(unittest.TestCase):
    def test_actions_render_inside_the_advertising_section(self):
        html = wr._render_advertising(LIVE, "#000", "#111", ads_brief=_brief())
        self.assertIn("What the ads need", html)
        self.assertIn("8 findings to act on", html)
        self.assertIn("Move budget from traffic and awareness to the lead ads.", html)
        self.assertIn("open 5 days", html)
        self.assertIn("href='/ads-brief'", html)
        self.assertIn("Putter &lt;b&gt;", html)
        self.assertNotIn("Putter <b>", html)
        # Still one Advertising section, with the campaign cards before the block.
        self.assertEqual(html.count('id="sec-Advertising"'), 1)
        self.assertLess(html.index("FitFacts"), html.index("What the ads need"))

    def test_no_brief_leaves_the_section_as_it_was(self):
        self.assertNotIn("What the ads need", wr._render_advertising(LIVE, "#000", "#111"))

    def test_nothing_to_do(self):
        html = wr._render_ads_brief(_brief(top_actions=[], headline={"actions": 0}))
        self.assertIn("0 findings to act on", html)
        self.assertIn("Nothing needs action this week.", html)

    def test_not_connected_brand_shows_no_block(self):
        html = wr._render_advertising({"paid_media_v24": {"data_status": "NOT_CONNECTED"}},
                                      "#000", "#111", ads_brief=_brief())
        self.assertNotIn("What the ads need", html)

    def test_markdown(self):
        lines = wr._ads_brief_markdown(_brief())
        self.assertEqual(lines[0], "### What the ads need")
        self.assertIn("1. **Move budget from traffic and awareness to the lead ads.**", lines)
        self.assertTrue(any("(Welcome David, Putter <b> · open 5 days)" in l for l in lines))
        self.assertEqual(wr._ads_brief_markdown(None), [])


class Read(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = self.tmp.name
        self.path = Path(self.tmp.name) / "brands" / "swing-shack" / "ads-brief" / "latest.json"
        self.path.parent.mkdir(parents=True)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._old
        self.tmp.cleanup()

    def test_fresh_brief_is_read(self):
        self.path.write_text(json.dumps(_brief()), encoding="utf-8")
        self.assertEqual(wr._read_ads_brief("swing-shack")["headline"]["actions"], 8)

    def test_missing_stale_or_wrong_brand_is_skipped(self):
        self.assertIsNone(wr._read_ads_brief("swing-shack"))
        old = (datetime.date.today() - datetime.timedelta(days=9)).isoformat()
        self.path.write_text(json.dumps(_brief(date=old)), encoding="utf-8")
        self.assertIsNone(wr._read_ads_brief("swing-shack"))
        self.path.write_text(json.dumps(_brief(brand_id="stick")), encoding="utf-8")
        self.assertIsNone(wr._read_ads_brief("swing-shack"))
        self.path.write_text("not json", encoding="utf-8")
        self.assertIsNone(wr._read_ads_brief("swing-shack"))

    def test_historical_report_gets_no_brief(self):
        self.path.write_text(json.dumps(_brief()), encoding="utf-8")
        self.assertIsNone(wr._read_ads_brief("swing-shack", as_of="2026-09-01"))


if __name__ == "__main__":
    unittest.main()
