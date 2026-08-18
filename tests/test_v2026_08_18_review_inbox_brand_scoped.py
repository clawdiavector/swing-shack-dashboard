"""
Regression test for review_inbox() brand leak.

Before 2026-08-18, /api/intel/review_inbox iterated every campaign in
campaign-data.json without brand-scoping. morning_brief() scopes by
calling _owns_campaign(cid, scoped_brand) — review_inbox() did not,
so the Review tab on the home page could silently pull in another
brand's pending drafts (e.g. when brands.json grows a new brand like
'takomo' / 'stick' / 'bag-drop' that owns its own campaigns).

When the active brand is swing-shack, the fix still returns the
swing-shack-owned campaigns (trackman-intelligence, takomo-101t,
winter-golf, use-the-right-equipment-…) — same as before. The fix
becomes visible only when a brand we DON'T own is added to the
dataset, which is when the leak would start.

The test stubs _REQUEST_BRAND_ID via set_request_brand() and asserts
that campaigns not in the active brand's brands.json campaign_ids are
NOT surfaced, while owned campaigns still are.

Static checks (1) review_inbox() reads get_request_brand(), and (2)
applies `_owns_campaign(cid, scoped_brand)` to skip non-owned rows.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
INTELLIGENCE = REPO / "campaign-os" / "_lib" / "intelligence.py"


class ReviewInboxBrandScopedTests(unittest.TestCase):
    """review_inbox() must respect the active brand."""

    @classmethod
    def setUpClass(cls):
        cls.src = INTELLIGENCE.read_text(encoding="utf-8")

    def test_source_reads_get_request_brand(self):
        # The fix calls get_request_brand() inside review_inbox() so the
        # active brand (set by app.py via set_request_brand) is honored.
        # Pin the call site to review_inbox so other functions don't
        # satisfy the assertion.
        import re
        m = re.search(
            r"def review_inbox\(.*?\n.*?cd\s*=\s*_campaign_data\(\)",
            self.src,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "review_inbox() does not start with cd = _campaign_data()")
        start = m.end()
        # Find the next def — review_inbox's body extends to the next top-level def.
        next_def = re.search(r"\ndef [a-z_]", self.src[start:])
        body = self.src[start : start + (next_def.start() if next_def else 4000)]
        self.assertIn(
            "get_request_brand",
            body,
            "review_inbox() body must call get_request_brand() to honor the active brand",
        )

    def test_source_applies_owns_campaign_skip(self):
        # The fix uses _owns_campaign(cid, scoped_brand) to skip rows
        # not owned by the active brand — same pattern morning_brief uses.
        import re
        m = re.search(
            r"def review_inbox\(.*?\n.*?cd\s*=\s*_campaign_data\(\)",
            self.src,
            re.DOTALL,
        )
        self.assertIsNotNone(m)
        start = m.end()
        next_def = re.search(r"\ndef [a-z_]", self.src[start:])
        body = self.src[start : start + (next_def.start() if next_def else 4000)]
        self.assertIn(
            "_owns_campaign",
            body,
            "review_inbox() must call _owns_campaign() to skip non-owned campaigns",
        )
        self.assertIn(
            "continue",
            body,
            "review_inbox() must `continue` past non-owned campaigns",
        )

    def test_live_call_filters_out_unowned_campaigns(self):
        """Live call: with a brand we don't own, its drafts must not appear."""
        # Import the module fresh (clear any cached state).
        for mod_name in [k for k in sys.modules if k.startswith("_lib")]:
            sys.modules.pop(mod_name, None)
        sys.path.insert(0, str(REPO / "campaign-os"))
        from _lib import intelligence as intel

        # Use a brand id that does NOT own any campaign in the live data.
        # If the active dataset accidentally gives 'nobody' a campaign,
        # pick a different phony id. The live swing-shack campaigns are
        # trackman-intelligence, takomo-101t, winter-golf, and
        # use-the-right-equipment-* — none of these are owned by 'nobody'.
        try:
            intel.set_request_brand("nobody-brand-xyz")
            out = intel.review_inbox()
        finally:
            intel.clear_request_brand()

        self.assertTrue(out.get("ok"))
        all_ids = (
            [x["campaignId"] for x in out.get("pending", [])]
            + [x["campaignId"] for x in out.get("approved", [])]
            + [x["campaignId"] for x in out.get("rejected", [])]
        )
        # The unrequested brand must see zero rows.
        self.assertEqual(
            len(all_ids),
            0,
            f"review_inbox() leaked {len(all_ids)} rows to unowned brand; "
            f"example: {all_ids[:3]}",
        )

    def test_live_call_returns_owned_campaigns(self):
        """Live call: with swing-shack brand, its owned campaigns must appear."""
        for mod_name in [k for k in sys.modules if k.startswith("_lib")]:
            sys.modules.pop(mod_name, None)
        sys.path.insert(0, str(REPO / "campaign-os"))
        from _lib import intelligence as intel

        try:
            intel.set_request_brand("swing-shack")
            out = intel.review_inbox()
        finally:
            intel.clear_request_brand()

        # The live dataset has 4 swing-shack campaigns. At least one
        # owned campaign must surface in the pending bucket.
        owned_cids = set(
            json.loads((REPO / "data" / "brands.json").read_text())
            .get("brands", {})
            .get("swing-shack", {})
            .get("campaign_ids", [])
        )
        self.assertTrue(owned_cids, "brands.json has no swing-shack campaign_ids")
        pending_cids = {x["campaignId"] for x in out.get("pending", [])}
        overlap = pending_cids & owned_cids
        self.assertTrue(
            overlap,
            f"review_inbox() returned no swing-shack-owned campaigns; "
            f"pending_cids={list(pending_cids)[:5]}, owned={list(owned_cids)[:5]}",
        )


if __name__ == "__main__":
    unittest.main()
