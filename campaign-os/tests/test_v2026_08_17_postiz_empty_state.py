"""v2026-08-17: Postiz Queue empty state must be actionable, not just "Queue empty".

Pre-pick sweep on the LIVE Postiz page showed `p.queue` returning 0 items
(`Publishing refs: 1. Queue: 0. Scheduled: 0. Published: 20 (21 total).`) and
the Queue card collapsed to a single italic grey line: "Queue empty". The
Review inbox at the time held 41 pending drafts, but the Postiz surface gave
the user no path from the empty state back to the inbox to approve one.
That's the exact "dead grey line when there is a one-click path to fill it"
pattern that earlier fixes (BB_EMPTY, the Calendar empty-state) had already
replaced elsewhere on the dashboard.

This test pins the new shape: when `p.queue` is empty, the renderer must
emit a home-empty-state (matching the .cal-empty-icon / .cal-empty-title /
.cal-empty-sub / .cal-empty-ctas pattern used by the Calendar + Billboards
empty states) and must NOT fall back to the bare "Queue empty" string.

Tests
-----
1. Old flat-fallback string "Queue empty" is gone from renderPostiz.
2. The new helper variable `postizQueueEmptyHtml` is referenced inside
   the `||` short-circuit (i.e. it is the new fallback, not dead code).
3. Both branches are present: the review-pointer branch (when Review has
   pending drafts) and the generate-fresh branch (when Review is empty).
4. Both branches use the .home-empty-state class (so the calendar empty
   styles apply uniformly).
5. Both branches carry an inline CTA button with `onclick="go('...')"`
   (so the empty state is actionable, not decorative).
6. No new em-dash introduced in either copy line (em-dash banned rule).
7. The "Open Review" button copy carries the live pending count via
   `${pendingCount}` interpolation (so the user sees the actual backlog).
8. The "Queue empty" fallback HTML literal `'<div class="empty">Queue
   empty</div>'` is gone from renderPostiz entirely.
"""

import os
import re
import sys
import unittest


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML_PATH = os.path.join(REPO_ROOT, "campaign-os", "campaign-os.html")


def _load_html() -> str:
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _render_postiz_block(html: str) -> str:
    """Pull out the renderPostiz function body (everything between the
    function opener and its closing brace). Best-effort string slice from
    the first line that declares the function to its matching brace pair,
    falling back to a generous window if the brace counting is brittle.
    """
    start = html.find("async function renderPostiz")
    if start == -1:
        raise AssertionError("renderPostiz() not found in campaign-os.html")
    # Walk braces from the first { after the function signature.
    brace_open = html.find("{", start)
    if brace_open == -1:
        raise AssertionError("renderPostiz() opener brace not found")
    depth = 0
    for i in range(brace_open, len(html)):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return html[brace_open : i + 1]
    raise AssertionError("renderPostiz() closing brace not found")


