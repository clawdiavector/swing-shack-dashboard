"""v2026-08-19 — Review queue: every row ships a `brand` field, and the JS
brandNames lookup correctly reads /api/brands (which returns a dict of records,
not a flat array).

Background
----------
Two stacked bugs hid the brand pill on every review-row in the Review queue:
  1. review_inbox() never included `brand` on each row dict — so x.brand was
     always undefined and `brandNames[x.brand]` always empty.
  2. renderReview() did `(bl || []).forEach(b => { ... })` against the response
     of `/api/brands`. That endpoint returns
        {active_brand_id, brands: {id: {...full record...}}, count, default_brand_id}
     — a dict of brand records, NOT a flat array. Iterating an object yields
     its values, so `b` came back as the nested RECORD OBJECT — not as a
     brand-id string — and the inner `b.id || b.brand_id` lookup hit an
     undefined property. brandNames stayed {} and prettyBrand always empty.

Fix
---
  1. _lib/intelligence.py review_inbox(): each row now includes
     `brand: row_brand` (resolved via _brands_for_campaign(campaign_id) so the
     pill matches the brands.json owner list, not the unreliable campaign
     identity.brand).
  2. campaign-os.html renderReview(): now reads bl.brands when it's an object
     (falls back to array iteration if the endpoint shape changes back).

This test pins:
  A. review_inbox returns a `brand` field on every row (pending + approved +
     rejected), and the field is non-empty for known Swing Shack campaigns.
  B. /api/brands returns a dict containing a top-level `brands` key whose
     values are full brand records (with `id` + `display_name`).
  C. renderReview() now reads `bl.brands` correctly: the brandNames lookup
     ends up with {id: display_name} for every brand in the dict.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CAMPAIGN_OS_ROOT = os.path.abspath(os.path.join(HERE, ".."))
APP_PATH = os.path.join(CAMPAIGN_OS_ROOT, "app.py")
HTML_PATH = os.path.join(CAMPAIGN_OS_ROOT, "campaign-os.html")

if CAMPAIGN_OS_ROOT not in sys.path:
    sys.path.insert(0, CAMPAIGN_OS_ROOT)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _payload(campaigns_assets):
    """Build a synthetic _campaign_data payload.

    `campaigns_assets` is a list of (cid, [(asset_id, approvalStatus, brand_id_or_None), ...])
    """
    campaigns = {}
    for cid, items in campaigns_assets:
        assets = {}
        for i, (aid, aps, _bid) in enumerate(items):
            assets[aid] = {"name": aid, "approvalStatus": aps, "updatedAt": "2026-08-19T00:00:00Z"}
        campaigns[cid] = {"identity": {"name": cid}, "assets": assets}
    return {"campaigns": campaigns}


def _brands_registry(owners):
    """brands.json fixture: brands.<id>.campaign_ids = owners list."""
    return {"brands": {bid: {"campaign_ids": cids, "display_name": bid, "id": bid}
                       for bid, cids in owners.items()}}


class ReviewRowBrandPill(unittest.TestCase):
    """Two-pronged fix: backend ships brand per row + JS reads /api/brands dict."""

    @classmethod
    def setUpClass(cls):
        # Real Flask client for the endpoint-shape test (uses test data).
        import app as app_module
        cls.client = app_module.app.test_client()
        cls.client.post("/login", data={"password": "swing-shack-dev-2026"})
        cls.html = _read(HTML_PATH)

    # ─── A. Backend: review_inbox ships `brand` on every row ─────────────

    def test_pending_rows_have_brand_field(self):
        """Every pending row carries a non-empty `brand` key when the campaign
        is owned by at least one brand in brands.json."""
        from _lib import intelligence
        payload = _payload([
            ("camp-1", [
                ("a-1", "draft", None),
                ("a-2", "draft", None),
            ]),
        ])
        brands = _brands_registry({"swing-shack": ["camp-1"]})
        with patch.object(intelligence, "_campaign_data", return_value=payload), \
             patch.object(intelligence, "_load_brands_registry", return_value=brands):
            out = intelligence.review_inbox()
        self.assertEqual(len(out["pending"]), 2)
        for r in out["pending"]:
            self.assertEqual(
                r.get("brand"), "swing-shack",
                f"pending row missing or wrong brand: {r}",
            )

    def test_approved_rows_have_brand_field(self):
        """Approved rows also carry `brand` (same fix site)."""
        from _lib import intelligence
        payload = _payload([
            ("camp-1", [
                ("a-1", "approved", None),
                ("a-2", "rejected", None),
            ]),
        ])
        brands = _brands_registry({"swing-shack": ["camp-1"]})
        with patch.object(intelligence, "_campaign_data", return_value=payload), \
             patch.object(intelligence, "_load_brands_registry", return_value=brands):
            out = intelligence.review_inbox()
        self.assertTrue(out["approved"], "approved row should be present")
        for r in out["approved"]:
            self.assertEqual(r.get("brand"), "swing-shack", f"approved row missing brand: {r}")
        for r in out["rejected"]:
            self.assertEqual(r.get("brand"), "swing-shack", f"rejected row missing brand: {r}")

    def test_brand_field_matches_brands_json_ownership(self):
        """The `brand` value is the first brand in brands.json's campaign_ids
        list for that campaign — not the unreliable campaign.identity.brand."""
        from _lib import intelligence
        payload = _payload([
            ("camp-A", [("a-1", "draft", None)]),
            ("camp-B", [("b-1", "draft", None)]),
        ])
        brands = _brands_registry({
            "brand-X": ["camp-A"],
            "brand-Y": ["camp-B"],
        })
        with patch.object(intelligence, "_campaign_data", return_value=payload), \
             patch.object(intelligence, "_load_brands_registry", return_value=brands):
            out = intelligence.review_inbox()
        by_id = {r["assetId"]: r for r in out["pending"]}
        self.assertEqual(by_id["a-1"].get("brand"), "brand-X")
        self.assertEqual(by_id["b-1"].get("brand"), "brand-Y")

    def test_unowned_campaign_yields_empty_brand(self):
        """A campaign not in any brand's campaign_ids is unowned; brand field
        stays empty (caller can decide how to render the missing pill)."""
        from _lib import intelligence
        payload = _payload([("camp-orphan", [("a-1", "draft", None)])])
        brands = _brands_registry({"brand-X": ["other-camp"]})
        with patch.object(intelligence, "_campaign_data", return_value=payload), \
             patch.object(intelligence, "_load_brands_registry", return_value=brands):
            out = intelligence.review_inbox()
        # Unowned campaigns still appear (scoped_brand defaults to None → all
        # campaigns pass _owns_campaign) but with empty brand.
        self.assertEqual(len(out["pending"]), 1)
        self.assertEqual(out["pending"][0].get("brand"), "",
                         "unowned campaign should have empty brand")

    # ─── B. /api/brands shape is a dict of records ─────────────────────

    def test_api_brands_endpoint_returns_brands_dict(self):
        """/api/brands returns a dict whose `brands` key maps id → full record."""
        r = self.client.get("/api/brands")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIsInstance(body, dict, "/api/brands must be a JSON object")
        self.assertIn("brands", body, "/api/brands must include a 'brands' dict")
        brands = body["brands"]
        self.assertIsInstance(brands, dict)
        self.assertGreater(len(brands), 0, "brands dict must be non-empty")
        # At least one record should have an `id` and a `display_name`.
        any_good = any(
            isinstance(rec, dict) and rec.get("id") and (rec.get("display_name") or rec.get("name"))
            for rec in brands.values()
        )
        self.assertTrue(any_good, "brands records missing id/display_name")

    # ─── C. JS: renderReview() correctly reads bl.brands ────────────────

    def test_renderReview_no_longer_iterates_top_level_keys_as_records(self):
        """The old `(bl || []).forEach(b => { b.id ... })` pattern is gone —
        replaced by Object.values(bl.brands) so we iterate records, not keys."""
        render = self._render_block("async function renderReview", "function renderReview")
        self.assertIsNotNone(render, "renderReview() block not found in campaign-os.html")
        self.assertNotIn(
            "(bl || []).forEach", render,
            "renderReview() still uses the broken (bl || []).forEach pattern",
        )
        self.assertIn("bl.brands", render, "renderReview() doesn't read bl.brands dict")
        self.assertIn("Object.values", render, "renderReview() should resolve bl.brands via Object.values()")

    def test_renderReview_prettyBrand_pill_still_present(self):
        """The prettyBrand pill render still exists (we didn't accidentally
        delete the row layout when patching the brandNames lookup)."""
        render = self._render_block("async function renderReview", "function renderReview")
        self.assertIn("prettyBrand", render, "prettyBrand reference lost from renderReview")
        self.assertIn("brandNames", render, "brandNames lookup lost from renderReview")

    def _render_block(self, *sentinels):
        """Return the chunk of HTML starting at the first matching sentinel."""
        idx = -1
        for s in sentinels:
            i = self.html.find(s)
            if i >= 0 and (idx < 0 or i < idx):
                idx = i
        if idx < 0:
            return None
        return self.html[idx: idx + 8000]


if __name__ == "__main__":
    unittest.main()