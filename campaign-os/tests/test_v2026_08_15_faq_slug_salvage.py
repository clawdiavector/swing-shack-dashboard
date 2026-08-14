"""v2026-08-15 — FAQ: salvage URL-slug rows whose slug is in the known map.

The blog_beast FAQ producer sometimes emits `target_keyword` as a sitemap
path (e.g. `/club-fitting/`, `/bookings/`, `/philosophy/`) and templates
that slug into every question, producing titles like "What is
/club-fitting/?". The previous renderer skipped those rows to avoid the
broken-looking output, but that hides 3 of 8 sets (37% of the FAQ corpus)
when the slug is one of the well-known website pages.

The fix: a small `_FAQ_SLUG_MAP` rewrites `target_keyword` AND every
question string for slugs we recognise. Unknown slugs still fall through
to the original "skipped" hint. A "N slug auto-fixed" counter credits
the salvage so Christelle can see the underlying health.

This test pins the new behavior so future regressions don't reintroduce
the "5x What is trackman golf? + 3 missing sets" wall.

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


class TestFAQsSalvageKnownUrlSlugs(unittest.TestCase):
    def setUp(self):
        self.html = _read(HTML_PATH)

    def _render_faqs_body(self):
        m = re.search(r"async function renderFAQs\(\)\{(.*?)\n\}", self.html, re.DOTALL)
        self.assertIsNotNone(m, "renderFAQs() function not found in HTML")
        return m.group(1)

    def test_slug_map_is_declared_at_top_level(self):
        # The known-slug map must live as a top-level const so the regex
        # and helper can share it (not duplicated inside renderFAQs).
        self.assertRegex(
            self.html,
            r"const\s+_FAQ_SLUG_MAP\s*=\s*\{",
            "_FAQ_SLUG_MAP must be declared as a top-level const so the "
            "salvage helper can share it across renders.",
        )

    def test_slug_map_includes_known_swingshack_slugs(self):
        # These are the slugs we have observed on swingshack.co.za that
        # blog_beast leaks. They MUST be in the map or those FAQ sets
        # stay hidden behind the "skipped" hint forever.
        body = self._render_faqs_body()
        m = re.search(r"const\s+_FAQ_SLUG_MAP\s*=\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(m, "Could not extract _FAQ_SLUG_MAP body")
        map_body = m.group(1)
        for required in ("/club-fitting/", "/bookings/", "/philosophy/"):
            self.assertIn(
                required,
                map_body,
                f"_FAQ_SLUG_MAP must include {required!r} so the corresponding "
                "FAQ sets render instead of being skipped.",
            )

    def test_salvage_helper_replaces_slug_in_target_keyword_and_questions(self):
        # The helper must rewrite both fields (target_keyword and every
        # question) and leave the cluster intact. A fix that only
        # rewrites target_keyword would still render "What is
        # /club-fitting/?".
        self.assertRegex(
            self.html,
            r"function\s+_faqSalvageSlugKeyword\s*\(",
            "_faqSalvageSlugKeyword helper must be declared.",
        )
        body = re.search(
            r"function\s+_faqSalvageSlugKeyword[^{]*\{(.*?)\n\}",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(body, "Could not extract _faqSalvageSlugKeyword body")
        hbody = body.group(1)
        self.assertIn(
            "target_keyword",
            hbody,
            "_faqSalvageSlugKeyword must rewrite target_keyword.",
        )
        self.assertIn(
            "questions",
            hbody,
            "_faqSalvageSlugKeyword must rewrite every question string.",
        )

    def test_renderfaqs_routes_known_slugs_through_salvage(self):
        # The URL-slug branch must call the salvage helper and fall
        # through to `stale.push` only when the helper returns null.
        body = self._render_faqs_body()
        self.assertIn(
            "_faqSalvageSlugKeyword",
            body,
            "renderFAQs() must invoke _faqSalvageSlugKeyword() inside the "
            "URL-slug branch.",
        )
        # The salvage branch should add to `seen` (rendered) and a
        # tracking `salvaged` array (so the count line can credit it).
        self.assertIn(
            "salvaged",
            body,
            "renderFAQs() must collect salvaged slugs so the count line "
            "can credit the auto-fix.",
        )

    def test_count_line_credits_salvaged_rows(self):
        # The small counter must surface the salvage count so the
        # underlying data health is visible ("N slug auto-fixed").
        body = self._render_faqs_body()
        self.assertRegex(
            body,
            r"slug auto-fixed",
            "renderFAQs() count line must mention 'slug auto-fixed' so "
            "Christelle can see the auto-fix is working.",
        )

    def test_existing_skip_hint_preserved(self):
        # Unknown slugs must STILL produce the "skipped" hint so the
        # data issue stays visible to the next agent run.
        body = self._render_faqs_body()
        self.assertRegex(
            body,
            r"skipped.*FAQ set|FAQ set.*skipped|target_keyword looks like",
            "renderFAQs() must still emit the 'skipped' hint for "
            "unrecognised URL slugs.",
        )

    def test_existing_dedup_contract_preserved(self):
        # The dedup key MUST still include cluster + target_keyword + first
        # question for BOTH the regular branch and the salvage branch, so
        # salvaged rows don't double-render alongside any pre-existing
        # matching row, and the existing test contract stays valid.
        body = self._render_faqs_body()
        keys = re.findall(r"const\s+key\s*=\s*`([^`]+)`", body)
        self.assertGreaterEqual(
            len(keys), 1,
            "renderFAQs() must build at least one dedup key from a template literal",
        )
        # Every dedup key must reference cluster (it.cluster OR fixed.cluster),
        # the keyword token (tk OR fixedTk), and the first-question token
        # (firstQ OR fixedFirstQ).
        for i, key_body in enumerate(keys):
            cluster_ref = "it.cluster" in key_body or "fixed.cluster" in key_body
            tk_ref = "tk" in key_body or "fixedTk" in key_body
            fq_ref = "firstQ" in key_body or "fixedFirstQ" in key_body
            self.assertTrue(
                cluster_ref,
                f"renderFAQs() dedup key #{i} must reference the cluster field. "
                f"Key body was: {key_body!r}",
            )
            self.assertTrue(
                tk_ref,
                f"renderFAQs() dedup key #{i} must reference the keyword token. "
                f"Key body was: {key_body!r}",
            )
            self.assertTrue(
                fq_ref,
                f"renderFAQs() dedup key #{i} must reference the first-question token. "
                f"Key body was: {key_body!r}",
            )

    def test_url_slug_regex_still_requires_both_slashes(self):
        # The strict URL-slug detector must NOT have been relaxed to
        # optional slashes (which would over-match real keywords).
        m = re.search(
            r"const\s+_FAQ_URL_SLUG_RE\s*=\s*(/\^[^;]+/\w*\s*);",
            self.html,
        )
        self.assertIsNotNone(m, "Could not extract _FAQ_URL_SLUG_RE assignment")
        assignment = m.group(1)
        escaped_slashes = assignment.count(r"\/")
        self.assertGreaterEqual(
            escaped_slashes, 2,
            "_FAQ_URL_SLUG_RE must still require BOTH leading and trailing slashes.",
        )


if __name__ == "__main__":
    unittest.main()
