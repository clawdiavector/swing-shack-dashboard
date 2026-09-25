"""Parse Krea MCP get_job tool responses (shared by poll job and probe script)."""

from __future__ import annotations

import json
from typing import Any


def parse_get_job_payload(poll_resp: dict[str, Any]) -> dict[str, Any]:
    """Return normalized {status, result_urls, error, raw_status}."""
    content = poll_resp.get("content") if isinstance(poll_resp.get("content"), list) else []
    text = ""
    if content and isinstance(content[0], dict):
        text = str(content[0].get("text") or "")
    parsed: dict[str, Any] = {}
    if text:
        try:
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                parsed = loaded
        except json.JSONDecodeError:
            parsed = {}
    status = str(parsed.get("status") or poll_resp.get("status") or "unknown").lower()
    result = parsed.get("result") if isinstance(parsed.get("result"), dict) else {}
    urls = result.get("urls") if isinstance(result.get("urls"), list) else []
    result_urls = [str(u) for u in urls if u]
    err = parsed.get("error") or parsed.get("message")
    return {
        "status": status,
        "result_urls": result_urls,
        "error": str(err) if err else None,
        "raw_status": status,
    }
