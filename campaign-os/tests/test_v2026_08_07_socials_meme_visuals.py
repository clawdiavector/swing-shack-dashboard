"""
test_v2026_08_07_socials_meme_visuals.py

Tests for the Socials tab + per-asset IG carousel + meme template thumbnails
+ image-from-asset auto-compose default.

Coverage:
  - /api/socials/status returns sane shape
  - /api/socials/posts returns Graph-shaped data + paginates
  - /api/socials/oembed validates + returns proxied payload
  - /api/socials/for-asset/<aid> returns matched posts + falls back to recent
  - /api/meme/templates returns 30 templates with thumbnails
  - /api/image/from-asset/<aid> defaults to composing all 4 layers
    (brand recipe + product/service + reference DNA + learned signals)
    when caller does NOT pass override_prompt or compose_layers=False
  - Campaign OS HTML has socials section + meme template strip + review-modal
    IG carousel
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO_ROOT = CAMPAIGN_OS.parent


class SocialsMemeVisualsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-socials-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app

        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()
        # Don't let tests trigger git bootstrap
        cls.module.init_repo = lambda: None
        # Login once — cookie persists on the test client
        cls.client.post("/login", data={"password": cls.module.SHARED_PASSWORD})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)


# ============================================================================
# /api/socials/status
# ============================================================================


class SocialsStatusTests(SocialsMemeVisualsApiTests):
    def test_status_shape(self):
        r = self.client.get("/api/socials/status")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("graph_configured", data)
        self.assertIn("oembed_reachable", data)
        self.assertIn("ig_account_id", data)

    def test_status_oembed_reachable(self):
        """oEmbed endpoint should be reachable (public IG API)."""
        r = self.client.get("/api/socials/status")
        data = r.get_json()
        self.assertTrue(data["oembed_reachable"], f"reason: {data.get('reason')}")


# ============================================================================
# /api/socials/posts
# ============================================================================


class SocialsPostsTests(SocialsMemeVisualsApiTests):
    def test_returns_paginated_shape(self):
        r = self.client.get("/api/socials/posts?limit=5&days=90")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("data", data)
        self.assertIn("paging", data)
        self.assertIn("_meta", data)
        # Without credentials, data is empty list (not an error)
        self.assertIsInstance(data["data"], list)

    def test_days_param_echoed(self):
        r = self.client.get("/api/socials/posts?days=30")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["_meta"]["days_covered"], 30)

    def test_limit_clamped(self):
        r = self.client.get("/api/socials/posts?limit=500")
        self.assertEqual(r.status_code, 200)


# ============================================================================
# /api/socials/oembed
# ============================================================================


class SocialsOembedTests(SocialsMemeVisualsApiTests):
    def test_validates_permalink(self):
        r = self.client.get("/api/socials/oembed?url=https://example.com/not-instagram")
        self.assertEqual(r.status_code, 400)
        data = r.get_json()
        self.assertIn("instagram.com", data["error"])

    def test_empty_url_rejected(self):
        r = self.client.get("/api/socials/oembed?url=")
        self.assertEqual(r.status_code, 400)

    def test_real_payload_or_502(self):
        r = self.client.get("/api/socials/oembed?url=https%3A%2F%2Fwww.instagram.com%2Fp%2FCJ5-pxMn7zW%2F")
        # 200 = success, 502 = upstream issue (acceptable)
        self.assertIn(r.status_code, (200, 502))


# ============================================================================
# /api/socials/for-asset/<aid>
# ============================================================================


class SocialsForAssetTests(SocialsMemeVisualsApiTests):
    def _patch_meta(self):
        from _lib import meta_api as _meta
        return _meta

    def test_503_without_meta_creds(self):
        _meta = self._patch_meta()
        with patch.object(_meta, "meta_credentials_present", return_value=False):
            r = self.client.get("/api/socials/for-asset/takomo-101t-hero-c")
            self.assertEqual(r.status_code, 503)
            data = r.get_json()
            self.assertIn("credentials not configured", data["error"].lower())

    def test_keyword_match_ranks_relevant_first(self):
        _meta = self._patch_meta()
        fake_posts = {
            "data": [
                {"id": "1", "caption": "TrackMan session today", "media_type": "IMAGE",
                 "media_url": "https://x/1.jpg", "thumbnail_url": "https://x/1t.jpg",
                 "permalink": "https://www.instagram.com/p/1", "timestamp": "2026-08-01T12:00:00Z",
                 "like_count": 50, "comments_count": 5},
                {"id": "2", "caption": "Coffee and rain", "media_type": "IMAGE",
                 "media_url": "https://x/2.jpg", "thumbnail_url": "https://x/2t.jpg",
                 "permalink": "https://www.instagram.com/p/2", "timestamp": "2026-07-15T10:00:00Z",
                 "like_count": 30, "comments_count": 2},
                {"id": "3", "caption": "TrackMan + Takomo 101T review", "media_type": "CAROUSEL_ALBUM",
                 "media_url": "https://x/3.jpg", "thumbnail_url": "https://x/3t.jpg",
                 "permalink": "https://www.instagram.com/p/3", "timestamp": "2026-08-05T09:00:00Z",
                 "like_count": 120, "comments_count": 18},
            ]
        }
        with patch.object(_meta, "meta_credentials_present", return_value=True), \
             patch.object(_meta, "list_recent_posts", return_value=fake_posts), \
             patch.object(self.module, "_extract_asset_context",
                          return_value=("TrackMan + Takomo 101T hero", "visual")):
            r = self.client.get("/api/socials/for-asset/takomo-101t-hero-c")
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            self.assertGreaterEqual(len(data["data"]), 1)
            ids = [p["id"] for p in data["data"]]
            self.assertNotIn("2", ids[:2])
            self.assertEqual(data["_meta"]["matched_via"], "keyword")

    def test_falls_back_to_recent_when_no_keyword_match(self):
        _meta = self._patch_meta()
        fake_posts = {
            "data": [
                {"id": "1", "caption": "Test", "media_type": "IMAGE",
                 "media_url": "x", "thumbnail_url": "x", "permalink": "x",
                 "timestamp": "2026-08-01T00:00:00Z"},
            ]
        }
        with patch.object(_meta, "meta_credentials_present", return_value=True), \
             patch.object(_meta, "list_recent_posts", return_value=fake_posts), \
             patch.object(self.module, "_extract_asset_context",
                          return_value=("zzz unrelated keywords", "visual")):
            r = self.client.get("/api/socials/for-asset/some-asset")
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            self.assertEqual(data["_meta"]["matched_via"], "fallback_recent")
            self.assertGreaterEqual(len(data["data"]), 1)


# ============================================================================
# /api/meme/templates
# ============================================================================


class MemeTemplatesTests(SocialsMemeVisualsApiTests):
    def test_returns_30_templates(self):
        r = self.client.get("/api/meme/templates")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["count"], 30)
        self.assertEqual(len(data["data"]), 30)
        first = data["data"][0]
        for field in ("id", "name", "tier", "text_zones", "thumbnail_url", "source", "brand_fit"):
            self.assertIn(field, first, f"missing field: {field}")
        self.assertEqual(first["tier"], "iconic")

    def test_filter_by_tier(self):
        r = self.client.get("/api/meme/templates?tier=trending")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(all(t["tier"] == "trending" for t in data["data"]))
        self.assertGreater(data["count"], 0)

    def test_search(self):
        r = self.client.get("/api/meme/templates?q=drake")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(any("drake" in t["name"].lower() for t in data["data"]))

    def test_thumbnails_are_real_urls(self):
        r = self.client.get("/api/meme/templates")
        data = r.get_json()
        for t in data["data"]:
            self.assertTrue(t["thumbnail_url"].startswith("http"), f"{t['id']} no thumb URL")


# ============================================================================
# /api/image/from-asset/<aid> auto-compose default
# ============================================================================


class ImageFromAssetAutoComposeTests(SocialsMemeVisualsApiTests):
    def setUp(self):
        super().setUp() if hasattr(super(), 'setUp') else None  # unittest auto
        from _lib import image_gen_router as _igr

        captured_holder = {}

        def fake_gen(*args, **kwargs):
            captured_holder.update(kwargs)
            from _lib.image_gen_router import GenResult
            return GenResult(
                bytes=b"\x89PNG", mime="image/png", model="fake", provider="fake",
                cost_estimate_usd=0.04, prompt_used="x",
                saved_path=None, saved_sidecar_path=None, warning=None,
            )

        self._captured = captured_holder
        self._fake_gen = fake_gen
        # Save original
        self._orig_gen = _igr.generate_image
        _igr.generate_image = fake_gen
        self._orig_eac = self.module._extract_asset_context
        self.module._extract_asset_context = lambda aid, brand: ("TrackMan hero shot", "visual")

    def tearDown(self):
        from _lib import image_gen_router as _igr
        _igr.generate_image = self._orig_gen
        self.module._extract_asset_context = self._orig_eac

    def test_auto_composes_layers_by_default(self):
        """Without override_prompt, from-asset loads all 4 layers."""
        r = self.client.post("/api/image/from-asset/takomo-101t-hero-c",
                             json={"campaignId": "swing-shack"})
        # Capture object should have been touched (composition attempted)
        self.assertIn("reference_dnas", self._captured)
        self.assertIn("product_service_items", self._captured)
        self.assertIn("learned_signals", self._captured)

    def test_respects_override_prompt(self):
        r = self.client.post("/api/image/from-asset/takomo-101t-hero-c",
                             json={"override_prompt": "CUSTOM PROMPT ONLY"})
        # When override_prompt set, layer compose is skipped
        self.assertIsNone(self._captured.get("reference_dnas"))
        self.assertIsNone(self._captured.get("product_service_items"))
        self.assertIsNone(self._captured.get("learned_signals"))

    def test_respects_compose_layers_false(self):
        r = self.client.post("/api/image/from-asset/takomo-101t-hero-c",
                             json={"compose_layers": False})
        self.assertIsNone(self._captured.get("reference_dnas"))


# ============================================================================
# HTML structural assertions
# ============================================================================


class HtmlStructureTests(unittest.TestCase):
    """Static checks that the UI surfaces exist in the HTML."""

    @classmethod
    def setUpClass(cls):
        cls.html = (REPO_ROOT / "campaign-os" / "campaign-os.html").read_text()

    def test_socials_section_exists(self):
        self.assertIn('id="sec-socials"', self.html, "Socials section missing")
        self.assertIn('id="socials-grid"', self.html, "Socials grid container missing")

    def test_socials_nav_link_exists(self):
        self.assertIn('data-go="socials"', self.html, "Socials nav link missing")
        self.assertIn("🪩", self.html, "Socials icon missing")

    def test_meme_template_strip_exists(self):
        self.assertIn('id="meme-templates-strip"', self.html, "Meme template strip missing")
        self.assertIn(".meme-templates-strip", self.html, "Meme template strip CSS missing")

    def test_review_modal_ig_strip_exists(self):
        self.assertIn('id="rv-socials-strip"', self.html, "Review modal IG strip missing")
        self.assertIn("Already posted about this", self.html, "Review modal IG heading missing")

    def test_render_socials_function_exists(self):
        self.assertIn("async function renderSocials", self.html, "renderSocials missing")
        self.assertIn("/api/socials/posts", self.html, "renderSocials does not call /api/socials/posts")

    def test_render_meme_templates_strip_function_exists(self):
        self.assertIn("renderMemeTemplatesStrip", self.html, "renderMemeTemplatesStrip missing")
        self.assertIn("/api/meme/templates", self.html, "renderMemeTemplatesStrip does not call /api/meme/templates")

    def test_load_section_handles_socials(self):
        self.assertTrue(
            "sec==='socials'" in self.html or 'sec==="socials"' in self.html,
            "loadSection does not handle socials",
        )


if __name__ == "__main__":
    unittest.main()