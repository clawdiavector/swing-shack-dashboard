"""
Daily Google Business posts come only from drafts a person approved.

- A draft needs a body, a link on its brand's site, a photo and a clean text
  gate before it can be approved.
- The daily plan takes approved drafts in approval order. An empty slot is a
  gap. Nothing is composed to fill it.
- A post goes to Postiz with its photo attached and its link in the text. A
  photo that fails to upload stops the post.

Run: python -m pytest campaign-os/tests/test_gbp_reviewed_drafts.py
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "campaign-os"))

from _lib import gbp_daily_poster as gbp  # noqa: E402


def _draft(draft_id, **over):
    base = {
        "id": draft_id,
        "brand": "swing-shack",
        "title": "Ball fitting at Swing Shack",
        "body": "A fitting session shows which ball fits your swing.",
        "cta": "Book now",
        "link": "https://swingshack.co.za/bookings/",
        "imageUrl": "C:/photos/fitting.jpg",
        "status": "draft",
        "createdAt": "2026-10-15T08:00:00Z",
    }
    base.update(over)
    return base


def _write(root: Path, draft: dict):
    (root / f"{draft['id']}.json").write_text(json.dumps(draft), encoding="utf-8")


class ReviewProblemsTests(unittest.TestCase):
    def test_complete_draft_has_no_problems(self):
        self.assertEqual(gbp.review_problems(_draft("a")), [])

    def test_missing_photo_and_link_block_approval(self):
        problems = gbp.review_problems(_draft("a", imageUrl="", link=""))
        self.assertIn("photo_missing", problems)
        self.assertIn("link_missing", problems)

    def test_link_must_be_on_the_brand_site(self):
        problems = gbp.review_problems(_draft("a", link="https://stickgolf.co.za/bookings/"))
        self.assertIn("link_not_brand_domain", problems)

    def test_em_dash_blocks_approval(self):
        problems = gbp.review_problems(_draft("a", body="Fit first \u2014 then buy."))
        self.assertIn("em_dash_or_en_dash_present", problems)


class PlanFromDraftsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_only_approved_drafts_enter_the_plan_in_approval_order(self):
        _write(self.root, _draft("late", status="approved", approvedAt="2026-10-15T10:00:00Z"))
        _write(self.root, _draft("early", status="approved", approvedAt="2026-10-14T10:00:00Z"))
        _write(self.root, _draft("waiting", status="draft"))
        plan = gbp.build_daily_plan("swing-shack", days=2, posts_per_day=1, drafts_dir=self.root)
        self.assertEqual([p["draft_id"] for p in plan["posts"]], ["early", "late"])
        self.assertEqual(plan["source_breakdown"], {"from_drafts": 2, "gaps": 0})

    def test_empty_slot_is_a_gap_not_composed_copy(self):
        _write(self.root, _draft("only", status="approved", approvedAt="2026-10-15T10:00:00Z"))
        plan = gbp.build_daily_plan("swing-shack", days=3, posts_per_day=1, drafts_dir=self.root)
        self.assertEqual(len(plan["posts"]), 1)
        self.assertEqual([g["error"] for g in plan["gaps"]], ["gap_no_approved_draft"] * 2)

    def test_other_brands_drafts_are_ignored(self):
        _write(self.root, _draft("stick-one", brand="stick", status="approved", approvedAt="2026-10-15T10:00:00Z"))
        plan = gbp.build_daily_plan("swing-shack", days=1, posts_per_day=1, drafts_dir=self.root)
        self.assertEqual(plan["posts"], [])

    def test_plan_post_carries_photo_and_link(self):
        _write(self.root, _draft("a", status="approved", approvedAt="2026-10-15T10:00:00Z"))
        post = gbp.build_daily_plan("swing-shack", days=1, posts_per_day=1, drafts_dir=self.root)["posts"][0]
        self.assertEqual(post["image_url"], "C:/photos/fitting.jpg")
        self.assertEqual(post["cta_url"], "https://swingshack.co.za/bookings/")


class SetDraftStatusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_approve_then_publish_updates_the_file(self):
        _write(self.root, _draft("a"))
        self.assertTrue(gbp.set_draft_status("a", "approved", drafts_dir=self.root))
        saved = json.loads((self.root / "a.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "approved")
        self.assertIn("approvedAt", saved)
        self.assertTrue(gbp.set_draft_status("a", "published", drafts_dir=self.root))
        self.assertEqual(json.loads((self.root / "a.json").read_text(encoding="utf-8"))["status"], "published")

    def test_unknown_status_and_missing_draft_are_refused(self):
        self.assertFalse(gbp.set_draft_status("a", "live", drafts_dir=self.root))
        self.assertFalse(gbp.set_draft_status("missing", "approved", drafts_dir=self.root))
        self.assertFalse(gbp.set_draft_status("../escape", "approved", drafts_dir=self.root))


class PublishPostTests(unittest.TestCase):
    def setUp(self):
        self._profile = mock.patch.dict(
            gbp.BRAND_PROFILES["swing-shack"], {"postiz_gbp_integration_id": "int-1"}
        )
        self._profile.start()

    def tearDown(self):
        self._profile.stop()

    def _post(self):
        return gbp.draft_post(_draft("a", status="approved"))

    def test_photo_is_uploaded_and_attached_and_link_is_in_text(self):
        with mock.patch("_lib.postiz_client.upload_media",
                        return_value=({"id": "img-1", "path": "https://x/img-1.jpg"}, None)) as up,                 mock.patch("_lib.postiz_client.create_post", return_value=({"id": "post-1"}, None)) as cp:
            result = gbp.publish_post(self._post())
        self.assertTrue(result["ok"], result)
        up.assert_called_once_with("C:/photos/fitting.jpg")
        kwargs = cp.call_args.kwargs
        self.assertEqual(kwargs["media_ids"], ["img-1"])
        self.assertIn("https://swingshack.co.za/bookings/", kwargs["content"])
        self.assertIn("Book now", kwargs["content"])

    def test_failed_photo_upload_stops_the_post(self):
        with mock.patch("_lib.postiz_client.upload_media", return_value=(None, ("413", "too large"))),                 mock.patch("_lib.postiz_client.create_post") as cp:
            result = gbp.publish_post(self._post())
        self.assertFalse(result["ok"])
        self.assertIn("image_upload_failed", result["error"])
        cp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
