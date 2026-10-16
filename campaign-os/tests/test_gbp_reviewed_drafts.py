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


class PhotoCheckTests(unittest.TestCase):
    def test_real_image_bytes_match_their_extension(self):
        self.assertTrue(gbp.looks_like_photo(b"\xff\xd8\xff\xe0rest", ".jpg"))
        self.assertTrue(gbp.looks_like_photo(b"\x89PNG\r\n\x1a\nrest", ".png"))
        self.assertTrue(gbp.looks_like_photo(b"RIFF\x00\x00\x00\x00WEBPrest", ".webp"))

    def test_text_renamed_to_jpg_is_refused(self):
        self.assertFalse(gbp.looks_like_photo(b"not a picture", ".jpg"))
        self.assertFalse(gbp.looks_like_photo(b"\x89PNG\r\n\x1a\n", ".jpg"))
        self.assertFalse(gbp.looks_like_photo(b"\xff\xd8\xff", ".gif"))


class RebuildPlanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_rebuild_includes_new_approval_and_keeps_publish_log(self):
        _write(self.root, _draft("first", status="approved", approvedAt="2026-10-15T10:00:00Z"))
        _write(self.root, _draft("second", status="approved", approvedAt="2026-10-15T11:00:00Z"))
        previous = {"publish": {"posts": [{"status": "scheduled"}], "scheduled_count": 1}}
        plan = gbp.rebuild_plan("swing-shack", previous=previous, drafts_dir=self.root)
        self.assertEqual([p["draft_id"] for p in plan["posts"]], ["first", "second"])
        self.assertEqual(plan["publish"], previous["publish"])


class SearchTermTests(unittest.TestCase):
    def _gsc(self, **over):
        payload = {
            "source": "google_search_console_api",
            "site_url": "sc-domain:swingshack.co.za",
            "updated": "2026-10-15T06:00:00Z",
            "data_window": {"start": "2026-09-17", "end": "2026-10-14"},
            "queries": [
                {"key": "golf simulator johannesburg", "impressions": 40, "clicks": 2, "position": 8.1},
                {"key": "club fitting randburg", "impressions": 310, "clicks": 9, "position": 4.2},
                {"key": "", "impressions": 999},
                {"key": "indoor golf", "impressions": 120, "clicks": 4, "position": 6.0},
            ],
        }
        payload.update(over)
        return payload

    def test_terms_are_sorted_by_impressions_and_blank_keys_dropped(self):
        out = gbp.search_terms("swing-shack", payload=self._gsc())
        self.assertTrue(out["ok"])
        self.assertEqual([t["query"] for t in out["terms"]],
                         ["club fitting randburg", "indoor golf", "golf simulator johannesburg"])

    def test_no_live_file_gives_a_reason_not_guesses(self):
        out = gbp.search_terms("swing-shack", payload=None)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "no_search_console_data")
        self.assertEqual(out["terms"], [])

    def test_search_console_for_another_site_is_refused(self):
        out = gbp.search_terms("stick", payload=self._gsc())
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "search_console_site_is_not_this_brand")

    def test_target_term_must_appear_in_the_text(self):
        draft = _draft("t", targetQuery="club fitting randburg")
        self.assertIn("target_query_not_in_body", gbp.review_problems(draft))
        draft = _draft("t", targetQuery="Club Fitting", body="Club fitting in Randburg, booked online.")
        self.assertNotIn("target_query_not_in_body", gbp.review_problems(draft))


def _jpeg_bytes() -> bytes:
    import io  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 30, 30)).save(buf, "JPEG")
    return buf.getvalue()


