"""Day desk — render_mode, moment PATCH, week_board day load (2026-10-02)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]


class RenderModeDayDeskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-render-mode-"))
        cls._prev_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["COS_JOB_TOKEN"] = "test-job-token-not-a-secret"
        sys.path.insert(0, str(CAMPAIGN_OS))
        cls.brand = "swing-shack"
        cls.cal_dir = cls.tmpdir / "intelligence" / "marketing-calendar"
        cls.cal_dir.mkdir(parents=True, exist_ok=True)
        cls.queue_path = cls.tmpdir / "agent-queue.json"
        import app as app_module

        cls.app_module = app_module
        cls.client = app_module.app.test_client()

    def setUp(self):
        os.environ["DATA_DIR"] = str(self.tmpdir)
        self.app_module.DATA_DIR = str(self.tmpdir)
        if self.queue_path.is_file():
            self.queue_path.unlink()
        cal_path = self.cal_dir / f"{self.brand}.jsonl"
        if cal_path.is_file():
            cal_path.unlink()
        edits = self.tmpdir / "human-edits.jsonl"
        if edits.is_file():
            edits.unlink()
        for name in list(sys.modules):
            if name.startswith("_lib."):
                del sys.modules[name]

    @classmethod
    def tearDownClass(cls):
        if cls._prev_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = cls._prev_data_dir

    def _write_moment(self, moment: dict) -> str:
        cal_id = moment.get("calendar_id") or "cal-test-1"
        moment.setdefault("calendar_id", cal_id)
        moment.setdefault("brand_id", self.brand)
        moment.setdefault("type", "moment")
        moment.setdefault("revision", 1)
        path = self.cal_dir / f"{self.brand}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(moment) + "\n")
        return cal_id

    def _queue_row_count(self) -> int:
        if not self.queue_path.is_file():
            return 0
        doc = json.loads(self.queue_path.read_text(encoding="utf-8"))
        rows = doc.get("rows") if isinstance(doc, dict) else doc
        return len(rows) if isinstance(rows, list) else 0

    def test_t1_render_mode_for_record_defaults(self):
        from _lib.marketing_calendar import render_mode_for_record

        self.assertEqual(render_mode_for_record({}), "template")
        self.assertEqual(render_mode_for_record({"render_mode": ""}), "template")
        self.assertEqual(render_mode_for_record({"render_mode": "nonsense"}), "template")
        self.assertEqual(render_mode_for_record({"render_mode": "oneshot"}), "oneshot")
        self.assertEqual(render_mode_for_record({"render_mode": "ONESHOT"}), "oneshot")

    def test_t2_set_fields_accepts_render_mode(self):
        from _lib.marketing_calendar import canonical_records, set_fields

        cal_id = self._write_moment(
            {
                "calendar_id": "cal-mode-1",
                "status": "candidate",
                "title": "T",
                "event_date": "2026-10-05",
            },
        )
        updated = set_fields(self.brand, cal_id, {"render_mode": "oneshot"}, reason="test")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.get("render_mode"), "oneshot")
        canon = {r.get("calendar_id"): r for r in canonical_records(self.brand)}
        self.assertEqual(canon[cal_id].get("render_mode"), "oneshot")

    def test_t3_set_fields_rejects_bad_mode(self):
        from _lib.marketing_calendar import set_fields

        cal_id = self._write_moment(
            {
                "calendar_id": "cal-mode-bad",
                "status": "candidate",
                "title": "T",
                "event_date": "2026-10-05",
            },
        )
        path = self.cal_dir / f"{self.brand}.jsonl"
        before_lines = path.read_text(encoding="utf-8").count("\n")
        with self.assertRaises(ValueError):
            set_fields(self.brand, cal_id, {"render_mode": "magic"}, reason="test")
        after_lines = path.read_text(encoding="utf-8").count("\n")
        self.assertEqual(before_lines, after_lines)

    def test_t4_set_fields_post_type_normalized(self):
        from _lib.marketing_calendar import set_fields

        cal_id = self._write_moment(
            {
                "calendar_id": "cal-pt-1",
                "status": "candidate",
                "title": "T",
                "event_date": "2026-10-05",
            },
        )
        updated = set_fields(self.brand, cal_id, {"post_type": "  TIP  "}, reason="test")
        self.assertEqual(updated.get("post_type"), "tip")

    def test_t5_week_board_row_carries_mode(self):
        from _lib.unified_inbox import week_board

        cal_id = self._write_moment(
            {
                "calendar_id": "cal-wb-1",
                "status": "approved",
                "title": "Booked row",
                "event_date": "2026-10-08",
                "event_start": "2026-10-08",
            },
        )
        board = week_board(
            brand_id=self.brand,
            start=date.fromisoformat("2026-10-08"),
            days=1,
            past_days=0,
            include_undated=False,
        )
        posts = board["days_list"][0]["posts"]
        row = next(p for p in posts if p.get("calendar_id") == cal_id)
        self.assertEqual(row.get("render_mode"), "template")

        from _lib.marketing_calendar import set_fields

        set_fields(self.brand, cal_id, {"render_mode": "oneshot"}, reason="test")
        board2 = week_board(
            brand_id=self.brand,
            start=date.fromisoformat("2026-10-08"),
            days=1,
            past_days=0,
            include_undated=False,
        )
        posts2 = board2["days_list"][0]["posts"]
        row2 = next(p for p in posts2 if p.get("calendar_id") == cal_id)
        self.assertEqual(row2.get("render_mode"), "oneshot")

    def test_t6_day_load_shape(self):
        from _lib.unified_inbox import week_board

        d = date.fromisoformat("2026-10-09")
        board = week_board(
            brand_id=self.brand,
            start=d,
            days=1,
            past_days=0,
            include_undated=False,
        )
        self.assertEqual(len(board["days_list"]), 1)
        self.assertEqual(board["days_list"][0]["date"], "2026-10-09")
        self.assertEqual(board.get("undated"), [])

    def test_t7_edit_item_mode_swap_candidate(self):
        from _lib import unified_inbox

        cal_id = self._write_moment(
            {
                "calendar_id": "cal-edit-1",
                "status": "candidate",
                "title": "Cand",
                "event_date": "2026-10-10",
                "event_start": "2026-10-10",
                "primary_channel": "facebook",
            },
        )
        item_id = f"calendar_candidate:{self.brand}:{cal_id}"
        result = unified_inbox.edit_item(
            item_id,
            editor="test",
            fields={"render_mode": "oneshot"},
        )
        self.assertTrue(result.get("ok"))
        self.assertIn("render_mode", result.get("changed") or [])
        edits_path = self.tmpdir / "human-edits.jsonl"
        lines = edits_path.read_text(encoding="utf-8").strip().split("\n")
        last = json.loads(lines[-1])
        self.assertEqual(last.get("previous", {}).get("render_mode"), "template")

    def test_t8_booked_moment_route(self):
        cal_id = self._write_moment(
            {
                "calendar_id": "cal-booked-1",
                "status": "approved",
                "title": "Lodged",
                "event_date": "2026-10-11",
                "event_start": "2026-10-11",
            },
        )
        inbox_id = f"calendar_candidate:{self.brand}:{cal_id}"
        miss = self.client.patch(
            f"/api/inbox/unified/{inbox_id}/edit",
            json={"editor": "test", "render_mode": "oneshot"},
        )
        self.assertEqual(miss.status_code, 404)

        ok = self.client.patch(
            f"/api/calendar/moment/{self.brand}/{cal_id}/fields",
            json={"editor": "test", "render_mode": "oneshot"},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.get_json().get("record", {}).get("render_mode"), "oneshot")

    def test_t9_moment_route_errors(self):
        anon = self.app_module.app.test_client(cos_anon=True)
        resp = anon.patch(
            "/api/calendar/moment/swing-shack/nope/fields",
            json={"editor": "test", "title": "x"},
        )
        self.assertEqual(resp.status_code, 401)

        cal_id = self._write_moment(
            {
                "calendar_id": "cal-x",
                "status": "approved",
                "title": "For bad mode",
                "event_date": "2026-10-14",
            },
        )
        bad = self.client.patch(
            f"/api/calendar/moment/swing-shack/{cal_id}/fields",
            json={"editor": "test", "render_mode": "bad"},
        )
        self.assertEqual(bad.status_code, 400)

        missing = self.client.patch(
            "/api/calendar/moment/swing-shack/cal-missing-404/fields",
            json={"editor": "test", "title": "x"},
        )
        self.assertEqual(missing.status_code, 404)

    def test_t10_no_enqueue_on_field_patch(self):
        cal_id = self._write_moment(
            {
                "calendar_id": "cal-no-enq",
                "status": "approved",
                "title": "No enqueue",
                "event_date": "2026-10-12",
                "angle": "a",
            },
        )
        before_q = self._queue_row_count()
        sidecar_dir = self.tmpdir / "draft-assets"
        before_sidecars = len(list(sidecar_dir.glob("*.json"))) if sidecar_dir.is_dir() else 0

        resp = self.client.patch(
            f"/api/calendar/moment/{self.brand}/{cal_id}/fields",
            json={
                "editor": "test",
                "render_mode": "oneshot",
                "post_type": "tip",
                "title": "Updated",
                "angle": "b",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._queue_row_count(), before_q)
        after_sidecars = len(list(sidecar_dir.glob("*.json"))) if sidecar_dir.is_dir() else 0
        self.assertEqual(after_sidecars, before_sidecars)

    def test_t11_calendar_items_meta_default_mode(self):
        from _lib import unified_inbox

        self._write_moment(
            {
                "calendar_id": "cal-meta-1",
                "status": "candidate",
                "title": "Meta",
                "event_date": "2026-10-13",
            },
        )
        payload = unified_inbox.list_items(status="all", brand=self.brand)
        items = payload.get("items") or []
        cand = next(i for i in items if i.get("meta", {}).get("calendar_id") == "cal-meta-1")
        self.assertEqual(cand["meta"].get("render_mode"), "template")


if __name__ == "__main__":
    unittest.main()
