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


if __name__ == "__main__":
    unittest.main()
