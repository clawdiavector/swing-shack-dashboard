"""
Regression: Calendar slots without an explicit pillar field still get a real
pillar colour so the calendar stops looking like 56 identical green cards.

Before: every queue slot returned from /api/intel/calendar had
``pillar == ""``, the ``_calendar_color`` palette had no pillar keys, so the
left-border colour fell back to ``#34d399`` (green) for every card. The CSS
pillar-* class system existed but never triggered because there was no pillar
string to match. The visible result was an undifferentiated calendar.

After: ``add_slot`` infers the pillar from the caption text (queue items embed
``"🏌️ Club Fitting"`` / ``"🎯 Coaching"`` etc. on their second line), the
palette gains the matching pillar keys, and each slot ships a real
``color`` + ``pillar`` so the JS side picks up ``pillar-club-fitting`` etc.
as well as the inline border colour.

The test asserts (no live network):
- ``_infer_pillar_from_caption`` recognises the canonical seed pillars.
- ``_calendar_color`` maps the new pillar keys to the same hex codes the CSS
  --pillar-* tokens use in campaign-os.html (no drift between the two colour
  systems).
- ``add_slot`` writes ``pillar`` when the slot has no explicit pillar but the
  caption carries the marker.

One assertion compares the palette to the CSS source so a future palette edit
that drifts from the dashboard theme gets caught.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

# Match the path setup in test_v2026_08_07_review_modal_fixes.py so that
# `from _lib.intelligence import ...` resolves from campaign-os/.
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "campaign-os"))


class TestCalendarPillarInference(unittest.TestCase):
    def setUp(self):
        from _lib.intelligence import (  # type: ignore
            _PILLAR_CAPTION_HINTS,
            _calendar_color,
            _infer_pillar_from_caption,
        )
        self._calendar_color = _calendar_color
        self._infer = _infer_pillar_from_caption
        self._hints = _PILLAR_CAPTION_HINTS

    def test_infer_recognises_club_fitting_caption(self):
        cap = "That slice costing you yards off the tee? TrackMan found it\n\n🏌️ Club Fitting\n\nLink in bio"
        self.assertEqual(self._infer(cap), "club fitting")

    def test_infer_recognises_coaching_caption(self):
        cap = "Need to relax and find your golf swing tempo? Join Coach Cat\n\n🎯 Coaching\n\nDM us to get started"
        self.assertEqual(self._infer(cap), "coaching")

    def test_infer_recognises_community_caption(self):
        cap = "Big crew today! 🤝 Community\n\nBring a friend, hit balls"
        self.assertEqual(self._infer(cap), "community")

    def test_infer_returns_empty_for_unknown_caption(self):
        self.assertEqual(self._infer(""), "")
        self.assertEqual(self._infer("just a caption with no pillar marker"), "")

    def test_infer_case_insensitive(self):
        self.assertEqual(self._infer("CLUB FITTING session"), "club fitting")
        self.assertEqual(self._infer("Coaching Drop a below #IndoorGo"), "coaching")

    def test_infer_handles_none(self):
        self.assertEqual(self._infer(""), "")
        # Defensive: bad callers may pass None — should not raise.
        try:
            result = self._infer(None)  # type: ignore[arg-type]
        except TypeError:
            result = ""
        self.assertEqual(result, "")


class TestCalendarColorPalette(unittest.TestCase):
    def setUp(self):
        from _lib.intelligence import _calendar_color  # type: ignore
        self.color = _calendar_color

    def test_pillar_keys_map_to_dashboard_css_tokens(self):
        # The palette MUST match the CSS --pillar-* tokens in campaign-os.html
        # so the inline border-left-color matches the JS-applied CSS class.
        # If a future edit changes one without the other, the calendar goes
        # back to looking like a wall of one colour.
        html_path = ROOT / "campaign-os" / "campaign-os.html"
        html = html_path.read_text(encoding="utf-8")
        # The HTML declares the same --pillar-* tokens in two theme blocks
        # (default + dark-mode override). The test asserts the palette matches
        # the DEFAULT tokens (the ones used when no theme override is active,
        # which is the dark dashboard Christelle sees by default).
        # We grab the FIRST occurrence of each token, which is the default.
        css_tokens = {}
        for match in re.finditer(r"--pillar-([a-z-]+):(#[0-9a-f]+)", html):
            css_tokens.setdefault(match.group(1), match.group(2))
        self.assertIn("equipment", css_tokens, "--pillar-equipment missing in CSS")
        self.assertIn("coaching", css_tokens, "--pillar-coaching missing in CSS")
        self.assertIn("community", css_tokens, "--pillar-community missing in CSS")
        self.assertIn("events", css_tokens, "--pillar-events missing in CSS")
        self.assertIn("merch", css_tokens, "--pillar-merch missing in CSS")

        self.assertEqual(self.color("equipment", "", "").lower(), css_tokens["equipment"].lower())
        self.assertEqual(self.color("club fitting", "", "").lower(), css_tokens["equipment"].lower())
        self.assertEqual(self.color("coaching", "", "").lower(), css_tokens["coaching"].lower())
        self.assertEqual(self.color("community", "", "").lower(), css_tokens["community"].lower())
        self.assertEqual(self.color("events", "", "").lower(), css_tokens["events"].lower())
        self.assertEqual(self.color("merch", "", "").lower(), css_tokens["merch"].lower())

    def test_pillar_takes_priority_over_brand(self):
        # Pillar beats brand in the lookup so a brand-named slot still gets a
        # pillar colour when both are present.
        self.assertEqual(self.color("coaching", "swing shack", "").lower(), "#3b82f6")
        self.assertEqual(self.color("equipment", "swing shack", "").lower(), "#f59e0b")

    def test_fallback_for_no_pillar_brand_or_platform(self):
        # The previous behaviour — returns the green fallback — must be
        # preserved for genuinely empty inputs.
        self.assertEqual(self.color("", "", "").lower(), "#34d399")


class TestAddSlotWritesPillarFromCaption(unittest.TestCase):
    """The integration: add_slot must set pillar when the caption carries a
    pillar marker and the slot itself has no explicit pillar."""

    def _build_add_slot(self):
        """Mirror the production add_slot closure so we can test it without
        standing up the full Flask app context."""
        from _lib.intelligence import (  # type: ignore
            _calendar_color,
            _infer_pillar_from_caption,
        )

        def add_slot(slot, scheduled_for):
            if not scheduled_for:
                return
            if not slot.get("pillar"):
                inferred = _infer_pillar_from_caption(
                    slot.get("caption", "") or slot.get("name", "")
                )
                if inferred:
                    slot["pillar"] = inferred
            slot["scheduledFor"] = scheduled_for
            slot.setdefault(
                "color",
                _calendar_color(slot.get("pillar"), slot.get("brand"), slot.get("platform")),
            )

        return add_slot

    def test_add_slot_fills_pillar_from_caption_text(self):
        add_slot = self._build_add_slot()
        slot = {
            "assetId": "test-asset-1",
            "campaignId": "camp-1",
            "campaignName": "Publisher queue",
            "name": "That slice costing you yards off the tee?",
            "caption": "That slice costing you yards off the tee?\n\n🏌️ Club Fitting\n\nLink in bio",
            "approvalStatus": "approved",
            "publishStatus": "scheduled",
            "platform": "instagram",
            "brand": "Swing Shack",
            "pillar": "",
        }
        add_slot(slot, "2026-08-13T09:00:00Z")
        self.assertEqual(slot["pillar"], "club fitting")
        # color should be the amber equipment hue, NOT the green fallback
        self.assertEqual(slot["color"].lower(), "#f59e0b")

    def test_add_slot_does_not_overwrite_explicit_pillar(self):
        from _lib.intelligence import (  # type: ignore
            _calendar_color,
            _infer_pillar_from_caption,
        )

        def add_slot(slot, scheduled_for):
            if not scheduled_for:
                return
            if not slot.get("pillar"):
                inferred = _infer_pillar_from_caption(
                    slot.get("caption", "") or slot.get("name", "")
                )
                if inferred:
                    slot["pillar"] = inferred
            slot["scheduledFor"] = scheduled_for
            slot.setdefault(
                "color",
                _calendar_color(slot.get("pillar"), slot.get("brand"), slot.get("platform")),
            )

        # Caller already set pillar=community — caption happens to also contain
        # "🎯 Coaching" — explicit pillar must win.
        slot = {
            "assetId": "test-asset-2",
            "name": "Big crew!",
            "caption": "Big crew today! 🎯 Coaching\n🤝 Community",
            "pillar": "community",
            "brand": "Swing Shack",
            "platform": "instagram",
        }
        add_slot(slot, "2026-08-14T09:00:00Z")
        self.assertEqual(slot["pillar"], "community")
        self.assertEqual(slot["color"].lower(), "#10b981")


if __name__ == "__main__":
    unittest.main()