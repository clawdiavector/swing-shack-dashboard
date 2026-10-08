"""Suggest Date form -> approve -> Brief, through the real HTTP routes.

Mirrors what the Calendar screen sends when the operator files a typed
entry as a campaign with a pillar and a "why".
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

CAMPAIGN_OS = Path(__file__).resolve().parents[1]

PURPOSE = "Drive Psycho Bunny sales in store using current stock"


def _form_body(**over):
    body = {
        "brand_id": "stick",
        "type": "campaign",
        "status": "candidate",
        "title": "Psycho Bunny retail campaign",
        "start": "2026-10-19",
        "end": "2026-10-19",
        "public_peak": "2026-10-19",
        "source": "OPERATOR_PROVIDED",
        "source_kind": "operator",
        "importance": "ASSESS",
        "notes": "",
        "created_by": "operator",
        "evidence_kind": "OPERATOR_PROVIDED",
        "is_suggested": True,
        "why_it_matters": PURPOSE,
        "pillars": ["stick-retail"],
    }
    body.update(over)
    return body


class TypedCampaignEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-typed-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app
        from _lib import campaign_brief as cb
        from _lib import marketing_calendar as mc

        cls.module, cls.mc, cls.cb = campaign_app, mc, cb
        campaign_app.init_repo = lambda: None
        cls.client = campaign_app.app.test_client()
        # Both modules read DATA_DIR at import; point them at the temp dir
        # whatever was imported before this test.
        cls.patches = [
            patch.object(mc, "_DATA_DIR", cls.tmpdir),
            patch.object(mc, "_CALENDAR_DIR", cls.tmpdir / "intelligence" / "marketing-calendar"),
            patch.object(mc, "_CALENDAR_DIR_READY", False),
            patch.object(cb, "DATA_DIR_DEFAULT", str(cls.tmpdir)),
        ]
        for p in cls.patches:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)

    def _suggest_and_approve(self, **over):
        brand = over.get("brand_id", "stick")
        res = self.client.post("/api/calendar/candidates", json=_form_body(**over))
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        cid = res.get_json()["record"]["calendar_id"]
        res = self.client.post(
            f"/api/planning/{brand}/candidates/{cid}/approve",
            json={}, headers={"X-Actor-Display-Name": "Christelle"})
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        return res.get_json()["event_key"]

    def _record(self, event_key):
        return next(r for r in self.mc.list_records("stick")
                    if r.get("event_key") == event_key and r.get("status") == "approved")

    def test_campaign_with_pillar_and_purpose_reaches_a_brief(self):
        event_key = self._suggest_and_approve()
        rec = self._record(event_key)
        self.assertEqual(rec["type"], "campaign")
        self.assertEqual(rec["pillars"], ["stick-retail"])
        self.assertEqual(rec["purpose"], PURPOSE)

        res = self.client.post("/api/brief/v1/create",
                               json={"brand_id": "stick", "opportunity_id": event_key})
        body = res.get_json()
        self.assertEqual(res.status_code, 200, body)
        brief = body["brief"]
        self.assertEqual(brief["opportunity_gate"]["gate"], "BRIEF")
        self.assertEqual(brief["opportunity"]["operator_purpose"], PURPOSE)
        self.assertIn(PURPOSE, brief["opportunity"]["why_it_may_matter"])
        self.assertEqual(brief["business_objective"]["pillar_supported"], "retail")

    def test_swing_shack_membership_campaign_reaches_a_brief(self):
        purpose = "Sign up 20 new members before the summer season"
        event_key = self._suggest_and_approve(
            brand_id="swing-shack", title="Summer membership drive",
            pillars=["ss-membership"], why_it_matters=purpose)

        found = self.client.get(f"/api/brief/v1/swing-shack/find-by-event/{event_key}").get_json()
        self.assertFalse(found["exists"])

        res = self.client.post("/api/brief/v1/create",
                               json={"brand_id": "swing-shack", "opportunity_id": event_key})
        body = res.get_json()
        self.assertEqual(res.status_code, 200, body)
        brief = body["brief"]
        self.assertEqual(brief["opportunity_gate"]["gate"], "BRIEF")
        self.assertEqual(brief["business_objective"]["pillar_supported"], "membership")
        self.assertEqual(brief["opportunity"]["operator_purpose"], purpose)

        # What the Create Brief button relies on afterwards.
        found = self.client.get(f"/api/brief/v1/swing-shack/find-by-event/{event_key}").get_json()
        self.assertTrue(found["exists"])
        self.assertEqual(found["brief"]["brief_id"], brief["brief_id"])
        again = self.client.post("/api/brief/v1/create",
                                 json={"brand_id": "swing-shack", "opportunity_id": event_key}).get_json()
        self.assertEqual(again["existing_brief"]["brief_id"], brief["brief_id"])
        review = self.client.get(f"/api/brief/v1/swing-shack/{brief['brief_id']}/review")
        self.assertEqual(review.status_code, 200)

    def test_importance_picked_on_the_form_becomes_the_tier(self):
        picked = self._suggest_and_approve(title="Picked B", importance="B-PIN")
        self.assertEqual(self._record(picked)["tier"], "B-PIN")
        assessed = self._suggest_and_approve(title="Left to assess", importance="ASSESS")
        self.assertEqual(self._record(assessed)["tier"], "C-PIN")

    def test_approved_entry_is_on_the_timeline_for_its_year(self):
        self._suggest_and_approve(title="New Year New Swing", start="2027-01-01",
                                  end="2027-01-02", public_peak="2027-01-01",
                                  pillars=["stick-coaching"], importance="B-PIN")
        # The range form is what the Calendar screen requests.
        res = self.client.get("/api/planning/stick/timeline?start=2026-10-08&end=2027-10-08")
        names = {e.get("name"): e for e in res.get_json().get("events", [])}
        self.assertIn("New Year New Swing", names)
        entry = names["New Year New Swing"]
        self.assertEqual(entry["tier"], "B-PIN")
        self.assertEqual(entry["start"], "2027-01-01")
        self.assertTrue(entry["id"])
        # Every event the timeline returns must be nameable and openable.
        for ev in res.get_json()["events"]:
            self.assertTrue(ev.get("name") and ev.get("id"), ev.get("event_key"))
        self.assertEqual(entry["pillars"], {"coaching": PURPOSE})
        self.assertEqual(entry["commercial_push"], PURPOSE)

        from urllib.parse import quote
        detail = self.client.get(f"/api/planning/stick/event/{quote(entry['id'], safe='')}")
        self.assertEqual(detail.status_code, 200, detail.get_data(as_text=True))
        self.assertEqual(detail.get_json()["event"]["name"], "New Year New Swing")
        self.assertEqual(self.client.get("/api/planning/stick/event/nope").status_code, 404)

    def _search(self, q, brand="stick"):
        return [r for r in self.client.get(f"/api/planning/{brand}/search?q={q}").get_json()["results"]]

    def test_search_shows_one_row_before_and_after_approval(self):
        title = "Dupe check drive"
        res = self.client.post("/api/calendar/candidates", json=_form_body(title=title))
        cid = res.get_json()["record"]["calendar_id"]
        rows = [r for r in self._search("dupe") if r["title"] == title]
        self.assertEqual([r["state"] for r in rows], ["CANDIDATE"])
        self.assertEqual(rows[0]["candidate_id"], cid)

        approved = self.client.post(
            f"/api/planning/stick/candidates/{cid}/approve",
            json={}, headers={"X-Actor-Display-Name": "Christelle"}).get_json()
        rows = [r for r in self._search("dupe") if r["title"] == title]
        self.assertEqual([r["state"] for r in rows], ["ON_MAIN_CALENDAR"])
        self.assertEqual(rows[0]["event_key"], approved["event_key"])
        self.assertEqual(rows[0]["candidate_id"], cid)

    def test_unapproved_suggestion_is_still_listed_once(self):
        title = "Still a candidate"
        self.client.post("/api/calendar/candidates", json=_form_body(title=title))
        rows = [r for r in self._search("still") if r["title"] == title]
        self.assertEqual([r["state"] for r in rows], ["CANDIDATE"])

    def test_open_planning_resolves_operator_entries(self):
        from urllib.parse import quote
        title = "Planning context drive"
        res = self.client.post("/api/calendar/candidates",
                               json=_form_body(title=title, importance="B-PIN"))
        cid = res.get_json()["record"]["calendar_id"]

        before = self.client.get(f"/api/planning/stick/candidates/{cid}/planning-context")
        self.assertEqual(before.status_code, 200, before.get_data(as_text=True))
        self.assertFalse(before.get_json()["is_approved"])
        self.assertEqual(before.get_json()["context"]["event"]["name"], title)

        event_key = self.client.post(
            f"/api/planning/stick/candidates/{cid}/approve",
            json={}, headers={"X-Actor-Display-Name": "Christelle"}).get_json()["event_key"]
        for ident in (cid, event_key):
            ctx = self.client.get(
                f"/api/planning/stick/candidates/{quote(ident, safe='')}/planning-context")
            body = ctx.get_json()
            self.assertEqual(ctx.status_code, 200, body)
            self.assertTrue(body["is_approved"], ident)
            self.assertEqual(body["event_key"], event_key)
            self.assertEqual(body["context"]["planning_state"], "on_spine")
            self.assertEqual(body["context"]["event"]["name"], title)
            self.assertEqual(body["context"]["tier"], "B-PIN")

        missing = self.client.get("/api/planning/stick/candidates/nope/planning-context")
        self.assertEqual(missing.status_code, 404)

    def test_moment_from_the_same_form_is_still_refused(self):
        event_key = self._suggest_and_approve(
            type="moment", title="Ladies clinic at Stick", pillars=[])
        self.assertEqual(self._record(event_key)["type"], "moment")
        res = self.client.post("/api/brief/v1/create",
                               json={"brand_id": "stick", "opportunity_id": event_key})
        self.assertEqual(res.get_json().get("decision"), "IGNORE")

    def _waiting(self, brand="stick"):
        body = self.client.get(f"/api/planning/{brand}/waiting").get_json()
        self.assertEqual(body["count"], len(body["suggestions"]))
        return body["suggestions"]

    def test_suggestion_waits_at_the_top_of_plan_until_it_is_added(self):
        title = "Waiting list drive"
        res = self.client.post("/api/calendar/candidates", json=_form_body(
            title=title, start="2026-11-20", end="2026-11-21", public_peak="2026-11-20"))
        cid = res.get_json()["record"]["calendar_id"]
        rows = [s for s in self._waiting() if s["title"] == title]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {
            "candidate_id": cid, "title": title, "date": "2026-11-20",
            "end_date": "2026-11-21", "type": "campaign", "pillars": ["stick-retail"],
            "why_it_matters": PURPOSE, "created_at": rows[0]["created_at"],
        })
        self.assertNotIn(title, [s["title"] for s in self._waiting("swing-shack")])

        self.client.post(f"/api/planning/stick/candidates/{cid}/approve",
                         json={}, headers={"X-Actor-Display-Name": "Christelle"})
        self.assertNotIn(title, [s["title"] for s in self._waiting()])

    def test_waiting_list_is_soonest_first(self):
        for title, day in (("Wait later", "2027-03-01"), ("Wait sooner", "2026-12-01")):
            self.client.post("/api/calendar/candidates", json=_form_body(
                title=title, start=day, end=day, public_peak=day))
        titles = [s["title"] for s in self._waiting() if s["title"].startswith("Wait ")]
        self.assertEqual(titles, ["Wait sooner", "Wait later"])

    def test_timeline_says_which_entries_already_have_a_brief(self):
        def entry(key):
            res = self.client.get("/api/planning/stick/timeline?start=2026-10-08&end=2027-10-08")
            return next(e for e in res.get_json()["events"] if e.get("event_key") == key)

        event_key = self._suggest_and_approve(title="Brief step drive")
        self.assertEqual(entry(event_key)["brief_id"], "")
        self.assertEqual(entry(event_key)["type"], "campaign")
        brief = self.client.post(
            "/api/brief/v1/create",
            json={"brand_id": "stick", "opportunity_id": event_key}).get_json()["brief"]
        self.assertEqual(entry(event_key)["brief_id"], brief["brief_id"])


if __name__ == "__main__":
    unittest.main()
