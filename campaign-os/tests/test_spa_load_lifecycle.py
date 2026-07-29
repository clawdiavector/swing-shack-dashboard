"""Regression tests for the SPA JS load lifecycle.

These tests use Playwright to drive the live SPA through critical user
journeys. They guard against the silent JS-failure bug where a top-level
`$('#missing').addEventListener(...)` kills the entire script before
window.toggleCampaignPlan is assigned.

If any of these tests fail, the user CANNOT expand a campaign plan —
that's a critical UX regression we want to know about immediately.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(
    os.environ.get("RUN_BROWSER_TESTS") == "1",
    "Set RUN_BROWSER_TESTS=1 to run browser-level SPA tests",
)
class SpaLoadLifecycleTests(unittest.TestCase):
    """Verify the SPA loads cleanly without runtime JS errors."""

    @classmethod
    def setUpClass(cls):
        # Ensure Playwright + Chromium are available
        from playwright.sync_api import sync_playwright

        cls._playwright = sync_playwright().start()
        cls._browser = cls._playwright.chromium.launch()
        cls._context = cls._browser.new_context()

    @classmethod
    def tearDownClass(cls):
        try:
            cls._context.close()
            cls._browser.close()
        finally:
            cls._playwright.stop()

    def _open(self, url):
        page = self._context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append((e.message, e.stack or "")))
        page.goto(url, wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(2500)
        return page, errors

    def test_spa_loads_without_runtime_errors(self):
        page, errors = self._open("https://episodes-images-futures-coleman.trycloudflare.com/")
        try:
            self.assertEqual(
                errors, [],
                f"SPA had {len(errors)} runtime errors on load: {errors[:3]}"
            )
        finally:
            page.close()

    def test_toggleCampaignPlan_is_defined_after_load(self):
        """The earlier bug: $('missing').addEventListener at top level killed
        the script before window.toggleCampaignPlan was assigned, making
        campaign plans un-expandable."""
        page, errors = self._open("https://episodes-images-futures-coleman.trycloudflare.com/")
        try:
            kind = page.evaluate("typeof window.toggleCampaignPlan")
            self.assertEqual(
                kind, "function",
                "window.toggleCampaignPlan must be a function — if undefined, "
                "a top-level JS error killed the script before this assignment. "
                f"Page errors: {errors[:3]}"
            )
        finally:
            page.close()

    def test_loadPlanAssets_is_defined_after_load(self):
        page, errors = self._open("https://episodes-images-futures-coleman.trycloudflare.com/")
        try:
            kind = page.evaluate("typeof window.loadPlanAssets")
            self.assertEqual(
                kind, "function",
                "window.loadPlanAssets must be a function. "
                f"Page errors: {errors[:3]}"
            )
        finally:
            page.close()

    def test_all_navigation_functions_defined(self):
        """Every sidebar nav item must have a working go() target."""
        expected = [
            "renderBrief", "renderReview", "renderPublish", "renderCalendar",
            "renderTrends", "renderIdeas", "renderPerformance", "renderLearning",
            "renderHooks", "renderMemes", "renderBillboards", "renderCaptions",
            "renderHeadlines", "renderCTAs", "renderHashtagSeo", "renderImageGen",
            "renderSEO", "renderSeoAudit", "renderGBP", "renderReddit",
            "renderFAQs", "renderPostiz", "renderCampaigns", "renderAgents",
        ]
        page, errors = self._open("https://episodes-images-futures-coleman.trycloudflare.com/")
        try:
            missing = [name for name in expected if page.evaluate(f"typeof {name}") != "function"]
            self.assertEqual(
                missing, [],
                f"Functions not defined (script likely crashed before reaching them): {missing}. "
                f"Page errors: {errors[:2]}"
            )
        finally:
            page.close()

    def test_campaign_plan_expands_inline_editor(self):
        """End-to-end: click 'Full plan' on a campaign card and verify
        the inline asset editor renders with the right number of cards."""
        page, errors = self._open("https://episodes-images-futures-coleman.trycloudflare.com/#campaigns")
        try:
            # Navigate via the SPA
            page.evaluate('go("campaigns")')
            page.wait_for_timeout(1500)
            page.evaluate('window.toggleCampaignPlan("use-the-right-equipment-mq5l90bk")')
            page.wait_for_timeout(2500)
            plan_present = page.evaluate('!!document.getElementById("plan-use-the-right-equipment-mq5l90bk")')
            asset_count = page.evaluate('document.querySelectorAll(".ed-cap").length')
            self.assertTrue(
                plan_present,
                "Campaign plan did not expand. toggleCampaignPlan likely failed silently."
            )
            self.assertGreater(
                asset_count, 0,
                "Inline editor rendered zero asset cards — plan expanded but editor empty"
            )
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)