#!/usr/bin/env python3
"""Blocks AI agents from editing locked checks (tests, snapshots, the check itself).

Usage (from a pre-tool hook):  protect_checks.py claude|cursor   (hook JSON on stdin)

What is locked is decided by `_common.locked_files`. This covers the agent's
file-edit tools AND shell commands that would write to a locked file (a redirect
into it, or sed -i / tee / mv / cp / rm / git checkout / Set-Content ... naming
it). Reading a locked file is never blocked. Shell detection is a heuristic; the
CI guard is the backstop.

CHECK_LOCK_MODE=ask (default: deny) turns a block into a permission prompt, so
a person can let one edit through without touching a file by hand. Where nobody
can answer the prompt it is still a block.

It also records the session's starting point for require_check.py, because this
hook runs before the first tool that can change a file.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

SHELL_TOOLS = {"Bash", "Shell", "PowerShell"}
SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|\n]")
# 2>&1, >&2, and anything sent to the null device are not writes to a file.
HARMLESS_REDIRECT = re.compile(r"[0-9]?>&[0-9]|[0-9*]?>>?\s*(/dev/null|\$null|NUL)\b", re.I)
WORD_SPLIT = re.compile(r"[\s\"'=(),]+")
REDIRECT_TARGET = re.compile(r">>?\s*(\"[^\"]+\"|'[^']+'|[^\s;&|<>()]+)")
WRITE_VERB = re.compile(
    r"""
      \b(sed|perl)\b[^|;&]*\s-[a-zA-Z]*i
    | (?<![\w./-])(tee|mv|cp|rm|truncate|dd|install|ln|del|erase|move|copy|ren)(?=\s)
    | \bgit\s+(checkout|restore|rm|mv|apply)\b
    | \b(Set-Content|Add-Content|Clear-Content|Out-File|Remove-Item|Move-Item|Copy-Item|Rename-Item|New-Item)\b
    | write_text|write_bytes|WriteAllText|WriteAllLines|open\([^)]*["'][wax+]
    """,
    re.X | re.I,
)


def respond(tool: str, decision: str, msg: str = "") -> None:
    """Print the hook's verdict in the calling tool's format and exit."""
    if tool == "cursor":
        out: dict = {"permission": decision}
        if msg:
            out.update(user_message=msg, agent_message=msg)
        print(json.dumps(out))
    elif decision != "allow":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": msg,
        }}))
    sys.exit(0)


def block(tool: str, data: dict, why: str) -> None:
    msg = (
        f"BLOCKED: {why} Change the code to make the check pass, not the check. "
        "If the check itself is wrong, stop and explain why so a person can decide."
    )
    ask = os.environ.get("CHECK_LOCK_MODE", "deny").lower() == "ask"
    # In bypass mode a prompt may never be shown, so "ask" would mean "allow".
    if ask and data.get("permission_mode") != "bypassPermissions":
        respond(tool, "ask", msg.replace("BLOCKED:", "LOCKED CHECK:", 1))
    respond(tool, "deny", msg)


def names_locked(token: str, locked: dict[str, tuple[str, str]]) -> str:
    """The reason a path-like word from a command refers to a locked file, or "".

    "tests/test_x.py", "./tests/test_x.py", an absolute path ending in it, a bare
    "test_x.py" and the directory "tests" all name tests/test_x.py;
    "other/test_x.py" does not.
    """
    t = c._norm(token.strip("\"'").replace("\\", "/"))
    while t.startswith("./"):
        t = t[2:]
    if not t:
        return ""
    for rel_n, (_, why) in locked.items():
        if rel_n == t or rel_n.endswith("/" + t) or t.endswith("/" + rel_n) or rel_n.startswith(t.rstrip("/") + "/"):
            return why
    return ""


def shell_hit(cmd: str, locked: dict[str, tuple[str, str]]) -> str:
    """The reason a shell command would modify a locked file, or ""."""
    for seg in SEGMENT_SPLIT.split(HARMLESS_REDIRECT.sub(" ", cmd)):
        words = [m.group(1) for m in REDIRECT_TARGET.finditer(seg)]
        if WRITE_VERB.search(seg):
            words += WORD_SPLIT.split(seg)
        for word in words:
            why = names_locked(word, locked)
            if why:
                return why
    return ""


def main() -> None:
    tool = sys.argv[1] if len(sys.argv) > 1 else "claude"
    data = c.read_hook_input()
    root = c.repo_root(data.get("cwd") if isinstance(data.get("cwd"), str) else None) or c.repo_root()
    if not root:
        respond(tool, "allow")
    c.ensure_baseline(root, c.session_key(data))

    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}

    if data.get("tool_name") in SHELL_TOOLS:
        cmd = str(tool_input.get("command") or "")
        scan = HARMLESS_REDIRECT.sub(" ", cmd)
        if not (">" in scan or WRITE_VERB.search(scan)):
            respond(tool, "allow")
        why = shell_hit(cmd, c.locked_files(root))
        if why:
            block(tool, data, f"this shell command would modify a locked check: {why}")
        respond(tool, "allow")

    path = next(
        (str(v) for v in (
            tool_input.get("file_path"), tool_input.get("path"), tool_input.get("target_file"),
            tool_input.get("notebook_path"), data.get("file_path"),
        ) if v),
        "",
    )
    if not path:
        respond(tool, "allow")
    p = Path(path)
    try:
        rel = (p if p.is_absolute() else root / p).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        respond(tool, "allow")  # outside this repo
    why = c.lock_reason(root, rel)
    if why:
        block(tool, data, why)
    respond(tool, "allow")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # a broken hook must be loud, and must not wedge the session
        print(f"protect_checks.py failed, so nothing was locked for this call: {exc!r}", file=sys.stderr)
        if len(sys.argv) > 1 and sys.argv[1] == "cursor":
            print(json.dumps({"permission": "allow"}))
            sys.exit(0)
        sys.exit(1)
