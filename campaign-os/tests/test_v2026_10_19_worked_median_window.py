"""
test_v2026_10_19_worked_median_window.py

What worked > posts card average (2026-10-19):
  - the average is a median, not a mean
  - posts older than 90 days are left out
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str((_Path(__file__).resolve().parent / '.').resolve()))

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import test_v2026_08_07_insights_v2 as _insights  # noqa: E402


class WorkedMedianWindowTests(_insights.InsightsV2ApiTests):
    # Same isolation as WorkedPostsSentenceTests; inherited tests are not collected twice.
    def _top_payload(self, posts):
        bundled_dir = Path(tempfile.mkdtemp(prefix="test-bundled-"))
        orig_bundled = os.environ.get("BUNDLED_DATA_DIR")
        os.environ["BUNDLED_DATA_DIR"] = str(bundled_dir)
        try:
            (self.tmpdir / "instagram.json").write_text(
                json.dumps({"updated": "2026-10-19T10:00:00Z", "posts": posts})
            )
            r = self.client.get("/api/insights/top-instagram-posts?limit=8")
            self.assertEqual(r.status_code, 200)
            return r.get_json()
        finally:
            shutil.rmtree(bundled_dir, ignore_errors=True)
            if orig_bundled is not None:
                os.environ["BUNDLED_DATA_DIR"] = orig_bundled
            else:
                os.environ.pop("BUNDLED_DATA_DIR", None)

    def test_average_is_median_not_mean(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        posts = [{"id": f"p{i}", "engagementRate": er, "timestamp": recent, "media_type": "IMAGE"}
                 for i, er in enumerate([1.0, 1.0, 1.0, 50.0])]
        data = self._top_payload(posts)
        self.assertEqual(data["_meta"]["average_kind"], "median")
        self.assertEqual(data["_meta"]["average_engagement"], 1.0)

    def test_posts_older_than_90_days_are_excluded(self):
        old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        recent = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        posts = [
            {"id": "old", "engagementRate": 99.0, "timestamp": old, "media_type": "IMAGE"},
            {"id": "new", "engagementRate": 2.0, "timestamp": recent, "media_type": "IMAGE"},
        ]
        data = self._top_payload(posts)
        self.assertEqual([p["id"] for p in data["posts"]], ["new"])
        self.assertEqual(data["_meta"]["total_scanned"], 1)
