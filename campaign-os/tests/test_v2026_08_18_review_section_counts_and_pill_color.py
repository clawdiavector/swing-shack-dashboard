"""v2026-08-18 — Review queue: section counts + pending breakdown + planned pill color.

Background
----------
The Review queue on the Review tab renders three sub-sections (Pending /
Approved / Rejected) with no count badge on the sub-header. The user has
to count rows manually to know there are 41 pending items, even though
the sidebar badge already shows "41". The Pending bucket itself hides
the draft-vs-review split: 35 items have `publishStatus=planned` (ready
for human review) and 6 items have no publishStatus (still agent-drafting,
rotting at 64-76 days old). The user couldn't see this split without
scrolling the whole list.

The `planned` publishStatus pill was rendered with the `.pill.draft`
class (gray) because `pill()` fell through to the default branch. But
semantically "planned" means "ready to schedule" — it should be visually
distinct from "draft" (gray, unfinished). The fix maps `planned` to the
existing `.pill.live` class (blue), matching the platform pill colour
so the planned items read as "ready to go" instead of "unfinished".

The 35 UTR Campaign rows have `updatedAt: null`, so the date span was
rendering as `<span class="muted"></span>` (empty). Skipped that span
when `updatedAt` is missing instead of leaving a blank trailing slot.

Fix
---
`renderReview()` in `campaign-os.html` now:
1. Writes the row count into `#review-pending-count`, `#review-approved-count`,
   `#review-rejected-count` so the sub-section H3 reads "Pending (41)" etc.
2. Computes the pending bucket split (drafts vs review-ready) and writes
   "35 ready for review · 6 still drafting" into #review-pending-breakdown
   (only when both buckets are non-empty so single-bucket queues stay clean).
3. Maps `publishStatus=planned` to `.pill.live` (blue) instead of falling
   through to `.pill.draft` (gray).
4. Skips the row date span when `updatedAt` is null.

This test pins:
  1. count badge IDs exist in the section header HTML
  2. breakdown span ID exists in the Pending header
  3. renderReview() writes the count into each badge
  4. renderReview() writes the breakdown copy when both buckets exist
  5. renderReview() hides the breakdown span when only one bucket exists
  6. the planned pill uses `.pill.live` (blue) instead of `.pill.draft` (gray)
  7. the row date span is skipped when updatedAt is null
  8. no em-dashes in the new copy (standing rule)
"""
from __future__ import annotations

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
HTML_PATH = os.path.join(ROOT, "campaign-os", "campaign-os.html")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class ReviewSectionCountsAndPillColorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(HTML_PATH)

    def test_section_count_badges_present_in_html(self):
        """The header HTML must contain the IDs that renderReview() writes to."""
        self.assertIn('id="review-pending-count"', self.html,
                      "Pending h3 must have an id=review-pending-count badge")
        self.assertIn('id="review-pending-breakdown"', self.html,
                      "Pending h-meta must have an id=review-pending-breakdown span")
        self.assertIn('id="review-approved-count"', self.html,
                      "Approved h3 must have an id=review-approved-count badge")
        self.assertIn('id="review-rejected-count"', self.html,
                      "Rejected h3 must have an id=review-rejected-count badge")

    def test_renderReview_writes_count_into_each_badge(self):
        """renderReview() must populate the three count badges from the API response."""
        # The actual source uses `if (_countEls.pending)  _countEls.pending.textContent = ...`
        # so we match the write line within a short window of the read.
        for label, key in [
            ("pending",  "pending"),
            ("approved", "approved"),
            ("rejected", "rejected"),
        ]:
            # Use re.search (not assertRegex) + a small window so we can
            # give a clearer error message when the test fails.
            pattern = rf"_countEls\.{label}\s*[\)&]?[\s\S]{{0,40}}?_countEls\.{label}\.textContent\s*=\s*\(\s*r\.{key}\s*\|\|\s*\[\]\s*\)\.length"
            with self.subTest(badge=label):
                self.assertRegex(
                    self.html, pattern,
                    f"renderReview must write {key} count from r.{key}.length",
                )

    def test_renderReview_writes_breakdown_copy_when_both_buckets_exist(self):
        """The breakdown span gets 'X ready for review · Y still drafting' when both buckets > 0."""
        self.assertIn("ready for review", self.html,
                      "breakdown copy must use 'ready for review' phrasing")
        self.assertIn("still drafting", self.html,
                      "breakdown copy must use 'still drafting' phrasing for the non-ready bucket")
        # The renderReview() block must compute the split via publishStatus==='planned'
        self.assertRegex(self.html,
            r"""_pendingReviews\s*=\s*\(r\.pending\s*\|\|\s*\[\]\s*\)\.filter\(\s*x\s*=>\s*\(x\.publishStatus\s*\|\|\s*''\)\.toLowerCase\(\)\s*===\s*'planned'\s*\)\.length""",
            "renderReview must derive the ready-for-review count from publishStatus==='planned'")

    def test_renderReview_hides_breakdown_when_only_one_bucket_exists(self):
        """If everything is 'planned' or everything is 'draft', the breakdown span should hide, not show '0 ready for review'."""
        self.assertRegex(self.html,
            r'if\s*\(\s*_pendingDrafts\s*>\s*0\s*&&\s*_pendingReviews\s*>\s*0\s*\)',
            "renderReview must guard the breakdown render on both buckets > 0 so the copy never reads '0 ready for review'")

    def test_planned_pill_uses_live_class_not_draft(self):
        """The pill() call for publishStatus must map 'planned' to 'live' (blue), not 'draft' (gray)."""
        m = re.search(
            r"x\.publishStatus\s*\?\s*pill\(x\.publishStatus==='scheduled'\?'on':x\.publishStatus==='published'\?'review':x\.publishStatus==='planned'\?'live':'draft',\s*x\.publishStatus\)",
            self.html,
        )
        self.assertIsNotNone(m,
            "publishStatus pill must map 'planned' to 'live' class (blue) so it reads as 'ready to schedule' not 'unfinished'")

    def test_row_date_span_skipped_when_updatedAt_missing(self):
        """renderRow() must use `x.updatedAt ? <span>... : ''` so null-updatedAt rows don't render an empty muted span."""
        self.assertRegex(self.html,
            r"x\.updatedAt\s*\?\s*`<span class=\"muted\">\s*\$\{esc\(x\.updatedAt\.slice\(0,10\)\)\}\s*</span>`",
            "renderRow must guard the date span on x.updatedAt so null rows don't render an empty span")

    def test_no_em_dashes_in_new_copy(self):
        """Standing rule: no em-dashes in published copy."""
        new_strings = [
            "ready for review",
            "still drafting",
        ]
        for s in new_strings:
            self.assertNotIn("\u2014", s, f"new string must not contain em-dash: {s!r}")
        # Also verify the HTML doesn't introduce a new em-dash in the
        # review section header breakdown block
        for bad in ("\u2014ready for review", "\u2014still drafting",
                    "ready for review\u2014", "still drafting\u2014"):
            self.assertNotIn(bad, self.html, f"review section must not contain: {bad!r}")


if __name__ == "__main__":
    unittest.main()
