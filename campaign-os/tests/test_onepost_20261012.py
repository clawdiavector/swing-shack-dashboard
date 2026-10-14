"""One post, N deliveries — cos-onepost slice (2026-10-12)."""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
TOKEN = "test-job-token-not-a-secret"
BRAND = "swing-shack"


def _image() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), (20, 90, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def _day(offset: int = 2) -> str:
    return (datetime.now(ZoneInfo("Africa/Johannesburg")).date() + timedelta(days=offset)).isoformat()


class OnepostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-onepost-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_SANDBOX_DIR", "COS_JOB_TOKEN")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        os.environ["COS_JOB_TOKEN"] = TOKEN
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as app_module

        cls.app_module = app_module

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        os.environ["DATA_DIR"] = str(self.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(self.tmpdir / "publish-sandbox")
        self.app_module.DATA_DIR = str(self.tmpdir)
        self.app_module.COS_JOB_TOKEN = TOKEN
        for child in self.tmpdir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        (self.tmpdir / "campaign-data.json").write_text(json.dumps({"campaigns": {}}))
        for name in list(sys.modules):
            if name.startswith("_lib.") and name != "_lib":
                del sys.modules[name]
        from _lib import publish_sandbox

        publish_sandbox.ensure_sandbox_layout()
        self.client = self.app_module.app.test_client(cos_anon=True)
        self.auth = {"Authorization": f"Bearer {TOKEN}", "X-Actor-Display-Name": "test"}

    def _lodge(self, **overrides):
        body = {
            "brand": BRAND,
            "slug": "onepost-test",
            "date": _day(),
            "caption": "One post test caption",
            "image_base64": base64.b64encode(_image()).decode(),
            "created_by": "test",
        }
        body.update(overrides)
        return self.client.post("/api/posts/lodge", json=body, headers=self.auth)

    def test_lodge_single_channel_one_row(self):
        r = self._lodge(channels=["instagram"])
        self.assertEqual(r.status_code, 200, r.get_json())
        doc = r.get_json()
        self.assertEqual(doc["publish_queue_rows"], 1)
        from _lib import publish_sandbox

        rows = publish_sandbox.queue_rows_for_brand(BRAND)
        keys = [str(x.get("idempotency_key")) for x in rows]
        self.assertEqual(len(keys), 1)
        self.assertTrue(keys[0].endswith("-instagram"))
        self.assertFalse(any(k.endswith("-facebook") for k in keys))

    def test_lodge_default_channels(self):
        r = self._lodge()
        self.assertEqual(r.status_code, 200, r.get_json())
        doc = r.get_json()
        self.assertEqual(doc["publish_queue_rows"], 2)
        from _lib import unified_inbox, publish_sandbox

        cal_id = doc["calendar_id"]
        st = unified_inbox.post_state_for(BRAND, cal_id)
        self.assertEqual(st.get("channels_picked"), ["instagram", "facebook"])
        _cid, asset = unified_inbox._campaign_asset_for_id(
            unified_inbox._load_campaign_data(), doc["asset_id"]
        )
        self.assertEqual(asset.get("channels"), ["instagram", "facebook"])

    def test_set_channels_skip_and_revive(self):
        r = self._lodge()
        doc = r.get_json()
        cal_id = doc["calendar_id"]
        ch = self.client.post(
            "/api/posts/channels",
            json={"brand_id": BRAND, "calendar_id": cal_id, "channels": ["instagram"]},
            headers=self.auth,
        )
        self.assertEqual(ch.status_code, 200, ch.get_json())
        from _lib import publish_sandbox

        rows = publish_sandbox.queue_rows_for_brand(BRAND)
        fb = next(r for r in rows if str(r.get("platform")) == "facebook")
        self.assertEqual(fb.get("status"), "skipped")
        ch2 = self.client.post(
            "/api/posts/channels",
            json={
                "brand_id": BRAND,
                "calendar_id": cal_id,
                "channels": ["instagram", "facebook"],
            },
            headers=self.auth,
        )
        self.assertEqual(ch2.status_code, 200, ch2.get_json())
        rows = publish_sandbox.queue_rows_for_brand(BRAND)
        fb = next(r for r in rows if str(r.get("platform")) == "facebook")
        self.assertEqual(fb.get("status"), "pending")

    def test_release_picked_only(self):
        r = self._lodge()
        doc = r.get_json()
        cal_id = doc["calendar_id"]
        from _lib import publish_sandbox

        publish_sandbox.set_post_channels(
            brand_id=BRAND, calendar_id=cal_id, channels=["instagram"]
        )
        rel = publish_sandbox.release_moment(
            brand_id=BRAND, calendar_id=cal_id, dispatch=False
        )
        self.assertTrue(rel["ok"])
        rows = publish_sandbox.queue_rows_for_brand(BRAND)
        ig = next(x for x in rows if x.get("platform") == "instagram")
        self.assertTrue(ig.get("human_approved"))
        fb = next(x for x in rows if x.get("platform") == "facebook")
        self.assertEqual(fb.get("status"), "skipped")
        self.assertFalse(fb.get("human_approved"))
        pending = publish_sandbox.dispatch_pending()
        self.assertEqual(pending.get("dispatched"), 0)

    def test_locks_after_release(self):
        r = self._lodge(channels=["instagram"])
        doc = r.get_json()
        cal_id = doc["calendar_id"]
        from _lib import publish_sandbox

        publish_sandbox.release_moment(brand_id=BRAND, calendar_id=cal_id, dispatch=False)
        locked = self.client.post(
            "/api/posts/channels",
            json={"brand_id": BRAND, "calendar_id": cal_id, "channels": ["facebook"]},
            headers=self.auth,
        )
        self.assertEqual(locked.status_code, 409)
        self.assertEqual(locked.get_json().get("code"), "channels_locked")
        again = self._lodge(slug="onepost-test")
        self.assertEqual(again.status_code, 409)
        from _lib import unified_inbox

        item_id = f"draft_asset:{BRAND}-calendar:{doc['asset_id']}"
        edit = unified_inbox.edit_item(
            item_id, editor="test", fields={"caption": "changed"}
        )
        self.assertFalse(edit.get("ok"))
        self.assertEqual(edit.get("code"), "locked")

    def test_scheduled_caption_edit_syncs(self):
        r = self._lodge(approve=False)
        doc = r.get_json()
        from _lib import unified_inbox

        item_id = f"draft_asset:{BRAND}-calendar:{doc['asset_id']}"
        edit = unified_inbox.edit_item(
            item_id, editor="test", fields={"caption": "Updated caption text"}
        )
        self.assertTrue(edit.get("ok"))
        from _lib import publish_sandbox

        rows = publish_sandbox.queue_rows_for_brand(BRAND)
        for row in rows:
            if str(row.get("status")) == "pending":
                self.assertIn("Updated", str(row.get("caption_preview")))

    def test_partial_failure_keeps_post(self):
        r = self._lodge()
        doc = r.get_json()
        cal_id = doc["calendar_id"]
        asset_id = doc["asset_id"]
        from _lib import publish_sandbox, unified_inbox

        publish_sandbox.release_moment(brand_id=BRAND, calendar_id=cal_id, dispatch=False)
        rows = publish_sandbox.queue_rows_for_brand(BRAND)
        ig_key = next(
            str(x["idempotency_key"]) for x in rows if x.get("platform") == "instagram"
        )
        fb_key = next(
            str(x["idempotency_key"]) for x in rows if x.get("platform") == "facebook"
        )

        def fake_dispatch(row, cache):
            plat = str(row.get("platform"))
            if plat == "instagram":
                receipt, _ = publish_sandbox.dispatch_item(row)
                return receipt, None
            return {}, "postiz create_post: 401 unauthorized"

        with mock.patch(
            "_lib.publish_live.postiz_status",
            return_value={"configured": True, "ok": True, "api_key_present": True},
        ), mock.patch("_lib.publish_live._dispatch_row_live", fake_dispatch):
            from _lib import publish_live

            publish_live.dispatch_pending(force_keys={ig_key, fb_key})
        rows = publish_sandbox.queue_rows_for_brand(BRAND)
        fb = next(x for x in rows if x.get("platform") == "facebook")
        self.assertEqual(int(fb.get("attempts") or 0), 1)
        self.assertTrue(fb.get("last_error"))
        st = unified_inbox.post_state_for(BRAND, cal_id)
        self.assertEqual(st.get("state"), "partly_posted")
        _cid, asset = unified_inbox._campaign_asset_for_id(
            unified_inbox._load_campaign_data(), asset_id
        )
        self.assertEqual(asset.get("caption"), "One post test caption")

    def test_retry_delivery(self):
        r = self._lodge(channels=["instagram"])
        doc = r.get_json()
        cal_id = doc["calendar_id"]
        from _lib import publish_sandbox

        publish_sandbox.release_moment(brand_id=BRAND, calendar_id=cal_id, dispatch=False)
        rows = publish_sandbox.queue_rows_for_brand(BRAND)
        row = rows[0]
        row["status"] = "failed"
        row["attempts"] = 3
        row["human_approved"] = True
        publish_sandbox._rewrite_jsonl(publish_sandbox._queue_path(), rows)
        out = publish_sandbox.retry_delivery(
            brand_id=BRAND, calendar_id=cal_id, channel="instagram"
        )
        self.assertTrue(out.get("ok"))
        rows = publish_sandbox.queue_rows_for_brand(BRAND)
        row = rows[0]
        self.assertEqual(row.get("status"), "pending")
        self.assertEqual(int(row.get("attempts") or 0), 0)
        self.assertTrue(row.get("human_approved"))

    def test_post_state_contract(self):
        r = self._lodge()
        doc = r.get_json()
        from _lib import unified_inbox

        ps = unified_inbox.post_state_for(BRAND, doc["calendar_id"])
        for key in (
            "deliveries",
            "channels_picked",
            "channels_available",
            "channels_locked",
            "delivery_summary",
        ):
            self.assertIn(key, ps)
        self.assertEqual(len(ps["deliveries"]), 2)

    def test_review_one_item_per_post(self):
        r = self._lodge(approve=False, slug="review-group-slug")
        doc = r.get_json()
        from _lib import unified_inbox, publish_sandbox
        from datetime import timezone

        ap = unified_inbox.approve_item(
            f"draft_asset:{BRAND}-calendar:{doc['asset_id']}",
            editor="test",
        )
        self.assertTrue(ap.get("ok"), ap)
        self.assertGreaterEqual(len(publish_sandbox.queue_rows_for_brand(BRAND)), 1)
        items = unified_inbox._publish_request_items(
            brand=BRAND, status="pending", now=datetime.now(timezone.utc)
        )
        asset_id = doc["asset_id"]
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0].get("meta") or {}).get("asset_id"), asset_id)
        legacy = unified_inbox.find_item(f"publish_request:qc-{asset_id}-instagram")
        self.assertIsNotNone(legacy)
        self.assertEqual(legacy["id"], items[0]["id"])

    def test_one_image_all_channels(self):
        r = self._lodge()
        doc = r.get_json()
        from _lib import publish_sandbox, unified_inbox

        rows = publish_sandbox.queue_rows_for_brand(BRAND)
        urls = {str(x.get("image_url") or "") for x in rows}
        urls.discard("")
        self.assertEqual(len(urls), 1)
        _cid, asset = unified_inbox._campaign_asset_for_id(
            unified_inbox._load_campaign_data(), doc["asset_id"]
        )
        self.assertIn("instagram", asset.get("composed") or {})

    def test_onepost_backfill(self):
        self._lodge()
        from _lib.jobs.onepost_backfill import run

        dry = run(apply=False)
        self.assertTrue(dry.get("ok"))
        self.assertTrue(dry.get("dry_run"))
        self.assertGreater(dry.get("writes", 0), 0)
        apply = run(apply=True)
        self.assertTrue(apply.get("ok"))
        self.assertFalse(apply.get("dry_run"))


if __name__ == "__main__":
    unittest.main()
