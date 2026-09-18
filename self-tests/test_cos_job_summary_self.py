"""Self-tests for scripts/cos_job_summary.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "cos_job_summary.py"


def _run(args: list[str]) -> int:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
    return proc.returncode


def test_single_run_assert_ok(tmp_path):
    path = tmp_path / "single.json"
    path.write_text(json.dumps({"ok": True, "status": "OK", "run_id": "r1"}), encoding="utf-8")
    assert _run(["assert-ok", str(path), "--hard-gate"]) == 0


def test_multi_run_skipped_does_not_fail_hard_gate(tmp_path):
    path = tmp_path / "multi.json"
    path.write_text(
        json.dumps(
            {
                "ok": True,
                "runs": [
                    {"ok": True, "status": "OK", "brand": "swing-shack"},
                    {"ok": True, "status": "SKIPPED", "brand": "stick"},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert _run(["assert-ok", str(path), "--hard-gate"]) == 0


def test_multi_run_failure_fails_hard_gate(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "ok": False,
                "runs": [
                    {"ok": True, "status": "OK", "brand": "swing-shack"},
                    {"ok": False, "status": "FAILED", "brand": "stick", "error": "boom"},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert _run(["assert-ok", str(path), "--hard-gate"]) == 1
