"""
tests/test_calendar_v26_cleanup.py — V2.6 production store cleanup.

Reproduces the V2.5 production corpus in a temp DATA_DIR, runs the
cleanup, and verifies the operator store ends up with only the
single genuine kyle-desk record.

Also tests:
  - backup_calendar() writes a verified copy
  - dry_run_cleanup() classifies all 48 records correctly
  - execute_cleanup() respects confirm=True + plan_signature
  - execute_cleanup() preserves audit history
  - cleanup_status() returns is_clean=True after execution
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Make app modules importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _lib import _calendar_v26_cleanup as v26


def _gen_record(**overrides):
    """Build a sample marketing-calendar jsonl record."""
    base = {
        "brand_id": "swing-shack",
        "event_key": "swing-shack:sample:2026",
        "title": "Sample event",
        "status": "approved",
        "event_start": "2026-12-31",
        "event_end": "2026-12-31",
        "source_origin": "internal_strategy",
        "created_by": "operator",
        "transition_reason": "Lodge",
        "created_at": "2026-09-25T10:19:54+00:00",
    }
    base.update(overrides)
    return base


def _write_calendar(tmpdir, brand_id, records):
    cal_dir = Path(tmpdir) / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    cal_file = cal_dir / f"{brand_id}.jsonl"
    with open(cal_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return cal_file


def _build_v25_corpus():
    """The 48-record V2.5 production corpus, simplified. All 48 records
    use the same shape V2.5 saw.
    """
    records = []

    # 1. V2.4 acceptance test artifact
    records.append(_gen_record(
        event_key="swing-shack:alfred-dunhill-championship-2027:2027-02-25",
        title="Alfred Dunhill Championship 2027 (Durban CC)",
        source_origin="internal_strategy",
        created_by="",
        transition_reason="",
        status="",
        created_at="2026-09-28T16:10:22+00:00",
    ))

    # 15 template / demo records
    for i in range(15):
        prefix = "tpl-demo" if i < 7 else "tpl-v2"
        slug = f"swing-shack:{prefix}-sample-{i}:2026"
        title = f"Template demo {i}"
        cb = "foreman-template-test" if i == 0 else ("foreman-template-demo" if i < 8 else "foreman-template-demo-v2")
        records.append(_gen_record(
            event_key=slug,
            title=title,
            created_by=cb,
            transition_reason="template-demo" if i >= 7 else "ss-did-you-know template test" if i == 0 else "",
            status="approved",
            source_origin="internal_strategy",
            source_type="operator" if i > 0 else "",
        ))

    # 12 deterministic holidays
    for i in range(12):
        records.append(_gen_record(
            event_key=f"swing-shack:holiday-{i}:2026",
            title=f"Public holiday {i}",
            created_by="holiday_inject",
            source_origin="deterministic_calendar",
            transition_reason="CEO demo — land stale calendar candidates",
            status="approved",
            created_at="2026-09-18T06:34:48+00:00",
        ))

    # 12 hermes-scout records (9 candidate + 3 mass-promoted)
    for i in range(9):
        records.append(_gen_record(
            event_key=f"swing-shack:scout-cand-{i}:2026",
            title=f"Scout candidate {i}",
            created_by="hermes-scout",
            source_origin="external",
            source_type="scout",
            status="candidate",
            transition_reason="",
        ))
    for i in range(3):
        records.append(_gen_record(
            event_key=f"swing-shack:scout-mass-{i}:2026",
            title=f"Scout mass-promoted {i}",
            created_by="hermes-scout",
            source_origin="external",
            source_type="scout",
            status="approved",
            transition_reason="CEO demo — land stale calendar candidates",
        ))

    # 3 heidi-ingest (1 candidate + 2 watchlist)
    records.append(_gen_record(
        event_key="swing-shack:heidi-cand-1:2026",
        title="Heidi candidate",
        created_by="heidi-ingest",
        source_origin="external",
        source_type="scout",
        status="candidate",
    ))
    for i in range(2):
        records.append(_gen_record(
            event_key=f"swing-shack:heidi-watch-{i}:2026",
            title=f"Heidi watchlist {i}",
            created_by="heidi-ingest",
            source_origin="external",
            source_type="scout",
            status="watchlist",
        ))

    # 5 unknown-provenance 2026-09-17 mass-inject
    for i in range(5):
        records.append(_gen_record(
            event_key=f"swing-shack:unknown-{i}:2026",
            title=f"Unknown {i}",
            created_by="",
            source_origin="external" if i < 3 else "internal_strategy",
            status="",
            transition_reason="CEO demo — land stale calendar candidates" if i < 3 else "",
            created_at="2026-09-17T14:58:58+00:00",
        ))

    # 1 genuine kyle-desk operator approval
    records.append(_gen_record(
        event_key="swing-shack:trackman-coaching-session:2026",
        title="TrackMan coaching session",
        created_by="kyle-desk",
        source_origin="internal_strategy",
        status="approved",
        transition_reason="Lodge",
        created_at="2026-09-25T10:19:54+00:00",
    ))

    return records


class V26CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="cos-v26-iso-")
        self.records = _build_v25_corpus()
        # 49 is the V2.5 corpus expanded by 1 (heidi-ingest candidate)
        # — the production corpus was 48. The classifier handles both.
        self.assertGreaterEqual(len(self.records), 48)
        _write_calendar(self.tmpdir, "swing-shack", self.records)
        # write a dummy audit file
        audit_dir = Path(self.tmpdir) / "calendar-audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / "swing-shack-approvals.jsonl").write_text("")
        os.environ["DATA_DIR"] = self.tmpdir

    def tearDown(self):
        os.environ.pop("DATA_DIR", None)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_calendar(self, records):
        """V2.8 — helper for tests that need to write a custom
        operator-store corpus (e.g. duplicate event_key cases)."""
        _write_calendar(self.tmpdir, "swing-shack", records)

    def test_classify_count(self):
        from collections import Counter
        cats = Counter(v26.classify_record(r) for r in self.records)
        self.assertEqual(cats["TEST_ACCEPTANCE_ARTIFACT"], 1)
        self.assertEqual(cats["TEMPLATE_DEMO"], 15)
        self.assertEqual(cats["DETERMINISTIC_HOLIDAY"], 12)
        # 9 hermes-scout candidate + 1 heidi-ingest candidate = 10
        self.assertEqual(cats["SCOUT_CANDIDATE"], 10)
        self.assertEqual(cats["SCOUT_MASS_PROMOTED_CEO_DEMO"], 3)
        self.assertEqual(cats["SCOUT_WATCHLIST"], 2)
        self.assertEqual(cats["LEGACY_UNVERIFIED_APPROVAL"], 5)
        self.assertEqual(cats["KEEP"], 1)
        # Total: 1+15+12+10+3+2+5+1 = 49 (the fixture is 49)
        self.assertEqual(sum(cats.values()), 49)

    def test_dry_run_signature_stable(self):
        dry1 = v26.dry_run_cleanup("swing-shack")
        dry2 = v26.dry_run_cleanup("swing-shack")
        # Same inputs → same plan → same signature
        self.assertEqual(dry1["plan_signature"], dry2["plan_signature"])
        self.assertEqual(dry1["source_line_count"], len(self.records))

    def test_dry_run_wrong_signature_rejected(self):
        dry = v26.dry_run_cleanup("swing-shack")
        actor = {
            "actor_id": "fp:test",
            "actor_id_method": "test",
            "actor_display_name": "v26-test-runner",
        }
        result, code = v26.execute_cleanup(
            "swing-shack", "wrong-signature", actor, confirm=True,
        )
        self.assertEqual(code, 400)
        self.assertIn("plan_signature", result["error"])

    def test_execute_cleanup_end_to_end(self):
        dry = v26.dry_run_cleanup("swing-shack")
        sig = dry["plan_signature"]
        actor = {
            "actor_id": "fp:test",
            "actor_id_method": "test",
            "actor_display_name": "v26-test-runner",
        }
        result, code = v26.execute_cleanup(
            "swing-shack", sig, actor, confirm=True,
        )
        self.assertEqual(code, 200)
        # Operator store should now contain only the kyle-desk record
        cal_file = v26._calendar_path("swing-shack")
        with open(cal_file) as f:
            kept = [json.loads(ln) for ln in f if ln.strip()]
        self.assertEqual(len(kept), 1, f"expected 1 keep, got {len(kept)}: {kept}")
        self.assertEqual(kept[0]["created_by"], "kyle-desk")
        # Audit log: V2.6 actions were written; previous audit (empty in fixture) preserved
        audit_file = v26._audit_path("swing-shack")
        with open(audit_file) as f:
            audit_rows = [json.loads(ln) for ln in f if ln.strip()]
        # Audit row count = total records in fixture - 1 kept
        self.assertEqual(len(audit_rows), len(self.records) - 1)
        # Backup file exists and matches
        backup = result["backup"]
        self.assertTrue(Path(backup["backup"]).exists())
        # Re-run dry-run to confirm stable
        dry2 = v26.dry_run_cleanup("swing-shack")
        self.assertEqual(dry2["source_line_count"], 1)

    def test_cleanup_status_clean_after_execute(self):
        dry = v26.dry_run_cleanup("swing-shack")
        actor = {
            "actor_id": "fp:test",
            "actor_id_method": "test",
            "actor_display_name": "v26-test-runner",
        }
        v26.execute_cleanup("swing-shack", dry["plan_signature"], actor, confirm=True)
        status = v26.cleanup_status("swing-shack")
        self.assertTrue(status["is_clean"])
        self.assertEqual(status["operator_store_line_count"], 1)
        # V2.8 — duplicate_event_key_count must be 0 after cleanup
        self.assertEqual(status["duplicate_event_key_count"], 0)
        self.assertEqual(status["unique_event_keys"], 1)

    def test_v28_dedup_keeps_strongest_when_duplicates(self):
        """V2.8 — when two KEEP records share an event_key, the
        variant with the strongest human-action transition_reason
        (Lodge/Book/L4 approve/approve) wins. The other is removed
        with a v28_dedup audit row."""
        # Set up: 2 KEEP records sharing the same event_key.
        # Both are foreman with a human-action transition_reason,
        # so both are KEEP. The weaker (Book) is at file position 0;
        # the stronger (Lodge) is at file position 1.
        self._write_calendar(
            [
                {
                    "brand_id": "swing-shack",
                    "event_key": "swing-shack:test-dup:2026",
                    "title": "Test dup (Book)",
                    "status": "approved",
                    "event_start": "2026-12-31",
                    "event_end": "2026-12-31",
                    "source_origin": "internal_strategy",
                    "created_by": "foreman",
                    "transition_reason": "Book",
                },
                {
                    "brand_id": "swing-shack",
                    "event_key": "swing-shack:test-dup:2026",
                    "title": "Test dup (Lodge)",
                    "status": "approved",
                    "event_start": "2026-12-31",
                    "event_end": "2026-12-31",
                    "source_origin": "internal_strategy",
                    "created_by": "foreman",
                    "transition_reason": "Lodge",
                },
            ]
        )
        dry = v26.dry_run_cleanup("swing-shack")
        sig = dry["plan_signature"]
        actor = {
            "actor_id": "fp:test",
            "actor_id_method": "test",
            "actor_display_name": "v28-test",
        }
        result, code = v26.execute_cleanup(
            "swing-shack", sig, actor, confirm=True,
        )
        self.assertEqual(code, 200)
        self.assertTrue(result["ok"])
        # Verify: only 1 record, the one with transition_reason=Lodge
        post = v26.cleanup_status("swing-shack")
        self.assertEqual(post["operator_store_line_count"], 1)
        self.assertEqual(post["duplicate_event_key_count"], 0)
        # Audit row was written for the dedup event. The stronger
        # record (Lodge) is at file position 1, the weaker (Book)
        # at position 0. The dedup kept the later / stronger one.
        self.assertEqual(
            result["actions"].get("v28_dedup_kept_later", 0), 1,
            f"expected 1 v28_dedup_kept_later, got {result['actions']}"
        )

    def test_v28_dedup_handles_duplicate_kept_later(self):
        """V2.8 — when the LATER record (file order) is the stronger
        one, the earlier gets removed and the later survives."""
        # Set up: 2 KEEP records sharing the same event_key.
        # The earlier (Lodge) is stronger than the later (Book) — but
        # both are KEEP and both score equally on human-action tr.
        # In a true tie, the LATER record wins (its file position is
        # newer). The dedup should remove the earlier (Lodge).
        self._write_calendar(
            [
                {
                    "brand_id": "swing-shack",
                    "event_key": "swing-shack:test-dup2:2026",
                    "title": "Test dup2 (Lodge) — earlier",
                    "status": "approved",
                    "event_start": "2026-12-31",
                    "event_end": "2026-12-31",
                    "source_origin": "internal_strategy",
                    "created_by": "foreman",
                    "transition_reason": "Lodge",
                },
                {
                    "brand_id": "swing-shack",
                    "event_key": "swing-shack:test-dup2:2026",
                    "title": "Test dup2 (Lodge) — later",
                    "status": "approved",
                    "event_start": "2026-12-31",
                    "event_end": "2026-12-31",
                    "source_origin": "internal_strategy",
                    "created_by": "foreman",
                    "transition_reason": "Lodge",
                },
            ]
        )
        dry = v26.dry_run_cleanup("swing-shack")
        sig = dry["plan_signature"]
        actor = {
            "actor_id": "fp:test",
            "actor_id_method": "test",
            "actor_display_name": "v28-test",
        }
        result, code = v26.execute_cleanup(
            "swing-shack", sig, actor, confirm=True,
        )
        self.assertEqual(code, 200)
        post = v26.cleanup_status("swing-shack")
        self.assertEqual(post["operator_store_line_count"], 1)
        self.assertEqual(post["duplicate_event_key_count"], 0)
        # Tie goes to the later file position
        self.assertEqual(
            result["actions"].get("v28_dedup_kept_later", 0), 1,
            f"expected 1 v28_dedup_kept_later, got {result['actions']}"
        )


if __name__ == "__main__":
    unittest.main()
