"""Space out posts of one brand that go out together (audit, 3 Nov 2026).

Due and Publish-now rows were all handed to Postiz as now + 5 minutes, so three Stick
posts landed at the same minute. Each post (not each platform) gets its own time,
GAP apart, after any post the brand already sent today; a slot later than LATEST SAST
moves to FIRST SAST the next morning.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")
LEAD = timedelta(minutes=5)  # Postiz is never given "now" (postiz_client.scheduled_at_least)
GAP = timedelta(hours=3)
LATEST = time(19, 30)
FIRST = time(9, 0)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: Optional[str]) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _within_day(slot: datetime) -> datetime:
    local = slot.astimezone(SAST)
    if local.time() <= LATEST:
        return slot
    next_morning = datetime.combine(local.date() + timedelta(days=1), FIRST, tzinfo=SAST)
    return next_morning.astimezone(timezone.utc)


def spaced_times(
    posts: Iterable[tuple[str, str]],
    *,
    now: Optional[datetime] = None,
    last_today: Optional[dict[str, str]] = None,
) -> dict[tuple[str, str], str]:
    """(brand, post) pairs in send order → a UTC send time, one per post."""
    now = now or datetime.now(timezone.utc)
    nxt: dict[str, datetime] = {}
    out: dict[tuple[str, str], str] = {}
    soonest = now + LEAD
    for brand, post in posts:
        if (brand, post) in out:
            continue
        if brand not in nxt:
            start = soonest
            last = _parse((last_today or {}).get(brand))
            if last and last + GAP > start:
                start = last + GAP
            nxt[brand] = start
        # The soonest slot is what was asked for (Publish now); only a pushed slot waits for morning.
        slot = nxt[brand] if nxt[brand] == soonest else _within_day(nxt[brand])
        out[(brand, post)] = _iso(slot)
        nxt[brand] = slot + GAP
    return out


def last_sent_today(receipts: Iterable[dict], *, now: Optional[datetime] = None) -> dict[str, str]:
    """Each brand's latest live send time today (SAST), from the receipts."""
    today = (now or datetime.now(timezone.utc)).astimezone(SAST).date()
    latest: dict[str, datetime] = {}
    for r in receipts:
        if str(r.get("mode") or "") == "sandbox":
            continue
        at = _parse(r.get("publish_at") or r.get("dispatched_at"))
        brand = str(r.get("brand_id") or "")
        if not at or not brand or at.astimezone(SAST).date() != today:
            continue
        if brand not in latest or at > latest[brand]:
            latest[brand] = at
    return {b: _iso(t) for b, t in latest.items()}
