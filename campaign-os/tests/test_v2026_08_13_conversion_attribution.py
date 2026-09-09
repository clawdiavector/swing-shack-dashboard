"""v2026-08-13: weekly_report conversion-truth attribution wire.

The CMO brain requires knowing which content/hook actually moves the
financial needle, not just which got likes. The conversion-truth engine
(scripts/run_conversion_truth_engine.js) reclassifies every revenue source
into a confidence band (DIRECT / STRONG_PROXY / WEAK_PROXY / UNMEASURABLE)
based on whether the GA4 booking confirmation event is live.

This test pins the wire: weekly_report() must surface roi-truth.json +
booking-events.json as 4 claims (1 verdict + 1 unblocker + 1 LOOK_AT
unmeasurable + 1 GA4 events inventory) and list them in sources_used.
"""
import json
import os
import sys
import tempfile
import unittest


REPO = "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard"


def _run_weekly_report_with_data(roi: dict, bookings: dict) -> dict:
    """Invoke weekly_report() against a tempdir containing only roi-truth.json
    + booking-events.json, so the test stays deterministic regardless of
    what's on disk right now.
    """
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, "roi-truth.json"), "w") as f:
        json.dump(roi, f)
    with open(os.path.join(tmp, "booking-events.json"), "w") as f:
        json.dump(bookings, f)
    os.environ["DATA_DIR"] = tmp
    # Force reload of the module so DATA_DIR takes effect.
    for mod in list(sys.modules.keys()):
        if "intelligence" in mod or "_lib" in mod:
            del sys.modules[mod]
    sys.path.insert(0, os.path.join(REPO, "campaign-os"))
    try:
        from _lib import intelligence as intel_mod  # type: ignore
        return intel_mod.weekly_report(brand="swing-shack")
    finally:
        os.environ.pop("DATA_DIR", None)


def _sample_roi():
    return {
        "schema": "https://clawdia.io/agents/roi-truth-engine/v1",
        "generated": "2026-04-23T10:54:50.186Z",
        "summary": {
            "total": 8,
            "direct": 1,
            "strong_proxy": 3,
            "weak_proxy": 2,
            "unmeasurable": 2,
            "verdict": "Publishing ROI is STRONG_PROXY. Lead and ad ROI is UNMEASURABLE. Only DIRECT comes when GA4 booking system integrates.",
        },
        "sources": [
            {"source": "low_risk_publish", "can_measure": "STRONG_PROXY", "name": "Low-Risk Publishing"},
            {"source": "lead_routing", "can_measure": "UNMEASURABLE", "name": "Lead Routing"},
            {"source": "tiny_ad_shift", "can_measure": "UNMEASURABLE", "name": "Budget Shifts"},
        ],
        "recommendations": [
            {
                "priority": 1, "source": "lead_routing", "name": "Lead Routing",
                "action": "WhatsApp Business API + CRM integration",
                "why": "Cannot prove ROI without this integration",
            },
            {
                "priority": 1, "source": "tiny_ad_shift", "name": "Budget Shifts",
                "action": "Meta Ads API + GA4 goal tracking",
                "why": "Cannot prove ROI without this integration",
            },
        ],
        "blockers": {},
    }


def _sample_bookings():
    return {
        "schema": "https://clawdia.io/agents/booking-events/v1",
        "generated": "2026-04-23T10:54:50.000Z",
        "events": [
            {"event_id": "form_submit", "current_measurable": True, "priority": 2, "description": "form submission"},
            {"event_id": "booking_completed", "current_measurable": False, "priority": 1, "description": "booking confirmation"},
            {"event_id": "service_selected", "current_measurable": True, "priority": 2, "description": "service chosen"},
        ],
        "summary": {"measurable": 2, "total": 3, "priority_one_unmeasured": 1},
    }


