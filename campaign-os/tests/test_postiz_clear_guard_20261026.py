"""Guard clear_postiz_on_unapprove — only future schedule-on-approve receipts (2026-10-26)."""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _fresh_modules():
    poa = importlib.reload(importlib.import_module("_lib.postiz_on_approve"))
    ps = importlib.reload(importlib.import_module("_lib.publish_sandbox"))
    ui = importlib.reload(importlib.import_module("_lib.unified_inbox"))
    mod = sys.modules.get(__name__)
    if mod is not None:
        mod.postiz_on_approve = poa
        mod.publish_sandbox = ps
        mod.unified_inbox = ui
    return poa, ps, ui


class PostizClearGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self._old_env = {
            k: os.environ.get(k)
            for k in (
                "DATA_DIR",
                "PUBLISH_MODE",
                "CAMPAIGN_OS_POSTIZ_ON_APPROVE",
                "POSTIZ_API_KEY_STICK",
            )
        }
        os.environ["DATA_DIR"] = str(self._root)
        os.environ["PUBLISH_MODE"] = "live"
        os.environ["POSTIZ_API_KEY_STICK"] = "test-key-stick-only"
        _fresh_modules()[1].ensure_sandbox_layout()

    def tearDown(self) -> None:
        self._tmp.cleanup()
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _enqueue(self, key: str) -> None:
        _, ps, _ = _fresh_modules()
        ps.enqueue_item(
            brand_id="stick",
            platform="instagram",
            caption_preview="Caption.",
            human_approved=True,
            would_publish_at="2026-10-28T07:00:00Z",
            idempotency_key=key,
            image_url="/brand-images/stick/x.png",
        )

    def _write_live_receipt(
        self,
        key: str,
        *,
        postiz_post_id: str = "postiz-live-1",
        postiz_scheduled_at: str | None = None,
    ) -> None:
        _, ps, _ = _fresh_modules()
        rec = {
            "schema": ps.RECEIPT_SCHEMA,
            "mode": "live",
            "brand_id": "stick",
            "platform": "instagram",
            "idempotency_key": key,
            "postiz_post_id": postiz_post_id,
            "dispatched_at": "2026-10-26T08:00:00Z",
        }
        if postiz_scheduled_at is not None:
            rec["postiz_scheduled_at"] = postiz_scheduled_at
        ps._append_jsonl(ps._receipts_path(), rec)

    def test_flag_off_normal_receipt_reject_keeps_receipt(self) -> None:
        os.environ.pop("CAMPAIGN_OS_POSTIZ_ON_APPROVE", None)
        poa, ps, ui = _fresh_modules()
        key = "qc-dispatch-only-instagram"
        self._enqueue(key)
        self._write_live_receipt(key)
        item_id = f"publish_request:{key}"
        with mock.patch.object(poa, "delete_post") as mock_del:
            result = ui.reject_item(item_id, editor="test", reason="no")
            self.assertTrue(result.get("ok"), result)
            mock_del.assert_not_called()
        self.assertEqual(len(ps._read_jsonl(ps._receipts_path())), 1)
        row = next(r for r in ps._read_jsonl(ps._queue_path()) if r["idempotency_key"] == key)
        self.assertEqual(row.get("status"), "rejected")

    def test_flag_on_past_scheduled_reject_refuses(self) -> None:
        os.environ["CAMPAIGN_OS_POSTIZ_ON_APPROVE"] = "1"
        poa, ps, ui = _fresh_modules()
        key = "qc-past-sched-instagram"
        self._enqueue(key)
        self._write_live_receipt(key, postiz_scheduled_at="2020-01-01T12:00:00Z")
        item_id = f"publish_request:{key}"
        with mock.patch.object(poa, "delete_post") as mock_del:
            result = ui.reject_item(item_id, editor="test", reason="no")
            self.assertFalse(result.get("ok"))
            self.assertIn("already sent to Postiz", str(result.get("error")))
            mock_del.assert_not_called()
        self.assertEqual(len(ps._read_jsonl(ps._receipts_path())), 1)
        row = next(r for r in ps._read_jsonl(ps._queue_path()) if r["idempotency_key"] == key)
        self.assertNotEqual(row.get("status"), "rejected")

    def test_unapprove_future_schedule_deletes_postiz(self) -> None:
        os.environ["CAMPAIGN_OS_POSTIZ_ON_APPROVE"] = "1"
        poa, ps, _ui = _fresh_modules()
        key = "qc-unapprove-future"
        self._enqueue(key)
        self._write_live_receipt(key, postiz_scheduled_at="2099-06-01T12:00:00Z")
        with mock.patch.object(poa, "delete_post", return_value=({}, None)) as mock_del:
            item, err = ps.unapprove_item(key)
            self.assertIsNone(err)
            self.assertFalse(item and item.get("human_approved"))
            mock_del.assert_called_once_with("postiz-live-1", brand_id="stick")
        self.assertEqual(ps._read_jsonl(ps._receipts_path()), [])

    def test_flag_on_future_scheduled_reject_deletes(self) -> None:
        os.environ["CAMPAIGN_OS_POSTIZ_ON_APPROVE"] = "1"
        poa, ps, ui = _fresh_modules()
        key = "qc-future-sched-instagram"
        self._enqueue(key)
        self._write_live_receipt(key, postiz_scheduled_at="2099-06-01T12:00:00Z")
        item_id = f"publish_request:{key}"
        with mock.patch.object(poa, "delete_post", return_value=({}, None)) as mock_del:
            result = ui.reject_item(item_id, editor="test", reason="no")
            self.assertTrue(result.get("ok"), result)
            mock_del.assert_called_once_with("postiz-live-1", brand_id="stick")
        self.assertEqual(ps._read_jsonl(ps._receipts_path()), [])


if __name__ == "__main__":
    unittest.main()
