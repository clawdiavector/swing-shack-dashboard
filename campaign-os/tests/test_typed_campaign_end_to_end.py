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

    def test_moment_from_the_same_form_is_still_refused(self):
        event_key = self._suggest_and_approve(
            type="moment", title="Ladies clinic at Stick", pillars=[])
        self.assertEqual(self._record(event_key)["type"], "moment")
        res = self.client.post("/api/brief/v1/create",
                               json={"brand_id": "stick", "opportunity_id": event_key})
        self.assertEqual(res.get_json().get("decision"), "IGNORE")


if __name__ == "__main__":
    unittest.main()
