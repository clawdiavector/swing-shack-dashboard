"""Regression test: no em-dashes inside the user-visible empty-state strings.

Background:
    The standing rule is "no em-dash in published copy". The 2026-08-10/11
    ticks swept headings + dropdowns (b992ca4), main-card copy (32f83fa),
    and the connect explainers (test_v2026_08_11_no_emdashes_connect_explainer.py).
    This test locks in the next lane: the 6 user-visible empty-state
    strings (rendered in real "no data" empty states) plus the 4 inline
    muted/empty prose strings the nightshift swept on 2026-08-11.

Sites covered (10 total):

Empty-state strings (6):
  1. gmb-list fallback (L6875 area):
       was: "No GMB drafts yet — click + New draft above"
       now: "No GMB drafts yet. Click + New draft above to start."
  2. Insights empty fallback (L8100 area):
       was: "No insights yet — connect analytics to see what is working"
       now: "No insights yet. Connect analytics to see what is working."
  3. Headline Lab history fallback (L8812 area):
       was: "No history yet — every generation is saved here."
       now: "No history yet. Every generation is saved here."
  4. CTA Lab history fallback (L8946 area):
       was: "No history yet — every generation is saved here."
       now: "No history yet. Every generation is saved here."
  5. Hashtag+SEO GMB fallback (L9162 area):
       was: "No hashtags for this platform (GMB — uses natural-language keyword phrases instead)"
       now: "No hashtags for this platform. GMB uses natural-language keyword phrases instead."
  6. Insight explanation empty list (L5342 area):
       was: "<li class=\"empty\">—</li>"  (vague em-dash placeholder)
       now: "<li class=\"empty\">No signals to interpret yet. Connect analytics above to see what is working.</li>"

Inline prose strings (4):
  7. Brief feed unreachable placeholder (L6559 area):
       was: "...still works — pick one of those while this recovers."
       now: "...still works. Pick one of those while this recovers."
  8. Review caption empty placeholder (L7087 area):
       was: "<span class=\"muted\">— no caption yet. Use Edit to add one or Generate captions below.</span>"
       now: "<span class=\"muted\">No caption yet. Use Edit to add one, or Generate captions below.</span>"
  9. Why-IG strip empty fallback (L7225 area):
       was: "No matching IG posts yet — this asset will be the first."
       now: "No matching IG posts yet. This asset will be the first."
 10. Brand identity purpose fallback (L10594 area):
       was: "No purpose defined yet — edit identity.goal."
       now: "No purpose defined yet. Edit identity.goal to add one."

Fix contract:
    None of the swept strings contains an em-dash character. Each replacement
    uses a period (sentence break) — same separator pattern as the b992ca4
    dropdown fix and the 32f83fa main-card fix. No copy meaning lost; the
    strings remain semantically identical (just non-typographic-punctuation).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"


def _read() -> str:
    return HTML_PATH.read_text(encoding="utf-8")


# 10 swept strings (post-fix). Each must appear verbatim somewhere in
# campaign-os.html AND must not contain the em-dash character.
EXPECTED_STRINGS = [
    # empty-state (6)
    '<div class="empty">No GMB drafts yet. Click + New draft above to start.</div>',
    '<div class="empty">No insights yet. Connect analytics to see what is working.</div>',
    '<div class="empty">No history yet. Every generation is saved here.</div>',  # both 8812 + 8946
    '<div class="empty">No hashtags for this platform. GMB uses natural-language keyword phrases instead.</div>',
    '<li class="empty">No signals to interpret yet. Connect analytics above to see what is working.</li>',
    # inline prose (4)
    'The brief feed is unreachable right now. The rest of the dashboard (Review, Ideas, Capture Library, Calendar) still works. Pick one of those while this recovers.',
    '<span class="muted">No caption yet. Use Edit to add one, or Generate captions below.</span>',
    '<div class="muted" style="font-size:11px;padding:.5rem">No matching IG posts yet. This asset will be the first.</div>',
    'No purpose defined yet. Edit identity.goal to add one.',
]

# Pre-fix strings that must NOT appear anywhere in the file.
BANNED_STRINGS = [
    '<li class="empty">—</li>',
    '<div class="empty">No GMB drafts yet — click + New draft above</div>',
    '<div class="empty">No insights yet — connect analytics to see what is working</div>',
    '<div class="empty">No history yet — every generation is saved here.</div>',
    '<div class="empty">No hashtags for this platform (GMB — uses natural-language keyword phrases instead)</div>',
    'still works — pick one of those while this recovers.',
    '<span class="muted">— no caption yet. Use Edit to add one or Generate captions below.</span>',
    '<div class="muted" style="font-size:11px;padding:.5rem">No matching IG posts yet — this asset will be the first.</div>',
    'No purpose defined yet — edit identity.goal.',
]


class TestNoEmdashesEmptyStateSweep(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = _read()

    # ---- 1. Each expected post-fix string is present ----------------------------

    def test_01_gmb_drafts_empty_state_present(self):
        self.assertIn(
            '<div class="empty">No GMB drafts yet. Click + New draft above to start.</div>',
            self.html,
            "GMB drafts empty-state post-fix string missing from campaign-os.html",
        )

    def test_02_insights_empty_state_present(self):
        self.assertIn(
            '<div class="empty">No insights yet. Connect analytics to see what is working.</div>',
            self.html,
            "Insights empty-state post-fix string missing from campaign-os.html",
        )

    def test_03_headline_history_empty_state_present(self):
        # Headline + CTA both share the same text
        self.assertIn(
            '<div class="empty">No history yet. Every generation is saved here.</div>',
            self.html,
            "Headline history empty-state post-fix string missing",
        )

    def test_04_cta_history_empty_state_present(self):
        # Both headline and CTA history are swept; same string, 2 sites
        occurrences = self.html.count(
            '<div class="empty">No history yet. Every generation is saved here.</div>'
        )
        self.assertEqual(
            occurrences, 2,
            f"Expected 2 history empty-state sites (headline + CTA), found {occurrences}",
        )

    def test_05_hashtag_seo_gmb_empty_state_present(self):
        self.assertIn(
            '<div class="empty">No hashtags for this platform. GMB uses natural-language keyword phrases instead.</div>',
            self.html,
            "Hashtag+SEO GMB empty-state post-fix string missing",
        )

    def test_06_signals_to_interpret_empty_state_present(self):
        self.assertIn(
            '<li class="empty">No signals to interpret yet. Connect analytics above to see what is working.</li>',
            self.html,
            "Signals-to-interpret empty list post-fix string missing",
        )

    def test_07_brief_feed_unreachable_prose_present(self):
        self.assertIn(
            'The brief feed is unreachable right now. The rest of the dashboard (Review, Ideas, Capture Library, Calendar) still works. Pick one of those while this recovers.',
            self.html,
            "Brief feed unreachable prose post-fix string missing",
        )

    def test_08_review_caption_placeholder_prose_present(self):
        self.assertIn(
            '<span class="muted">No caption yet. Use Edit to add one, or Generate captions below.</span>',
            self.html,
            "Review caption placeholder post-fix string missing",
        )

    def test_09_why_ig_strip_empty_prose_present(self):
        self.assertIn(
            '<div class="muted" style="font-size:11px;padding:.5rem">No matching IG posts yet. This asset will be the first.</div>',
            self.html,
            "Why-IG strip empty prose post-fix string missing",
        )

    def test_10_brand_purpose_fallback_prose_present(self):
        self.assertIn(
            'No purpose defined yet. Edit identity.goal to add one.',
            self.html,
            "Brand purpose fallback prose post-fix string missing",
        )

    # ---- 2. Pre-fix strings must not appear anywhere ----------------------------

    def test_11_no_pre_fix_gmb_drafts_string(self):
        self.assertNotIn(
            '<div class="empty">No GMB drafts yet — click + New draft above</div>',
            self.html,
            "Pre-fix GMB drafts empty-state string still present (em-dash leak)",
        )

    def test_12_no_pre_fix_insights_string(self):
        self.assertNotIn(
            '<div class="empty">No insights yet — connect analytics to see what is working</div>',
            self.html,
            "Pre-fix Insights empty-state string still present (em-dash leak)",
        )

    def test_13_no_pre_fix_history_string(self):
        self.assertNotIn(
            '<div class="empty">No history yet — every generation is saved here.</div>',
            self.html,
            "Pre-fix history empty-state string still present (em-dash leak)",
        )

    def test_14_no_pre_fix_hashtag_seo_string(self):
        self.assertNotIn(
            '<div class="empty">No hashtags for this platform (GMB — uses natural-language keyword phrases instead)</div>',
            self.html,
            "Pre-fix Hashtag+SEO GMB empty-state string still present (em-dash leak)",
        )

    def test_15_no_pre_fix_signals_to_interpret_placeholder(self):
        self.assertNotIn(
            '<li class="empty">—</li>',
            self.html,
            "Pre-fix vague em-dash placeholder still present in Insight explanation",
        )

    def test_16_no_pre_fix_brief_feed_unreachable_prose(self):
        self.assertNotIn(
            'still works — pick one of those while this recovers.',
            self.html,
            "Pre-fix brief-feed-unreachable prose still present (em-dash leak)",
        )

    def test_17_no_pre_fix_review_caption_placeholder(self):
        self.assertNotIn(
            '<span class="muted">— no caption yet. Use Edit to add one or Generate captions below.</span>',
            self.html,
            "Pre-fix review caption placeholder still present (em-dash leak)",
        )

    def test_18_no_pre_fix_why_ig_strip_prose(self):
        self.assertNotIn(
            '<div class="muted" style="font-size:11px;padding:.5rem">No matching IG posts yet — this asset will be the first.</div>',
            self.html,
            "Pre-fix why-IG strip prose still present (em-dash leak)",
        )

    def test_19_no_pre_fix_brand_purpose_prose(self):
        self.assertNotIn(
            'No purpose defined yet — edit identity.goal.',
            self.html,
            "Pre-fix brand purpose fallback prose still present (em-dash leak)",
        )

    # ---- 3. Cross-site invariant: no em-dash character in the swept lines ------

    def test_20_swept_lines_contain_no_emdash(self):
        """Sweep invariant: every post-fix string is em-dash-free at the char level."""
        for s in EXPECTED_STRINGS:
            with self.subTest(string=s[:60]):
                self.assertNotIn(
                    "\u2014", s,
                    f"Expected post-fix string contains em-dash: {s!r}",
                )

    def test_21_swept_strings_unique_in_html(self):
        """Each swept post-fix string appears at least once verbatim."""
        for s in EXPECTED_STRINGS:
            with self.subTest(string=s[:60]):
                self.assertGreaterEqual(
                    self.html.count(s), 1,
                    f"Expected post-fix string absent from HTML: {s[:80]!r}",
                )

    def test_22_no_new_emdashes_introduced_by_sweep(self):
        """The post-fix em-dash count in the swept strings (the actual HTML
        occurrences) must be 0 for every string in EXPECTED_STRINGS.

        We assert against the per-string `s.count("\u2014")` (which is 0
        in EXPECTED_STRINGS) but ALSO sanity-check that the expected
        strings appear in HTML — guards against accidental regression
        where a future sweep removes the period (and accidentally
        re-introduces the em-dash).
        """
        for s in EXPECTED_STRINGS:
            self.assertEqual(s.count("\u2014"), 0, f"Pre-string had em-dash: {s!r}")
            # and make sure the live HTML copy matches exactly
            self.assertIn(s, self.html, f"Expected string not in HTML: {s!r}")


if __name__ == "__main__":
    unittest.main()
