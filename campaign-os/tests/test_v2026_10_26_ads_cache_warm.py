"""The ads job warms the Meta ad cache the weekly report reads, so the report never opens with
'Advertising is not yet connected' because the first request had to ingest from Meta (slow, timed out)."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

from _lib import ads_cache_warm  # noqa: E402


def _write(path: Path, fetched_at: dt.datetime, body: str = "x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": fetched_at.isoformat(), "body": body}), encoding="utf-8")


class Warm(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.calls = []
        self.now = dt.datetime.now(dt.timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def ingest(self, ok=True):
        def fn(brand_id, period_days=31, ytd=True):
            self.calls.append((brand_id, period_days, ytd))
            if ok:
                _write(self.dir / "paid-media" / f"{brand_id}.json", self.now, f"fresh{period_days}")
            return {"current_period": {"ok": ok}}
        return fn

    def test_refreshes_both_windows_when_missing_and_copies_the_canonical_file_per_window(self):
        out = ads_cache_warm.warm("stick", ingest=self.ingest(), data_dir=self.dir)
        self.assertEqual(self.calls, [("stick", 7, False), ("stick", 31, True)])
        self.assertEqual(out, {"7": "refreshed", "31": "refreshed"})
        for p in (7, 31):
            body = json.loads((self.dir / "paid-media" / f"stick__{p}d.json").read_text(encoding="utf-8"))
            self.assertEqual(body["body"], f"fresh{p}")

    def test_leaves_a_recent_copy_alone(self):
        for p in (7, 31):
            _write(self.dir / "paid-media" / f"stick__{p}d.json", self.now - dt.timedelta(hours=1))
        out = ads_cache_warm.warm("stick", ingest=self.ingest(), data_dir=self.dir)
        self.assertEqual(self.calls, [])
        self.assertEqual(out, {"7": "already fresh", "31": "already fresh"})

    def test_refreshes_a_copy_older_than_the_threshold(self):
        _write(self.dir / "paid-media" / "stick__7d.json", self.now - dt.timedelta(hours=7))
        _write(self.dir / "paid-media" / "stick__31d.json", self.now - dt.timedelta(hours=1))
        out = ads_cache_warm.warm("stick", ingest=self.ingest(), data_dir=self.dir)
        self.assertEqual(self.calls, [("stick", 7, False)])
        self.assertEqual(out["7"], "refreshed")

    def test_a_failed_ingest_keeps_the_old_copy_and_says_so(self):
        _write(self.dir / "paid-media" / "stick__31d.json", self.now - dt.timedelta(hours=9), "old")
        out = ads_cache_warm.warm("stick", ingest=self.ingest(ok=False), data_dir=self.dir)
        self.assertEqual(out["31"], "failed")
        body = json.loads((self.dir / "paid-media" / "stick__31d.json").read_text(encoding="utf-8"))
        self.assertEqual(body["body"], "old")

    def test_an_exception_in_one_window_does_not_stop_the_other(self):
        def boom(brand_id, period_days=31, ytd=True):
            if period_days == 7:
                raise RuntimeError("meta down")
            _write(self.dir / "paid-media" / f"{brand_id}.json", self.now)
            return {"current_period": {"ok": True}}
        out = ads_cache_warm.warm("stick", ingest=boom, data_dir=self.dir)
        self.assertTrue(out["7"].startswith("failed"))
        self.assertEqual(out["31"], "refreshed")

    def test_gives_up_when_the_job_is_short_of_time(self):
        out = ads_cache_warm.warm("stick", ingest=self.ingest(), data_dir=self.dir, deadline=time.monotonic() - 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(out, {"7": "skipped: out of time", "31": "skipped: out of time"})


class InTheJob(unittest.TestCase):
    def test_the_ads_job_is_given_enough_time_to_warm_the_cache(self):
        from _lib.jobs.layer7 import layer7_specs
        spec = next(s for s in layer7_specs() if s.name == "ads_brief")
        self.assertGreaterEqual(spec.timeout_seconds, 300)


if __name__ == "__main__":
    unittest.main()
