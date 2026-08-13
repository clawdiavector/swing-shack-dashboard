"""
Regression: review_inbox() must float stale (>7d) pending drafts to the top
of the queue, oldest-first within stale.

Background:
    2026-08-13T19:18Z next-pick queue flagged: "Review Pending tab shows
    6 stale Takomo drafts buried mid-list instead of at the top. 7 of
    41 pending rows are rotting (>7d) but they're scattered; Christelle
    scrolls past 35 fresh rows to find them." The renderReview() side
    already colour-codes stale via reviewAgePill(), but the queue's
    *order* wasn't being sorted server-side. The review_inbox()
    docstring claimed "sorted by priority" but shipped no sort code.

Fix:
    review_inbox() now sorts `pending` by a (bucket, age_ms) key:
      - bucket 0 (stale, age > 7d) → emitted first
      - bucket 1 (fresh, age ≤ 7d) → emitted after
      - bucket 2 (no updatedAt)   → emitted last (bottom of fresh)
    Within bucket 0 the oldest item sorts first (highest -age_ms wins);
    within bucket 1 the most-recently-updated item sorts first so a
    campaign that just regenerated still reads top-down. Approved and
    rejected queues are left in natural order — they already cap at
    20/10 items so staleness isn't a UX problem there.

These tests monkey-patch intelligence._campaign_data() so each test
injects synthetic data without touching disk. No live server needed.
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "campaign-os"))

from _lib import intelligence  # noqa: E402
from _lib.intelligence import review_inbox  # noqa: E402


def _make_data(per_asset_status_age):
    """Build a synthetic _campaign_data payload.

    `per_asset_status_age` is a list of (approvalStatus, age_days_or_None)
    tuples. Insertion order is preserved as the assetId suffix.
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    assets = {}
    for i, (aps, age) in enumerate(per_asset_status_age):
        aid = f"asset-{i:03d}"
        if age is None:
            ua = None
        else:
            ua_dt = now - _dt.timedelta(days=age)
            ua = ua_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        assets[aid] = {"name": aid, "approvalStatus": aps, "updatedAt": ua}
    return {"campaigns": {"camp-1": {"identity": {"name": "Camp-1"}, "assets": assets}}}


class TestReviewInboxStaleFirst(unittest.TestCase):
    def _view(self, per_asset_status_age):
        payload = _make_data(per_asset_status_age)
        with patch.object(intelligence, "_campaign_data", return_value=payload):
            return review_inbox()

    def test_stale_floated_above_fresh_basic(self):
        """Mixed queue: stale items must come first (oldest-first within
        stale); fresh items must follow (most-recently-updated first so a
        campaign that just regenerated lands at the top of the fresh
        section)."""
        # Insertion order: 8d(stale), 0d(fresh), 12d(stale), 3d(fresh).
        out = self._view([
            ("draft", 8),
            ("draft", 0),
            ("draft", 12),
            ("draft", 3),
        ])
        assert out["ok"] is True, out
        ids = [r["assetId"] for r in out["pending"]]
        self.assertEqual(
            ids[:2], ["asset-002", "asset-000"],
            f"stale bucket should be oldest-first; got {ids[:2]} "
            f"(expected 12d then 8d)",
        )
        # Within fresh, most-recent-updated first: 0d (asset-001) before 3d (asset-003).
        self.assertEqual(
            ids[2:], ["asset-001", "asset-003"],
            f"fresh bucket should sort most-recent-updated first; got {ids[2:]}",
        )

    def test_no_updatedAt_falls_to_bottom(self):
        """Items with no updatedAt must sort into bucket 2 (bottom of fresh)."""
        out = self._view([
            ("draft", 2),
            ("draft", None),
            ("draft", 30),
            ("draft", None),
        ])
        ids = [r["assetId"] for r in out["pending"]]
        self.assertEqual(
            ids, ["asset-002", "asset-000", "asset-001", "asset-003"],
            f"no-updatedAt items should sink to bottom; got {ids}",
        )

    def test_seven_days_is_still_fresh(self):
        """Boundary: age == 7d is still fresh (the rule is strict >7d)."""
        out = self._view([("draft", 7)])
        self.assertEqual(len(out["pending"]), 1)
        self.assertEqual(out["pending"][0]["assetId"], "asset-000")

    def test_eight_days_is_stale(self):
        """Boundary: age == 8d lands in the stale bucket."""
        out = self._view([("draft", 8)])
        self.assertEqual(out["pending"][0]["assetId"], "asset-000")

    def test_approved_and_rejected_queues_unsorted(self):
        """Approved / rejected queues must keep insertion order — their
        counts are capped at 20 / 10 so staleness isn't a UX problem
        there."""
        out = self._view([
            ("approved", 60),
            ("approved", 1),
            ("rejected", 90),
            ("rejected", 2),
        ])
        approved_ids = [r["assetId"] for r in out["approved"]]
        rejected_ids = [r["assetId"] for r in out["rejected"]]
        self.assertEqual(approved_ids, ["asset-000", "asset-001"])
        self.assertEqual(rejected_ids, ["asset-002", "asset-003"])

    def test_archived_assets_never_surface(self):
        """archived must not appear in any queue regardless of age."""
        out = self._view([
            ("archived", 400),
            ("draft", 1),
        ])
        all_ids = (
            [r["assetId"] for r in out["pending"]]
            + [r["assetId"] for r in out["approved"]]
            + [r["assetId"] for r in out["rejected"]]
        )
        self.assertNotIn("asset-000", all_ids)
        self.assertIn("asset-001", all_ids)

    def test_summary_format_unchanged(self):
        """The summary string format must not change — fleet tests match it."""
        out = self._view([("draft", 8), ("draft", 1), ("draft", 30)])
        self.assertEqual(out["summary"], "3 pending review · 0 approved · 0 rejected")


if __name__ == "__main__":
    unittest.main()