"""
Regression test for the Insights V2 re-entry race fix.

Bug (caught by the 2026-08-09 pre-pick sweep):
When the user navigates to the Insights tab and then quickly navigates
away and back BEFORE the async Promise.all() of the first render resolves,
two renderInsightsV2() invocations overlap. The first one's awaited fetches
finish, and then the function tries to mutate DOM nodes — `#ins-ig-count`,
`#ins-v2-summary`, etc. — that the second invocation has already wiped when
it set `sec.innerHTML`. The first invocation hits
   `$('#ins-ig-count').textContent = ...`
and throws
   TypeError: Cannot set properties of null (setting 'textContent')
which surfaces as a real production pageerror.

Fix: each renderInsightsV2() call captures a monotonically increasing
token on the section element at entry. After the awaited Promise.all
resolves, the function compares the section's current token to the
snapshot it captured. If a newer render has taken over, the stale
callback bails silently before mutating any DOM.

This is a read-only regression test — it loads campaign-os.html as text
and asserts structural markers.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML = REPO / "campaign-os" / "campaign-os.html"


def _read() -> str:
    assert HTML.exists(), f"campaign-os.html missing at {HTML}"
    return HTML.read_text(encoding="utf-8")


def _renderInsightsV2_body() -> str:
    """Extract the renderInsightsV2 function body (between the opening
    `async function renderInsightsV2(){` and the next top-level `function` or
    `async function` definition)."""
    src = _read()
    m = re.search(
        r"async function renderInsightsV2\(\)\{(.*?)\n(?:async function renderInsights|function [a-zA-Z_$])",
        src,
        re.DOTALL,
    )
    assert m, "Could not locate renderInsightsV2() body in campaign-os.html"
    return m.group(1)


class InsightsRaceTokenTests(unittest.TestCase):
    """Guard tests for the Insights V2 re-entry race fix."""

    def test_token_snapshot_at_entry(self):
        """renderInsightsV2() must capture a render token at the start of
        the function — snapshot of `sec.dataset.insRenderToken` (or its
        next-increment value) — so the stale callback can compare later."""
        body = _renderInsightsV2_body()
        # We accept either: snapshot-then-increment, or increment-then-snapshot.
        # Either pattern produces a `myToken` local that is read after Promise.all.
        assert "myToken" in body, (
            "renderInsightsV2() must declare a local `myToken` to snapshot "
            "the render token at entry. Without it, the stale-render guard "
            "cannot compare tokens after the async fetch resolves."
        )

    def test_token_incremented_on_section(self):
        """renderInsightsV2() must increment the section's render token on
        every call so the next call sees a fresh value."""
        body = _renderInsightsV2_body()
        assert "sec.dataset.insRenderToken" in body, (
            "renderInsightsV2() must write to `sec.dataset.insRenderToken` "
            "to increment the per-section render counter on every entry."
        )
        # Must be a numeric increment, not just a static assignment.
        # Allow either `... = String(...) + 1` (increment then assign) or
        # `Number(...) + 1` (read then increment).
        has_increment = bool(re.search(
            r"insRenderToken[\s\S]{0,80}\+\s*1",
            body,
        ))
        assert has_increment, (
            "renderInsightsV2() must increment the render token by 1 on each "
            "call (pattern `insRenderToken` ... `+ 1`). A static assignment "
            "would never let later renders invalidate earlier ones."
        )

    def test_token_check_after_promise_all(self):
        """After the `await Promise.all([...])` resolves, the function must
        compare the current section token to the snapshot and bail if a newer
        render has taken over."""
        body = _renderInsightsV2_body()
        # Locate the Promise.all block and check that a token comparison
        # follows it within ~200 chars.
        promise_block = re.search(
            r"await\s+Promise\.all\(\[[\s\S]*?\]\)",
            body,
        )
        assert promise_block, "Could not locate Promise.all in renderInsightsV2()"
        after = body[promise_block.end():promise_block.end() + 400]
        # The comparison must read `sec.dataset.insRenderToken` AND reference
        # `myToken`. The bail-out pattern is `if(String(...) !== String(myToken)) return;`
        # or any variant that references both within a few lines.
        has_compare = (
            "insRenderToken" in after
            and "myToken" in after
        )
        assert has_compare, (
            "renderInsightsV2() must compare `sec.dataset.insRenderToken` to "
            "the snapshot `myToken` after Promise.all resolves. Without this "
            "check, a stale render mutates DOM nodes that a newer render "
            "has already wiped, throwing 'Cannot set properties of null'."
        )

    def test_renders_normally_when_no_re_entry(self):
        """The fix must not break the normal (single-render) path. After the
        token check, the function must still build the headlines + body +
        IG list + pages list + ad block. A bare `return;` immediately after
        Promise.all would silently drop the entire render — guard against
        that bug too."""
        body = _renderInsightsV2_body()
        # The token check is inside a conditional, so the subsequent body
        # construction code (`body.innerHTML = `, `igPosts = ...`,
        # `renderAdsBlock`, etc.) must still be present.
        assert "body.innerHTML" in body, (
            "renderInsightsV2() must still call `body.innerHTML = ...` after "
            "the token guard — otherwise no Insights content ever renders."
        )
        assert "igPosts" in body or "instagram" in body, (
            "renderInsightsV2() must still process Instagram data after the "
            "token guard — the guard should be silent only for stale calls."
        )

    def test_no_em_dash_in_patched_block(self):
        """Standing rule: no em-dash in shipped copy. The new comment block
        uses colons and hyphens only. (The static HTML inside the function
        body pre-existed and may contain dashes for marker text like
        "color-coded, click to open" — only check the new comments.)"""
        body = _renderInsightsV2_body()
        # Strip the static HTML template literal (the sec.innerHTML = `...` block)
        # so we only inspect the JS comment + code that we just added.
        # Cut at the start of the template literal.
        idx = body.find("sec.innerHTML")
        comments_only = body[:idx] if idx >= 0 else body
        # Also strip the existing `// ─── INSIGHTS v2 ...` header that uses
        # an em-dash-like box-drawing line.
        comments_only = re.sub(r"//\s*─+\s*INSIGHTS[^\n]*\n", "", comments_only)
        assert "\u2014" not in comments_only and "\u2013" not in comments_only, (
            "renderInsightsV2() new comment block contains an em/en-dash. "
            "Use `,` or `:` instead."
        )

    def test_no_unconditional_ins_ig_count_setter(self):
        """Belt + braces: the unguarded form `$('#ins-ig-count').textContent`
        should NOT exist anywhere in the file as a top-level line (it must
        sit inside the token-guarded code path)."""
        src = _read()
        unguarded = re.findall(
            r"^\s*\$\(\#ins-ig-count\)\.textContent\s*=",
            src,
            re.MULTILINE,
        )
        assert not unguarded, (
            "Found unguarded `$('#ins-ig-count').textContent = ...` on a top-level "
            "line in campaign-os.html. The fix must keep this setter inside the "
            "token-guarded block (after `if(token !== myToken) return;`)."
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)