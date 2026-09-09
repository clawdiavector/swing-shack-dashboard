"""
First-run welcome modal + phase-1 nav consolidation tests.

Verifies:
  • Old "+ More tools" / "all-tools-toggle" markup is GONE
  • New collapsible groups exist (Daily/Build/Insight/Reach/External)
  • Each nav group has a header with aria-expanded and chevron
  • Welcome modal markup exists with required IDs
  • Welcome tour has 5 steps wired
  • "Restart tour" item exists in sidebar
  • GMB renamed to Google Business
  • External links have ↗ marker
  • Publish flow strip exists
  • Calendar Today button exists
  • Old stale CSS hooks don't break page load

These are smoke tests — they grep the rendered HTML for required IDs
and structural patterns. They don't exercise the JS handlers directly
(since the SPA is mostly client-rendered); that's covered by the
hand-test on the live URL.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CAMPAIGN_OS_HTML = REPO / "campaign-os" / "campaign-os.html"


class WelcomeModalTests(unittest.TestCase):
    """First-run welcome tour markup + behaviour wiring."""

    @classmethod
    def setUpClass(cls):
        cls.html = CAMPAIGN_OS_HTML.read_text(encoding="utf-8")

    def test_welcome_modal_markup_present(self):
        for must_have in [
            'id="welcome-bg"',
            'id="welcome-ico"',
            'id="welcome-step-title"',
            'id="welcome-step-desc"',
            'id="welcome-jump"',
            'id="welcome-progress"',
            'id="welcome-skip"',
            'id="welcome-cta"',
            'id="welcome-step-card"',
        ]:
            self.assertIn(must_have, self.html, f"missing {must_have}")

    def test_welcome_modal_class_welcome_bg(self):
        self.assertIn("class=\"welcome-bg\"", self.html)

    def test_tour_steps_constant(self):
        self.assertIn("const TOUR_STEPS = [", self.html)
        self.assertIn("{ ico:'🏠', title:'Today'", self.html)
        self.assertIn("{ ico:'✅', title:'Review'", self.html)
        self.assertIn("{ ico:'🪄', title:'Create'", self.html)
        self.assertIn("{ ico:'📈', title:'Insights'", self.html)
        self.assertIn("{ ico:'🧬', title:'Image Lab'", self.html)

    def test_tour_storage_key(self):
        self.assertIn("campaign-os.tour.dismissed.v2", self.html)

    def test_tour_dismiss_writes_localstorage(self):
        # When user clicks skip/close, dismissed flag should persist
        self.assertIn("localStorage.setItem(TOUR_KEY, '1')", self.html)

    def test_tour_open_function(self):
        self.assertIn("function openWelcome()", self.html)
        self.assertIn("function closeWelcome()", self.html)
        self.assertIn("function maybeShowWelcome()", self.html)

    def test_restart_tour_nav_item_exists(self):
        self.assertIn('id="nav-restart-tour"', self.html)
        self.assertIn("Restart tour", self.html)

    def test_restart_tour_handler_wired(self):
        self.assertIn("$('#nav-restart-tour').addEventListener", self.html)


class NavGroupTests(unittest.TestCase):
    """Phase-1 collapsible nav group consolidation."""

    @classmethod
    def setUpClass(cls):
        cls.html = CAMPAIGN_OS_HTML.read_text(encoding="utf-8")

    def test_old_all_tools_section_gone(self):
        self.assertNotIn('id="all-tools-section"', self.html)
        self.assertNotIn('id="all-tools-toggle"', self.html)
        self.assertNotIn("+ More tools", self.html)

    def test_old_all_tools_label_gone(self):
        self.assertNotIn('id="all-tools-toggle-label"', self.html)

    def test_new_nav_groups_exist(self):
        for grp in ["daily", "build", "insight", "reach", "external"]:
            self.assertIn(f'data-nav-group="{grp}"', self.html)
            self.assertIn(f'id="nav-group-{grp}"', self.html)

    def test_each_group_has_aria_expanded(self):
        # Daily starts expanded; others collapsed by default
        for grp in ["daily", "build", "insight", "reach", "external"]:
            self.assertIn(
                f'data-nav-group="{grp}" tabindex="0" role="button" aria-expanded=',
                self.html,
                f"{grp} missing aria-expanded role",
            )

    def test_daily_starts_open_others_start_closed(self):
        # Default state: Daily expanded, others collapsed
        daily = self.html.find('data-nav-group="daily"')
        build = self.html.find('data-nav-group="build"')
        self.assertIn('aria-expanded="true"', self.html[daily:daily + 200])
        self.assertIn('aria-expanded="false"', self.html[build:build + 200])

    def test_nav_state_persists_to_localstorage(self):
        self.assertIn("campaign-os.nav-groups.v1", self.html)
        self.assertIn("function loadNavState()", self.html)
        self.assertIn("function toggleNavGroup(g)", self.html)

    def test_group_labels_have_tags(self):
        # Each group has a one-liner tag explaining what it is
        for tag in ["5 essentials", "create + brand", "what's working", "schedule + ship", "5 apps"]:
            self.assertIn(tag, self.html)

    def test_gmb_renamed_to_google_business(self):
        # Nav label should say "Google Business", not "GMB"
        # (the legacy "GMB Drafts" tooltip name may still exist in help text)
        self.assertIn("> Google Business <", self.html)

    def test_external_nav_items_have_arrow_marker(self):
        # External apps get a ↗ glyph
        self.assertIn('class="ext-mark">↗<', self.html)

    def test_no_more_quick_links_section(self):
        self.assertNotIn('class="nav-title">Quick links', self.html)

    def test_external_group_contains_all_external_apps(self):
        # All 4 external apps present
        ext_grp_start = self.html.find('id="nav-group-external"')
        ext_grp_end = self.html.find('</div>\n    </div>\n\n    <!-- Reset onboarding link', ext_grp_start)
        section = self.html[ext_grp_start:ext_grp_end]
        for app in ['/visualizer', '/meme-lab', '/image-lab', '/cockpit-operational']:
            self.assertIn(app, section)


class PublishFlowArrowTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.html = CAMPAIGN_OS_HTML.read_text(encoding="utf-8")

    def test_pub_flow_strip_exists(self):
        self.assertIn("class=\"pub-flow\"", self.html)

    def test_pub_flow_steps(self):
        self.assertIn("📝 Draft", self.html)
        self.assertIn("🗓️ Scheduled", self.html)
        self.assertIn("✓ Live", self.html)
        self.assertIn("🚨 Failed", self.html)
        self.assertIn("class=\"pub-flow-arrow\">→<", self.html)


class CalendarTodayButtonTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.html = CAMPAIGN_OS_HTML.read_text(encoding="utf-8")

    def test_today_button_exists(self):
        self.assertIn('id="cal-today-btn"', self.html)
        self.assertIn("📍 Today", self.html)


class NavStaleBindingSafetyTests(unittest.TestCase):
    """The new code must not throw on legacy references."""

    @classmethod
    def setUpClass(cls):
        cls.html = CAMPAIGN_OS_HTML.read_text(encoding="utf-8")

    def test_old_all_tools_handler_is_guarded(self):
        # Guard pattern must exist so old code doesn't throw
        self.assertIn("if($('#all-tools-toggle'))", self.html)

    def test_no_more_bare_all_tools_bind(self):
        # Make sure we replaced the bare call with the guarded one
        self.assertNotIn("$('#all-tools-toggle').addEventListener('click', () => {\n  const sec = $('#all-tools-section');\n  const isHidden", self.html)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False, verbosity=2).result.wasSuccessful() else 1)