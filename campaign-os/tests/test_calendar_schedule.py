"""Calendar scheduling API tests.

These tests exercise the real Flask routes against an isolated DATA_DIR.  The
bundled campaign-data.json is never modified; runtime writes go to the temp
persistent-disk equivalent, exactly as they do in production.
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
REPO_ROOT = CAMPAIGN_OS.parent


class CalendarScheduleApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-calendar-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app

        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()
        # Do not let a test request attempt a network git bootstrap.
        cls.module.init_repo = lambda: None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)

    def setUp(self):
        self._write_fixture()
        schedule_path = self.tmpdir / "scheduled-items.json"
        if schedule_path.exists():
            schedule_path.unlink()
        self.git_patch = patch.object(self.module, "git_push", return_value=(True, "test sync"))
        self.git_patch.start()

    def tearDown(self):
        self.git_patch.stop()

    def _write_fixture(self):
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
                            "pillarName": "Education",
                            "caption": "Stop guessing about your slice.",
                            "approvalStatus": "approved",
                            "publishStatus": "planned",
                            "publishingReferences": [{"postizId": "old-post"}],
                            "history": [{"event": "created"}],
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
        # Keep route tests focused on their fixture. The live app's bundled
        # queue is intentionally populated and is tested separately.
        (self.tmpdir / "publish-queue.json").write_text(
            json.dumps({"queued": []}), encoding="utf-8"
        )

    def _write_queue_fixture(self):
        queue = json.loads((REPO_ROOT / "data" / "publish-queue.json").read_text())
        item = queue["queued"][0]
        (self.tmpdir / "publish-queue.json").write_text(
            json.dumps({"queued": [item]}), encoding="utf-8"
        )
        return item["item_id"]

    def test_get_schedule_returns_publisher_shape_without_mutating_source(self):
        response = self.client.get("/api/schedule")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["ok"])
        self.assertIsInstance(body["scheduled"], list)
        self.assertEqual(body["total"], 0)

    def test_reschedule_writes_sidecar_and_calendar_uses_override(self):
        target = "2026-08-02T09:00:00Z"
        response = self.client.post(
            "/api/schedule/asset-1",
            json={"campaignId": "winter-golf", "scheduledFor": target},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["scheduledFor"], target)
        self.assertIsNone(body["previousScheduledFor"])

        manifest = json.loads((self.tmpdir / "scheduled-items.json").read_text())
        self.assertEqual(manifest["total"], 1)
        self.assertEqual(manifest["scheduled"][0]["assetId"], "asset-1")
        self.assertEqual(manifest["scheduled"][0]["scheduledFor"], target)

        calendar = self.client.get(
            "/api/intel/calendar?days=1&start=2026-08-02"
        ).get_json()
        self.assertEqual(calendar["totalScheduled"], 1)
        slot = calendar["days"][0]["slots"][0]
        self.assertEqual(slot["assetId"], "asset-1")
        self.assertEqual(slot["scheduledFor"], target)
        self.assertEqual(slot["source"], "calendar")
        self.assertTrue(slot["color"].startswith("#"))

    def test_invalid_schedule_is_rejected_without_file_write(self):
        response = self.client.post(
            "/api/schedule/asset-1",
            json={"scheduledFor": "not-a-date"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("ISO", response.get_json()["error"])
        self.assertFalse((self.tmpdir / "scheduled-items.json").exists())

        missing = self.client.post(
            "/api/schedule/not-real",
            json={"scheduledFor": "2026-08-02T09:00:00Z"},
        )
        self.assertEqual(missing.status_code, 404)

    def test_duplicate_creates_new_asset_via_api_and_schedules_it(self):
        target = "2026-08-04T12:30:00Z"
        response = self.client.post(
            "/api/schedule/asset-1/duplicate",
            json={"campaignId": "winter-golf", "scheduledFor": target},
        )
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertTrue(body["ok"])
        new_id = body["newAssetId"]
        self.assertNotEqual(new_id, "asset-1")
        self.assertEqual(body["scheduledFor"], target)

        data = json.loads((self.tmpdir / "campaign-data.json").read_text())
        new_asset = data["campaigns"]["winter-golf"]["assets"][new_id]
        self.assertEqual(new_asset["assetId"], new_id)
        self.assertEqual(new_asset["campaignId"], "winter-golf")
        self.assertEqual(new_asset["publishStatus"], "planned")
        self.assertEqual(new_asset["approvalStatus"], "draft")
        self.assertEqual(new_asset["publishingReferences"], [])
        self.assertEqual(new_asset["scheduledFor"], target)
        self.assertEqual(len(data["campaigns"]["winter-golf"]["assets"]), 2)

        manifest = json.loads((self.tmpdir / "scheduled-items.json").read_text())
        ids = {item["assetId"] for item in manifest["scheduled"]}
        self.assertIn(new_id, ids)

    def test_queue_item_can_be_scheduled_without_campaign_data_mutation(self):
        queue_id = self._write_queue_fixture()
        response = self.client.post(
            f"/api/schedule/{queue_id}",
            json={"scheduledFor": "2026-08-05T18:00:00Z"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"], "queue")
        manifest = json.loads((self.tmpdir / "scheduled-items.json").read_text())
        self.assertEqual(manifest["scheduled"][0]["assetId"], queue_id)
        data = json.loads((self.tmpdir / "campaign-data.json").read_text())
        self.assertEqual(list(data["campaigns"]["winter-golf"]["assets"]), ["asset-1"])

    def test_queue_duplicate_is_visible_as_a_calendar_slot(self):
        queue_id = self._write_queue_fixture()
        response = self.client.post(
            f"/api/schedule/{queue_id}/duplicate",
            json={"scheduledFor": "2026-08-05T18:00:00Z"},
        )
        self.assertEqual(response.status_code, 201)
        new_id = response.get_json()["newAssetId"]
        calendar = self.client.get(
            "/api/intel/calendar?days=1&start=2026-08-05"
        ).get_json()
        ids = {slot.get("assetId") for slot in calendar["days"][0]["slots"]}
        self.assertIn(new_id, ids)
        copied = next(slot for slot in calendar["days"][0]["slots"] if slot.get("assetId") == new_id)
        self.assertEqual(copied["source"], "calendar")
        self.assertEqual(copied["scheduledFor"], "2026-08-05T18:00:00Z")


if __name__ == "__main__":
    unittest.main(verbosity=2)
