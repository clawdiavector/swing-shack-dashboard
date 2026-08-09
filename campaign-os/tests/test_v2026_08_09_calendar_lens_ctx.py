"""Regression tests for the Calendar 'How to read this view' lens banner.

Mirrors the prior-lane invariants (Insights v2 + Socials): a static-HTML probe
that the banner block exists inside `#sec-calendar`, sits before the HUD strip
+ grid, explains the slot state colours (draft / review / scheduled), the HUD
purpose, the drag-drop + duplicate semantics, and the Prev/Today/Next window
controls. No server required.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HTML = REPO / "campaign-os.html"


def _read() -> str:
    return HTML.read_text(encoding="utf-8")


def _sec_calendar_slice(html: str) -> str:
    m = re.search(
        r'<section[^>]*id="sec-calendar"[^>]*>(.*?)</section>',
        html,
        flags=re.DOTALL,
    )
    assert m, "sec-calendar section must exist in campaign-os.html"
    return m.group(1)


def _banner_block(slice_html: str) -> str:
    """Return just the banner block (between the calendar-lens-ctx class marker
    and the first closing </div> that ends it)."""
    idx = slice_html.find("calendar-lens-ctx")
    assert idx > -1, "calendar-lens-ctx banner must exist"
    # The banner is one <div class="card col-12 calendar-lens-ctx"> ... </div>.
    # Slice from idx to the matching closing tag. The banner is the first
    # col-12 div after the section-h close, so the first 'data-cal-shift'
    # occurrence (Prev/Today/Next buttons) lands AFTER the banner end. Walk
    # forward from idx until we've seen a </div> at the same nesting depth.
    start = slice_html.rfind("<div", 0, idx)
    depth = 0
    pos = start
    while pos < len(slice_html):
        nxt_open = slice_html.find("<div", pos + 1)
        nxt_close = slice_html.find("</div>", pos + 1)
        if nxt_close == -1:
            break
        if nxt_open != -1 and nxt_open < nxt_close:
            depth += 1
            pos = nxt_open
        else:
            if depth == 0:
                return slice_html[start:nxt_close + len("</div>")]
            depth -= 1
            pos = nxt_close
    return slice_html[start:idx + 400]


class CalendarLensCtx(unittest.TestCase):
    def setUp(self) -> None:
        self.html = _read()
        self.slice = _sec_calendar_slice(self.html)
        self.banner = _banner_block(self.slice)

    def test_banner_block_present(self):
        self.assertIn(
            'class="card col-12 calendar-lens-ctx"',
            self.slice,
            "calendar-lens-ctx banner must live inside #sec-calendar",
        )

    def test_banner_sits_before_hud_strip(self):
        banner_idx = self.slice.find("calendar-lens-ctx")
        hud_idx = self.slice.find('id="cal-hud"')
        self.assertGreater(banner_idx, -1, "banner must exist")
        self.assertGreater(hud_idx, -1, "HUD strip must exist")
        self.assertLess(
            banner_idx,
            hud_idx,
            "banner must paint BEFORE the HUD strip so users see the framing before any numbers",
        )

    def test_banner_sits_before_cal_grid(self):
        banner_idx = self.slice.find("calendar-lens-ctx")
        grid_idx = self.slice.find('id="cal-grid"')
        self.assertGreater(banner_idx, -1, "banner must exist")
        self.assertGreater(grid_idx, -1, "cal-grid must exist")
        self.assertLess(
            banner_idx,
            grid_idx,
            "banner must paint BEFORE the 14-day grid so the explainer leads the view",
        )

    def test_banner_sits_after_section_h(self):
        # The H2 + filter toolbar (.section-h) must keep its position above the
        # banner — that's where the prev/today/next controls live.
        section_h_close = self.slice.find("</div>", self.slice.find("Calendar</h2>"))
        banner_idx = self.slice.find("calendar-lens-ctx")
        self.assertGreater(section_h_close, -1, "section-h must close inside #sec-calendar")
        self.assertGreater(banner_idx, -1, "banner must exist")
        self.assertLess(
            section_h_close,
            banner_idx,
            "section-h (H2 + Prev/Today/Next + filters) must remain ABOVE the lens banner",
        )

    def test_banner_documents_slot_state_legend(self):
        # Each of the three slot states must be named so first-time users know
        # what the colours mean.
        for state in ("draft", "review", "scheduled"):
            self.assertIn(
                state,
                self.banner,
                f"slot state legend must mention '{state}'",
            )
        # And each must appear as a styled .pill chip inside the banner body,
        # so the visual key matches the slot class system.
        self.assertIn('class="pill draft"', self.banner)
        self.assertIn('class="pill review"', self.banner)
        # The scheduled pill uses .pill.live (blu tone) — that's the closest
        # existing pill class for the approved+queued state.
        self.assertRegex(
            self.banner,
            r'class="pill live"[^>]*>scheduled</span>',
            "scheduled pill chip must render with the .pill.live class so the legend matches the slot's blu border",
        )

    def test_pill_chips_not_collapsed_into_block_layout(self):
        # Regression guard: `.review` is also defined as a block-level review-row
        # class (padding:.75rem 1rem, display:flex, etc.) that overrides
        # `.pill.review`'s inline-flex chip layout. To prevent the chip from
        # stretching into a full-width review card, every pill chip must carry
        # an inline `display:inline-flex` override. The CSS-cascade collision
        # was visible on the live Railway screenshot before this fix landed.
        for cls in ("draft", "review", "live"):
            self.assertRegex(
                self.banner,
                rf'class="pill {cls}"[^>]*display:inline-flex',
                f"pill chip '{cls}' must declare inline `display:inline-flex` so the .review block class doesn't stretch it",
            )

    def test_banner_documents_drag_and_duplicate(self):
        # The Calendar tab's primary affordance is drag-to-reschedule + drop-to-
        # duplicate. The banner must teach that explicitly so users don't think
        # the cells are static.
        self.assertIn(
            "Duplicate zone",
            self.banner,
            "banner must reference the ⧉ Duplicate zone so users know the bottom drop target exists",
        )
        # The duplicate glyph ⧉ is the visual hook on that zone — banner must
        # mention it so users can match the icon to the affordance.
        self.assertIn("⧉", self.banner)

    def test_banner_documents_hud_purpose(self):
        # The HUD strip is the row of small cards immediately above the grid
        # (today's workload, overdue count, tomorrow's preview). Banner must
        # name it so users don't mistake it for unrelated noise.
        self.assertIn("HUD strip", self.banner)

    def test_banner_documents_prev_today_next(self):
        # The 14-day window is controlled by Prev / Today / Next + the 📍 Today
        # jump button. Banner must explain the ±7d shift + the jump semantics.
        self.assertIn("Prev / Today / Next", self.banner)
        self.assertIn("📍 Today", self.banner)
        self.assertIn("±7 days", self.banner)

    def test_banner_cross_links_review_and_analytics(self):
        # Calendar is the schedule, not the inbox — banner must redirect
        # approval work to Review and post-publish reads to Analytics.
        self.assertIn("Review", self.banner)
        self.assertIn("Analytics", self.banner)

    def test_banner_no_smart_quote_artifacts(self):
        # The Insights v2 banner had a regression on smart quotes once. Make
        # sure none of the typographically-decoded quote marks snuck into the
        # Calendar copy either.
        for bad in ("\u201c", "\u201d", "\u2018", "\u2019"):
            self.assertNotIn(
                bad,
                self.banner,
                f"banner must not contain smart-quote char U+{ord(bad):04X}",
            )

    def test_no_duplicate_banner(self):
        # Two banners would be a maintenance trap (the Insights v2 lane has a
        # known dead-code duplicate that bites the next reader). Lock the
        # exactly-once invariant.
        self.assertEqual(
            self.slice.count("calendar-lens-ctx"),
            1,
            "calendar-lens-ctx banner must appear exactly once in #sec-calendar",
        )

    def test_other_tabs_unchanged(self):
        # Sanity: adding the Calendar banner must not regress the Socials or
        # Insights banners.
        full = self.html
        self.assertEqual(
            full.count("socials-lens-ctx"),
            1,
            "Socials banner must still appear exactly once — no regression on the prior lane",
        )
        self.assertEqual(
            full.count("insights-lens-ctx"),
            2,
            "Insights v2 banner (live + dead-code clone) must still appear twice — no regression on the prior lane",
        )


if __name__ == "__main__":
    unittest.main()