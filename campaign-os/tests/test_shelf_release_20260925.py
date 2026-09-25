"""Post Flow P3 — shelf_board, release_moment, auto_release (2026-09-25)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CAMPAIGN_OS = Path(__file__).resolve().parents[1]


class ShelfReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-shelf-release-"))
        cls._prev_data_dir = os.environ.get("DATA_DIR")
        cls._prev_sandbox_dir = os.environ.get("PUBLISH_SANDBOX_DIR")
        cls._prev_auto = os.environ.get("CAMPAIGN_OS_AUTO_RELEASE")
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        sys.path.insert(0, str(CAMPAIGN_OS))
        from _lib import publish_sandbox

        publish_sandbox.ensure_sandbox_layout()
        cls.brand = "swing-shack"
        cls.cal_dir = cls.tmpdir / "intelligence" / "marketing-calendar"
        cls.cal_dir.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        os.environ["DATA_DIR"] = str(self.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(self.tmpdir / "publish-sandbox")
        os.environ.pop("CAMPAIGN_OS_AUTO_RELEASE", None)
        cal_path = self.cal_dir / f"{self.brand}.jsonl"
        if cal_path.is_file():
            cal_path.unlink()
        for extra in ("campaign-data.json", "brands.json"):
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
            if name in (
                "_lib.marketing_calendar",
                "_lib.unified_inbox",
                "_lib.publish_sandbox",
                "_lib.jobs.auto_release",
            ):
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
        if cls._prev_auto is None:
            os.environ.pop("CAMPAIGN_OS_AUTO_RELEASE", None)
        else:
            os.environ["CAMPAIGN_OS_AUTO_RELEASE"] = cls._prev_auto

    def _write_moment(self, moment: dict) -> None:
        brand = moment.get("brand_id", self.brand)
        path = self.cal_dir / f"{brand}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(moment) + "\n")

    def _seed_scheduled(
        self,
        cal_id: str,
        *,
        event_date: str = "2026-09-28",
        brand: str | None = None,
        with_queue: bool = True,
    ) -> str:
        brand = brand or self.brand
        self._write_moment(
            {
                "calendar_id": cal_id,
                "brand_id": brand,
                "type": "moment",
                "status": "approved",
                "title": f"Scheduled {cal_id}",
                "event_date": event_date,
                "primary_channel": "instagram",
            }
        )
        campaign_id = f"cos-drafts-{brand}"
        asset_id = f"asset-{cal_id}"
        campaign_path = self.tmpdir / "campaign-data.json"
        doc: dict = {"campaigns": {}}
        if campaign_path.is_file():
            try:
                loaded = json.loads(campaign_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    doc = loaded
            except json.JSONDecodeError:
                pass
        campaigns = doc.setdefault("campaigns", {})
        campaign = campaigns.setdefault(campaign_id, {})
        assets = campaign.setdefault("assets", {})
        assets[asset_id] = {
            "caption": "Caption",
            "approvalStatus": "approved",
            "platform": "instagram",
        }
        campaign_path.write_text(json.dumps(doc), encoding="utf-8")
        sidecar_dir = self.tmpdir / "draft-assets"
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        inbox_ref = f"calendar_candidate:{brand}:{cal_id}"
        (sidecar_dir / f"{asset_id}.json").write_text(
            json.dumps(
                {
                    "asset_id": asset_id,
                    "campaign_id": campaign_id,
                    "brand_id": brand,
                    "source_inbox_item_id": inbox_ref,
                }
            ),
            encoding="utf-8",
        )
        if with_queue:
            from _lib import publish_sandbox

            publish_sandbox.enqueue_item(
                brand_id=brand,
                inbox_item_id=inbox_ref,
                human_approved=False,
                idempotency_key=f"qc-{asset_id}-instagram",
            )
        return inbox_ref

    def test_would_publish_at_strips_offset(self):
        from _lib.publish_sandbox import _would_publish_at_from_event_date

        out = _would_publish_at_from_event_date("2026-10-01T00:00:00+02:00")
        self.assertEqual(out, "2026-10-01T09:00:00Z")
        datetime.fromisoformat(out.replace("Z", "+00:00"))

    def test_calendar_event_date_slices_to_day(self):
        from _lib.jobs.layer5.image_draft_context import calendar_event_date_for_item

        cal_id = "cal-date-slice"
        self._write_moment(
            {
                "calendar_id": cal_id,
                "brand_id": self.brand,
                "type": "moment",
                "status": "approved",
                "event_start": "2026-10-01T00:00:00+02:00",
            }
        )
        ref = f"calendar_candidate:{self.brand}:{cal_id}"
        self.assertEqual(calendar_event_date_for_item(self.brand, ref), "2026-10-01")

    def test_shelf_board_lists_scheduled_not_posted(self):
        from _lib import unified_inbox

        cal_sched = "cal-shelf-sched"
        cal_posted = "cal-shelf-posted"
        self._seed_scheduled(cal_sched)
        self._seed_scheduled(cal_posted)
        from _lib import publish_sandbox

        rows = publish_sandbox.queue_rows_for_brand(self.brand)
        posted_row = next(r for r in rows if "cal-shelf-posted" in str(r.get("idempotency_key")))
        publish_sandbox.approve_item(str(posted_row["idempotency_key"]))
        publish_sandbox.dispatch_item({**posted_row, "human_approved": True})

        board = unified_inbox.shelf_board(brand_id=self.brand)
        ids = [
            p["calendar_id"]
            for group in board["date_groups"]
            for p in group["posts"]
        ] + [p["calendar_id"] for p in board["undated"]]
        self.assertIn(cal_sched, ids)
        self.assertNotIn(cal_posted, ids)

    def test_release_moment_scheduled_to_posted_sandbox(self):
        from _lib import publish_sandbox

        cal_id = "cal-release-1"
        self._seed_scheduled(cal_id)
        result = publish_sandbox.release_moment(
            brand_id=self.brand,
            calendar_id=cal_id,
            dispatch=True,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "posted")
        again = publish_sandbox.release_moment(
            brand_id=self.brand,
            calendar_id=cal_id,
            dispatch=True,
        )
        self.assertFalse(again["ok"])
        self.assertEqual(again["code"], "already_released")

    def test_release_not_scheduled_refused(self):
        from _lib import publish_sandbox

        cal_id = "cal-not-sched"
        self._write_moment(
            {
                "calendar_id": cal_id,
                "brand_id": self.brand,
                "type": "moment",
                "status": "approved",
                "event_date": "2026-09-28",
            }
        )
        result = publish_sandbox.release_moment(
            brand_id=self.brand,
            calendar_id=cal_id,
            dispatch=False,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "not_scheduled")

    def test_release_no_channel_bag_drop(self):
        from _lib import publish_sandbox

        cal_id = "cal-bag-drop"
        self._seed_scheduled(cal_id, brand="bag-drop", with_queue=False)
        result = publish_sandbox.release_moment(
            brand_id="bag-drop",
            calendar_id=cal_id,
            dispatch=False,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "no_channel")

    def test_auto_release_gated_by_default(self):
        from _lib.jobs import auto_release

        cal_id = "cal-auto-today"
        today = datetime.now(ZoneInfo("Africa/Johannesburg")).date().isoformat()
        self._seed_scheduled(cal_id, event_date=today)
        out = auto_release.run(brand=self.brand)
        self.assertTrue(out["ok"])
        self.assertTrue(out.get("gated"))
        self.assertEqual(out.get("released"), 0)
        self.assertGreaterEqual(out.get("rows", 0), 1)

    def test_auto_release_enabled_today_only(self):
        from _lib.jobs import auto_release
        from _lib import publish_sandbox

        os.environ["CAMPAIGN_OS_AUTO_RELEASE"] = "1"
        today = datetime.now(ZoneInfo("Africa/Johannesburg")).date().isoformat()
        tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
        cal_today = "cal-auto-on-today"
        cal_future = "cal-auto-on-future"
        self._seed_scheduled(cal_today, event_date=today)
        self._seed_scheduled(cal_future, event_date=tomorrow)
        out = auto_release.run(brand=self.brand)
        self.assertTrue(out["ok"])
        self.assertFalse(out.get("gated"))
        self.assertEqual(out.get("released"), 1)
        rows = publish_sandbox.queue_rows_for_brand(self.brand)
        today_row = next(r for r in rows if cal_today in str(r.get("inbox_item_id")))
        future_row = next(r for r in rows if cal_future in str(r.get("inbox_item_id")))
        self.assertTrue(today_row.get("human_approved"))
        self.assertFalse(future_row.get("human_approved"))

    def test_auto_release_hour_gate(self):
        from _lib.jobs import auto_release

        os.environ["CAMPAIGN_OS_AUTO_RELEASE"] = "1"
        os.environ["CAMPAIGN_OS_AUTO_RELEASE_HOUR"] = "23"
        today = datetime.now(ZoneInfo("Africa/Johannesburg")).date().isoformat()
        cal_id = "cal-hour-gate"
        self._seed_scheduled(cal_id, event_date=today)
        noon_sast = datetime.now(timezone.utc).astimezone(ZoneInfo("Africa/Johannesburg")).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        out = auto_release.run(brand=self.brand, now=noon_sast)
        self.assertEqual(out.get("released"), 0)


if __name__ == "__main__":
    unittest.main()
