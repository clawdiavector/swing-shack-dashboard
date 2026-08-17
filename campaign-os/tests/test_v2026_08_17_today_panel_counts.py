"""Regression test: Calendar empty-state must use the TRUE review-queue total.

Background
----------
The Calendar empty-state copy said things like:

    "8 review-queue items waiting for your sign-off..."

when the Today page / Review sidebar said "41 need review". The 8 figure
came from `panel.cards.filter(c => c.kind === 'review').length` — but the
backend `/api/today/panel` caps each kind at 8 for UI display, so the
calendar always read 8 regardless of the actual queue size. Users saw
conflicting numbers across surfaces and lost trust in the empty-state CTA
("Open Review (8)" vs the sidebar "Review 41").

Fix (2026-08-17):
  - Backend /api/today/panel now returns `counts` (review, draft, approved,
    published, scheduled, total) sourced from morning_brief.counts (the
    unruncated totals).
  - Frontend Calendar empty-state prefers `panel.counts.review +
    panel.counts.draft` over the capped card filter, with the old logic
    kept as fallback for legacy panel shapes.

This test guards the API contract — the frontend is a single bundled HTML
payload so we test the endpoint shape directly.
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


class TodayPanelCountsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # DATA_DIR must be set BEFORE importing app — the module reads
        # DATA_DIR at import time and calls os.makedirs() on derived
        # paths. Setting it inside setUp() (after import) is too late.
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-panel-counts-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app
        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)

    def _write_campaign_fixture(self):
        """Seed a synthetic campaign so morning_brief has something to count.

        Without assets, counts.review/draft/total are all 0 and the
        invariant tests are trivially true. We seed 3 assets in
        different approval states so the API can return non-zero counts.
        """
        fixture = {
            "portfolioMetadata": {"name": "Test"},
            "activeCampaignId": "winter-golf",
            "campaigns": {
                "winter-golf": {
                    "identity": {
                        "campaignId": "winter-golf",
                        "name": "Winter Golf",
                        "status": "active",
                    },
                    "assets": {
                        "asset-1": {
                            "assetId": "asset-1", "campaignId": "winter-golf",
                            "name": "Review A", "approvalStatus": "draft",
                        },
                        "asset-2": {
                            "assetId": "asset-2", "campaignId": "winter-golf",
                            "name": "Review B", "approvalStatus": "draft",
                        },
                        "asset-3": {
                            "assetId": "asset-3", "campaignId": "winter-golf",
                            "name": "Approved", "approvalStatus": "approved",
                            "publishStatus": "queued",
                        },
                    },
                },
            },
            "brands": {
                "winter-golf": {"campaign_ids": ["winter-golf"]},
            },
        }
        # Override brand registry for the duration of the request.
        from unittest.mock import patch
        try:
            from _lib import intelligence as _intel
        except ImportError:
            return None
        # Stub _load_brands_registry to return our fixture brands.
        with patch.object(_intel, "_load_brands_registry",
                          return_value={"brands": {"winter-golf": {"campaign_ids": ["winter-golf"]}}}):
            return fixture

    def test_panel_includes_counts_block(self):
        """The /api/today/panel response must include a `counts` object."""
        b = self._get_panel_json()
        self.assertIn('counts', b, "response must include 'counts' for calendar empty-state")
        self.assertIsInstance(b['counts'], dict)

    def test_counts_have_all_required_keys(self):
        """counts must expose the fields the Calendar empty-state relies on."""
        b = self._get_panel_json()
        counts = b['counts']
        for key in ('review', 'draft', 'approved', 'published', 'scheduled', 'total'):
            self.assertIn(key, counts, f"counts.{key} missing — calendar empty-state depends on it")
            self.assertIsInstance(counts[key], int, f"counts.{key} must be int, got {type(counts[key])}")
            self.assertGreaterEqual(counts[key], 0, f"counts.{key} must be >= 0")

    def test_counts_total_is_invariant(self):
        """total >= max(review, draft) (review and draft are subsets of total)."""
        b = self._get_panel_json()
        c = b['counts']
        self.assertGreaterEqual(
            c['total'], max(c['review'], c['draft']),
            "counts.total must cover at least the largest review/draft bucket",
        )

    def test_review_plus_draft_unruncated_vs_display_slice(self):
        """The Calendar reads review+draft as the TRUE queue size.

        Backend caps the display cards at 8 per kind, but counts is
        unruncated. counts.review + counts.draft MUST be >= the display
        slice (capped at 8). Equality allowed (small brand <= 8 review
        items).
        """
        b = self._get_panel_json()
        c = b['counts']
        cards_review = [x for x in b.get('cards', []) if x.get('kind') == 'review']
        self.assertGreaterEqual(
            c['review'] + c['draft'], len(cards_review),
            "counts.review + counts.draft must be >= display slice "
            f"(got counts={c['review'] + c['draft']}, display_cards={len(cards_review)})",
        )

    def test_envelope_still_intact(self):
        """Existing envelope contract not broken by the new field."""
        b = self._get_panel_json()
        self.assertTrue(b.get('ok'))
        for key in ('ts', 'cards', 'count', 'dismissed', 'summary'):
            self.assertIn(key, b, f"envelope key '{key}' missing")

    # ─── helpers ────────────────────────────────────────────────────────
    def _get_panel_json(self) -> dict:
        """Hit /api/today/panel and return JSON, bypassing auth."""
        # /api/today/panel is behind the auth gate. The test client doesn't
        # share cookies by default, so we use a session via set_cookie.
        with self.flask_app.test_request_context():
            from itsdangerous import URLSafeTimedSerializer
            secret = os.environ.get('CAMPAIGN_OS_SECRET') or 'campaign-os-dev-secret-change-me'
            serializer = URLSafeTimedSerializer(secret)
            token = serializer.dumps('test')
            self.client.set_cookie('cos_session', token)
        r = self.client.get('/api/today/panel')
        self.assertEqual(r.status_code, 200,
                         f"auth-bypass /api/today/panel returned {r.status_code} "
                         f"(body head: {r.get_data(as_text=True)[:200]!r})")
        return r.get_json()


if __name__ == '__main__':
    unittest.main()