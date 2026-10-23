"""Today's story suggestion: one thing to feature and the brand page to repost from.

Pure and deterministic, no model. Days alternate between a retail brand and a
service; the service day names a stocked brand that fits it, so the repost relates
to what we sell. Brands listed under "daily" in story-brands.json (Psycho Bunny
for Stick) get a slot every day. Brands without a page we can open (RipIt, for
now) are skipped. The lists live in data/brand-directory/<brand>/story-brands.json.

A stock line from the weekly stock list can also be the day's story: our own
product, shot or enhanced from our photo, with no repost link.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "data" / "brand-directory"


def _load(brand: str) -> dict | None:
    try:
        return json.loads((_ROOT / brand / "story-brands.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _page(b: dict) -> dict:
    return {"id": b["id"], "name": b["name"], "instagram": b.get("instagram"),
            "facebook": b.get("facebook"), "look_for": b.get("look_for", "")}


def daily_ids(brand: str) -> list[str]:
    """Brands that get a slot every day (story-brands.json "daily")."""
    data = _load(brand) or {}
    return list(data.get("daily") or [])


def suggest(brand: str, day: date, settings: dict | None = None) -> list[dict]:
    """Today's set for one brand: a retail brand, a service, and a golf moment when pages exist.

    settings comes from story_settings.read(); a daily brand switched off there gets no slot.
    """
    data = _load(brand)
    if not data:
        return []
    on = (settings or {}).get("daily_on") or {}
    n = day.toordinal()
    retail = [b for b in data["retail"] if b.get("instagram") or b.get("facebook")]
    daily_ids = set(data.get("daily") or [])
    daily = [b for b in retail if b["id"] in daily_ids]
    retail = [b for b in retail if b["id"] not in daily_ids]
    services = data.get("services") or []
    moments = [m for m in data.get("moments") or [] if m.get("instagram") or m.get("facebook")]
    out = []
    for b in daily:
        if not on.get(b["id"], True):
            continue
        out.append({"brand": brand, "date": day.isoformat(), "kind": "daily",
                    "feature": b["name"], "repost_from": _page(b)})
    paired_id = None
    if services:
        svc = services[n % len(services)]
        paired = next((b for b in retail if b["id"] == svc.get("pairs_with")), None)
        used = paired or (retail[n % len(retail)] if retail else None)
        paired_id = used["id"] if used else None
        out.append({"brand": brand, "date": day.isoformat(), "kind": "service", "feature": svc["name"],
                    "repost_from": _page(used)} if used else None)
    # The retail pick avoids the brand the service already uses, so the two stories differ.
    pool = [b for b in retail if b["id"] != paired_id] or retail
    if pool:
        pick = pool[n % len(pool)]
        out.append({"brand": brand, "date": day.isoformat(), "kind": "retail",
                    "feature": pick["name"], "repost_from": _page(pick)})
    if moments:
        m = moments[n % len(moments)]
        out.append({"brand": brand, "date": day.isoformat(), "kind": "moment",
                    "feature": m["name"], "repost_from": _page(m)})
    return [x for x in out if x]


def stock_story(brand: str, day: date, candidates: list[dict]) -> dict | None:
    """Today's stock story: one line from the stock list, rotating by day. None when no list is saved."""
    if not candidates:
        return None
    c = candidates[day.toordinal() % len(candidates)]
    why = c.get("reason") or ""
    return {"brand": brand, "date": day.isoformat(), "kind": "stock",
            "feature": c["name"], "repost_from": None, "why": why}


def stock_stories(brand: str, day: date, candidates: list[dict], count: int) -> list[dict]:
    """Up to `count` stock stories for the day, rotating through the candidates. Empty when none saved."""
    if not candidates or count <= 0:
        return []
    out, n = [], day.toordinal()
    for k in range(min(count, len(candidates))):
        c = candidates[(n + k) % len(candidates)]
        out.append({"brand": brand, "date": day.isoformat(), "kind": "stock",
                    "feature": c["name"], "repost_from": None, "why": c.get("reason") or ""})
    return out
