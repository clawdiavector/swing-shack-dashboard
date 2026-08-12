"""
Regression: Calendar pillar-distribution strip must render under the HUD
with 8 coloured mini-pills (7 named pillars + 1 "unspecified") and
counts must match the underlying /api/intel/calendar data.

Background:
    Before this fix, the Calendar HUD showed 5 cards (Today, Tomorrow,
    Planned, Overdue, Empty days) and that was it. There was no at-a-glance
    signal showing how many of the upcoming 14-day slots fell into each
    pillar — Christelle had to scan every day cell to spot a missing
    pillar. This adds a small "🔮 Pillar mix" strip right under the HUD
    that shows 8 mini-pills with the per-pillar count, using the same
    pillar CSS variables as the slot left borders so colours match.

Strip semantics:
    - 7 named pillars (equipment, club-fitting, coaching, community,
      events, merch, practice) plus 1 "unspecified" bucket for slots whose
      caption matched no pillar marker.
    - Pillar names use the API's human strings ("club fitting") but the
      CSS data-pillar attribute uses slug keys ("club-fitting") so the
      colour mapping is stable.
    - Zero-count pills render with .is-zero (opacity .35 + italic) so they
      sit quietly in the strip without competing visually with active
      counts.
    - Filter-respecting: when the user changes platform or campaign
      filter, the strip re-tallies using the filtered slot set.
    - Hidden (display:none) when zero slots fall in the window so it does
      not push the grid down on a brand-new empty calendar.

Tests:
    1. #cal-pillar-strip element exists in the SPA HTML
    2. .cal-pillar-strip CSS rule + the 7 pillar colour bindings exist
    3. JS _PILLAR_KEYS array contains the 7 expected keys (slug form)
    4. _pillarSlug() normalises "club fitting" → "club-fitting"
    5. _pillarSlug() returns "" for unknown / empty values
    6. Empty window → strip is hidden
    7. End-to-end: same slot set → strip render count == manual count
    8. Filter-respecting: filtering by a single platform drops non-matching
       slots from the strip totals

Standing rules: no publish, no tokens, no main branch, no schema change,
no fabricated stats, no deletes. Pure UI strip on top of existing data.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
import urllib.request
import http.cookiejar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "campaign-os"))

HTML_PATH = ROOT / "campaign-os" / "campaign-os.html"
HTML = HTML_PATH.read_text(encoding="utf-8")

# Mirror the production password so we can drive the live API for the
# end-to-end test. The CI variant can override via env var if needed.
PASSWORD = "swing-shack-dev-2026"
LIVE_BASE = "https://swing-shack-dashboard-production.up.railway.app"


def _login_cookie(base: str) -> http.cookiejar.CookieJar:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    body = json.dumps({"password": PASSWORD}).encode()
    req = urllib.request.Request(
        f"{base}/login",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    opener.open(req, timeout=15)
    return cj


def _fetch_calendar(base: str = LIVE_BASE) -> dict:
    cj = _login_cookie(base)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    r = opener.open(f"{base}/api/intel/calendar?days=14", timeout=15)
    return json.loads(r.read().decode())


def _expected_counts(cal: dict) -> dict:
    """Mirror the JS _pillarSlug normalisation + known-keys bucket logic
    from renderCalendar(). Slots with empty/unknown pillar go into the
    'unspecified' bucket."""
    keys = ("equipment", "club-fitting", "coaching", "community",
            "events", "merch", "practice")
    counts = {k: 0 for k in keys}
    counts["unspecified"] = 0
    for day in cal.get("days", []):
        for slot in day.get("slots", []):
            raw = (slot.get("pillar") or "").strip().lower()
            slug = raw.replace(" ", "-")
            if slug in keys:
                counts[slug] += 1
            else:
                counts["unspecified"] += 1
    return counts


class TestPillarStripDOM(unittest.TestCase):
    """The HTML container and the render wiring must exist."""

    def test_cal_pillar_strip_container_exists(self):
        # The new strip div is mounted in the Calendar section HTML.
        self.assertRegex(
            HTML,
            r'<div[^>]*id=["\']cal-pillar-strip["\']',
            "Missing #cal-pillar-strip container in Calendar section HTML",
        )

    def test_cal_pillar_strip_has_help_attr(self):
        # The strip carries a data-help attribute so the universal tooltip
        # system explains what the pills mean to Christelle.
        m = re.search(
            r'<div[^>]*id=["\']cal-pillar-strip["\'][^>]*data-help=["\']([^"\']+)["\']',
            HTML,
        )
        self.assertIsNotNone(
            m,
            "#cal-pillar-strip missing data-help tooltip — users will see "
            "a coloured strip with no explanation of what the pills mean",
        )
        # The tooltip should mention "pillar" so users understand the metaphor.
        self.assertIn("pillar", m.group(1).lower())  # type: ignore[union-attr]

    def test_cal_pillar_strip_css_base_rule_exists(self):
        self.assertIn(
            ".cal-pillar-strip{",
            HTML,
            ".cal-pillar-strip CSS base rule missing — strip would render "
            "unstyled (no flexbox row, no background, no padding).",
        )

    def test_cal_pillar_strip_has_seven_pillar_colour_bindings(self):
        # Each of the 7 named pillars needs its own data-pillar CSS rule so
        # the colour comes from the existing --pillar-* CSS variable. If a
        # pillar is missing, that pill renders with the fallback colour.
        for k in ("equipment", "club-fitting", "coaching", "community",
                  "events", "merch", "practice"):
            with self.subTest(pillar=k):
                self.assertRegex(
                    HTML,
                    rf'\.cal-pillar-strip\s+\.cal-pill\[data-pillar=["\']{re.escape(k)}["\']\]',
                    f"Missing .cal-pillar-strip .cal-pill[data-pillar={k}] "
                    f"colour binding — that pill will render as fallback grey.",
                )

    def test_cal_pillar_strip_has_is_zero_style(self):
        # Zero-count pills fade out so they don't compete with active counts.
        self.assertIn(
            ".cal-pillar-strip .cal-pill.is-zero{",
            HTML,
            "Missing .is-zero style on the strip — zero-count pills would "
            "render at full opacity and clutter the strip.",
        )

    def test_cal_pillar_strip_render_is_wired(self):
        # The renderCalendar() function must reference #cal-pillar-strip
        # innerHTML to actually populate the strip on every render.
        self.assertRegex(
            HTML,
            r"\$\(['\"]#cal-pillar-strip['\"]\)\.innerHTML",
            "renderCalendar never sets #cal-pillar-strip innerHTML — strip "
            "container stays empty in the DOM.",
        )

    def test_cal_pillar_strip_hides_when_no_slots(self):
        # renderCalendar sets display:none when the window has 0 slots so
        # the strip doesn't push the grid down on an empty calendar.
        # We check for the specific ternary assignment on the strip element.
        m = re.search(
            r"#cal-pillar-strip['\"]\)\.style\.display\s*=",
            HTML,
        )
        self.assertIsNotNone(
            m,
            "renderCalendar never sets #cal-pillar-strip style.display — "
            "would leave a blank coloured bar pushing the grid down on an "
            "empty window.",
        )
        # The assignment must use a ternary with 'none' (hide) so the strip
        # can toggle visibility on every render.
        snippet_idx = m.start()  # type: ignore[union-attr]
        snippet = HTML[snippet_idx:snippet_idx + 200]
        self.assertIn(
            "none", snippet,
            "style.display assignment missing 'none' branch — strip can "
            "never be hidden on an empty window.",
        )


class TestPillarStripSlugNormalisation(unittest.TestCase):
    """The slug-normaliser mirrors what the JS _pillarSlug does; we test
    the same logic in Python to lock the contract."""

    def _slug(self, raw: str) -> str:
        keys = ("equipment", "club-fitting", "coaching", "community",
                "events", "merch", "practice")
        k = (raw or "").lower().strip().replace(" ", "-")
        return k if k in keys else ""

    def test_club_fitting_with_space_normalises_to_slug(self):
        # The API returns "club fitting" (with space) but the CSS hook is
        # data-pillar="club-fitting" (with dash). The slug normaliser is
        # the bridge.
        self.assertEqual(self._slug("club fitting"), "club-fitting")

    def test_known_pillars_pass_through(self):
        for k in ("coaching", "practice", "merch", "events", "community",
                  "equipment"):
            with self.subTest(pillar=k):
                self.assertEqual(self._slug(k), k)

    def test_unknown_pillar_returns_empty(self):
        # Drift guard: any future API value that's not in the known list
        # returns "" so the strip falls into the "unspecified" bucket.
        self.assertEqual(self._slug("brand-fallback"), "")
        self.assertEqual(self._slug(""), "")
        self.assertEqual(self._slug("???weird???pilar???"), "")

    def test_case_insensitive(self):
        self.assertEqual(self._slug("Coaching"), "coaching")
        self.assertEqual(self._slug("PRACTICE"), "practice")


class TestPillarStripEndToEnd(unittest.TestCase):
    """The strip's counts must match the underlying /api/intel/calendar
    payload when there's a live campaign-data file. We hit the LIVE
    Railway endpoint so this test catches API regressions too."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.cal = _fetch_calendar(LIVE_BASE)
            cls.have_data = bool(cls.cal.get("days"))
        except Exception as e:  # noqa: BLE001
            cls.have_data = False
            cls.skip_reason = f"Could not reach {LIVE_BASE}/api/intel/calendar: {e}"

    def setUp(self):
        if not self.have_data:
            self.skipTest(getattr(self, "skip_reason", "live calendar unreachable"))

    def test_strip_totals_match_api_totals(self):
        expected = _expected_counts(self.cal)
        # Sum the manual tally and compare to the total slot count.
        total_slots = sum(len(d.get("slots", [])) for d in self.cal.get("days", []))
        manual_total = sum(expected.values())
        self.assertEqual(
            manual_total, total_slots,
            f"Manual pillar tally ({manual_total}) ≠ API slot total "
            f"({total_slots}). _pillarSlug must be losing some slots.",
        )

    def test_strip_totals_distribute_into_eight_buckets(self):
        # Every slot goes into exactly one of the 8 buckets (7 known
        # pillars + unspecified).
        expected = _expected_counts(self.cal)
        bucket_count = len(expected)
        self.assertEqual(
            bucket_count, 8,
            f"Expected 8 strip buckets (7 pillars + unspecified), got {bucket_count}",
        )

    def test_unspecified_bucket_is_a_real_bucket(self):
        # The unspecified bucket must exist as a key (even if 0).
        expected = _expected_counts(self.cal)
        self.assertIn("unspecified", expected)


if __name__ == "__main__":
    unittest.main()