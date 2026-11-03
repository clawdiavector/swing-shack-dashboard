"""Rejecting from the clean calendar is obvious and visible (2026-10-29).

Christelle typed a reason ("H cuts off") and could not see how to send it: the
reject only went when Reject was clicked a second time. And a rejected post
still read "Waiting for a yes", so a reject looked like it did nothing.

Now: the note box has its own Send button (her calendar and Herman's page),
and a rejected post leaves the Needs your OK count, stays on its day marked
"Sent back" with the reason, and can still be moved or commented on.
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

TOKEN = "test-job-token-not-a-secret"
BRAND = "swing-shack"


class RejectedWordingTests(unittest.TestCase):
    def test_a_rejected_draft_says_sent_back_with_the_reason(self):
        from _lib.clean_calendar import count_views, post_entry

        e = post_entry({"calendar_id": "c", "state": "draft_ready", "go_live_date": "2026-11-02",
                        "rejected_reason": "H cuts off"}, BRAND, caption="x", today=date(2026, 10, 29))
        self.assertTrue(e["rejected"])
        self.assertEqual(e["view"], "approval")
        self.assertEqual(e["status"], "Sent back: H cuts off")
        self.assertEqual(e["actions"], ["comment"])
        self.assertTrue(e["movable"])
        self.assertEqual(count_views([e])["approval"], 0)

    def test_herman_s_page_has_a_send_button_for_notes(self):
        from _lib import clean_calendar as cc

        e = cc.post_entry({"calendar_id": "a", "state": "draft_ready", "go_live_date": "2026-11-02",
                           "title": "Post"}, BRAND, caption="x")
        view = {"brand": BRAND, "brand_name": "Swing Shack", "month": "2026-11", "month_label": "November 2026",
                "counts": {"scheduled": 0, "approval": 1, "ideas": 0}, "entries": [e]}
        html = cc.render_share_page(view, token="tok", who="Herman")
        self.assertIn("data-send", html)
        self.assertIn("Send", html)


def _image() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1080, 1350), (20, 90, 60)).save(buf, format="JPEG")
    return buf.getvalue()


class RejectRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-clean-cal-reject-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_SANDBOX_DIR", "COS_JOB_TOKEN")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        os.environ["COS_JOB_TOKEN"] = TOKEN
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
        from _lib import marketing_calendar, publish_sandbox

        publish_sandbox.ensure_sandbox_layout()
        app = self.app_module
        self._gate_orig = app._v26_mc_orig_upsert_event
        app._v26_mc_orig_upsert_event = marketing_calendar.upsert_event
        marketing_calendar.upsert_event = app._v26_wrapped_upsert_event
        self.anon = app.app.test_client(cos_anon=True)
        self.me = app.app.test_client()

    def tearDown(self):
        self.app_module._v26_mc_orig_upsert_event = self._gate_orig

    def test_a_rejected_post_leaves_the_waiting_count_and_shows_the_reason(self):
        day = (datetime.now(ZoneInfo("Africa/Johannesburg")).date() + timedelta(days=3)).isoformat()
        r = self.anon.post("/api/posts/lodge", headers={"Authorization": f"Bearer {TOKEN}",
                                                         "X-Actor-Display-Name": "christelle"}, json={
            "brand": BRAND, "slug": "ss-reject-a", "date": day, "title": "Iron fitting",
            "caption": "Book a fitting. DM us.", "image_base64": base64.b64encode(_image()).decode(),
            "approve": False,
        })
        self.assertEqual(r.status_code, 200, r.get_json())
        cid = r.get_json()["calendar_id"]
        before = self.me.get(f"/api/clean-calendar/{BRAND}?month={day[:7]}").get_json()["counts"]["approval"]
        r = self.me.post(f"/api/clean-calendar/{BRAND}/act",
                         json={"key": cid, "kind": "post", "action": "reject", "text": "H cuts off"})
        self.assertEqual(r.status_code, 200, r.get_json())
        body = self.me.get(f"/api/clean-calendar/{BRAND}?month={day[:7]}").get_json()
        self.assertEqual(body["counts"]["approval"], before - 1)
        entry = next(e for e in body["entries"] if e["key"] == cid)
        self.assertTrue(entry["rejected"])
        self.assertEqual(entry["status"], "Sent back: H cuts off")


if __name__ == "__main__":
    unittest.main()
