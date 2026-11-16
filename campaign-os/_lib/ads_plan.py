"""Ads a week ahead: what to advertise next week, so the money is set aside and the reel is ready.

Pure. The page passes in what the calendar, the campaign plans and the stock list already hold:

    posts         Plan calendar posts (clean_calendar.post_entry rows: key, date, format, caption, title, plan_id)
    boost_steps   campaign plan steps (campaign_plan.month_steps rows); a "boost" step is a planned ad slot
    campaigns     campaign umbrellas with start and end dates (marketing_lanes.list_campaigns)
    stock         this week's stock lines (stock_pulse analyse rows: name, status, qty)

For each post landing in the next 7 days it says which ad type to run, from the day after it lands, how much to set
aside from that week's budget, and which campaign it serves. New or returning stock with no post planned is flagged,
so someone films a reel for it before the week starts.
"""
from __future__ import annotations

import datetime as _dt
import re

from . import ads_suggest as sg

AHEAD_DAYS = 7
STOCK_WORTH = ("new", "back")


def _d(v):
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _window(c: dict):
    w = c.get("window") or {}
    return _d(c.get("start_date") or w.get("start")), _d(c.get("end_date") or w.get("end"))


def _campaign_on(day: _dt.date, campaigns: list) -> str | None:
    for c in campaigns or []:
        start, end = _window(c)
        if start and end and start <= day <= end:
            return c.get("name") or c.get("title") or c.get("campaign_id")
    return None


def _words(name: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(w) >= 4][:2]


def upcoming(brand_id: str, *, posts: list, boost_steps: list, campaigns: list, stock: list, settings: dict | None,
             figures: dict | None, brief: dict | None, learned: dict | None, today: _dt.date) -> dict:
    site = sg.SITES.get(brand_id) or {}
    first, last = today + _dt.timedelta(days=1), today + _dt.timedelta(days=AHEAD_DAYS)
    costs = sg.unit_costs(brief or {})
    budget = sg.weekly_budget(settings or {}, today)
    room = max(0.0, budget - float((figures or {}).get("daily_run_rate") or 0) * 7)
    plan_events = {s.get("plan_id"): s.get("event_name") for s in boost_steps or [] if s.get("event_name")}

    raw = []
    for p in posts or []:
        day = _d(p.get("date"))
        if not day or not first <= day <= last or p.get("format") not in ("reel", "feed"):
            continue
        text = p.get("caption") or p.get("title") or ""
        theme = sg.theme_of(text)
        if not theme:
            continue
        if p["format"] == "feed" and theme not in sg.PRODUCT_THEMES:
            continue
        raw.append({"key": p["key"], "source": "calendar", "date": day, "start": day + _dt.timedelta(days=1),
                    "text": text, "title": p.get("title") or text[:60], "format": p["format"], "theme": theme,
                    "context": _campaign_on(day, campaigns) or plan_events.get(p.get("plan_id"))})
    for s in boost_steps or []:
        day = _d(s.get("date"))
        if s.get("step") != "boost" or not day or not first <= day <= last:
            continue
        raw.append({"key": s["key"], "source": "plan_boost", "date": day, "start": day, "text": s.get("title") or "",
                    "title": s.get("title") or "Planned boost", "format": "reel",
                    "theme": sg.theme_of(s.get("title") or "") or None,
                    "context": s.get("event_name") or _campaign_on(day, campaigns)})
    raw.sort(key=lambda r: r["start"])

    items = []
    for r in raw:
        item = {k: (v.isoformat() if isinstance(v, _dt.date) else v) for k, v in r.items()}
        lands = f"Lands {r['date']:%a %d %b}" if r["source"] == "calendar" else f"Boost step planned for {r['date']:%a %d %b}"
        item["why"] = lands + (f", part of {r['context']}" if r["context"] else "") + "."
        if r["format"] == "feed":
            item.update({"ad_type": "animated_still", "spend": None,
                         "money": f"Animate the product photo before {r['date']:%d %b} so it can run as a messages ad."})
            items.append(item)
            continue
        pick = sg.choose_type(r["theme"], r["text"], site, standout=False, costs=costs, learned=learned)
        kind = pick["ad_type"] if r["theme"] else "awareness"
        cost, where = sg._cost_for(kind, r["theme"], costs, learned)
        spend = sg._spend(kind, cost, where)
        if room >= spend["total"]:
            money = (f"Set aside {sg._r(spend['total'])} from the budget for the week of {r['start']:%d %b}; "
                     f"{sg._r(room - spend['total'])} stays free after this.")
            room -= spend["total"]
        else:
            money = (f"Set aside {sg._r(spend['total'])}, but only {sg._r(room)} is free that week: the rest "
                     "needs Herman's yes, or a weaker ad paused.")
            room = 0.0
        item.update({"ad_type": kind, "type_reason": pick["type_reason"], "spend": spend, "money": money})
        items.append(item)

    planned = " ".join((p.get("caption") or p.get("title") or "").lower() for p in posts or []
                       if (_d(p.get("date")) or today) >= today)
    gaps = []
    for s in stock or []:
        if s.get("status") not in STOCK_WORTH:
            continue
        words = _words(s.get("name"))
        if words and all(w in planned for w in words):
            continue
        gaps.append({"name": s.get("name"), "status": s.get("status"), "qty": s.get("qty"),
                     "todo": ("Film a short real-person reel of it (or animate the product photo) and put it on the "
                              "calendar, so it can run as a messages ad next week.")})
    return {"brand_id": brand_id, "window": {"start": first.isoformat(), "end": last.isoformat()},
            "items": items, "stock_gaps": gaps}
