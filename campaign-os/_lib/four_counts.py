"""The four counts every page shows (audit, 3 Nov 2026).

To approve and Dates to decide come from the unified inbox (Approve drafts, Inbox),
Scheduled from the shelf, and Sent this week from the send queue. The old tiles read
campaign-data.json asset statuses, which the shelf and Postiz never update.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")
KEYS = ("to_approve", "dates_to_decide", "scheduled", "sent_this_week")
# The shelf takes ~8 s to build (42 s next to Today's other requests), so keep each
# brand's counts briefly: every page that opens in that window shares them.
CACHE_SECONDS = 120
_cache: dict[str, tuple[float, dict[str, int]]] = {}


def _clock() -> float:
    return time.monotonic()


def clear_cache() -> None:
    _cache.clear()


def week_start(now: datetime | None = None) -> datetime:
    """Monday 00:00 SAST of this week, in UTC."""
    local = (now or datetime.now(timezone.utc)).astimezone(SAST)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(timezone.utc)


def _queue_rows() -> list[dict[str, Any]]:
    from _lib.publish_sandbox import _queue_path, _read_jsonl  # noqa: PLC0415

    return list(_read_jsonl(_queue_path()))


def sent_this_week(rows: list[dict[str, Any]], brand_id: str, *, now: datetime | None = None) -> int:
    """Posts (not platforms) this brand sent since Monday 00:00 SAST."""
    since = week_start(now)
    sent: set[str] = set()
    for row in rows:
        if str(row.get("brand_id") or "") != brand_id or row.get("status") != "dispatched":
            continue
        try:
            at = datetime.fromisoformat(str(row.get("dispatched_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if at >= since:
            sent.add(_post_id(row))
    return len(sent)


def _post_id(row: dict[str, Any]) -> str:
    """The post a queue row belongs to; live rows carry it only in qc-<asset>-<platform>."""
    if row.get("asset_id"):
        return str(row["asset_id"])
    from _lib.unified_inbox import asset_id_from_queue_row  # noqa: PLC0415

    return asset_id_from_queue_row(row) or str(row.get("idempotency_key") or "")


def brand_counts(brand_id: str, *, now: datetime | None = None) -> dict[str, int]:
    """One brand's counts, kept for CACHE_SECONDS."""
    hit = _cache.get(brand_id)
    at = _clock()
    if hit and at - hit[0] < CACHE_SECONDS:
        return dict(hit[1])
    fresh = _fresh_brand_counts(brand_id, now=now)
    _cache[brand_id] = (at, dict(fresh))
    return fresh


def _fresh_brand_counts(brand_id: str, *, now: datetime | None = None) -> dict[str, int]:
    from _lib import unified_inbox  # noqa: PLC0415

    drafts = unified_inbox.list_items(brand=brand_id, item_type="draft_asset").get("items") or []
    dates = unified_inbox.list_items(brand=brand_id, item_type="calendar_candidate").get("items") or []
    shelf = unified_inbox.shelf_board(brand_id=brand_id).get("counts") or {}
    return {
        "to_approve": len(drafts),
        "dates_to_decide": len(dates),
        "scheduled": int(shelf.get("scheduled") or 0),
        "sent_this_week": sent_this_week(_queue_rows(), brand_id, now=now),
    }


def counts(brand: str, *, now: datetime | None = None) -> dict[str, Any]:
    """One brand's counts, or 'all' added up with each brand's own under ``brands``."""
    from _lib.marketing_calendar import VALID_BRAND_IDS  # noqa: PLC0415

    if brand != "all":
        if brand not in VALID_BRAND_IDS:
            raise ValueError(f"brand_id '{brand}' is not an operating brand")
        return {"brand": brand, **brand_counts(brand, now=now)}
    per = {b: brand_counts(b, now=now) for b in VALID_BRAND_IDS}
    total = {k: sum(c[k] for c in per.values()) for k in KEYS}
    return {"brand": "all", **total, "brands": per}
