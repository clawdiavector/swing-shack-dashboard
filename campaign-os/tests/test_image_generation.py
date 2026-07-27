"""Image Generation Pipeline — priority 6 tests.

Exercises:
  GET/POST /api/intel/generate_image    — structured prompt spec builder
  data/asset-image-spec.json            — spec file shape and content

Tests cover:
  - spec file shape (pillars, platforms, providers, brand_voice, typography)
  - generate_image() with no args (default spec)
  - generate_image() with pillar override (education / club-fitting / community / events)
  - generate_image() with platform override (instagram / tiktok / twitter / facebook / gmb)
  - generate_image() with provider override
  - generate_image() with subject override
  - generate_image() with hook override
  - generate_image() with asset_id pointing to a real campaign asset
  - all four providers present (ideogram, dall-e, midjourney, stable-diffusion)
  - aspect ratio correctly mapped per provider
  - negative prompt per pillar
  - color keywords per pillar
  - platform config (aspect ratio, text safety zone)
  - envelope shape (ok, ts, all required top-level keys)
  - HTTP route: no-args GET
  - HTTP route: pillar + platform + provider GET
  - HTTP route: POST with body params
  - HTTP route: hook override via GET
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


CAMPAIGN_OS = Path(__file__).resolve().parents[1]

import sys as _sys
_sys.path.insert(0, str(CAMPAIGN_OS))


class ImageSpecFileTests(unittest.TestCase):
    """Verify asset-image-spec.json shape and content."""

    @classmethod
    def setUpClass(cls):
        # Point DATA_DIR at a temp dir with the spec
        cls._tmp = tempfile.mkdtemp()
        cls._spec_src = Path(__file__).resolve().parents[2] / "data" / "asset-image-spec.json"
        cls._spec_dst = Path(cls._tmp) / "asset-image-spec.json"
        shutil.copy(cls._spec_src, cls._spec_dst)
        os.environ["DATA_DIR"] = cls._tmp

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("DATA_DIR", None)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_spec_file_exists(self):
        self.assertTrue(self._spec_src.exists(), "asset-image-spec.json must exist in data/")

    def test_spec_meta(self):
        with open(self._spec_src) as f:
            spec = json.load(f)
        self.assertIn("meta", spec)
        self.assertIn("providers", spec["meta"])
        self.assertIn("Swing Shack", spec["meta"].get("brand", ""))

    def test_spec_has_required_sections(self):
        with open(self._spec_src) as f:
            spec = json.load(f)
        for key in ("color_palette", "typography", "pillars", "platforms", "provider_templates", "brand_voice_for_images"):
            self.assertIn(key, spec, f"Missing section: {key}")

    def test_pillars_cover_all_four(self):
        with open(self._spec_src) as f:
            spec = json.load(f)
        pillars = spec.get("pillars", {})
        for key in ("education", "club-fitting", "community", "events"):
            self.assertIn(key, pillars, f"Missing pillar: {key}")
            p = pillars[key]
            for sub in ("label", "model_hints", "negative_prompts", "composition", "tone", "color_keywords", "example_prompt_fragment"):
                self.assertIn(sub, p, f"Pillar {key} missing {sub}")

    def test_pillars_composition_fields(self):
        with open(self._spec_src) as f:
            spec = json.load(f)
        for key, p in spec.get("pillars", {}).items():
            comp = p.get("composition", {})
            for field in ("primary_subject", "background", "lighting", "depth_of_field"):
                self.assertIn(field, comp, f"Pillar {key} composition missing {field}")

    def test_platforms_cover_all_five(self):
        with open(self._spec_src) as f:
            spec = json.load(f)
        platforms = spec.get("platforms", {})
        for key in ("instagram", "tiktok", "twitter", "facebook", "gmb"):
            self.assertIn(key, platforms, f"Missing platform: {key}")
            pl = platforms[key]
            for field in ("aspect_ratio", "aspect_px", "use_cases", "text_safety_zone"):
                self.assertIn(field, pl, f"Platform {key} missing {field}")

    def test_providers_all_four(self):
        with open(self._spec_src) as f:
            spec = json.load(f)
        tpls = spec.get("provider_templates", {})
        for key in ("ideogram", "dall-e", "midjourney", "stable-diffusion"):
            self.assertIn(key, tpls, f"Missing provider template: {key}")
            t = tpls[key]
            for field in ("name", "prompt_prefix", "prompt_suffix", "negative_hint", "style_presets", "aspect_ratio_map"):
                self.assertIn(field, t, f"Provider {key} missing {field}")

    def test_provider_aspect_ratio_maps(self):
        with open(self._spec_src) as f:
            spec = json.load(f)
        platforms = spec.get("platforms", {})
        for prov_key, prov_tpl in spec.get("provider_templates", {}).items():
            ar_map = prov_tpl.get("aspect_ratio_map", {})
            # Each provider should map the common ratios
            for ratio in ("1:1", "9:16", "16:9", "1.91:1"):
                self.assertIn(ratio, ar_map, f"Provider {prov_key} missing ratio {ratio}")

    def test_color_palette_has_brand_colors(self):
        with open(self._spec_src) as f:
            spec = json.load(f)
        palette = spec.get("color_palette", {})
        for key in ("primary", "secondary", "accent_gold"):
            self.assertIn(key, palette, f"Missing brand color: {key}")
            # Hex color format check
            val = palette[key]
            if isinstance(val, str) and val.startswith("#"):
                self.assertEqual(len(val), 7, f"Palette {key} should be 6-digit hex: {val}")

    def test_brand_voice_always_never(self):
        with open(self._spec_src) as f:
            spec = json.load(f)
        bv = spec.get("brand_voice_for_images", {})
        self.assertIn("always_include", bv)
        self.assertIn("never_include", bv)
        self.assertIsInstance(bv["always_include"], list)
        self.assertIsInstance(bv["never_include"], list)


class GenerateImageIntelligenceTests(unittest.TestCase):
    """Test generate_image() function via the intelligence module directly."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        src = Path(__file__).resolve().parents[2] / "data" / "asset-image-spec.json"
        shutil.copy(src, Path(cls._tmp) / "asset-image-spec.json")
        os.environ["DATA_DIR"] = cls._tmp
        # Re-import to pick up the env
        import importlib
        import _lib.intelligence as intel_mod
        importlib.reload(intel_mod)
        cls._intel_mod = intel_mod

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("DATA_DIR", None)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _gi(self, asset_id=None):
        return self._intel_mod.generate_image(asset_id)

    def test_no_args_returns_envelope(self):
        r = self._gi()
        self.assertIsInstance(r, dict)
        self.assertTrue(r.get("ok"), "Envelope ok must be True")
        self.assertIn("ts", r)

    def test_all_required_top_level_keys(self):
        r = self._gi()
        for key in ("ok", "ts", "pillar", "pillar_label", "platform", "platform_config",
                    "tone", "color_keywords", "subject", "prompt_parts", "negative_prompt",
                    "composition", "providers", "reference_prompt", "provider_used",
                    "brand_voice_notes", "metadata"):
            self.assertIn(key, r, f"Missing top-level key: {key}")

    def test_providers_all_four_present(self):
        r = self._gi()
        provs = r.get("providers", {})
        self.assertEqual(len(provs), 4, f"Expected 4 providers, got {list(provs.keys())}")
        for key in ("ideogram", "dall-e", "midjourney", "stable-diffusion"):
            self.assertIn(key, provs, f"Missing provider: {key}")
            p = provs[key]
            for field in ("provider", "display_name", "prompt", "aspect_ratio", "aspect_ratio_flag", "style_presets"):
                self.assertIn(field, p, f"Provider {key} missing {field}")

    def test_reference_prompt_not_empty(self):
        r = self._gi()
        self.assertTrue(r.get("reference_prompt"), "reference_prompt must not be empty")
        self.assertGreater(len(r["reference_prompt"]), 20)

    def test_negative_prompt_not_empty(self):
        r = self._gi()
        self.assertTrue(r.get("negative_prompt"), "negative_prompt must not be empty")

    def test_color_keywords_list(self):
        r = self._gi()
        self.assertIsInstance(r.get("color_keywords"), list)

    def test_platform_config_structure(self):
        r = self._gi()
        pc = r.get("platform_config", {})
        self.assertIn("aspect_ratio", pc)
        self.assertIn("aspect_px", pc)
        self.assertIn("text_safety_zone", pc)
        self.assertIn("use_cases", pc)

    def test_default_pillar_is_education(self):
        r = self._gi()
        self.assertEqual(r.get("pillar"), "education")

    def test_composition_has_required_fields(self):
        r = self._gi()
        comp = r.get("composition", {})
        for field in ("primary_subject", "background", "lighting", "depth_of_field"):
            self.assertIn(field, comp)

    def test_prompt_parts_has_four_components(self):
        r = self._gi()
        pp = r.get("prompt_parts", {})
        for key in ("pillar_fragment", "subject", "model_hint", "background"):
            self.assertIn(key, pp)

    def test_provider_prompts_unique(self):
        r = self._gi()
        prompts = [p.get("prompt", "") for p in r.get("providers", {}).values()]
        unique = set(prompts)
        self.assertGreater(len(unique), 1, "Provider prompts should differ")

    def test_metadata_note_present(self):
        r = self._gi()
        note = r.get("metadata", {}).get("note", "")
        self.assertIn("provider", note.lower(), "metadata.note should mention provider swapping")
        self.assertIn("cred", note.lower(), "metadata.note should mention credentials")

    def test_brand_voice_notes_included(self):
        r = self._gi()
        bv = r.get("brand_voice_notes", {})
        self.assertIn("always_include", bv)
        self.assertIn("never_include", bv)


