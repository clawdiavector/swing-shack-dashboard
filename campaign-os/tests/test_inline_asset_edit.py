"""Inline asset edit API tests.

Exercises the PATCH /api/assets/<id> endpoint that allows editing captions,
visual briefs, image prompts, etc. without going through the full review
workflow. Campaign-data.json is rewritten to a temp DATA_DIR.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


CAMPAIGN_OS = Path(__file__).resolve().parents[1]


class InlineAssetEditApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-inline-edit-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app
        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()
        cls.module.init_repo = lambda: None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)

    def setUp(self):
        fixture = {
            "portfolioMetadata": {"name": "Test portfolio"},
            "activeCampaignId": "winter-golf",
            "campaigns": {
                "winter-golf": {
                    "identity": {
                        "campaignId": "winter-golf",
                        "name": "Winter Golf",
                        "status": "active",
                        "goal": "Drive winter bookings",
                    },
                    "assets": {
                        "asset-1": {
                            "assetId": "asset-1",
                            "campaignId": "winter-golf",
                            "name": "Driver slice diagnostic",
                            "assetType": "feed-post",
                            "platform": "instagram",
                            "pillar": "education",
                            "caption": "Original caption text.",
                            "visualBrief": "Original brief.",
                            "approvalStatus": "draft",
                            "publishStatus": "planned",
                            "history": [{"event": "created", "ts": "2026-07-27T07:00:00Z"}],
                            "publishingReferences": [{"postizId": "old-post"}],
                            "createdAt": "2026-07-27T07:00:00Z",
                            "updatedAt": "2026-07-27T07:00:00Z",
                        }
                    },
                }
            },
            "updatedAt": "2026-07-27T07:00:00Z",
        }
        (self.tmpdir / "campaign-data.json").write_text(
            json.dumps(fixture), encoding="utf-8"
        )
        self.git_patch = patch.object(self.module, "git_push", return_value=(True, "test sync"))
        self.git_patch.start()

    def tearDown(self):
        self.git_patch.stop()

    def test_patch_caption_returns_changes_and_preserves_approval_state(self):
        response = self.client.patch(
            "/api/assets/asset-1",
            json={"campaignId": "winter-golf",
                  "caption": "Refined caption with more punch."},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["asset"]["caption"], "Refined caption with more punch.")
        self.assertEqual(body["asset"]["approvalStatus"], "draft")  # unchanged
        self.assertEqual(body["asset"]["publishingReferences"], [{"postizId": "old-post"}])  # preserved
        self.assertEqual(len(body["changes"]), 1)
        self.assertEqual(body["changes"][0]["field"], "caption")
        self.assertEqual(body["changes"][0]["old"], "Original caption text.")
        self.assertEqual(body["changes"][0]["new"], "Refined caption with more punch.")

        # History was appended
        history = body["asset"]["history"]
        self.assertGreaterEqual(len(history), 2)
        last = history[-1]
        self.assertEqual(last["event"], "inline-edit")
        self.assertEqual(last["fields"], ["caption"])

    def test_patch_multiple_fields_normalises_hashtags_and_rejects_unknown(self):
        response = self.client.patch(
            "/api/assets/asset-1",
            json={
                "campaignId": "winter-golf",
                "visualBrief": "New brief",
                "headline": "Drop the slice in 6 swings",
                "hashtags": "#golf #johannesburg #trackman",
                "approvalStatus": "approved",  # forbidden via inline edit
                "publishingReferences": [{"postizId": "fake"}],  # forbidden
                "notes": "ready to ship",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["ok"])
        a = body["asset"]
        self.assertEqual(a["visualBrief"], "New brief")
        self.assertEqual(a["headline"], "Drop the slice in 6 swings")
        self.assertEqual(a["hashtags"], ["golf", "johannesburg", "trackman"])  # normalised
        self.assertEqual(a["notes"], "ready to ship")
        self.assertEqual(a["approvalStatus"], "draft")  # rejected — unchanged
        self.assertEqual(a["publishingReferences"], [{"postizId": "old-post"}])  # rejected — unchanged
        self.assertIn("approvalStatus", body["rejectedFields"])
        self.assertIn("publishingReferences", body["rejectedFields"])
        self.assertEqual(len(body["changes"]), 4)

    def test_patch_missing_campaign_id_returns_400(self):
        response = self.client.patch(
            "/api/assets/asset-1",
            json={"caption": "orphan edit"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("campaignId", response.get_json()["error"])

    def test_patch_unknown_asset_returns_404(self):
        response = self.client.patch(
            "/api/assets/does-not-exist",
            json={"campaignId": "winter-golf", "caption": "ghost"},
        )
        self.assertEqual(response.status_code, 404)

    def test_patch_unknown_campaign_returns_404(self):
        response = self.client.patch(
            "/api/assets/asset-1",
            json={"campaignId": "no-such", "caption": "ghost"},
        )
        self.assertEqual(response.status_code, 404)

    def test_patch_no_changes_returns_message_no_changes(self):
        response = self.client.patch(
            "/api/assets/asset-1",
            json={"campaignId": "winter-golf", "caption": "Original caption text."},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["message"], "no changes")
        self.assertEqual(body["changes"], [])

    def test_patch_invalid_scheduledFor_returns_400(self):
        response = self.client.patch(
            "/api/assets/asset-1",
            json={"campaignId": "winter-golf", "scheduledFor": "not-a-date"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("ISO", response.get_json()["error"])

    def test_patch_persists_to_disk(self):
        response = self.client.patch(
            "/api/assets/asset-1",
            json={"campaignId": "winter-golf", "imagePrompt": "Studio shot, golfer mid-swing"},
        )
        self.assertEqual(response.status_code, 200)
        # Reload disk and verify
        data = json.loads((self.tmpdir / "campaign-data.json").read_text())
        asset = data["campaigns"]["winter-golf"]["assets"]["asset-1"]
        self.assertEqual(asset["imagePrompt"], "Studio shot, golfer mid-swing")
        # History entry persisted
        self.assertTrue(any(e.get("event") == "inline-edit" for e in asset["history"]))

    def test_get_history_returns_timeline(self):
        # First do a patch
        self.client.patch(
            "/api/assets/asset-1",
            json={"campaignId": "winter-golf", "caption": "First edit"},
        )
        response = self.client.get("/api/assets/asset-1/history?campaignId=winter-golf")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["assetId"], "asset-1")
        self.assertEqual(body["campaignId"], "winter-golf")
        self.assertGreaterEqual(body["historyTotal"], 2)
        last_event = body["history"][-1]
        self.assertEqual(last_event["event"], "inline-edit")
        self.assertEqual(last_event["fields"], ["caption"])

    def test_history_finds_asset_without_campaignId_hint(self):
        response = self.client.get("/api/assets/asset-1/history")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["campaignId"], "winter-golf")

    def test_history_missing_asset_returns_404(self):
        response = self.client.get("/api/assets/no-such/history?campaignId=winter-golf")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)