"""Foreman morning summary — today's posts, approval queue, failing jobs.

Pure aggregation and formatting. The HTTP route and scheduled job load live data
and call these helpers. Telegram delivery is optional (env-gated) in the job runner.
"""
from __future__ import annotations

import datetime as _dt
import os
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from _lib.plan_todo import BRAND_LABEL

_TZ = ZoneInfo("Africa/Johannesburg")
_DEFAULT_BASE = "https://swing-shack-dashboard-production.up.railway.app"
_MAX_LINES = 8
_TODAY_POST_STATES = frozenset({"scheduled", "released", "partly_posted", "send_failed"})
_BRANDS = ("swing-shack", "stick", "bag-drop")


def public_base_url() -> str:
    raw = (os.environ.get("CAMPAIGN_OS_PUBLIC_URL") or _DEFAULT_BASE).strip()
    return raw.rstrip("/")


def approve_href(brand_id: str, base: str | None = None) -> str:
    root = (base or public_base_url()).rstrip("/")
    return f"{root}/?page=review&brand={brand_id}"


def scheduled_today_titles(brand_id: str, today: _dt.date) -> List[str]:
    """Post titles on the calendar for today (scheduled or awaiting dispatch)."""
    from _lib.unified_inbox import week_board  # noqa: PLC0415

    board = week_board(brand_id=brand_id, start=today, days=1, past_days=0)
    titles: List[str] = []
    for day in board.get("days_list") or []:
        if str(day.get("date") or "") != today.isoformat():
            continue
        for post in day.get("posts") or []:
            if str(post.get("state") or "") not in _TODAY_POST_STATES:
                continue
            title = str(post.get("title") or post.get("display_title") or "").strip()
            if title:
                titles.append(title)
    titles.sort()
    return titles


def pending_approval_titles(brand_id: str) -> List[str]:
    from _lib.unified_inbox import list_items  # noqa: PLC0415

    payload = list_items(brand=brand_id, status="pending")
    titles: List[str] = []
    for item in payload.get("items") or []:
        if item.get("status") != "pending":
            continue
        title = str(item.get("title") or item.get("display_title") or "").strip()
        if title:
            titles.append(title)
    return titles


def open_job_failures() -> List[dict[str, Any]]:
    from _lib.jobs.diagnostics import list_open_failures  # noqa: PLC0415

    return list_open_failures()


def brand_section(brand_id: str, today: _dt.date, *, base_url: str | None = None) -> Dict[str, Any]:
    return {
        "brand_id": brand_id,
        "scheduled_today": scheduled_today_titles(brand_id, today),
        "pending": pending_approval_titles(brand_id),
        "approve_url": approve_href(brand_id, base_url),
    }


def _bullet_block(header: str, titles: List[str], empty_line: str) -> List[str]:
    if not titles:
        return [empty_line]
    lines = [header.format(n=len(titles)) if "{n}" in header else header]
    shown = titles[:_MAX_LINES]
    lines.extend(f"• {t}" for t in shown)
    more = len(titles) - len(shown)
    if more > 0:
        lines.append(f"…and {more} more")
    return lines


def _failures_block(failures: List[dict[str, Any]]) -> List[str]:
    if not failures:
        return ["Failing jobs: none."]
    names = [f"{f.get('job')} ({f.get('verdict')})" for f in failures[:_MAX_LINES]]
    line = "Failing jobs: " + ", ".join(names)
    if len(failures) > _MAX_LINES:
        line += f" …and {len(failures) - _MAX_LINES} more"
    return [line]


def summary_text(
    sections: Dict[str, Dict[str, Any]],
    today: _dt.date,
    failures: List[dict[str, Any]],
) -> str:
    """Telegram / API body."""
    lines: List[str] = [f"Morning summary, {today.strftime('%a %d %b')}."]
    lines.extend(_failures_block(failures))
    for brand_id, sec in sections.items():
        label = BRAND_LABEL.get(brand_id, brand_id)
        if len(sections) > 1:
            lines.append("")
            lines.append(f"— {label} —")
        else:
            lines.append("")
            lines.append(label)
        lines.extend(
            _bullet_block(
                "Scheduled today ({n}):",
                sec.get("scheduled_today") or [],
                "Scheduled today: nothing on the calendar.",
            )
        )
        lines.extend(
            _bullet_block(
                "Awaiting approval ({n}):",
                sec.get("pending") or [],
                "Awaiting approval: nothing.",
            )
        )
        lines.append(f"Approve drafts: {sec.get('approve_url') or approve_href(brand_id)}")
    if not sections:
        lines.append("No brands in scope.")
    return "\n".join(lines)


def build_payload(
    brands: List[str] | None = None,
    today: _dt.date | None = None,
) -> dict[str, Any]:
    today = today or _dt.datetime.now(_TZ).date()
    scope = list(brands or _BRANDS)
    base = public_base_url()
    sections = {b: brand_section(b, today, base_url=base) for b in scope}
    failures = open_job_failures()
    text = summary_text(sections, today, failures)
    return {
        "ok": True,
        "date": today.isoformat(),
        "text": text,
        "sections": sections,
        "failing_jobs": len(failures),
        "failures": [
            {"job": f.get("job"), "verdict": f.get("verdict"), "error_class": f.get("error_class")}
            for f in failures
        ],
        "scheduled_today": sum(len(s.get("scheduled_today") or []) for s in sections.values()),
        "pending_approval": sum(len(s.get("pending") or []) for s in sections.values()),
    }
