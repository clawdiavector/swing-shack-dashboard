"""Messages for each facility's staff (sent on WhatsApp, next to Foreman's Telegram ones).

Written for the people in the shop, not for Christelle: what customers will see online
this week, what goes out today, stories to share, and last week's report. Each builder
returns {"send": bool, "text": str}; "send" is False when there is nothing worth a message.
Pure functions: the route gathers calendar entries (clean_calendar.month_view shape) and
story links, and may pass topics a model wrote (checked with parse_topics first).
Wording approved by Christelle, 13 Nov 2026.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Dict, Iterable, List, Optional

BRAND_LABEL = {"stick": "Stick", "swing-shack": "Swing Shack", "bag-drop": "Bag Drop"}
MAX_ITEMS = 5
HEADLINE_MAX = 60
TOPIC_MAX = 60

# Titles that only say where a post went, not what it was about.
_PLACEHOLDER = re.compile(
    r"^(untitled( post)?|((instagram|facebook|tiktok|google|youtube)\s*)?(story|reel|post|video|short)?)$"
)


def _label(brand: str) -> str:
    return BRAND_LABEL.get(brand, brand)


def _day(d: _dt.date) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def _parse(iso: Any) -> Optional[_dt.date]:
    try:
        return _dt.date.fromisoformat(str(iso or "")[:10])
    except ValueError:
        return None


def week_bounds(today: _dt.date) -> tuple:
    monday = today - _dt.timedelta(days=today.weekday())
    return monday, monday + _dt.timedelta(days=6)


def _range(monday: _dt.date, sunday: _dt.date) -> str:
    if monday.month == sunday.month:
        return f"{monday.day}–{sunday.day} {sunday:%b}"
    return f"{monday.day} {monday:%b}–{sunday.day} {sunday:%b}"


def is_placeholder(title: Any) -> bool:
    t = re.sub(r"[^a-z ]", "", str(title or "").lower()).strip()
    return bool(_PLACEHOLDER.match(re.sub(r"\s+", " ", t)))


def headline(title: Any) -> str:
    """The first sentence of a title or caption, cut at a word if it is still long."""
    first = str(title or "").strip().split("\n", 1)[0].strip()
    first = re.split(r"(?<=[.!?])\s", first, maxsplit=1)[0].rstrip(".!? ").strip()
    if len(first) <= HEADLINE_MAX:
        return first
    return first[:HEADLINE_MAX].rsplit(" ", 1)[0].rstrip(" ,;:-–") + "…"


def is_live(entry: Dict[str, Any]) -> bool:
    """Customers see it: posted, scheduled or posted outside Campaign OS, with a real title."""
    return entry.get("view") == "scheduled" and not is_placeholder(entry.get("title"))


def week_entries(entries: Iterable[Dict[str, Any]], today: _dt.date) -> List[Dict[str, Any]]:
    monday, sunday = week_bounds(today)
    out = [e for e in entries if is_live(e) and (d := _parse(e.get("date"))) and monday <= d <= sunday]
    return sorted(out, key=lambda e: (str(e.get("date")), str(e.get("title"))))


def headlines(entries: Iterable[Dict[str, Any]], limit: int = MAX_ITEMS) -> List[str]:
    seen, out = set(), []
    for e in entries:
        h = headline(e.get("title"))
        if h and h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
    return out[:limit]


def parse_topics(raw: Any) -> Optional[List[str]]:
    """Topic lines a model wrote, or None if they don't look like short topics."""
    lines = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", ln).strip() for ln in str(raw or "").splitlines()]
    topics = [ln.rstrip(".") for ln in lines if ln]
    if not topics or len(topics) > MAX_ITEMS + 1:
        return None
    if any(len(t) > TOPIC_MAX or re.search(r"\d", t) for t in topics):
        return None
    return topics


def topics_prompt(brand: str, entries: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    posts = "\n\n".join(f"- {e.get('title')}\n{str(e.get('caption') or '')[:400]}" for e in entries)
    return [
        {"role": "system", "content": (
            "You tell shop staff what their business is posting about online this week, so they "
            "know what customers may ask. Reply with 3 to 5 lines, each a short plain topic of at "
            "most 6 words, like 'Club and ball fittings' or 'The new Srixon RKT irons'. Name only "
            "products, services and campaigns the posts mention. No prices, percentages, dates or "
            "other numbers. No sales language, no emoji, no intro line.")},
        {"role": "user", "content": f"{_label(brand)}'s posts this week:\n\n{posts}"},
    ]


def week_message(brand: str, entries: Iterable[Dict[str, Any]], today: _dt.date,
                 topics: Optional[List[str]] = None) -> Dict[str, Any]:
    """Monday: what customers will see online this week."""
    week = week_entries(entries, today)
    if not week:
        return {"send": False, "text": ""}
    items = topics or headlines(week)
    monday, sunday = week_bounds(today)
    lines = [f"Morning {_label(brand)} team 👋", "",
             f"This week online ({_range(monday, sunday)}) we're talking about:"]
    lines += [f"• {t}" for t in items[:MAX_ITEMS]]
    lines += ["", "If a customer mentions something they saw online, it's probably one of these."]
    return {"send": True, "text": "\n".join(lines)}


def today_message(brand: str, entries: Iterable[Dict[str, Any]], today: _dt.date) -> Dict[str, Any]:
    """Every morning: what goes out on the brand's channels today."""
    todays = [e for e in entries if is_live(e) and _parse(e.get("date")) == today]
    if not todays:
        return {"send": False, "text": ""}
    seen, lines = set(), []
    for e in sorted(todays, key=lambda e: (str(e.get("where")), str(e.get("title")))):
        line = f"• {e.get('where') or 'Instagram'}: {headline(e.get('title'))}"
        if line not in seen:
            seen.add(line)
            lines.append(line)
    text = "\n".join([f"Today on {_label(brand)}'s socials ({_day(today)}):", *lines[:MAX_ITEMS * 2], "",
                      "Nothing for you to do. Just know what customers might ask about."])
    return {"send": True, "text": text}


def stories_message(brand: str, items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Every morning: open story links to share, if there are any."""
    items = [i for i in items if i.get("url")]
    if not items:
        return {"send": False, "text": ""}
    n = len(items)
    lines = [f"{n} {'story' if n == 1 else 'stories'} to share today 📲"]
    for k, it in enumerate(items, 1):
        note = str(it.get("note") or "").strip()
        lines.append(f"{k}. {note}: {it['url']}" if note else f"{k}. {it['url']}")
    lines += ["", "Open the link on your phone, tap the paper plane, then \"Add to story\"."]
    return {"send": True, "text": "\n".join(lines)}


def report_message(brand: str, link: str) -> Dict[str, Any]:
    """Tuesday: last week's report for this facility."""
    text = f"How {_label(brand)} did online last week 📊\n{link}\n\nOpens without a login, works for 7 days."
    return {"send": True, "text": text}
