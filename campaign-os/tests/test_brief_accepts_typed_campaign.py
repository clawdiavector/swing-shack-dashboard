"""A campaign typed into the Calendar must be able to reach a Brief.

Before this, the add-event path wrote the pillar under `pillar` while the
Brief gate read `pillars`, and every operator-entered record scored
date_confidence=LOW. A typed campaign failed four hard gates and could
never be briefed. Other operator pins (content / moment / reminder) are
still refused.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import _planning_events as pe  # noqa: E402
from _lib import campaign_brief as cb  # noqa: E402


def _typed(type_="campaign", pillar="stick-retail"):
    return pe.build_event_record(
        "stick", "Psycho Bunny retail campaign", "2026-10-19",
        type_=type_, pillar=pillar, added_by="christelle")


def _gate(record):
    opp = cb._map_canonical_to_opportunity(record, "calendar")
    with patch.object(cb, "_find_opp_cluster", return_value=None):
        return cb._opportunity_gate("stick", opp, {}, {}, {})


def _failed(gate):
    return sorted({f["gate"] for f in gate.get("hard_gate_failures", [])})


class AddEventWritesCanonicalPillars(unittest.TestCase):
    def test_pillar_is_written_as_the_canonical_list(self):
        rec = _typed()
        self.assertEqual(rec["pillars"], ["stick-retail"])
        self.assertEqual(rec["pillar"], "stick-retail")

    def test_no_pillar_writes_no_pillars(self):
        self.assertNotIn("pillars", _typed(pillar=None))


class OpportunityMapping(unittest.TestCase):
    def test_typed_campaign_has_medium_date_confidence(self):
        opp = cb._map_canonical_to_opportunity(_typed(), "calendar")
        self.assertEqual(opp["date_confidence"], "MEDIUM")
        self.assertEqual(opp["pillars"], ["stick-retail"])

    def test_other_operator_pins_stay_low(self):
        for type_ in ("content", "moment", "reminder"):
            opp = cb._map_canonical_to_opportunity(_typed(type_=type_), "calendar")
            self.assertEqual(opp["date_confidence"], "LOW", type_)

    def test_untrusted_campaign_stays_low(self):
        rec = _typed()
        rec["trusted_for_planning"] = False
        opp = cb._map_canonical_to_opportunity(rec, "calendar")
        self.assertEqual(opp["date_confidence"], "LOW")

    def test_legacy_record_with_only_singular_pillar_is_read(self):
        rec = _typed()
        del rec["pillars"]
        opp = cb._map_canonical_to_opportunity(rec, "calendar")
        self.assertEqual(opp["pillars"], ["stick-retail"])

    def test_external_and_scout_dates_are_unchanged(self):
        rec = _typed()
        rec["source_origin"] = "scout"
        self.assertEqual(
            cb._map_canonical_to_opportunity(rec, "calendar")["date_confidence"], "HIGH")


class OpportunityGate(unittest.TestCase):
    def test_typed_campaign_passes_every_hard_gate(self):
        gate = _gate(_typed())
        self.assertEqual(_failed(gate), [])
        self.assertNotEqual(gate["gate"], cb.GATE_IGNORE)

    def test_legacy_typed_campaign_passes_too(self):
        rec = _typed()
        del rec["pillars"]
        self.assertEqual(_failed(_gate(rec)), [])

    def test_content_pin_is_still_refused(self):
        gate = _gate(_typed(type_="content"))
        self.assertEqual(gate["gate"], cb.GATE_IGNORE)
        self.assertEqual(_failed(gate), ["sufficient_evidence"])

    def test_campaign_without_a_pillar_is_still_refused(self):
        gate = _gate(_typed(pillar=None))
        self.assertEqual(gate["gate"], cb.GATE_IGNORE)
        self.assertIn("strategic_relevance", _failed(gate))


class BrandPillars(unittest.TestCase):
    """A pillar the brand declares in calendar_config must be briefable."""

    def _gate(self, brand, pillar):
        rec = pe.build_event_record(brand, "Membership drive", "2026-11-02",
                                    type_="campaign", pillar=pillar)
        opp = cb._map_canonical_to_opportunity(rec, "calendar")
        with patch.object(cb, "_find_opp_cluster", return_value=None):
            return cb._opportunity_gate(brand, opp, {}, {}, {})

    def test_swing_shack_declares_membership(self):
        self.assertIn("membership", cb._pillar_keys("swing-shack"))
        self.assertIn("membership", cb._north_stars("swing-shack"))

    def test_stick_keys_are_unchanged(self):
        self.assertEqual(cb._pillar_keys("stick"), cb.PILLAR_KEYS)

    def test_swing_shack_membership_campaign_passes_every_hard_gate(self):
        gate = self._gate("swing-shack", "ss-membership")
        self.assertEqual(_failed(gate), [])
        self.assertNotEqual(gate["gate"], cb.GATE_IGNORE)

    def test_membership_is_not_a_stick_pillar(self):
        gate = self._gate("stick", "ss-membership")
        self.assertEqual(gate["gate"], cb.GATE_IGNORE)
        self.assertIn("strategic_relevance", _failed(gate))


if __name__ == "__main__":
    unittest.main()
