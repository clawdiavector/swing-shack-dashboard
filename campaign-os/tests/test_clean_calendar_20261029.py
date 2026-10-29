"""The clean calendar (2026-10-29): three views and a no-login link for Herman.

Christelle asked for a calendar anyone can read with no context: one view for
what is scheduled, one for what needs a yes, one for ideas. She shares a link
with Herman; he opens it without logging in, sees the real image and plain
words for every entry, and can approve, comment or reject.

Her decisions (2026-10-29): Herman's Approve sends the post the same way hers
does; the link needs no login and lasts 14 days; the clean view replaces the
Plan page, with the old grid one tab away.
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

from itsdangerous import URLSafeTimedSerializer

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

TOKEN = "test-job-token-not-a-secret"
BRAND = "swing-shack"


def _image(colour=(20, 90, 60)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1080, 1350), colour).save(buf, format="JPEG")
    return buf.getvalue()


def _day(offset: int = 3) -> str:
    return (datetime.now(ZoneInfo("Africa/Johannesburg")).date() + timedelta(days=offset)).isoformat()


# ── the module on its own ────────────────────────────────────────────────────


class ShareTokenTests(unittest.TestCase):
    def setUp(self):
        from _lib import clean_calendar as cc

        self.cc = cc
        self.ser = URLSafeTimedSerializer("not-a-real-secret")

    def test_a_link_names_one_brand_and_the_person_it_is_for(self):
        token = self.cc.mint_share_token(self.ser, "stick", who="Herman")
        self.assertEqual(self.cc.read_share_token(self.ser, token), {"brand": "stick", "who": "Herman"})

    def test_a_link_lasts_fourteen_days(self):
        self.assertEqual(self.cc.SHARE_MAX_AGE, 14 * 24 * 60 * 60)

    def test_a_token_minted_for_something_else_does_not_open_the_calendar(self):
        other = self.ser.dumps({"scope": "weekly_report_export", "v": 1})
        self.assertIsNone(self.cc.read_share_token(self.ser, other))
        session = self.ser.dumps({"authed": True})
        self.assertIsNone(self.cc.read_share_token(self.ser, session))

    def test_a_changed_or_expired_link_is_refused(self):
        token = self.cc.mint_share_token(self.ser, "stick")
        self.assertIsNone(self.cc.read_share_token(self.ser, token[:-2] + "xx"))
        self.assertIsNone(self.cc.read_share_token(self.ser, token, max_age=-1))
        self.assertIsNone(self.cc.read_share_token(self.ser, ""))

    def test_a_link_for_an_unknown_brand_cannot_be_made(self):
        with self.assertRaises(ValueError):
            self.cc.mint_share_token(self.ser, "mcm")


class ViewSortingTests(unittest.TestCase):
    def setUp(self):
        from _lib import clean_calendar as cc

        self.cc = cc

    def test_each_post_state_lands_in_one_view(self):
        b = self.cc.bucket_for_state
        for st in ("scheduled", "released", "posted", "partly_posted", "send_failed"):
            self.assertEqual(b(st), "scheduled", st)
        self.assertEqual(b("draft_ready"), "approval")
        for st in ("booked", "drafting", "needs_fix", "gap"):
            self.assertEqual(b(st), "making", st)
        self.assertIsNone(b("candidate"))

    def test_a_post_reads_without_context(self):
        row = {
            "calendar_id": "cal-1", "state": "draft_ready", "title": "Pro V1 in store",
            "go_live_date": "2026-10-31", "angle": "It arrived on this week's stock list.",
            "channels_picked": ["instagram", "facebook"], "post_type": "stick-product-post",
            "image_url": "/x.jpg",
        }
        e = self.cc.post_entry(row, "stick", caption="Fresh Pro V1s.\n\nDM us.")
        self.assertEqual(e["key"], "cal-1")
        self.assertEqual(e["view"], "approval")
        self.assertEqual(e["brand_name"], "Stick")
        self.assertEqual(e["when"], "Sat 31 Oct")
        self.assertEqual(e["where"], "Instagram and Facebook")
        self.assertTrue(e["what"])
        self.assertEqual(e["why"], "It arrived on this week's stock list.")
        self.assertEqual(e["caption"], "Fresh Pro V1s.\n\nDM us.")
        self.assertEqual(e["actions"], ["approve", "comment", "reject"])

    def test_a_scheduled_post_can_only_be_commented_on(self):
        e = self.cc.post_entry({"calendar_id": "c", "state": "scheduled", "go_live_date": "2026-11-02"},
                               "stick", caption="x")
        self.assertEqual(e["view"], "scheduled")
        self.assertEqual(e["actions"], ["comment"])

    def test_a_post_being_made_shows_under_approval_without_buttons(self):
        e = self.cc.post_entry({"calendar_id": "c", "state": "drafting", "go_live_date": "2026-11-02"},
                               "stick", caption="")
        self.assertEqual(e["view"], "approval")
        self.assertTrue(e["making"])
        self.assertEqual(e["actions"], ["comment"])

    def test_an_idea_says_what_happens_when_it_is_approved(self):
        item = {"key": "stock:abc", "source": "stock", "title": "Odyssey Ai-One putter",
                "date": "2026-11-04", "end": "2026-11-04", "why": "New on the stock list.",
                "kind": "stock"}
        e = self.cc.idea_entry(item, "stick")
        self.assertEqual(e["view"], "ideas")
        self.assertEqual(e["kind"], "idea")
        self.assertEqual(e["key"], "stock:abc")
        self.assertIn("stock list", e["what"].lower())
        self.assertEqual(e["why"], "New on the stock list.")
        self.assertIn("made", e["next"].lower())
        self.assertEqual(e["actions"], ["approve", "comment", "reject"])


class CommentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-clean-cal-"))
        self._prev = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.tmp)
        from _lib import clean_calendar as cc

        self.cc = cc

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_comments_are_kept_per_brand_and_entry(self):
        self.cc.add_comment("stick", "cal-1", "Herman", "Use the blue one.")
        self.cc.add_comment("swing-shack", "cal-1", "Herman", "Other brand.")
        got = self.cc.comments_by_key("stick")
        self.assertEqual([c["text"] for c in got["cal-1"]], ["Use the blue one."])
        self.assertEqual(got["cal-1"][0]["who"], "Herman")

    def test_an_empty_comment_is_refused(self):
        with self.assertRaises(ValueError):
            self.cc.add_comment("stick", "cal-1", "Herman", "   ")


class SharePageTests(unittest.TestCase):
    def test_the_page_escapes_captions_and_only_offers_allowed_buttons(self):
        from _lib import clean_calendar as cc

        view = {
            "brand": "stick", "brand_name": "Stick", "month": "2026-11", "month_label": "November 2026",
            "counts": {"scheduled": 1, "approval": 1, "ideas": 0},
            "entries": [
                cc.post_entry({"calendar_id": "a", "state": "draft_ready", "go_live_date": "2026-11-02",
                               "title": "<script>alert(1)</script>"}, "stick", caption="x"),
                cc.post_entry({"calendar_id": "b", "state": "scheduled", "go_live_date": "2026-11-03",
                               "title": "Already set"}, "stick", caption="y"),
            ],
        }
        html = cc.render_share_page(view, token="tok", who="Herman")
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Needs your OK", html)
        self.assertIn('data-key="a"', html)
        self.assertIn('data-action="approve"', html)
        self.assertNotIn('data-key="b" data-kind="post" data-action="approve"', html)


# ── the routes, end to end on a lodged draft ────────────────────────────────


class CleanCalendarRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-clean-cal-routes-"))
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
        self.bearer = {"Authorization": f"Bearer {TOKEN}", "X-Actor-Display-Name": "christelle"}

    def tearDown(self):
        self.app_module._v26_mc_orig_upsert_event = self._gate_orig

    def _lodge_draft(self, slug="ss-clean-cal-test", day=None):
        day = day or _day()
        r = self.anon.post("/api/posts/lodge", headers=self.bearer, json={
            "brand": BRAND, "slug": slug, "date": day, "title": "Bay hire this weekend",
            "caption": "Bays open all weekend. DM us to book.",
            "image_base64": base64.b64encode(_image()).decode(), "approve": False,
        })
        self.assertEqual(r.status_code, 200, r.get_json())
        body = r.get_json()
        self.assertEqual(body["state"], "draft_ready")
        return body["calendar_id"], day

    def _share(self, brand=BRAND):
        r = self.me.post(f"/api/clean-calendar/{brand}/share", json={"who": "Herman"})
        self.assertEqual(r.status_code, 200, r.get_json())
        url = r.get_json()["share_url"]
        self.assertIn("/share/calendar/", url)
        return url.split("/share/calendar/", 1)[1]

    def test_sharing_needs_a_login(self):
        r = self.anon.post(f"/api/clean-calendar/{BRAND}/share", json={})
        self.assertEqual(r.status_code, 401)
        r = self.anon.get(f"/api/clean-calendar/{BRAND}?month=2026-11")
        self.assertEqual(r.status_code, 401)

    def test_a_bad_link_shows_a_plain_page_not_the_login(self):
        r = self.anon.get("/share/calendar/not-a-token")
        self.assertEqual(r.status_code, 404)
        self.assertIn(b"link", r.data.lower())

    def test_my_view_lists_the_draft_under_needs_approval(self):
        cal_id, day = self._lodge_draft()
        r = self.me.get(f"/api/clean-calendar/{BRAND}?month={day[:7]}")
        self.assertEqual(r.status_code, 200, r.get_json())
        body = r.get_json()
        self.assertGreaterEqual(body["counts"]["approval"], 1)
        entry = next(e for e in body["entries"] if e["key"] == cal_id)
        self.assertEqual(entry["view"], "approval")
        self.assertEqual(entry["caption"], "Bays open all weekend. DM us to book.")
        self.assertTrue(entry["image"])

    def test_herman_opens_the_link_and_approves_without_logging_in(self):
        cal_id, day = self._lodge_draft()
        token = self._share()
        page = self.anon.get(f"/share/calendar/{token}?month={day[:7]}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Bay hire this weekend", page.data)
        img = self.anon.get(f"/share/calendar/{token}/image/{cal_id}")
        self.assertEqual(img.status_code, 200)
        self.assertTrue(img.mimetype.startswith("image/"))
        r = self.anon.post(f"/share/calendar/{token}/act",
                           json={"key": cal_id, "kind": "post", "action": "approve", "month": day[:7]})
        self.assertEqual(r.status_code, 200, r.get_json())
        from _lib import unified_inbox

        self.assertEqual(unified_inbox.post_state_for(BRAND, cal_id)["state"], "scheduled")

    def test_a_reject_needs_a_reason_and_is_kept_as_a_comment(self):
        cal_id, day = self._lodge_draft()
        token = self._share()
        r = self.anon.post(f"/share/calendar/{token}/act",
                           json={"key": cal_id, "kind": "post", "action": "reject", "text": ""})
        self.assertEqual(r.status_code, 400)
        r = self.anon.post(f"/share/calendar/{token}/act",
                           json={"key": cal_id, "kind": "post", "action": "reject", "text": "Wrong bay photo."})
        self.assertEqual(r.status_code, 200, r.get_json())
        mine = self.me.get(f"/api/clean-calendar/{BRAND}?month={day[:7]}").get_json()
        notes = [c for e in mine["entries"] for c in e.get("comments", []) if c["text"] == "Wrong bay photo."]
        self.assertEqual(notes[0]["who"], "Herman")

    def test_a_comment_shows_on_my_calendar(self):
        cal_id, day = self._lodge_draft()
        token = self._share()
        r = self.anon.post(f"/share/calendar/{token}/act",
                           json={"key": cal_id, "kind": "post", "action": "comment", "text": "Love it."})
        self.assertEqual(r.status_code, 200, r.get_json())
        mine = self.me.get(f"/api/clean-calendar/{BRAND}?month={day[:7]}").get_json()
        entry = next(e for e in mine["entries"] if e["key"] == cal_id)
        self.assertEqual(entry["comments"][-1]["text"], "Love it.")

    def test_a_link_for_one_brand_cannot_touch_the_other(self):
        cal_id, _ = self._lodge_draft()
        token = self._share("stick")
        r = self.anon.post(f"/share/calendar/{token}/act",
                           json={"key": cal_id, "kind": "post", "action": "approve"})
        self.assertEqual(r.status_code, 404)
        img = self.anon.get(f"/share/calendar/{token}/image/{cal_id}")
        self.assertEqual(img.status_code, 404)
        from _lib import unified_inbox

        self.assertEqual(unified_inbox.post_state_for(BRAND, cal_id)["state"], "draft_ready")

    def test_the_link_opens_nothing_else(self):
        token = self._share()
        r = self.anon.get(f"/api/clean-calendar/{BRAND}?month=2026-11&share={token}")
        self.assertEqual(r.status_code, 401)
        r = self.anon.get(f"/app/calendar/posts?share={token}")
        self.assertEqual(r.status_code, 302)


if __name__ == "__main__":
    unittest.main()