class DraftRouteTests(unittest.TestCase):
    """Approve, photo upload and dismiss through the Flask routes, on temp folders."""

    def setUp(self):
        import app as app_module  # noqa: PLC0415

        self.app_module = app_module
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "gmb-drafts"
        self.media = Path(self._tmp.name) / "media"
        self.root.mkdir()
        self.media.mkdir()
        self._patches = [
            mock.patch.object(app_module, "GMB_DRAFTS_DIR", str(self.root)),
            mock.patch.object(app_module, "ASSET_MEDIA_DIR", str(self.media)),
            mock.patch.object(app_module._gdp, "GMB_DRAFTS_DIR", self.root),
            mock.patch.object(app_module._gdp, "save_plan", return_value=Path("x.json")),
        ]
        for p in self._patches:
            p.start()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def _save(self, **over):
        draft = _draft("route-draft", **{"imageUrl": "", **over})
        _write(self.root, draft)
        return draft

    def test_approve_refused_until_photo_is_attached(self):
        self._save()
        res = self.client.post("/api/intel/gmb/draft/route-draft/approve")
        self.assertEqual(res.status_code, 409)
        self.assertIn("photo_missing", res.get_json()["problems"])

    def test_photo_upload_then_approve_works_and_rebuilds_plan(self):
        self._save()
        jpg = _jpeg_bytes()
        res = self.client.post(
            "/api/intel/gmb/draft/route-draft/photo",
            data={"file": (__import__("io").BytesIO(jpg), "fitting.jpg")},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 200, res.get_json())
        saved_path = res.get_json()["draft"]["imageUrl"]
        self.assertTrue(Path(saved_path).is_file())
        res = self.client.post("/api/intel/gmb/draft/route-draft/approve", json={"photoMatch": True})
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertTrue(res.get_json()["plan_rebuilt"])

    def test_approve_refused_until_photo_match_is_confirmed(self):
        self._save(imageUrl=str(self.media / "x.jpg"))
        (self.media / "x.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 64)
        res = self.client.post("/api/intel/gmb/draft/route-draft/approve", json={})
        self.assertEqual(res.status_code, 409)
        self.assertIn("photo_match_not_confirmed", res.get_json()["problems"])

    def test_photo_file_only_serves_files_in_the_media_folder(self):
        outside = Path(self._tmp.name) / "secret.jpg"
        outside.write_bytes(b"\xff\xd8\xff" + b"0" * 8)
        self._save(imageUrl=str(outside))
        res = self.client.get("/api/intel/gmb/draft/route-draft/photo-file")
        self.assertEqual(res.status_code, 404)

    def test_resize_keeps_the_original_and_shrinks_the_copy(self):
        from PIL import Image  # noqa: PLC0415

        src_path = self.media / "big.png"
        Image.new("RGB", (3000, 1500), (10, 120, 80)).save(src_path)
        out = self.media / "big.jpg"
        gbp.resize_photo(src_path, out, max_side=2000)
        self.assertEqual(Image.open(out).size, (2000, 1000))
        self.assertEqual(Image.open(src_path).size, (3000, 1500))

    def test_photo_that_is_not_an_image_is_refused(self):
        self._save()
        res = self.client.post(
            "/api/intel/gmb/draft/route-draft/photo",
            data={"file": (__import__("io").BytesIO(b"hello"), "fitting.jpg")},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(list(self.media.iterdir()), [])


class TodayCardRouteTests(unittest.TestCase):
    """The Today card: pending shows the draft and its photo; approve refuses a post that moved on."""

    def setUp(self):
        import app as app_module  # noqa: PLC0415

        self.app_module = app_module
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "gmb-drafts"
        self.media = Path(self._tmp.name) / "media"
        self.root.mkdir()
        self.media.mkdir()
        photo = self.media / "card.jpg"
        photo.write_bytes(_jpeg_bytes())
        _write(self.root, _draft("card-draft", status="approved", approvedAt="2026-10-15T10:00:00Z",
                                 imageUrl=str(photo)))
        self._patches = [
            mock.patch.object(app_module, "GMB_DRAFTS_DIR", str(self.root)),
            mock.patch.object(app_module, "ASSET_MEDIA_DIR", str(self.media)),
            mock.patch.object(app_module._gdp, "GMB_DRAFTS_DIR", self.root),
            mock.patch.object(app_module._gdp, "save_plan", return_value=Path("x.json")),
            mock.patch.object(app_module._gdp, "latest_plan",
                              side_effect=lambda b: app_module._gdp.rebuild_plan(b, drafts_dir=self.root)),
        ]
        for p in self._patches:
            p.start()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_pending_names_the_draft_and_its_photo(self):
        res = self.client.get("/api/gbp/daily-poster/pending?brand_id=swing-shack")
        post = res.get_json()["post"]
        self.assertEqual(post["draft_id"], "card-draft")
        self.assertTrue(post["has_photo"])
        self.assertEqual(post["photo_url"], "/api/intel/gmb/draft/card-draft/photo-file")

    def test_approve_refuses_a_post_that_is_no_longer_the_one_shown(self):
        res = self.client.post("/api/gbp/daily-poster/approve?brand_id=swing-shack",
                               json={"draft_id": "some-other-draft"})
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.get_json()["error"], "stale")


if __name__ == "__main__":
    unittest.main()
