"""
tests/test_calendar_v27_intake.py — V2.7 intake + write-gate closure.

Reproduces and verifies:
  - automation_writer classification (hermes-scout, heidi-ingest,
    holiday_inject, cos-reactive-watch, foreman-template-*,
    foreman-generative-replace).
  - intake store API (write_intake_record, write_important_dates).
  - classifier changes: foreman records without an approval-lodge
    transition_reason → REQUIRES_REAPPROVAL, not KEEP.
  - end-to-end: automation writers are forbidden from touching the
    operator store (V2.7 §3), the canonical approval path still works.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _lib import _calendar_v27_intake as v27
from _lib import _calendar_v26_cleanup as v26


class AutomationWriterClassificationTests(unittest.TestCase):
    """V2.7 §3 — classify which writers are automation."""

    def test_hermes_scout_is_automation(self):
        self.assertTrue(v27.is_automation_writer({"created_by": "hermes-scout"}))

    def test_heidi_ingest_is_automation(self):
        self.assertTrue(v27.is_automation_writer({"created_by": "heidi-ingest"}))

    def test_holiday_inject_is_automation(self):
        self.assertTrue(v27.is_automation_writer(
            {"created_by": "holiday_inject", "source_origin": "deterministic_calendar"}
        ))

    def test_cos_reactive_watch_is_automation(self):
        self.assertTrue(v27.is_automation_writer({"created_by": "cos-reactive-watch"}))

    def test_foreman_template_test_is_automation(self):
        self.assertTrue(v27.is_automation_writer({"created_by": "foreman-template-test"}))

    def test_foreman_template_demo_v2_is_automation(self):
        self.assertTrue(v27.is_automation_writer({"created_by": "foreman-template-demo-v2"}))

    def test_foreman_generative_replace_is_automation(self):
        self.assertTrue(v27.is_automation_writer({"created_by": "foreman-generative-replace"}))

    def test_kyle_desk_is_NOT_automation(self):
        # kyle-desk is the human-approval author — never automation.
        self.assertFalse(v27.is_automation_writer({"created_by": "kyle-desk"}))

    def test_empty_created_by_with_deterministic_origin_is_automation(self):
        # Empty creator + automated source_type = automation
        self.assertTrue(v27.is_automation_writer({
            "created_by": "", "source_type": "scout"
        }))

    def test_interpreter_source_type_is_automation(self):
        self.assertTrue(v27.is_automation_writer({"source_type": "interpreter"}))


class V26ClassifierV27RulesTests(unittest.TestCase):
    """V2.7 §4 — foreman is NOT automatically human. Records with
    cb=='foreman' must have an approval transition_reason to KEEP."""

    def test_kyle_desk_is_KEEP(self):
        rec = {"created_by": "kyle-desk", "transition_reason": "Lodge"}
        self.assertEqual(v26.classify_record(rec), "KEEP")

    def test_kyle_desk_no_transition_reason_is_REQUIRES_REAPPROVAL(self):
        """V2.8 dedup — kyle-desk without a human transition_reason
        is REQUIRES_REAPPROVAL (the dedup picks the strongest
        variant)."""
        rec = {"created_by": "kyle-desk"}  # no transition_reason
        self.assertEqual(v26.classify_record(rec), "REQUIRES_REAPPROVAL")

    def test_foreman_with_lodge_is_KEEP(self):
        rec = {"created_by": "foreman", "transition_reason": "Lodge"}
        self.assertEqual(v26.classify_record(rec), "KEEP")

    def test_foreman_with_book_is_KEEP(self):
        rec = {"created_by": "foreman", "transition_reason": "Book"}
        self.assertEqual(v26.classify_record(rec), "KEEP")

    def test_foreman_with_L4_approve_is_KEEP(self):
        rec = {"created_by": "foreman", "transition_reason": "L4 approve"}
        self.assertEqual(v26.classify_record(rec), "KEEP")

    def test_foreman_empty_transition_requires_reapproval(self):
        # Empty transition_reason → REQUIRES_REAPPROVAL
        rec = {"created_by": "foreman", "transition_reason": ""}
        self.assertEqual(v26.classify_record(rec), "REQUIRES_REAPPROVAL")

    def test_foreman_no_transition_reason_field_requires_reapproval(self):
        # Missing transition_reason field → REQUIRES_REAPPROVAL
        rec = {"created_by": "foreman"}
        self.assertEqual(v26.classify_record(rec), "REQUIRES_REAPPROVAL")

    def test_foreman_with_generative_replace_transition_requires_reapproval(self):
        # transition_reason present but automation-tagged
        rec = {"created_by": "foreman", "transition_reason": "generative-replace-v1"}
        self.assertEqual(v26.classify_record(rec), "REQUIRES_REAPPROVAL")

    def test_foreman_template_test_is_template_demo(self):
        rec = {"created_by": "foreman-template-test", "transition_reason": ""}
        self.assertEqual(v26.classify_record(rec), "TEMPLATE_DEMO")

    def test_foreman_generative_replace_is_template_demo(self):
        """V2.7 §6 — foreman-generative-replace is template/test pollution."""
        rec = {
            "created_by": "foreman-generative-replace",
            "source_origin": "internal_strategy",
            "transition_reason": "generative-replace-v1",
            "status": "candidate",
        }
        self.assertEqual(v26.classify_record(rec), "TEMPLATE_DEMO")

    def test_foreman_template_demo_v2_is_template_demo(self):
        rec = {"created_by": "foreman-template-demo-v2"}
        self.assertEqual(v26.classify_record(rec), "TEMPLATE_DEMO")

    def test_cos_reactive_watch_is_scout_candidate(self):
        """V2.7 §7 — cos-reactive-watch goes to intake, not Main Calendar."""
        rec = {
            "created_by": "cos-reactive-watch",
            "source_origin": "deterministic_calendar",
            "status": "candidate",
        }
        self.assertEqual(v26.classify_record(rec), "SCOUT_CANDIDATE")

    def test_empty_creator_with_scout_source_type_is_scout_candidate(self):
        """V2.7 — legacy mass-inject with empty created_by + scout source_type."""
        rec = {
            "created_by": "",
            "source_type": "scout",
            "status": "",
        }
        self.assertEqual(v26.classify_record(rec), "SCOUT_CANDIDATE")

    def test_production_corpus_has_zero_unclassified(self):
        """The V2.7 classifier handles every category in V2.5's
        production corpus — no UNCLASSIFIED fallout."""
        corpus_categories = [
            # V2.5-class shape records
            ("TEST_ACCEPTANCE_ARTIFACT", {"created_by": "", "event_key": "swing-shack:alfred-dunhill-championship-2027:2027-02-25"}),
            ("TEMPLATE_DEMO", {"created_by": "foreman-template-demo"}),
            ("DETERMINISTIC_HOLIDAY", {"created_by": "holiday_inject", "source_origin": "deterministic_calendar"}),
            ("SCOUT_CANDIDATE", {"created_by": "hermes-scout", "status": "candidate"}),
            ("SCOUT_MASS_PROMOTED_CEO_DEMO", {"created_by": "hermes-scout", "transition_reason": "CEO demo — land stale calendar candidates", "status": "approved"}),
            ("SCOUT_WATCHLIST", {"created_by": "heidi-ingest", "status": "watchlist"}),
            ("LEGACY_UNVERIFIED_APPROVAL", {"created_by": "", "transition_reason": "CEO demo — land stale calendar candidates"}),
            ("REQUIRES_REAPPROVAL", {"created_by": "foreman"}),
            ("KEEP", {"created_by": "kyle-desk", "transition_reason": "Lodge"}),
            # V2.7-new shape records
            ("TEMPLATE_DEMO", {"created_by": "foreman-generative-replace"}),
            ("SCOUT_CANDIDATE", {"created_by": "cos-reactive-watch"}),
            # V2.7 §9 alfred-dunhill laundered records
            ("SCOUT_CANDIDATE", {"event_key": "swing-shack:alfred-dunhill-championship:2027", "status": "candidate"}),
            ("REQUIRES_REAPPROVAL", {"event_key": "swing-shack:alfred-dunhill-championship:2027", "status": "approved"}),
            # V2.7 §9 automation-laundered transition_reason
            ("REQUIRES_REAPPROVAL", {"transition_reason": "canonical status still candidate; lodge so cooker can run"}),
            # V2.7 §6 foreman-gen-* variants
            ("TEMPLATE_DEMO", {"created_by": "foreman-gen-unblock"}),
            ("TEMPLATE_DEMO", {"created_by": "foreman-gen-v2-ss-fitting"}),
            # V2.8 dedup: kyle-desk without transition_reason is now
            # REQUIRES_REAPPROVAL (not KEEP). The dedup rule keeps
            # only the variant with a human-action transition_reason.
            ("REQUIRES_REAPPROVAL", {"created_by": "kyle-desk"}),
            # V2.8 §6 — Stick/Bag-Drop unknown-provenance records
            # (empty cb + empty so + empty tr) → REQUIRES_REAPPROVAL.
            ("REQUIRES_REAPPROVAL", {"event_key": "stick:nedbank-golf-challenge:2026", "created_by": "", "source_origin": "", "status": "", "transition_reason": ""}),
            ("REQUIRES_REAPPROVAL", {"event_key": "stick:presidents-cup:2026", "created_by": "", "source_origin": "", "status": "candidate", "transition_reason": ""}),
        ]
        for expected_category, record in corpus_categories:
            actual = v26.classify_record(record)
            self.assertEqual(
                actual, expected_category,
                f"expected {expected_category} for {record}, got {actual}"
            )


class IntakeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="cos-v27-intake-")
        os.environ["DATA_DIR"] = self.tmpdir

    def tearDown(self):
        os.environ.pop("DATA_DIR", None)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_intake_record_creates_new(self):
        rec = v27.write_intake_record("swing-shack", {
            "type": "moment",
            "title": "Test intake",
            "event_start": "2026-12-31",
            "event_end": "2026-12-31",
            "status": "candidate",
            "created_by": "hermes-scout",
            "event_key": "swing-shack:test:2026",
        })
        # The returned record should carry intake tags
        self.assertTrue(rec.get("intake_store"))
        self.assertEqual(rec["revision"], 1)
        self.assertEqual(rec["change_type"], "new_event")
        # File written
        self.assertEqual(v27.intake_count("swing-shack"), 1)

    def test_write_intake_record_idempotent_on_event_key(self):
        # First write
        v27.write_intake_record("swing-shack", {
            "type": "moment",
            "title": "Test",
            "event_start": "2026-12-31",
            "event_end": "2026-12-31",
            "status": "candidate",
            "created_by": "hermes-scout",
            "event_key": "swing-shack:test:2026",
        })
        # Second write with same event_key → revision 2
        rec = v27.write_intake_record("swing-shack", {
            "type": "moment",
            "title": "Test (updated)",
            "event_start": "2026-12-31",
            "event_end": "2026-12-31",
            "status": "candidate",
            "created_by": "hermes-scout",
            "event_key": "swing-shack:test:2026",
        })
        self.assertEqual(rec["revision"], 2)
        self.assertEqual(rec["change_type"], "updated")
        # Total count = 2 records (original + updated)
        self.assertEqual(v27.intake_count("swing-shack"), 2)

    def test_write_important_dates_creates(self):
        result = v27.write_important_dates("swing-shack", {
            "type": "moment",
            "title": "Heritage Day",
            "event_start": "2026-09-24",
            "event_end": "2026-09-24",
            "status": "candidate",
            "source_origin": "deterministic_calendar",
            "event_key": "swing-shack:heritage-day:2026",
        })
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["record"].get("layer"), "strategic_moment")
        self.assertEqual(v27.important_dates_count("swing-shack"), 1)

    def test_write_important_dates_idempotent(self):
        record = {
            "title": "Heritage Day",
            "event_start": "2026-09-24",
            "event_end": "2026-09-24",
            "status": "candidate",
            "source_origin": "deterministic_calendar",
            "event_key": "swing-shack:heritage-day:2026",
        }
        v27.write_important_dates("swing-shack", record)
        result = v27.write_important_dates("swing-shack", record)
        self.assertEqual(result["action"], "noop")
        self.assertEqual(v27.important_dates_count("swing-shack"), 1)

    def test_store_snapshot(self):
        v27.write_intake_record("swing-shack", {
            "type": "moment", "title": "T", "event_start": "2026-12-31",
            "event_end": "2026-12-31", "status": "candidate",
            "created_by": "hermes-scout", "event_key": "swing-shack:test:2026",
        })
        v27.write_important_dates("swing-shack", {
            "title": "Heritage Day", "event_start": "2026-09-24",
            "event_end": "2026-09-24", "status": "candidate",
            "source_origin": "deterministic_calendar",
            "event_key": "swing-shack:heritage-day:2026",
        })
        snap = v27.store_snapshot("swing-shack")
        self.assertEqual(snap["intake"], 1)
        self.assertEqual(snap["important_dates"], 1)
        self.assertEqual(snap["operator_main_calendar"], 0)

    def test_automation_writer_blocked_from_operator_store(self):
        """V2.7 §3 — automation writer + operator-store target = blocked."""
        rec = {
            "created_by": "hermes-scout",
            "source_type": "scout",
            "title": "Scout tried operator-store",
        }
        with self.assertRaises(PermissionError) as ctx:
            v27.assert_automation_uses_intake_or_important_dates(rec, "operator")
        self.assertIn("V2.7", str(ctx.exception))

    def test_human_approval_allowed_in_operator_store(self):
        """V2.7 §3 — human approvals may target operator-store."""
        rec = {
            "created_by": "kyle-desk",
            "transition_reason": "Lodge",
            "title": "K approved this",
        }
        # Should NOT raise
        v27.assert_automation_uses_intake_or_important_dates(rec, "operator")


if __name__ == "__main__":
    unittest.main()
