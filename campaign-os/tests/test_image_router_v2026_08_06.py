"""
test_image_router_v2026_08_06.py — Tests for the unified image router + 4 new routes.

Exercises:
  _lib/image_gen_router.py     — pure-Python unit tests (no network)
  GET  /api/image/status       — capability check (returns ok, no key values)
  POST /api/image/generate     — auth / bad request / happy path (mocked upstream)
  POST /api/image/edit         — auth / bad request / happy path (mocked upstream)
  POST /api/image/from-asset/<id> — asset_id resolution across data/
  Back-compat: existing /api/visual-library/<brand>/generate still works

Strategy:
  - Unit tests on the router use mocks for the network layer; we never hit
    OpenAI or OpenRouter during tests.
  - HTTP route tests use Flask's test_client and mock the router layer.
  - Live integration (real upstream call) is exercised by the smoke test in
    scripts/smoke_test_image_router.py — separate from CI.
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))


# ── Helper: a 1×1 transparent PNG (smallest valid PNG) ──────────────
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _png_data_url() -> str:
    return "data:image/png;base64," + base64.b64encode(PNG_1x1).decode("ascii")


# ── Mock upstream responses ──────────────────────────────────────────

def _mock_openrouter_generate_response(model: str = "google/gemini-2.5-flash-image") -> dict:
    return {
        "id": "gen-test-1234",
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "",
                "images": [{"image_url": {"url": _png_data_url()}}],
            },
        }],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 1290,
            "total_tokens": 1340,
            "cost": 0.0391,
        },
    }


def _mock_openai_generate_response() -> dict:
    return {
        "created": 1234567890,
        "data": [{"b64_json": base64.b64encode(PNG_1x1).decode("ascii"), "revised_prompt": "A 1024x1024 editorial image of a fitted Mizuno iron with golden accent"}],
    }


# ─────────────────────────────────────────────────────────────────────
# Pure-router unit tests (no Flask, no real network)
# ─────────────────────────────────────────────────────────────────────

class ImageRouterUnitTests(unittest.TestCase):
    """Unit tests for the image router. Patches upstream callers."""

    def setUp(self):
        from _lib import image_gen_router as router
        self.router = router

    def test_status_report_shape(self):
        """status_report() returns the documented shape without echoing keys."""
        s = self.router.status_report()
        self.assertIn("configured", s)
        self.assertIn("providers", s)
        self.assertIn("active_provider", s)
        self.assertIn("active_model", s)
        self.assertIn("valid_sizes", s)
        self.assertIn("max_cost_default_usd", s)
        # No key values should be in the response
        self.assertNotIn("api_key", s)
        self.assertNotIn("key", s)
        self.assertNotIn("token", s)
        # Both providers present
        self.assertIn("openai", s["providers"])
        self.assertIn("openrouter", s["providers"])
        # OpenRouter supports edit
        self.assertTrue(s["providers"]["openrouter"]["supports_edit"])
        # OpenAI direct does not support edit
        self.assertFalse(s["providers"]["openai"]["supports_edit"])

    def test_enhance_prompt_with_recipe(self):
        """Brand recipe DNA merges into the prompt when quality filter passes."""
        recipe = {
            "palette": {"primary": "orange"},
            "mood": {"primary": "cinematic"},
            "objects": {"primary": "golf ball"},
            "summary": "Premium golf editorial",
        }
        out = self.router.enhance_prompt_with_recipe("fitted driver", recipe)
        self.assertIn("fitted driver", out)
        self.assertIn("dominant color: orange", out)
        self.assertIn("mood: cinematic", out)
        self.assertIn("subject: golf ball", out)
        self.assertIn("brand context: Premium golf editorial", out)

    def test_enhance_prompt_skips_junk(self):
        """Recipe fields with quality flags are skipped."""
        recipe = {
            "palette": {"primary": "other"},
            "mood": {"primary": "neutral"},
            "objects": {"primary": "general"},
            "summary": "ok",
        }
        # Tighten the summary filter — skip if shorter than 4 meaningful chars
        # (or any of the standard junk values)
        out = self.router.enhance_prompt_with_recipe("fitted driver", recipe)
        # Expect "fitted driver" only — short "ok" summary is junk
        self.assertEqual(out, "fitted driver")

    def test_enhance_prompt_handles_none(self):
        """None recipe returns the prompt unchanged."""
        out = self.router.enhance_prompt_with_recipe("fitted driver", None)
        self.assertEqual(out, "fitted driver")

    def test_logo_preserve_detection(self):
        """Detector flags instructions that ask the model to preserve text/logo."""
        self.assertTrue(self.router._detect_logo_preserve_drift("preserve the logo exactly"))
        self.assertTrue(self.router._detect_logo_preserve_drift("don't change the text"))
        self.assertTrue(self.router._detect_logo_preserve_drift("leave the wordmark alone"))
        self.assertFalse(self.router._detect_logo_preserve_drift("change background to pink"))
        self.assertFalse(self.router._detect_logo_preserve_drift("add a gold accent"))

    def test_detect_mime(self):
        """MIME detection from raw bytes, not filename."""
        self.assertEqual(self.router._detect_mime(PNG_1x1), "image/png")
        # JPEG magic
        jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 50
        self.assertEqual(self.router._detect_mime(jpeg), "image/jpeg")
        # WebP magic
        webp = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 50
        self.assertEqual(self.router._detect_mime(webp), "image/webp")
        # GIF magic
        gif = b"GIF89a" + b"\x00" * 50
        self.assertEqual(self.router._detect_mime(gif), "image/gif")

    def test_data_url_construction(self):
        url = self.router._data_url(PNG_1x1)
        self.assertTrue(url.startswith("data:image/png;base64,"))
        self.assertIn(base64.b64encode(PNG_1x1).decode("ascii"), url)

    def test_cost_from_usage(self):
        """Cost extraction from usage dict; never invents."""
        self.assertEqual(self.router._cost_from_usage({"cost": 0.0391}), 0.0391)
        self.assertEqual(self.router._cost_from_usage({}), 0.0)
        self.assertEqual(self.router._cost_from_usage(None), 0.0)
        self.assertEqual(self.router._cost_from_usage({"cost": "bad"}), 0.0)

    def test_generate_image_bad_request(self):
        """Empty prompt raises ImageGenBadRequest."""
        with self.assertRaises(self.router.ImageGenBadRequest):
            self.router.generate_image("")

    def test_generate_image_no_credentials_openai(self):
        """If OpenAI is selected and key is missing, ImageGenAuthError."""
        with patch.object(self.router, "_resolve_openai_key", return_value=None):
            with self.assertRaises(self.router.ImageGenAuthError):
                self.router.generate_image("test prompt", provider="openai")

    def test_generate_image_no_credentials_openrouter(self):
        """If OpenRouter is selected and key is missing, ImageGenAuthError."""
        with patch.object(self.router, "_resolve_openrouter_key", return_value=None):
            with self.assertRaises(self.router.ImageGenAuthError):
                self.router.generate_image("test prompt", provider="openrouter")

    def test_generate_image_openrouter_happy_path(self):
        """OpenRouter path: mocked upstream returns PNG bytes + cost."""
        with patch.object(self.router, "_resolve_openrouter_key", return_value="sk-or-test"):
            with patch.object(self.router, "_call_openrouter_multimodal", return_value=_mock_openrouter_generate_response()):
                r = self.router.generate_image("fitted driver with yellow accent", provider="openrouter")
                self.assertIsInstance(r, self.router.GenResult)
                self.assertEqual(len(r.bytes), len(PNG_1x1))
                self.assertEqual(r.mime, "image/png")
                self.assertEqual(r.model, "google/gemini-2.5-flash-image")
                self.assertEqual(r.provider, "openrouter")
                self.assertAlmostEqual(r.cost_estimate_usd, 0.0391, places=3)
                self.assertIn("fitted driver", r.prompt_used)
                self.assertEqual(r.warning, None)
                self.assertNotIn("logo", r.warning or "")  # explicit no warn

    def test_generate_image_openai_happy_path(self):
        """OpenAI direct path: mocked upstream returns b64_json."""
        with patch.object(self.router, "_resolve_openai_key", return_value="sk-test"):
            with patch.object(self.router, "_call_openai_generate", return_value=_mock_openai_generate_response()):
                r = self.router.generate_image("fitted driver", provider="openai")
                self.assertIsInstance(r, self.router.GenResult)
                self.assertEqual(r.provider, "openai")
                self.assertEqual(r.model, "gpt-image-1")
                self.assertTrue(len(r.bytes) > 0)
                self.assertEqual(r.mime, "image/png")
                # revised_prompt comes from OpenAI response
                self.assertIn("Mizuno", r.revised_prompt or "")

    def test_generate_image_with_persistence(self):
        """Persistence writes to brand-directory/<brand>/images/gen-<ts>.png + sidecar."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(self.router, "_resolve_openrouter_key", return_value="sk-or-test"):
                with patch.object(self.router, "_call_openrouter_multimodal", return_value=_mock_openrouter_generate_response()):
                    r = self.router.generate_image_with_persistence(
                        "test prompt",
                        brand_id="test-brand",
                        provider="openrouter",
                        output_base=tmp,
                    )
                    self.assertIsNotNone(r.saved_path)
                    self.assertIsNotNone(r.saved_sidecar_path)
                    saved = Path(r.saved_path)
                    self.assertTrue(saved.exists())
                    self.assertTrue(saved.read_bytes() == PNG_1x1)
                    sidecar = json.loads(Path(r.saved_sidecar_path).read_text())
                    self.assertEqual(sidecar["model"], "google/gemini-2.5-flash-image")
                    self.assertEqual(sidecar["provider"], "openrouter")
                    self.assertAlmostEqual(sidecar["cost_estimate_usd"], 0.0391, places=3)

    def test_edit_image_bad_request(self):
        """Empty source or instruction raises ImageGenBadRequest."""
        with self.assertRaises(self.router.ImageGenBadRequest):
            self.router.edit_image(b"", "instruction")
        with self.assertRaises(self.router.ImageGenBadRequest):
            self.router.edit_image(PNG_1x1, "")

    def test_edit_image_rejects_openai(self):
        """OpenAI direct does not support edit; raises ImageGenBadRequest."""
        with patch.object(self.router, "_resolve_openrouter_key", return_value="sk-or-test"):
            with self.assertRaises(self.router.ImageGenBadRequest):
                self.router.edit_image(PNG_1x1, "recolor to pink", provider="openai")

    def test_edit_image_logo_preserve_warning(self):
        """Edit instruction that asks to preserve text triggers warning."""
        with patch.object(self.router, "_resolve_openrouter_key", return_value="sk-or-test"):
            with patch.object(self.router, "_call_openrouter_multimodal", return_value=_mock_openrouter_generate_response()):
                r = self.router.edit_image(PNG_1x1, "preserve the wordmark exactly")
                self.assertIsNotNone(r.warning)
                self.assertIn("logo", r.warning.lower())

    def test_edit_image_happy_path(self):
        """Edit returns bytes + cost."""
        with patch.object(self.router, "_resolve_openrouter_key", return_value="sk-or-test"):
            with patch.object(self.router, "_call_openrouter_multimodal", return_value=_mock_openrouter_generate_response()):
                r = self.router.edit_image(PNG_1x1, "change background to pink")
                self.assertIsInstance(r, self.router.EditResult)
                self.assertEqual(r.mime, "image/png")
                self.assertEqual(r.model, "google/gemini-2.5-flash-image")
                self.assertAlmostEqual(r.cost_estimate_usd, 0.0391, places=3)
                self.assertEqual(r.warning, None)


