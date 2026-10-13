"""Approved dates that are close and not ready: no plan, no content.

A date on the Main Calendar with nothing prepared for it is the failure the
team cannot afford to miss, so this lists them loudly. Pure: the route in
app.py reads the stores and passes rows in.

An event is "covered" when its plan is on the calendar (the steps are dated and
booked), or when content for it is already booked in the run-up. Otherwise it
is flagged, and the flag gets louder as the day nears:

    A-PIN   warn from 35 days out, scream from 21
    B-PIN   warn from 21 days out, scream from 10
    C-PIN   never flagged (public holidays and the like)

An approved entry with no tier counts as B.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Iterable, List, Optional

WARN_DAYS = {"A-PIN": 35, "B-PIN": 21}
SCREAM_DAYS = {"A-PIN": 21, "B-PIN": 10}

# How far before an event booked content still counts as being for it.
CONTENT_WINDOW_DAYS = 10


def _parse(iso: Any) -> Optional[_dt.date]:
    try:
        return _dt.date.fromisoformat(str(iso or "")[:10])
    except ValueError:
        return None


def _tier(raw: Any) -> str:
    return raw if raw in ("A-PIN", "B-PIN", "C-PIN") else "B-PIN"


def _state(brief_id: Optional[str], plan: Optional[Dict[str, Any]]) -> str:
    """no_plan | plan_draft | plan_approved | on_calendar"""
    if plan and plan.get("placed_at"):
        return "on_calendar"
    if plan and plan.get("status") == "approved":
        return "plan_approved"
    if plan:
        return "plan_draft"
    return "no_plan"


_WORDS = {
    "no_plan": "has no plan",
    "plan_draft": "has a draft plan that is not approved",
    "plan_approved": "has an approved plan that is not on the calendar",
}


def _days_phrase(n: int) -> str:
    if n == 0:
        return "is today"
    if n == 1:
        return "is tomorrow"
    return f"is in {n} days"


def find_alerts(
    brand_id: str,
    events: Iterable[Dict[str, Any]],
    briefs_by_event: Dict[str, str],
    plans_by_brief: Dict[str, Dict[str, Any]],
    content_dates: Iterable[Any],
    today: _dt.date,
) -> List[Dict[str, Any]]:
    """Alerts for approved events, most urgent first.

    events           [{id/event_key, name, start, tier}] approved on the calendar
    briefs_by_event  {event key: brief id}
    plans_by_brief   {brief id: live plan}
    content_dates    dates of content already booked (not made by a plan)
    """
    booked = sorted(d for d in (_parse(x) for x in content_dates) if d)
    out: List[Dict[str, Any]] = []
    seen = set()
    for e in events:
        start = _parse(e.get("start") or e.get("event_start"))
        name = str(e.get("name") or e.get("title") or "").strip()
        key = e.get("event_key") or e.get("id")
        if not start or not name or not key:
            continue
        tier = _tier(e.get("tier"))
        if tier not in WARN_DAYS:
            continue
        days = (start - today).days
        if days < 0 or days > WARN_DAYS[tier] or (name.lower(), start) in seen:
            continue
        seen.add((name.lower(), start))
        brief_id = briefs_by_event.get(key) or ""
        plan = plans_by_brief.get(brief_id) if brief_id else None
        state = _state(brief_id, plan)
        if state == "on_calendar":
            continue
        window_start = start - _dt.timedelta(days=CONTENT_WINDOW_DAYS)
        if any(window_start <= d <= start for d in booked):
            continue
        level = "scream" if days <= SCREAM_DAYS[tier] else "warn"
        out.append({
            "event_key": key,
            "name": name,
            "date": start.isoformat(),
            "days": days,
            "tier": tier,
            "level": level,
            "state": state,
            "brief_id": brief_id or None,
            "plan_id": (plan or {}).get("plan_id"),
            "brand_id": brand_id,
            "kind": e.get("kind") or "standard",
            "message": f"{name} {_days_phrase(days)} and {_WORDS[state]}.",
        })
    out.sort(key=lambda a: (a["level"] != "scream", a["days"], a["name"]))
    return out
