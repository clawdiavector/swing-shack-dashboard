"""
Postiz refuses a post whose photo has an id but no address ("image.0.path should
not be null"). Google Business posts must send both, from the upload response.

Run: python -m pytest campaign-os/tests/test_gbp_media_path.py
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_gbp_reviewed_drafts import _draft, gbp  # noqa: E402
from test_gbp_schedule_brand import ScheduleBrandTests  # noqa: E402

UPLOAD = {"id": "img-1", "path": "https://uploads.postiz.com/img-1.jpg"}


class DailyPosterMediaTests(unittest.TestCase):
    def setUp(self):
        self._profile = mock.patch.dict(gbp.BRAND_PROFILES["swing-shack"], {"postiz_gbp_integration_id": "int-1"})
        self._profile.start()

    def tearDown(self):
        self._profile.stop()

    def test_photo_id_and_address_are_both_sent(self):
        post = gbp.draft_post(_draft("a", status="approved"))
        with mock.patch("_lib.postiz_client.upload_media", return_value=(UPLOAD, None)), \
                mock.patch("_lib.postiz_client.create_post", return_value=({"id": "p"}, None)) as cp:
            result = gbp.publish_post(post)
        self.assertTrue(result["ok"], result)
        self.assertEqual(cp.call_args.kwargs["media"], [UPLOAD])


class DraftRouteMediaTests(ScheduleBrandTests):
    def test_draft_publish_sends_photo_id_and_address(self):
        self.pz.upload_media.return_value = (UPLOAD, None)
        self._approved("stick", "https://stickgolf.co.za/")
        res = self.client.post("/api/intel/gmb/draft/d/schedule", json={})
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertEqual(self.pz.create_post.call_args.kwargs["media"], [UPLOAD])


# The inherited brand tests already run in their own file.
for _n in [n for n in dir(ScheduleBrandTests) if n.startswith("test_")]:
    setattr(DraftRouteMediaTests, _n, getattr(DraftRouteMediaTests, _n) if _n in ("test_draft_publish_sends_photo_id_and_address",) else None)


if __name__ == "__main__":
    unittest.main()
