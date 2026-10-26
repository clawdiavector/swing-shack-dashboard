"""PR #217 review — reject clears Postiz, delete failure keeps receipt (2026-10-26)."""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _fresh_modules():
    """Re-bind after L7 learn's _lib.* purge (no conftest hook required)."""
    poa = importlib.reload(importlib.import_module("_lib.postiz_on_approve"))
    ps = importlib.reload(importlib.import_module("_lib.publish_sandbox"))
    ui = importlib.reload(importlib.import_module("_lib.unified_inbox"))
    mod = sys.modules.get(__name__)
    if mod is not None:
        mod.postiz_on_approve = poa
        mod.publish_sandbox = ps
        mod.unified_inbox = ui
    return poa, ps, ui


class PostizRejectAndDeleteFailureTests(unittest.TestCase):
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
        os.environ["CAMPAIGN_OS_POSTIZ_ON_APPROVE"] = "1"
        _fresh_modules()[1].ensure_sandbox_layout()

    def tearDown(self) -> None:
        self._tmp.cleanup()
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _approve_with_mocks(self, key: str) -> None:
        poa, ps, _ui = _fresh_modules()
        integrations = [{"id": "int-ig", "identifier": "instagram", "name": "Stick"}]
        with mock.patch.object(ps, "preflight_queue_row", return_value=(True, "")), mock.patch.object(
            poa.publish_live,
            "_integrations_for_brand",
            return_value=(integrations, None),
        ), mock.patch.object(
            poa.publish_live,
            "_media_for_row",
            return_value=[],
        ), mock.patch.object(
            poa,
            "create_post",
            return_value=({"id": "postiz-sched-1"}, None),
        ):
            approved, err = ps.approve_item(key)
            self.assertIsNone(err, err)
            self.assertTrue(approved and approved.get("human_approved"))

    def test_reject_publish_request_calls_delete_post(self) -> None:
        poa, ps, ui = _fresh_modules()
        key = "qc-reject-me-instagram"
        ps.enqueue_item(
            brand_id="stick",
            platform="instagram",
            caption_preview="Caption.",
            human_approved=False,
            would_publish_at="2026-10-28T07:00:00Z",
            idempotency_key=key,
            image_url="/brand-images/stick/x.png",
            event_date="2026-10-28",
        )
        self._approve_with_mocks(key)
        item_id = f"publish_request:{key}"
        with mock.patch.object(poa, "delete_post", return_value=({}, None)) as mock_del:
            result = ui.reject_item(item_id, editor="test", reason="not now")
            self.assertTrue(result.get("ok"), result)
            mock_del.assert_called_once_with("postiz-sched-1", brand_id="stick")
        rows = ps._read_jsonl(ps._queue_path())
        row = next(r for r in rows if r["idempotency_key"] == key)
        self.assertEqual(row.get("status"), "rejected")
        self.assertFalse(row.get("human_approved"))
        self.assertEqual(ps._read_jsonl(ps._receipts_path()), [])

    def test_delete_failure_keeps_receipt(self) -> None:
        poa, ps, _ui = _fresh_modules()
        key = "qc-del-fail"
        ps.enqueue_item(
            brand_id="stick",
            platform="instagram",
            caption_preview="Caption.",
            human_approved=False,
            would_publish_at="2026-10-28T07:00:00Z",
            idempotency_key=key,
            image_url="/brand-images/stick/x.png",
        )
        self._approve_with_mocks(key)
        self.assertEqual(len(ps._read_jsonl(ps._receipts_path())), 1)
        with mock.patch.object(poa, "delete_post", return_value=(None, ("502", "upstream"))):
            _out, err = poa.clear_postiz_on_unapprove(key)
            self.assertIsNotNone(err)
            self.assertIn("delete_post", str(err))
        self.assertEqual(len(ps._read_jsonl(ps._receipts_path())), 1)

    def test_approve_schedule_failure_leaves_row_unapproved(self) -> None:
        poa, ps, _ui = _fresh_modules()
        key = "qc-sched-fail"
        ps.enqueue_item(
            brand_id="stick",
            platform="instagram",
            caption_preview="Caption.",
            human_approved=False,
            would_publish_at="2026-10-28T07:00:00Z",
            idempotency_key=key,
            image_url="/brand-images/stick/x.png",
        )
        integrations = [{"id": "int-ig", "identifier": "instagram", "name": "Stick"}]
        with mock.patch.object(ps, "preflight_queue_row", return_value=(True, "")), mock.patch.object(
            poa.publish_live,
            "_integrations_for_brand",
            return_value=(integrations, None),
        ), mock.patch.object(
            poa.publish_live,
            "_media_for_row",
            return_value=[],
        ), mock.patch.object(
            poa,
            "create_post",
            return_value=(None, ("401", "nope")),
        ):
            approved, err = ps.approve_item(key)
            self.assertIsNone(approved)
            self.assertIn("create_post", str(err))
        rows = ps._read_jsonl(ps._queue_path())
        row = next(r for r in rows if r["idempotency_key"] == key)
        self.assertFalse(row.get("human_approved"))
        self.assertEqual(ps._read_jsonl(ps._receipts_path()), [])


if __name__ == "__main__":
    unittest.main()
