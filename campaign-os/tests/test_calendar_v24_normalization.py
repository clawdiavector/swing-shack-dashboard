"""
tests/test_calendar_v24_normalization.py — Calendar V2.4 normalizer
regression fixture.

Reproduces the production failure mode the V2.3 'default=str' workaround
masked, then proves the V2.4 _normalize_for_json() fix produces a strict
JSON-compatible value the normal Flask jsonify() path can serialise
WITHOUT default=str.

Run with:
    .venv/bin/python -m pytest campaign-os/tests/test_calendar_v24_normalization.py -v
or just:
    .venv/bin/python campaign-os/tests/test_calendar_v24_normalization.py
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import sys
import unittest
import uuid as _uuid
from pathlib import Path

# Make _lib + app importable
_here = Path(__file__).resolve()
_app_py = _here.parents[1] / "app.py"
sys.path.insert(0, str(_app_py.parent))

from app import _normalize_for_json  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Test fixtures — each is a minimal shape that has triggered SOME kind
# of JSON-encoding pain in production. We test against each.
# ──────────────────────────────────────────────────────────────────────

def _canonical_spine_event() -> dict:
    """Shape produced by data/brand-planning/swing-shack-events-2026.json"""
    return {
        "event_key": "swing-shack:alfred-dunhill-championship-2027:2027-02-25",
        "name": "Alfred Dunhill Championship 2027 (Durban Country Club)",
        "start": "2027-02-25",
        "end": "2027-02-28",
        "public_peak": "2027-02-28",
        "tier": "B-PIN",
        "geography": "Durban Country Club",
        "phases": [
            {"label": "PLAN", "task": "Brief + lanes", "weeks_before_peak": 4,
             "start": "2027-01-28", "end": "2027-02-11",
             "verified": False},
        ],
    }


def _operator_record_event() -> dict:
    """Shape produced by marketing_calendar.jsonl (operator-store)"""
    return {
        "event_key": "swing-shack:nedbank-golf-challenge:2026",
        "title": "Nedbank Golf Challenge 2026 (Sun City, 3-6 Dec)",
        "tier": "A-PIN",
        "event_start": "2026-12-03",
        "event_end": "2026-12-06",
        "source_origin": "external",
        "relevance_reason": "Africa's Major DP World Tour event at Sun City 3-6 Dec 2026.",
        "source_urls": ["https://www.nedbankgolfchallenge.com/"],
    }


def _missing_optional_fields_event() -> dict:
    """Edge case: record lacks every recommended field except event_key."""
    return {
        "event_key": "swing-shack:edge-case-a:2026",
        "title": "Edge case record A",
    }


def _null_optional_event() -> dict:
    """Edge case: record has explicit nulls for every recommended field."""
    return {
        "event_key": "swing-shack:edge-case-b:2026",
        "title": "Edge case record B",
        "tier": None,
        "event_start": None,
        "event_end": None,
        "public_peak": None,
        "source_url": None,
    }


def _mixed_legacy_current_event() -> dict:
    """Mixed shape — has both legacy (start/end) and current (event_start/event_end) names."""
    return {
        "event_key": "swing-shack:edge-case-c:2026",
        "title": "Edge case record C",
        "start": "2026-04-01",
        "end": "2026-04-05",
        "event_start": "2026-04-01",
        "event_end": "2026-04-05",
        "tier": "C-PIN",
    }


def _malformed_shape_event() -> dict:
    """Stress-case payload: Mixed-type dict keys.
    Reproduces the production V2.3 failure: json.dumps(..., sort_keys=True)
    crashes with TypeError "unsupported < between instances of...".
    """
    return {
        "event_key": "swing-shack:stress:2026",
        "title": "Stress shape",
        "tier": "B-PIN",
        "event_start": "2026-05-01",
        "event_end": "2026-05-04",
        # Mixed-type dict key — crashes json.dumps with sort_keys=True
        "score": {1: "first", "second": 2, _dt.date(2026, 1, 1): "marker"},
    }


def _malformed_with_datetime_event() -> dict:
    """Datetime-bearing record — Flask jsonify would choke on this without
    the V2.4 normaliser.
    """
    return {
        "event_key": "swing-shack:stress-dt:2026",
        "title": "Stress shape with datetime",
        "tier": "B-PIN",
        "event_start": "2026-05-01",
        "event_end": "2026-05-04",
        "audit": {
            "checked_at": _dt.datetime(2026, 5, 1, 12, 0, 0),
            "review_id": _uuid.uuid4(),
        },
    }


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────

class NormalizeForJsonTests(unittest.TestCase):
    """V2.4 — _normalize_for_json() must produce strict JSON-compatible
    output that Flask jsonify() can serialize WITHOUT default=str."""

    def test_canonical_spine_event(self):
        raw = _canonical_spine_event()
        out = _normalize_for_json(raw)
        body = json.dumps(out, sort_keys=True)
        self.assertIn("alfred-dunhill-championship-2027", body)
        # Phases are preserved as a list of dicts
        self.assertIsInstance(out["phases"], list)

    def test_operator_store_event(self):
        raw = _operator_record_event()
        out = _normalize_for_json(raw)
        body = json.dumps(out, sort_keys=True)
        self.assertIn("nedbank-golf-challenge", body)

    def test_missing_optional_fields(self):
        raw = _missing_optional_fields_event()
        out = _normalize_for_json(raw)
        # No fields missing should crash json.dumps
        json.dumps(out, sort_keys=True)

    def test_null_optional_fields(self):
        raw = _null_optional_event()
        out = _normalize_for_json(raw)
        body = json.dumps(out, sort_keys=True)
        # null → 'null' in JSON (with a leading space because sort_keys)
        # Use substring matches via re.
        import re
        self.assertRegex(body, r'"tier"\s*:\s*null')
        self.assertRegex(body, r'"event_start"\s*:\s*null')
        self.assertRegex(body, r'"event_end"\s*:\s*null')

    def test_mixed_legacy_current_event(self):
        raw = _mixed_legacy_current_event()
        out = _normalize_for_json(raw)
        body = json.dumps(out, sort_keys=True)
        # Both legacy start and current event_start are preserved.
        import re
        self.assertRegex(body, r'"event_start":\s*"2026-04-01"')
        self.assertRegex(body, r'"start":\s*"2026-04-01"')

    def test_malformed_shape_with_mixed_keys_does_not_crash_sort_keys(self):
        """THE V2.3 FAILURE REPRODUCTION.

        Before _normalize_for_json: json.dumps(..., sort_keys=True) on the
        raw record raises TypeError "'<' not supported between instances
        of 'str' and 'date'" because 'score' had a mixed-type key dict.

        After _normalize_for_json: keys are coerced to str → no crash.
        """
        raw = _malformed_shape_event()
        # Sanity: raw itself DOES crash with sort_keys=True on mixed keys
        with self.assertRaises(TypeError) as ctx:
            json.dumps(raw, sort_keys=True)
        self.assertIn("<", str(ctx.exception))
        # But normalized does NOT crash
        out = _normalize_for_json(raw)
        body = json.dumps(out, sort_keys=True)
        # All 'score' keys are now str
        score = json.loads(body)["score"]
        for k in score:
            self.assertIsInstance(k, str)

    def test_mixed_keys_with_uuid_datetime_via_normalize(self):
        """Pre-fix: json.dumps fails on raw for two reasons — mixed keys
        AND datetime/UUID values. Post-normalize: it succeeds.
        """
        raw = _malformed_with_datetime_event()
        # Pre-normalization: should fail
        with self.assertRaises(TypeError):
            json.dumps(raw, sort_keys=True, default=None)
        # Post-normalization: should pass
        out = _normalize_for_json(raw)
        body = json.dumps(out, sort_keys=True, default=None)
        self.assertIn("stress-dt:2026", body)
        # datetime → ISO string
        parsed = json.loads(body)
        self.assertEqual(parsed["audit"]["checked_at"], "2026-05-01T12:00:00")

    def test_no_datetime_or_set_or_uuid_remain_in_payload(self):
        """Strict invariant — no non-JSON-native types may survive normalise."""
        raw = {
            "a": _dt.datetime(2026, 1, 1),
            "b": {1, 2, 3},
            "c": _uuid.uuid4(),
            "d": {"nested": {"datetime": _dt.date(2026, 2, 2)}},
        }
        out = _normalize_for_json(raw)
        body = json.dumps(out, sort_keys=True)
        # Re-parse to walk the structure
        parsed = json.loads(body)
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v)
            elif isinstance(o, list):
                for it in o:
                    walk(it)
            else:
                self.assertIn(
                    type(o).__name__, {"str", "int", "float", "bool",
                                        "NoneType"},
                    f"unexpected type {type(o).__name__} survived _normalize_for_json"
                )
        walk(parsed)

    def test_no_default_str_used_in_serialization(self):
        """The whole point: Flask's normal jsonify() must work.

        We model Flask's normal path by calling json.dumps(... default=None)
        and asserting it succeeds on the normalised payload.
        """
        raw = _malformed_shape_event()
        out = _normalize_for_json(raw)
        body = json.dumps(out, sort_keys=True, default=None)
        self.assertIsInstance(body, str)
        parsed = json.loads(body)
        # Verify some known fields
        self.assertEqual(parsed["event_key"], "swing-shack:stress:2026")
        self.assertIn("score", parsed)

    def test_content_type_application_json_via_flask_jsonify(self):
        """Integration: pass the normalised payload to Flask jsonify()
        and assert the response has application/json content type.
        """
        from flask import Flask, jsonify
        app = Flask(__name__)
        with app.app_context():
            with app.test_request_context("/"):
                raw = _malformed_shape_event()
                out = _normalize_for_json(raw)
                resp = jsonify(out)
                self.assertIn(
                    "application/json",
                    resp.headers.get("Content-Type", "")
                )


# ──────────────────────────────────────────────────────────────────────
# End-to-end timeline-shape test that mirrors the production range-mode
# response.
# ──────────────────────────────────────────────────────────────────────

class TimelinePayloadTests(unittest.TestCase):
    """The timeline endpoint's shape must serialise cleanly via Flask's
    default jsonify() (sort_keys=True, default=None)."""

    def _simulated_timeline_payload(self):
        return {
            "ok": True,
            "brand_id": "swing-shack",
            "start": "2026-09-28",
            "end": "2027-09-28",
            "years": [2026, 2027],
            "always_on_pillars": [],
            "events": [
                _canonical_spine_event(),
                _operator_record_event(),
                _missing_optional_fields_event(),
                _null_optional_event(),
                _mixed_legacy_current_event(),
                _malformed_shape_event(),
            ],
            "tier_counts": {"A-PIN": 1, "B-PIN": 2, "C-PIN": 1},
            "source": "/app/campaign-os/../data/brand-planning/swing-shack-events-2026.json",
            "sources": [
                "/app/campaign-os/../data/brand-planning/swing-shack-events-2026.json",
                "marketing_calendar[swing-shack].jsonl",
            ],
            "canonical_store": {
                "seed": "data/brand-planning/<brand>-events-<YYYY>.json",
                "operator_approvals": "<DATA_DIR>/calendar/<brand>.jsonl",
                "audit": "<DATA_DIR>/calendar-audit/<brand>-approvals.jsonl",
            },
            "event_count": 6,
            "shopping_moment_count": 0,
            "mode": "range",
            "mc_read_error": None,
        }

    def test_full_timeline_payload_serialises_via_flask_jsonify(self):
        from flask import Flask, jsonify
        app = Flask(__name__)
        with app.app_context():
            with app.test_request_context("/"):
                payload = self._simulated_timeline_payload()
                # Pre-normalisation, the JSON path may crash (mixed keys).
                # Post-normalisation, never.
                normalised = _normalize_for_json(payload)
                resp = jsonify(normalised)
                self.assertIn("application/json",
                              resp.headers.get("Content-Type", ""))
                # Inspect the body
                body = resp.get_data(as_text=True)
                self.assertIn("swing-shack", body)
                self.assertIn("event_count", body)

    def test_full_timeline_payload_dumps_cleanly(self):
        payload = self._simulated_timeline_payload()
        normalised = _normalize_for_json(payload)
        body = json.dumps(normalised, sort_keys=True, default=None)
        parsed = json.loads(body)
        # 6 events survive
        self.assertEqual(parsed["event_count"], 6)
        self.assertEqual(len(parsed["events"]), 6)
        # All 'event_key' fields present
        for event in parsed["events"]:
            self.assertIn("event_key", event)


if __name__ == "__main__":
    unittest.main(verbosity=2)
