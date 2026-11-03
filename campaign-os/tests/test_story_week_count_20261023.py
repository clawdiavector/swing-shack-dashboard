"""Stories shared this week: queue items done plus Shared marks since Monday 00:00 (Johannesburg)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import story_marks, story_queue, story_week  # noqa: E402

TZ = ZoneInfo("Africa/Johannesburg")
FRI = datetime(2026, 10, 23, 15, 0, tzinfo=TZ)


class WeekCountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"DATA_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_week_starts_monday(self):
        self.assertEqual(story_week.week_start(FRI).isoformat(), "2026-10-19T00:00:00+02:00")

    def test_counts_shared_marks_and_done_items_this_week_only(self):
        story_marks._save({
            "post|https://instagram.com/p/A": {"state": "shared", "at": "2026-10-20T09:00:00+02:00", "brand": "stick"},
            "post|https://instagram.com/p/B": {"state": "shared", "at": "2026-10-18T09:00:00+02:00", "brand": "stick"},
            "post|https://instagram.com/p/C": {"state": "skipped", "at": "2026-10-21T09:00:00+02:00", "brand": "stick"},
            "idea|swing-shack|2026-10-22|retail|Takomo": {"state": "shared", "at": "2026-10-22T10:00:00+02:00"},
        })
        story_queue._save([
            {"id": "a", "brand": "stick", "url": "https://instagram.com/p/Q", "status": "done", "done_at": "2026-10-22T11:00:00+02:00"},
            {"id": "b", "brand": "stick", "url": "https://instagram.com/p/R", "status": "done", "done_at": "2026-10-17T11:00:00+02:00"},
            {"id": "c", "brand": "stick", "url": "https://instagram.com/p/S", "status": "open", "done_at": None},
        ])
        self.assertEqual(story_week.shared_this_week(None, FRI), 3)
        self.assertEqual(story_week.shared_this_week(["stick"], FRI), 2)
        self.assertEqual(story_week.shared_this_week(["swing-shack"], FRI), 1)

    def test_same_link_in_queue_and_marks_counts_once(self):
        story_marks._save({"post|https://instagram.com/p/Q": {"state": "shared", "at": "2026-10-22T09:00:00+02:00", "brand": "stick"}})
        story_queue._save([{"id": "a", "brand": "stick", "url": "https://instagram.com/p/Q", "status": "done", "done_at": "2026-10-22T11:00:00+02:00"}])
        self.assertEqual(story_week.shared_this_week(None, FRI), 1)


if __name__ == "__main__":
    unittest.main()
