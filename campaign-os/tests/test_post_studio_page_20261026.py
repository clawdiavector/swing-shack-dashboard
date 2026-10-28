"""Post studio page API — field metadata and compose preview (T15, 2026-10-26)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
TOKEN = "test-job-token-not-a-secret"
BRAND = "swing-shack"
ARCHETYPE = "ss-fitting-headline"


class PostStudioPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-post-studio-page-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_SANDBOX_DIR", "COS_JOB_TOKEN")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
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
        os.environ["COS_JOB_TOKEN"] = TOKEN
        self.app_module.DATA_DIR = str(self.tmpdir)
        self.app_module.COS_JOB_TOKEN = TOKEN
        (self.tmpdir / "campaign-data.json").write_text(json.dumps({"campaigns": {}}))
        self.client = self.app_module.app.test_client(cos_anon=True)
        self.auth = {"Authorization": f"Bearer {TOKEN}"}

    def test_fields_lists_text_zones(self):
        r = self.client.get(
            f"/api/posts/studio/fields?brand={BRAND}&archetype={ARCHETYPE}",
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.get_json())
        doc = r.get_json()
        keys = {row["key"] for row in doc.get("fields") or []}
        self.assertIn("caption_hook", keys)
        self.assertIn("service_lockup", keys)

    def test_preview_returns_instagram_data_url(self):
        r = self.client.post(
            "/api/posts/studio/preview",
            json={
                "brand": BRAND,
                "archetype": ARCHETYPE,
                "channels": ["instagram"],
                "fields": {
                    "caption_hook": "YOU WOULDN'T DIG WITH A SPOON.",
                    "service_lockup": "WHY PLAY THE WRONG CLUBS?",
                },
            },
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.get_json())
        doc = r.get_json()
        self.assertTrue(doc.get("ok"))
        ig = (doc.get("images") or {}).get("instagram") or ""
        self.assertTrue(ig.startswith("data:image/png;base64,"), ig[:40])

    def _preview_with_photo(self, photo):
        return self.client.post(
            "/api/posts/studio/preview",
            json={"brand": BRAND, "archetype": ARCHETYPE, "channels": ["instagram"], "photo": photo},
            headers=self.auth,
        )

    def test_preview_refuses_photo_outside_brand_files(self):
        for photo in ("/etc/hostname", "data/brand-directory/swing-shack/../../../app.py", "app.py"):
            r = self._preview_with_photo(photo)
            self.assertEqual(r.status_code, 400, (photo, r.get_json()))

    def test_preview_missing_photo_is_400_not_exit(self):
        r = self._preview_with_photo(f"data/brand-directory/{BRAND}/images/no-such-file.jpg")
        self.assertEqual(r.status_code, 400, r.get_json())
        self.assertIn("photo not found", r.get_json().get("error", ""))

    def test_preview_refuses_unknown_archetype(self):
        r = self.client.post(
            "/api/posts/studio/preview",
            json={"brand": BRAND, "archetype": "not-a-template", "fields": {}},
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json().get("ok"))


if __name__ == "__main__":
    unittest.main()
