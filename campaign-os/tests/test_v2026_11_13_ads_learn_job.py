"""The morning ads job keeps the suggestions log: today's suggestions remembered, running ads matched."""
from __future__ import annotations

import json
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_10_08_ads_brief as bfx  # noqa: E402


class Log(bfx._JobCase):
    def test_the_job_remembers_todays_suggestions(self):
        lane = self.lane.parent
        lane.mkdir(parents=True, exist_ok=True)
        when = bfx.DAY.isoformat() + "T08:00:00+0000"
        (lane / "post-outcomes.json").write_text(json.dumps({"outcomes": [
            {"post_id": "p1", "caption_preview": "Book a fitting at Stick, driver day.", "format_type": "reel",
             "reach": 900, "score": 60, "permalink": "https://www.instagram.com/reel/p1/", "timestamp": when}]}),
            encoding="utf-8")
        out = self.run_job(bfx.fx.STICK, bfx.DAY)
        self.assertTrue(out["ok"], out)
        log = json.loads((lane / "ads-suggest" / "log.json").read_text(encoding="utf-8"))
        self.assertEqual([e["post_id"] for e in log["entries"]], ["p1"])
        self.assertEqual(log["entries"][0]["status"], "SUGGESTED")
