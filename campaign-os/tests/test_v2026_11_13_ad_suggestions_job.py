"""The morning ads job keeps the list of what already runs as an ad, for the Ad suggestions page."""
from __future__ import annotations

import json
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_10_08_ads_brief as bfx  # noqa: E402
from _lib import ads_suggest  # noqa: E402


class Running(bfx._JobCase):
    def test_the_job_writes_running_ad_captions_beside_the_brief(self):
        out = self.run_job(bfx.fx.STICK, bfx.DAY)
        self.assertTrue(out["ok"], out)
        path = self.lane.parent / "ads-suggest" / "running.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["date"], bfx.DAY.isoformat())
        self.assertTrue(doc["bodies"])
        self.assertTrue(all(b == ads_suggest.norm(b) or len(b) <= 60 for b in doc["bodies"]))
        self.assertIsInstance(doc["post_ids"], list)
