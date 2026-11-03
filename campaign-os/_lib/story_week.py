"""How many Stories were shared this week (Monday 00:00 to now, Johannesburg time).

Counts queue items marked done plus Shared marks on idea cards and scouted posts.
A link that is both a queue item and a mark counts once.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import story_marks, story_queue

_TZ = ZoneInfo("Africa/Johannesburg")


def week_start(now: datetime | None = None) -> datetime:
    now = (now or datetime.now(_TZ)).astimezone(_TZ)
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def _since(stamp: str | None, start: datetime) -> bool:
    try:
        return bool(stamp) and datetime.fromisoformat(stamp) >= start
    except ValueError:
        return False


def shared_this_week(brands: list[str] | None = None, now: datetime | None = None) -> int:
    """Brands None means all. A mark with no brand on record counts only when brands is None."""
    start = week_start(now)
    seen: set[str] = set()
    for it in story_queue._load():
        if it.get("status") == "done" and _since(it.get("done_at"), start) and (not brands or it["brand"] in brands):
            seen.add(story_marks.post_key(it["url"]))
    for key, v in story_marks._load().items():
        if not isinstance(v, dict) or v.get("state") != "shared" or not _since(v.get("at"), start):
            continue
        brand = key.split("|")[1] if key.startswith("idea|") else v.get("brand")
        if brands and brand not in brands:
            continue
        seen.add(key)
    return len(seen)
