"""Everything on the clean calendar, and one campaign's timeline (2026-10-29).

Christelle, after the first build: "EVERYTHING need to be viewable in the
calendar", and a way to single out one campaign and see only its timeline
(planning, shoot, posts), shareable or exportable. Her calls the same day:
the export is a PDF; Approve on a Postiz draft schedules it in Postiz.

What used to be missing or mislabelled:
  - posts made outside Campaign OS and videos sent to Postiz showed as "being made"
  - plan steps (research, shoot, edit, review, boost) showed as "being made"
  - stories and drafts that exist only in Postiz did not show at all
  - Google Business posts did not show at all
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from itsdangerous import URLSafeTimedSerializer

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

BRAND = "stick"


def _cc():
    from _lib import clean_calendar as cc

    return cc


# ── calendar records that are not ordinary posts ────────────────────────────


class RecordKindTests(unittest.TestCase):
    def test_a_post_made_outside_campaign_os_is_scheduled_with_its_picture_and_link(self):
        e = _cc().post_entry({
            "calendar_id": "c1", "state": "booked", "go_live_date": "2026-11-02", "title": "Instagram story",
            "post_type": "posted-outside-campaign-os", "thumbnail_url": "https://cdn.example/x.jpg",
            "permalink": "https://instagram.com/p/abc",
        }, BRAND, caption="")
        self.assertEqual(e["view"], "scheduled")
        self.assertFalse(e["making"])
        self.assertEqual(e["status"], "Posted outside Campaign OS")
        self.assertTrue(e["has_image"])
        self.assertEqual(e["link"], "https://instagram.com/p/abc")

    def test_a_video_in_postiz_reads_as_scheduled_or_waiting(self):
        cc = _cc()
        sched = cc.post_entry({"calendar_id": "v1", "state": "booked", "go_live_date": "2026-11-02",
                               "postiz_mode": "schedule"}, BRAND, caption="")
        self.assertEqual(sched["view"], "scheduled")
        self.assertIn("Postiz", sched["status"])
        draft = cc.post_entry({"calendar_id": "v2", "state": "booked", "go_live_date": "2026-11-02",
                               "postiz_mode": "draft", "postiz_post_id": "pz-9"}, BRAND, caption="")
        self.assertEqual(draft["view"], "approval")
        self.assertFalse(draft["making"])
        self.assertEqual(draft["actions"], ["approve", "comment", "reject"])

    def test_a_plan_step_is_a_to_do_not_a_post_being_made(self):
        e = _cc().post_entry({"calendar_id": "s1", "state": "booked", "go_live_date": "2026-11-06",
                              "plan_item_kind": "shoot", "title": "Shoot bags in store"}, BRAND, caption="")
        self.assertEqual(e["view"], "todo")
        self.assertEqual(e["kind"], "task")
        self.assertFalse(e["making"])
        self.assertIn("shoot", e["what"].lower())
        self.assertEqual(e["actions"], ["comment"])

    def test_a_planned_post_step_is_still_a_post(self):
        e = _cc().post_entry({"calendar_id": "p1", "state": "booked", "go_live_date": "2026-11-15",
                              "plan_item_kind": "post"}, BRAND, caption="")
        self.assertEqual(e["view"], "approval")
        self.assertTrue(e["making"])


# ── Postiz-only posts ───────────────────────────────────────────────────────


def _pz(pid, state, when="2026-11-04T07:00:00.000Z", **over):
    row = {"id": pid, "state": state, "publishDate": when, "content": "<p>Offer is <b>live</b></p>",
           "image": json.dumps([{"id": "m1", "path": "https://uploads.postiz.com/a.jpg"}]),
           "integration": {"id": "int-ig", "providerIdentifier": "instagram-standalone", "name": "stick"}}
    row.update(over)
    return row


class PostizTests(unittest.TestCase):
    def test_queued_and_draft_posts_show_published_ones_are_left_to_the_sync(self):
        cc = _cc()
        rows = [_pz("a", "QUEUE"), _pz("b", "DRAFT"), _pz("c", "PUBLISHED"), _pz("d", "ERROR")]
        got = {e["key"]: e for e in cc.postiz_entries(rows, BRAND, linked_ids=set(), month="2026-11")}
        self.assertEqual(set(got), {"postiz:a", "postiz:b", "postiz:d"})
        self.assertEqual(got["postiz:a"]["view"], "scheduled")
        self.assertEqual(got["postiz:b"]["view"], "approval")
        self.assertEqual(got["postiz:b"]["actions"], ["approve", "comment", "reject"])
        self.assertEqual(got["postiz:a"]["actions"], ["comment"])
        self.assertEqual(got["postiz:d"]["view"], "approval")
        self.assertIn("did not send", got["postiz:d"]["status"].lower())

    def test_a_postiz_post_reads_without_context(self):
        e = _cc().postiz_entries([_pz("a", "QUEUE")], BRAND, linked_ids=set(), month="2026-11")[0]
        self.assertEqual(e["kind"], "postiz")
        self.assertEqual(e["date"], "2026-11-04")
        self.assertEqual(e["where"], "Instagram")
        self.assertEqual(e["caption"], "Offer is live")
        self.assertEqual(e["image"], "https://uploads.postiz.com/a.jpg")
        self.assertTrue(e["what"])

    def test_a_story_says_so(self):
        e = _cc().postiz_entries([_pz("s", "QUEUE", settings={"post_type": "story"})], BRAND,
                                 linked_ids=set(), month="2026-11")[0]
        self.assertEqual(e["what"], "An Instagram story")

    def test_posts_campaign_os_already_knows_and_other_months_are_skipped(self):
        cc = _cc()
        rows = [_pz("a", "QUEUE"), _pz("b", "QUEUE", when="2026-12-01T07:00:00Z")]
        self.assertEqual(cc.postiz_entries(rows, BRAND, linked_ids={"a"}, month="2026-11"), [])

    def test_approving_a_draft_schedules_a_copy_then_removes_the_draft(self):
        cc = _cc()
        calls = []

        class FakePz:
            def create_post(self, integration_id, content, media=None, **kw):
                calls.append(("create", integration_id, content, media, kw.get("publish_date"), kw.get("draft")))
                return {"id": "new"}, None

            def delete_post(self, post_id, **kw):
                calls.append(("delete", post_id))
                return {}, None

        ok, msg = cc.schedule_postiz_draft(FakePz(), BRAND, _pz("b", "DRAFT"))
        self.assertTrue(ok, msg)
        self.assertEqual(calls[0][0], "create")
        self.assertEqual(calls[0][1], "int-ig")
        self.assertEqual(calls[0][3], [{"id": "m1", "path": "https://uploads.postiz.com/a.jpg"}])
        self.assertEqual(calls[0][4], "2026-11-04T07:00:00.000Z")
        self.assertFalse(calls[0][5])
        self.assertEqual(calls[1], ("delete", "b"))

    def test_a_failed_schedule_keeps_the_draft(self):
        cc = _cc()
        deleted = []

        class FakePz:
            def create_post(self, *a, **kw):
                return None, ("http_500", "boom")

            def delete_post(self, post_id, **kw):
                deleted.append(post_id)
                return {}, None

        ok, msg = cc.schedule_postiz_draft(FakePz(), BRAND, _pz("b", "DRAFT"))
        self.assertFalse(ok)
        self.assertEqual(deleted, [])
        self.assertIn("draft is still there", msg.lower())


# ── Google Business posts ───────────────────────────────────────────────────


class GbpTests(unittest.TestCase):
    def test_approved_posts_go_one_a_day_in_approval_order_and_waiting_ones_need_a_yes(self):
        cc = _cc()
        drafts = [
            {"id": "g2", "brand": BRAND, "status": "approved", "approvedAt": "2026-10-28T10:00:00Z", "title": "Second"},
            {"id": "g1", "brand": BRAND, "status": "approved", "approvedAt": "2026-10-27T10:00:00Z", "title": "First",
             "imageUrl": "https://x/1.jpg", "body": "Come in."},
            {"id": "g3", "brand": BRAND, "status": "draft", "title": "Waiting"},
        ]
        got = {e["key"]: e for e in cc.gbp_entries(drafts, BRAND, first_slot=date(2026, 11, 2))}
        self.assertEqual(got["gbp:g1"]["date"], "2026-11-02")
        self.assertEqual(got["gbp:g2"]["date"], "2026-11-03")
        self.assertEqual(got["gbp:g1"]["view"], "scheduled")
        self.assertEqual(got["gbp:g1"]["where"], "Google")
        self.assertEqual(got["gbp:g1"]["caption"], "Come in.")
        self.assertEqual(got["gbp:g3"]["view"], "approval")
        self.assertEqual(got["gbp:g3"]["actions"], ["approve", "comment", "reject"])


# ── one campaign's timeline ─────────────────────────────────────────────────


def _plan():
    return {
        "plan_id": "pln-bf", "brand_id": BRAND, "event_name": "Black Friday 2026", "event_date": "2026-11-27",
        "window_start": "2026-11-23", "peak_date": "2026-11-27", "status": "approved",
        "items": [
            {"item_id": "i3", "kind": "post", "title": "Teaser", "due": "2026-11-15", "status": "kept",
             "calendar_id": "cal-teaser", "owner": "Christelle"},
            {"item_id": "i1", "kind": "research", "title": "Check stock", "due": "2026-10-26", "status": "done"},
            {"item_id": "i2", "kind": "shoot", "title": "Shoot bags", "due": "2026-11-06", "status": "kept",
             "owner": "Christelle", "shots": ["Bag on a trolley"], "late": False},
            {"item_id": "i4", "kind": "boost", "title": "Boost the reel", "due": "2026-11-23", "status": "removed"},
        ],
    }


class TimelineTests(unittest.TestCase):
    def test_steps_run_in_date_order_with_phases_and_removed_steps_left_out(self):
        cc = _cc()
        post = cc.post_entry({"calendar_id": "cal-teaser", "state": "draft_ready", "go_live_date": "2026-11-15",
                              "title": "Teaser"}, BRAND, caption="Soon.")
        t = cc.campaign_timeline(_plan(), {"cal-teaser": post}, BRAND)
        self.assertEqual(t["title"], "Black Friday 2026")
        self.assertEqual([s["item_id"] for s in t["steps"]], ["i1", "i2", "i3"])
        self.assertEqual([s["phase"] for s in t["steps"]], ["Planning", "Shoot", "Posts"])
        self.assertEqual(t["steps"][0]["status"], "Done")
        self.assertEqual(t["steps"][1]["shots"], ["Bag on a trolley"])
        self.assertEqual(t["steps"][2]["entry"]["key"], "cal-teaser")
        self.assertEqual(t["steps"][2]["status"], "Waiting for a yes")

    def test_the_campaign_list_leaves_out_replaced_and_archived_plans(self):
        cc = _cc()
        plans = [_plan(), {**_plan(), "plan_id": "old", "status": "superseded"},
                 {**_plan(), "plan_id": "gone", "status": "archived"}]
        self.assertEqual([c["plan_id"] for c in cc.campaign_list(plans)], ["pln-bf"])

    def test_a_campaign_link_names_its_plan(self):
        cc = _cc()
        ser = URLSafeTimedSerializer("not-a-real-secret")
        tok = cc.mint_share_token(ser, BRAND, who="Herman", plan_id="pln-bf")
        self.assertEqual(cc.read_share_token(ser, tok), {"brand": BRAND, "who": "Herman", "plan": "pln-bf"})

    def test_the_printable_page_escapes_text_and_offers_save_as_pdf(self):
        cc = _cc()
        plan = _plan()
        plan["event_name"] = "<b>BF</b>"
        html = cc.render_campaign_page(cc.campaign_timeline(plan, {}, BRAND), token="", who="", printable=True)
        self.assertIn("&lt;b&gt;BF&lt;/b&gt;", html)
        self.assertIn("Save as PDF", html)
        self.assertNotIn('data-action="approve"', html)


# ── the routes ──────────────────────────────────────────────────────────────


class CampaignRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-clean-cal-camp-"))
        cls._prev = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        import app as app_module

        cls.app_module = app_module

    @classmethod
    def tearDownClass(cls):
        if cls._prev is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = cls._prev
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        os.environ["DATA_DIR"] = str(self.tmpdir)
        self.app_module.DATA_DIR = str(self.tmpdir)
        plans = self.tmpdir / "plans" / BRAND
        plans.mkdir(parents=True, exist_ok=True)
        (plans / "pln-bf.json").write_text(json.dumps(_plan()), encoding="utf-8")
        self.me = self.app_module.app.test_client()
        self.anon = self.app_module.app.test_client(cos_anon=True)

    def test_i_can_list_campaigns_and_open_one(self):
        r = self.me.get(f"/api/clean-calendar/{BRAND}/campaigns")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertIn("pln-bf", [c["plan_id"] for c in r.get_json()["campaigns"]])
        r = self.me.get(f"/api/clean-calendar/{BRAND}/campaign/pln-bf")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["title"], "Black Friday 2026")
        self.assertEqual(self.me.get(f"/api/clean-calendar/{BRAND}/campaign/nope").status_code, 404)

    def test_the_pdf_page_needs_a_login_and_prints(self):
        self.assertNotEqual(self.anon.get(f"/api/clean-calendar/{BRAND}/campaign/pln-bf/print").status_code, 200)
        r = self.me.get(f"/api/clean-calendar/{BRAND}/campaign/pln-bf/print")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Save as PDF", r.data)
        self.assertIn(b"Black Friday 2026", r.data)

    def test_a_campaign_link_opens_only_that_campaign_without_a_login(self):
        r = self.me.post(f"/api/clean-calendar/{BRAND}/share", json={"who": "Herman", "plan_id": "pln-bf"})
        self.assertEqual(r.status_code, 200, r.get_json())
        token = r.get_json()["share_url"].split("/share/calendar/", 1)[1]
        page = self.anon.get(f"/share/calendar/{token}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Black Friday 2026", page.data)
        self.assertIn(b"Shoot bags", page.data)
        self.assertIn(b"Save as PDF", page.data)

    def test_a_link_for_a_campaign_that_is_not_there_is_refused(self):
        r = self.me.post(f"/api/clean-calendar/{BRAND}/share", json={"plan_id": "nope"})
        self.assertEqual(r.status_code, 404)

    def test_the_month_counts_the_to_do_list(self):
        r = self.me.get(f"/api/clean-calendar/{BRAND}?month=2026-11")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertIn("todo", r.get_json()["counts"])


if __name__ == "__main__":
    unittest.main()
