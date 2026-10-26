"""Minimal Telegram Bot API sender for foreman digests.

Secrets stay in env; this module never logs token values.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def flag_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("on", "1", "true", "yes")


def configured() -> dict[str, bool]:
    return {
        "bot_token": bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()),
        "chat_id": bool(os.environ.get("TELEGRAM_CHAT_ID", "").strip()),
    }


def send_message(text: str, *, parse_mode: str | None = None) -> dict[str, Any]:
    """POST sendMessage. Returns {ok, skipped?, reason?, message_id?}."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {
            "ok": False,
            "skipped": True,
            "reason": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set",
        }
    body: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if parse_mode:
        body["parse_mode"] = parse_mode
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        return {"ok": False, "error": f"telegram http {exc.code}: {detail}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}
    if not payload.get("ok"):
        return {"ok": False, "error": str(payload.get("description") or "telegram rejected")[:200]}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return {"ok": True, "message_id": result.get("message_id")}
