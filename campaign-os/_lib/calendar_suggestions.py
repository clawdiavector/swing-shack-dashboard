"""Suggestions drawn on the month calendar, faded, until someone decides.

Three kinds of thing wait for a yes and used to be invisible on the grid:

  yours   a date the operator typed through "New date or campaign"
  scout   a date an agent found and filed as a candidate
  date    an entry on the operator's own list of important dates

`month_items()` lists the ones that start in a month (a long one is drawn
on its first day only). Pure: the routes in
app.py read the stores and pass rows in. Decisions on important dates (which
have no row of their own until approved) are kept in a small file so a
rejected date stops being offered and an undo brings it back.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import uuid
from typing import Any, Dict, Iterable, List, Optional

from _lib.data_paths import runtime_data_dir as _runtime_data_dir
from _lib.plan_profiles import event_kind
from _lib.plan_extras import _JUNK_TITLE_RE, _key, _parse, dates_to_note, _same_event

SOURCES = ("yours", "scout", "date", "stock")
# Sources decided on by key: approve, reject or swap is written to the decisions file.
DECIDED_SOURCES = ("date", "stock")
# A stock suggestion every other day, so a month shows a steady rhythm and not a wall.
STOCK_EVERY_DAYS = 2


def month_bounds(month: str) -> tuple[_dt.date, _dt.date]:
    """(first day, last day) of 'YYYY-MM'. Raises ValueError on bad input."""
    if not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        raise ValueError("month must be YYYY-MM")
    y, m = int(month[:4]), int(month[5:7])
    first = _dt.date(y, m, 1)
    nxt = _dt.date(y + (m == 12), (m % 12) + 1, 1)
    return first, nxt - _dt.timedelta(days=1)


def _row_date(r: Dict[str, Any]) -> Optional[_dt.date]:
    return _parse(r.get("public_peak") or r.get("event_start") or r.get("event_date") or r.get("start"))


def row_key(calendar_id: str) -> str:
    return f"row:{calendar_id}"


def month_items(
    brand_id: str,
    month: str,
    pending_rows: Iterable[Dict[str, Any]],
    typed_by_operator,
    note_rows: Iterable[Dict[str, Any]],
    decisions: Dict[str, Any],
    approved_names: Iterable[str],
    today: _dt.date,
) -> List[Dict[str, Any]]:
    """Faded suggestions for `month`, soonest first.

    pending_rows   operator-store rows still waiting (current status candidate)
    typed_by_operator   fn(row) -> True when a person filed it
    note_rows      important-dates and golf-moments rows
    decisions      {note id: {"decision": ...}} for important dates already decided
    approved_names names already on the calendar, so the same event is not offered twice
    """
    first, last = month_bounds(month)
    approved = [k for k in (_key(n) for n in approved_names) if k]
    out: List[Dict[str, Any]] = []
    seen = set()

    for r in pending_rows:
        cid = r.get("calendar_id") or r.get("event_key")
        title = str(r.get("title") or r.get("name") or "").strip()
        d = _row_date(r)
        if not cid or not title or not d:
            continue
        mine = bool(typed_by_operator(r))
        if not mine and (d < today or _JUNK_TITLE_RE.search(title)):
            continue
        # A find by an agent that is already on the calendar is not a suggestion.
        # One the operator typed stays: they asked for it by name.
        if not mine and any(_same_event(_key(title), t) for t in approved):
            continue
        end = _parse(r.get("event_end") or r.get("end")) or d
        if not first <= d <= last:  # drawn once, on its first day
            continue
        k = _key(title)
        if (k, d) in seen:
            continue
        seen.add((k, d))
        out.append({
            "key": row_key(cid),
            "source": "yours" if mine else "scout",
            "title": title,
            "date": d.isoformat(),
            "end": end.isoformat(),
            "tier": r.get("tier") if r.get("tier") in ("A-PIN", "B-PIN", "C-PIN") else None,
            "category": r.get("category") or (r.get("type") or "").replace("_", " "),
            "why": r.get("why_it_matters") or r.get("summary") or r.get("relevance_reason") or r.get("angle") or "",
            "calendar_id": cid,
            "pillars": [p for p in (r.get("pillars") or []) if isinstance(p, str)],
            "kind": event_kind({**r, "name": title, "start": d.isoformat(), "end": end.isoformat()}),
        })

    taken = list(approved) + [_key(i["title"]) for i in out]
    for n in dates_to_note(brand_id, note_rows, first, last, already_named=taken):
        # Approved and rejected dates are done with. "Not now" keeps a date on the grid.
        if (decisions.get(n["id"]) or {}).get("decision") in ("approved", "rejected", "archived"):
            continue
        if not first <= _parse(n["start"]) <= last:
            continue
        if any(_same_event(_key(n["name"]), t) for t in taken):
            continue
        out.append({
            "key": n["id"],
            "source": "date",
            "title": n["name"],
            "date": n["start"],
            "end": n["end"],
            "tier": n.get("tier"),
            "category": n.get("category") or "",
            "why": n.get("commercial_push") or "",
            "calendar_id": None,
            "pillars": [],
            "kind": event_kind({"name": n["name"], "tier": n.get("tier"), "category": n.get("category"),
                                "start": n["start"], "end": n["end"]}),
        })

    out.sort(key=lambda i: (i["date"], i["title"]))
    return out


def stock_key(name: str, month: str) -> str:
    """Stable key for a stock line in one month. Decisions are per month, so a
    line still sitting on the shelf can be offered again next month."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return f"stock:{slug}:{month}"


