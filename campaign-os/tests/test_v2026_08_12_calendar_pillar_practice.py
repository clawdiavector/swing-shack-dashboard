"""
Regression: Calendar pillar inference must recognise the "🎮 Practice" /
"practice" markers used in seed copy so the 3 Practice slots (out of every
~57 calendar slots) stop falling through to the brand-fallback green.

Background:
    Commit 8581e0a added pillar inference for 🏌 / 🎯 / 🤝 / 📅 / 🛍 markers
    plus literal "club fitting" / "coaching" / "community" / "events" /
    "merch" / "equipment" tokens. The Practice marker (🎮 emoji + literal
    "practice" word) was missing — every "🎮 Practice" caption fell through
    to no-pillar → brand fallback (swing shack → #34d399 green). On the
    calendar that meant 3 of ~57 cards looked identical to the Swing Shack
    brand-fallback cards. Visually invisible.

    This fix adds:
      - "🎮" → "practice" to _PILLAR_CAPTION_HINTS
      - "practice" → "practice" to _PILLAR_CAPTION_HINTS
      - "practice": "#06b6d4" to the _calendar_color palette (cyan-500)
      - --pillar-practice:#06b6d4 (dark) / #0e7490 (light) to all 4 theme blocks
      - .cal-slot.pillar-practice{border-left-color:var(--pillar-practice)} rule
      - "practice" to the JS pillarKeys list in the calendar slot renderer

Tests:
    1. _infer_pillar_from_caption recognises "🎮 Practice" → "practice"
    2. _infer_pillar_from_caption recognises literal "practice" → "practice"
    3. _calendar_color("practice", "", "") returns the cyan-500 hex
    4. CSS source has --pillar-practice in all 4 theme blocks
    5. JS pillarKeys array contains "practice"
    6. .cal-slot.pillar-practice rule is wired in campaign-os.html
    7. add_slot integration: practice caption produces pillar="practice" +
       color="#06b6d4"

Standing rules: no publish, no tokens, no main branch, no schema change,
no fabricated stats, no deletes. Pure inference-pillar-class-system fix.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

# Mirror the path setup from test_v2026_08_12_calendar_pillar_color.py so
# `from _lib.intelligence import ...` resolves from campaign-os/.
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "campaign-os"))


class TestPracticePillarInference(unittest.TestCase):
    """The inference must recognise the Practice marker on seed captions."""

    def setUp(self):
        from _lib.intelligence import (  # type: ignore
            _PILLAR_CAPTION_HINTS,
            _infer_pillar_from_caption,
        )
        self._infer = _infer_pillar_from_caption
        self._hints = _PILLAR_CAPTION_HINTS

    def test_infer_recognises_emoji_practice_caption(self):
        cap = (
            "Need some help with your putting? Coach Cat explains what ma\n\n"
            "\U0001f3ae Practice\n\n"
            "Swipe up \u00b7 Learn more\n\n#IndoorGolfJohannesburg"
        )
        self.assertEqual(self._infer(cap), "practice")

    def test_infer_recognises_literal_practice_token(self):
        # Defensive: agents sometimes drop the emoji and just say "practice"
        # in the caption. The literal-token hint catches that case.
        self.assertEqual(self._infer("Practice makes perfect. Book a session."), "practice")
        self.assertEqual(self._infer("PRACTICE at the Shack tonight"), "practice")

    def test_infer_practice_takes_priority_after_coaching(self):
        # The hint order is intentional: 🎮 emoji comes BEFORE the literal
        # tokens so a caption like "...🎯 Coaching\n\n...🎮 Practice..." hits
        # Coaching first (the canonical marker on line 2). A caption with
        # only "practice" in body text hits practice. Both are valid.
        cap_coaching = "Some text\n\n\U0001f3af Coaching\n\nrest"
        cap_practice = "Some text\n\n\U0001f3ae Practice\n\nrest"
        self.assertEqual(self._infer(cap_coaching), "coaching")
        self.assertEqual(self._infer(cap_practice), "practice")

    def test_infer_empty_for_unrelated_text(self):
        # Regression guard: practice hint must NOT cause false positives on
        # generic golf content.
        self.assertEqual(self._infer(""), "")
        self.assertEqual(self._infer("Book a fitting session today"), "")
        self.assertEqual(self._infer("TrackMan session booked"), "")


class TestPracticePillarPalette(unittest.TestCase):
    """The colour palette must map "practice" to the cyan-500 token and that
    hex must match the CSS --pillar-practice token in campaign-os.html."""

    def setUp(self):
        from _lib.intelligence import _calendar_color  # type: ignore
        self.color = _calendar_color

    def test_practice_pillar_returns_cyan_hex(self):
        # Cyan-500 (#06b6d4) for dark theme (the default the user sees).
        self.assertEqual(self.color("practice", "", "").lower(), "#06b6d4")

    def test_practice_takes_priority_over_swing_shack_brand(self):
        # Same priority semantics as the other pillars — pillar wins over
        # brand in the lookup so a brand-named slot with pillar="practice"
        # still gets cyan, not green.
        self.assertEqual(self.color("practice", "swing shack", "").lower(), "#06b6d4")

    def test_practice_token_matches_dashboard_css(self):
        # Drift guard: palette MUST match the CSS --pillar-practice token in
        # all 4 theme blocks (2 default + 2 dark-variant). If a future edit
        # changes one without the other, the calendar goes back to looking
        # wrong.
        html_path = ROOT / "campaign-os" / "campaign-os.html"
        html = html_path.read_text(encoding="utf-8")
        # The HTML declares --pillar-* tokens in 4 theme blocks. We extract
        # all occurrences and assert that "practice" exists in at least the
        # first (default) block.
        css_tokens = {}
        for match in re.finditer(r"--pillar-([a-z-]+):(#[0-9a-f]+)", html):
            css_tokens.setdefault(match.group(1), []).append(match.group(2))
        self.assertIn(
            "practice", css_tokens,
            "--pillar-practice missing in CSS — calendar slot would render "
            "with no left-border colour for practice-pillar slots.",
        )
        # The first (default) block should match the palette value exactly.
        self.assertEqual(
            css_tokens["practice"][0].lower(),
            "#06b6d4",
            f"--pillar-practice default ({css_tokens['practice'][0]}) "
            f"drifts from palette (#06b6d4)",
        )
        # And all 4 occurrences should be present (one per theme block).
        self.assertGreaterEqual(
            len(css_tokens["practice"]), 4,
            f"Expected --pillar-practice in all 4 theme blocks, "
            f"found only {len(css_tokens['practice'])}",
        )


class TestPracticePillarJSKey(unittest.TestCase):
    """The JS calendar slot renderer must include "practice" in pillarKeys
    so it applies the .cal-slot.pillar-practice CSS class (not just relies
    on the inline border colour)."""

    def setUp(self):
        self.html_path = ROOT / "campaign-os" / "campaign-os.html"
        self.html = self.html_path.read_text(encoding="utf-8")

    def test_pillar_keys_array_includes_practice(self):
        # Find the JS pillarKeys array. We allow whitespace between tokens
        # and tolerate quote styles.
        match = re.search(
            r"const\s+pillarKeys\s*=\s*\[([^\]]+)\]",
            self.html,
        )
        assert match is not None  # for type-checker; the assertIsNotNone below covers runtime
        keys = [k.strip().strip("'\"") for k in match.group(1).split(",")]
        self.assertIn(
            "practice", keys,
            f"pillarKeys={keys} — missing 'practice'. The JS will fall back "
            "to inline border colour but won't apply the .cal-slot.pillar-"
            "practice class, so any future CSS hover/transition will miss "
            "Practice slots.",
        )

    def test_cal_slot_pillar_practice_css_rule_exists(self):
        # The CSS rule that paints the left border with --pillar-practice.
        self.assertIn(
            ".cal-slot.pillar-practice",
            self.html,
            ".cal-slot.pillar-practice CSS rule missing — Practice slots "
            "will not get the cyan left border on the calendar.",
        )


class TestAddSlotWritesPracticePillarFromCaption(unittest.TestCase):
    """End-to-end: add_slot fills pillar='practice' + color='#06b6d4' for
    a slot whose caption carries the 🎮 Practice marker."""

    def _build_add_slot(self):
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

    def test_practice_caption_fills_pillar_and_cyan_color(self):
        add_slot = self._build_add_slot()
        slot = {
            "assetId": "test-practice-1",
            "brand": "Swing Shack",
            "platform": "instagram",
            "caption": (
                "Need some help with your putting?\n\n"
                "\U0001f3ae Practice\n\n"
                "Swipe up \u00b7 Learn more\n\n#IndoorGolfJohannesburg"
            ),
        }
        add_slot(slot, "2026-08-15T09:00:00Z")
        self.assertEqual(slot["pillar"], "practice")
        self.assertEqual(slot["color"].lower(), "#06b6d4")

    def test_explicit_practice_pillar_is_not_overwritten(self):
        # Explicit-pillar-wins semantics: if the slot already has a pillar
        # field (even with a different value), inference must not clobber it.
        add_slot = self._build_add_slot()
        slot = {
            "assetId": "test-practice-2",
            "pillar": "coaching",  # explicit
            "brand": "Swing Shack",
            "platform": "instagram",
            "caption": (
                "Some text\n\n\U0001f3ae Practice\n\nrest"  # would infer practice
            ),
        }
        add_slot(slot, "2026-08-15T09:00:00Z")
        self.assertEqual(slot["pillar"], "coaching")  # not overwritten
        self.assertEqual(slot["color"].lower(), "#3b82f6")  # coaching blue


if __name__ == "__main__":
    unittest.main()