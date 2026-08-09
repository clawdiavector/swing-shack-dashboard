"""
Read-only regression test for Socials "Connect Instagram" CTA + status wording fix.

Background:
    The Socials section was rendering a wall of nothing when Meta Graph returned
    zero posts because Instagram wasn't wired. Status said "⚪ empty" (small white
    circle, almost invisible) and the empty card just said "No posts in the last
    90 days. Try widening the range." — misleading because widening the range
    doesn't help when Graph is genuinely disconnected.

Fix (2026-08-09 nightshift tick):
    1. Added #socials-connect-cta slot in sec-socials.
    2. renderSocials() now injects the "Connect Instagram" CTA when meta.sources.graph === 0.
    3. Status text now reads "🔌 not wired" (vs "⚪ empty" for legitimate quiet period).
    4. Empty card copy branches: explains widening-the-range won't help when not wired.

Tests:
    - All static-HTML checks (no server required). Read campaign-os.html once,
      run all assertions, exit 0 if all pass.
"""
import os
import re
import sys
import unittest

REPO = "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard"
HTML = os.path.join(REPO, "campaign-os", "campaign-os.html")


def _read():
    with open(HTML) as f:
        return f.read()


class TestSocialsConnectCta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read()

    def test_01_cta_slot_in_section(self):
        """sec-socials must have a #socials-connect-cta slot."""
        m = re.search(r'<section class="section" id="sec-socials">.*?</section>',
                      self.html, re.DOTALL)
        self.assertIsNotNone(m, "sec-socials section not found")
        section = m.group(0)
        self.assertIn('id="socials-connect-cta"', section,
                      "sec-socials must contain #socials-connect-cta slot")

    def test_02_render_socials_injects_cta(self):
        """renderSocials() must inject the CTA when graph is empty."""
        m = re.search(r'async function renderSocials\(\)\{.*?^\}', self.html,
                      re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(m, "renderSocials function not found")
        body = m.group(0)
        self.assertIn('#socials-connect-cta', body,
                      "renderSocials must reference #socials-connect-cta")
        self.assertIn('Connect Instagram', body,
                      "renderSocials must mention 'Connect Instagram'")
        # The branch condition: graph is 0 → inject
        self.assertIn('meta.sources.graph', body,
                      "renderSocials must check meta.sources.graph for emptiness")

    def test_03_status_label_has_not_wired(self):
        """Status text must branch on graphEmpty to show '🔌 not wired' vs '⚪ empty'."""
        m = re.search(r"status\.textContent = `\$\{meta\.newest.*?`;", self.html)
        self.assertIsNotNone(m, "status.textContent template literal not found")
        self.assertIn("🔌 not wired", m.group(0),
                      "status text must include '🔌 not wired' label")
        self.assertIn("⚪ empty", m.group(0),
                      "status text must preserve '⚪ empty' as fallback")

    def test_04_empty_card_branches_on_graph_empty(self):
        """Empty card copy must explain widening-the-range won't help when not wired."""
        # The new empty msg uses the graphEmpty ternary
        m = re.search(r"const emptyMsg = graphEmpty\s*\?\s*`.*?`\s*:\s*`.*?`;",
                      self.html, re.DOTALL)
        self.assertIsNotNone(m, "emptyMsg ternary with graphEmpty not found")
        self.assertIn("Connect Instagram", m.group(0),
                      "emptyMsg must reference the Connect Instagram card")
        self.assertIn("widening the range", m.group(0),
                      "emptyMsg must preserve 'widening the range' fallback")

    def test_05_ig_account_id_in_cta_body(self):
        """CTA body must surface IG + page IDs so the user knows which slot to fill."""
        m = re.search(r"const connectCta = `.*?`;", self.html, re.DOTALL)
        self.assertIsNotNone(m, "connectCta block not found")
        block = m.group(0)
        self.assertIn("IG business account", block,
                      "CTA must mention the IG business account id")
        self.assertIn("Facebook page", block,
                      "CTA must mention the Facebook page id")
        self.assertIn("setup-portal", block,
                      "CTA must point at the setup-portal flow")

    def test_06_cta_is_idempotent(self):
        """Repeated renderSocials() calls must not stack CTAs."""
        # The render code is plain innerHTML assignment (not +=), so idempotent
        # by construction. Verify the assignment pattern.
        self.assertRegex(self.html,
                         r"ctaEl\.innerHTML = graphEmpty \? connectCta : '';",
                         "CTA innerHTML must be a single ternary assignment, not append")

    def test_07_does_not_break_when_meta_undefined(self):
        """Defensive: if meta is missing or has no sources key, should not throw."""
        # The graphEmpty check uses `!meta.sources || (meta.sources.graph || 0) === 0`
        self.assertRegex(self.html,
                         r"!meta\.sources \|\| \(meta\.sources\.graph \|\| 0\) === 0",
                         "graphEmpty check must be defensive against missing meta.sources")

    def test_08_no_smart_quote_artifacts(self):
        """No \u201c \u201d \u2018 \u2019 in the new code."""
        # Find all lines in renderSocials after the change
        m = re.search(r"// graphEmpty = both Meta Graph.*?^\}", self.html,
                      re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(m, "renderSocials block not found after the change")
        block = m.group(0)
        for bad in ["\u201c", "\u201d", "\u2018", "\u2019"]:
            self.assertNotIn(bad, block,
                             f"renderSocials must not contain smart quote {bad!r}")

    def test_09_ask_heidi_button_uses_safe_window_alias(self):
        """The CTA buttons must use the (window.ASK_HEIDI_OPEN||alert) pattern (matches Performance CTA)."""
        cta_section = re.search(r"const connectCta = `.*?`;", self.html, re.DOTALL)
        self.assertIsNotNone(cta_section)
        block = cta_section.group(0)
        self.assertIn("window.ASK_HEIDI_OPEN||alert", block,
                      "CTA buttons must use ASK_HEIDI_OPEN||alert fallback")

    def test_10_does_not_collide_with_performance_cta(self):
        """The Socials CTA must be its own block — not a duplicate of perf-connect-cta."""
        self.assertIn("#socials-connect-cta", self.html)
        self.assertIn("#perf-connect-cta", self.html)
        # Both slots exist and are wired to their own injectors.
        # Each appears 2x: once as id="..." slot, once as $('#...') injector.
        self.assertEqual(self.html.count("socials-connect-cta"), 2,
                          "socials-connect-cta must appear exactly 2x (slot + lookup)")
        self.assertEqual(self.html.count("perf-connect-cta"), 2,
                          "perf-connect-cta must appear exactly 2x (slot + lookup)")


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2)[0]
    sys.exit(0 if result.wasSuccessful() else 1)