def stock_items(
    brand_id: str,
    month: str,
    candidates: Iterable[Dict[str, Any]],
    decisions: Dict[str, Any],
    approved_names: Iterable[str],
    taken_days: Iterable[str],
    today: _dt.date,
    every: int = STOCK_EVERY_DAYS,
) -> List[Dict[str, Any]]:
    """Stock-list suggestions for `month`: one line every `every` days, from today on.

    candidates   stock_pulse.candidates() for the brand, most urgent first
    decisions    the decisions file; approved, rejected and swapped lines are left out
    approved_names names already on the calendar
    taken_days   ISO dates already holding another suggestion, so stock does not stack on them
    """
    first, last = month_bounds(month)
    start = max(first, today)
    if start > last:
        return []
    taken = set(taken_days)
    approved = [k for k in (_key(n) for n in approved_names) if k]
    every = max(1, int(every))
    days = [start + _dt.timedelta(days=i) for i in range(0, (last - start).days + 1, every)]
    days = [d for d in days if d.isoformat() not in taken]
    open_lines = []
    for c in candidates:
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        key = stock_key(name, month)
        if (decisions.get(key) or {}).get("decision") in ("approved", "rejected", "swapped", "archived"):
            continue
        if any(_same_event(_key(name), t) for t in approved):
            continue
        open_lines.append((key, c))
    out: List[Dict[str, Any]] = []
    for d, (key, c) in zip(days, open_lines):
        reason, idea = (c.get("reason") or "").strip(), (c.get("idea") or "").strip()
        why = f"{reason.rstrip('.')}. {idea}" if reason and idea else (reason or idea)
        item = {
            "key": key,
            "source": "stock",
            "title": c["name"],
            "date": d.isoformat(),
            "end": d.isoformat(),
            "tier": None,
            "category": "Stock list",
            "why": why,
            "calendar_id": None,
            "pillars": [],
            "kind": "stock",
        }
        if brand_id == "swing-shack":
            from _lib import retail_campaign as rc  # noqa: PLC0415

            hist = rc.product_layout_history(brand_id)
            layout = rc.suggest_product_layout(1, hist)
            item["product_layout"] = layout
            item["archetype_id"] = rc.archetype_for_layout(layout)
        out.append(item)
    return out