class ConversionAttributionWireTests(unittest.TestCase):
    """Test the new conversion-truth attribution block in weekly_report()."""

    def test_roi_truth_appears_in_sources_used(self):
        result = _run_weekly_report_with_data(_sample_roi(), _sample_bookings())
        interp = result.get("interpretation") or result.get("interp") or {}
        sources = interp.get("sources_used", [])
        self.assertIn(
            "roi-truth.json", sources,
            "weekly_report must list roi-truth.json in sources_used "
            "so the audit trail shows the conversion-truth wire is live.",
        )
        self.assertIn(
            "booking-events.json", sources,
            "weekly_report must list booking-events.json in sources_used "
            "so the GA4 booking event inventory is auditable.",
        )

    def test_conversion_truth_verdict_claim_fires(self):
        result = _run_weekly_report_with_data(_sample_roi(), _sample_bookings())
        interp = result.get("interpretation") or result.get("interp") or {}
        attribution = [c for c in interp.get("whats_working", []) if c.get("category") == "attribution"]
        # Should have at least the verdict claim + unblocker claim.
        self.assertGreaterEqual(
            len(attribution), 1,
            "Expected at least 1 attribution claim in whats_working; "
            f"got {len(attribution)}",
        )
        verdict_claim = next(
            (c for c in attribution if "Conversion truth band" in c.get("claim", "")),
            None,
        )
        self.assertIsNotNone(
            verdict_claim,
            "Expected the 'Conversion truth band' headline claim to fire",
        )
        # The verdict must quote the engine summary verbatim.
        self.assertIn("STRONG_PROXY", verdict_claim["claim"])
        self.assertIn("UNMEASURABLE", verdict_claim["claim"])
        # The claim must cite the source so audit trail is intact.
        self.assertEqual(verdict_claim["source"], "roi-truth.json")

    def test_unblocker_claim_fires_with_priority_1_recs(self):
        result = _run_weekly_report_with_data(_sample_roi(), _sample_bookings())
        interp = result.get("interpretation") or result.get("interp") or {}
        attribution = [c for c in interp.get("whats_working", []) if c.get("category") == "attribution"]
        unblocker = next(
            (c for c in attribution if "Top attribution unblocker" in c.get("claim", "")),
            None,
        )
        self.assertIsNotNone(unblocker, "Expected the unblocker claim to fire")
        # Both priority-1 names should appear.
        self.assertIn("Lead Routing", unblocker["claim"])
        self.assertIn("Budget Shifts", unblocker["claim"])

    def test_unmeasurable_sources_surface_as_look_at(self):
        result = _run_weekly_report_with_data(_sample_roi(), _sample_bookings())
        interp = result.get("interpretation") or result.get("interp") or {}
        look_at = interp.get("look_at", [])
        unmeasurable_look_at = [
            c for c in look_at if c.get("category") == "attribution"
        ]
        self.assertEqual(
            len(unmeasurable_look_at), 1,
            f"Expected exactly 1 attribution LOOK_AT (the unmeasurable-count claim); got {len(unmeasurable_look_at)}",
        )
        # The count must reflect the number of UNMEASURABLE sources.
        self.assertIn("2", unmeasurable_look_at[0]["claim"])
        self.assertIn("Lead Routing", unmeasurable_look_at[0]["claim"])
        self.assertIn("Budget Shifts", unmeasurable_look_at[0]["claim"])

    def test_ga4_booking_events_inventory_fires(self):
        result = _run_weekly_report_with_data(_sample_roi(), _sample_bookings())
        interp = result.get("interpretation") or result.get("interp") or {}
        attribution = [c for c in interp.get("whats_working", []) if c.get("category") == "attribution"]
        events_claim = next(
            (c for c in attribution if "GA4 booking events" in c.get("claim", "")),
            None,
        )
        self.assertIsNotNone(events_claim, "Expected GA4 booking events inventory claim")
        # Fixture has 3 events with 2 measurable, priority-1 unmeasured = booking_completed.
        # Pin exact format so a future rewording doesn't silently drop the metric.
        self.assertIn("2 of 3 measurable", events_claim["claim"])
        self.assertIn("booking_completed", events_claim["claim"])

    def test_block_does_not_crash_when_files_missing(self):
        """If roi-truth.json and booking-events.json are both absent,
        the wire must silently contribute nothing - no crash, no fake claims.
        """
        # The module reads DATA_DIR via _runtime_data_file() which honours
        # the env var, falling back to the bundled REPO_ROOT/data. To force
        # a true "files missing" state, monkey-patch the runtime helper
        # itself to return None for these two files.
        for mod in list(sys.modules.keys()):
            if "intelligence" in mod or "_lib" in mod:
                del sys.modules[mod]
        sys.path.insert(0, os.path.join(REPO, "campaign-os"))
        from _lib import intelligence as intel_mod  # type: ignore

        orig_runtime = intel_mod._runtime_data_file

        def _patched(name):
            if name in ("roi-truth.json", "booking-events.json"):
                return f"/nonexistent/{name}"
            return orig_runtime(name)

        intel_mod._runtime_data_file = _patched
        try:
            result = intel_mod.weekly_report(brand="swing-shack")
            interp = result.get("interpretation") or result.get("interp") or {}
            sources = interp.get("sources_used", [])
            self.assertNotIn("roi-truth.json", sources)
            self.assertNotIn("booking-events.json", sources)
            attribution = [
                c for c in interp.get("whats_working", [])
                if c.get("category") == "attribution"
            ]
            self.assertEqual(
                len(attribution), 0,
                f"Wire should contribute nothing when files are missing, "
                f"got {len(attribution)} fake attribution claims",
            )
        finally:
            intel_mod._runtime_data_file = orig_runtime


class ConversionAttributionOnDiskTests(unittest.TestCase):
    """Smoke test: the actual on-disk roi-truth.json + booking-events.json
    files exist and have the shape weekly_report() reads. Catches the case
    where someone deletes / corrupts the data file without realizing the
    CMO band wire depends on it.
    """

    def test_roi_truth_on_disk_has_required_keys(self):
        path = os.path.join(REPO, "data", "roi-truth.json")
        self.assertTrue(os.path.exists(path), f"missing: {path}")
        d = json.load(open(path))
        self.assertIn("summary", d)
        self.assertIn("sources", d)
        self.assertIn("recommendations", d)
        self.assertIn("verdict", d["summary"])

    def test_booking_events_on_disk_has_required_keys(self):
        path = os.path.join(REPO, "data", "booking-events.json")
        self.assertTrue(os.path.exists(path), f"missing: {path}")
        d = json.load(open(path))
        self.assertIn("events", d)
        self.assertIn("summary", d)


if __name__ == "__main__":
    unittest.main()
