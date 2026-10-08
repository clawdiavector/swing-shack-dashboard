#!/usr/bin/env python3
"""Hooks for the-algorithm skill. Registered by the skill's frontmatter, so they
exist only in sessions where the skill was loaded. `off` / `on` mute them.

  hook.py remind        UserPromptSubmit — one line of context per prompt
  hook.py gate          PreToolUse(Write) — first attempt at a new file in a
                        gated path is denied with the step-1/step-2 questions;
                        the retry goes through
  hook.py off|on <sid>  mute / unmute for one session
"""
import json
import os
import re
import sys
from pathlib import Path

STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "campaign-os-algorithm"

# New files here are new capability. Edits to existing files are never gated.
GATED = re.compile(r"^(campaign-os/_lib|campaign-os/scripts|plugins/campaign-os)/")

REMIND = (
    "The algorithm is on for this session. If this prompt adds, builds or automates "
    "anything, work the steps in order and say which one you are on: "
    "1 question the requirement (whose name is on it?) → 2 delete → 3 simplify → "
    "4 accelerate → 5 automate. Skip it for questions and small edits."
)


def session_dir(sid):
    return STATE / re.sub(r"[^A-Za-z0-9_.-]", "_", sid or "unknown")


def muted(sid):
    return (session_dir(sid) / "off").exists()


def remind(event):
    if muted(event.get("session_id")):
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": REMIND}}))


def gate(event):
    sid = event.get("session_id")
    if muted(sid):
        return
    path = (event.get("tool_input") or {}).get("file_path") or ""
    if not path:
        return
    cwd = Path(event.get("cwd") or ".")
    full = (Path(path) if os.path.isabs(path) else cwd / path).resolve()
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd).resolve()
    try:
        rel = full.relative_to(root).as_posix()
    except ValueError:
        return  # outside the project
    if full.exists() or not GATED.search(rel):
        return
    seen = session_dir(sid) / "challenged"
    key = full.as_posix()
    if seen.exists() and key in seen.read_text().splitlines():
        return
    seen.parent.mkdir(parents=True, exist_ok=True)
    with seen.open("a") as f:
        f.write(key + "\n")
    reason = (
        f"The algorithm: {full.name} would be a new file in Campaign OS. Before creating it, "
        "tell the user in one or two lines: (1) whose name is on this requirement — Kyle, "
        "Christelle, or nobody (then ask instead of building); (2) what you checked to delete "
        "or reuse instead — campaign-os-map, an existing module, a step that could go. "
        "If it still needs to exist, retry the same Write; it will go through."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))


def toggle(cmd, sid):
    d = session_dir(sid)
    if cmd == "off":
        d.mkdir(parents=True, exist_ok=True)
        (d / "off").touch()
        print("the-algorithm: off for this session")
    else:
        (d / "off").unlink(missing_ok=True)
        print("the-algorithm: on for this session")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd in ("off", "on"):
        toggle(cmd, sys.argv[2] if len(sys.argv) > 2 else "")
        return
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return  # never break the session over a malformed event
    {"remind": remind, "gate": gate}.get(cmd, lambda e: None)(event)


if __name__ == "__main__":
    main()
