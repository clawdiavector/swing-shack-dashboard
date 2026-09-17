"""
Regression test for the Agents & health "Campaign OS fleet" card.

Before this fix, renderAgents() called safeList(a.agents, 24).map(agentRunHtml)
on the legacy /api/intel/agents lane roster (pulse_keeper, data_harvester, etc.).

Fix: renderAgents() fetches GET /api/ops/agents for the fleet list card and
cosAgentHtml() paints each cos-* row with heartbeat, schedule, and ops link.
/api/intel/agents is still fetched for system_health + integration_health only.

Read-only regression test — never imports flask, never hits a running server.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML = REPO / "campaign-os" / "campaign-os.html"


def _read() -> str:
    assert HTML.exists(), f"campaign-os.html missing at {HTML}"
    return HTML.read_text(encoding="utf-8")


def _render_agents_body(src: str) -> str:
    m = re.search(r"async function renderAgents\(\)\{(.+?)\n\}", src, re.DOTALL)
    assert m, "Could not locate renderAgents() body"
    return m.group(1)


def test_cosAgentHtml_function_defined():
    """The fix introduces cosAgentHtml() for the ops fleet roster."""
    src = _read()
    assert "function cosAgentHtml(" in src, (
        "Expected cosAgentHtml() in campaign-os.html for the Campaign OS fleet card."
    )


def test_renderAgents_fetches_ops_agents_for_fleet_list():
    """renderAgents() must fetch /api/ops/agents for the fleet list card."""
    body = _render_agents_body(_read())
    assert "/api/ops/agents" in body, (
        "renderAgents must fetch GET /api/ops/agents for the Campaign OS fleet roster."
    )
    assert "S.cosFleet" in body, "renderAgents must cache the ops fleet payload on S.cosFleet"


def test_renderAgents_uses_cosAgentHtml_not_intel_agents_list():
    """renderAgents() must render S.cosFleet.agents via cosAgentHtml, not intel a.agents."""
    body = _render_agents_body(_read())
    assert ".map(cosAgentHtml)" in body, (
        "renderAgents must call cosAgentHtml() on the ops fleet list."
    )
    assert "safeList(a.agents" not in body, (
        "renderAgents must NOT render a.agents from /api/intel/agents for the fleet card."
    )
    assert ".map(agentRunHtml)" not in body.split("#agents-list")[0], (
        "renderAgents must NOT call agentRunHtml on the fleet list."
    )


def test_renderAgents_still_fetches_intel_for_health():
    """renderAgents() must still fetch /api/intel/agents for system + integration health."""
    body = _render_agents_body(_read())
    assert "/api/intel/agents" in body, (
        "renderAgents must still fetch /api/intel/agents for system_health + integration_health."
    )
    assert "systemHealthHtml(h)" in body, "system health card must still render via systemHealthHtml"
    assert "integrationHealthHtml" in body, "integration health card must still render"


def test_cosAgentHtml_renders_status_pill():
    """cosAgentHtml() must emit a fleet status pill from last_status."""
    src = _read()
    m = re.search(r"function cosAgentHtml\((.+?)\n\}", src, re.DOTALL)
    assert m, "cosAgentHtml function not found"
    body = m.group(1)
    assert "pill" in body, "cosAgentHtml must paint a status pill"
    assert "last_status" in body, "cosAgentHtml must read last_status from the ops agent record"


def test_cosAgentHtml_renders_fleet_fields():
    """cosAgentHtml() must surface id, kind, layer, schedule, enabled, heartbeat, writes, skill."""
    src = _read()
    m = re.search(r"function cosAgentHtml\((.+?)\n\}", src, re.DOTALL)
    assert m, "cosAgentHtml function not found"
    body = m.group(1)
    for field in ("a.id", "a.kind", "a.layer", "a.schedule", "a.enabled", "last_heartbeat_at", "last_writes", "a.skill", "last_action"):
        assert field in body, f"cosAgentHtml must reference {field}"


def test_cosAgentHtml_renders_ops_link():
    """cosAgentHtml() must link rows to /ops?layer=agents&agent=<id>."""
    src = _read()
    m = re.search(r"function cosAgentHtml\((.+?)\n\}", src, re.DOTALL)
    assert m, "cosAgentHtml function not found"
    body = m.group(0)
    assert "/ops?layer=agents&agent=" in body, (
        "cosAgentHtml must emit a drill-down link to ops for each agent row."
    )


def test_cosAgentHtml_emits_li_detail_block():
    """cosAgentHtml() must emit a li-detail block for click-to-expand."""
    src = _read()
    m = re.search(r"function cosAgentHtml\((.+?)\n\}", src, re.DOTALL)
    assert m, "cosAgentHtml function not found"
    body = m.group(0)
    assert "li-detail" in body, "cosAgentHtml must render an expandable li-detail block"


def test_fleet_card_header_renamed():
    """The fleet card h3 must read Campaign OS fleet, not Agent runs."""
    src = _read()
    assert "Campaign OS fleet" in src, "Card header must be renamed to Campaign OS fleet"
    assert 'data-help-title="Campaign OS fleet"' in src, (
        "Fleet card h3 must carry data-help-title=\"Campaign OS fleet\""
    )


def test_status_pill_color_mapping_matches_ops_jobs():
    """OK/LATE/FAILED/NEVER must map to fleet-* pill classes aligned with ops-jobs."""
    src = _read()
    m = re.search(r"function cosFleetStatusPillClass\((.+?)\n\}", src, re.DOTALL)
    assert m, "cosFleetStatusPillClass function not found"
    body = m.group(1)
    assert "fleet-OK" in body and "OK" in body
    assert "fleet-LATE" in body and "LATE" in body
    assert "fleet-FAILED" in body and "FAILED" in body
    assert "fleet-NEVER" in body


if __name__ == "__main__":
    tests = [
        test_cosAgentHtml_function_defined,
        test_renderAgents_fetches_ops_agents_for_fleet_list,
        test_renderAgents_uses_cosAgentHtml_not_intel_agents_list,
        test_renderAgents_still_fetches_intel_for_health,
        test_cosAgentHtml_renders_status_pill,
        test_cosAgentHtml_renders_fleet_fields,
        test_cosAgentHtml_renders_ops_link,
        test_cosAgentHtml_emits_li_detail_block,
        test_fleet_card_header_renamed,
        test_status_pill_color_mapping_matches_ops_jobs,
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