class PostizEmptyStateTests(unittest.TestCase):
    """Static regression tests for the new actionable Postiz Queue empty state."""

    @classmethod
    def setUpClass(cls):
        cls.html = _load_html()
        cls.fn = _render_postiz_block(cls.html)

    def test_old_flat_fallback_string_gone(self):
        """The bare `<div class="empty">Queue empty</div>` fallback must be
        gone from renderPostiz so the dead-grey line can't resurface.
        """
        self.assertNotIn(
            '<div class="empty">Queue empty</div>',
            self.fn,
            "renderPostiz still emits the flat 'Queue empty' div. "
            "Replace with the home-empty-state HTML so the empty card is actionable.",
        )

    def test_new_helper_variable_used_as_fallback(self):
        """The new helper variable must be the fallback (after `||`) for
        the queue .map().join('') result. Without this, the renderer would
        still produce an empty string and the empty-state markup would
        never reach the DOM.
        """
        # Find the `$('#postiz-queue').innerHTML = safeList(p.queue, 20).map(...)`
        # block, then assert the `|| postizQueueEmptyHtml` fallback is right
        # after the .join('') close-paren.
        m = re.search(
            r"\$\('#postiz-queue'\)\.innerHTML\s*=\s*safeList\(p\.queue,\s*20\)\.map\([\s\S]*?\)\.join\(''\)\s*\|\|\s*([A-Za-z_][A-Za-z0-9_]*)\s*;",
            self.fn,
        )
        self.assertIsNotNone(
            m,
            "Could not find `$('#postiz-queue').innerHTML = safeList(...).join('') || X;` "
            "in renderPostiz. The new fallback variable must be wired as the `||` RHS.",
        )
        rhs = m.group(1) if m else ""
        self.assertEqual(
            rhs, "postizQueueEmptyHtml",
            "Fallback RHS should be postizQueueEmptyHtml (the new helper). Got: %s" % rhs,
        )

    def test_helper_variable_defined_with_two_branches(self):
        """The postizQueueEmptyHtml helper must be defined with both the
        review-pointer branch (when pendingCount > 0) AND the
        generate-fresh branch (else). Otherwise one user segment sees the
        flat empty state.
        """
        self.assertIn(
            "let postizQueueEmptyHtml = ''",
            self.fn,
            "Helper variable postizQueueEmptyHtml not declared.",
        )
        self.assertIn(
            "if (pendingCount > 0)",
            self.fn,
            "Review-pointer branch (pendingCount > 0) not present.",
        )
        self.assertIn(
            "Open Review (${pendingCount})",
            self.fn,
            "Open Review CTA must interpolate pendingCount so the user sees the live backlog.",
        )
        self.assertIn(
            "Generate new post",
            self.fn,
            "Generate-fresh fallback CTA missing.",
        )

    def test_branches_use_home_empty_state_class(self):
        """Both empty-state HTML strings must use the .home-empty-state
        class so the unified empty-state styles apply (icon + title +
        sub + CTA buttons centered in a dashed card).
        """
        branches = re.findall(r'<li class="empty home-empty-state"[^>]*>', self.fn)
        self.assertGreaterEqual(
            len(branches), 2,
            "Expected >= 2 .home-empty-state branches (review + blank). Found %d." % len(branches),
        )

    def test_branches_carry_inline_go_cta(self):
        """Both branches must carry an inline CTA that calls go(...) so
        the user is one click from filling the queue.
        """
        ctas = re.findall(r'onclick="go\(\'([A-Za-z]+)\'\)"', self.fn)
        # review-pointer: go('review') + go('calendar') -> 2
        # generate-fresh: go('create') + go('review') -> 2
        # Total expected: >= 4 distinct CTA clicks across both branches.
        self.assertGreaterEqual(
            len(ctas), 4,
            "Expected >= 4 inline go(...) CTAs across both empty-state branches. "
            "Found %d." % len(ctas),
        )
        # Review branch must include go('review') + go('calendar')
        # Generate branch must include go('create') + go('review')
        self.assertIn("review", ctas)
        self.assertIn("calendar", ctas)
        self.assertIn("create", ctas)

    def test_no_new_emdash_in_copy(self):
        """Em-dash banned in published copy. Both branches render to the
        browser as visible copy, so any em-dash would surface.
        """
        # Pull just the template-literal copy out of the helper. The two
        # templates are the only `.empty-sub` lines.
        subs = re.findall(r'<div class="cal-empty-sub">(.*?)</div>', self.fn, flags=re.DOTALL)
        self.assertGreaterEqual(len(subs), 2)
        for s in subs:
            self.assertNotIn(
                "\u2014", s,
                "Em-dash found in new Postiz empty-state copy. Replace with : or (): " + s[:80],
            )
            # Also catch the legacy en-dash while we're here
            self.assertNotIn(
                "\u2013", s,
                "En-dash found in new Postiz empty-state copy. Replace with : or (): " + s[:80],
            )

    def test_pending_count_is_interpolated_into_review_cta(self):
        """The 'Open Review (N)' CTA must interpolate pendingCount (not a
        hard-coded literal) so the empty state matches the live backlog.
        Otherwise"""
        self.assertIn(
            "Open Review (${pendingCount})",
            self.fn,
            "Review CTA must use ${pendingCount} interpolation so the backlog number is live.",
        )


if __name__ == "__main__":
    unittest.main()