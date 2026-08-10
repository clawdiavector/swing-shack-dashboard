"""Regression tests for the 2026-08-10 home-page brief-loading-skeleton fix.

Bug: The Home (Brief) page showed a raw "Loading…" string in two prominent
places for several seconds on every first paint:
  - the "Do this right now" recommendation card body
  - the right-rail Today ticker
  - a stray em-dash placeholder (`—`) in the recommendation-rationale and
    today-rail-ts spans

On a fresh load, the brief feeds take a few seconds to land. Before this fix
the user saw what looked like a broken page: dry "Loading…" text and em-dash
placeholders, no skeleton, no hint that data was on the way. Christelle's
#1 used surface looked broken on every visit.

Fix: Replace the dry placeholders with friendly skeletons that use the
existing `.skeleton` shimmer (defined at line 511 in the CSS) plus a short
status string ("Picking today's highest-leverage action…", "Pulling live
signals…"). The skeletons are in static HTML, so they paint with the first
response and get replaced wholesale when `renderBrief()` populates the
elements. No JS changes are needed — the existing renderTodayRail() and
recommendation-body assignments already do `el.innerHTML = ...` and
`textContent = ...`, which clear the skeletons.

This test asserts:
  1. The static "Loading recommendation…" string is gone from the
     brief-recommendation-body initial markup.
  2. A skeleton block now lives inside the brief-recommendation-body.
  3. The static "Loading…" string in today-rail-list is gone.
  4. Skeleton cards now live in the today-rail-list initial markup.
  5. The em-dash placeholders in the rationale and today-rail-ts are gone
     (replaced with informative text).
  6. The matching CSS for .rail-skel-card and .brief-rec-skel exists.
  7. The renderBrief() path still replaces these (sanity check — make sure
     the fix didn't accidentally also touch the JS to remove the replacement).
"""
from __future__ import annotations
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPA = REPO / "campaign-os" / "campaign-os.html"


class HomeBriefLoadingSkeletonTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.html = SPA.read_text(encoding="utf-8")

    # 1. Brief recommendation body: no more "Loading recommendation…"
    def test_no_loading_recommendation_string(self):
        self.assertNotIn("Loading recommendation…", self.html,
                         "Static 'Loading recommendation…' placeholder is gone — should be a skeleton")

    # 2. Brief recommendation body: contains a skeleton
    def test_brief_recommendation_body_has_skeleton(self):
        m = re.search(
            r'<div id="brief-recommendation-body">(.*?)</div>\s*\n\s*</div>',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "Could not find brief-recommendation-body block")
        body = m.group(1)
        self.assertIn('class="brief-rec-skel"', body,
                      "brief-recommendation-body must contain the brief-rec-skel skeleton wrapper")
        self.assertIn('class="skeleton"', body,
                      "brief-rec-skel must contain at least one .skeleton bar")

    # 3. Today rail list: no more "Loading…" placeholder
    def test_today_rail_no_loading_text(self):
        # Match the static <div class="muted">Loading…</div> placeholder
        self.assertNotIn(
            '<div id="today-rail-list"><div class="muted">Loading…</div></div>',
            self.html,
        )

    # 4. Today rail list: contains skeleton cards
    def test_today_rail_has_skeleton_cards(self):
        m = re.search(
            r'<div id="today-rail-list">(.*?)</div>\s*\n\s*</aside>',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "Could not find today-rail-list block")
        body = m.group(1)
        self.assertIn("rail-skel-card", body,
                      "today-rail-list must contain at least one .rail-skel-card")
        self.assertIn("Pulling live signals", body,
                      "today-rail-list should include a 'Pulling live signals…' hint")

    # 5. Em-dash placeholders removed from home-page rationale + ts
    def test_no_dash_placeholders_in_brief_or_today(self):
        # Span #brief-recommendation-rationale should not start with `—`
        m = re.search(
            r'<span class="muted" id="brief-recommendation-rationale"[^>]*>(.*?)</span>',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "brief-recommendation-rationale span not found")
        self.assertNotIn("—", m.group(1),
                         "brief-recommendation-rationale should not contain em-dash placeholder")
        # Span #today-rail-ts should not start with `—`
        m2 = re.search(
            r'<span class="muted" id="today-rail-ts"[^>]*>(.*?)</span>',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m2, "today-rail-ts span not found")
        self.assertNotIn("—", m2.group(1),
                         "today-rail-ts should not contain em-dash placeholder")

    # 6. CSS exists
    def test_skeleton_css_classes_exist(self):
        self.assertIn(".rail-skel-card{", self.html,
                      "Missing .rail-skel-card CSS rule")
        self.assertIn(".brief-rec-skel{", self.html,
                      "Missing .brief-rec-skel CSS rule")

    # 7. renderBrief() and renderTodayRail() still replace the body
    #    (sanity — we did not accidentally neuter the replacement).
    def test_render_still_replaces_skeleton_containers(self):
        # renderTodayRail() must do el.innerHTML = `...` (skeleton wipe)
        self.assertRegex(
            self.html,
            r"async function renderTodayRail\(\)\{[\s\S]{0,400}el\.innerHTML\s*=",
            "renderTodayRail() no longer overwrites the rail HTML",
        )
        # brief-recommendation-body must be assigned somewhere in renderBrief
        self.assertRegex(
            self.html,
            r"bodyEl\.innerHTML\s*=",
            "brief-recommendation-body is no longer assigned by renderBrief()",
        )
        # brief-recommendation-rationale must be assigned
        self.assertRegex(
            self.html,
            r"rationaleEl\.textContent\s*=",
            "brief-recommendation-rationale is no longer assigned by renderBrief()",
        )

    # 8. No new em-dashes leaked into the new copy
    def test_no_new_em_dashes_in_new_strings(self):
        new_strings = [
            "Picking today's highest-leverage action…",
            "Pulling live signals…",
        ]
        for s in new_strings:
            self.assertNotIn("—", s, f"em-dash leaked into new copy: {s!r}")
            self.assertNotIn("–", s, f"en-dash leaked into new copy: {s!r}")


if __name__ == "__main__":
    unittest.main()
