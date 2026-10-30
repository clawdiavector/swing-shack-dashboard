"""plan_todo.py — the working list that comes out of the plans, and the morning message.

Every plan is a list of dated steps, spread over many plans. This puts them in
one list by date (overdue, today, this week, later), so the day's work is in one
place, and writes the short message a person reads first thing.

Pure: the routes in app.py read the plans and the alerts and pass them in.
"""
from __future__ import annotations

import datetime as _dt
import re as _re
from typing import Any, Dict, Iterable, List, Optional

BUCKETS = ("overdue", "today", "this_week", "later")
BUCKET_LABEL = {
    "overdue": "Overdue",
    "today": "Today",
    "this_week": "This week",
    "later": "Coming up",
}
KIND_LABEL = {
    "research": "Check", "decide": "Decide", "shoot": "Shoot", "edit": "Edit",
    "review": "Approve", "post": "Post", "story": "Story", "boost": "Boost",
}
BRAND_LABEL = {"stick": "Stick", "swing-shack": "Swing Shack", "bag-drop": "Bag Drop"}

HORIZON_DAYS = 30
WEEK_DAYS = 7


def _parse(iso: Any) -> Optional[_dt.date]:
    try:
        return _dt.date.fromisoformat(str(iso or "")[:10])
    except ValueError:
        return None


def bucket_for(due: _dt.date, today: _dt.date) -> Optional[str]:
    """Which part of the list a step falls in; None when it is too far off to show."""
    n = (due - today).days
    if n < 0:
        return "overdue"
    if n == 0:
        return "today"
    if n <= WEEK_DAYS:
        return "this_week"
    if n <= HORIZON_DAYS:
        return "later"
    return None


def todo_steps(brand_id: str, plans: Iterable[Dict[str, Any]], today: _dt.date) -> List[Dict[str, Any]]:
    """Steps still to do, from every live plan, soonest first (overdue first of all).

    A step is still to do when it is not done and not removed. Superseded plans
    are ignored. What each step needs next is carried with it (a shoot with no
    shot list, a shoot nobody has been asked for, a boost with no budget).
    """
    out: List[Dict[str, Any]] = []
    for p in plans:
        if p.get("status") == "superseded":
            continue
        for i in p.get("items") or []:
            if i.get("status") in ("done", "removed"):
                continue
            due = _parse(i.get("due"))
            if not due:
                continue
            b = bucket_for(due, today)
            if not b:
                continue
            kind = i.get("kind") or ""
            needs: List[str] = []
            if kind == "shoot" and not i.get("shots"):
                needs.append("no shot list yet")
            if kind == "shoot" and i.get("shots") and i.get("shots_suggested"):
                needs.append("suggested shots: check them")
            if kind == "shoot" and not i.get("asked"):
                needs.append("nobody asked yet")
            if kind == "boost" and not i.get("budget"):
                needs.append("no budget yet")
            if kind == "post" and p.get("status") == "approved" and i.get("calendar_id") and not i.get("draft"):
                needs.append("no draft yet")
            out.append({
                "key": f"{p['plan_id']}:{i['item_id']}",
                "brand_id": brand_id,
                "plan_id": p["plan_id"],
                "item_id": i["item_id"],
                "step": kind,
                "title": i.get("title") or "",
                "due": due.isoformat(),
                "days": (due - today).days,
                "bucket": b,
                "event_name": p.get("event_name") or "",
                "event_date": p.get("event_date") or "",
                "event_kind": p.get("event_kind") or p.get("profile") or "standard",
                "plan_status": p.get("status"),
                "asked": i.get("asked"),
                "draft": i.get("draft"),
                "needs": needs,
            })
    out.sort(key=lambda s: (BUCKETS.index(s["bucket"]), s["due"], s["event_name"], s["title"]))
    return out


