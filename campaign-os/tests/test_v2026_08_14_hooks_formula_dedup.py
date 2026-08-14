"""Regression test for the Hook Bank formula dedup fix.

Bug: the Hook Bank page rendered the same hook text twice in the same view —
once in the "Watched + worked" panel (where it sits with its score) and once
in the "Hook formulas" panel (where the formula's `best_example` was the
verbatim top hook of that bucket). Users read the same line twice and skipped
the right-hand panel.

Fix: renderHooks() now builds a normalised lookup over `all_hooks` and, when a
formula's best_example matches an entry there, replaces the duplicated hook
text with a "see top <formula> hook above" cross-reference badge. The formula
label / count / avg score still render, so the panel stays informative.

This test hits the LIVE URL (or local server if CO_TEST_URL is set) with
Playwright and asserts:
1. The hooks page loads with no JS errors.
2. Every formula row's title either (a) is NOT a normalized match of any
   rendered Watched + worked hook, or (b) is a cross-reference placeholder
   instead of duplicating the hook text.
3. The formula label, count, and avg score still appear (panel is still
   useful, not stripped).

Each test gets a fresh browser context so cookies / SPA state from a previous
test can't bleed in. Set RUN_BROWSER_TESTS=1 to execute (same gate as the
other browser tests).
"""
from __future__ import annotations

import os
import re
import unittest

REPO = __import__("pathlib").Path(__file__).resolve().parents[2]

# Default to the live URL; set CO_TEST_URL=http://127.0.0.1:8765 to run
# against the local flask server (same SPA, same data).
LIVE_URL = os.environ.get(
    "CO_TEST_URL", "https://swing-shack-dashboard-production.up.railway.app"
)
PWD = "swing-shack-dev-2026"


@unittest.skipUnless(
    os.environ.get("RUN_BROWSER_TESTS") == "1",
    "Set RUN_BROWSER_TESTS=1 to run browser-level SPA tests",
)
class HookFormulaDedupTests(unittest.TestCase):
    """Verify the hook-formula panel no longer duplicates WW rows."""

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls._playwright = sync_playwright().start()
        cls._browser = cls._playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        try:
            cls._browser.close()
        finally:
            cls._playwright.stop()

    # ────────────────────────────────────────────────────────────────
    # Per-test helper: fresh context → login → click Hook Bank nav.
    # ────────────────────────────────────────────────────────────────
    def _open_hooks(self):
        ctx = self._browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(("pageerror", str(e))))
        page.on(
            "console",
            lambda m: errors.append((m.type, m.text))
            if m.type == "error"
            else None,
        )

        page.goto(LIVE_URL, wait_until="networkidle", timeout=20000)
        try:
            page.fill('input[name="password"], input[type="password"]', PWD)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        # Skip the tour so it doesn't cover the panels. Don't reload — live
        # URL reloads occasionally race with the session cookie and abort;
        # the SPA tour check on next nav still picks up the localStorage key.
        try:
            page.evaluate("localStorage.setItem('cos.tour.skipped', '1')")
            page.wait_for_timeout(800)
        except Exception:
            pass

        # Click the Hook Bank nav. Try both the topbar and the sidebar copy.
        clicked = page.evaluate(
            """() => {
              const links = document.querySelectorAll('[data-go="hooks"]');
              if (links.length) { links[0].click(); return 'clicked'; }
              return 'not-found';
            }"""
        )
        # Wait for both panels to actually render the data, not just the DOM.
        try:
            page.wait_for_function(
                """() => {
                  const ww = document.querySelector('#hooks-ww');
                  const fm = document.querySelector('#hooks-formulas');
                  if (!ww || !fm) return false;
                  return ww.querySelectorAll('.li').length > 0
                      && fm.querySelectorAll('.li').length > 0;
                }""",
                timeout=15000,
            )
        except Exception:
            pass
        page.wait_for_timeout(1500)
        return page, errors, ctx, clicked

    @staticmethod
    def _norm(text):
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def _gather_titles(self, page, selector):
        return page.evaluate(
            f"""() => Array.from(document.querySelectorAll('{selector} .li-title')).map(n => n.innerText.trim())"""
        )

    # ────────────────────────────────────────────────────────────────
    # Tests
    # ────────────────────────────────────────────────────────────────
    def test_hooks_page_loads_clean(self):
        page, errors, ctx, _ = self._open_hooks()
        try:
            real = [e for e in errors if e[0] == "pageerror"]
            self.assertEqual(
                real, [],
                f"Hook Bank page had {len(real)} pageerror(s): {real[:3]}",
            )
        finally:
            page.close()
            ctx.close()

    def test_formulas_do_not_repeat_ww_hooks(self):
        page, _, ctx, clicked = self._open_hooks()
        try:
            self.assertIn(clicked, ("clicked",),
                          f"Could not click [data-go=hooks] ({clicked})")
            ww_titles = self._gather_titles(page, "#hooks-ww")
            form_titles = self._gather_titles(page, "#hooks-formulas")
            self.assertTrue(ww_titles, "Watched + worked panel is empty in the test")
            self.assertTrue(form_titles, "Hook formulas panel is empty in the test")

            ww_keys = {self._norm(t) for t in ww_titles if t}
            dups = [t for t in form_titles if self._norm(t) in ww_keys]
            self.assertEqual(
                dups, [],
                f"{len(dups)} formula row(s) still duplicate a Watched + worked "
                f"hook verbatim. Examples: {dups[:3]}",
            )
        finally:
            page.close()
            ctx.close()

    def test_formulas_panel_still_has_signal_label_and_numbers(self):
        page, _, ctx, _ = self._open_hooks()
        try:
            meta_html = page.evaluate(
                """() => Array.from(document.querySelectorAll('#hooks-formulas .li-meta')).map(n => n.innerText.trim())"""
            )
            self.assertTrue(meta_html, "Hook formulas panel meta rows are empty")
            joined = " | ".join(meta_html).lower()
            self.assertIn("uses", joined, "Formulas meta should still show 'uses'")
            self.assertIn("avg score", joined, "Formulas meta should still show 'avg score'")
        finally:
            page.close()
            ctx.close()


if __name__ == "__main__":
    unittest.main()
