"""Foreman end-of-day Telegram report — post counts today and rest of week.

Pure formatting and aggregation; app.py loads live data and calls these helpers.
Mirrors the morning message in plan_todo.py: the Mac cron reads GET
/api/jobs/evening-message and sends `text` — this module does not send anything.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from _lib.plan_todo import BRAND_LABEL

_TZ = ZoneInfo("Africa/Johannesburg")
_DEFAULT_BASE = "https://swing-shack-dashboard-production.up.railway.app"
_READY_STATES = frozenset({"draft_ready", "scheduled", "released", "posted"})
_MAX_PENDING_LINES = 5


def public_base_url() -> str:
    raw = (os.environ.get("CAMPAIGN_OS_PUBLIC_URL") or _DEFAULT_BASE).strip()
    return raw.rstrip("/")


def approve_href(brand_id: str, base: str | None = None) -> str:
    root = (base or public_base_url()).rstrip("/")
    return f"{root}/?page=review&brand={brand_id}"


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _parse_iso(value: str | None) -> Optional[_dt.datetime]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def _ts_on_local_day(ts: str | None, day: _dt.date, tz: ZoneInfo) -> bool:
    parsed = _parse_iso(ts)
    if parsed is None:
        return False
    return parsed.astimezone(tz).date() == day


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def created_today(brand_id: str, today: _dt.date, tz: ZoneInfo = _TZ) -> int:
    """Draft sidecars lodged today for this brand."""
    draft_dir = _data_dir() / "draft-assets"
    if not draft_dir.is_dir():
        return 0
    n = 0
    for path in draft_dir.glob("*.json"):
        if path.name.endswith(".brief.json") or path.name.endswith(".qc.json"):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        if str(doc.get("brand_id") or "") not in ("", brand_id):
            if doc.get("brand_id") and str(doc.get("brand_id")) != brand_id:
                continue
        created = str(doc.get("created_at") or "")
        if _ts_on_local_day(created, today, tz):
            n += 1
    return n


def _human_edits_today(brand_id: str, action: str, today: _dt.date, tz: ZoneInfo = _TZ) -> int:
    path = _data_dir() / "human-edits.jsonl"
    n = 0
    for row in _read_jsonl(path):
        if str(row.get("action") or "") != action:
            continue
        if str(row.get("brand_id") or "") != brand_id:
            continue
        if _ts_on_local_day(str(row.get("ts") or ""), today, tz):
            n += 1
    return n


def approved_today(brand_id: str, today: _dt.date, tz: ZoneInfo = _TZ) -> int:
    return _human_edits_today(brand_id, "approve", today, tz)


def released_today(brand_id: str, today: _dt.date, tz: ZoneInfo = _TZ) -> int:
    return _human_edits_today(brand_id, "release", today, tz)


def _local_day_utc_bounds(today: _dt.date, tz: ZoneInfo) -> tuple[str, str]:
    start = _dt.datetime.combine(today, _dt.time.min, tzinfo=tz).astimezone(_dt.timezone.utc)
    end = _dt.datetime.combine(today + _dt.timedelta(days=1), _dt.time.min, tzinfo=tz).astimezone(
        _dt.timezone.utc
    )
    def _iso_z(dt: _dt.datetime) -> str:
        return dt.isoformat().replace("+00:00", "Z")

    return _iso_z(start), _iso_z(end)


def _postiz_posts_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)]
    if isinstance(raw, dict):
        for key in ("posts", "data", "items"):
            val = raw.get(key)
            if isinstance(val, list):
                return [p for p in val if isinstance(p, dict)]
    return []


def _postiz_integrations(brand_id: str) -> list[dict[str, Any]]:
    from _lib import postiz_client as pz  # noqa: PLC0415

    raw, err = pz.list_integrations(brand_id=brand_id)
    if err or raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("integrations") or raw.get("identities") or raw.get("data") or []
    else:
        items = []
    return [i for i in items if isinstance(i, dict)]


def _postiz_live_key(post: dict[str, Any]) -> str:
    group = post.get("group")
    if group:
        return f"postiz-group:{group}"
    pid = post.get("id") or post.get("postId")
    return f"postiz:{pid}"


def _postiz_published_today(brand_id: str, today: _dt.date, tz: ZoneInfo = _TZ) -> int | None:
    """Count Postiz PUBLISHED posts for today. None when Postiz is not configured."""
    from _lib import postiz_client as pz  # noqa: PLC0415

    if not pz.postiz_status(brand_id).get("api_key_present"):
        return None
    start_iso, end_iso = _local_day_utc_bounds(today, tz)
    keys: set[str] = set()
    for integration in _postiz_integrations(brand_id):
        int_id = integration.get("id") or integration.get("_id")
        if not int_id:
            continue
        raw, err = pz.list_posts(
            str(int_id),
            start_date=start_iso,
            end_date=end_iso,
            state="PUBLISHED",
            brand_id=brand_id,
        )
        if err:
            continue
        for post in _postiz_posts_list(raw):
            state = str(post.get("state") or post.get("status") or "").upper()
            if state and state != "PUBLISHED":
                continue
            when = (
                post.get("publishDate")
                or post.get("publish_date")
                or post.get("date")
                or post.get("scheduled_date")
            )
            if not _ts_on_local_day(str(when or ""), today, tz):
                continue
            keys.add(_postiz_live_key(post))
    return len(keys)


def _meta_ig_published_today(brand_id: str, today: _dt.date, tz: ZoneInfo = _TZ) -> int:
    from _lib import meta_api as ma  # noqa: PLC0415

    try:
        cfg = ma.load_brand_integration(brand_id)
    except Exception:
        return 0
    if not cfg.get("ig_business_account_id") or not cfg.get("configured", True):
        return 0
    try:
        resp = ma.list_recent_posts_for_brand(brand_id, limit=50) or {}
    except Exception:
        return 0
    meta = resp.get("_meta") or {}
    if (
        meta.get("ig_account_id")
        and cfg.get("ig_business_account_id")
        and meta["ig_account_id"] != cfg["ig_business_account_id"]
    ):
        return 0
    n = 0
    for post in resp.get("data") or []:
        if not isinstance(post, dict):
            continue
        if _ts_on_local_day(str(post.get("timestamp") or ""), today, tz):
            n += 1
    return n


def on_social_today(brand_id: str, today: _dt.date, tz: ZoneInfo = _TZ) -> int:
    """Posts live on brand channels today (Postiz or Meta read-back, never sandbox receipts)."""
    postiz_n = _postiz_published_today(brand_id, today, tz)
    if postiz_n is not None:
        return postiz_n
    return _meta_ig_published_today(brand_id, today, tz)


def rest_of_week_days(brand_id: str, today: _dt.date) -> List[Dict[str, Any]]:
    """Per future day: ready count, planned count, gap flag."""
    from _lib.unified_inbox import week_board  # noqa: PLC0415

    board = week_board(brand_id=brand_id, start=today, days=7, past_days=0)
    out: List[Dict[str, Any]] = []
    for day in board.get("days_list") or []:
        day_iso = str(day.get("date") or "")
        try:
            d = _dt.date.fromisoformat(day_iso)
        except ValueError:
            continue
        if d <= today:
            continue
        posts = day.get("posts") or []
        planned = len(posts)
        ready = sum(1 for p in posts if str(p.get("state") or "") in _READY_STATES)
        has_gap = any(str(p.get("state") or "") == "gap" for p in posts)
        out.append(
            {
                "date": day_iso,
                "weekday": d.strftime("%a"),
                "ready": ready,
                "planned": planned,
                "gap": has_gap,
            }
        )
    return out


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


def brand_section(brand_id: str, today: _dt.date, *, base_url: str | None = None) -> Dict[str, Any]:
    base = base_url or public_base_url()
    return {
        "brand_id": brand_id,
        "counts": {
            "created": created_today(brand_id, today),
            "approved": approved_today(brand_id, today),
            "released": released_today(brand_id, today),
            "on_social": on_social_today(brand_id, today),
        },
        "rest_of_week": rest_of_week_days(brand_id, today),
        "pending": pending_approval_titles(brand_id),
        "approve_url": approve_href(brand_id, base),
    }


def _rest_line(days: List[Dict[str, Any]]) -> str:
    if not days:
        return "Rest of week: nothing scheduled."
    parts: List[str] = []
    for d in days:
        bit = f"{d['weekday']} {d['ready']}/{d['planned']}"
        if d.get("gap"):
            bit += " (gap)"
        parts.append(bit)
    return "Rest of week: " + " · ".join(parts)


def _pending_block(titles: List[str], approve_url: str) -> List[str]:
    if not titles:
        return ["Waiting for approval: nothing.", f"Approve drafts: {approve_url}"]
    shown = titles[:_MAX_PENDING_LINES]
    more = len(titles) - len(shown)
    lines = [f"Waiting for approval ({len(titles)}):"]
    lines.extend(f"• {t}" for t in shown)
    if more > 0:
        lines.append(f"…and {more} more")
    lines.append(f"Approve drafts: {approve_url}")
    return lines


def eod_text(
    sections: Dict[str, Dict[str, Any]],
    today: _dt.date,
) -> str:
    """Telegram body. sections is {brand_id: brand_section(...)}."""
    lines: List[str] = []
    for brand_id, sec in sections.items():
        label = BRAND_LABEL.get(brand_id, brand_id)
        counts = sec.get("counts") or {}
        if lines:
            lines.append("")
        lines.append(f"{label}, today")
        lines.append(
            "Created {created} · Approved {approved} · Released {released} · On social {on_social}".format(
                created=int(counts.get("created") or 0),
                approved=int(counts.get("approved") or 0),
                released=int(counts.get("released") or 0),
                on_social=int(counts.get("on_social") or 0),
            )
        )
        lines.append(_rest_line(sec.get("rest_of_week") or []))
        lines.extend(_pending_block(sec.get("pending") or [], str(sec.get("approve_url") or approve_href(brand_id))))
    if not lines:
        lines.append(f"End of day, {today.strftime('%a %d %b')}. No brands in scope.")
    return "\n".join(lines)
