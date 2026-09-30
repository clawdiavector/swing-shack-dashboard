"""Tests for caption copy contracts and P11 gates."""
from __future__ import annotations

import unittest


class CaptionCopyContractTests(unittest.TestCase):
    def test_vague_data_rejected_by_fact_check(self):
        from _lib.p11_context_engine import _check_fact

        ctx = {"copy_contract": {}, "user_brief": "iron fitting", "product_service": {}}
        r = _check_fact("Data shows that fitting helps your game.", ctx)
        self.assertFalse(r["passed"])
        self.assertTrue(any("vague" in x for x in (r.get("reasons") or [r.get("reason")])))

    def test_stick_membership_rejected(self):
        from _lib.caption_copy_contract import build_copy_contract, check_copy_contract

        contract = build_copy_contract(
            brand_id="stick",
            template_id="stick-service-square",
            post_type="service_square",
            lodge_title="FITTING @ stick",
            user_brief="fitting",
        )
        ctx = {"copy_contract": contract, "user_brief": "fitting"}
        r = check_copy_contract(
            "Join our fitting membership and get sorted.",
            ctx,
        )
        self.assertFalse(r["passed"])

    def test_iron_template_rejects_putter_without_brief(self):
        from _lib.caption_copy_contract import build_copy_contract, check_copy_contract

        contract = build_copy_contract(
            brand_id="swing-shack",
            template_id="ss-fitting-headline",
            post_type="fitting_headline",
            lodge_title="Hit more greens — iron fitting",
            user_brief="Hit more greens — iron fitting",
        )
        ctx = {"copy_contract": contract, "user_brief": contract["brief_blob"]}
        bad = (
            "Hitting more greens starts with your putter. "
            "A tailored fitting session can reveal stroke type."
        )
        r = check_copy_contract(bad, ctx)
        self.assertFalse(r["passed"])

    def test_alignment_iron_headline_putter_caption(self):
        from _lib.caption_copy_contract import (
            build_copy_contract,
            check_poster_caption_alignment,
        )

        contract = build_copy_contract(
            brand_id="swing-shack",
            template_id="ss-fitting-headline",
            lodge_title="Hit more greens — iron fitting",
            user_brief="iron fitting session",
        )
        ctx = {"copy_contract": contract, "user_brief": "iron fitting session"}
        pkg = {"poster_hook": "HIT MORE GREENS — IRON FITTING", "caption_body": ""}
        r = check_poster_caption_alignment(
            "Your putter stroke type matters on the greens.",
            ctx,
            pkg,
        )
        self.assertFalse(r["passed"])

    def test_merged_banned_includes_data_shows(self):
        from _lib.p11_context_engine import _extract_banned_terms

        banned = _extract_banned_terms("stick")
        low = [b.lower() for b in banned]
        self.assertIn("data shows", low)

    def test_build_context_includes_contract(self):
        from _lib.p11_context_engine import build_generation_context

        ctx = build_generation_context(
            brand_id="swing-shack",
            user_brief="Hit more greens — iron fitting",
            template_id="ss-fitting-headline",
            post_type="fitting_headline",
            lodge_title="Hit more greens — iron fitting",
        )
        self.assertTrue(ctx.get("ok"))
        contract = ctx.get("copy_contract") or {}
        self.assertEqual(contract.get("template_id"), "ss-fitting-headline")
        self.assertEqual(ctx.get("product_service", {}).get("brief_subject"), "iron fitting")


if __name__ == "__main__":
    unittest.main()
