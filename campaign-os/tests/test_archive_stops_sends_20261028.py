"""Archiving a draft takes it out of the send queue and Postiz; published drafts stay (2026-10-28).

T16 closeout gaps A-D: archive never touched the send queue or Postiz, a published draft
could be archived, and Library bulk archive skipped the audit row and purge date.
"""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BRAND = "stick"
CAMP = "camp-arch"


def _fresh():
    poa = importlib.reload(importlib.import_module("_lib.postiz_on_approve"))
    ps = importlib.reload(importlib.import_module("_lib.publish_sandbox"))
    importlib.reload(importlib.import_module("_lib.unified_inbox"))
    ca = importlib.reload(importlib.import_module("_lib.content_archive"))
    ls = importlib.reload(importlib.import_module("_lib.library_shelf"))
    return poa, ps, ca, ls


class ArchiveStopsSendsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old = {k: os.environ.get(k) for k in (
            "DATA_DIR", "PUBLISH_MODE", "CAMPAIGN_OS_POSTIZ_ON_APPROVE", "POSTIZ_API_KEY_STICK")}
        os.environ["DATA_DIR"] = str(self.root)
        os.environ["PUBLISH_MODE"] = "live"
        os.environ["CAMPAIGN_OS_POSTIZ_ON_APPROVE"] = "1"
        os.environ["POSTIZ_API_KEY_STICK"] = "test-key-stick-only"
        (self.root / "draft-assets").mkdir(parents=True, exist_ok=True)
        _fresh()[1].ensure_sandbox_layout()

    def tearDown(self) -> None:
        self._tmp.cleanup()
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _draft(self, aid: str, status: str = "approved") -> None:
        (self.root / "draft-assets" / f"{aid}.json").write_text(json.dumps({
            "asset_id": aid, "brand_id": BRAND, "campaign_id": CAMP,
            "created_at": "2026-10-27T10:00:00Z"}), encoding="utf-8")
        path = self.root / "campaign-data.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"campaigns": {}}
        data["campaigns"].setdefault(CAMP, {"assets": {}})["assets"][aid] = {
            "caption": f"Post {aid}", "approvalStatus": status, "updatedAt": "2026-10-27T10:00:00Z"}
        path.write_text(json.dumps(data), encoding="utf-8")

    def _queue(self, aid: str, *, status: str | None = None) -> str:
        _, ps, _, _ = _fresh()
        key = f"qc-{aid}-instagram"
        ps.enqueue_item(brand_id=BRAND, platform="instagram", caption_preview="Caption.",
                        human_approved=True, would_publish_at="2099-06-01T07:00:00Z",
                        idempotency_key=key, image_url=f"/brand-images/{BRAND}/x.png")
        if status:
            rows = ps._read_jsonl(ps._queue_path())
            for r in rows:
                if r["idempotency_key"] == key:
                    r["status"] = status
            ps._rewrite_jsonl(ps._queue_path(), rows)
        return key

    def _receipt(self, key: str, scheduled_at: str) -> None:
        _, ps, _, _ = _fresh()
        ps._append_jsonl(ps._receipts_path(), {
            "schema": ps.RECEIPT_SCHEMA, "mode": "live", "brand_id": BRAND, "platform": "instagram",
            "idempotency_key": key, "postiz_post_id": "postiz-1",
            "dispatched_at": "2026-10-27T08:00:00Z", "postiz_scheduled_at": scheduled_at})

    def _row(self, ps, key):
        return next(r for r in ps._read_jsonl(ps._queue_path()) if r["idempotency_key"] == key)

    def _asset(self, aid):
        data = json.loads((self.root / "campaign-data.json").read_text(encoding="utf-8"))
        return data["campaigns"][CAMP]["assets"][aid]

    def test_archive_takes_approved_draft_out_of_queue(self) -> None:
        self._draft("a1")
        key = self._queue("a1")
        _, ps, ca, _ = _fresh()
        preview = ca.preview_archive(BRAND, kind="draft", item_id="a1")
        self.assertIn("stops it going out", preview["message"])
        ca.archive_item(BRAND, kind="draft", item_id="a1", actor="test")
        row = self._row(ps, key)
        self.assertEqual(row["status"], "skipped")
        self.assertFalse(row["human_approved"])
        self.assertEqual(self._asset("a1")["approvalStatus"], "archived")

    def test_archive_deletes_future_postiz_schedule(self) -> None:
        self._draft("a2")
        key = self._queue("a2", status="dispatched")
        self._receipt(key, "2099-06-01T07:00:00Z")
        poa, ps, ca, _ = _fresh()
        with mock.patch.object(poa, "delete_post", return_value=({}, None)) as mock_del:
            ca.archive_item(BRAND, kind="draft", item_id="a2", actor="test")
            mock_del.assert_called_once_with("postiz-1", brand_id=BRAND)
        self.assertEqual(ps._read_jsonl(ps._receipts_path()), [])
        self.assertEqual(self._row(ps, key)["status"], "skipped")

    def test_archive_refused_when_already_sent_to_postiz(self) -> None:
        self._draft("a3")
        key = self._queue("a3", status="dispatched")
        self._receipt(key, "2020-01-01T07:00:00Z")
        poa, ps, ca, _ = _fresh()
        with mock.patch.object(poa, "delete_post") as mock_del:
            with self.assertRaises(ValueError):
                ca.archive_item(BRAND, kind="draft", item_id="a3", actor="test")
            mock_del.assert_not_called()
        self.assertEqual(self._asset("a3")["approvalStatus"], "approved")
        self.assertEqual(self._row(ps, key)["status"], "dispatched")

    def test_archive_refused_when_postiz_delete_fails(self) -> None:
        self._draft("a4")
        key = self._queue("a4", status="dispatched")
        self._receipt(key, "2099-06-01T07:00:00Z")
        poa, ps, ca, _ = _fresh()
        with mock.patch.object(poa, "delete_post", return_value=({}, ("http_500", "boom"))):
            with self.assertRaises(ValueError):
                ca.archive_item(BRAND, kind="draft", item_id="a4", actor="test")
        self.assertEqual(self._asset("a4")["approvalStatus"], "approved")
        self.assertEqual(len(ps._read_jsonl(ps._receipts_path())), 1)

    def test_published_draft_cannot_be_archived(self) -> None:
        self._draft("a5", status="published")
        _, _, ca, _ = _fresh()
        with self.assertRaises(ValueError):
            ca.archive_item(BRAND, kind="draft", item_id="a5", actor="test")
        self.assertEqual(self._asset("a5")["approvalStatus"], "published")

    def test_bulk_archive_writes_purge_date_and_stops_queue(self) -> None:
        self._draft("a6")
        key = self._queue("a6")
        self._draft("a7", status="published")
        _, ps, _, ls = _fresh()
        out = ls.apply_library_bulk(BRAND, lane="drafts", action="archive", ids=["a6", "a7"], actor="kyle")
        self.assertEqual(out["applied_count"], 1)
        self.assertEqual([s["id"] for s in out["skipped"]], ["a7"])
        asset = self._asset("a6")
        self.assertEqual(asset["approvalStatus"], "archived")
        self.assertEqual(asset["archived_by"], "kyle")
        self.assertTrue(asset.get("purge_at"))
        self.assertEqual(self._row(ps, key)["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
