"""07:00 SAST foreman morning summary — optional Telegram send."""

from __future__ import annotations

from typing import Any

from _lib import foreman_morning_summary as fms
from _lib import telegram_bot as tg

JOB_NAME = "foreman_morning_summary"
TELEGRAM_FLAG = "FOREMAN_MORNING_SUMMARY_TELEGRAM"


def run(brand: str | None = None) -> dict[str, Any]:
    """Build the summary for all brands. brand= is accepted for job-runner parity but ignored."""
    payload = fms.build_payload()
    out: dict[str, Any] = {
        "ok": True,
        "job": JOB_NAME,
        "date": payload["date"],
        "text": payload["text"],
        "scheduled_today": payload["scheduled_today"],
        "pending_approval": payload["pending_approval"],
        "failing_jobs": payload["failing_jobs"],
    }
    if not tg.flag_on(TELEGRAM_FLAG):
        out["telegram"] = {
            "skipped": True,
            "reason": f"{TELEGRAM_FLAG} is not on (default off)",
        }
        return out
    creds = tg.configured()
    if not creds["bot_token"] or not creds["chat_id"]:
        out["telegram"] = {
            "skipped": True,
            "reason": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set",
        }
        return out
    sent = tg.send_message(payload["text"])
    out["telegram"] = sent
    if not sent.get("ok"):
        out["ok"] = False
        out["error"] = sent.get("error") or sent.get("reason") or "telegram send failed"
    return out