LATER_DAYS = 14
PRODUCT_NEARBY_DAYS = 7

# Posting states that count as real work on a day (lodged, approved, scheduled, …).
PRIMARY_POST_STATES = frozenset(
    {"booked", "drafting", "needs_fix", "draft_ready", "scheduled", "released", "posted"}
)


def is_primary_post(state: str) -> bool:
    return str(state or "") in PRIMARY_POST_STATES


def _layout_slug_from_template(template_id: str) -> str:
    tid = (template_id or "").lower()
    for slug in ("one-hero", "type-hero", "pick-yours"):
        if slug in tid:
            return slug
    return ""


def _post_layout(post: Dict[str, Any]) -> str:
    layout = str(post.get("layout") or "")
    if layout:
        return layout
    return _layout_slug_from_template(str(post.get("template_id") or ""))


def _record_layouts(brand_id: str) -> Dict[str, str]:
    """calendar_id -> product layout, read from the calendar record (archetype,
    post_type or render_spec), since week_board rows carry no layout."""
    try:
        from _lib import retail_campaign as rc  # noqa: PLC0415
        from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

        out: Dict[str, str] = {}
        for rec in canonical_records(brand_id):
            layout = rc._layout_from_record(rec)  # noqa: SLF001
            cid = str(rec.get("calendar_id") or "")
            if layout and cid:
                out[cid] = layout
        return out
    except Exception:  # noqa: BLE001 - suggestions must still render
        return {}


def posts_by_day_for_month(brand_id: str, month: str) -> Dict[str, List[Dict[str, Any]]]:
    """Primary (non-candidate) posts keyed by go-live ISO date in `month`."""
    from _lib.unified_inbox import week_board  # noqa: PLC0415

    first, last = month_bounds(month)
    span = (last - first).days + 1
    try:
        payload = week_board(
            brand_id=brand_id,
            start=first,
            days=span,
            past_days=0,
            include_candidates=True,
            include_undated=False,
        )
    except ValueError:
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    record_layouts = _record_layouts(brand_id)
    for day in payload.get("days_list") or []:
        iso = str(day.get("date") or "")
        if not iso.startswith(month):
            continue
        primaries: List[Dict[str, Any]] = []
        for post in day.get("posts") or []:
            if not is_primary_post(str(post.get("state") or "")):
                continue
            # T9 outside posts already draw their own grey chip; not our scheduled posts.
            if str(post.get("post_type") or "") == "posted-outside-campaign-os":
                continue
            row: Dict[str, Any] = {
                "calendar_id": post.get("calendar_id"),
                "title": str(post.get("title") or "").strip(),
                "state": post.get("state"),
            }
            tid = str(post.get("template_id") or "")
            if tid:
                row["template_id"] = tid
            layout = _post_layout({"template_id": tid}) if tid else ""
            layout = layout or record_layouts.get(str(post.get("calendar_id") or ""), "")
            if layout:
                row["layout"] = layout
            primaries.append(row)
        if primaries:
            out[iso] = primaries
    return out


def _product_nearby(title: str, day: _dt.date, posts_by_day: Dict[str, List[Dict[str, Any]]], window: int) -> bool:
    key = _key(title)
    if not key:
        return False
    for offset in range(-window, window + 1):
        if offset == 0:
            continue
        other = day + _dt.timedelta(days=offset)
        for post in posts_by_day.get(other.isoformat()) or []:
            if _key(str(post.get("title") or "")) == key:
                return True
    return False


def _layout_on_previous_day(day: _dt.date, posts_by_day: Dict[str, List[Dict[str, Any]]]) -> str:
    prev = (day - _dt.timedelta(days=1)).isoformat()
    for post in posts_by_day.get(prev) or []:
        layout = _post_layout(post)
        if layout:
            return layout
    return ""


