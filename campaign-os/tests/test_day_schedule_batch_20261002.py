"""Day desk schedule-day batch — candidates only, one oneshot per brand (2026-10-02)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
MEME_KB = REPO_ROOT / "data" / "meme_knowledge.json"


class DayScheduleBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-day-schedule-"))
        cls._prev_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["COS_JOB_TOKEN"] = "test-job-token-not-a-secret"
        sys.path.insert(0, str(CAMPAIGN_OS))
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
        for brand in ("swing-shack", "stick"):
            p = self.cal_dir / f"{brand}.jsonl"
            if p.is_file():
                p.unlink()
        for name in list(sys.modules):
            if name.startswith("_lib."):
                del sys.modules[name]

    @classmethod
    def tearDownClass(cls):
        if cls._prev_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = cls._prev_data_dir

    def _write_moment(self, brand: str, moment: dict) -> str:
        cal_id = moment.get("calendar_id") or "cal-test-1"
        moment.setdefault("calendar_id", cal_id)
        moment.setdefault("brand_id", brand)
        moment.setdefault("type", "moment")
        moment.setdefault("revision", 1)
        path = self.cal_dir / f"{brand}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(moment) + "\n")
        return cal_id

    def _jsonl_lines(self, brand: str) -> int:
        path = self.cal_dir / f"{brand}.jsonl"
        if not path.is_file():
            return 0
        return path.read_text(encoding="utf-8").count("\n")

    def _queue_row_count(self) -> int:
        if not self.queue_path.is_file():
            return 0
        doc = json.loads(self.queue_path.read_text(encoding="utf-8"))
        rows = doc.get("rows") if isinstance(doc, dict) else doc
        return len(rows) if isinstance(rows, list) else 0

    def test_t1_allowlist_integrity(self):
        from _lib.marketing_calendar import (
            ALWAYS_TEMPLATE_POST_TYPES,
            ONESHOT_ALLOWED_POST_TYPES,
            oneshot_blocked,
            oneshot_eligible,
        )

        self.assertFalse(ONESHOT_ALLOWED_POST_TYPES & ALWAYS_TEMPLATE_POST_TYPES)
        for pt in ONESHOT_ALLOWED_POST_TYPES:
            self.assertTrue(oneshot_eligible(pt))
        for pt in ("", "tip"):
            self.assertFalse(oneshot_eligible(pt))
        for pt in ALWAYS_TEMPLATE_POST_TYPES:
            self.assertFalse(oneshot_eligible(pt))
        for pt in ALWAYS_TEMPLATE_POST_TYPES:
            self.assertTrue(oneshot_blocked(pt))
        for pt in ("", "tip"):
            self.assertFalse(oneshot_blocked(pt))
        for pt in ONESHOT_ALLOWED_POST_TYPES:
            self.assertFalse(oneshot_blocked(pt))

    def test_t2_day_is_empty(self):
        from _lib.day_schedule import day_is_empty

        day = "2026-10-06"
        self.assertTrue(day_is_empty(brand_id="stick", day_iso=day))
        self._write_moment(
            "stick",
            {
                "calendar_id": "cal-on-day",
                "status": "candidate",
                "title": "On day",
                "event_date": day,
                "event_start": day,
                "event_end": day,
            },
        )
        self.assertFalse(day_is_empty(brand_id="stick", day_iso=day))
        self.assertTrue(day_is_empty(brand_id="stick", day_iso="2026-10-05"))

    def test_t3_plan_swing_shack(self):
        from _lib.day_schedule import plan_day_batch

        rows = plan_day_batch(brand_id="swing-shack", day_iso="2026-10-06")
        self.assertEqual(len(rows), 4)
        oneshots = [r for r in rows if r.get("render_mode") == "oneshot"]
        self.assertEqual(len(oneshots), 1)
        self.assertEqual(oneshots[0].get("post_type"), "fitting_headline")
        dailies = [r for r in rows if r.get("render_mode") == "template" and r.get("post_type") == ""]
        self.assertEqual(len(dailies), 2)
        for r in rows:
            self.assertEqual(r.get("status"), "candidate")

    def test_t4_plan_stick_rotation(self):
        from _lib.day_schedule import plan_day_batch

        day_a = "2026-10-07"
        day_b = "2026-10-08"
        batch = "deterministic-batch-id"
        plan_a = plan_day_batch(brand_id="stick", day_iso=day_a, batch_id=batch)
        plan_b = plan_day_batch(brand_id="stick", day_iso=day_a, batch_id=batch)
        self.assertEqual(plan_a, plan_b)
        self.assertEqual(len(plan_a), 4)
        self.assertEqual(sum(1 for r in plan_a if r.get("render_mode") == "oneshot"), 1)
        oneshot_a = next(r for r in plan_a if r.get("render_mode") == "oneshot")
        oneshot_c = next(
            r for r in plan_day_batch(brand_id="stick", day_iso=day_b, batch_id=batch)
            if r.get("render_mode") == "oneshot"
        )
        self.assertNotEqual(oneshot_a.get("post_type"), oneshot_c.get("post_type"))

    def test_t5_humour_card(self):
        from _lib.day_schedule import plan_day_batch
        from _lib.meme_lord import apply_meme

        rows = plan_day_batch(
            brand_id="stick",
            day_iso="2026-10-06",
            oneshot_override="humour_card",
        )
        humour = next(r for r in rows if r.get("post_type") == "humour_card")
        self.assertEqual(humour.get("process"), "humour")
        self.assertEqual(humour.get("origin", {}).get("kind"), "meme_lord")
        meme = humour.get("meme") or {}
        self.assertTrue(meme.get("id"))
        kb = json.loads(MEME_KB.read_text(encoding="utf-8"))
        ids = {m["id"] for m in kb.get("memes") or []}
        self.assertIn(meme.get("id"), ids)
        self.assertIn(meme.get("flavour"), {"sarcastic", "wholesome", "hard-truth"})
        applied = apply_meme(
            meme_id=meme["id"],
            voice=meme.get("voice", "stick"),
            pillar=meme.get("pillar", "community"),
            platform="instagram",
            pick_seed_index=0,
        )
        expected = next(
            c["text"] for c in applied["captions"] if c["flavour"] == meme["flavour"]
        )
        self.assertTrue(humour.get("angle"))
        self.assertEqual(humour.get("angle"), expected)
        self.assertEqual(meme.get("caption"), expected)

    def test_t6_schedule_day_writes(self):
        from _lib.day_schedule import schedule_day
        from _lib.unified_inbox import week_board

        day = "2026-10-08"
        result = schedule_day(brand_id="stick", day_iso=day)
        self.assertTrue(result.get("ok"))
        batch_id = result.get("batch_id")
        from datetime import date as date_cls

        board = week_board(brand_id="stick", start=date_cls.fromisoformat(day), days=1)
        posts = (board.get("days_list") or [{}])[0].get("posts") or []
        self.assertEqual(len(posts), 4)
        for p in posts:
            self.assertEqual(p.get("state"), "candidate")
        from _lib.marketing_calendar import canonical_records

        persisted = [r for r in canonical_records("stick") if r.get("schedule_batch_id") == batch_id]
        self.assertEqual(len(persisted), 4)
        for r in persisted:
            self.assertEqual(r.get("source_type"), "operator")
            self.assertEqual(r.get("created_by"), "operator")

    def test_t7_nothing_generates(self):
        from _lib.day_schedule import schedule_day

        before_q = self._queue_row_count()
        sidecar_dir = self.tmpdir / "draft-assets"
        before_sidecars = len(list(sidecar_dir.glob("*.json"))) if sidecar_dir.is_dir() else 0
        with mock.patch(
            "_lib.intelligence.generate_image",
            side_effect=AssertionError("generate_image must not run"),
        ):
            schedule_day(brand_id="swing-shack", day_iso="2026-10-09")
        self.assertEqual(self._queue_row_count(), before_q)
        after_sidecars = len(list(sidecar_dir.glob("*.json"))) if sidecar_dir.is_dir() else 0
        self.assertEqual(after_sidecars, before_sidecars)

    def test_t8_route(self):
        day = "2026-10-10"
        ok = self.client.post(
            "/api/calendar/schedule-day",
            json={"brand_id": "stick", "date": day},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.get_json().get("ok"))
        dup = self.client.post(
            "/api/calendar/schedule-day",
            json={"brand_id": "stick", "date": day},
        )
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(dup.get_json().get("code"), "day_not_empty")
        forced = self.client.post(
            "/api/calendar/schedule-day",
            json={"brand_id": "stick", "date": day, "force": True},
        )
        self.assertEqual(forced.status_code, 200)
        anon = self.app_module.app.test_client(cos_anon=True)
        self.assertEqual(
            anon.post("/api/calendar/schedule-day", json={"brand_id": "stick", "date": "2026-10-11"}).status_code,
            401,
        )
        bad_date = self.client.post(
            "/api/calendar/schedule-day",
            json={"brand_id": "stick", "date": "not-a-date"},
        )
        self.assertEqual(bad_date.status_code, 400)

    def test_t9_patch_guard(self):
        from _lib.marketing_calendar import set_fields

        cal_id = self._write_moment(
            "swing-shack",
            {
                "calendar_id": "cal-price",
                "status": "candidate",
                "title": "Price",
                "event_date": "2026-10-15",
                "post_type": "price_list",
            },
        )
        before = self._jsonl_lines("swing-shack")
        with self.assertRaises(ValueError):
            set_fields(
                "swing-shack",
                cal_id,
                {"post_type": "price_list", "render_mode": "oneshot"},
                reason="test",
            )
        self.assertEqual(self._jsonl_lines("swing-shack"), before)

        cal_blank = self._write_moment(
            "swing-shack",
            {
                "calendar_id": "cal-blank-pt",
                "status": "candidate",
                "title": "Blank pt",
                "event_date": "2026-10-16",
            },
        )
        updated = set_fields("swing-shack", cal_blank, {"render_mode": "oneshot"}, reason="test")
        self.assertEqual(updated.get("render_mode"), "oneshot")

        cal_tip = self._write_moment(
            "swing-shack",
            {
                "calendar_id": "cal-tip",
                "status": "candidate",
                "title": "Tip",
                "event_date": "2026-10-17",
            },
        )
        updated_tip = set_fields(
            "swing-shack",
            cal_tip,
            {"render_mode": "oneshot", "post_type": "tip"},
            reason="test",
        )
        self.assertEqual(updated_tip.get("render_mode"), "oneshot")
        self.assertEqual(updated_tip.get("post_type"), "tip")


if __name__ == "__main__":
    unittest.main()
