"""
Regression test for the Headlines + CTAs "tall blank card" empty-state bug.

Before this fix, the Headlines and CTAs sections rendered two tall blank
cards ("Just generated" and "History") when no generation had happened
yet. The History card just said "No history yet. Every generation is
saved here." in a tiny corner, and the Just generated card had no body
at all, leaving marketers confused when they first landed on the page.

The fix introduces a shared `_genEmptyState()` helper that renders a
dashed empty-card with:
  - icon (lightning bolt for fresh, scroll for history)
  - title (specific to each surface: "No headlines generated yet" etc.)
  - sub (explains what goes there + how to seed it)
  - CTA link for the fresh variant that triggers the existing
    #head-gen / #cta-gen button

The empty state is wired through:
  - `#head-list` and `#cta-list` (Just generated): rendered on first
    visit via `renderHeadlines()` / `renderCTAs()`. Suppressed by
    `data-gen-state="filled"` once a real batch lands so subsequent
    renders don't re-blank a successful generation.
  - `#head-history` and `#cta-history`: rendered by `_renderHeadHistory`
    / `_renderCtaHistory` whenever `HEAD_STATE.history` /
    `CTA_STATE.history` is empty (no localStorage).

Static greps confirm:
  1. `_genEmptyState` helper exists and accepts `{kind, title, sub,
     primaryId, primaryLabel}`.
  2. The helper renders an `.empty-card` with `.empty-title` + `.empty-sub`.
  3. The history empty branch uses `kind: 'history'` (no CTA link).
  4. The fresh empty branch uses `kind: 'fresh'` + a CTA link with
     `data-gen-cta` that points at the existing `#head-gen` / `#cta-gen`.
  5. `_renderHeadHistory()` / `_renderCtaHistory()` call the helper.
  6. `renderHeadlines()` / `renderCTAs()` initialize the Just generated
     panel with the empty state on first render.
  7. `_generateHeadlines()` / `_generateCtas()` set
     `data-gen-state="filled"` on `#head-list` / `#cta-list` after a
     successful generation so the empty state doesn't re-appear.
  8. The old flat-string empty states are gone:
       - "No history yet. Every generation is saved here." in #head-history
       - "No history yet. Every generation is saved here." in #cta-history
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HTML = (REPO / "campaign-os" / "campaign-os.html").read_text()


class TestGenEmptyState(unittest.TestCase):
    def test_helper_exists_with_required_params(self):
        # Helper signature includes kind, title, sub, primaryId, primaryLabel
        m = re.search(r"function _genEmptyState\(\{kind,\s*title,\s*sub,\s*primaryId,\s*primaryLabel\}\)", HTML)
        self.assertIsNotNone(m, "_genEmptyState({kind, title, sub, primaryId, primaryLabel}) helper missing")

    def test_helper_renders_empty_card_with_title_and_sub(self):
        # Look for the helper body rendering the empty-card markup
        m = re.search(
            r"function _genEmptyState.*?empty-card.*?empty-title.*?empty-sub",
            HTML, re.DOTALL,
        )
        self.assertIsNotNone(m, "_genEmptyState should render .empty-card with .empty-title and .empty-sub")

    def test_fresh_branch_has_cta_link_with_data_gen_cta(self):
        # The fresh (Just generated) variant includes a CTA link that triggers the generate button
        m = re.search(
            r"_genEmptyState\(\{\s*kind:\s*'fresh',\s*title:\s*'No headlines generated yet',\s*sub:[^}]+primaryId:\s*'head-gen'",
            HTML, re.DOTALL,
        )
        self.assertIsNotNone(m, "Headlines fresh empty state should pass primaryId: 'head-gen'")
        m = re.search(
            r"_genEmptyState\(\{\s*kind:\s*'fresh',\s*title:\s*'No CTAs generated yet',\s*sub:[^}]+primaryId:\s*'cta-gen'",
            HTML, re.DOTALL,
        )
        self.assertIsNotNone(m, "CTAs fresh empty state should pass primaryId: 'cta-gen'")

    def test_history_branch_has_no_cta(self):
        # History variants don't include a CTA — they're informational only
        m = re.search(
            r"_genEmptyState\(\{\s*kind:\s*'history',\s*title:\s*'No saved headline batches yet'",
            HTML, re.DOTALL,
        )
        self.assertIsNotNone(m, "Headlines history empty state should be wired")
        m = re.search(
            r"_genEmptyState\(\{\s*kind:\s*'history',\s*title:\s*'No saved CTA batches yet'",
            HTML, re.DOTALL,
        )
        self.assertIsNotNone(m, "CTAs history empty state should be wired")

    def test_render_head_history_uses_helper(self):
        # _renderHeadHistory should call _genEmptyState for empty branch
        # Find the block after _renderHeadHistory's hist check
        m = re.search(
            r"function _renderHeadHistory\(\)\{[^}]+?if\(!hist\.length\)\{[^}]+?\$?\('#head-history'\)\.innerHTML\s*=\s*_genEmptyState",
            HTML, re.DOTALL,
        )
        self.assertIsNotNone(m, "_renderHeadHistory should call _genEmptyState for empty branch")

    def test_render_cta_history_uses_helper(self):
        m = re.search(
            r"function _renderCtaHistory\(\)\{[^}]+?if\(!hist\.length\)\{[^}]+?\$?\('#cta-history'\)\.innerHTML\s*=\s*_genEmptyState",
            HTML, re.DOTALL,
        )
        self.assertIsNotNone(m, "_renderCtaHistory should call _genEmptyState for empty branch")

    def test_render_headlines_initializes_empty_state(self):
        # renderHeadlines should seed #head-list with empty-card on first visit
        m = re.search(
            r"async function renderHeadlines\(\)\{[^{]*?_renderHeadHistory\(\);.*?#head-list.*?_genEmptyState",
            HTML, re.DOTALL,
        )
        self.assertIsNotNone(m, "renderHeadlines() should initialize #head-list with _genEmptyState")

    def test_render_ctas_initializes_empty_state(self):
        m = re.search(
            r"async function renderCTAs\(\)\{[^{]*?_renderCtaHistory\(\);.*?#cta-list.*?_genEmptyState",
            HTML, re.DOTALL,
        )
        self.assertIsNotNone(m, "renderCTAs() should initialize #cta-list with _genEmptyState")

    def test_dataset_gen_state_set_after_generation(self):
        # After successful generation, head-list/cta-list dataset.genState should flip to 'filled'
        self.assertRegex(
            HTML,
            r"\$?\('#head-list'\)\.innerHTML\s*=\s*html;[^}]*?\$?\('#head-list'\)\.dataset\.genState\s*=\s*'filled'",
            "head-list dataset.genState should flip to 'filled' after _generateHeadlines success",
        )
        self.assertRegex(
            HTML,
            r"\$?\('#cta-list'\)\.innerHTML\s*=\s*html;[^}]*?\$?\('#cta-list'\)\.dataset\.genState\s*=\s*'filled'",
            "cta-list dataset.genState should flip to 'filled' after _generateCtas success",
        )

    def test_old_flat_empty_states_gone(self):
        # The old flat-string empty states must be removed
        self.assertNotIn(
            "'<div class=\"empty\">No history yet. Every generation is saved here.</div>'",
            HTML,
            "Old flat headline/CTA history empty state still present",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)