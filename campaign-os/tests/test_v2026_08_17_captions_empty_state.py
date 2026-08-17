"""Regression test: Caption Studio "Generated variants" panel uses the new empty-state pattern.

Background:
    The 2026-08-14 db97278 commit taught the Headlines + CTAs generators to
    render a dashed `.empty-card` with icon + title + explanatory sub + a
    one-click mini-link CTA that triggers the existing Generate button.
    Before that fix, a marketer landing on either surface saw a tall blank
    card (the count pill in the header said "0" and the body was empty).

    The Captions surface was missed by that sweep: line 9603 still had
    `empty('cap-results', 'Pick a voice + tone, then click Generate');` —
    a single line of grey text with no title, no explanation, no CTA link.
    Anyone landing on Captions first hit the same dead-end UX the Headlines
    + CTAs fix solved.

    This commit closes that gap by wiring renderCaptions() into the same
    `_genEmptyState({kind:'fresh', primaryId:'cap-gen', ...})` pattern.
    On first render (when #cap-results has no `data-gen-state` attribute),
    it renders the new empty-card. After a successful generate, the
    handler at the cap-gen click listener sets `data-gen-state='filled'`
    so the empty-state is suppressed on subsequent renders.

This test asserts (10 assertions, all static-grep on campaign-os.html):
  1. The old bare-text empty call is gone.
  2. renderCaptions references _genEmptyState.
  3. The new empty-state points at primaryId: 'cap-gen' (the existing
     Generate button) so the inline CTA link fires the real handler.
  4. data-gen-state='filled' is set after a successful generate so a
     refresh keeps the batch (no re-blanking).
  5. The new copy mentions the user-controllable inputs (voice, tone,
     asset picker) so a first-time user knows what knobs to touch.
  6. The pattern matches Headlines + CTAs: same _genEmptyState helper,
     same data-gen-state flag, same shape.
  7. No em-dash in the new copy (standing rule).
  8. No fabricated stats (no fake counts, no fake engagement numbers).
  9. The CTA link's click handler still clicks #cap-gen (defensive).
  10. The empty-state contains the title "No captions generated yet" so a
      regression to the old "Pick a voice + tone…" copy is impossible.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"
HTML = HTML_PATH.read_text(encoding="utf-8")


def _window(marker: str, length: int = 3000) -> str:
    """Return the slice of HTML that starts at marker (anchored)."""
    idx = HTML.find(marker)
    assert idx >= 0, f"marker {marker!r} not found in campaign-os.html"
    return HTML[idx: idx + length]


class CaptionEmptyStateRegression(unittest.TestCase):
    """Lock in the Captions empty-state upgrade (mirrors db97278)."""

    # --- 1. The old bare-text empty call is gone -------------------------
    def test_01_old_bare_text_empty_call_removed(self):
        # The db97278 sweep missed captions — this string was the offender.
        self.assertNotIn(
            "empty('cap-results', 'Pick a voice + tone, then click Generate');",
            HTML,
            "Old bare-text empty('cap-results', 'Pick a voice + tone, ...') "
            "call must be replaced by _genEmptyState(...) — same as Headlines + CTAs.",
        )

    # --- 2. renderCaptions uses _genEmptyState -----------------------------
    def test_02_renderCaptions_uses_genEmptyState(self):
        window = _window("async function renderCaptions()")
        self.assertIn("_genEmptyState(", window,
                      "renderCaptions must wire into _genEmptyState helper.")

    # --- 3. The new empty-state points at the existing Generate button ---
    def test_03_empty_state_targets_cap_gen_button(self):
        window = _window("async function renderCaptions()")
        self.assertIn("primaryId: 'cap-gen'", window,
                      "Captions empty-state must point at primaryId 'cap-gen' "
                      "so the inline CTA link fires the real handler.")
        self.assertIn("primaryLabel: '⚡ Generate captions'", window,
                      "Captions empty-state must label the CTA with the "
                      "Generate-captions button label.")

    # --- 4. data-gen-state='filled' is set after a successful generate ----
    def test_04_filled_state_set_after_generate(self):
        window = _window("$('#cap-gen').addEventListener('click'")
        self.assertIn("$('#cap-results').dataset.genState = 'filled'", window,
                      "After a successful generate, cap-results.genState "
                      "must be 'filled' so the empty-state does not re-blank "
                      "a real batch on the next render.")

    # --- 5. New copy teaches the user-controllable inputs -----------------
    def test_05_empty_state_mentions_inputs(self):
        window = _window("async function renderCaptions()")
        for token in ("voice", "tone", "asset"):
            self.assertIn(token, window.lower(),
                          f"Captions empty-state copy must mention {token!r} "
                          "so a first-time user knows which input to touch.")

    # --- 6. Mirrors the Headlines + CTAs pattern -------------------------
    def test_06_matches_headlines_ctas_pattern(self):
        # Both empty-cards should:
        #   - set data-gen-state to 'empty' on first render
        #   - set data-gen-state to 'filled' after a successful generate
        #   - use the same _genEmptyState helper
        for sec, marker, primary_id in [
            ("captions", "async function renderCaptions()", "cap-gen"),
            ("headlines", "async function renderHeadlines()", "head-gen"),
            ("ctas",      "async function renderCTAs()",      "cta-gen"),
        ]:
            window = _window(marker)
            self.assertIn(".dataset.genState = 'empty'", window,
                          f"{sec} empty-state must mark itself empty on first render.")
            self.assertIn(f"primaryId: '{primary_id}'", window,
                          f"{sec} empty-state must wire to its generate button.")
            self.assertIn("_genEmptyState({", window,
                          f"{sec} empty-state must use the shared helper.")

    # --- 7. No em-dash in the new copy -----------------------------------
    def test_07_no_emdash_in_new_copy(self):
        window = _window("async function renderCaptions()")
        # Carve out: only the new empty-state copy inside renderCaptions.
        # Look for em-dash / en-dash only in user-visible prose we just added.
        # The new copy we added starts at "Generated caption variants land here"
        # and ends at "click Generate.".
        m = re.search(r"sub:\s*'([^']+)'", window)
        self.assertIsNotNone(m, "Captions empty-state must define a sub string.")
        sub = m.group(1)
        self.assertNotIn("\u2014", sub,
                         "No em-dash in new captions empty-state sub copy.")
        self.assertNotIn("\u2013", sub,
                         "No en-dash in new captions empty-state sub copy.")

    # --- 8. No fabricated stats -----------------------------------------
    def test_08_no_fabricated_stats(self):
        window = _window("async function renderCaptions()")
        # No fake counts (e.g. "+18% lift", "310% better") in the empty copy.
        m = re.search(r"sub:\s*'([^']+)'", window)
        sub = m.group(1) if m else ""
        for pattern in (r"\+\d+%\s*lift", r"\d+%\s*better", r"\d+x\s*avg",
                        r"avg\s*\d+", r"top\s*\d+"):
            self.assertNotRegex(sub, pattern,
                                f"No fabricated stat pattern {pattern!r} in empty-state copy.")

    # --- 9. The CTA link's click handler still clicks #cap-gen -----------
    def test_09_cta_link_fires_cap_gen(self):
        window = _window("async function renderCaptions()")
        # The inline CTA link uses an arrow-function handler: `(e) => { e.preventDefault(); $('#cap-gen')?.click(); ... }`
        # Defensive check: the handler must still trigger the existing #cap-gen click.
        self.assertIn("[data-gen-cta]", window,
                      "Captions empty-state must render a [data-gen-cta] anchor.")
        self.assertRegex(window,
                         r"#cap-results\s+\[data-gen-cta\][^}]*\$\('#cap-gen'\)\?\.click\(\)",
                         "Inline CTA link click handler must trigger $('#cap-gen').click().")

    # --- 10. Empty-state contains the new title ---------------------------
    def test_10_new_title_in_empty_state(self):
        window = _window("async function renderCaptions()")
        self.assertIn("title: 'No captions generated yet'", window,
                      "Captions empty-state must carry the new title "
                      "'No captions generated yet' so a regression to the "
                      "old bare-text copy is impossible.")


if __name__ == "__main__":
    unittest.main()