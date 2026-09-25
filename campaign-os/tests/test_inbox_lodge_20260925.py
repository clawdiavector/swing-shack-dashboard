"""Post Flow P2 — lodge/book approve modes, PATCH edit, holiday candidates."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]


class InboxLodgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-inbox-lodge-"))
        cls._prev_data_dir = os.environ.get("DATA_DIR")
        cls._prev_enqueue = os.environ.get("CAMPAIGN_OS_L5_ENQUEUE")
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["CAMPAIGN_OS_L5_ENQUEUE"] = "1"
        sys.path.insert(0, str(CAMPAIGN_OS))
        cls.brand = "swing-shack"
        cls.cal_dir = cls.tmpdir / "intelligence" / "marketing-calendar"
        cls.cal_dir.mkdir(parents=True, exist_ok=True)
        cls.queue_path = cls.tmpdir / "agent-queue.json"

    def setUp(self):
        os.environ["DATA_DIR"] = str(self.tmpdir)
        os.environ["CAMPAIGN_OS_L5_ENQUEUE"] = "1"
        if self.queue_path.is_file():
            self.queue_path.unlink()
        cal_path = self.cal_dir / f"{self.brand}.jsonl"
        if cal_path.is_file():
            cal_path.unlink()
        for name in list(sys.modules):
            if name.startswith("_lib."):
                del sys.modules[name]

    @classmethod
    def tearDownClass(cls):
        if cls._prev_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = cls._prev_data_dir
        if cls._prev_enqueue is None:
            os.environ.pop("CAMPAIGN_OS_L5_ENQUEUE", None)
        else:
            os.environ["CAMPAIGN_OS_L5_ENQUEUE"] = cls._prev_enqueue

    def _write_moment(self, moment: dict) -> str:
        brand = moment.get("brand_id", self.brand)
        path = self.cal_dir / f"{brand}.jsonl"
        cal_id = moment.get("calendar_id") or "cal-test-1"
        moment.setdefault("calendar_id", cal_id)
        moment.setdefault("brand_id", brand)
        moment.setdefault("type", "moment")
        moment.setdefault("status", "candidate")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(moment) + "\n")
        return cal_id

    def _inbox_id(self, cal_id: str) -> str:
        return f"calendar_candidate:{self.brand}:{cal_id}"

    def _queue_actions(self) -> list[str]:
        if not self.queue_path.is_file():
            return []
        doc = json.loads(self.queue_path.read_text())
        rows = doc.get("rows") if isinstance(doc, dict) else doc
        if not isinstance(rows, list):
            return []
        return [str(r.get("action") or "") for r in rows if isinstance(r, dict)]

    def test_mode_book_no_enqueue(self):
        from _lib import unified_inbox

        cal_id = self._write_moment(
            {
                "calendar_id": "cal-book-1",
                "title": "Book only",
                "event_date": "2026-10-15",
                "primary_channel": "instagram",
            }
        )
        item_id = self._inbox_id(cal_id)
        result = unified_inbox.approve_item(item_id, mode="book")
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("mode"), "book")
        self.assertEqual(result.get("enqueued"), [])
        self.assertEqual(self._queue_actions(), [])

    def test_mode_lodge_enqueues(self):
        from _lib import unified_inbox

        cal_id = self._write_moment(
            {
                "calendar_id": "cal-lodge-1",
                "title": "Lodge",
                "event_date": "2026-10-16",
                "primary_channel": "instagram",
            }
        )
        item_id = self._inbox_id(cal_id)
        result = unified_inbox.approve_item(item_id, mode="lodge")
        self.assertTrue(result.get("ok"))
        actions = self._queue_actions()
        self.assertIn("draft_caption", actions)
        self.assertIn("draft_image", actions)

    def test_default_mode_is_lodge(self):
        from _lib import unified_inbox

        cal_id = self._write_moment(
            {
                "calendar_id": "cal-default-1",
                "event_date": "2026-10-17",
                "primary_channel": "instagram",
            }
        )
        unified_inbox.approve_item(self._inbox_id(cal_id))
        self.assertTrue(self._queue_actions())

    def test_lodge_no_date_400(self):
        from _lib import unified_inbox

        cal_id = self._write_moment({"calendar_id": "cal-nodate-1", "title": "Undated"})
        result = unified_inbox.approve_item(self._inbox_id(cal_id), mode="lodge")
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("code"), "no_date")

    def test_book_undated_ok(self):
        from _lib import unified_inbox

        cal_id = self._write_moment({"calendar_id": "cal-undated-book", "title": "Undated book"})
        result = unified_inbox.approve_item(self._inbox_id(cal_id), mode="book")
        self.assertTrue(result.get("ok"))

    def test_edit_event_date_persists(self):
        from _lib import unified_inbox
        from _lib.marketing_calendar import canonical_records

        cal_id = self._write_moment(
            {
                "calendar_id": "cal-edit-1",
                "event_date": "2027-03-26",
                "event_start": "2027-03-26",
                "primary_channel": "instagram",
            }
        )
        item_id = self._inbox_id(cal_id)
        future = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
        result = unified_inbox.edit_item(item_id, fields={"event_date": future})
        self.assertTrue(result.get("ok"))
        self.assertIn("event_date", result.get("changed") or [])
        record = next(r for r in canonical_records(self.brand) if r.get("calendar_id") == cal_id)
        self.assertEqual(record.get("event_date"), future)
        self.assertEqual(record.get("status"), "candidate")

    def test_holiday_not_stale_at_30_days(self):
        from _lib import unified_inbox
        from _lib.jobs.layer2 import holiday_inject

        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        cal_id = self._write_moment(
            {
                "calendar_id": "cal-hol-1",
                "title": "Heritage",
                "event_date": "2026-09-24",
                "source_type": "holiday",
                "created_by": "holiday_inject",
                "created_at": old,
            }
        )
        payload = unified_inbox.list_items(
            brand=self.brand, status="pending", item_type="calendar_candidate"
        )
        item = next(i for i in payload["items"] if i["id"].endswith(cal_id))
        flags = item.get("meta", {}).get("flags") or []
        self.assertIn("holiday", flags)
        self.assertNotIn("stale", flags)
        holiday_inject.run(today=datetime.now(timezone.utc).date())

    def test_enqueue_kill_switch(self):
        from _lib import unified_inbox

        os.environ["CAMPAIGN_OS_L5_ENQUEUE"] = "0"
        cal_id = self._write_moment(
            {
                "calendar_id": "cal-kill-1",
                "event_date": "2026-10-18",
                "primary_channel": "instagram",
            }
        )
        result = unified_inbox.approve_item(self._inbox_id(cal_id), mode="lodge")
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("enqueued"), [])
        self.assertEqual(result.get("enqueue_suppressed"), "CAMPAIGN_OS_L5_ENQUEUE=0")
