"""Regression tests for the Library tab fixes (2026-08-18 nightshift).

Bug 1: $$('#lib-tabs .lib-tab').find(...) throws "$$(...).find is not a
       function" because $$ returns a NodeList, not an Array. The error
       was silent and left the Search-everything quick-launch tile
       broken: clicking it de-highlighted all tabs and left the pane
       stuck on the previous tab's content with no captions-tab search
       input.

Bug 2: /api/assets (GET) does not exist on the backend (404). The
       "approved" Library tab called it and showed "Failed to load."
       for every user on every brand. Fix swaps to /api/intel/review_inbox
       which returns the approved array pre-bucketed by the backend.
"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HTML = REPO / 'campaign-os' / 'campaign-os.html'


class TestLibrarySearchEverythingNodeListFix(unittest.TestCase):
    """The Search-everything quick-launch tile handler must spread the
    NodeList into an Array before calling .find()."""

    def setUp(self):
        self.html = HTML.read_text()

    def test_no_dollar_dollar_find_in_search_handler(self):
        # Find the lib-search-trigger click handler and verify the
        # offending pattern is gone.
        m = re.search(
            r"lib-search-trigger'\)\.addEventListener\('click'.*?\}\);",
            self.html, re.DOTALL,
        )
        self.assertIsNotNone(m, "lib-search-trigger click handler not found")
        body = m.group(0)
        # The original buggy line was:
        #   const captionsTab = $$('#lib-tabs .lib-tab').find(b => b.dataset.libTab === 'captions');
        # That threw "$$(...).find is not a function" because $$ returns a NodeList.
        self.assertNotIn("$$('#lib-tabs .lib-tab').find(", body,
                         "Buggy $$().find() call still in search-everything handler")
        # The fix spreads into Array first.
        self.assertIn("[...$$('#lib-tabs .lib-tab')].find(", body,
                      "Spread-then-find pattern missing from search-everything handler")

    def test_no_dollar_dollar_find_elsewhere(self):
        # No $$().find() chain anywhere in the file (it crashes silently
        # because $$ returns a NodeList). Single regression-prone spot.
        matches = re.findall(r"\$\$\([^)]*\)\.find\(", self.html)
        self.assertEqual(matches, [],
                         f"Found $$().find() calls (NodeList has no .find): {matches}")


class TestLibraryApprovedTabEndpointFix(unittest.TestCase):
    """The 'approved' Library tab must call /api/intel/review_inbox,
    not the nonexistent /api/assets GET endpoint."""

    def setUp(self):
        self.html = HTML.read_text()

    def test_approved_tab_does_not_call_broken_assets_endpoint(self):
        # The /api/assets (GET) endpoint does not exist on the backend.
        # Any code path that calls it produces a permanent "Failed to load."
        # for the user.
        self.assertNotIn(
            "/api/assets?status=approved",
            self.html,
            "Library 'approved' tab still calls nonexistent /api/assets endpoint",
        )

    def test_approved_tab_uses_review_inbox(self):
        # The new code path must fetch from /api/intel/review_inbox and
        # read r.approved.
        m = re.search(
            r"\} else if\(kind === 'approved'\)\{.*?\} else if\(kind === 'captions'",
            self.html, re.DOTALL,
        )
        self.assertIsNotNone(m, "approved tab block not found")
        block = m.group(0)
        self.assertIn("/api/intel/review_inbox", block,
                      "approved tab must call /api/intel/review_inbox")
        self.assertIn("r.approved", block,
                      "approved tab must read the r.approved array")
        # Empty-state copy must surface the active brand so the user can
        # see WHY the list is empty (different brand = different state).
        self.assertIn("No approved assets yet for", block,
                      "approved tab empty-state must mention active brand")

    def test_approved_tab_does_not_filter_out_brand_scoped_assets(self):
        # The brand_id (e.g. "swing-shack") is NOT a prefix of the
        # campaignId (e.g. "use-the-right-equipment-mq5l90bk"). A naive
        # client-side filter `a.campaignId.startsWith(bid)` would drop
        # legitimate Swing Shack assets. The fix trusts the backend's
        # bucketing and surfaces everything r.approved returns.
        m = re.search(
            r"\} else if\(kind === 'approved'\)\{.*?\} else if\(kind === 'captions'",
            self.html, re.DOTALL,
        )
        block = m.group(0)
        self.assertNotIn("startsWith(bid)", block,
                         "approved tab must NOT client-side filter by campaignId.startsWith(bid) — campaignId shape doesn't include the brand_id prefix")

    def test_approved_tab_uses_correct_field_names(self):
        # The backend returns assets with these fields: name, assetId,
        # campaignId, campaignName, platform, approvalStatus, publishStatus.
        # The renderer must read the correct ones (not a.title / a.kind /
        # a.pillar which never existed on this endpoint).
        m = re.search(
            r"\} else if\(kind === 'approved'\)\{.*?\} else if\(kind === 'captions'",
            self.html, re.DOTALL,
        )
        block = m.group(0)
        self.assertIn("a.name", block, "approved tab must render a.name")
        self.assertIn("a.campaignName", block, "approved tab must render a.campaignName")
        self.assertIn("a.platform", block, "approved tab must render a.platform")
        # These fields were never on the asset shape and would render "undefined":
        self.assertNotIn("a.title", block, "approved tab still reads a.title (was undefined)")
        self.assertNotIn("a.pillar", block, "approved tab still reads a.pillar (was undefined)")


if __name__ == '__main__':
    unittest.main(verbosity=2)