# ─────────────────────────────────────────────────────────────────────
# Flask route tests (with router mocked)
# ─────────────────────────────────────────────────────────────────────

class ImageRouterRouteTests(unittest.TestCase):
    """HTTP route tests via Flask test_client. Router is patched."""

    @classmethod
    def setUpClass(cls):
        # Set up a temp DATA_DIR with seed data files for asset_id lookup
        cls._tmp = tempfile.mkdtemp()
        os.environ["DATA_DIR"] = cls._tmp
        # Seed hook-bank
        (Path(cls._tmp) / "hook-bank.json").write_text(json.dumps({
            "hooks": [
                {"id": "hk-test-001", "text": "Hit longer drives this winter"},
                {"id": "hk-test-002", "text": "Book a custom club fitting in JHB"},
            ]
        }))
        # Seed captions
        (Path(cls._tmp) / "captions.json").write_text(json.dumps({
            "captions": [
                {"id": "cp-test-001", "text": "Winter training montage"},
            ]
        }))
        # Seed headlines
        (Path(cls._tmp) / "headlines.json").write_text(json.dumps({
            "headlines": [
                {"id": "hl-test-001", "text": "Drive distance up 15% this winter"},
            ]
        }))

        # Import app with patched paths
        import importlib
        import app as app_mod
        app_mod.DATA_DIR = cls._tmp
        # Patch _data_paths
        cls._orig_data_paths = app_mod._data_paths
        def _patched_data_paths():
            return {'data_dir': cls._tmp, 'campaign_file': os.path.join(cls._tmp, 'campaign-data.json'), 'schedule_file': os.path.join(cls._tmp, 'scheduled-items.json')}
        app_mod._data_paths = _patched_data_paths

        # The from-asset route reads from BUNDLED_DATA_DIR — patch it to our tmp
        # so the seeded hook-bank.json / captions.json / headlines.json are found.
        cls._orig_bundled = app_mod.BUNDLED_DATA_DIR
        app_mod.BUNDLED_DATA_DIR = cls._tmp

        cls._app = app_mod.app
        cls._client = cls._app.test_client()

        # Login once — the app has an auth gate. Subsequent requests reuse
        # the session cookie.
        cls._client.post("/login", data={"password": "swing-shack-dev-2026"})

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("DATA_DIR", None)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    # ── /api/image/status ───────────────────────────────────────────

    def test_status_route_returns_ok(self):
        r = self._client.get("/api/image/status")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d.get("ok"))
        self.assertIn("providers", d)
        self.assertIn("active_provider", d)
        self.assertNotIn("api_key", json.dumps(d))

    # ── /api/image/generate ─────────────────────────────────────────

    def test_generate_route_bad_request_no_prompt(self):
        r = self._client.post("/api/image/generate", json={})
        self.assertEqual(r.status_code, 400)
        d = r.get_json()
        self.assertFalse(d.get("ok"))
        self.assertIn("prompt", d.get("error", "").lower())

    def test_generate_route_happy_path(self):
        """Happy path with router mocked — returns base64 bytes + metadata."""
        from _lib import image_gen_router as router
        mock_result = router.GenResult(
            bytes=PNG_1x1,
            mime="image/png",
            model="google/gemini-2.5-flash-image",
            provider="openrouter",
            cost_estimate_usd=0.0391,
            prompt_used="test prompt used",
            revised_prompt=None,
            saved_path=None,
            warning=None,
            usage={"prompt_tokens": 50, "completion_tokens": 1290, "cost": 0.0391},
        )
        with patch.object(router, "generate_image", return_value=mock_result):
            r = self._client.post("/api/image/generate", json={
                "prompt": "Editorial shot of fitted driver",
                "brand_id": "swing-shack",
                "save": False,
            })
            self.assertEqual(r.status_code, 200)
            d = r.get_json()
            self.assertTrue(d.get("ok"))
            self.assertEqual(d["model"], "google/gemini-2.5-flash-image")
            self.assertEqual(d["provider"], "openrouter")
            self.assertIn("bytes_b64", d)
            # Round-trip base64
            roundtrip = base64.b64decode(d["bytes_b64"])
            self.assertEqual(roundtrip, PNG_1x1)
            self.assertAlmostEqual(d["cost_estimate_usd"], 0.0391, places=3)

    def test_generate_route_auth_error(self):
        """If router raises ImageGenAuthError, route returns 503."""
        from _lib import image_gen_router as router
        with patch.object(router, "generate_image", side_effect=router.ImageGenAuthError("no key")):
            r = self._client.post("/api/image/generate", json={"prompt": "test", "save": False})
            self.assertEqual(r.status_code, 503)
            d = r.get_json()
            self.assertFalse(d.get("ok"))
            self.assertEqual(d.get("code"), "auth")

    # ── /api/image/edit ─────────────────────────────────────────────

    def test_edit_route_bad_request_no_instruction(self):
        r = self._client.post("/api/image/edit", json={"source_b64": base64.b64encode(PNG_1x1).decode("ascii")})
        self.assertEqual(r.status_code, 400)
        d = r.get_json()
        self.assertFalse(d.get("ok"))
        self.assertIn("instruction", d.get("error", "").lower())

    def test_edit_route_bad_request_no_source(self):
        r = self._client.post("/api/image/edit", json={"instruction": "recolor"})
        self.assertEqual(r.status_code, 400)
        d = r.get_json()
        self.assertFalse(d.get("ok"))

    def test_edit_route_happy_path(self):
        from _lib import image_gen_router as router
        mock_result = router.EditResult(
            bytes=PNG_1x1,
            mime="image/png",
            model="google/gemini-2.5-flash-image",
            provider="openrouter",
            cost_estimate_usd=0.0391,
            instruction_used="change background to pink",
            saved_path=None,
            warning=None,
            usage={"cost": 0.0391},
        )
        with patch.object(router, "edit_image", return_value=mock_result):
            r = self._client.post("/api/image/edit", json={
                "instruction": "change background to pink",
                "source_b64": base64.b64encode(PNG_1x1).decode("ascii"),
                "save": False,
            })
            self.assertEqual(r.status_code, 200)
            d = r.get_json()
            self.assertTrue(d.get("ok"))
            self.assertIn("bytes_b64", d)

    # ── /api/image/from-asset/<id> ──────────────────────────────────

    def test_from_asset_route_unknown_id(self):
        r = self._client.post("/api/image/from-asset/this-id-does-not-exist", json={})
        self.assertEqual(r.status_code, 404)

    def test_from_asset_route_hook_match(self):
        """Hook id matches data/hook-bank.json → prompt extracted."""
        from _lib import image_gen_router as router
        mock_result = router.GenResult(
            bytes=PNG_1x1, mime="image/png",
            model="google/gemini-2.5-flash-image", provider="openrouter",
            cost_estimate_usd=0.0391, prompt_used="Hit longer drives",
            warning=None, usage={"cost": 0.0391},
            saved_path="/tmp/something.png",
            saved_sidecar_path="/tmp/something.png.meta.json",
        )
        with patch.object(router, "generate_image", return_value=mock_result):
            with patch.object(router, "_persist", return_value=("/tmp/something.png", "/tmp/something.png.meta.json")):
                r = self._client.post("/api/image/from-asset/hk-test-001", json={})
                self.assertEqual(r.status_code, 200)
                d = r.get_json()
                self.assertTrue(d.get("ok"))
                self.assertEqual(d["asset_kind"], "hook")
                self.assertEqual(d["asset_id"], "hk-test-001")
                self.assertIn("Hit longer drives", d["extracted_prompt"])

    def test_from_asset_route_caption_match(self):
        """Caption id matches data/captions.json."""
        from _lib import image_gen_router as router
        mock_result = router.GenResult(
            bytes=PNG_1x1, mime="image/png",
            model="google/gemini-2.5-flash-image", provider="openrouter",
            cost_estimate_usd=0.0391, prompt_used="Winter training montage",
            warning=None, usage={"cost": 0.0391},
            saved_path=None, saved_sidecar_path=None,
        )
        with patch.object(router, "generate_image", return_value=mock_result):
            with patch.object(router, "_persist", return_value=(None, None)):
                r = self._client.post("/api/image/from-asset/cp-test-001", json={})
                self.assertEqual(r.status_code, 200)
                d = r.get_json()
                self.assertEqual(d["asset_kind"], "caption")
                self.assertIn("Winter training", d["extracted_prompt"])

    # ── back-compat: existing route still wired ──────────────────────

    def test_visual_library_generate_route_still_registered(self):
        """Existing /api/visual-library/<brand>/generate route is still available."""
        # 503 (auth) or 400 (no prompt) both prove the route is alive
        r = self._client.post("/api/visual-library/swing-shack/generate", json={})
        self.assertIn(r.status_code, (400, 503, 502))


# ─────────────────────────────────────────────────────────────────────
# Smoke-test entry — run with `python -m unittest test_image_router_v2026_08_06.py`
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)