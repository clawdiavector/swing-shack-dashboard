"""
Tests for the Ideas "missed-opportunities" and "funnel-leaks" empty-state cards.

Background: prior to the fix, both cards fell through to a generic
'<div class="empty">Nothing here</div>' fallback in renderList(). For
those two cards specifically, "nothing here" reads like a bug because:

- ideas-missed (Trends that already peaked and the brand did not post):
  empty is POSITIVE — the brand kept up with every trend.
- ideas-funnel (Pages that get traffic but fail to convert):
  empty is USUALLY DATA-DRIVEN — funnel-leaks.json needs GA4 page-view
  + conversion events; usually empty because GA4 is not connected.

Fix: special-case the two renderList() calls so they emit distinct
friendly empty cards (renderMissedEmpty, renderFunnelEmpty) when the
source array is empty. Other 5 cards keep the generic renderList().

These tests parse the campaign-os.html source to verify the JS source
shape — they don't run the browser. They guard against:
1. Reverting the special case to the generic renderList() call
2. Removing the friendly empty-state helpers entirely
3. Removing the "No missed opportunities" / "No funnel leaks detected"
   friendly copy
4. Hard-coding an empty array (which would skip the empty state)
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "campaign-os.html"
SRC = HTML.read_text(encoding="utf-8")


def _slice_render_ideas() -> str:
    """Return the slice of campaign-os.html that defines renderIdeas."""
    # Find the function body of renderIdeas
    m = re.search(r"function\s+renderIdeas\s*\([^)]*\)\s*\{", SRC)
    assert m, "renderIdeas function not found in campaign-os.html"
    start = m.start()
    # Walk braces to find the matching close
    depth = 0
    i = m.end() - 1  # at the opening {
    while i < len(SRC):
        ch = SRC[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return SRC[start : i + 1]
        i += 1
    raise AssertionError("renderIdeas body not closed")


def test_missed_special_case_exists():
    body = _slice_render_ideas()
    assert "renderMissedEmpty" in body, "renderMissedEmpty helper must exist for ideas-missed"
    assert re.search(
        r"#ideas-missed'\)\.innerHTML\s*=\s*\(d\.missed\s*&&\s*d\.missed\.length\)",
        body,
    ), "ideas-missed must short-circuit to renderMissedEmpty() when d.missed is empty"


def test_funnel_special_case_exists():
    body = _slice_render_ideas()
    assert "renderFunnelEmpty" in body, "renderFunnelEmpty helper must exist for ideas-funnel"
    assert re.search(
        r"#ideas-funnel'\)\.innerHTML\s*=\s*\(d\.funnel_leaks\s*&&\s*d\.funnel_leaks\.length\)",
        body,
    ), "ideas-funnel must short-circuit to renderFunnelEmpty() when d.funnel_leaks is empty"


def test_missed_empty_copy_is_friendly():
    body = _slice_render_ideas()
    m = re.search(r"renderMissedEmpty\s*=\s*\(\)\s*=>\s*\{(.*?)\};", body, re.DOTALL)
    assert m, "renderMissedEmpty arrow function body not found"
    inner = m.group(1)
    assert "No missed opportunities" in inner, "must keep the friendly 'No missed opportunities' heading"
    # Encourage a positive framing (vs. the old "Nothing here")
    assert re.search(r"kept up|already has a post|peak", inner, re.IGNORECASE), (
        "renderMissedEmpty should frame the empty state positively (kept up / peaked)"
    )


def test_funnel_empty_copy_is_friendly():
    body = _slice_render_ideas()
    m = re.search(r"renderFunnelEmpty\s*=\s*\(\)\s*=>\s*\{(.*?)\};", body, re.DOTALL)
    assert m, "renderFunnelEmpty arrow function body not found"
    inner = m.group(1)
    assert "No funnel leaks detected" in inner, "must keep the friendly 'No funnel leaks detected' heading"
    # Must explain the GA4 dependency and surface the next step.
    # Point users at the /ga4 setup-portal (NOT /meta — /meta is for
    # Instagram/Facebook; funnel-leaks feeds on GA4 specifically).
    assert "GA4" in inner, "renderFunnelEmpty must mention the GA4 dependency"
    assert "setup-portal" in inner, "renderFunnelEmpty should point users at the setup-portal"
    assert "/ga4" in inner, "renderFunnelEmpty must point at /ga4 (GA4 setup-portal), not /meta"


def test_other_ideas_cards_kept_generic():
    """The other 5 Ideas cards must still use renderList() (no churn)."""
    body = _slice_render_ideas()
    # Cards that must stay on renderList(): ideas-list, ideas-today, ideas-week, ideas-upsell, ideas-bundles, ideas-landing
    for cid in ("ideas-list", "ideas-today", "ideas-week", "ideas-upsell", "ideas-bundles", "ideas-landing"):
        assert re.search(rf"#{cid}'\)\.innerHTML\s*=\s*renderList\(", body), (
            f"{cid} must keep the generic renderList() path; the friendly-state change targets only ideas-missed and ideas-funnel"
        )


def test_no_double_assignment():
    """The two cards must have exactly ONE assignment (no fallback re-assignment)."""
    body = _slice_render_ideas()
    for cid in ("ideas-missed", "ideas-funnel"):
        assignments = re.findall(rf"#{cid}'\)\.innerHTML\s*=", body)
        assert len(assignments) == 1, (
            f"{cid} must have exactly one innerHTML assignment; found {len(assignments)} (likely the generic fallback re-stamped over the friendly card)"
        )


def test_no_em_dash_in_published_copy():
    """Standing rule: no em-dash in published copy. New copy is published (visible daily)."""
    body = _slice_render_ideas()
    for fn_name in ("renderMissedEmpty", "renderFunnelEmpty"):
        m = re.search(rf"{fn_name}\s*=\s*\(\)\s*=>\s*\{{(.*?)\}};", body, re.DOTALL)
        assert m, f"{fn_name} body not found"
        inner = m.group(1)
        assert "—" not in inner, (
            f"{fn_name} contains an em-dash — banned in published copy per the standing rule"
        )
