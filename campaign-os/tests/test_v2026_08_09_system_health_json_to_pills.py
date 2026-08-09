"""
Regression test for the Agents & health "System health" card.

Bug: before this fix, renderAgents() appended `pretty(h.data_status)` to the
KV row. data_status is a plain STRING ("STALE" / "FRESH" / "MISSING"), not an
object. pretty() ran it through JSON.stringify(..., null, 2) and wrapped the
output in a <pre> block — wrong format (JSON dump of a string), wrong
affordance (a code-style box instead of a status pill), and it dropped three
other useful fields (priority, next_action, qa_warnings) that the payload
carried but the renderer ignored.

Fix: a new systemHealthHtml(h) function paints data_status + priority as
colour-mapped pills (FRESH=on/green, STALE=review/amber, MISSING/OFFLINE=
blocked/red, default=draft; HIGH/P0=warn/orange, MEDIUM/P1=review/amber,
LOW/P2/P3=draft), surfaces next_action as a one-line summary, and lists up
to 5 qa_warnings as a small <ul>. Returns "" when nothing renderable.

This is a read-only regression test — it never imports flask, never hits a
running server. It loads the HTML file as text and asserts structural markers.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML = REPO / "campaign-os" / "campaign-os.html"


def _read() -> str:
    assert HTML.exists(), f"campaign-os.html missing at {HTML}"
    return HTML.read_text(encoding="utf-8")


def _slice(src: str, start_marker: str, end_marker: str = "</script>") -> str:
    """Return the text between start_marker and the next </script>."""
    i = src.find(start_marker)
    assert i >= 0, f"marker not found: {start_marker!r}"
    j = src.find(end_marker, i)
    assert j > i, f"end marker not found after {start_marker!r}"
    return src[i:j]


def _function_body(src: str, fn_name: str) -> str:
    """Return the text of the named function body, balanced to its closing brace."""
    sig = f"function {fn_name}("
    i = src.find(sig)
    assert i >= 0, f"function {fn_name}() not found"
    # Find the first '{' after the signature (signature may span multiple lines)
    brace_open = src.find("{", i)
    assert brace_open > 0, f"opening brace not found for {fn_name}()"
    depth = 0
    k = brace_open
    while k < len(src):
        ch = src[k]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[i:k+1]
        k += 1
    raise AssertionError(f"closing brace not found for {fn_name}()")


# ─── presence ────────────────────────────────────────────────────


def test_systemHealthHtml_function_defined():
    """The fix introduces a new function systemHealthHtml in campaign-os.html."""
    src = _read()
    assert "function systemHealthHtml(" in src, (
        "Expected systemHealthHtml() function to exist in campaign-os.html — "
        "this is the fix that turns the raw JSON dump of data_status into "
        "colour-mapped pills + surfaced next_action + qa_warnings."
    )


def test_renderAgents_uses_systemHealthHtml_not_pretty():
    """renderAgents() must call systemHealthHtml(h), not pretty(h.data_status)."""
    src = _read()
    body = _slice(src, "async function renderAgents(){")
    assert "systemHealthHtml(h)" in body, (
        "renderAgents() must call systemHealthHtml(h) to render the "
        "System health extras below the Status/Confidence/Generated KV row."
    )
    assert "pretty(h.data_status)" not in body, (
        "renderAgents() must NOT call pretty(h.data_status) any more — "
        "that was the JSON-<pre>-dump bug this fix removes."
    )


def test_css_classes_for_system_health_extras_exist():
    """The new layout classes (.sh-extras, .sh-next, .sh-warn) must be styled."""
    src = _read()
    for cls in (".sh-extras", ".sh-next", ".sh-warn"):
        assert cls in src, f"Missing CSS class {cls} in campaign-os.html"


# ─── data_status pill colour mapping ─────────────────────────────


def test_data_status_pill_kind_branches():
    """systemHealthHtml must map FRESH → on, STALE → review, MISSING/OFFLINE/FAILED → blocked, default → draft."""
    src = _read()
    body = _function_body(src, "systemHealthHtml")
    # FRESH → on (green)
    m = re.search(r"if\(dsRaw === 'FRESH'\)\s*dsKind = 'on';", body)
    assert m, "Expected FRESH → 'on' pill kind"
    # STALE → review (amber)
    m = re.search(r"else if\(dsRaw === 'STALE'\)\s*dsKind = 'review';", body)
    assert m, "Expected STALE → 'review' pill kind"
    # MISSING / OFFLINE / FAILED → blocked (red)
    assert "'MISSING'" in body and "'OFFLINE'" in body and "'FAILED'" in body, (
        "Expected MISSING / OFFLINE / FAILED all mapped to blocked"
    )
    m = re.search(r"else if\(dsRaw === 'MISSING' \|\| dsRaw === 'OFFLINE' \|\| dsRaw === 'FAILED'\)\s*dsKind = 'blocked';", body)
    assert m, "Expected MISSING/OFFLINE/FAILED → 'blocked' pill kind"
    # default = draft (the initial assignment)
    assert "let dsKind = 'draft';" in body, "Expected default dsKind = 'draft'"


def test_data_status_pill_rendered_with_pill_class():
    """The data_status pill must use the standard pill class + kind."""
    src = _read()
    body = _function_body(src, "systemHealthHtml")
    assert re.search(r'<dd><span class="pill \$\{dsKind\}">\$\{esc\(dsRaw\)\}</span></dd>', body), (
        "Expected data_status rendered as <span class=pill dsKind>esc(dsRaw)</span>"
    )


# ─── priority pill colour mapping ─────────────────────────────────


def test_priority_pill_kind_branches():
    """systemHealthHtml must map HIGH/P0/URGENT → warn, MEDIUM/P1/NORMAL → review, LOW/P2/P3 → draft, default → draft."""
    src = _read()
    body = _function_body(src, "systemHealthHtml")
    assert "let prKind = 'draft';" in body, "Expected default prKind = 'draft'"
    assert "'HIGH'" in body and "'P0'" in body and "'URGENT'" in body, (
        "Expected HIGH/P0/URGENT branch"
    )
    assert "'MEDIUM'" in body and "'P1'" in body and "'NORMAL'" in body, (
        "Expected MEDIUM/P1/NORMAL branch"
    )
    assert "'LOW'" in body and "'P2'" in body and "'P3'" in body, (
        "Expected LOW/P2/P3 branch"
    )


def test_priority_pill_rendered_with_pill_class():
    """The priority pill must use the standard pill class + kind."""
    src = _read()
    body = _function_body(src, "systemHealthHtml")
    assert re.search(r'<dd><span class="pill \$\{prKind\}">\$\{esc\(prRaw\)\}</span></dd>', body), (
        "Expected priority rendered as <span class=pill prKind>esc(prRaw)</span>"
    )


# ─── next_action + qa_warnings surfacing ──────────────────────────


def test_next_action_surfaced_as_one_line():
    """systemHealthHtml must render h.next_action as a one-line summary when present."""
    src = _read()
    body = _function_body(src, "systemHealthHtml")
    assert "h.next_action" in body, "Expected next_action branch in systemHealthHtml"
    assert re.search(r"<b>Next:</b> \$\{esc\(h\.next_action\)\}", body), (
        "Expected <b>Next:</b> esc(h.next_action) in the rendered output"
    )


def test_qa_warnings_rendered_as_ul_limited_to_5():
    """systemHealthHtml must render h.qa_warnings as a <ul> capped at 5 items."""
    src = _read()
    body = _function_body(src, "systemHealthHtml")
    assert "h.qa_warnings" in body, "Expected qa_warnings branch"
    assert "Array.isArray(h.qa_warnings)" in body, "Expected Array.isArray guard on qa_warnings"
    assert ".slice(0,5)" in body, "Expected qa_warnings capped at 5 items"
    assert re.search(r"<ul>\$\{items\}</ul>", body), "Expected <ul> wrapper for warning items"


def test_no_renderer_output_when_payload_empty():
    """systemHealthHtml must return '' when nothing renderable — never an empty <dl>."""
    src = _read()
    body = _function_body(src, "systemHealthHtml")
    assert re.search(r"if\(!parts\.length && !extra\)\s*return '';", body), (
        "Expected empty-string return when no fields render"
    )


# ─── escaping + hygiene ───────────────────────────────────────────


def test_systemHealthHtml_escapes_user_fields():
    """All user-supplied fields must be passed through esc() — no raw HTML injection."""
    src = _read()
    body = _function_body(src, "systemHealthHtml")
    # dsRaw and prRaw get esc() in the template
    assert "esc(dsRaw)" in body and "esc(prRaw)" in body, (
        "Expected dsRaw + prRaw passed through esc()"
    )
    # next_action + qa_warnings items escaped
    assert "esc(h.next_action)" in body, "Expected esc(h.next_action)"
    assert "esc(String(w))" in body, "Expected esc(String(w)) for qa_warnings items"


def test_no_em_dash_added_in_system_health_renderer():
    """Standing rule: no em-dash in rendered output. Use colon / pipe / comma."""
    src = _read()
    body = _function_body(src, "systemHealthHtml")
    # Strip the JSDoc-style comment block (everything between /* and */ before the body)
    body_no_comments = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)
    body_no_comments = re.sub(r"//[^\n]*", "", body_no_comments)
    assert "\u2014" not in body_no_comments, (
        "Em-dash not allowed in systemHealthHtml body (outside comments)"
    )
    # confirm we used the allowed separators ("Next:" colon is fine)
    assert "<b>Next:</b>" in body, "Expected colon separator in <b>Next:</b>"


def test_guard_against_non_object_input():
    """systemHealthHtml must guard against null/non-object h and return '' safely."""
    src = _read()
    body = _function_body(src, "systemHealthHtml")
    assert "if(!h || typeof h !== 'object') return '';" in body, (
        "Expected null/non-object guard at top of systemHealthHtml"
    )


# ─── non-regression on the prior-lane fix ─────────────────────────


def test_agent_run_renderer_still_defined():
    """Sanity: yesterday's agentRunHtml fix must not have been removed."""
    src = _read()
    assert "function agentRunHtml(" in src, (
        "agentRunHtml() from the previous tick must still exist — "
        "this fix must not regress the Agent runs card."
    )