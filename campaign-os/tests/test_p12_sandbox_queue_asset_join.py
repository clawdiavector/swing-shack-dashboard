"""P12 — sandbox queue joins draft asset_id → image_url; inbox type filter."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]


class SandboxQueueAssetJoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-p12-sandbox-"))
        cls._prev_data_dir = os.environ.get("DATA_DIR")
        cls._prev_sandbox_dir = os.environ.get("PUBLISH_SANDBOX_DIR")
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        sys.path.insert(0, str(CAMPAIGN_OS))
        from _lib import publish_sandbox, unified_inbox

        cls.publish_sandbox = publish_sandbox
        cls.unified_inbox = unified_inbox
        publish_sandbox.ensure_sandbox_layout()

    @classmethod
    def tearDownClass(cls):
        try:
            from _lib.intelligence import clear_request_brand

            clear_request_brand()
        except Exception:
            pass
        if cls._prev_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = cls._prev_data_dir
        if cls._prev_sandbox_dir is None:
            os.environ.pop("PUBLISH_SANDBOX_DIR", None)
        else:
            os.environ["PUBLISH_SANDBOX_DIR"] = cls._prev_sandbox_dir

    def test_asset_id_from_queue_row_hyphen_safe(self):
        fn = self.unified_inbox.asset_id_from_queue_row
        asset = "draft-a1b2c3d4e5f6"
        row = {"idempotency_key": f"qc-{asset}-instagram", "platform": "instagram"}
        self.assertEqual(fn(row), asset)
        row["platform"] = "facebook"
        row["idempotency_key"] = f"qc-{asset}-facebook"
        self.assertEqual(fn(row), asset)
        row["platform"] = "gbp"
        row["idempotency_key"] = f"qc-{asset}-gbp"
        self.assertEqual(fn(row), asset)

    def test_asset_id_from_queue_row_sb_and_mismatch(self):
        fn = self.unified_inbox.asset_id_from_queue_row
        self.assertIsNone(fn({"idempotency_key": "sb-stick-instagram-deadbeef", "platform": "instagram"}))
        self.assertIsNone(
            fn({"idempotency_key": "qc-draft-abc-instagram", "platform": "facebook"}),
        )

    def test_publish_request_meta_image_url(self):
        asset_id = "draft-abc123def456"
        campaign_id = "camp-test"
        image_url = "/brand-images/stick/gen-test.png"
        campaign_data = {
            "campaigns": {
                campaign_id: {
                    "assets": {
                        asset_id: {
                            "caption": "Hello shelf",
                            "image_url": image_url,
                        }
                    }
                }
            }
        }
        (self.tmpdir / "campaign-data.json").write_text(json.dumps(campaign_data), encoding="utf-8")
        row = {
            "idempotency_key": f"qc-{asset_id}-instagram",
            "platform": "instagram",
            "brand_id": "stick",
            "caption_preview": "Hello shelf",
            "human_approved": False,
            "channel": "postiz",
            "status": "pending",
            "created_at": "2026-09-23T10:00:00Z",
            "inbox_item_id": "calendar_candidate:stick:cal1",
        }
        queue_path = self.publish_sandbox._queue_path()
        queue_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

        now = datetime.now(timezone.utc)
        items = self.unified_inbox._publish_request_items(brand="stick", status="pending", now=now)  # noqa: SLF001
        self.assertEqual(len(items), 1)
        meta = items[0]["meta"]
        self.assertEqual(meta.get("asset_id"), asset_id)
        self.assertEqual(meta.get("campaign_id"), campaign_id)
        self.assertEqual(meta.get("image_url"), image_url)
        self.assertEqual(meta.get("inbox_item_id"), row["inbox_item_id"])

    def test_caption_draft_stays_bare(self):
        asset_id = "draft-captiononly01"
        campaign_id = "camp-cap"
        campaign_data = {
            "campaigns": {
                campaign_id: {
                    "assets": {
                        asset_id: {
                            "caption": "Words only",
                        }
                    }
                }
            }
        }
        (self.tmpdir / "campaign-data.json").write_text(json.dumps(campaign_data), encoding="utf-8")
        row = {
            "idempotency_key": f"qc-{asset_id}-instagram",
            "platform": "instagram",
            "brand_id": "stick",
            "status": "pending",
            "created_at": "2026-09-23T10:00:00Z",
        }
        self.publish_sandbox._queue_path().write_text(json.dumps(row) + "\n", encoding="utf-8")
        items = self.unified_inbox._publish_request_items(
            brand="stick",
            status="pending",
            now=datetime.now(timezone.utc),
        )
        meta = items[0]["meta"]
        self.assertIsNone(meta.get("image_url"))

    def test_list_items_type_filter_draft_only(self):
        proposals = self.tmpdir / "proposals"
        proposals.mkdir(parents=True, exist_ok=True)
        (proposals / "pending.jsonl").write_text(
            json.dumps(
                {
                    "id": "prop-1",
                    "brand_id": "stick",
                    "title": "Should not appear",
                    "status": "pending",
                    "created_at": "2026-09-23T09:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        payload = self.unified_inbox.list_items(status="pending", item_type="draft_asset", brand="stick")
        types = {i.get("type") for i in payload.get("items") or []}
        self.assertFalse(types & {"proposal", "calendar_candidate", "publish_request"})

    def test_sandbox_list_queue_enriches_image(self):
        self.publish_sandbox._queue_path().write_text("", encoding="utf-8")
        asset_id = "draft-listqueue01"
        image_url = "/brand-images/bag-drop/gen-list.png"
        (self.tmpdir / "campaign-data.json").write_text(
            json.dumps(
                {
                    "campaigns": {
                        "c1": {"assets": {asset_id: {"image_url": image_url, "caption": "Cap"}}},
                    }
                }
            ),
            encoding="utf-8",
        )
        self.publish_sandbox.enqueue_item(
            brand_id="bag-drop",
            platform="instagram",
            caption_preview="Cap",
            idempotency_key=f"qc-{asset_id}-instagram",
        )
        out = self.publish_sandbox.list_queue(brand="bag-drop")
        self.assertTrue(out.get("ok"))
        items = out.get("items") or []
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].get("image_url"), image_url)
        self.assertEqual(items[0].get("asset_id"), asset_id)


if __name__ == "__main__":
    unittest.main()
