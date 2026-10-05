#!/usr/bin/env python3
"""stdio -> Streamable-HTTP bridge for the Krea MCP endpoint.

Why this exists: `.mcp.json` can only expand environment variables, so the Krea
token reached the MCP client by inheritance from the launching shell. A client
started before `~/.hermes/.env` was re-synced connected with a stale value and
got 401 AUTH_HEADER_REJECTED while the token on disk was fine. This bridge reads
the token at connect time instead, so the live file is always the source of
truth and no secret lands in git.

Token resolution order (first hit wins):
  1. $KREA_MCP_TOKEN                     (explicit override)
  2. ~/.krea/mcp.json -> "access_token"   (the Krea CLI's own store)
  3. ~/.hermes/.env   -> KREA_API_KEY     (what .bashrc exports)
  4. $KREA_API_KEY                        (inherited env, last resort)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ENDPOINT = os.environ.get("KREA_MCP_URL", "https://api.krea.ai/mcp")
PROTOCOL_ACCEPT = "application/json, text/event-stream"


def _log(msg: str) -> None:
    """stderr only — stdout is the JSON-RPC channel and must stay clean."""
    print(f"[krea-bridge] {msg}", file=sys.stderr, flush=True)


def resolve_token() -> str:
    explicit = (os.environ.get("KREA_MCP_TOKEN") or "").strip()
    if explicit:
        _log("token from $KREA_MCP_TOKEN")
        return explicit

    krea_store = Path.home() / ".krea" / "mcp.json"
    if krea_store.is_file():
        try:
            tok = (json.loads(krea_store.read_text()).get("access_token") or "").strip()
            if tok:
                _log(f"token from {krea_store}")
                return tok
        except (json.JSONDecodeError, OSError) as e:
            _log(f"{krea_store} unreadable: {e}")

    hermes_env = Path.home() / ".hermes" / ".env"
    if hermes_env.is_file():
        try:
            for line in hermes_env.read_text().splitlines():
                if line.startswith("KREA_API_KEY="):
                    tok = line.split("=", 1)[1].strip().strip("'\"")
                    if tok:
                        _log(f"token from {hermes_env}")
                        return tok
        except OSError as e:
            _log(f"{hermes_env} unreadable: {e}")

    inherited = (os.environ.get("KREA_API_KEY") or "").strip()
    if inherited:
        _log("token from inherited $KREA_API_KEY (may be stale)")
        return inherited

    _log("FATAL: no Krea token found")
    raise SystemExit(1)


def _parse_sse(body: str) -> list[dict]:
    """Pull JSON payloads out of a text/event-stream response body."""
    out = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload and payload != "[DONE]":
                    try:
                        out.append(json.loads(payload))
                    except json.JSONDecodeError:
                        pass
    return out


def main() -> None:
    import requests

    token = resolve_token()
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": PROTOCOL_ACCEPT,
    })
    mcp_session_id: str | None = None

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            _log(f"dropping unparseable stdin line: {raw[:120]}")
            continue

        headers = {}
        if mcp_session_id:
            headers["Mcp-Session-Id"] = mcp_session_id

        try:
            resp = session.post(ENDPOINT, data=raw, headers=headers, timeout=600)
        except requests.RequestException as e:
            if message.get("id") is not None:
                _emit({"jsonrpc": "2.0", "id": message["id"],
                       "error": {"code": -32001, "message": f"bridge transport error: {e}"}})
            continue

        # The server assigns a session on initialize; carry it on every later call.
        got_session = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
        if got_session:
            mcp_session_id = got_session

        if resp.status_code == 202 or not resp.content:
            continue  # accepted notification, nothing to relay

        if resp.status_code >= 400:
            _log(f"HTTP {resp.status_code}: {resp.text[:300]}")
            if message.get("id") is not None:
                _emit({"jsonrpc": "2.0", "id": message["id"],
                       "error": {"code": -32001,
                                 "message": f"Krea MCP HTTP {resp.status_code}: {resp.text[:300]}"}})
            continue

        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "text/event-stream" in ctype:
            for payload in _parse_sse(resp.text):
                _emit(payload)
        else:
            try:
                _emit(resp.json())
            except json.JSONDecodeError:
                _log(f"non-JSON body: {resp.text[:200]}")


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
