"""Brand-bible linter on the caption gate, and markdown voice in generation context."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


class BrandLintGateTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("BRAND_LINT_GATE", None)

    def test_default_warn_keeps_existing_passes(self):
        from _lib.caption_copy_contract import gate_text

        club = gate_text("stick", "Club fitting at Stick. Fit first. Buy second.")
        self.assertTrue(club["passed"])
        assessment = gate_text("swing-shack", "FREE CLUB ASSESSMENT")
        self.assertTrue(assessment["passed"])
        self.assertEqual(assessment["lint_mode"], "warn")
        self.assertGreater(assessment["lint"]["hard"], 0)
        shack = gate_text("swing-shack", "Join the club. Four practice sessions a month.")
        self.assertTrue(shack["passed"])

    def test_warn_reports_a_hard_bible_fail_without_blocking(self):
        from _lib.caption_copy_contract import gate_text

        result = gate_text("stick", "Picture this: a better swing starts with a fitting.")
        self.assertTrue(result["passed"])
        self.assertEqual(result["reason"], "ok")
        self.assertGreater(result["lint"]["hard"], 0)

    def test_block_fails_on_a_hard_bible_fail(self):
        from _lib.caption_copy_contract import gate_text

        os.environ["BRAND_LINT_GATE"] = "block"
        result = gate_text(
            "stick",
            "Picture this: a better swing starts with a fitting.",
            ctx={"lane": "coaching", "when": "2026-10-16"},
        )
        self.assertFalse(result["passed"])
        self.assertTrue(result["reason"].startswith("brand_lint:"))
        self.assertEqual(result["lint_mode"], "block")

    def test_stick_membership_phrase_still_blocks_in_warn_mode(self):
        from _lib.caption_copy_contract import gate_text

        result = gate_text("stick", "Join the club and get fitted.")
        self.assertFalse(result["passed"])
        self.assertIn("join the club", result["reason"])

    def test_markdown_voice_is_per_brand(self):
        from _lib.brand_bible import markdown_voice_slice

        stick = markdown_voice_slice("stick")
        shack = markdown_voice_slice("swing-shack")
        bag = markdown_voice_slice("bag-drop")
        self.assertIn("calm, plain and dry", stick["voice_description"].lower())
        self.assertNotIn("sarcastic", stick["rules_excerpt"].lower())
        self.assertIn("sharp", stick["personality"].lower())
        self.assertNotIn("join the club", shack["rules_excerpt"].lower())
        self.assertIn("warm", shack["personality"].lower())
        self.assertNotIn("member social", bag["voice_description"].lower())
        self.assertIn("dry", bag["voice_description"].lower())

    def test_generation_context_uses_the_markdown_voice(self):
        from _lib.p11_context_engine import build_generation_context

        stick = build_generation_context(
            "stick", user_brief="a fitting", n_recent=1, n_semantic=0, n_structural=0, n_performance=0,
        )
        shack = build_generation_context(
            "swing-shack", user_brief="a fitting", n_recent=1, n_semantic=0, n_structural=0, n_performance=0,
        )
        stick_brand = stick["brand"]
        shack_brand = shack["brand"]
        self.assertIn("calm, plain and dry", stick_brand["voice_description"].lower())
        self.assertNotIn("sarcastic", stick_brand["rules_excerpt"].lower())
        self.assertNotIn("join the club", shack_brand["rules_excerpt"].lower())
        self.assertIn("warm", shack_brand["personality"].lower())


if __name__ == "__main__":
    unittest.main()
