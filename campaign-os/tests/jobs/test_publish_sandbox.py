"""publish sandbox + publish_dispatch job tests."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _lib import publish_sandbox
from _lib.jobs import publish_dispatch as publish_dispatch_job


class PublishSandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        os.environ["DATA_DIR"] = str(self._root)
        os.environ["PUBLISH_MODE"] = "sandbox"
        publish_sandbox.ensure_sandbox_layout()

    def tearDown(self) -> None:
        self._tmp.cleanup()
        os.environ.pop("DATA_DIR", None)
        os.environ.pop("PUBLISH_MODE", None)

    def test_refuse_dispatch_without_human_approved(self) -> None:
        item = publish_sandbox.enqueue_item(
            brand_id="stick",
            caption_preview="test caption",
            human_approved=False,
        )
        receipt, err = publish_sandbox.dispatch_item(item)
        self.assertEqual(err, "human_approved required")
        self.assertEqual(receipt, {})

    def test_sandbox_dispatch_writes_receipt_no_http(self) -> None:
        item = publish_sandbox.enqueue_item(
            brand_id="stick",
            platform="instagram",
            caption_preview="Hello sandbox",
            human_approved=True,
        )
        with patch("urllib.request.urlopen") as mock_urlopen:
            result = publish_dispatch_job.run()
            mock_urlopen.assert_not_called()
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("mode"), "sandbox")
        self.assertEqual(result.get("dispatched"), 1)
        receipts = publish_sandbox._read_jsonl(publish_sandbox._receipts_path())
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].get("mode"), "sandbox")
        self.assertTrue(str(receipts[0].get("sandbox_post_id", "")).startswith("sb-post-"))

    def test_idempotent_dispatch(self) -> None:
        key = "sb-idem-test"
        publish_sandbox.enqueue_item(
            brand_id="stick",
            human_approved=True,
            idempotency_key=key,
        )
        publish_dispatch_job.run()
        publish_dispatch_job.run()
        receipts = publish_sandbox._read_jsonl(publish_sandbox._receipts_path())
        self.assertEqual(len(receipts), 1)

    def test_approve_then_dispatch(self) -> None:
        item = publish_sandbox.enqueue_item(brand_id="bag-drop", human_approved=False)
        approved, err = publish_sandbox.approve_item(item["idempotency_key"])
        self.assertIsNone(err)
        self.assertTrue(approved and approved.get("human_approved"))
        result = publish_dispatch_job.run()
        self.assertEqual(result.get("dispatched"), 1)

    def test_summary_counts(self) -> None:
        publish_sandbox.enqueue_item(brand_id="stick", human_approved=False)
        publish_sandbox.enqueue_item(brand_id="stick", human_approved=True)
        s = publish_sandbox.summary()
        self.assertEqual(s["queue_depth"], 2)
        self.assertEqual(s["queue_approved_ready"], 1)

    def test_enqueue_rejects_invalid_brand(self) -> None:
        with self.assertRaises(ValueError):
            publish_sandbox.enqueue_item(brand_id="takomo", human_approved=False)

    def test_enqueue_for_intended_channels_ig_and_facebook(self) -> None:
        brands = {
            "brands": {
                "stick": {"id": "stick", "publish_channels": ["instagram", "facebook"]},
            }
        }
        (self._root / "brands.json").write_text(json.dumps(brands), encoding="utf-8")
        asset_id = "asset-dual"
        composed = {
            "instagram": "/brand-images/stick/composed-x-instagram.png",
            "facebook": "/brand-images/stick/composed-x-facebook.png",
        }
        items = publish_sandbox.enqueue_for_intended_channels(
            brand_id="stick",
            caption_preview="Dual channel caption",
            inbox_item_id="calendar_candidate:stick:cal1",
            asset_id=asset_id,
            asset={"caption": "Dual channel caption", "composed": composed},
            sidecar={"composed": composed},
        )
        self.assertEqual(len(items), 2)
        platforms = {str(i.get("platform")) for i in items}
        self.assertEqual(platforms, {"instagram", "facebook"})
        queue = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
        self.assertEqual(len(queue), 2)
        fb_row = next(r for r in queue if r.get("platform") == "facebook")
        self.assertEqual(fb_row.get("image_url"), composed["facebook"])

    def test_sync_queue_rows_updates_caption_from_draft(self) -> None:
        brands = {
            "brands": {
                "stick": {"id": "stick", "publish_channels": ["instagram", "facebook"]},
            }
        }
        (self._root / "brands.json").write_text(json.dumps(brands), encoding="utf-8")
        asset_id = "draft-sync-cap"
        publish_sandbox.enqueue_item(
            brand_id="stick",
            platform="instagram",
            caption_preview="old queue caption",
            idempotency_key=f"qc-{asset_id}-instagram",
            human_approved=True,
        )
        (self._root / "campaign-data.json").write_text(
            json.dumps(
                {
                    "campaigns": {
                        "camp": {
                            "assets": {
                                asset_id: {
                                    "caption": "Approved draft caption exactly",
                                    "composed": {
                                        "instagram": "/brand-images/stick/x-ig.png",
                                    },
                                }
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        (self._root / "draft-assets").mkdir(exist_ok=True)
        (self._root / "draft-assets" / f"{asset_id}.json").write_text(
            json.dumps(
                {
                    "asset_id": asset_id,
                    "brand_id": "stick",
                    "composed": {"instagram": "/brand-images/stick/x-ig.png"},
                }
            ),
            encoding="utf-8",
        )
        out = publish_sandbox.sync_queue_rows_for_asset(
            brand_id="stick",
            asset_id=asset_id,
        )
        self.assertEqual(out.get("updated"), 1)
        rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
        self.assertEqual(rows[0].get("caption_preview"), "Approved draft caption exactly")

    def test_enqueue_idempotent_on_key(self) -> None:
        key = "qc-test-asset"
        first = publish_sandbox.enqueue_item(
            brand_id="stick",
            caption_preview="first",
            idempotency_key=key,
        )
        second = publish_sandbox.enqueue_item(
            brand_id="stick",
            caption_preview="second",
            idempotency_key=key,
        )
        queue = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
        self.assertEqual(len(queue), 1)
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])
        self.assertEqual(first["queue_id"], second["queue_id"])

    def test_live_dispatch_calls_postiz_when_configured(self) -> None:
        os.environ["PUBLISH_MODE"] = "live"
        asset_id = "draft-live-1"
        (self._root / "draft-assets").mkdir(exist_ok=True)
        (self._root / "draft-assets" / f"{asset_id}.json").write_text(
            json.dumps(
                {
                    "asset_id": asset_id,
                    "brand_id": "stick",
                    "composed": {"instagram": "/brand-images/stick/x.png"},
                }
            ),
            encoding="utf-8",
        )
        (self._root / "campaign-data.json").write_text(
            json.dumps(
                {
                    "campaigns": {
                        "camp": {
                            "assets": {
                                asset_id: {
                                    "caption": "Live caption",
                                    "composed": {"instagram": "/brand-images/stick/x.png"},
                                }
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        publish_sandbox.enqueue_item(
            brand_id="stick",
            platform="instagram",
            caption_preview="Live caption",
            human_approved=True,
            idempotency_key=f"qc-{asset_id}-instagram",
            image_url="/brand-images/stick/x.png",
        )
        fake_integrations = [{"id": "ig-1", "providerIdentifier": "instagram", "name": "Instagram"}]
        with patch("urllib.request.urlopen") as mock_urlopen:
            with patch("_lib.publish_live.postiz_status", return_value={"configured": True}):
                with patch("_lib.publish_live.list_integrations", return_value=(fake_integrations, None)):
                    with patch(
                        "_lib.publish_live.create_post",
                        return_value=({"id": "postiz-123"}, None),
                    ):
                        result = publish_dispatch_job.run()
            mock_urlopen.assert_not_called()
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("mode"), "live")
        self.assertEqual(result.get("dispatched"), 1)
        receipts = publish_sandbox._read_jsonl(publish_sandbox._receipts_path())
        self.assertEqual(receipts[0].get("postiz_post_id"), "postiz-123")

    def test_live_dispatch_skips_future_schedule(self) -> None:
        os.environ["PUBLISH_MODE"] = "live"
        publish_sandbox.enqueue_item(
            brand_id="stick",
            platform="instagram",
            caption_preview="Later caption",
            human_approved=True,
            idempotency_key="qc-future-instagram",
            image_url="/brand-images/stick/x.png",
            would_publish_at="2099-01-01T11:00:00Z",
        )
        with patch("_lib.publish_live.postiz_status", return_value={"configured": True}):
            with patch("_lib.publish_live.create_post") as create_post:
                result = publish_dispatch_job.run()
        create_post.assert_not_called()
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("dispatched"), 0)
        queue = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
        self.assertEqual(queue[0].get("status"), "pending")

    def test_dispatch_now_sends_future_row(self) -> None:
        os.environ["PUBLISH_MODE"] = "live"
        asset_id = "draft-now-1"
        (self._root / "draft-assets").mkdir(exist_ok=True)
        (self._root / "draft-assets" / f"{asset_id}.json").write_text(
            json.dumps(
                {
                    "asset_id": asset_id,
                    "brand_id": "stick",
                    "composed": {"instagram": "/brand-images/stick/x.png"},
                }
            ),
            encoding="utf-8",
        )
        (self._root / "campaign-data.json").write_text(
            json.dumps(
                {
                    "campaigns": {
                        "camp": {
                            "assets": {
                                asset_id: {
                                    "caption": "Now caption",
                                    "composed": {"instagram": "/brand-images/stick/x.png"},
                                }
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        key = f"qc-{asset_id}-instagram"
        publish_sandbox.enqueue_item(
            brand_id="stick",
            platform="instagram",
            caption_preview="Now caption",
            human_approved=True,
            idempotency_key=key,
            image_url="/brand-images/stick/x.png",
            would_publish_at="2099-01-01T11:00:00Z",
        )
        from _lib.publish_live import dispatch_now

        fake_integrations = [{"id": "ig-1", "identifier": "instagram", "name": "Instagram"}]
        with patch("_lib.publish_live.postiz_status", return_value={"configured": True}):
            with patch("_lib.publish_live.list_integrations", return_value=(fake_integrations, None)):
                with patch(
                    "_lib.publish_live.create_post",
                    return_value=({"id": "postiz-now"}, None),
                ) as create_post:
                    result = dispatch_now([key])
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("dispatched"), 1)
        _args, kwargs = create_post.call_args
        self.assertIsNone(kwargs.get("publish_date"))

    def test_integration_match_uses_identifier_not_first_channel(self) -> None:
        from _lib.publish_live import _integration_for_platform

        integrations = [
            {"id": "tt", "name": "stick Paarl", "identifier": "tiktok-business"},
            {"id": "ig", "name": "Stick", "identifier": "instagram"},
            {"id": "fb", "name": "Stick Paarl", "identifier": "facebook"},
        ]
        self.assertEqual(_integration_for_platform(integrations, "instagram"), "ig")
        self.assertEqual(_integration_for_platform(integrations, "facebook"), "fb")
        self.assertIsNone(_integration_for_platform(integrations, "linkedin"))


if __name__ == "__main__":
    unittest.main()
