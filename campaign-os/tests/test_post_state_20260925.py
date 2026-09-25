"""Post Flow P1 — post_state() and week_board window (2026-09-25)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]


class PostStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-post-state-"))
        cls._prev_data_dir = os.environ.get("DATA_DIR")
        cls._prev_sandbox_dir = os.environ.get("PUBLISH_SANDBOX_DIR")
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        sys.path.insert(0, str(CAMPAIGN_OS))
        from _lib import publish_sandbox

        publish_sandbox.ensure_sandbox_layout()
        cls.brand = "swing-shack"
        cls.cal_dir = cls.tmpdir / "intelligence" / "marketing-calendar"
        cls.cal_dir.mkdir(parents=True, exist_ok=True)

        import app as app_module

        cls.app_module = app_module
        cls.client = app_module.app.test_client()

    def setUp(self):
        os.environ["DATA_DIR"] = str(self.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(self.tmpdir / "publish-sandbox")
        self.app_module.DATA_DIR = str(self.tmpdir)
        cal_path = self.cal_dir / f"{self.brand}.jsonl"
        if cal_path.is_file():
            cal_path.unlink()
        for extra in ("campaign-data.json",):
            p = self.tmpdir / extra
            if p.is_file():
                p.unlink()
        sidecar_dir = self.tmpdir / "draft-assets"
        if sidecar_dir.is_dir():
            for p in sidecar_dir.glob("*.json"):
                p.unlink()
        sandbox = self.tmpdir / "publish-sandbox"
        for name in ("queue.jsonl", "receipts.jsonl"):
            p = sandbox / name
            if p.is_file():
                p.write_text("", encoding="utf-8")
        for name in list(sys.modules):
            if name in ("_lib.marketing_calendar", "_lib.unified_inbox", "_lib.publish_sandbox"):
                del sys.modules[name]

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

    def _write_moment(self, moment: dict) -> None:
        brand = moment.get("brand_id", self.brand)
        path = self.cal_dir / f"{brand}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(moment) + "\n")

    def test_posted_beats_released(self):
        from _lib import unified_inbox

        cal_id = "cal-posted-1"
        self._write_moment(
            {
                "calendar_id": cal_id,
                "brand_id": self.brand,
                "type": "moment",
                "status": "approved",
                "title": "Posted moment",
                "event_date": "2026-09-28",
                "primary_channel": "instagram",
            }
        )
        inbox_ref = f"calendar_candidate:{self.brand}:{cal_id}"
        from _lib import publish_sandbox

        publish_sandbox.enqueue_item(
            brand_id=self.brand,
            inbox_item_id=inbox_ref,
            human_approved=True,
            idempotency_key="qc-asset1-instagram",
        )
        rows = publish_sandbox.queue_rows_for_brand(self.brand)
        publish_sandbox.dispatch_item(rows[0])

        index = unified_inbox.build_post_index(brand_id=self.brand)
        record = next(
            r
            for r in __import__("_lib.marketing_calendar", fromlist=["canonical_records"]).canonical_records(
                self.brand
            )
            if r.get("calendar_id") == cal_id
        )
        out = unified_inbox.post_state(record, index=index)
        self.assertEqual(out["state"], "posted")
        self.assertTrue(out["stages"]["posted"])

    def test_stale_candidate_not_holiday(self):
        from _lib import unified_inbox

        cal_id = "cal-stale-candidate"
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        self._write_moment(
            {
                "calendar_id": cal_id,
                "brand_id": self.brand,
                "type": "moment",
                "status": "candidate",
                "title": "Old candidate",
                "event_date": "2026-09-28",
                "created_at": old,
            }
        )
        index = unified_inbox.build_post_index(brand_id=self.brand)
        record = next(
            r
            for r in __import__("_lib.marketing_calendar", fromlist=["canonical_records"]).canonical_records(
                self.brand
            )
            if r.get("calendar_id") == cal_id
        )
        out = unified_inbox.post_state(record, index=index)
        self.assertIn("stale", out["flags"])

    def test_holiday_candidate_not_stale(self):
        from _lib import unified_inbox

        cal_id = "cal-holiday-heritage"
        old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat().replace("+00:00", "Z")
        self._write_moment(
            {
                "calendar_id": cal_id,
                "brand_id": self.brand,
                "type": "moment",
                "status": "candidate",
                "title": "Heritage Day",
                "event_date": "2026-09-24",
                "created_by": "holiday_inject",
                "created_at": old,
            }
        )
        index = unified_inbox.build_post_index(brand_id=self.brand)
        record = next(
            r
            for r in __import__("_lib.marketing_calendar", fromlist=["canonical_records"]).canonical_records(
                self.brand
            )
            if r.get("calendar_id") == cal_id
        )
        out = unified_inbox.post_state(record, index=index)
        self.assertIn("holiday", out["flags"])
        self.assertNotIn("stale", out["flags"])

    def test_dispatched_queue_row_keeps_queued_stage(self):
        from _lib import publish_sandbox, unified_inbox

        cal_id = "cal-dispatch-regression"
        self._write_moment(
            {
                "calendar_id": cal_id,
                "brand_id": self.brand,
                "type": "moment",
                "status": "approved",
                "title": "Dispatch regression",
                "event_date": "2026-09-28",
                "primary_channel": "instagram",
            }
        )
        inbox_ref = f"calendar_candidate:{self.brand}:{cal_id}"
        row = publish_sandbox.enqueue_item(
            brand_id=self.brand,
            inbox_item_id=inbox_ref,
            human_approved=True,
            idempotency_key="qc-dispatch-reg-instagram",
        )
        publish_sandbox.dispatch_item(row)

        index = unified_inbox.build_post_index(brand_id=self.brand)
        record = next(
            r
            for r in __import__("_lib.marketing_calendar", fromlist=["canonical_records"]).canonical_records(
                self.brand
            )
            if r.get("calendar_id") == cal_id
        )
        out = unified_inbox.post_state(record, index=index)
        self.assertEqual(out["state"], "posted")
        self.assertTrue(out["stages"]["queued"])

    def test_operator_24_sep_needs_fix_no_image(self):
        """AC-7: operator post on past day — caption done, needs_fix no image."""
        from _lib import unified_inbox

        cal_id = "cal-operator-24sep"
        event_day = "2026-09-24"
        self._write_moment(
            {
                "calendar_id": cal_id,
                "brand_id": self.brand,
                "type": "moment",
                "status": "approved",
                "title": "Book your fitting",
                "event_date": event_day,
                "source_type": "operator",
                "primary_channel": "facebook",
            }
        )
        campaign_id = "cos-drafts-swing-shack"
        asset_id = "draft-operator24"
        (self.tmpdir / "campaign-data.json").write_text(
            json.dumps(
                {
                    "campaigns": {
                        campaign_id: {
                            "assets": {
                                asset_id: {
                                    "caption": "Caption without image",
                                    "approvalStatus": "draft",
                                    "platform": "facebook",
                                }
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        sidecar_dir = self.tmpdir / "draft-assets"
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        inbox_ref = f"calendar_candidate:{self.brand}:{cal_id}"
        (sidecar_dir / f"{asset_id}.json").write_text(
            json.dumps(
                {
                    "asset_id": asset_id,
                    "campaign_id": campaign_id,
                    "brand_id": self.brand,
                    "source_inbox_item_id": inbox_ref,
                }
            ),
            encoding="utf-8",
        )

        payload = unified_inbox.week_board(
            brand_id=self.brand,
            start=date.fromisoformat("2026-09-23"),
            days=7,
            past_days=3,
        )
        past_day = next(d for d in payload["days_list"] if d["date"] == event_day)
        self.assertTrue(past_day.get("is_past"))
        post = next(p for p in past_day["posts"] if p["calendar_id"] == cal_id)
        self.assertEqual(post["state"], "needs_fix")
        self.assertEqual(post.get("needs_fix_reason"), "no image")
        self.assertTrue(post["stages"]["caption"])
        self.assertFalse(post["stages"]["image"])

    def test_week_past_window_and_undated(self):
        from _lib import unified_inbox

        self._write_moment(
            {
                "calendar_id": "cal-undated",
                "brand_id": self.brand,
                "type": "moment",
                "status": "candidate",
                "title": "No date idea",
            }
        )
        payload = unified_inbox.week_board(
            brand_id=self.brand,
            start=date.fromisoformat("2026-09-25"),
            days=7,
            past_days=3,
        )
        self.assertEqual(len(payload["days_list"]), 10)
        past = [d for d in payload["days_list"] if d.get("is_past")]
        self.assertEqual(len(past), 3)
        self.assertGreaterEqual(payload.get("undated_total", 0), 1)


if __name__ == "__main__":
    unittest.main()
