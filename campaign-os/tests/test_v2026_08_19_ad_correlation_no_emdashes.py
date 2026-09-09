"""
Regression test: no em-dashes in ad-correlation verdict strings.

Background:
    The Insights ad-correlation card renders one verdict per campaign, built
    server-side in campaign-os/_lib/insights_correlator.py. When Meta/Google
    spend + click data is missing, the old template filled the gap with the
    typographic em-dash '—' placeholder, and the rendered text appeared in
    every Insights tab page-load as 'spent — and drove — clicks to /'.

    That violated the standing rule "em dash banned in published copy" (the
    Insights tab is user-visible to anyone authenticated). It also rendered
    a raw `1.5` spend without a currency prefix, which read as a typo instead
    of Rands.

    Pre-fix (captured live on the deployed URL):
        Campaign 'Coach Cat takes us through a simple process on getting into '
        spent 1.5 and drove — clicks to /. GA4 shows 370 sessions on that
        page (clicks were 0.0% of sessions) - R0.0 per session.

Fix (2026-08-19 nightshift tick):
    spend_str   -> 'R{spend}' when present, 'unknown spend' otherwise.
    clicks_str  -> '{int(clicks)}' when present, 'unknown clicks' otherwise.
    The "tracking gap — low-traffic URL" em-dash became a mid-dot separator.
    The '- R{cps} per session' hyphen became a mid-dot separator too (the
    em-dash ban reads to typographic dashes in copy; mid-dot is the same
    separator pattern the rest of the dashboard uses).

    Post-fix (captured live):
        Campaign 'Coach Cat takes us through a simple process on getting into '
        spent R1.5 and drove 0 clicks to /. GA4 shows 370 sessions on that
        page (clicks were 0.0% of sessions) · R0.0 per session.

This test guards the fix by inspecting the verdict-building f-strings in
the correlator source and asserting:
  1. No em-dash literal inside any verdict f-string in the file.
  2. No ' or '—' fallback pattern for spend/clicks (the broken template).
  3. The spend format string includes the 'R' currency prefix.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "_lib" / "insights_correlator.py"


def _read() -> str:
    return SRC.read_text(encoding="utf-8")


class TestAdCorrelationNoEmdashes(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.src = _read()

    # ---- slice helpers -----------------------------------------------------

    def _verdict_block(self) -> str:
        """Return the body of _verdicts_for that contains the 3 verdict
        f-strings. We anchor on the unique comment '# Verdict string:' and
        walk forward to the closing 'verdicts.append({' so we don't pick up
        unrelated em-dashes (e.g. comments or docstrings elsewhere in file)."""
        m = re.search(r"# Verdict string:", self.src)
        assert m is not None, "'# Verdict string:' anchor not found"
        start = m.start()
        # Find the matching 'verdicts.append({' line — that's the block terminator
        end_m = re.search(r"verdicts\.append\(\{", self.src[start:])
        assert end_m is not None, "'verdicts.append({' terminator not found"
        return self.src[start:start + end_m.start()]

    # ---- test cases --------------------------------------------------------

    def test_01_no_emdash_literal_in_verdict_block(self) -> None:
        block = self._verdict_block()
        # The em-dash unicode char U+2014 must NOT appear inside the verdict
        # f-string block. (Other typographic dashes U+2013 en-dash are also
        # not present here but we focus on the explicit U+2014 ban.)
        self.assertNotIn(
            "\u2014",
            block,
            "ad-correlation verdict block still contains an em-dash literal "
            "(standing rule: no em-dash in published copy).",
        )

    def test_02_no_emdash_fallback_pattern(self) -> None:
        block = self._verdict_block()
        # The exact broken pattern was `f"... spent {spend or '—'} ..."`. Any
        # `or '—'` or `or "\u2014"` fallback is the template bug. Assert the
        # broken pattern is gone.
        self.assertNotIn(
            "or '\u2014'",
            block,
            "verdict f-string still uses `spend or '—'` fallback. Use "
            "`unknown spend` / `unknown clicks` placeholders instead.",
        )
        self.assertNotIn(
            'or "\u2014"',
            block,
            "verdict f-string still uses `spend or \"\u2014\"` fallback. Use "
            "`unknown spend` / `unknown clicks` placeholders instead.",
        )

    def test_03_spend_includes_currency_prefix(self) -> None:
        block = self._verdict_block()
        # The fix prefixes spend with R so a raw 1.5 can't be misread as a
        # typo. Look for the format string token that produces "R{...}".
        self.assertRegex(
            block,
            r"R\{spend\}",
            "spend format string must prefix with 'R' so the value reads as "
            "Rands, not a bare number. Found:\n" + block[:400],
        )

    def test_04_unknown_spend_placeholder_present(self) -> None:
        block = self._verdict_block()
        # When spend is missing the new template uses the word "unknown"
        # instead of an em-dash. This is the literal string the user sees.
        self.assertIn(
            "unknown spend",
            block,
            "missing-spend placeholder must be the word 'unknown spend' (so "
            "the Insights tab reads 'spent unknown spend' rather than "
            "'spent —').",
        )

    def test_05_unknown_clicks_placeholder_present(self) -> None:
        block = self._verdict_block()
        self.assertIn(
            "unknown clicks",
            block,
            "missing-clicks placeholder must be the word 'unknown clicks'.",
        )

    def test_06_tracking_gap_message_no_emdash(self) -> None:
        block = self._verdict_block()
        # The pre-fix line "GA4 has no data for that page yet — could be a
        # tracking gap or a low-traffic URL." must no longer contain an
        # em-dash. We assert the phrase "tracking gap or a low-traffic URL"
        # is present (kept) and that the surrounding block has no U+2014.
        self.assertIn(
            "tracking gap or a low-traffic URL",
            block,
            "the tracking-gap clause must be preserved (just without the "
            "em-dash).",
        )
        self.assertNotIn(
            "\u2014",
            block,
            "verdict block still has an em-dash after the tracking-gap fix.",
        )


if __name__ == "__main__":
    unittest.main()
