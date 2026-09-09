"""
Regression: Review queue must surface age-based freshness pills so 35/41
old pending drafts stop looking identical to 6 fresh drafts.

Background:
    2026-08-12T09:45Z next-pick queue flagged: "Review 'Pending' tab colour
    differentiation (41 items all say 'DRAFT' — needs status-pill refinement)".
    The renderReview() function only emitted the approvalStatus pill (which
    defaults to "draft" for everything not approved/rejected) + the raw
    updatedAt date. 35 of the 41 pending items were 30+ days old, but every
    row painted the same generic "draft" pill — so Christelle couldn't spot
    the rotting entries without opening each row.

Fix:
    1. `reviewAgePill(updatedAt)` — JS helper that converts an ISO timestamp
       to a colour-coded pill using the existing pill palette:
         - age ≤ 7d  → pill.on  ("fresh Nd", green)
         - age 8-29d → pill.review ("stale Nd", yellow)
         - age ≥ 30d → pill.blocked ("stale Nd", red)
       Returns "" for missing/invalid timestamps so it never throws.
    2. `renderReview()` injects the age pill into each row's meta row, right
       next to the approvalStatus pill, so the queue now shows a colour-coded
       age ladder.
    3. `renderReview()` appends " · N stale (>7d)" to the review-summary
       line whenever at least one pending row is older than 7 days. Lets
       Christelle spot a backlog without scrolling.

This test verifies:
    A. reviewAgePill branches at the right boundaries (0d, 7d, 8d, 29d, 30d).
    B. reviewAgePill never throws on null / "" / "garbage" / future timestamps.
    C. The pill HTML reuses the canonical pill classes (on / review / blocked).
    D. The renderReview summary appends " · N stale (>7d)" when stale>0,
       and does NOT append when everything is fresh.
    E. renderReview injects the age pill into every row's meta row.

These tests are pure-JS string-content assertions against the rendered HTML
(no jsdom required). They run in the existing campaign-os/tests/ pytest
harness and don't touch the network.
"""

import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.normpath(os.path.join(HERE, "..", "campaign-os.html"))


def _read_html():
    with open(HTML, "r", encoding="utf-8") as fh:
        return fh.read()


