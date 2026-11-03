"""Drag a post to another day on the clean calendar (2026-10-29).

Christelle asked for drag and drop on the month grid. A move changes the day
everywhere the post is booked: the calendar record, any pending send in the
queue, and Postiz for a post that lives there. Only Christelle's own calendar
can move things; Herman's link cannot.

What cannot move: anything already sent or sending, ideas (not on the
calendar yet), Google posts (their day is their place in the one-a-day
queue), and nothing moves onto a day that has passed.
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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

TOKEN = "test-job-token-not-a-secret"
BRAND = "swing-shack"
TODAY = date(2026, 10, 29)


def _cc():
    from _lib import clean_calendar as cc

    return cc


class MoveRuleTests(unittest.TestCase):
    def _post(self, state, day="2026-11-03", **row):
        return _cc().post_entry({"calendar_id": "c", "state": state, "go_live_date": day, **row}, BRAND,
                                caption="", today=TODAY)

    def test_posts_not_yet_sent_and_plan_steps_can_move(self):
        cc = _cc()
        for state in ("booked", "drafting", "needs_fix", "draft_ready", "scheduled", "gap"):
            self.assertTrue(self._post(state)["movable"], state)
            self.assertIsNone(cc.move_refusal(self._post(state), date(2026, 11, 5), TODAY), state)
        self.assertTrue(self._post("booked", plan_item_kind="shoot")["movable"])

    def test_sent_posts_ideas_and_google_posts_stay_put(self):
        cc = _cc()
        for state in ("released", "posted", "partly_posted", "send_failed"):
            e = self._post(state)
            self.assertFalse(e["movable"], state)
            self.assertIn("already", cc.move_refusal(e, date(2026, 11, 5), TODAY).lower())
        self.assertFalse(self._post("booked", post_type="posted-outside-campaign-os")["movable"])
        idea = cc.idea_entry({"key": "k", "source": "stock", "title": "x", "date": "2026-11-04"}, BRAND)
        self.assertFalse(idea["movable"])
        gbp = cc.gbp_entries([{"id": "g", "brand": BRAND, "status": "approved", "approvedAt": "1"}], BRAND,
                             first_slot=date(2026, 11, 2))[0]
        self.assertFalse(gbp["movable"])
        self.assertIn("google", cc.move_refusal(gbp, date(2026, 11, 5), TODAY).lower())

    def test_a_missed_post_can_be_moved_to_a_day_still_to_come(self):
        cc = _cc()
        e = self._post("booked", day="2026-10-02")
        self.assertTrue(e["movable"])
        self.assertIsNone(cc.move_refusal(e, date(2026, 11, 5), TODAY))

    def test_nothing_moves_onto_a_day_that_has_passed(self):
        cc = _cc()
        msg = cc.move_refusal(self._post("draft_ready"), date(2026, 10, 28), TODAY)
        self.assertIn("passed", msg.lower())
        self.assertIsNone(cc.move_refusal(self._post("draft_ready"), TODAY, TODAY))

    def test_a_postiz_post_keeps_its_time_and_never_lands_sooner_than_five_minutes(self):
        cc = _cc()
        sent = []

        class FakePz:
            def scheduled_at_least(self, publish_date, minutes=5):
                from _lib.postiz_client import scheduled_at_least

                return scheduled_at_least(publish_date, minutes)

            def reschedule_post(self, post_id, publish_date, *, brand_id=None):
                sent.append((post_id, publish_date, brand_id))
                return {"ok": True}, None

        # Far enough ahead that the real clock never makes it "too soon".
        row = {"id": "p1", "state": "QUEUE", "publishDate": "2030-11-04T07:30:00.000Z"}
        ok, msg = cc.move_postiz_post(FakePz(), BRAND, row, date(2030, 11, 9))
        self.assertTrue(ok, msg)
        self.assertEqual(sent[0][0], "p1")
        self.assertTrue(sent[0][1].startswith("2030-11-09T07:30"))
        self.assertEqual(sent[0][2], BRAND)

    def test_postiz_refusing_a_move_changes_nothing_and_says_so(self):
        cc = _cc()

        class FakePz:
            def scheduled_at_least(self, publish_date, minutes=5):
                return publish_date, False

            def reschedule_post(self, post_id, publish_date, *, brand_id=None):
                return None, ("http_400", "nope")

        ok, msg = cc.move_postiz_post(FakePz(), BRAND, {"id": "p1", "publishDate": "2026-11-04T07:30:00Z"},
                                      date(2026, 11, 9))
        self.assertFalse(ok)
        self.assertIn("still on", msg.lower())


def _image() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1080, 1350), (20, 90, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def _day(offset: int) -> str:
    return (datetime.now(ZoneInfo("Africa/Johannesburg")).date() + timedelta(days=offset)).isoformat()


class MoveRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-clean-cal-move-"))
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

    def _lodge(self, slug, approve, day):
        r = self.anon.post("/api/posts/lodge", headers=self.bearer, json={
            "brand": BRAND, "slug": slug, "date": day, "title": "Bay hire", "caption": "Book a bay. DM us.",
            "image_base64": base64.b64encode(_image()).decode(), "approve": approve,
        })
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["calendar_id"]

    def _move(self, key, day, client=None):
        return (client or self.me).post(f"/api/clean-calendar/{BRAND}/move",
                                        json={"key": key, "kind": "post", "date": day})

    def test_a_draft_moves_to_another_day(self):
        cid = self._lodge("ss-move-a", False, _day(3))
        r = self._move(cid, _day(6))
        self.assertEqual(r.status_code, 200, r.get_json())
        from _lib import unified_inbox

        state = unified_inbox.post_state_for(BRAND, cid)
        self.assertEqual(state["go_live_date"], _day(6))
        self.assertEqual(state["state"], "draft_ready")

    def test_a_scheduled_post_moves_its_pending_send_too(self):
        cid = self._lodge("ss-move-b", True, _day(3))
        r = self._move(cid, _day(8))
        self.assertEqual(r.status_code, 200, r.get_json())
        from _lib import unified_inbox

        state = unified_inbox.post_state_for(BRAND, cid)
        self.assertEqual(state["go_live_date"], _day(8))
        self.assertEqual(state["state"], "scheduled")
        pending = [s for s in state["sandbox"] if s.get("status") == "pending"]
        self.assertTrue(pending)
        for s in pending:
            self.assertTrue(str(s["would_publish_at"]).startswith(_day(8)), s)

    def test_a_move_onto_a_past_day_is_refused_and_nothing_changes(self):
        cid = self._lodge("ss-move-c", False, _day(3))
        r = self._move(cid, _day(-1))
        self.assertEqual(r.status_code, 400)
        from _lib import unified_inbox

        self.assertEqual(unified_inbox.post_state_for(BRAND, cid)["go_live_date"], _day(3))

    def test_moving_needs_a_login_and_herman_s_link_cannot_move(self):
        cid = self._lodge("ss-move-d", False, _day(3))
        self.assertEqual(self._move(cid, _day(5), client=self.anon).status_code, 401)
        token = self.me.post(f"/api/clean-calendar/{BRAND}/share", json={}).get_json()["share_url"].rsplit("/", 1)[1]
        r = self.anon.post(f"/share/calendar/{token}/move", json={"key": cid, "kind": "post", "date": _day(5)})
        self.assertIn(r.status_code, (404, 405))

    def test_the_month_view_says_what_can_move(self):
        cid = self._lodge("ss-move-e", False, _day(3))
        body = self.me.get(f"/api/clean-calendar/{BRAND}?month={_day(3)[:7]}").get_json()
        entry = next(e for e in body["entries"] if e["key"] == cid)
        self.assertTrue(entry["movable"])


if __name__ == "__main__":
    unittest.main()
