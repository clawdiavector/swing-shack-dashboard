"""Story reposts (2026-10-12): Foreman adds an Instagram/Facebook link from Telegram,
the Today page lists it, a person taps it and marks it done."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
TOKEN = "test-job-token-not-a-secret"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


class StoryQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-stories-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "COS_JOB_TOKEN")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["COS_JOB_TOKEN"] = TOKEN
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as app_module

        cls.app_module = app_module

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        os.environ["DATA_DIR"] = str(self.tmpdir)
        self.app_module.COS_JOB_TOKEN = TOKEN
        (self.tmpdir / "story-queue.json").unlink(missing_ok=True)
        self.client = self.app_module.app.test_client(cos_anon=True)

    def _add(self, **over):
        body = {"brand": "swing-shack", "url": "https://www.instagram.com/p/ABC123/?igsh=xyz",
                "note": "Psycho Bunny polo", "added_by": "Herman"}
        body.update(over)
        return self.client.post("/api/stories", json=body, headers=BEARER)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/stories").status_code, 401)
        self.assertEqual(
            self.client.post("/api/stories", json={"brand": "stick", "url": "instagram.com/p/x"}).status_code, 401)

    def test_add_strips_tracking_and_lists(self):
        r = self._add()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["item"]["url"], "https://instagram.com/p/ABC123")
        listed = self.client.get("/api/stories?brand=swing-shack", headers=BEARER).get_json()
        self.assertEqual(len(listed["open"]), 1)
        self.assertEqual(listed["open"][0]["added_by"], "Herman")
        self.assertEqual(self.client.get("/api/stories?brand=stick", headers=BEARER).get_json()["open"], [])

    def test_same_link_twice_is_not_duplicated(self):
        self._add()
        r = self._add(url="instagram.com/p/ABC123/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["created"])
        self.assertEqual(len(self.client.get("/api/stories", headers=BEARER).get_json()["open"]), 1)

    def test_rejects_other_sites_and_bad_brand(self):
        self.assertEqual(self._add(url="https://evil.example/instagram.com").status_code, 400)
        self.assertEqual(self._add(url="https://notinstagram.com/p/x").status_code, 400)
        self.assertEqual(self._add(brand="takomo").status_code, 400)
        self.assertEqual(self._add(url="").status_code, 400)

    def test_done_moves_to_done_today_and_can_be_undone(self):
        item_id = self._add().get_json()["item"]["id"]
        self.assertEqual(self.client.post(f"/api/stories/{item_id}/done", headers=BEARER).status_code, 200)
        listed = self.client.get("/api/stories", headers=BEARER).get_json()
        self.assertEqual((len(listed["open"]), len(listed["done_today"])), (0, 1))
        self.client.post(f"/api/stories/{item_id}/open", headers=BEARER)
        self.assertEqual(len(self.client.get("/api/stories", headers=BEARER).get_json()["open"]), 1)

    def test_unknown_id_and_status(self):
        self.assertEqual(self.client.post("/api/stories/nope/done", headers=BEARER).status_code, 404)
        item_id = self._add().get_json()["item"]["id"]
        self.assertEqual(self.client.post(f"/api/stories/{item_id}/bogus", headers=BEARER).status_code, 400)

    def test_postiz_requires_auth_and_known_id(self):
        self.assertEqual(self.client.post("/api/stories/nope/postiz").status_code, 401)
        self.assertEqual(self.client.post("/api/stories/nope/postiz", headers=BEARER).status_code, 404)

    def test_postiz_sandbox_does_not_publish(self):
        item_id = self._add().get_json()["item"]["id"]
        os.environ["PUBLISH_MODE"] = "sandbox"
        with patch("_lib.story_postiz.list_integrations") as listed:
            r = self.client.post(f"/api/stories/{item_id}/postiz", headers=BEARER)
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["dry_run"])
        self.assertFalse(body.get("postiz_post_id"))
        listed.assert_not_called()
        self.assertEqual(len(self.client.get("/api/stories", headers=BEARER).get_json()["open"]), 1)

    def test_postiz_live_posts_story_card_and_marks_done(self):
        item_id = self._add().get_json()["item"]["id"]
        os.environ["PUBLISH_MODE"] = "live"
        uploaded = {}

        def fake_upload(path, brand_id=None):
            uploaded["path"] = path
            uploaded["brand"] = brand_id
            self.assertTrue(str(path).endswith(".png"))
            self.assertGreater(os.path.getsize(path), 500)
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")
            return {"id": "media-1", "path": "https://cdn.example/story.png"}, None

        with patch("_lib.story_postiz.postiz_status", return_value={"configured": True}), \
             patch("_lib.story_postiz.list_integrations", return_value=([{"id": "ig-1", "providerIdentifier": "instagram"}], None)), \
             patch("_lib.story_postiz.upload_media", side_effect=fake_upload), \
             patch("_lib.story_postiz.create_post", return_value=({"id": "post-9"}, None)) as created, \
             patch("urllib.request.urlopen", side_effect=AssertionError("source post must not be downloaded")):
            r = self.client.post(f"/api/stories/{item_id}/postiz", headers=BEARER)
        self.assertEqual(r.status_code, 200, r.get_json())
        body = r.get_json()
        self.assertFalse(body["dry_run"])
        self.assertEqual(body["postiz_post_id"], "post-9")
        self.assertEqual(uploaded["brand"], "swing-shack")
        kwargs = created.call_args.kwargs
        self.assertEqual(kwargs["integration_id"], "ig-1")
        self.assertEqual(kwargs["platform_settings"], {"post_type": "story"})
        self.assertEqual(kwargs["media"], [{"id": "media-1", "path": "https://cdn.example/story.png"}])
        self.assertEqual(kwargs["content"], "Psycho Bunny polo")
        listed = self.client.get("/api/stories", headers=BEARER).get_json()
        self.assertEqual(len(listed["open"]), 0)
        self.assertEqual(listed["done_today"][0]["postiz_post_id"], "post-9")

    def test_postiz_missing_instagram_stays_open(self):
        item_id = self._add().get_json()["item"]["id"]
        os.environ["PUBLISH_MODE"] = "live"
        with patch("_lib.story_postiz.postiz_status", return_value={"configured": True}), \
             patch("_lib.story_postiz.list_integrations", return_value=([{"id": "fb-1", "providerIdentifier": "facebook"}], None)):
            r = self.client.post(f"/api/stories/{item_id}/postiz", headers=BEARER)
        self.assertEqual(r.status_code, 409)
        self.assertIn("Instagram", r.get_json()["error"])
        self.assertEqual(len(self.client.get("/api/stories", headers=BEARER).get_json()["open"]), 1)

    def tearDown(self):
        os.environ.pop("PUBLISH_MODE", None)


if __name__ == "__main__":
    unittest.main()
