"""Approving a calendar date must still resolve for Make a plan.

The month view writes calendar_id cal-<brand>-cam-<ts>-<hex>, then immediately
asks the Brief engine for that id. Looking only at spine slugs (halloween-2026)
returned 'opportunity … not found' on every approve.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import campaign_brief as cb  # noqa: E402
from _lib import _planning_events as pe  # noqa: E402

CID = "cal-swing-shack-cam-1762547176-860196b6"
EVENT_KEY = f"swing-shack:{CID}:2026-11-07"
HYPHEN_KEY = f"swing-shack:{CID}-2026-11-07"


def _row(**over):
    rec = {
        "event_key": EVENT_KEY,
        "calendar_id": CID,
        "title": "Halloween",
        "type": "campaign",
        "status": "approved",
        "event_start": "2026-11-07",
        "event_end": "2026-11-07",
        "source_origin": "internal_strategy",
        "trusted_for_planning": True,
        "pillars": ["ss-fitting"],
        "lanes": ["campaign"],
    }
    rec.update(over)
    return rec


class LaneKeys(unittest.TestCase):
    def test_dict_and_list_and_empty(self):
        self.assertEqual(cb._lane_keys({"paid": {}, "crm": {}}), ["paid", "crm"])
        self.assertEqual(cb._lane_keys(["campaign", "paid"]), ["campaign", "paid"])
        self.assertEqual(cb._lane_keys(None), [])
        self.assertEqual(cb._lane_keys(""), [])

    def test_map_does_not_throw_on_list_lanes(self):
        opp = cb._map_canonical_to_opportunity(_row(), "calendar")
        self.assertEqual(opp["lanes"], ["campaign"])
        self.assertEqual(opp["calendar_id"], CID)


class ApprovedCalendarResolve(unittest.TestCase):
    def setUp(self):
        self.mc = MagicMock()
        self.mc.canonical_records.return_value = [_row()]
        self.mc.list_records.return_value = [_row()]
        self.mc.load_brand_config.return_value = {}
        self.mc.compute_lead_time_schedule.return_value = {}
        self.patch = patch.object(cb, "_marketing_calendar_import", return_value=self.mc)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_colon_event_key_from_approve(self):
        opp = cb._resolve_opportunity("swing-shack", EVENT_KEY)
        self.assertEqual(opp.get("name"), "Halloween")
        self.assertEqual(opp.get("event_key"), EVENT_KEY)

    def test_hyphen_event_key_as_shown_in_the_banner(self):
        opp = cb._resolve_opportunity("swing-shack", HYPHEN_KEY)
        self.assertEqual(opp.get("name"), "Halloween")

    def test_raw_calendar_id(self):
        opp = cb._resolve_opportunity("swing-shack", CID)
        self.assertEqual(opp.get("calendar_id"), CID)

    def test_unknown_still_empty(self):
        self.mc.canonical_records.return_value = []
        self.mc.list_records.return_value = []
        self.assertEqual(cb._resolve_opportunity("swing-shack", "nope-2026"), {})

    def test_approved_date_without_source_origin_is_still_briefable(self):
        thin = _row(source_origin="", trusted_for_planning=False)
        self.mc.canonical_records.return_value = [thin]
        opp = cb._resolve_opportunity("swing-shack", EVENT_KEY)
        self.assertEqual(opp.get("date_confidence"), "MEDIUM")
        self.assertEqual(opp.get("source_origin"), "internal_strategy")
        gate = cb._opportunity_gate("swing-shack", opp, {}, {}, {})
        reasons = " ".join(f.get("reason") or "" for f in gate.get("hard_gate_failures") or [])
        self.assertNotIn("date_confidence=LOW", reasons)
        self.assertNotIn("source_origin=", reasons)

    def test_one_bad_row_does_not_hide_the_date(self):
        bad = _row(event_key="swing-shack:broken", source_urls=123)
        good = _row()
        self.mc.canonical_records.return_value = [bad, good]
        opps = cb.get_brief_opportunities("swing-shack")
        keys = {o.get("event_key") for o in opps}
        self.assertIn(EVENT_KEY, keys)


class ApprovedSlug(unittest.TestCase):
    def test_generated_calendar_id_slugs_from_the_title(self):
        key = pe._build_event_key_from_candidate("swing-shack", {
            "id": CID,
            "name": "Halloween",
            "start": "2026-10-31",
        })
        self.assertEqual(key, "swing-shack:halloween:2026-10-31")
        self.assertNotIn("cal-", key)

    def test_real_candidate_id_still_uses_the_id(self):
        key = pe._build_event_key_from_candidate("stick", {
            "id": "candidate-alfred-dunhill-championship-2027",
            "start": "2027-12-09",
        })
        self.assertEqual(key, "stick:alfred-dunhill-championship-2027:2027-12-09")


if __name__ == "__main__":
    unittest.main()
