"""
Regression test for the Agents & health "System health" card data-sources block.

Bug: the system-health payload carries a `data_sources.sources` array of 15+
per-source entries (each with label, file, status FRESH/STALE/MISSING, age).
The previous renderer only showed the aggregate "9 source(s) older than 24h"
warning — Christelle had to open the API to find WHICH sources were stale or
missing.

Fix: systemHealthHtml() now renders the data_sources.sources array as a
scrollable list of compact rows. Each row carries the source label, the file
name (monospace, on hover), the human-readable age, and a colour-mapped
status pill (FRESH=green/on, STALE=amber/review, MISSING=red/blocked).
Sources are sorted FRESH → STALE → MISSING and the section header shows
"X total · Y fresh · Z stale · W missing".

This is a read-only regression test — it loads the HTML file as text and
asserts structural markers. Never imports flask, never hits a running server.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML = REPO / "campaign-os" / "campaign-os.html"


def _read() -> str:
    assert HTML.exists(), f"campaign-os.html missing at {HTML}"
    return HTML.read_text(encoding="utf-8")


def _function_body(src: str, fn_name: str) -> str:
    sig = f"function {fn_name}("
    i = src.find(sig)
    assert i >= 0, f"function {fn_name}() not found"
    brace_open = src.find("{", i)
    assert brace_open > 0, f"opening brace not found for {fn_name}()"
    depth = 0
    k = brace_open
    while k < len(src):
        ch = src[k]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[i : k + 1]
        k += 1
    raise AssertionError(f"closing brace not found for {fn_name}()")


class SystemHealthDataSourcesTests(unittest.TestCase):
    """Regression tests for the data_sources block in systemHealthHtml()."""

# ─── presence + structure ────────────────────────────────────────


    def test_data_sources_render_block_exists(self):
        """systemHealthHtml should now reference data_sources.sources."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        assert "data_sources" in body, (
            "Expected systemHealthHtml() to read h.data_sources.sources — "
            "this is the fix that turns the invisible per-source freshness "
            "list into a scrollable set of compact rows."
        )
        assert "sh-sources" in body, (
            "Expected systemHealthHtml() to emit .sh-sources container HTML."
        )


    def test_data_sources_sorts_fresh_first(self):
        """Sources should be sorted FRESH → STALE → MISSING so the worst
        land at the bottom and easy-to-skim."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        assert "FRESH: 0, STALE: 1, MISSING: 2" in body or (
            "FRESH" in body and "STALE" in body and "MISSING" in body and ".sort(" in body
        ), (
            "Expected a sort() ordering FRESH → STALE → MISSING in "
            "systemHealthHtml()."
        )


    def test_data_sources_renders_each_row(self):
        """Each source row should carry label + file + age + status pill."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        for marker in ("sh-source-label", "sh-source-file", "sh-source-age", "sh-source-row"):
            assert marker in body, f"Expected '{marker}' in systemHealthHtml()."


    def test_data_sources_status_pill_branches(self):
        """FRESH=on, STALE=review, MISSING=blocked pills must all be reachable."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        # All three branch kinds must appear in the row-rendering block.
        assert "pKind = 'on'" in body, "FRESH pill should map to kind='on'."
        assert "pKind = 'review'" in body, "STALE pill should map to kind='review'."
        assert "pKind = 'blocked'" in body, "MISSING pill should map to kind='blocked'."


    def test_data_sources_uses_esc_on_every_field(self):
        """All user-supplied source fields must be passed through esc()."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        # esc() calls must surround label, file, age_label, status
        for field in ("s.file", "s.label", "s.age_label"):
            assert f"esc({field}" in body, (
                f"Expected esc({field}) in systemHealthHtml() row renderer — "
                "user-supplied fields must be HTML-escaped."
            )


    def test_data_sources_capped_at_24(self):
        """The list must be capped to prevent runaway growth."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        assert "slice(0, 24)" in body, (
            "Expected sources.slice(0, 24) cap in systemHealthHtml()."
        )


    def test_data_sources_header_shows_counts(self):
        """The 'Data sources' header should show total + fresh + stale + missing."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        for marker in ("total", "fresh", "stale", "missing"):
            assert marker in body, f"Expected '{marker}' count in data-sources header."


# ─── CSS ──────────────────────────────────────────────────────────


    def test_sh_sources_css_block_exists(self):
        """CSS for .sh-sources, .sh-source-row, .sh-source-row.s-fresh/stale/missing."""
        src = _read()
        for cls in (".sh-sources", ".sh-source-row", ".sh-source-row.s-fresh",
                    ".sh-source-row.s-stale", ".sh-source-row.s-missing",
                    ".sh-source-label", ".sh-source-file", ".sh-source-age",
                    ".sh-sources-scroller", ".sh-sources-h"):
            assert cls in src, f"Expected CSS selector '{cls}' in campaign-os.html."


    def test_sh_sources_border_colors_use_theme_vars(self):
        """The colour-coded left borders should use theme CSS vars, not hardcoded hex."""
        src = _read()
        # The three colour rules must use the existing theme palette tokens.
        fresh_idx = src.find(".sh-source-row.s-fresh{")
        stale_idx = src.find(".sh-source-row.s-stale{")
        missing_idx = src.find(".sh-source-row.s-missing{")
        assert fresh_idx > 0 and stale_idx > 0 and missing_idx > 0, (
            "Expected three .sh-source-row.s-* CSS rules."
        )
        fresh_chunk = src[fresh_idx:fresh_idx + 80]
        stale_chunk = src[stale_idx:stale_idx + 80]
        missing_chunk = src[missing_idx:missing_idx + 80]
        assert "var(--ac)" in fresh_chunk, "FRESH border should use --ac (green)."
        assert "var(--yel)" in stale_chunk, "STALE border should use --yel (yellow)."
        assert "var(--red)" in missing_chunk, "MISSING border should use --red (red)."


    def test_no_em_dash_in_patched_block(self):
        """Standing rule: no em-dashes in published copy (use pipes/commas/colons)."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        # Comment block + row HTML
        assert "—" not in body, "No em-dash in systemHealthHtml() after the data-sources patch."


# ─── prior-lane non-regression ────────────────────────────────────


    def test_qa_warnings_still_rendered(self):
        """The qa_warnings block added by the previous tick must still be present."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        assert "qa_warnings" in body, "qa_warnings rendering must still exist."
        assert "sh-warn" in body, ".sh-warn CSS class must still be referenced."


    def test_data_status_pill_still_present(self):
        """The data_status pill rendering from the previous tick must still work."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        assert "h.data_status" in body, "data_status handling must remain."
        assert "Data</dt>" in body, "Data KV row must still render."


    def test_priority_pill_still_present(self):
        """The priority pill rendering from the previous tick must still work."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        assert "h.priority" in body, "priority handling must remain."


    def test_next_action_still_rendered(self):
        """The next_action one-liner must still render after the patch."""
        src = _read()
        body = _function_body(src, "systemHealthHtml")
        assert "sh-next" in body, ".sh-next block must still be present."
        assert "Next:</b>" in body, "Next: prefix must still render."


if __name__ == "__main__":
    unittest.main()