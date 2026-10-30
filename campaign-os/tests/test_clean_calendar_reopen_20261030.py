"""Reopen a sent-back post on the clean calendar (2026-10-30).

The 07:15 asset check wrongly rejected lodged posts, including one Christelle
had approved. There was no way back: a rejected draft could not be opened
again. Reopen puts a sent-back post back to waiting for a yes (reason
cleared, noted on the post), and from there it can be approved as usual.
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
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

TOKEN = "test-job-token-not-a-secret"
BRAND = "swing-shack"


def _image() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1080, 1350), (20, 90, 60)).save(buf, format="JPEG")
    return buf.getvalue()


class ReopenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-clean-cal-reopen-"))
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

    def _entry(self, cid, month):
        body = self.me.get(f"/api/clean-calendar/{BRAND}?month={month}").get_json()
        return next(e for e in body["entries"] if e["key"] == cid)

    def _act(self, cid, action, text=""):
        return self.me.post(f"/api/clean-calendar/{BRAND}/act",
                            json={"key": cid, "kind": "post", "action": action, "text": text})

    def test_a_sent_back_post_reopens_then_approves(self):
        day = (datetime.now(ZoneInfo("Africa/Johannesburg")).date() + timedelta(days=3)).isoformat()
        r = self.anon.post("/api/posts/lodge", headers={"Authorization": f"Bearer {TOKEN}",
                                                         "X-Actor-Display-Name": "christelle"}, json={
            "brand": BRAND, "slug": "ss-reopen-a", "date": day, "title": "Quantum Mini",
            "caption": "New Quantum Mini in store. DM us.", "image_base64": base64.b64encode(_image()).decode(),
            "approve": False,
        })
        self.assertEqual(r.status_code, 200, r.get_json())
        cid = r.get_json()["calendar_id"]
        self.assertEqual(self._act(cid, "reject", "image file missing or empty").status_code, 200)
        self.assertTrue(self._entry(cid, day[:7])["rejected"])

        r = self._act(cid, "reopen")
        self.assertEqual(r.status_code, 200, r.get_json())
        e = self._entry(cid, day[:7])
        self.assertFalse(e["rejected"])
        self.assertEqual(e["status"], "Waiting for a yes")
        self.assertIn("Reopened", [c["text"] for c in e["comments"]])

        self.assertEqual(self._act(cid, "approve").status_code, 200)
        from _lib import unified_inbox

        self.assertEqual(unified_inbox.post_state_for(BRAND, cid)["state"], "scheduled")

    def test_only_a_sent_back_post_can_be_reopened(self):
        day = (datetime.now(ZoneInfo("Africa/Johannesburg")).date() + timedelta(days=3)).isoformat()
        r = self.anon.post("/api/posts/lodge", headers={"Authorization": f"Bearer {TOKEN}",
                                                         "X-Actor-Display-Name": "christelle"}, json={
            "brand": BRAND, "slug": "ss-reopen-b", "date": day, "title": "Waiting",
            "caption": "Book a bay. DM us.", "image_base64": base64.b64encode(_image()).decode(),
            "approve": False,
        })
        cid = r.get_json()["calendar_id"]
        self.assertEqual(self._act(cid, "reopen").status_code, 409)


if __name__ == "__main__":
    unittest.main()
