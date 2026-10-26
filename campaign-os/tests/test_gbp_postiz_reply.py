"""
Postiz answers a new post with a list, [{"postId": ...}], not one object. The Google
Business Publish route crashed reading it ('list' object has no attribute 'get')
after the post had already been scheduled, so the draft was never marked sent and
could be published twice.

Run: python -m pytest campaign-os/tests/test_gbp_postiz_reply.py
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_gbp_schedule_brand import ScheduleBrandTests  # noqa: E402

UPLOAD = {"id": "img-1", "path": "https://uploads.postiz.com/img-1.jpg"}


class ListReplyTests(ScheduleBrandTests):
    def test_a_list_reply_marks_the_draft_sent(self):
        self.pz.upload_media.return_value = (UPLOAD, None)
        self.pz.create_post.return_value = ([{"postId": "p-1", "integration": "x"}], None)
        self._approved("stick", "https://stickgolf.co.za/")
        res = self.client.post("/api/intel/gmb/draft/d/schedule", json={})
        self.assertEqual(res.status_code, 200, res.get_json())
        saved = json.loads((self.root / "d.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "scheduled")
        self.assertEqual(saved["postizId"], "p-1")

    def test_a_single_object_reply_still_works(self):
        self.pz.upload_media.return_value = (UPLOAD, None)
        self.pz.create_post.return_value = ({"id": "p-2"}, None)
        self._approved("stick", "https://stickgolf.co.za/")
        res = self.client.post("/api/intel/gmb/draft/d/schedule", json={})
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertEqual(res.get_json()["postizId"], "p-2")


# The inherited brand tests already run in their own file.
for _n in [n for n in dir(ScheduleBrandTests) if n.startswith("test_")]:
    if _n not in ("test_a_list_reply_marks_the_draft_sent", "test_a_single_object_reply_still_works"):
        setattr(ListReplyTests, _n, None)


if __name__ == "__main__":
    unittest.main()
