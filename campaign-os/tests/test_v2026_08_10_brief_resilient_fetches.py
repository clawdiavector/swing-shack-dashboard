"""v2026-08-10 — Brief feed resilience: one failed fetch must not blank the page.

The pre-pick sweep (scripts/sweep_campaign_os_live.py) caught a console
error during the very first page load:

    console.error: TypeError: Failed to fetch
        at renderBrief (.../campaign-os.html:6442:11)
        at boot (.../campaign-os.html:10779:11)

Root cause: renderBrief's Promise.all contained 3 direct API.get calls
(morning_brief, review_inbox, trend_catcher) with no .catch() handler.
If any one of those rejected (transient network, browser aborted the
fetch, backend restart mid-boot), the entire Promise.all rejected, the
renderBrief `await` threw, and boot()'s catch handler surfaced a
"Boot failed: Failed to fetch" toast to the user — plus the brief
strip went blank.

Fix: wrap the 3 direct fetches in a safeGet() helper that returns null
on rejection, and only assign state (S.brief / S.review / S.trends)
when the primary morning_brief payload is non-null. If it IS null,
keep any prior cached brief and surface a quiet warn toast instead
of a hard "Boot failed" error.

These tests are read-only — they probe the static HTML for the repaired
markers so a regression that removes the safeGet wrapper or reverts
the unconditional state assignment fails loudly.
"""

import os
import re
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML_PATH = os.path.join(REPO_ROOT, "campaign-os", "campaign-os.html")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _render_brief_body(html: str) -> str:
    """Return the body of renderBrief() — the lines from `async function
    renderBrief(){` up to the closing `}` of that function. We use a
    brace-counting approach so the test stays robust if comments grow.
    """
    m = re.search(r"async function renderBrief\(\)\{", html)
    if not m:
        raise AssertionError("Could not locate renderBrief() declaration")
    start = m.end() - 1  # position of the opening `{`
    depth = 0
    i = start
    while i < len(html):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return html[start:i + 1]
        i += 1
    raise AssertionError("renderBrief() body never closed")


class BriefResilientFetches(unittest.TestCase):
    def setUp(self):
        self.html = _read(HTML_PATH)
        self.body = _render_brief_body(self.html)

    def test_safeGet_helper_is_defined(self):
        """The fix introduces a safeGet wrapper so each fetches' rejection
        becomes a null resolution instead of a Promise.all-wide failure."""
        self.assertRegex(
            self.body,
            r"const\s+safeGet\s*=\s*\(p\)\s*=>\s*API\.get\(p\)\.catch\(",
            "renderBrief() must define a safeGet() helper that swallows fetch errors",
        )

    def test_three_primary_endpoints_use_safeGet(self):
        """morning_brief, review_inbox, trend_catcher must all be wrapped —
        these are the direct (un-chained) fetches that used to reject the
        whole batch."""
        for endpoint in ("morning_brief", "review_inbox", "trend_catcher"):
            with self.subTest(endpoint=endpoint):
                # Look for safeGet('/api/intel/<endpoint>') specifically
                pat = r"safeGet\(['\"]/api/intel/" + re.escape(endpoint) + r"['\"]\)"
                self.assertRegex(
                    self.body,
                    pat,
                    f"renderBrief() must call safeGet('/api/intel/{endpoint}') — was the .catch() wrapper removed?",
                )

    def test_state_assignment_is_guarded_by_brief_payload(self):
        """The S.brief = b; S.review = r; S.trends = t; line must only run
        when the primary morning_brief payload is non-null. Otherwise a
        null deref of b.__cacheBrand would throw inside the Promise.all
        continuation."""
        # Find the Promise.all block and look for the if(!b) guard before
        # the state assignment.
        pa_block = re.search(
            r"const\s+\[b,\s*r,\s*t\]\s*=\s*await\s+Promise\.all\(\[.*?\]\);",
            self.body,
            re.DOTALL,
        )
        self.assertIsNotNone(pa_block, "Could not find Promise.all block in renderBrief()")
        after = self.body[pa_block.end():pa_block.end() + 800]
        self.assertIn(
            "if(!b)",
            after,
            "After Promise.all, renderBrief() must guard state assignment with `if(!b)` so a null morning_brief doesn't crash the page",
        )

    def test_no_unwrapped_API_get_in_brief_promise_all(self):
        """Regression guard: no direct API.get(..../morning_brief|review_inbox|trend_catcher)
        inside the Promise.all array. The chained fetch helpers (fetchBrandContext,
        fetchTodayPanel, fetchWhatsNew, fetchFreshness) already have their own
        .catch() and don't need to be wrapped."""
        pa_block = re.search(
            r"const\s+\[b,\s*r,\s*t\]\s*=\s*await\s+Promise\.all\(\[.*?\]\);",
            self.body,
            re.DOTALL,
        )
        self.assertIsNotNone(pa_block)
        block = pa_block.group(0)
        # Find direct API.get calls (not safeGet, not chained) to the 3 endpoints
        for endpoint in ("morning_brief", "review_inbox", "trend_catcher"):
            with self.subTest(endpoint=endpoint):
                # A bare API.get('/api/intel/<endpoint>') (not safeGet) inside the block
                bare = re.search(
                    r"API\.get\(['\"]/api/intel/" + re.escape(endpoint) + r"['\"]\)",
                    block,
                )
                self.assertIsNone(
                    bare,
                    f"bare API.get('/api/intel/{endpoint}') still inside Promise.all — wrap with safeGet()",
                )

    def test_warn_toast_on_null_brief_when_no_cache(self):
        """When the primary brief payload is null AND there's no prior cached
        brief, fall back to a warn-level toast (not a hard error toast).
        This is the user-visible UX of the fix."""
        self.assertIn(
            "toast('Brief feed unreachable",
            self.body,
            "renderBrief() must toast a soft warning when the primary brief payload is null and no cache exists",
        )

    def test_downstream_b_property_accesses_are_guarded(self):
        """If S.brief is null after the safeGet wrapper returns, the rest of
        renderBrief must NOT continue to read b.counts / b.do_first /
        b.needs_review / b.ready_to_publish / b.missed_high_impact /
        b.seo_quick_wins / b.post_today — those would crash with
        "Cannot read properties of null". The guard is a top-level early
        return once the strip placeholder is rendered."""
        # The guard: `if(!b || !b.summary){ ...; return; }` must appear
        # between the `const b = S.brief;` read and the first downstream
        # b.counts / b.do_first access.
        m = re.search(r"const\s+b\s*=\s*S\.brief\s*;", self.body)
        self.assertIsNotNone(m, "Could not find `const b = S.brief;` in renderBrief()")
        after = self.body[m.end():m.end() + 1200]
        self.assertRegex(
            after,
            r"if\s*\(\s*!b\s*\|\|\s*!b\.summary\s*\)\s*\{[^}]*return\s*;",
            "renderBrief() must guard downstream b.* reads with `if(!b || !b.summary){ ...; return; }`",
        )
        # Verify the guard returns BEFORE we hit the first `b.counts` access.
        # In the body, the first `b.counts` should appear AFTER `return;` inside
        # the guard block, not before. Simpler check: the guard's `return;` must
        # appear before the line `const c = b.counts;`.
        cdot = self.body.find("const c = b.counts")
        ret = self.body.find("return;", m.end())
        self.assertGreater(
            ret, m.end(),
            "renderBrief() must return early from the null-brief branch",
        )
        self.assertLess(
            ret, cdot,
            "renderBrief() must `return;` before reaching `const c = b.counts;`",
        )


if __name__ == "__main__":
    unittest.main()
