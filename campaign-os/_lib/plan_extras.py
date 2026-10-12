"""What Plan shows beside the calendar itself: dates to note, and the scout's picks.

Two stores already held this and neither reached Plan's default view:

- The operator's own list of important dates (and the golf-moments list)
  fed only the Month grid. `dates_to_note()` shapes them like timeline
  events so the List and the Timeline can show them.
- Suggestions written by the agents sat in the same store as the
  operator's, mixed with probe and test rows. `scout_suggestions()` picks
  the few worth showing at the top of Plan.

Pure functions: the routes in app.py read the stores and pass rows in.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# "A-LOCAL tier Paarl sport", "B/C-tier shopping", "Rugby. Tier B."
_TIER_RE = re.compile(r"\b([ABC])(?:/[ABC])?(?:-LOCAL)?[- ]tier\b|\btier ([ABC])\b", re.IGNORECASE)

# Local to Stick (Paarl, Western Cape). Swing Shack is in Randburg, so these
# are left off its plan.
_WESTERN_CAPE = (
    "paarl", "boland", "winelands", "western cape", "cape town", "newlands",
    "stellenbosch", "wildeklawer", "cape epic", "cycle tour", "franschhoek",
)
_LOCAL_TO = {"stick": _WESTERN_CAPE}

_JUNK_TITLE_RE = re.compile(r"\bprobe\b|\btest\b|do not release|\bfixture\b|\bplate\b", re.IGNORECASE)

_TYPE_LABELS = {
    "SA_SPORT": "SA sport",
    "GOLF_EVENT": "Golf",
    "GOLF_MOMENT": "Golf",
    "SCHOOL_HOLIDAY": "School",
    "PUBLIC_HOLIDAY": "Public holiday",
    "SHOPPING": "Shopping",
    "RETAIL": "Shopping",
}


def _key(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def tier_of(notes: Any) -> Optional[str]:
    """The tier the operator wrote into a date's notes, as a pin. None if unstated."""
    m = _TIER_RE.search(str(notes or ""))
    if not m:
        return None
    return f"{(m.group(1) or m.group(2)).upper()}-PIN"


def _mentions(row: Dict[str, Any], words: Iterable[str]) -> bool:
    blob = f"{row.get('event_name') or ''} {row.get('notes') or ''} {row.get('venue') or ''}".lower()
    return any(w in blob for w in words)


def _parse(iso: Any) -> Optional[_dt.date]:
    try:
        return _dt.date.fromisoformat(str(iso or "")[:10])
    except ValueError:
        return None


def dates_to_note(
    brand_id: str,
    dates: Iterable[Dict[str, Any]],
    start: _dt.date,
    end: _dt.date,
    already_named: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    """Important dates inside [start, end], shaped like timeline events.

    Skips a date the calendar already carries under the same name (either
    name containing the other, so "Black Friday" does not repeat beside
    "Black Friday + Cyber Monday"), and a date local to another brand's town.
    """
    taken = [k for k in (_key(n) for n in already_named) if k]
    other_brands_local = {
        w for brand, words in _LOCAL_TO.items() if brand != brand_id for w in words
    }
    home = _LOCAL_TO.get(brand_id, ())
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in dates:
        name = str(row.get("event_name") or "").strip()
        d_start = _parse(row.get("start_date") or row.get("date"))
        if not name or not d_start:
            continue
        d_end = _parse(row.get("end_date")) or d_start
        if d_end < start or d_start > end:
            continue
        if _mentions(row, other_brands_local):
            continue
        key = _key(name)
        if (key, d_start) in seen or any(key in t or t in key for t in taken):
            continue
        seen.add((key, d_start))
        event_type = str(row.get("event_type") or "")
        out.append({
            "id": f"note:{key}:{d_start.isoformat()}",
            "name": name,
            "start": d_start.isoformat(),
            "end": d_end.isoformat(),
            "tier": tier_of(row.get("notes")) or "C-PIN",
            "category": _TYPE_LABELS.get(event_type, event_type.replace("_", " ").capitalize()),
            "commercial_push": row.get("notes") or "",
            "note_only": True,
            "local": _mentions(row, home),
        })
    out.sort(key=lambda e: (e["start"], e["name"]))
    return out


def scout_suggestions(
    records: Iterable[Dict[str, Any]],
    today: _dt.date,
    limit: int = 50,
) -> Tuple[List[Dict[str, Any]], int]:
    """The soonest upcoming agent suggestions, and how many there are in all.

    `records` are pending suggestions the operator did not type. Dropped:
    rows with no date or a past one, probe and test rows, and repeats of a
    title already listed.
    """
    picked: List[Dict[str, Any]] = []
    seen = set()
    for r in records:
        title = str(r.get("title") or r.get("name") or "").strip()
        date = _parse(r.get("public_peak") or r.get("event_date") or r.get("event_start") or r.get("start"))
        if not title or not date or date < today or _JUNK_TITLE_RE.search(title):
            continue
        key = _key(title)
        if key in seen:
            continue
        seen.add(key)
        picked.append({
            "candidate_id": r.get("calendar_id") or r.get("event_key"),
            "title": title,
            "date": date.isoformat(),
            "end_date": r.get("event_end") or r.get("end"),
            "type": r.get("type") or "moment",
            "pillars": r.get("pillars") if isinstance(r.get("pillars"), list) else [],
            "why_it_matters": r.get("why_it_matters") or r.get("summary") or r.get("relevance_reason") or r.get("angle"),
            "created_at": r.get("created_at"),
        })
    picked.sort(key=lambda s: (s["date"], s["title"]))
    return picked[:limit], len(picked)