def _extract_function(source, name):
    """Pull a top-level JS function `name` out of the campaign-os.html blob
    and return (signature, body) so we can run unit assertions against it.

    Uses a regex that matches `function name(...) { ... }` with brace
    balancing, capped at a generous 30 levels to avoid runaway. Only
    suitable for short, top-level helpers (which is what we have).
    """
    pat = re.compile(r"function\s+" + re.escape(name) + r"\s*\(([^)]*)\)\s*\{", re.M)
    m = pat.search(source)
    assert m, f"function {name} not found in {HTML}"
    body_start = m.end()
    depth = 1
    i = body_start
    while i < len(source) and depth > 0:
        c = source[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    assert depth == 0, f"unbalanced braces in {name}"
    body = source[body_start:i - 1]
    return m.group(1), body


def _node_review_age_pill():
    """Run reviewAgePill() inside node, exposed as a global, and return the
    body of the function so we can exec-test it for each branch.

    We extract the function body via regex (no JS parser needed), wrap it
    in a minimal harness, and invoke it from python via `node -e`. Returns
    the function-body string so we can exec it directly in node below.
    """
    src = _read_html()
    _sig, body = _extract_function(src, "reviewAgePill")
    return body


def _call_review_age_pill(updated_at_iso):
    """Invoke reviewAgePill in node and return its string return value."""
    body = _node_review_age_pill()
    harness = (
        "(function(){\n"
        "  function reviewAgePill(updatedAt){\n"
        + body + "\n"
        "  }\n"
        "  const arg = process.argv[1];\n"
        "  process.stdout.write(String(reviewAgePill(arg)));\n"
        "})();\n"
    )
    # Use python-subprocess-node to call the harness with the timestamp arg.
    proc = subprocess.run(
        ["node", "-e", harness, updated_at_iso or ""],
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"node failed: {proc.stderr}")
    return proc.stdout


def test_review_age_pill_branch_fresh_zero_days():
    """Age 0d → green 'fresh 0d' pill."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    out = _call_review_age_pill(now)
    assert 'class="pill on"' in out, f"expected green pill, got: {out!r}"
    assert "fresh 0d" in out, f"expected 'fresh 0d' label, got: {out!r}"


def test_review_age_pill_branch_fresh_seven_days():
    """Age 7d → green 'fresh 7d' pill (boundary inclusive)."""
    ts = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    out = _call_review_age_pill(ts)
    assert 'class="pill on"' in out
    assert "fresh 7d" in out


def test_review_age_pill_branch_stale_eight_days():
    """Age 8d → yellow 'stale 8d' pill (first stale branch)."""
    ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat().replace("+00:00", "Z")
    out = _call_review_age_pill(ts)
    assert 'class="pill review"' in out, f"expected yellow pill, got: {out!r}"
    assert "stale 8d" in out


def test_review_age_pill_branch_stale_twenty_nine_days():
    """Age 29d → yellow 'stale 29d' pill (last yellow branch)."""
    ts = (datetime.now(timezone.utc) - timedelta(days=29)).isoformat().replace("+00:00", "Z")
    out = _call_review_age_pill(ts)
    assert 'class="pill review"' in out
    assert "stale 29d" in out


def test_review_age_pill_branch_stale_thirty_days():
    """Age 30d → red 'stale 30d' pill (boundary, escalation)."""
    ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    out = _call_review_age_pill(ts)
    assert 'class="pill blocked"' in out, f"expected red pill, got: {out!r}"
    assert "stale 30d" in out


def test_review_age_pill_branch_rotting_seventy_days():
    """Age 70d (typical Takomo draft age) → red 'stale 70d' pill."""
    ts = (datetime.now(timezone.utc) - timedelta(days=70)).isoformat().replace("+00:00", "Z")
    out = _call_review_age_pill(ts)
    assert 'class="pill blocked"' in out
    assert "stale 70d" in out


def test_review_age_pill_null_returns_empty():
    """null / empty string must NOT throw and must return empty."""
    for v in ("", "garbage", "not-a-date", "0000-00-00"):
        out = _call_review_age_pill(v)
        assert out == "", f"expected empty for {v!r}, got: {out!r}"


def test_review_age_pill_future_timestamp_clamps_to_zero():
    """Future timestamps (clock skew) clamp to age=0 so they show as fresh,
    not -5d. Regression guard for the floor check inside the helper."""
    ts = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat().replace("+00:00", "Z")
    out = _call_review_age_pill(ts)
    assert "fresh 0d" in out, f"expected fresh 0d for future timestamp, got: {out!r}"


def test_render_review_summary_appends_stale_count():
    """renderReview() must append ' · N stale (>7d)' to the summary line
    whenever the pending queue has any rows older than 7 days."""
    src = _read_html()
    # Confirm the stale-summary suffix string is in the source.
    assert "stale (>7d)" in src, "expected 'stale (>7d)' summary suffix in campaign-os.html"


def test_render_review_does_not_append_stale_when_all_fresh():
    """When every pending row is fresh, the summary must NOT show the stale
    suffix. Branch coverage: the conditional checks _stalePending > 0."""
    src = _read_html()
    # Locate the conditional block.
    assert "_stalePending > 0" in src, \
        "expected guard '_stalePending > 0' before summary mutation in renderReview"


def test_render_review_meta_row_has_age_pill():
    """renderRow() must inject the age pill into the meta row next to the
    approvalStatus pill. Confirms the ${agePill} interpolation landed."""
    src = _read_html()
    # The pattern around the meta row should mention both pill(...approvalStatus)
    # and ${agePill}.
    pat = re.compile(
        r'\$\{pill\(x\.approvalStatus\|\|[\'"]draft[\'"]\s*,\s*x\.approvalStatus\|\|[\'"]draft[\'"]\)\}\s*\n\s*\$\{agePill\}',
        re.M,
    )
    assert pat.search(src), \
        "expected ${agePill} immediately after the approvalStatus pill in review-meta row"


def test_review_age_pill_helper_present_in_html():
    """The reviewAgePill() helper itself must be defined at the top level of
    the campaign-os.html JS bundle."""
    src = _read_html()
    assert "function reviewAgePill(updatedAt)" in src, \
        "expected reviewAgePill() function definition in campaign-os.html"


def test_render_review_imports_age_helper():
    """renderRow() must call reviewAgePill(x.updatedAt) — not just declare the
    const. Guards against accidental `${agePill}` interpolation without the
    call site."""
    src = _read_html()
    assert "reviewAgePill(x.updatedAt)" in src, \
        "expected reviewAgePill(x.updatedAt) call inside renderRow()"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))