"""cos-brand-bible slice — caption + poster phrase gates and bible retrieval."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DATA = _REPO / "data"


class CosBrandBible20260930Tests(unittest.TestCase):
    def test_gate_stick_join_the_club_blocked(self):
        from _lib.caption_copy_contract import gate_text

        r = gate_text("stick", "Join the club and get fitted.")
        self.assertFalse(r["passed"])

    def test_gate_swing_shack_join_the_club_passes(self):
        from _lib.caption_copy_contract import gate_text

        # Workbook §D approved CTA for Swing Shack membership
        r = gate_text("swing-shack", "Join the club. Four practice sessions a month.")
        self.assertTrue(r["passed"])

    def test_gate_stick_club_fitting_passes(self):
        from _lib.caption_copy_contract import gate_text

        r = gate_text("stick", "Club fitting at Stick. Fit first. Buy second.")
        self.assertTrue(r["passed"])

    def test_gate_swing_shack_free_club_assessment_passes(self):
        from _lib.caption_copy_contract import gate_text

        r = gate_text("swing-shack", "FREE CLUB ASSESSMENT")
        self.assertTrue(r["passed"])

    def test_gate_data_shows_blocked(self):
        from _lib.caption_copy_contract import gate_text

        r = gate_text("stick", "Data shows fitting helps.")
        self.assertFalse(r["passed"])
        self.assertIn("data shows", r["reason"].lower())

    def test_data_confirms_in_promise_passes(self):
        from _lib.caption_copy_contract import gate_text

        r = gate_text(
            "swing-shack",
            "The ball speaks. Data confirms. Feel seals the deal.",
        )
        self.assertTrue(r["passed"])

    def test_gate_copy_package_poster_hook(self):
        from _lib.caption_copy_contract import gate_copy_package

        r = gate_copy_package(
            "stick",
            {
                "caption_body": "ok",
                "poster_hook": "JOIN THE CLUB",
                "cta_line": "Book a fitting",
            },
        )
        self.assertFalse(r["passed"])
        self.assertEqual(r["field"], "poster_hook")

    def test_gate_copy_package_cta_line(self):
        from _lib.caption_copy_contract import gate_copy_package

        r = gate_copy_package(
            "stick",
            {
                "caption_body": "ok",
                "poster_hook": "FITTINGS",
                "cta_line": "Join the club today",
            },
        )
        self.assertFalse(r["passed"])
        self.assertEqual(r["field"], "cta_line")

    def test_visual_copy_blocks_join_the_club_hook(self):
        from _lib.compose_visual_copy import visual_copy_for_archetype

        arch = {"id": "stick-service-frame", "applies_to": {"needs_photo": False}}
        fields = visual_copy_for_archetype(
            brand_id="stick",
            moment_id="proposal:stick:x",
            caption="Fitting promo",
            archetype=arch,
            sidecar={"compose_headline": "Join the club"},
        )
        self.assertNotEqual(fields.get("caption_hook", "").lower(), "join the club")
        self.assertIn("caption_hook", fields.get("_poster_gate_blocked", ""))

    def test_service_cta_differs_by_brand_no_free(self):
        from _lib.compose_visual_copy import _service_cta

        ss = _service_cta(
            brand_id="swing-shack",
            moment_id="calendar_candidate:swing-shack:noop",
            caption="club fitting session",
        )
        st = _service_cta(
            brand_id="stick",
            moment_id="calendar_candidate:stick:noop",
            caption="club fitting session",
        )
        self.assertNotEqual(ss, st)
        self.assertNotIn("free", ss.lower())
        self.assertNotIn("free", st.lower())

    def test_parse_dont_say_swing_shack_phrases(self):
        from _lib.caption_copy_contract import parse_dont_say_markdown

        md = (_DATA / "brand-directory/swing-shack/voice/do-say-dont-say.md").read_text()
        phrases = parse_dont_say_markdown(md)
        self.assertIn("world-class", phrases)
        self.assertIn("look no further", phrases)
        self.assertTrue(all("—" not in p for p in phrases))

    def test_parse_dont_say_stick_cross_brand_survives(self):
        from _lib.caption_copy_contract import parse_dont_say_markdown

        md = (_DATA / "brand-directory/stick/voice/do-say-dont-say.md").read_text()
        phrases = parse_dont_say_markdown(md)
        joined = " ".join(phrases).lower()
        self.assertTrue(
            "bag drop" in joined or "other brands" in joined or "swing shack" in joined
        )

    def test_extract_required_terms_swing_shack_nonempty(self):
        from _lib.p11_context_engine import _extract_required_terms

        req = _extract_required_terms("swing-shack")
        self.assertTrue(len(req) > 0)

    def test_retrieve_caption_signature_lines(self):
        from _lib.brand_bible import retrieve_for_job

        row = retrieve_for_job("stick", lane="caption")
        sig = row["fields"]["copy_system"]["signature_lines"]
        self.assertIn("Better Begins Here", sig)

    def test_retrieve_poster_omits_master_and_internal(self):
        from _lib.brand_bible import retrieve_for_job

        cs = retrieve_for_job("stick", lane="poster")["fields"]["copy_system"]
        self.assertNotIn("master_message", cs)
        self.assertNotIn("internal_only", cs)

    def test_retrieve_swing_shack_banned_asymmetry(self):
        from _lib.brand_bible import retrieve_for_job

        banned = retrieve_for_job("swing-shack", lane="caption")["fields"]["copy_system"][
            "banned_phrases"
        ]
        self.assertIn("world-class", banned)
        self.assertNotIn("join the club", banned)

    def test_retrieve_bag_drop_unavailable(self):
        from _lib.brand_bible import retrieve_for_job

        row = retrieve_for_job("bag-drop", lane="caption")
        self.assertFalse(row["available"])

    def test_build_generation_context_bible_slice(self):
        from _lib.p11_context_engine import build_generation_context

        ctx = build_generation_context(brand_id="stick", user_brief="driver fitting")
        bible = ctx["brand"].get("bible") or {}
        self.assertTrue(bible.get("voice_in_5_words"))

    def test_build_llm_prompt_includes_bible_not_sarcastic(self):
        from _lib.p11_context_engine import _build_llm_prompt, build_generation_context

        ctx = build_generation_context(brand_id="stick", user_brief="driver fitting")
        route = {
            "mechanism": "proof",
            "brand_fit": 5,
            "rhetorical_structure_suggestion": "claim + evidence + CTA",
            "rationale": "Stick proof route",
        }
        system, _user = _build_llm_prompt(ctx, route)
        self.assertIn("Better Begins Here", system)
        self.assertNotIn("sarcastic", system.lower())

    def test_bible_slice_excludes_internal_only_mantra(self):
        from _lib.p11_context_engine import build_generation_context

        ctx = build_generation_context(brand_id="swing-shack", user_brief="coaching")
        blob = json.dumps(ctx["brand"].get("bible") or {})
        self.assertNotIn("Real Golf. Real Data. Real Welcome.", blob)

    def test_voice_bible_stick_demoted(self):
        vb = json.loads((_DATA / "voice_bible.json").read_text())
        stick = vb["voices"]["stick"]
        self.assertNotIn("sarcastic", stick["allowed_tones"])
        self.assertNotIn("sarcastic", stick["personality"].lower())

    def test_voice_bible_stick_no_swingshack_domain(self):
        vb = json.loads((_DATA / "voice_bible.json").read_text())
        blob = json.dumps(vb["voices"]["stick"])
        self.assertNotIn("swingshack.co.za", blob)

    def test_clubs_deserve_better_removed(self):
        vb = json.loads((_DATA / "voice_bible.json").read_text())
        phrase = "Your clubs deserve better than you."
        for brand in ("stick", "swing-shack"):
            alts = vb["voices"][brand].get("cta_alternatives") or []
            self.assertNotIn(phrase, alts)
            ctas_md = (_DATA / f"brand-directory/{brand}/copy/ctas.md").read_text()
            self.assertNotIn(phrase, ctas_md)

    def test_voice_bible_bag_drop_unchanged(self):
        base = subprocess.run(
            [
                "git",
                "show",
                "480f4a44:data/voice_bible.json",
            ],
            cwd=_REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        current = (_DATA / "voice_bible.json").read_text()
        base_bd = json.loads(base)["voices"]["bag-drop"]
        cur_bd = json.loads(current)["voices"]["bag-drop"]
        self.assertEqual(base_bd, cur_bd)

    def test_check_fact_signature_truth_allowed(self):
        from _lib.p11_context_engine import _check_fact

        ctx = {"brand_id": "swing-shack", "copy_contract": {}, "user_brief": "", "product_service": {}}
        r = _check_fact("The swing may lie, but the ball tells the truth.", ctx)
        self.assertTrue(r["passed"])

    def test_check_fact_guarantee_still_fails(self):
        from _lib.p11_context_engine import _check_fact

        ctx = {"brand_id": "stick", "copy_contract": {}, "user_brief": "", "product_service": {}}
        r = _check_fact("This fitting is guaranteed to add 10 metres.", ctx)
        self.assertFalse(r["passed"])


if __name__ == "__main__":
    unittest.main()
