"""
Regression test: Agent runs rows must actually drill into the per-script
results of the most recent run when clicked.

Bug: the Agents & health <h2> tooltip (line ~2061) promises "Click any red
row to drill into the error log." But agentRunHtml() rendered an <li class="li"
onclick="this.classList.toggle('open')"> that toggled the .open class with
NO inner .li-detail content — so clicking a red row did literally nothing
visible. The tooltip promised a flow that did not exist.

Fix:
  1. _lib/intelligence.py::agents_view() forwards `last_scripts`
     (a per-script list from the most recent run, each with
     {script, status, duration_ms}) and `outputs_invalid` (the entries from
     outputs_validated whose valid=false, with {file, reason}).
  2. agentRunHtml() renders a `<div class="li-detail">` block (CSS rule
     `.li.open .li-detail{display:block}` already exists) showing the
     per-script results table and the invalid-output reasons so the
     promised "drill into the error log" actually surfaces the error data.
  3. Tooltip text changes from "Click any red row" (only-red + dead
     promise) to "Click any row to see the per-script results" (every
     row + a flow that actually works).

Read-only. Never imports flask, never hits a running server. Loads the HTML
file as text and runs the agents_view() function in a fresh subprocess
against a synthetic agent-runs.json to assert the forwarded fields.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML = REPO / "campaign-os" / "campaign-os.html"
LIB_DIR = REPO / "campaign-os" / "_lib"


# ────────────────────────────────────────────────────────────────────
# Test 01: agents_view() forwards last_scripts (list of {script, status,
# duration_ms}) from the most recent run.
# ────────────────────────────────────────────────────────────────────
def test_agents_view_forwards_last_scripts():
    """agents_view() must include a `last_scripts` array per agent."""
    fixture = {
        "agents": {
            "pulse_keeper": [
                {
                    "agent_id": "pulse_keeper",
                    "run_at": "2026-08-20T00:00:00.000Z",
                    "status": "PARTIAL",
                    "duration_ms": 140,
                    "scripts": [
                        {"script": "generate_pulse_keeper.js", "status": "PASS", "duration_ms": 47},
                        {"script": "store_daily_learnings.js", "status": "FAIL", "duration_ms": 43},
                    ],
                    "passed": 1,
                    "failed": 1,
                }
            ]
        }
    }
    out = _run_agents_view(fixture)
    assert out["ok"] is True, out
    rows = out["agents"]
    assert len(rows) == 1
    row = rows[0]
    assert "last_scripts" in row, (
        "agents_view() must forward `last_scripts` (per-script results from "
        "the most recent run) so the front-end can render it on row click. "
        f"Got row keys: {sorted(row.keys())}"
    )
    scripts = row["last_scripts"]
    assert isinstance(scripts, list) and scripts, "last_scripts must be a non-empty list"
    s0 = scripts[0]
    for key in ("script", "status", "duration_ms"):
        assert key in s0, f"last_scripts[0] missing `{key}` — got {s0!r}"
    # Confirm both PASS and FAIL scripts are present, in source order
    statuses = [s["status"] for s in scripts]
    assert "PASS" in statuses and "FAIL" in statuses, (
        f"last_scripts must preserve all per-script statuses — got {statuses}"
    )


# ────────────────────────────────────────────────────────────────────
# Test 02: agents_view() forwards outputs_invalid (the {file, reason}
# entries from outputs_validated where valid=false).
# ────────────────────────────────────────────────────────────────────
def test_agents_view_forwards_outputs_invalid():
    """agents_view() must include `outputs_invalid` when a run had invalid outputs."""
    fixture = {
        "agents": {
            "pulse_keeper": [
                {
                    "agent_id": "pulse_keeper",
                    "run_at": "2026-08-20T00:00:00.000Z",
                    "status": "PARTIAL",
                    "scripts": [
                        {"script": "store_daily_learnings.js", "status": "FAIL", "duration_ms": 43}
                    ],
                    "outputs_validated": {
                        "data/system-health.json": {"valid": True, "keys": 19},
                        "memory/daily/2026-08-20.json": {
                            "valid": False,
                            "reason": "ENOENT: no such file or directory",
                        },
                    },
                }
            ]
        }
    }
    out = _run_agents_view(fixture)
    assert out["ok"] is True
    row = out["agents"][0]
    assert "outputs_invalid" in row, (
        "agents_view() must forward `outputs_invalid` so the front-end can "
        "show WHY a run went PARTIAL/FAIL. Got row keys: " + ",".join(sorted(row.keys()))
    )
    invalid = row["outputs_invalid"]
    assert isinstance(invalid, list) and len(invalid) == 1, (
        f"expected exactly 1 invalid output, got {invalid!r}"
    )
    entry = invalid[0]
    assert "memory/daily/2026-08-20.json" in entry.get("file", ""), entry
    assert "ENOENT" in entry.get("reason", ""), entry


# ────────────────────────────────────────────────────────────────────
# Test 03: outputs_invalid is empty (not absent) when a run was clean.
# ────────────────────────────────────────────────────────────────────
def test_agents_view_outputs_invalid_empty_when_clean():
    """Clean runs must still carry outputs_invalid=[] (not the key absent)."""
    fixture = {
        "agents": {
            "data_harvester": [
                {
                    "agent_id": "data_harvester",
                    "run_at": "2026-08-20T00:00:00.000Z",
                    "status": "PASS",
                    "scripts": [{"script": "x.js", "status": "PASS", "duration_ms": 5}],
                    "outputs_validated": {"a.json": {"valid": True, "keys": 3}},
                }
            ]
        }
    }
    out = _run_agents_view(fixture)
    row = out["agents"][0]
    assert row.get("outputs_invalid") == [], (
        f"clean runs must surface outputs_invalid=[] (not the key absent) so "
        f"the front-end detail block is well-defined. Got: {row.get('outputs_invalid')!r}"
    )


# ────────────────────────────────────────────────────────────────────
# Test 04: agentRunHtml renders a .li-detail block (so .open toggle shows
# the drill-into content).
# ────────────────────────────────────────────────────────────────────
def test_agentRunHtml_emits_li_detail_block():
    """agentRunHtml() must emit a <div class=\"li-detail\"> block so the
    click-to-drill affordance promised by the tooltip actually works."""
    src = HTML.read_text(encoding="utf-8")
    m = re.search(r"function agentRunHtml\(.+?\n\}", src, re.DOTALL)
    assert m, "agentRunHtml() function not found"
    body = m.group(0)
    assert "li-detail" in body, (
        "agentRunHtml() must render a <div class=\"li-detail\"> block — the "
        "click-to-drill affordance relies on the existing CSS rule "
        "`.li.open .li-detail{display:block}`. Without a detail block, "
        "clicking the row is a no-op even though the tooltip promises a flow."
    )


# ────────────────────────────────────────────────────────────────────
# Test 05: agentRunHtml renders the per-script status from it.last_scripts.
# ────────────────────────────────────────────────────────────────────
def test_agentRunHtml_renders_last_scripts():
    """agentRunHtml() must reference it.last_scripts (or last_scripts) so
    the per-script drill content actually appears on click."""
    src = HTML.read_text(encoding="utf-8")
    m = re.search(r"function agentRunHtml\(.+?\n\}", src, re.DOTALL)
    assert m, "agentRunHtml() function not found"
    body = m.group(0)
    assert "last_scripts" in body, (
        "agentRunHtml() must read it.last_scripts (the per-script array "
        "forwarded by agents_view) so the drill-into block has real content."
    )


# ────────────────────────────────────────────────────────────────────
# Test 06: Tooltip no longer says "Click any red row" (the broken promise).
# ────────────────────────────────────────────────────────────────────
def test_agents_health_tooltip_no_false_red_only_promise():
    """The Agents & health <h2> tooltip must not promise a 'red row only'
    drill that the renderer cannot fulfill (rows do not have a stable
    'red' state at render time)."""
    src = HTML.read_text(encoding="utf-8")
    # Find the tooltip on the Agents & health h2 specifically
    m = re.search(
        r'data-help-title="Agents \+ health"[^>]*>Agents.*?</h2>',
        src,
        re.DOTALL,
    )
    assert m, "Agents & health h2 not found"
    # Find its full data-help attribute
    h2_start = src.find('data-help-title="Agents + health"')
    assert h2_start >= 0
    # The data-help attribute precedes the closing > of the h2. Find it.
    help_match = re.search(
        r'data-help="([^"]*)"\s*data-help-title="Agents \+ health"',
        src,
    )
    assert help_match, "Could not locate the Agents h2 data-help attribute"
    help_text = help_match.group(1)
    # Old broken promise must be gone
    assert "Click any red row" not in help_text, (
        "Tooltip must not promise 'Click any red row' — agent rows have no "
        "stable red state and the click did not drill into anything anyway. "
        f"Current tooltip: {help_text!r}"
    )
    # New promise must be present
    assert "per-script" in help_text.lower() or "last run" in help_text.lower(), (
        "Tooltip must describe what clicking actually does (per-script / last "
        f"run results). Current: {help_text!r}"
    )


# ────────────────────────────────────────────────────────────────────
# Helper: run agents_view() in a clean subprocess against a fixture.
# ────────────────────────────────────────────────────────────────────
def _run_agents_view(agent_runs_fixture):
    """Run the agents_view() function in a clean subprocess. The function
    reads agent-runs.json from its module-level DATA_DIR constant, so we
    monkey-patch the constant in the child process to point at a temp dir
    containing a synthetic agent-runs.json + empty system-health +
    integration-health stubs. Returns the parsed dict the function would
    have returned."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "agent-runs.json").write_text(
            json.dumps(agent_runs_fixture), encoding="utf-8"
        )
        (tmp_path / "system-health.json").write_text("{}", encoding="utf-8")
        (tmp_path / "integration-health.json").write_text("{}", encoding="utf-8")
        runner = tmp_path / "_run.py"
        # Use absolute path: the test cwd may be the repo root OR
        # campaign-os/ depending on how pytest was invoked. An absolute
        # insertion sidesteps that.
        lib_parent_abs = str(LIB_DIR.parent.resolve())
        runner.write_text(
            "import json, sys\n"
            "sys.path.insert(0, %r)\n" % lib_parent_abs +
            "from _lib import intelligence as _i\n"
            "_i.DATA_DIR = %r\n" % str(tmp_path) +
            "print(json.dumps(_i.agents_view()))\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(runner)],
            capture_output=True, text=True, timeout=20,
            cwd=lib_parent_abs,
        )
        if proc.returncode != 0:
            raise AssertionError(
                f"agents_view() subprocess failed (exit {proc.returncode}):\n"
                f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
            )
        return json.loads(proc.stdout)
