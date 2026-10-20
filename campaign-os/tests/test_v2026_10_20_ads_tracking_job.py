"""The ads_brief job writes a tracking check beside the brief, and survives a GA4 or tag read failing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_10_08_ads_brain as fx  # noqa: E402
import test_v2026_10_08_ads_brief as base  # noqa: E402


class TrackingFile(base._JobCase):
    def test_writes_tracking_even_with_no_ga4_configured(self):
        out = self.job.run(brand="stick", today=base.DAY, get=base._get(fx.STICK, base.RECENT["stick"]),
                           get_as=fx._fake_get_as(fx.STICK))
        self.assertTrue(out["ok"], out)
        path = Path(self.tmp.name) / "brands" / "stick" / "ads-tracking" / "latest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["brand_id"], "stick")
        self.assertIn("summary", data)
        self.assertTrue(any("GA4" in e for e in data["errors"]), data["errors"])
        # The brief itself is untouched by the add-on.
        self.assertTrue(self.read("latest.json")["headline"])
