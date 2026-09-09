"""
Regression: morning_brief() Priority-1 "schedule this approved asset" must
NOT recommend assets whose own publishStatus flag is already 'scheduled'.

Background:
    2026-08-13T20:30Z nightshift tick caught a destructive CTA bug. The
    Brief page surfaced a "📌 Put on calendar (next slot)" recommendation
    for an Instagram asset with:
        approvalStatus = "approved"
        publishStatus  = "scheduled"
        scheduledFor   = (missing)
    The same asset was NOT in `ready_to_publish` (because the loop that
    builds that list filters out ps='scheduled'), so the brief strip
    showed "0 ready to publish" while the recommendation card above
    contradicted that with a primary CTA to put it on the next empty
    slot. Clicking the CTA silently upserted the asset into the runtime
    schedule manifest with a NEW scheduledFor (overwriting the existing
    slot stored under the campaign-data.json publishStatus flag — two
    sources of truth that had drifted out of sync).

Root cause:
    The Priority-1 `already_scheduled` check only consulted
    (a) the runtime `scheduled-items.json` manifest and
    (b) the asset's own `scheduledFor` field.
    It missed (c) the asset's `publishStatus` flag — which is the
    canonical signal that the asset is on the rail, regardless of
    whether the runtime manifest has been synced.

Fix:
    `_lib/intelligence.py::morning_brief()` Priority-1 now treats an
    asset as already-scheduled when ANY of:
        - aid in scheduled_set
        - asset.scheduledFor is truthy
        - asset.publishStatus in ('scheduled', 'published')
    The fix is a pure additive widening of the predicate; no other
    branches or downstream consumers change. Click-the-CTA contract is
    now consistent with the `ready_to_publish` filter that the rest of
    the brief uses.

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
from _lib.intelligence import morning_brief  # noqa: E402


def _make_data(per_asset):
    """Build a synthetic _campaign_data payload.

    `per_asset` is a list of dicts with the keys we care about:
        aid, approvalStatus, publishStatus, scheduledFor, updatedAt
    Insertion order is preserved via the assetId suffix.
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    assets = {}
    for i, spec in enumerate(per_asset):
        aid = spec.get("aid") or f"asset-{i:03d}"
        age = spec.get("age_days")
        ua = None if age is None else (now - _dt.timedelta(days=age)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assets[aid] = {
            "name": spec.get("name", aid),
            "approvalStatus": spec.get("approvalStatus", "draft"),
            "publishStatus": spec.get("publishStatus", ""),
            "scheduledFor": spec.get("scheduledFor"),
            "updatedAt": ua,
        }
    return {"campaigns": {"camp-1": {"identity": {"name": "Camp-1"}, "assets": assets}}}


class TestBriefRecommendedActionSkipsAlreadyScheduled(unittest.TestCase):
    """The Priority-1 recommendation must skip assets that are already
    on the rail under ANY of the three flags."""

    def _view(self, per_asset, do_first=None):
        payload = _make_data(per_asset)
        do_first = do_first if do_first is not None else []
        def _rj(path, *a, **kw):
            if "recommendation-scores" in str(path):
                return {"do_first": do_first}
            return {}
        with patch.object(intelligence, "_campaign_data", return_value=payload), \
             patch.object(intelligence, "_read_json", side_effect=_rj), \
             patch.object(intelligence, "_filter_fresh_ideas", return_value=[]), \
             patch.object(intelligence, "_enrich_do_first_where", side_effect=lambda x: x), \
             patch.object(intelligence, "_runtime_data_file", return_value="/dev/null"):
            return morning_brief()

    def test_publishStatus_scheduled_skipped_from_recommendation(self):
        """The exact live scenario: approved + publishStatus=scheduled
        and no scheduledFor and not in runtime manifest → must NOT be
        surfaced as the Priority-1 schedule action."""
        out = self._view([
            # The asset that triggered the bug
            {
                "aid": "use-the-right-equipment-mq5l90bk-feed-post-04",
                "approvalStatus": "approved",
                "publishStatus": "scheduled",
                "scheduledFor": None,
                "age_days": 21,
            },
            # A second approved asset that IS unscheduled (control)
            {
                "aid": "control-fresh-approved",
                "approvalStatus": "approved",
                "publishStatus": "",
                "scheduledFor": None,
                "age_days": 2,
            },
        ])
        rec = out.get("recommended_action") or {}
        # The flagged-already-scheduled asset must NEVER be the recommendation
        self.assertNotEqual(
            rec.get("assetId"),
            "use-the-right-equipment-mq5l90bk-feed-post-04",
            f"Priority-1 must not surface an already-scheduled asset "
            f"(got {rec})",
        )
        # ...but a truly-fresh approved asset must still surface (control)
        self.assertEqual(rec.get("type"), "schedule")
        self.assertEqual(rec.get("assetId"), "control-fresh-approved")

    def test_publishStatus_published_skipped_from_recommendation(self):
        """An asset that already shipped must never be re-recommended."""
        out = self._view([
            {
                "aid": "shipped-asset",
                "approvalStatus": "approved",
                "publishStatus": "published",
                "scheduledFor": None,
                "age_days": 60,
            },
        ])
        rec = out.get("recommended_action") or {}
        self.assertNotEqual(rec.get("type"), "schedule")
        self.assertNotEqual(rec.get("assetId"), "shipped-asset")

    def test_scheduledFor_present_skipped_from_recommendation(self):
        """An asset with its own scheduledFor timestamp is already on the rail."""
        out = self._view([
            {
                "aid": "self-stamped",
                "approvalStatus": "approved",
                "publishStatus": "",
                "scheduledFor": "2026-08-20T09:00:00Z",
                "age_days": 5,
            },
        ])
        rec = out.get("recommended_action") or {}
        self.assertNotEqual(rec.get("type"), "schedule")

    def test_truly_unscheduled_approved_still_surfaces(self):
        """Control: an asset with no scheduling signal at all must still
        be surfaced as the Priority-1 schedule action."""
        out = self._view([
            {
                "aid": "truly-fresh-approved",
                "approvalStatus": "approved",
                "publishStatus": "",
                "scheduledFor": None,
                "age_days": 1,
            },
        ])
        rec = out.get("recommended_action") or {}
        self.assertEqual(rec.get("type"), "schedule")
        self.assertEqual(rec.get("assetId"), "truly-fresh-approved")
        # Rationale must be the canonical 'approved but never scheduled'
        self.assertIn("never put on the calendar", out.get("recommended_rationale") or "")

    def test_ready_to_publish_excludes_publishStatus_scheduled(self):
        """The sibling `ready_to_publish` filter must still skip
        publishStatus=scheduled assets. This locks the invariant: the
        brief's Ready-to-publish count and its Priority-1
        recommendation will never disagree about whether an asset is
        on the rail."""
        out = self._view([
            {
                "aid": "scheduled-only",
                "approvalStatus": "approved",
                "publishStatus": "scheduled",
                "scheduledFor": None,
                "age_days": 21,
            },
        ])
        rtp_ids = [x.get("assetId") for x in out.get("ready_to_publish", [])]
        self.assertNotIn("scheduled-only", rtp_ids)
        # And the recommendation must not be a schedule action either
        rec = out.get("recommended_action") or {}
        self.assertNotEqual(rec.get("type"), "schedule")


class TestBriefPriority2RepostHeadlineFromNestedItem(unittest.TestCase):
    """When Priority-1 has nothing to recommend, the fallback walks
    do_first[0] for a "repost" candidate. The live do_first[0] shape
    is {emoji, item:{hook}, label, slot, where} — the headline lives
    under item.hook, not at the top level. The original code only
    looked at top.headline/title/name which were None for "post" rows,
    so the renderer fell back to "No urgent action" while the rationale
    said "Top IG performer · make a fresh take" — internally
    inconsistent card. Fix: walk item.hook as a deeper fallback."""

    def _view(self, do_first):
        # Empty campaigns so Priority-1 has no candidate and we fall
        # straight through to Priority-2.
        payload = {"campaigns": {}}
        def _rj(path, *a, **kw):
            if "recommendation-scores" in str(path):
                return {"do_first": do_first}
            return {}
        with patch.object(intelligence, "_campaign_data", return_value=payload), \
             patch.object(intelligence, "_read_json", side_effect=_rj), \
             patch.object(intelligence, "_filter_fresh_ideas", return_value=[]), \
             patch.object(intelligence, "_enrich_do_first_where", side_effect=lambda x: x), \
             patch.object(intelligence, "_runtime_data_file", return_value="/dev/null"):
            return morning_brief()

    def test_post_slot_recommendation_pulls_headline_from_item_hook(self):
        """The exact live shape: do_first[0] is a "post" slot wrapped
        as {emoji, item:{hook}, label, slot, where}. Priority-2 must
        surface the hook as the headline, otherwise the renderer
        silently drops it to a "No urgent action" card."""
        out = self._view([
            {
                "emoji": "🎯",
                "label": "Post this first",
                "slot": "post",
                "item": {"hook": "THAT SLICE COSTING YOU YARDS?", "score": 7},
                "where": {"label": "📱 Post on Instagram", "url": "https://app.postiz.com"},
            },
        ])
        rec = out.get("recommended_action") or {}
        self.assertEqual(rec.get("type"), "repost",
                         f"Expected type=repost fallback, got {rec}")
        self.assertEqual(rec.get("headline"), "THAT SLICE COSTING YOU YARDS?",
                         f"Headline must fall back through item.hook, got {rec.get('headline')!r}")
        self.assertIn("Top IG performer", out.get("recommended_rationale") or "")

    def test_top_level_headline_still_wins(self):
        """If top.headline is set, it must still win over item.hook
        (back-compat with any older do_first rows that surface the
        headline at the top level)."""
        out = self._view([
            {
                "label": "Custom label",
                "headline": "Top-level headline wins",
                "item": {"hook": "nested hook — should be ignored"},
            },
        ])
        rec = out.get("recommended_action") or {}
        self.assertEqual(rec.get("headline"), "Top-level headline wins")


if __name__ == "__main__":
    unittest.main()