def group_by_bucket(steps: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {b: [] for b in BUCKETS}
    for s in steps:
        out[s["bucket"]].append(s)
    return out


# ── the morning message ──────────────────────────────────────────────

MAX_LINES = 5


def _ago(days: int) -> str:
    return "yesterday" if days == -1 else f"{-days} days ago"


def _line(s: Dict[str, Any]) -> str:
    extra = f" ({', '.join(s['needs'])})" if s.get("needs") else ""
    when = f", was due {_ago(s['days'])}" if s["bucket"] == "overdue" else ""
    return f"• {KIND_LABEL.get(s['step'], s['step'])}: {s['title']} — {s['event_name']}{when}{extra}"


def _block(heading: str, lines: List[str]) -> List[str]:
    if not lines:
        return []
    shown = lines[:MAX_LINES]
    more = len(lines) - len(shown)
    return ["", heading, *shown, *([f"…and {more} more"] if more > 0 else [])]


def morning_text(
    sections: Dict[str, Dict[str, Any]],
    today: _dt.date,
) -> str:
    """The message. `sections` is {brand_id: {"alerts": [...], "steps": [...]}}.

    Alerts come first, because those are the dates that are close with nothing
    ready. Then what is overdue and what is due today. This week and later are
    left out: the message is for what needs you now. Nothing to say is said too.
    """
    lines = [f"Good morning. Calendar check, {today.strftime('%a')} {today.day} {today.strftime('%b')}."]
    anything = False
    for brand_id, sec in sections.items():
        alerts = sec.get("alerts") or []
        steps = sec.get("steps") or []
        loud = [a for a in alerts if a.get("level") == "scream"]
        overdue = [s for s in steps if s["bucket"] == "overdue"]
        today_steps = [s for s in steps if s["bucket"] == "today"]
        block: List[str] = []
        block += _block("Close and not ready:", [f"• {a['message']}" for a in loud])
        block += _block(f"Overdue ({len(overdue)}):", [_line(s) for s in overdue])
        block += _block(f"Due today ({len(today_steps)}):", [_line(s) for s in today_steps])
        if block:
            anything = True
            if len(sections) > 1:
                lines += ["", f"— {BRAND_LABEL.get(brand_id, brand_id)} —"]
            lines += block
    if not anything:
        lines += ["", "Nothing needs you today."]
    return "\n".join(lines)


def week_bounds(today: _dt.date) -> tuple:
    """Monday and Sunday of the week `today` falls in."""
    monday = today - _dt.timedelta(days=today.weekday())
    return monday, monday + _dt.timedelta(days=6)


def _day(d: _dt.date) -> str:
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


_GENERIC_ROW = _re.compile(r"^(instagram|facebook|tiktok)\s+(story|stories|reel|post|video)s?$", _re.I)
_TRAILING_TAG = _re.compile(r"\s*\([^)]*\)\s*$")
WEEKLY_SHOWN = 6


def _plain_title(title: Any) -> Optional[str]:
    """A calendar row's name as a person would say it, or None when it is not a name.

    Left out: the generic "Instagram story" rows, caption sentences, and anything long
    enough to be a caption. A trailing "(resend)" or "(retail B)" tag is dropped.
    """
    t = _TRAILING_TAG.sub("", str(title or "").strip())
    if not t or _GENERIC_ROW.match(t) or t.endswith((".", "!", "?")) or len(t) > 60:
        return None
    return t


def weekly_selling_text(sections: Dict[str, Dict[str, Any]], today: _dt.date) -> str:
    """Monday's message: what is on each facility's calendar this week, in plain words.

    `sections` is {brand_id: {"items": [{"date": iso, "title": str}]}}. Items outside
    Monday to Sunday, generic story rows, caption lines and repeats are left out, six
    are shown per facility, and a facility with nothing says so.
    """
    monday, sunday = week_bounds(today)
    lines = [f"Good morning. What we are selling this week, {_day(monday)} to {_day(sunday)}.",
             "", "Here's what is lined up at each place."]
    for brand_id, sec in sections.items():
        week = sorted(
            ((d, i) for i in sec.get("items") or [] if (d := _parse(i.get("date"))) and monday <= d <= sunday),
            key=lambda p: (p[0], str(p[1].get("title"))),
        )
        seen, shown = set(), []
        for d, i in week:
            name = _plain_title(i.get("title"))
            if name and name.lower() not in seen:
                seen.add(name.lower())
                shown.append(f"• {_day(d)}: {name}")
        lines += ["", f"— {BRAND_LABEL.get(brand_id, brand_id)} —"]
        if not shown:
            lines.append("Nothing on the calendar yet.")
            continue
        lines += shown[:WEEKLY_SHOWN]
        if len(shown) > WEEKLY_SHOWN:
            lines.append(f"Plus {len(shown) - WEEKLY_SHOWN} more lined up.")
    return "\n".join(lines + ["", "Have a good week."])


def weekly_report_text(links: Dict[str, str], today: _dt.date) -> str:
    """Tuesday's message: one weekly report link per facility."""
    lines = [f"Good morning. The weekly report, {_day(today)}.", "", "Here's how last week went at each place:", ""]
    lines += [f"{BRAND_LABEL.get(b, b)}: {url}" for b, url in links.items()]
    lines += ["", "Each link opens without a login and works for 7 days."]
    return "\n".join(lines)