def _annotate_stock_layouts(
    items: List[Dict[str, Any]],
    brand_id: str,
    posts_by_day: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    if brand_id != "swing-shack":
        return items
    from _lib import product_post_templates as pt  # noqa: PLC0415

    history: List[str] = []
    for iso in sorted(posts_by_day):
        for post in posts_by_day[iso]:
            layout = _post_layout(post)
            if layout:
                history.append(layout)
    out: List[Dict[str, Any]] = []
    for it in sorted(items, key=lambda i: (i.get("date") or "", i.get("title") or "")):
        if it.get("source") != "stock":
            out.append(it)
            continue
        layout = pt.layout_for(1, history)
        out.append({**it, "_layout": layout})
        history.append(layout)
    return out


def filter_suggestions_nearby_scheduled(
    items: List[Dict[str, Any]],
    posts_by_day: Dict[str, List[Dict[str, Any]]],
    brand_id: str,
    *,
    product_window: int = PRODUCT_NEARBY_DAYS,
) -> List[Dict[str, Any]]:
    """Drop stock lines that repeat a nearby product or the same layout twice in a row."""
    annotated = _annotate_stock_layouts(items, brand_id, posts_by_day)
    kept: List[Dict[str, Any]] = []
    for it in annotated:
        if it.get("source") != "stock":
            kept.append({k: v for k, v in it.items() if k != "_layout"})
            continue
        day = _parse(str(it.get("date") or ""))
        if not day:
            continue
        if _product_nearby(str(it.get("title") or ""), day, posts_by_day, product_window):
            continue
        if brand_id == "swing-shack":
            prev_layout = _layout_on_previous_day(day, posts_by_day)
            if prev_layout and str(it.get("_layout") or "") == prev_layout:
                continue
        kept.append({k: v for k, v in it.items() if k != "_layout"})
    return kept


def month_suggestions_bundle(
    brand_id: str,
    month: str,
    today: _dt.date,
    pending_rows: Iterable[Dict[str, Any]],
    typed_by_operator,
    note_rows: Iterable[Dict[str, Any]],
    decisions: Dict[str, Any],
    approved_names: Iterable[str],
    stock_candidates: Iterable[Dict[str, Any]],
    stock_every: int,
) -> Dict[str, Any]:
    """Faded suggestions plus primary posts per day for the month grid and Today."""
    items = month_items(
        brand_id, month, pending_rows, typed_by_operator, note_rows, decisions, approved_names, today
    )
    taken = [i["date"] for i in items]
    items += stock_items(
        brand_id, month, stock_candidates, decisions, approved_names, taken, today, stock_every
    )
    posts_by_day = posts_by_day_for_month(brand_id, month)
    items = filter_suggestions_nearby_scheduled(items, posts_by_day, brand_id)
    items.sort(key=lambda i: (i["date"], i["title"]))
    return {"items": items, "posts_by_day": posts_by_day}


def triage_items(
    brand_id: str,
    today: _dt.date,
    note_rows: Iterable[Dict[str, Any]],
    approved_names: Iterable[str],
    decisions: Dict[str, Any],
    months: int = 13,
) -> List[Dict[str, Any]]:
    """Important dates still waiting for a decision, soonest first, for the
    next `months` months. A date put off with "not now" is left out of this
    list until its two weeks are up, but stays on the month grid."""
    notes = list(note_rows)
    names = list(approved_names)
    out: List[Dict[str, Any]] = []
    seen = set()
    y, m = today.year, today.month
    for _ in range(months):
        for i in month_items(brand_id, f"{y:04d}-{m:02d}", [], lambda r: False, notes, decisions, names, today):
            if i["source"] != "date" or i["key"] in seen:
                continue
            d = _parse(i["date"])
            if not d or d < today:
                continue
            later = decisions.get(i["key"]) or {}
            if later.get("decision") == "later" and str(later.get("until") or "") > today.isoformat():
                continue
            seen.add(i["key"])
            out.append(i)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    out.sort(key=lambda i: (i["date"], i["title"]))
    return out


SOON_DAYS = 7


def approval_date_check(date_iso: Any, today: _dt.date) -> Dict[str, Any]:
    """Can this date be approved? A date that has passed cannot. One only days away can,
    with a warning, because most of its plan steps will already be late."""
    d = _parse(date_iso)
    if not d:
        return {"ok": False, "error": "this one has no date yet, so it cannot be approved"}
    days = (d - today).days
    if days < 0:
        return {"ok": False, "days": days, "error": f"that date has passed ({d.isoformat()}); pick a date still to come"}
    warning = ""
    if days <= SOON_DAYS:
        warning = (f"Only {days} day{'s' if days != 1 else ''} away, so most plan steps will be late."
                   if days else "That is today, so most plan steps will be late.")
    return {"ok": True, "days": days, "warning": warning}


# ── undo tokens ───────────────────────────────────────────────────────
#
# Approve and reject hand back a token; undo takes the token, not the details.
# What to reverse is read from what the server stored when the action happened,
# so a request cannot name some other record. A token works once and lapses
# after a day.

UNDO_TTL_HOURS = 24


def _undo_path(brand_id: str) -> str:
    return os.path.join(str(_runtime_data_dir()), "calendar-suggestion-undo", f"{brand_id}.json")


def _read_undo(brand_id: str) -> Dict[str, Any]:
    try:
        with open(_undo_path(brand_id), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_undo(brand_id: str, d: Dict[str, Any]) -> None:
    p = _undo_path(brand_id)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, p)


def issue_undo(brand_id: str, payload: Dict[str, Any], now: Optional[_dt.datetime] = None) -> str:
    """Store what an action did and return the token that reverses it."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    keep = {t: v for t, v in _read_undo(brand_id).items()
            if _dt.datetime.fromisoformat(v["at"]) > now - _dt.timedelta(hours=UNDO_TTL_HOURS)}
    token = "und-" + uuid.uuid4().hex[:16]
    keep[token] = {"at": now.isoformat(), "payload": payload}
    _write_undo(brand_id, keep)
    return token


def get_undo(brand_id: str, token: Any, now: Optional[_dt.datetime] = None) -> Optional[Dict[str, Any]]:
    """The stored payload for a token that is known and has not lapsed, else None."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    rec = _read_undo(brand_id).get(str(token or ""))
    if not rec:
        return None
    try:
        if _dt.datetime.fromisoformat(rec["at"]) <= now - _dt.timedelta(hours=UNDO_TTL_HOURS):
            return None
    except (KeyError, ValueError):
        return None
    return rec.get("payload")


def drop_undo(brand_id: str, token: Any) -> None:
    d = _read_undo(brand_id)
    if str(token or "") in d:
        del d[str(token)]
        _write_undo(brand_id, d)


# ── decisions on important dates ──────────────────────────────────────

def _decisions_path(brand_id: str) -> str:
    return os.path.join(str(_runtime_data_dir()), "calendar-suggestion-decisions", f"{brand_id}.json")


def read_decisions(brand_id: str) -> Dict[str, Any]:
    try:
        with open(_decisions_path(brand_id), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_decisions(brand_id: str, d: Dict[str, Any]) -> None:
    p = _decisions_path(brand_id)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def record_decision(brand_id: str, key: str, decision: str, actor: str, **extra: Any) -> None:
    d = read_decisions(brand_id)
    d[key] = {"decision": decision, "actor": actor,
              "at": _dt.datetime.now(_dt.timezone.utc).isoformat(), **extra}
    _write_decisions(brand_id, d)


def clear_decision(brand_id: str, key: str) -> bool:
    d = read_decisions(brand_id)
    if key not in d:
        return False
    del d[key]
    _write_decisions(brand_id, d)
    return True
