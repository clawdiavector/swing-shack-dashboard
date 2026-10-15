"""Music intelligence data foundation. Synthetic rows below are development
fixtures only; nothing here is written to brand data."""
from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
from _lib import music_intel as mi  # noqa: E402

REAL_AUDIT = CAMPAIGN_OS.parent / "data" / "brand-directory" / "stick" / "feedback" / "instagram-audit.json"


class T(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def test_identity_dedupes_spelling_and_keeps_unknown_null(self):
        a = mi.upsert_audio("stick", platform="instagram", root=self.root, title="Song  A!", artist="X")
        b = mi.upsert_audio("stick", platform="instagram", root=self.root, title="song a", artist="x", bpm=120.0)
        self.assertEqual(a["audio_id"], b["audio_id"])
        self.assertIsNone(b["genre"])
        self.assertEqual(b["bpm"], 120.0)
        self.assertEqual(len(mi._load("stick", "audio.json", self.root)), 1)

    def test_conflicting_value_is_recorded_not_overwritten(self):
        mi.upsert_audio("stick", platform="instagram", root=self.root, title="S", bpm=100.0)
        r = mi.upsert_audio("stick", platform="instagram", root=self.root, title="S", bpm=140.0)
        self.assertEqual(r["bpm"], 100.0)
        self.assertEqual(r["conflicts"], [{"field": "bpm", "other": 140.0}])

    def test_licence_default_refuses_and_verified_needs_evidence(self):
        a = mi.upsert_audio("stick", platform="instagram", root=self.root, title="S")
        ok, why = mi.commercially_usable(a, platform="instagram", country="ZA", use="organic")
        self.assertFalse(ok)
        with self.assertRaises(mi.MusicIntelError):
            mi.record_licence("stick", a["audio_id"], platform="instagram", country="ZA",
                              status="VERIFIED", root=self.root)

    def test_licence_hard_filter(self):
        a = mi.upsert_audio("stick", platform="instagram", root=self.root, title="S")["audio_id"]
        mi.record_licence("stick", a, platform="instagram", country="ZA", status="VERIFIED",
                          organic=True, paid=False, business_account=True,
                          evidence_url="https://example.test/lic", verified_on="2026-10-01",
                          valid_until="2026-12-31", root=self.root)
        row = mi._load("stick", "audio.json", self.root)[0]
        day = dt.date(2026, 10, 14)
        f = lambda **k: mi.commercially_usable(row, today=day, **{"platform": "instagram", "country": "ZA", **k})[0]
        self.assertTrue(f(use="organic"))
        self.assertFalse(f(use="paid"))
        self.assertFalse(f(use="organic", country="US"))
        self.assertFalse(f(use="organic", platform="tiktok"))
        self.assertFalse(mi.commercially_usable(row, platform="instagram", country="ZA",
                                                use="organic", today=dt.date(2027, 1, 1))[0])
        self.assertEqual(len(mi.usable_audio("stick", platform="instagram", country="ZA",
                                             use="organic", root=self.root, today=day)), 1)
        self.assertEqual(mi.usable_audio("stick", platform="instagram", country="ZA",
                                         use="paid", root=self.root, today=day), [])

    def test_import_is_idempotent(self):
        rows = [{"platform": "instagram", "post_id": "1", "title": "A", "bpm": "120"},
                {"platform": "instagram", "post_id": "2", "title": "a"},
                {"platform": "instagram", "post_id": "3", "title": ""},
                {"platform": "myspace", "post_id": "4", "title": "A"}]
        first = mi.import_post_audio("stick", rows, root=self.root)
        again = mi.import_post_audio("stick", rows, root=self.root)
        self.assertEqual(first, {"added": 2, "updated": 0, "unchanged": 0, "skipped": 2})
        self.assertEqual(again, {"added": 0, "updated": 0, "unchanged": 2, "skipped": 2})
        self.assertEqual(len(mi._load("stick", "audio.json", self.root)), 1)

    def test_brand_isolation(self):
        mi.import_post_audio("stick", [{"platform": "instagram", "post_id": "1", "title": "A"}], root=self.root)
        self.assertEqual(mi._load("swing-shack", "audio.json", self.root), [])
        self.assertEqual(mi.health("swing-shack", root=self.root, audit_path=self.root / "none.json")
                         ["distinct_audio"], 0)
        with self.assertRaises(mi.MusicIntelError):
            mi.upsert_audio("../stick", platform="instagram", root=self.root, title="A")

    def test_snapshots_idempotent_and_platform_metrics_enforced(self):
        kw = dict(platform="instagram", post_id="1", age_hours=168, observed_at="2026-10-14", root=self.root)
        self.assertTrue(mi.record_snapshot("stick", metrics={"reach": 10}, **kw))
        self.assertFalse(mi.record_snapshot("stick", metrics={"reach": 99}, **kw))
        with self.assertRaises(mi.MusicIntelError):
            mi.record_snapshot("stick", platform="tiktok", post_id="1", age_hours=24,
                               metrics={"reach": 5}, observed_at="x", root=self.root)
        with self.assertRaises(mi.MusicIntelError):
            mi.record_snapshot("stick", platform="instagram", post_id="1", age_hours=5,
                               metrics={}, observed_at="x", root=self.root)

    def test_relative_reach_needs_baseline_and_ignores_future_posts(self):
        pub = {str(i): f"2026-09-{i:02d}" for i in range(1, 9)}
        for i, v in zip(range(1, 9), [100, 100, 100, 100, 100, 100, 300, 9999]):
            mi.record_snapshot("stick", platform="instagram", post_id=str(i), age_hours=168,
                               metrics={"reach": v}, observed_at="x", root=self.root)
        r = mi.relative_reach("stick", "instagram", "7", published=pub, root=self.root)
        self.assertEqual((r["ratio"], r["n_baseline"]), (3.0, 6))  # post 8 (future) excluded
        r = mi.relative_reach("stick", "instagram", "3", published=pub, root=self.root)
        self.assertIsNone(r["ratio"])

    def test_health_refuses_to_claim_comparability_on_small_data(self):
        mi.import_post_audio("stick", [{"platform": "instagram", "post_id": "1", "title": "A"}], root=self.root)
        h = mi.health("stick", root=self.root, audit_path=self.root / "none.json")
        self.assertFalse(h["can_compare_audio"])
        self.assertEqual(h["audio_used_once"], 1)

    @unittest.skipUnless(REAL_AUDIT.exists(), "real audit not present")
    def test_real_feed_worksheet_and_health(self):
        ws = mi.worksheet("stick", audit_path=REAL_AUDIT, root=self.root)
        self.assertGreater(len(ws), 100)
        self.assertTrue(all("/reel/" in (w["permalink"] or "") or "/p/" in (w["permalink"] or "") for w in ws))
        h = mi.health("stick", audit_path=REAL_AUDIT, root=self.root)
        self.assertEqual((h["videos_in_feed"], h["videos_with_audio"]), (len(ws), 0))


if __name__ == "__main__":
    unittest.main()
