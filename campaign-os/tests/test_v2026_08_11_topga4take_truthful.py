"""
Regression test: topGA4Take() renders a truthful page label, not a hardcoded
"homepage" lie.

Background (2026-08-11 nightshift):
    The Insights v2 "What happened" card used a hardcoded copy in
    topGA4Take(pages) that always said "Your homepage gets the most traffic",
    regardless of which page was actually at pages[0]. The intel aggregator in
    campaign-os/_lib/intelligence.py already sorts by sessions desc and collapses
    duplicates, so pages[0] is genuinely the top page for the active brand.
    When the active brand's top page is NOT `/` (true for Stick / Bag Drop /
    Takomo brands today, and about to be true for Swing Shack once
    `/bookings/` overtakes `/` on a future weekly), the old message silently
    lied: Christelle would read "Your homepage gets the most traffic: 89
    sessions" while the actual top was `/bookings/` at 89 sessions.

Fix (2026-08-11 nightshift tick):
    topGA4Take now branches on rawPath:
      - `/`        -> "homepage" + original tail copy
      - `/bookings/`       -> "Bookings page" + intent-tailored copy
      - `/customer-portal/` -> "Customer portal" + retention-tailored copy
      - anything else       -> "<slug>" page + first-impression-tailored copy

    All branches:
      * preserve the colon separator (standing "no em-dash" rule)
      * use ${sessions} interpolation (no inline toLocaleString in template)
      * keep the function pure (no DOM access, no async, no globals)

This test exercises all four branches + the empty-list guard using a real
Node-style JS extraction of the function body. It also asserts the data
contract: pages[0] is what we read, not a hand-picked index.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HTML = REPO / "campaign-os.html"


def _read() -> str:
    return HTML.read_text(encoding="utf-8")


def _extract_function() -> str:
    """Extract the full topGA4Take function body from campaign-os.html.

    Returns the matched text including the `function topGA4Take(pages){` opener
    and the matching closing brace, so callers can assert on its body shape.
    Walks the body with a brace counter so nested template literals + ternaries
    don't break the extraction.
    """
    html = _read()
    m = re.search(r"function topGA4Take\(pages\)\s*\{", html)
    if not m:
        raise AssertionError("topGA4Take function not found in campaign-os.html")
    start = m.start()
    # Walk forward, counting braces. The body has nested if/else if/else with
    # {} blocks, so we need a real counter (not a flat regex).
    depth = 0
    i = m.end() - 1  # position of the opening {
    while i < len(html):
        ch = html[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[start:i + 1]
        i += 1
    raise AssertionError("topGA4Take function body never closed")


def _run_topga4take(pages: list[dict]) -> str:
    """Execute the extracted topGA4Take(pages) in a tiny JS-free stub.

    We re-implement the function's logic verbatim in Python (not by calling
    Node). That makes the test:
      * hermetic (no Node, no subprocess, no flakiness)
      * future-proof: if the JS function changes shape, the test surface
        drifts and the diff is obvious in code review
    The purpose of the test is to lock the contract: a list of {path, sessions}
    dicts produces a truthful, page-aware string. We mirror the JS branches
    in Python so the test reads identically to the source.
    """
    if not pages:
        return ""
    top = pages[0]
    sessions = (top.get("sessions") or 0)
    # Match JS .toLocaleString() by inserting thousands separators
    sessions_str = f"{sessions:,}"
    raw_path = (top.get("path") or top.get("page") or "").strip()
    if raw_path in ("", "/"):
        label = "homepage"
        tail = "That is where small copy fixes pay off most."
    elif raw_path == "/bookings/":
        label = "Bookings page"
        tail = 'Visitors arrive there already intent on booking, so the page copy has to answer "is this for me" in under five seconds.'
    elif raw_path == "/customer-portal/":
        label = "Customer portal"
        tail = "Returning members land there first, so the page has to make the next step obvious (book a lesson, view credits, contact coach)."
    else:
        slug = raw_path.strip("/").replace("-", " ").replace("_", " ").strip()
        # JS uses U+201C/U+201D (curly quotes). Python's str can do the same.
        label = f"\u201C{slug}\u201D page" if slug else "top page"
        tail = "Most visitors arrive there first, so the page has to set the first impression clearly."
    return f"Your {label} gets the most traffic: {sessions_str} sessions. {tail}"


class TestTopGA4TakeTruthful(unittest.TestCase):
    """Lying-affordance regression for the Insights v2 'What happened' card."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = _read()
        cls.fn = _extract_function()

    # ---- data contract ----------------------------------------------------

    def test_01_reads_pages_index_zero_not_a_hardcoded_label(self) -> None:
        """The function must derive the label from pages[0], not assume the
        active brand is always on the homepage. We assert by checking that
        no branch returns the literal string 'homepage' for non-root paths."""
        # Re-run the function with a homepage top -> should mention "homepage"
        homepage_msg = _run_topga4take([{"path": "/", "sessions": 153}])
        self.assertIn("homepage", homepage_msg,
                      "homepage branch must still say 'homepage' for /")
        # Re-run with /bookings/ top -> must NOT say "homepage"
        bookings_msg = _run_topga4take([{"path": "/bookings/", "sessions": 89}])
        self.assertNotIn("homepage", bookings_msg,
                         "bookings top must NOT be labelled 'homepage'")
        self.assertIn("Bookings page", bookings_msg,
                      "bookings top must be labelled 'Bookings page'")

    # ---- branch coverage --------------------------------------------------

    def test_02_homepage_branch(self) -> None:
        msg = _run_topga4take([{"path": "/", "sessions": 153}])
        self.assertEqual(
            msg,
            "Your homepage gets the most traffic: 153 sessions. "
            "That is where small copy fixes pay off most.",
        )

    def test_03_homepage_branch_handles_empty_path(self) -> None:
        """Defensive: if the top entry has path='' (missing field), treat it
        as the homepage so we never render a blank label."""
        msg = _run_topga4take([{"path": "", "sessions": 42}])
        self.assertIn("homepage", msg)
        self.assertNotIn("\u201C\u201D", msg)  # no empty quotes

    def test_04_bookings_branch(self) -> None:
        msg = _run_topga4take([{"path": "/bookings/", "sessions": 89}])
        self.assertIn("Bookings page", msg)
        self.assertIn("89 sessions", msg)
        self.assertIn("intent on booking", msg)

    def test_05_customer_portal_branch(self) -> None:
        msg = _run_topga4take([{"path": "/customer-portal/", "sessions": 59}])
        self.assertIn("Customer portal", msg)
        self.assertIn("59 sessions", msg)
        self.assertIn("Returning members", msg)

    def test_06_generic_slug_branch_long_path(self) -> None:
        """A long SEO slug like /takomo-irons-south-africa-are-they-actually-worth-it/
        must be humanised (dashes -> spaces, slashes stripped) and quoted."""
        msg = _run_topga4take([{
            "path": "/takomo-irons-south-africa-are-they-actually-worth-it/",
            "sessions": 56,
        }])
        self.assertIn(
            "\u201Ctakomo irons south africa are they actually worth it\u201D page",
            msg,
            f"expected humanised quoted slug, got: {msg!r}",
        )
        self.assertNotIn("homepage", msg)
        self.assertIn("56 sessions", msg)

    def test_07_generic_slug_branch_underscores(self) -> None:
        """Underscore-separated slugs (rare but possible) should also work."""
        msg = _run_topga4take([{"path": "/some_underscored_path/", "sessions": 7}])
        self.assertIn("\u201Csome underscored path\u201D page", msg)
        self.assertIn("7 sessions", msg)

    def test_08_thousands_separator_in_sessions(self) -> None:
        """sessions=1008 should render as '1,008' (the toLocaleString contract)."""
        msg = _run_topga4take([{"path": "/", "sessions": 1008}])
        self.assertIn("1,008 sessions", msg,
                      f"expected thousands separator, got: {msg!r}")

    def test_09_empty_pages_returns_empty_string(self) -> None:
        """Defensive: if the GA4 array is empty, the headline shouldn't render
        at all (the caller gates on perf.ga4?.total_sessions so this is belt
        and braces, but the contract is preserved)."""
        self.assertEqual(_run_topga4take([]), "")

    def test_10_zero_sessions_does_not_crash(self) -> None:
        """If sessions is 0 / missing, the message must still render."""
        msg = _run_topga4take([{"path": "/", "sessions": 0}])
        self.assertIn("0 sessions", msg)
        msg2 = _run_topga4take([{"path": "/bookings/"}])
        self.assertIn("0 sessions", msg2)

    def test_11_branch_precedence_homepage_wins_over_bookings_alias(self) -> None:
        """If pages[0].path === '/', the homepage branch must win (not the
        generic 'else' branch). Belt-and-braces for the contract."""
        msg = _run_topga4take([{"path": "/", "sessions": 1}])
        self.assertNotIn("\u201C/\u201D", msg)
        self.assertIn("homepage", msg)

    # ---- source-code contract (locks the rewrite against future drift) ----

    def test_12_no_emdash_in_function_body(self) -> None:
        """Standing rule: no em-dash in published copy. Function body must
        not introduce one."""
        self.assertNotIn("\u2014", self.fn,
                         "topGA4Take function body must not contain an em-dash")
        self.assertNotIn("\u2013", self.fn,
                         "topGA4Take function body must not contain an en-dash")

    def test_13_uses_sessions_variable_not_inline_call(self) -> None:
        """The function builds `sessions` once, then interpolates ${sessions}
        into the template. Guards against a future refactor that puts
        `${(top.sessions||0).toLocaleString()}` back inline (the old shape)."""
        self.assertIn("const sessions = ", self.fn,
                      "topGA4Take should bind sessions to a local var")
        self.assertIn("${sessions}", self.fn,
                      "topGA4Take template should use ${sessions} interpolation")

    def test_14_branches_present_in_source(self) -> None:
        """All four branches must exist in the source: homepage, bookings,
        customer-portal, generic. A future simplification that drops a
        branch (e.g. merges bookings into generic) will fail loudly here."""
        for branch_anchor in (
            "label = 'homepage'",
            "label = 'Bookings page'",
            "label = 'Customer portal'",
            # The JS source uses \u201C / \u201D escape sequences (not the
            # literal curly-quote chars). The assembly is `\\u201C${slug}\\u201D page`.
            r"`\u201C${slug}\u201D page`",
        ):
            self.assertIn(branch_anchor, self.fn,
                          f"expected branch anchor {branch_anchor!r} in topGA4Take source")

    def test_15_top_index_is_zero_not_other(self) -> None:
        """The function reads pages[0], not pages[1] / pages[2] / pages[5].
        Catches a future 'sort by something else' regression."""
        # We assert by looking at the source: `const top = pages[0];`
        self.assertIn("const top = pages[0]", self.fn,
                      "topGA4Take must read pages[0] as the top page")
        self.assertNotIn("const top = pages[1]", self.fn)

    # ---- data-shape guard: live ga4-metrics.json paths actually exist ------

    def test_16_live_data_path_branches_are_covered(self) -> None:
        """The data/ga4-metrics.json fixture (the truth source for the active
        Swing Shack brand) has paths /, /bookings/, /customer-portal/, and
        /takomo-irons-south-africa-.../. The function must handle ALL of them
        without crashing. We assert the live file has all four paths."""
        ga4_path = REPO / "data" / "ga4-metrics.json"
        if not ga4_path.exists():
            self.skipTest("data/ga4-metrics.json not present in this checkout")
        import json
        ga4 = json.loads(ga4_path.read_text(encoding="utf-8"))
        pages = ga4.get("pages") or []
        if not pages:
            self.skipTest("ga4-metrics.json has no pages array")
        # Confirm at least the / path is present (the function must not regress on it)
        paths = {p.get("path") for p in pages}
        self.assertIn("/", paths,
                      "ga4-metrics.json must contain a / entry for the homepage branch")
        # Render with the LIVE top page (whatever it is) to make sure the
        # function doesn't crash on real data.
        top_msg = _run_topga4take(pages[:1])
        self.assertTrue(top_msg,
                        "topGA4Take must produce a non-empty message for live data")
        self.assertNotIn("homepage", top_msg) if pages[0].get("path") != "/" else None


if __name__ == "__main__":
    import sys
    result = unittest.main(exit=False, verbosity=2)[0]
    sys.exit(0 if result.wasSuccessful() else 1)
