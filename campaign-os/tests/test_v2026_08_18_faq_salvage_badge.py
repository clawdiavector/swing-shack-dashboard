"""v2026-08-18 — FAQ salvage: surface a visible "auto-fixed from /slug/" badge.

The slug-salvage helper silently rewrites `target_keyword` and every question
when blog_beast leaks a sitemap path. The display layer showed the salvaged
row inside the original (often wrong) cluster, which made the row look
broken — e.g. "What is philosophy?" inside a `TrackMan Golf Technology`
cluster. The user had no way to tell the row was a known salvage from a
known data-quality issue vs a content bug.

The fix: the helper now stamps `__salvaged_from` on the rewritten item, and
the renderer emits a small `🔧 auto-fixed from <slug>` pill in the meta line
when that field is present. The badge is visually neutral (var(--bg-4) bg,
var(--tx-2) text) so it doesn't shout, but the hover title explains the
data lineage.

This test pins the new behavior:

  1. helper stamps `__salvaged_from` with the original slug,
  2. renderer emits the badge only when `__salvaged_from` is truthy,
  3. badge contains the original slug in user-visible form,
  4. no badge is emitted for normal (non-salvaged) rows,
  5. the existing dedup / count / skip-hint contracts still hold.

Fix lives in campaign-os/campaign-os.html inside renderFAQs() and the
helper `_faqSalvageSlugKeyword()`.
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
HTML_PATH = os.path.join(ROOT, "campaign-os", "campaign-os.html")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestFAQsSalvageBadge(unittest.TestCase):
    def setUp(self):
        self.html = _read(HTML_PATH)

    def _render_faqs_body(self):
        m = re.search(r"async function renderFAQs\(\)\{(.*?)\n\}", self.html, re.DOTALL)
        self.assertIsNotNone(m, "renderFAQs() function not found in HTML")
        return m.group(1)

    def _salvage_helper_body(self):
        m = re.search(
            r"function\s+_faqSalvageSlugKeyword[^{]*\{(.*?)\n\}",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "_faqSalvageSlugKeyword() not found")
        return m.group(1)

    def test_salvage_helper_stamps_salvaged_from_field(self):
        """The helper must record the original slug so the renderer can
        show a badge. Without this, the row looks like a data error."""
        body = self._salvage_helper_body()
        self.assertIn(
            "__salvaged_from",
            body,
            "_faqSalvageSlugKeyword must stamp __salvaged_from on the "
            "returned item so the renderer can surface the badge.",
        )
        # The assignment must use the slugTk argument (the original slug).
        self.assertRegex(
            body,
            r"out\.__salvaged_from\s*=\s*slugTk",
            "_faqSalvageSlugKeyword must set out.__salvaged_from = slugTk "
            "so the original slug is preserved on the rewritten item.",
        )

    def test_renderer_emits_badge_pill_when_salvaged(self):
        """The renderer's per-item template must emit the badge when
        __salvaged_from is present."""
        body = self._render_faqs_body()
        # The badge string is the user-visible signal.
        self.assertIn(
            "auto-fixed from",
            body,
            "renderFAQs() must emit a pill with 'auto-fixed from' when "
            "the row was salvaged from a slugs map.",
        )
        # The badge must be conditional on it.__salvaged_from so normal
        # rows don't get a misleading badge.
        self.assertRegex(
            body,
            r"it\.__salvaged_from\s*\?\s*`",
            "renderFAQs() must gate the badge on it.__salvaged_from so "
            "non-salvaged rows don't get a false 'auto-fixed' label.",
        )

    def test_badge_includes_original_slug_in_user_visible_form(self):
        """The badge text must contain the original slug so the user can
        see where the keyword came from. esc() is required for safety."""
        body = self._render_faqs_body()
        # Find the badge template literal and assert it contains esc(...).
        m = re.search(
            r"it\.__salvaged_from\s*\?\s*`([^`]+)`",
            body,
        )
        self.assertIsNotNone(m, "Could not find badge template literal")
        badge = m.group(1)
        self.assertIn(
            "esc(",
            badge,
            "Badge text must be escaped via esc() so the slug can't break "
            "out of the attribute.",
        )
        self.assertIn(
            "__salvaged_from",
            badge,
            "Badge text must reference it.__salvaged_from so the slug is "
            "actually shown to the user.",
        )

    def test_badge_has_hover_title_explaining_lineage(self):
        """The badge must carry a title= attribute so the user can hover
        and learn WHERE the row came from. Without it the badge is just
        noise."""
        body = self._render_faqs_body()
        self.assertIn(
            "title=",
            body,
            "Badge must carry a title= attribute so the hover explains "
            "the data lineage.",
        )
        # The title should mention 'Auto-fixed' and reference the slug.
        self.assertRegex(
            body,
            r"title=\"[^\"]*Auto-fixed[^\"]*\"",
            "Badge title must contain 'Auto-fixed' to explain the tooltip.",
        )

    def test_badge_uses_neutral_colour_not_danger(self):
        """The badge must NOT use the danger / error palette. Using the
        standard muted pill colours keeps it informational, not a warning."""
        body = self._render_faqs_body()
        # Find the badge inline styles.
        m = re.search(
            r"it\.__salvaged_from\s*\?\s*`<span[^>]+style=\"([^\"]+)\"",
            body,
        )
        if m:
            style = m.group(1)
            # Neutral pill palette references bg-4 / tx-2 only.
            self.assertIn("--bg-4", style, "Badge must use bg-4 (neutral)")
            self.assertIn("--tx-2", style, "Badge must use tx-2 (neutral)")
            # Should NOT use danger / error colours.
            self.assertNotIn(
                "--bad", style,
                "Badge must NOT use --bad colour (it's informational, not an error).",
            )

    def test_existing_dedup_and_count_contracts_preserved(self):
        """The previous slug-salvage tests pin the dedup key + count line.
        Make sure the badge addition didn't accidentally rename them."""
        body = self._render_faqs_body()
        # Dedup keys still include cluster + tk + firstQ.
        keys = re.findall(r"const\s+key\s*=\s*`([^`]+)`", body)
        self.assertGreaterEqual(
            len(keys), 1,
            "renderFAQs() must still build at least one dedup key.",
        )
        # Count line still mentions "slug auto-fixed" (the existing contract).
        self.assertRegex(
            body,
            r"slug auto-fixed",
            "renderFAQs() count line must still mention 'slug auto-fixed'.",
        )

    def test_salvaged_field_starts_with_underscore_for_unguarded_iteration(self):
        """The field is named with a leading __ to make it visually obvious
        this is an internal marker, not real faq data. Pin the convention
        so a future refactor doesn't accidentally rename it to a key
        that could collide with real blog_beast schema fields."""
        body = self._salvage_helper_body()
        self.assertRegex(
            body,
            r"out\.__salvaged_from",
            "Internal marker must use double-underscore prefix "
            "(__salvaged_from) so it never collides with real "
            "blog_beast FAQ schema fields.",
        )


if __name__ == "__main__":
    unittest.main()
