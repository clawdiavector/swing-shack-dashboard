"""
Regression test for the Agents & health "Agent runs" card.

Bug: before this fix, renderAgents() called safeList(a.agents, 20).map(itemHtml)
and the generic itemHtml() couldn't find a title-worthy field in the agent
object ({agent_id, last_run, last_status, runs}), so it fell back to
JSON.stringify(it).slice(0,80). The Agents tab showed rows of raw JSON like
{"agent_id":"pulse_keeper","last_run":null,...} instead of readable cards.

Fix: agentRunHtml(it) knows the agent shape and paints it as
<agent_id> · <N runs total> · last <age> · <status pill>.

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


def test_agentRunHtml_function_defined():
    """The fix introduces a new function agentRunHtml in campaign-os.html."""
    src = _read()
    assert "function agentRunHtml(" in src, (
        "Expected agentRunHtml() function to exist in campaign-os.html — "
        "this is the fix that turns raw JSON agent records into readable rows."
    )


def test_renderAgents_uses_agentRunHtml_not_itemHtml():
    """renderAgents() must call agentRunHtml on a.agents, not itemHtml."""
    src = _read()
    # Find the body of renderAgents()
    m = re.search(r"async function renderAgents\(\)\{(.+?)\n\}", src, re.DOTALL)
    assert m, "Could not locate renderAgents() body"
    body = m.group(1)
    assert "safeList(a.agents" in body, "renderAgents must slice a.agents via safeList"
    assert ".map(agentRunHtml)" in body, (
        "renderAgents must call agentRunHtml() to render each agent record — "
        "falling back to itemHtml() dumps raw JSON for the agent shape."
    )
    assert ".map(itemHtml)" not in body.split("#agents-list")[1].split(";")[0], (
        "agents-list row render path must NOT use itemHtml — that's the original bug."
    )


def test_agentRunHtml_renders_status_pill():
    """The new renderer must emit a status pill with the agent's last_status."""
    src = _read()
    m = re.search(r"function agentRunHtml\((.+?)\n\}", src, re.DOTALL)
    assert m, "agentRunHtml function not found"
    body = m.group(1)
    assert "pill" in body, "agentRunHtml must paint a status pill"
    assert "last_status" in body, "agentRunHtml must read last_status from the agent record"


def test_agentRunHtml_renders_runs_count():
    """The new renderer must show the runs total in human-readable form."""
    src = _read()
    m = re.search(r"function agentRunHtml\((.+?)\n\}", src, re.DOTALL)
    assert m, "agentRunHtml function not found"
    body = m.group(1)
    assert "runs" in body, "agentRunHtml must surface the runs count"
    # Should pluralise: 1 run vs N runs
    assert "run' : 'runs" in body or "'runs'" in body, (
        "agentRunHtml must pluralise 'run'/'runs' so 1 vs 2+ reads naturally."
    )


def test_agentRunHtml_renders_age_in_words():
    """last_run (ISO or null) must be rendered as human-readable age."""
    src = _read()
    m = re.search(r"function agentRunHtml\((.+?)\n\}", src, re.DOTALL)
    assert m, "agentRunHtml function not found"
    body = m.group(1)
    assert "ago" in body, "agentRunHtml must produce a human-readable age (Xm ago / Xh ago / Xd ago)"
    assert "never" in body, "agentRunHtml must say 'never' when last_run is null"


def test_no_em_dash_added_in_new_agent_run_renderer():
    """Standing rule: no em-dashes in published copy. Code comments can use → arrows
    (which is a different unicode codepoint, U+2192) but em-dashes (U+2014) are banned."""
    src = _read()
    m = re.search(r"function agentRunHtml\((.+?)\n\}", src, re.DOTALL)
    assert m, "agentRunHtml function not found"
    body = m.group(1)
    assert "—" not in body and "\u2014" not in body, (
        "agentRunHtml must NOT use em-dashes (U+2014) — standing rule. Use pipes/commas/colons or → arrows."
    )


def test_agentRunHtml_escapes_user_fields():
    """agent_id and last_status flow from API → must be HTML-escaped."""
    src = _read()
    m = re.search(r"function agentRunHtml\((.+?)\n\}", src, re.DOTALL)
    assert m, "agentRunHtml function not found"
    body = m.group(1)
    assert "esc(it.agent_id" in body, "agent_id must be escaped"
    assert "esc(status" in body, "status must be escaped"


def test_status_pill_color_mapping():
    """PARTIAL → review (amber), FAIL → blocked (red), PASS → on (green)."""
    src = _read()
    m = re.search(r"function agentRunHtml\((.+?)\n\}", src, re.DOTALL)
    assert m, "agentRunHtml function not found"
    body = m.group(1)
    # Three branches by status
    assert "PARTIAL" in body and "review" in body, "PARTIAL must map to review pill"
    assert ("FAIL" in body and "blocked" in body) or (
        "FAILED" in body and "blocked" in body
    ), "FAIL must map to blocked pill"
    # Default on (green) for PASS — verify 'on' is the default pillKind
    assert "let pillKind" in body and "'on'" in body, "PASS must default to on pill (green)"


if __name__ == "__main__":
    tests = [
        test_agentRunHtml_function_defined,
        test_renderAgents_uses_agentRunHtml_not_itemHtml,
        test_agentRunHtml_renders_status_pill,
        test_agentRunHtml_renders_runs_count,
        test_agentRunHtml_renders_age_in_words,
        test_no_em_dash_added_in_new_agent_run_renderer,
        test_agentRunHtml_escapes_user_fields,
        test_status_pill_color_mapping,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(0 if failed == 0 else 1)