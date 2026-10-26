"""
Approved Google Business posts go out one a day, earliest approval first, by the
09:00 SAST job. Approve twelve on Monday and they are fed out over twelve days.

Run: python -m pytest campaign-os/tests/test_gbp_queue.py
"""

import datetime as dt
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_gbp_reviewed_drafts import _draft, _write  # noqa: E402
import test_gbp_schedule_brand as _brand  # noqa: E402

ScheduleBrandTests = _brand.ScheduleBrandTests

UPLOAD = {"id": "img-1", "path": "https://uploads.postiz.com/img-1.jpg"}


class QueueTests(ScheduleBrandTests):
    def setUp(self):
        super().setUp()
        self.pz.upload_media.return_value = (UPLOAD, None)
        self._plan = mock.patch.object(self.app_module._gdp, "save_plan", return_value=Path("x.json"))
        self._plan.start()

    def tearDown(self):
        self._plan.stop()
        super().tearDown()

    def _approve(self, draft_id, approved_at, **over):
        _write(self.root, _draft(draft_id, brand="stick", link="https://stickgolf.co.za/", status="approved",
                                 approvedAt=approved_at, imageUrl=str(self.media / "p.jpg"), **over))

    def _status(self, draft_id):
        return json.loads((self.root / f"{draft_id}.json").read_text(encoding="utf-8"))["status"]

    def test_sends_only_the_earliest_approved_post(self):
        self._approve("second", "2026-10-26T09:00:00Z")
        self._approve("first", "2026-10-26T08:00:00Z")
        out = self.app_module._gbp_publish_next(brand="stick")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["draft_id"], "first")
        self.assertEqual(self._status("first"), "scheduled")
        self.assertEqual(self._status("second"), "approved")
        self.assertEqual(self.pz.create_post.call_count, 1)

    def test_a_second_run_the_same_day_sends_nothing(self):
        self._approve("first", "2026-10-26T08:00:00Z")
        self._approve("second", "2026-10-26T09:00:00Z")
        self.app_module._gbp_publish_next(brand="stick")
        out = self.app_module._gbp_publish_next(brand="stick")
        self.assertEqual(out["skipped"], "already_sent_today")
        self.assertEqual(self.pz.create_post.call_count, 1)
        self.assertEqual(self._status("second"), "approved")

    def test_next_day_sends_the_next_post(self):
        self._approve("second", "2026-10-26T09:00:00Z")
        _write(self.root, _draft("old", brand="stick", status="scheduled", updatedAt="2026-10-24T07:00:00Z"))
        out = self.app_module._gbp_publish_next(brand="stick")
        self.assertEqual(out["draft_id"], "second")

    def test_a_post_that_fails_review_goes_back_and_the_next_is_sent(self):
        _write(self.root, _draft("nophoto", brand="stick", link="https://stickgolf.co.za/", status="approved",
                                 approvedAt="2026-10-26T08:00:00Z", imageUrl=""))
        self._approve("good", "2026-10-26T09:00:00Z")
        out = self.app_module._gbp_publish_next(brand="stick")
        self.assertEqual(out["draft_id"], "good")
        self.assertEqual(self._status("nophoto"), "draft")
        self.assertEqual(out["returned_to_review"][0]["draft_id"], "nophoto")

    def test_nothing_approved_sends_nothing(self):
        out = self.app_module._gbp_publish_next(brand="stick")
        self.assertEqual(out["skipped"], "nothing_approved")
        self.pz.create_post.assert_not_called()

    def test_a_postiz_failure_leaves_the_post_approved_for_tomorrow(self):
        self.pz.create_post.return_value = (None, ("500", "boom"))
        self._approve("first", "2026-10-26T08:00:00Z")
        out = self.app_module._gbp_publish_next(brand="stick")
        self.assertFalse(out["ok"])
        self.assertEqual(self._status("first"), "approved")


# The inherited brand tests already run in their own file.
for _n in [n for n in dir(ScheduleBrandTests) if n.startswith("test_")]:
    setattr(QueueTests, _n, None)
for _n in ("test_sends_only_the_earliest_approved_post", "test_a_second_run_the_same_day_sends_nothing",
           "test_next_day_sends_the_next_post", "test_a_post_that_fails_review_goes_back_and_the_next_is_sent",
           "test_nothing_approved_sends_nothing", "test_a_postiz_failure_leaves_the_post_approved_for_tomorrow"):
    setattr(QueueTests, _n, QueueTests.__dict__[_n] if _n in QueueTests.__dict__ else None)


if __name__ == "__main__":
    unittest.main()
