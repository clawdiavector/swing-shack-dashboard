"""T5 — Postiz schedule on approve, sandbox release honesty, calendar labels (2026-10-26)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _lib import publish_sandbox
from _lib import postiz_on_approve


def _reload_calendar_modules() -> None:
    for name in list(sys.modules):
        if name in (
            "_lib.marketing_calendar",
            "_lib.unified_inbox",
            "_lib.publish_sandbox",
        ):
            del sys.modules[name]


class PostizScheduleOnApproveTests(unittest.TestCase):
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
        publish_sandbox.ensure_sandbox_layout()

    def tearDown(self) -> None:
        self._tmp.cleanup()
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _row(self, *, key: str = "qc-asset1-instagram", when: str | None = "2026-10-28T07:00:00Z") -> dict:
        publish_sandbox.enqueue_item(
            brand_id="stick",
            platform="instagram",
            caption_preview="Caption for Postiz.",
            human_approved=False,
            would_publish_at=when,
            idempotency_key=key,
            image_url="/brand-images/stick/x.png",
            event_date="2026-10-28",
        )
        rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
        return next(r for r in rows if r["idempotency_key"] == key)

    def test_flag_off_approve_does_not_call_postiz(self) -> None:
        os.environ.pop("CAMPAIGN_OS_POSTIZ_ON_APPROVE", None)
        row = self._row()
        with mock.patch("urllib.request.urlopen") as mock_urlopen, mock.patch.object(
            postiz_on_approve,
            "create_post",
        ) as mock_create:
            approved, err = publish_sandbox.approve_item(row["idempotency_key"])
            self.assertIsNone(err)
            self.assertTrue(approved and approved.get("human_approved"))
            mock_urlopen.assert_not_called()
            mock_create.assert_not_called()
        self.assertEqual(len(publish_sandbox._read_jsonl(publish_sandbox._receipts_path())), 0)

    def test_flag_on_schedules_and_writes_receipt(self) -> None:
        os.environ["CAMPAIGN_OS_POSTIZ_ON_APPROVE"] = "1"
        row = self._row()
        integrations = [{"id": "int-ig", "identifier": "instagram", "name": "Stick"}]
        with mock.patch.object(
            publish_sandbox,
            "preflight_queue_row",
            return_value=(True, ""),
        ), mock.patch.object(
            postiz_on_approve.publish_live,
            "_integrations_for_brand",
            return_value=(integrations, None),
        ), mock.patch.object(
            postiz_on_approve.publish_live,
            "_media_for_row",
            return_value=[],
        ), mock.patch.object(
            postiz_on_approve,
            "create_post",
            return_value=({"id": "postiz-sched-1"}, None),
        ) as mock_create:
            approved, err = publish_sandbox.approve_item(row["idempotency_key"])
            self.assertIsNone(err, err)
            self.assertTrue(approved)
            mock_create.assert_called_once()
            _args, kwargs = mock_create.call_args
            self.assertIn("publish_date", kwargs)
        receipts = publish_sandbox._read_jsonl(publish_sandbox._receipts_path())
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].get("postiz_post_id"), "postiz-sched-1")
        self.assertEqual(receipts[0].get("would_publish_at"), "2026-10-28T07:00:00Z")

    def test_flag_on_missing_schedule_refuses(self) -> None:
        os.environ["CAMPAIGN_OS_POSTIZ_ON_APPROVE"] = "1"
        row = self._row(key="qc-no-date", when=None)
        rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
        for r in rows:
            if r["idempotency_key"] == "qc-no-date":
                r.pop("event_date", None)
        publish_sandbox._rewrite_jsonl(publish_sandbox._queue_path(), rows)
        approved, err = publish_sandbox.approve_item("qc-no-date")
        self.assertIsNone(approved)
        self.assertIn("would_publish_at", str(err))

    def test_flag_on_skips_when_live_receipt_exists(self) -> None:
        os.environ["CAMPAIGN_OS_POSTIZ_ON_APPROVE"] = "1"
        row = self._row(key="qc-idem")
        publish_sandbox._append_jsonl(
            publish_sandbox._receipts_path(),
            {
                "schema": publish_sandbox.RECEIPT_SCHEMA,
                "mode": "live",
                "idempotency_key": "qc-idem",
                "postiz_post_id": "existing-99",
                "brand_id": "stick",
            },
        )
        with mock.patch.object(postiz_on_approve, "create_post") as mock_create:
            approved, err = publish_sandbox.approve_item("qc-idem")
            self.assertIsNone(err)
            self.assertTrue(approved)
            mock_create.assert_not_called()

    def test_unapprove_deletes_postiz_and_receipt(self) -> None:
        os.environ["CAMPAIGN_OS_POSTIZ_ON_APPROVE"] = "1"
        row = self._row(key="qc-unapprove")
        publish_sandbox._append_jsonl(
            publish_sandbox._receipts_path(),
            {
                "schema": publish_sandbox.RECEIPT_SCHEMA,
                "mode": "live",
                "idempotency_key": "qc-unapprove",
                "postiz_post_id": "postiz-del-1",
                "brand_id": "stick",
                "postiz_scheduled_at": "2099-06-01T12:00:00Z",
            },
        )
        rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
        for r in rows:
            if r["idempotency_key"] == "qc-unapprove":
                r["human_approved"] = True
        publish_sandbox._rewrite_jsonl(publish_sandbox._queue_path(), rows)
        with mock.patch.object(postiz_on_approve, "delete_post", return_value=({}, None)) as mock_del:
            item, err = publish_sandbox.unapprove_item("qc-unapprove")
            self.assertIsNone(err)
            self.assertFalse(item and item.get("human_approved"))
            mock_del.assert_called_once_with("postiz-del-1", brand_id="stick")
        self.assertEqual(publish_sandbox._read_jsonl(publish_sandbox._receipts_path()), [])


class SandboxReleaseDoesNotBurnTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        os.environ["DATA_DIR"] = str(self._root)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(self._root / "publish-sandbox")
        os.environ["PUBLISH_MODE"] = "sandbox"
        publish_sandbox.ensure_sandbox_layout()
        self.brand = "swing-shack"
        self.cal_dir = self._root / "intelligence" / "marketing-calendar"
        self.cal_dir.mkdir(parents=True, exist_ok=True)
        _reload_calendar_modules()
        self._seed_scheduled("cal-no-burn")

    def tearDown(self) -> None:
        self._tmp.cleanup()
        os.environ.pop("DATA_DIR", None)
        os.environ.pop("PUBLISH_SANDBOX_DIR", None)
        os.environ.pop("PUBLISH_MODE", None)

    def _seed_scheduled(self, cal_id: str) -> None:
        path = self.cal_dir / f"{self.brand}.jsonl"
        path.write_text(
            json.dumps(
                {
                    "calendar_id": cal_id,
                    "brand_id": self.brand,
                    "type": "moment",
                    "status": "approved",
                    "title": "Burn test",
                    "event_date": "2026-10-28",
                    "primary_channel": "instagram",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        asset_id = f"asset-{cal_id}"
        campaign_id = f"cos-drafts-{self.brand}"
        (self._root / "campaign-data.json").write_text(
            json.dumps(
                {
                    "campaigns": {
                        campaign_id: {
                            "assets": {
                                asset_id: {
                                    "caption": "Caption",
                                    "approvalStatus": "approved",
                                    "channels": ["instagram"],
                                    "composed": {"instagram": "/x.png"},
                                    "image_url": "/x.png",
                                }
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        inbox_ref = f"calendar_candidate:{self.brand}:{cal_id}"
        side = self._root / "draft-assets" / f"{asset_id}.json"
        side.parent.mkdir(parents=True, exist_ok=True)
        side.write_text(
            json.dumps(
                {
                    "asset_id": asset_id,
                    "draft_bucket": "approved",
                    "source_inbox_item_id": inbox_ref,
                    "caption": "Caption",
                    "image_url": "/x.png",
                }
            ),
            encoding="utf-8",
        )
        from _lib import publish_sandbox as ps

        ps.enqueue_item(
            brand_id=self.brand,
            inbox_item_id=inbox_ref,
            human_approved=False,
            idempotency_key=f"qc-{asset_id}-instagram",
            caption_preview="Caption",
            image_url="/x.png",
        )

    def test_release_without_dispatch_writes_no_receipt(self) -> None:
        from _lib import publish_sandbox as ps

        result = ps.release_moment(
            brand_id=self.brand,
            calendar_id="cal-no-burn",
            dispatch=False,
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(ps._read_jsonl(ps._receipts_path()), [])
        with_dispatch = ps.release_moment(
            brand_id=self.brand,
            calendar_id="cal-no-burn",
            dispatch=True,
        )
        self.assertTrue(with_dispatch.get("ok"))
        self.assertEqual(len(ps._read_jsonl(ps._receipts_path())), 1)


class CalendarSandboxHonestyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        os.environ["DATA_DIR"] = str(self._root)
        os.environ["PUBLISH_MODE"] = "sandbox"
        publish_sandbox.ensure_sandbox_layout()
        self.brand = "stick"
        self.cal_id = "cal-sandbox-honesty"
        cal_dir = self._root / "intelligence" / "marketing-calendar"
        cal_dir.mkdir(parents=True, exist_ok=True)
        (cal_dir / f"{self.brand}.jsonl").write_text(
            json.dumps(
                {
                    "calendar_id": self.cal_id,
                    "type": "moment",
                    "status": "approved",
                    "event_date": "2026-10-28",
                    "title": "Sandbox honesty",
                    "primary_channel": "instagram",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        side = self._root / "draft-assets" / "asset-sb.json"
        side.parent.mkdir(parents=True, exist_ok=True)
        side.write_text(
            json.dumps(
                {
                    "asset_id": "asset-sb",
                    "draft_bucket": "approved",
                    "caption": "Hello",
                    "image_url": "/x.png",
                    "source_inbox_item_id": f"calendar_candidate:{self.brand}:{self.cal_id}",
                }
            ),
            encoding="utf-8",
        )
        data = {
            "campaigns": {
                "camp-stick": {
                    "assets": {
                        "asset-sb": {
                            "caption": "Hello",
                            "channels": ["instagram"],
                            "composed": {"instagram": "/x.png"},
                            "image_url": "/x.png",
                        }
                    }
                }
            }
        }
        (self._root / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")
        _reload_calendar_modules()
        from _lib import publish_sandbox as ps

        ps.enqueue_for_intended_channels(
            brand_id=self.brand,
            caption_preview="Hello",
            inbox_item_id=f"calendar_candidate:{self.brand}:{self.cal_id}",
            asset_id="asset-sb",
        )
        rows = ps._read_jsonl(ps._queue_path())
        key = rows[0]["idempotency_key"]
        ps.approve_item(key)
        ps.dispatch_item({**rows[0], "human_approved": True})

    def tearDown(self) -> None:
        self._tmp.cleanup()
        os.environ.pop("DATA_DIR", None)
        os.environ.pop("PUBLISH_MODE", None)

    def test_post_state_sandbox_receipt_not_posted(self) -> None:
        from _lib import unified_inbox

        st = unified_inbox.post_state_for(self.brand, self.cal_id)
        self.assertIsNotNone(st)
        assert st is not None
        self.assertNotEqual(st.get("state"), "posted")
        self.assertEqual(st.get("next_action"), "Sandbox only (not sent)")
        self.assertEqual(st.get("delivery_summary", {}).get("posted"), 0)

    def test_week_board_shows_sandbox_only_label(self) -> None:
        from _lib import unified_inbox

        board = unified_inbox.week_board(
            brand_id=self.brand,
            start=__import__("datetime").date.fromisoformat("2026-10-28"),
            days=1,
        )
        posts = board["days_list"][0]["posts"]
        match = next(p for p in posts if p.get("calendar_id") == self.cal_id)
        self.assertEqual(match.get("next_action"), "Sandbox only (not sent)")
        self.assertNotEqual(match.get("state"), "posted")


if __name__ == "__main__":
    unittest.main()
