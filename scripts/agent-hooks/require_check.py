#!/usr/bin/env python3
"""Stops an AI agent from finishing while ./check fails; feeds the failures back to it.

Usage (from a stop hook):  require_check.py claude|cursor   (hook JSON on stdin)

The check runs only when this session changed something since the check last
passed. "Changed" is measured against a fingerprint protect_checks.py recorded
before the session's first write-capable tool, so a tree that was already dirty
(the image ingest leaves one) and a pure Q&A chat both skip the suite.

  CHECK_ON_STOP=0        never run the check here (slow machine; CI still decides)
  CHECK_MAX_RETRIES=5    push-backs per turn before handing back to the person
  CHECK_TIMEOUT=840      seconds; keep it under the hook's own timeout
  CHECK_CMD=...          run something other than ./check
"""
from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

TAIL_LINES = 40


def done(tool: str, note: str = "") -> None:
    """Let the agent stop. A note is shown to the person, not sent to the agent."""
    if tool == "cursor":
        print("{}")
    elif note:
        print(json.dumps({"systemMessage": note}))
    sys.exit(0)


def push_back(tool: str, msg: str) -> None:
    if tool == "cursor":
        print(json.dumps({"followup_message": msg}))
    else:
        print(json.dumps({"decision": "block", "reason": msg}))
    sys.exit(0)


def run_check(root: Path) -> tuple[int | None, str]:
    """(exit code, output). Exit code None means it ran out of time."""
    override = os.environ.get("CHECK_CMD", "").strip()
    cmd = shlex.split(override, posix=os.name != "nt") if override else [sys.executable, str(root / "check")]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    kwargs: dict = {"start_new_session": True} if os.name != "nt" else {}
    proc = subprocess.Popen(
        cmd, cwd=root, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs,
    )
    try:
        out, _ = proc.communicate(timeout=float(os.environ.get("CHECK_TIMEOUT", "840")))
        return proc.returncode, out.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        # Take the test runner down with it, not just the wrapper.
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return None, ""


def main() -> None:
    tool = sys.argv[1] if len(sys.argv) > 1 else "claude"
    data = c.read_hook_input()
    root = c.repo_root(data.get("cwd") if isinstance(data.get("cwd"), str) else None) or c.repo_root()
    if not root or os.environ.get("CHECK_ON_STOP", "1") == "0":
        done(tool)
    if not os.environ.get("CHECK_CMD") and not (root / "check").is_file():
        done(tool)

    key = c.session_key(data)
    state = c.read_state(root, key)
    if "baseline" not in state:
        done(tool)  # no write-capable tool ran in this session
    now = c.fingerprint_id(c.fingerprint(root))
    if now == state["baseline"]:
        done(tool)  # nothing changed since the session began or the check last passed

    # Claude Code: count push-backs so it cannot loop forever (Cursor has loop_limit).
    retries = int(state.get("retries", 0)) if data.get("stop_hook_active") else 0
    if tool == "claude" and retries >= int(os.environ.get("CHECK_MAX_RETRIES", "5")):
        c.write_state(root, key, {"baseline": now, "retries": 0})
        done(tool, f"./check was still failing after {retries} attempts, so the agent was allowed to stop. The work is NOT verified.")

    code, out = run_check(root)
    if code is None:
        c.write_state(root, key, {"baseline": now, "retries": 0})
        done(tool, "./check did not finish in time on this machine, so this work is NOT verified locally. CI will decide. Set CHECK_ON_STOP=0 to skip the wait.")
    if code == 0:
        # Re-fingerprint: the run itself may have left caches or scratch files.
        c.write_state(root, key, {"baseline": c.fingerprint_id(c.fingerprint(root)), "retries": 0})
        done(tool)

    c.write_state(root, key, {"baseline": state["baseline"], "retries": retries + 1})
    tail = "\n".join(out.splitlines()[-TAIL_LINES:])
    push_back(tool, (
        "./check is failing, so the task is not done. Fix the code (not the tests, "
        "snapshots or the known-failures list) and run it again. Last output:\n" + tail
    ))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # a broken hook must be loud, and must not trap the session
        print(f"require_check.py failed, so ./check was not enforced: {exc!r}", file=sys.stderr)
        if len(sys.argv) > 1 and sys.argv[1] == "cursor":
            print("{}")
            sys.exit(0)
        sys.exit(1)
