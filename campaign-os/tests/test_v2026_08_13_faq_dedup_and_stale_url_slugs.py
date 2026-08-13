"""v2026-08-13 — FAQ tab: dedup identical rows + surface URL-slug target_keyword as a hint.

The blog_beast agent (the producer of /api/intel/faq_generator) emits two
visible failure shapes:

  1. Same FAQ set emitted N times in one run — 5 rows titled
     "What is trackman golf?" in a row look broken.
  2. target_keyword is sometimes a literal URL path (/bookings/,
     /club-fitting/, /philosophy/), which then gets templated into every
     question ("What is /bookings/?"). Looks like a render bug, but it's
     actually a stale seed leaking from the sitemap.

Fix contract:
  • renderFAQs() collapses duplicates by (cluster, target_keyword, first-question).
  • Items whose target_keyword looks like a URL slug are NOT rendered as
    question rows — they're listed in a one-line "skipped" hint so the
    underlying data issue stays visible.
  • A small "N unique · M duplicates collapsed" counter is shown above
    the list when duplicates exist.

The fix lives in campaign-os/campaign-os.html inside renderFAQs(). This
test pins the behavior so future regressions don't reintroduce the
"5x What is trackman golf?" wall.
"""

import os
import re
import sys
import unittest

# Make project root importable so we can locate the HTML file from anywhere.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
HTML_PATH = os.path.join(ROOT, "campaign-os", "campaign-os.html")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestFAQsDedupAndStaleUrlSlugs(unittest.TestCase):
    def setUp(self):
        self.html = _read(HTML_PATH)

    def _render_faqs_body(self):
        """Return the body of async function renderFAQs(){ ... }."""
        m = re.search(r"async function renderFAQs\(\)\{(.*?)\n\}", self.html, re.DOTALL)
        self.assertIsNotNone(m, "renderFAQs() function not found in HTML")
        return m.group(1)

    def test_dedup_key_includes_cluster_target_keyword_and_first_question(self):
        # The dedup key MUST collapse on cluster + target_keyword + first
        # question. Any narrower key (just title, just cluster) leaks dupes.
        # The implementation uses a template literal (`${...}${...}${...}`).
        # Look for all three references appearing together in the same
        # template literal assignment to `key`.
        body = self._render_faqs_body()
        m = re.search(r"const\s+key\s*=\s*`([^`]+)`", body)
        self.assertIsNotNone(
            m,
            "renderFAQs() must build the dedup key from a template literal "
            "assigned to a `key` variable.",
        )
        key_body = m.group(1)
        for token in ("it.cluster", "tk", "firstQ"):
            self.assertIn(
                token,
                key_body,
                f"renderFAQs() dedup key must include {token!r} so duplicate "
                f"FAQ sets actually collapse. Key body was: {key_body!r}",
            )

    def test_url_slug_regex_is_defined(self):
        # The URL-slug detector must exist as a top-level const so the
        # regex is shared (not duplicated inside renderFAQs).
        self.assertRegex(
            self.html,
            r"const\s+_FAQ_URL_SLUG_RE\s*=\s*/[^/]+/",
            "_FAQ_URL_SLUG_RE regex must be declared so renderFAQs() can "
            "filter target_keyword values that look like URL paths.",
        )

    def test_stale_topics_render_as_hint_not_as_question_rows(self):
        # We must NOT render `qs[0]` directly when the target_keyword is
        # a URL path AND the first question would also be polluted. The
        # renderFAQs() body must collect those into a `stale` array and
        # produce a "skipped" hint with the URL paths surfaced.
        body = self._render_faqs_body()
        self.assertIn(
            "stale",
            body,
            "renderFAQs() must collect URL-slug rows into a `stale` array "
            "rather than rendering 'What is /bookings/?' titles.",
        )
        self.assertRegex(
            body,
            r"skipped.*FAQ set|FAQ set.*skipped|target_keyword looks like",
            "renderFAQs() must emit a visible hint explaining the skipped "
            "rows so the data issue stays visible to the next agent run.",
        )

    def test_duplicate_counter_is_rendered_when_dupes_exist(self):
        body = self._render_faqs_body()
        self.assertRegex(
            body,
            r"duplicate[s']?\s+collapsed|collapsed",
            "renderFAQs() must show a small counter when duplicates are "
            "collapsed so Christelle can see the underlying health.",
        )

    def test_existing_title_and_meta_behavior_preserved(self):
        # The dedup + stale filter must NOT regress the existing contract:
        # title = it.questions[0] (or cluster), preview = remaining
        # questions, meta shows cluster + target_keyword + status pill.
        body = self._render_faqs_body()
        self.assertRegex(
            body,
            r"it\.questions(?:\s*\[\s*0\s*\]|\s*\.slice|\s*\.length|\s*\.filter)",
            "renderFAQs() still must read it.questions for the title.",
        )
        self.assertIn(
            "it.cluster",
            body,
            "renderFAQs() still must surface it.cluster in the meta row.",
        )
        self.assertIn(
            "it.target_keyword",
            body,
            "renderFAQs() still must surface it.target_keyword in the meta row.",
        )


if __name__ == "__main__":
    unittest.main()