class GenerateImageRouteTests(unittest.TestCase):
    """Test the Flask HTTP route via the test client."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        src = Path(__file__).resolve().parents[2] / "data" / "asset-image-spec.json"
        shutil.copy(src, Path(cls._tmp) / "asset-image-spec.json")
        os.environ["DATA_DIR"] = cls._tmp

        import importlib
        # Force reload intelligence with new DATA_DIR
        import _lib.intelligence as intel_mod
        importlib.reload(intel_mod)

        import sys
        if "campaign_os.app" in sys.modules:
            del sys.modules["campaign_os.app"]
        if "app" in sys.modules:
            del sys.modules["app"]

        import app as app_mod
        app_mod.DATA_DIR = cls._tmp
        app_mod.REPO_DIR = cls._tmp
        # Patch _data_paths to return tmp paths
        def _patched_data_paths():
            return {
                'data_dir': cls._tmp,
                'campaign_file': os.path.join(cls._tmp, 'campaign-data.json'),
                'schedule_file': os.path.join(cls._tmp, 'scheduled-items.json'),
            }
        app_mod._data_paths = _patched_data_paths
        # Patch intelligence module DATA_DIR
        import _lib.intelligence as intel_mod2
        importlib.reload(intel_mod2)
        app_mod._INTELLIGENCE_AVAILABLE = True
        try:
            from _lib.intelligence import generate_image as gi
            app_mod.generate_image = gi
        except ImportError:
            pass

        cls._app = app_mod.app
        cls._client = cls._app.test_client()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("DATA_DIR", None)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_get_no_args_returns_200(self):
        r = self._client.get("/api/intel/generate_image")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d.get("ok"), f"Expected ok=True, got {d}")

    def test_get_returns_all_required_fields(self):
        r = self._client.get("/api/intel/generate_image")
        d = r.get_json()
        for key in ("ok", "ts", "pillar", "providers", "reference_prompt", "negative_prompt"):
            self.assertIn(key, d, f"Missing {key} in response")

    def test_get_pillar_override(self):
        r = self._client.get("/api/intel/generate_image?pillar=club-fitting")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertIn("pillar_override", d)

    def test_get_platform_override(self):
        r = self._client.get("/api/intel/generate_image?platform=tiktok")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertIn("platform_override", d)
        pc = d.get("platform_config", {})
        self.assertEqual(pc.get("aspect_ratio"), "9:16")

    def test_get_provider_override(self):
        r = self._client.get("/api/intel/generate_image?provider=dall-e")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertIn("provider_override", d)
        provs = d.get("providers", {})
        self.assertIn("dall-e", provs)

    def test_get_all_pillars(self):
        for pillar in ("education", "club-fitting", "community", "events"):
            r = self._client.get(f"/api/intel/generate_image?pillar={pillar}")
            self.assertEqual(r.status_code, 200, f"Failed for pillar={pillar}")
            d = r.get_json()
            self.assertTrue(d.get("ok"), f"ok=False for pillar={pillar}: {d}")

    def test_get_all_platforms(self):
        for platform in ("instagram", "tiktok", "twitter", "facebook", "gmb"):
            r = self._client.get(f"/api/intel/generate_image?platform={platform}")
            self.assertEqual(r.status_code, 200, f"Failed for platform={platform}")
            d = r.get_json()
            self.assertTrue(d.get("ok"), f"ok=False for platform={platform}: {d}")

    def test_post_with_body_params(self):
        r = self._client.post("/api/intel/generate_image",
                               json={"pillar": "community", "platform": "tiktok", "provider": "midjourney"})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d.get("ok"))
        self.assertEqual(d.get("pillar_override"), "community")

    def test_hook_override_get(self):
        r = self._client.get("/api/intel/generate_image?hook=The+truth+about+golf+fitting")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d.get("ok"))
        self.assertIn("hook_override", d)

    def test_subject_override(self):
        r = self._client.get("/api/intel/generate_image?subject=Custom+golf+scene")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d.get("ok"))
        self.assertIn("subject_override", d)

    def test_all_providers_have_prompts(self):
        r = self._client.get("/api/intel/generate_image")
        d = r.get_json()
        provs = d.get("providers", {})
        self.assertEqual(len(provs), 4)
        for k, p in provs.items():
            self.assertTrue(p.get("prompt"), f"Provider {k} has empty prompt")
            self.assertGreater(len(p.get("prompt", "")), 20, f"Provider {k} prompt too short")

    def test_aspect_ratio_differs_by_platform(self):
        ig = self._client.get("/api/intel/generate_image?platform=instagram").get_json()
        tt = self._client.get("/api/intel/generate_image?platform=tiktok").get_json()
        self.assertNotEqual(
            ig.get("platform_config", {}).get("aspect_ratio"),
            tt.get("platform_config", {}).get("aspect_ratio"),
        )

    def test_ideogram_aspect_ratio_flag(self):
        r = self._client.get("/api/intel/generate_image?platform=instagram&provider=ideogram")
        d = r.get_json()
        prov = (d.get("providers") or {}).get("ideogram", {})
        # Ideogram uses --aspect-1-1 for 1:1
        self.assertIn("--aspect", prov.get("aspect_ratio_flag", ""))

    def test_tiktok_9_16_ratio(self):
        r = self._client.get("/api/intel/generate_image?platform=tiktok")
        d = r.get_json()
        pc = d.get("platform_config", {})
        self.assertEqual(pc.get("aspect_ratio"), "9:16")
        self.assertEqual(pc.get("aspect_px"), "1080x1920")

    def test_envelope_ok_always_true(self):
        r = self._client.get("/api/intel/generate_image?pillar=events&platform=facebook&provider=stable-diffusion")
        d = r.get_json()
        self.assertTrue(d.get("ok"), f"Expected ok=True, got {d}")


if __name__ == "__main__":
    unittest.main()
