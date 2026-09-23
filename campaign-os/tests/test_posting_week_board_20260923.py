"""Review this week — GET /api/inbox/week horizon join (2026-09-23 ticket)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]


class PostingWeekBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-posting-week-"))
        cls._prev_data_dir = os.environ.get("DATA_DIR")
        cls._prev_sandbox_dir = os.environ.get("PUBLISH_SANDBOX_DIR")
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        sys.path.insert(0, str(CAMPAIGN_OS))
        from _lib import publish_sandbox

        publish_sandbox.ensure_sandbox_layout()
        cls.cal_dir = cls.tmpdir / "intelligence" / "marketing-calendar"
        cls.cal_dir.mkdir(parents=True, exist_ok=True)
        cls.brand = "swing-shack"
        cls.cal_id = "cal-swing-shack-moment-test-3b25b978"
        cls.start = "2026-09-23"
        cls.event_day = "2026-09-24"
        cls.campaign_id = "cos-drafts-swing-shack"
        cls.asset_id = "draft-testasset01"
        cls.inbox_ref = f"calendar_candidate:{cls.brand}:{cls.cal_id}"

        moment = {
            "calendar_id": cls.cal_id,
            "event_key": f"{cls.brand}:operator-{cls.event_day}-book-fitting",
            "brand_id": cls.brand,
            "type": "moment",
            "status": "approved",
            "title": "Book your fitting",
            "event_date": cls.event_day,
            "event_start": cls.event_day,
            "source_type": "operator",
            "primary_channel": "facebook",
            "revision": 1,
        }
        (cls.cal_dir / f"{cls.brand}.jsonl").write_text(json.dumps(moment) + "\n", encoding="utf-8")

        campaign_data = {
            "campaigns": {
                cls.campaign_id: {
                    "assets": {
                        cls.asset_id: {
                            "caption": "Book your fitting caption",
                            "approvalStatus": "draft",
                            "platform": "facebook",
                            "updatedAt": "2026-09-23T12:00:00Z",
                        }
                    }
                }
            }
        }
        (cls.tmpdir / "campaign-data.json").write_text(json.dumps(campaign_data), encoding="utf-8")

        sidecar_dir = cls.tmpdir / "draft-assets"
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        sidecar = {
            "schema": "campaign-os/draft-asset/v1",
            "asset_id": cls.asset_id,
            "campaign_id": cls.campaign_id,
            "brand_id": cls.brand,
            "source_inbox_item_id": cls.inbox_ref,
            "created_at": "2026-09-23T12:00:00Z",
        }
        (sidecar_dir / f"{cls.asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")

        queue_row = {
            "idempotency_key": f"qc-{cls.asset_id}-facebook",
            "platform": "facebook",
            "brand_id": cls.brand,
            "caption_preview": "Book your fitting caption",
            "human_approved": False,
            "channel": "postiz",
            "status": "pending",
            "created_at": "2026-09-23T12:00:00Z",
            "inbox_item_id": cls.inbox_ref,
        }
        queue_path = publish_sandbox._queue_path()
        queue_path.write_text(json.dumps(queue_row) + "\n", encoding="utf-8")

        orphan_asset = "draft-orphan01"
        (sidecar_dir / f"{orphan_asset}.json").write_text(
            json.dumps(
                {
                    "asset_id": orphan_asset,
                    "brand_id": cls.brand,
                    "source_inbox_item_id": "proposal:swing-shack:orphan",
                }
            ),
            encoding="utf-8",
        )

        import app as app_module

        cls.app_module = app_module
        cls.client = app_module.app.test_client()

    @classmethod
    def tearDownClass(cls):
        if cls._prev_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = cls._prev_data_dir
        if cls._prev_sandbox_dir is None:
            os.environ.pop("PUBLISH_SANDBOX_DIR", None)
        else:
            os.environ["PUBLISH_SANDBOX_DIR"] = cls._prev_sandbox_dir

    def test_horizon_join_on_event_day(self):
        resp = self.client.get(
            f"/api/inbox/week?brand={self.brand}&start={self.start}&days=7"
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get("ok"))
        day = next(d for d in body["days_list"] if d["date"] == self.event_day)
        posts = day["posts"]
        self.assertEqual(len(posts), 1)
        post = posts[0]
        self.assertEqual(post["calendar_id"], self.cal_id)
        self.assertEqual(post["title"], "Book your fitting")
        stages = post["stages"]
        self.assertTrue(stages["booked"])
        self.assertTrue(stages["caption"])
        self.assertTrue(stages["in_review"])
        self.assertTrue(stages["queued"])
        self.assertEqual(post["stage"], "queued")

    def test_approved_moment_status_included(self):
        from _lib import unified_inbox

        payload = unified_inbox.week_board(
            brand_id=self.brand,
            start=__import__("datetime").date.fromisoformat(self.start),
            days=7,
        )
        ids = [
            p["calendar_id"]
            for day in payload["days_list"]
            for p in day["posts"]
        ]
        self.assertIn(self.cal_id, ids)

    def test_orphan_draft_counted(self):
        resp = self.client.get(
            f"/api/inbox/week?brand={self.brand}&start={self.start}&days=7"
        )
        body = resp.get_json()
        self.assertGreaterEqual(body.get("orphan_drafts", 0), 1)

    def test_anon_gets_401(self):
        anon = self.app_module.app.test_client(cos_anon=True)
        resp = anon.get(f"/api/inbox/week?brand={self.brand}")
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.get_json().get("ok"))


if __name__ == "__main__":
    unittest.main()
