"""How many placements a day each brand aims for, and how much of each day is made.

Christelle's target (2026-10-27, wiki decisions/daily-posting-target-50-per-brand-2026-10-27):
20 placements a day per brand to start, building to 50; stories count, and a story mirrored
to Facebook counts as its own placement. A brand can carry its own split in data/brands.json
as "daily_target": {"ig_story": 9, ...}; otherwise the default below applies.

A placement is one channel slot: a feed post going to Instagram and Facebook fills two.
"done" is scheduled (or already out); "waiting" is a post that exists but needs a yes or is
still being made. Ideas and plan steps are not made yet, so they count for nothing.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

SLOT_LABELS = {
    "ig_story": "Instagram stories",
    "fb_story": "Facebook stories",
    "ig_feed": "Instagram feed",
    "fb_feed": "Facebook page",
    "reel": "Reels",
    "google": "Google",
    "tiktok": "TikTok",
}

DEFAULT_SPLIT = {"ig_story": 9, "fb_story": 4, "ig_feed": 2, "fb_feed": 1, "reel": 1, "google": 1, "tiktok": 2}

# Brands working towards the target; Bag Drop has no posting channels yet.
TARGET_BRANDS = ("stick", "swing-shack")

_BRANDS_FILE = Path(__file__).resolve().parents[2] / "data" / "brands.json"


# ── the day's lead category ─────────────────────────────────────────────────
# Each day one group leads (40% of the day), the next takes 30%, the other two 15% each.
# In every four days each group leads once, so none leads two days running; the group with the
# most stuck or heavy stock (stock_pulse candidates) leads first in each four.

GROUP_LABELS = {"services": "Services", "off_the_rack": "Off the rack", "accessories": "Accessories",
                "apparel": "Apparel"}
SHARES = (0.40, 0.30, 0.15, 0.15)
_OFF_THE_RACK = {"putter", "wedge", "driver-wood", "iron", "shaft"}
# Services both brands offer (service_tiein, free assessments on both booking widgets, coaching).
SERVICES = ["Free club and swing assessment", "Club fitting", "Ball fitting", "Putter fitting",
            "Wedge gapping", "Re-grip", "Coaching"]
_PUSH_MAX = 5


def group_of(stock_category: str) -> str:
    if stock_category == "apparel":
        return "apparel"
    return "off_the_rack" if stock_category in _OFF_THE_RACK else "accessories"


def split_counts(total: int) -> list[int]:
    """Placements for lead, second, third and fourth, adding up to total."""
    raw = [total * s for s in SHARES]
    counts = [int(r) for r in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - counts[i], reverse=True)[: total - sum(counts)]:
        counts[i] += 1
    return counts


def day_order(day: date, boost: dict[str, int]) -> list[str]:
    """The four groups for a day, lead first. Depends only on the date and the stock, not the month viewed."""
    ranked = sorted(GROUP_LABELS, key=lambda g: (-boost.get(g, 0), list(GROUP_LABELS).index(g)))
    pos = day.toordinal() % 4
    # The second, third and fourth follow on from the lead, so the second changes daily too.
    return ranked[pos:] + ranked[:pos]


def _stock_candidates(brand_id: str) -> list[dict[str, Any]]:
    from _lib import stock_pulse  # noqa: PLC0415

    try:
        return stock_pulse.candidates_for(brand_id)
    except Exception:
        return []


def day_leads(brand_id: str, first: date, last: date, total: int) -> dict[str, Any]:
    """Per day: the four groups with their share of the target, and what to push for the lead."""
    stock = _stock_candidates(brand_id)
    push: dict[str, list[str]] = {g: [] for g in GROUP_LABELS}
    for c in stock:
        names = push[group_of(str(c.get("category") or ""))]
        if c.get("name") and c["name"] not in names and len(names) < _PUSH_MAX:
            names.append(c["name"])
    push["services"] = list(SERVICES)
    boost = {g: sum(1 for c in stock if group_of(str(c.get("category") or "")) == g) for g in GROUP_LABELS}
    counts = split_counts(total)
    out: dict[str, Any] = {}
    d = first
    while d <= last:
        order = day_order(d, boost)
        out[d.isoformat()] = {
            "order": [{"group": g, "label": GROUP_LABELS[g], "count": n} for g, n in zip(order, counts)],
            "push": push[order[0]],
        }
        d += timedelta(days=1)
    return out


def target_for(brand_id: str) -> dict[str, int] | None:
    if brand_id not in TARGET_BRANDS:
        return None
    try:
        entry = json.loads(_BRANDS_FILE.read_text(encoding="utf-8"))["brands"][brand_id]
        custom = entry.get("daily_target")
    except (OSError, ValueError, KeyError, TypeError):
        custom = None
    if isinstance(custom, dict) and custom:
        return {k: int(v) for k, v in custom.items() if k in SLOT_LABELS}
    return dict(DEFAULT_SPLIT)


def slots_of(entry: dict[str, Any]) -> list[str]:
    """The slots one calendar entry fills."""
    if entry.get("kind") in ("idea", "task") or entry.get("view") in ("ideas", "todo"):
        return []
    fmt = str(entry.get("format") or "feed")
    out: list[str] = []
    for ch in entry.get("channels") or []:
        ch = str(ch).lower()
        if ch == "tiktok":
            slot = "tiktok"
        elif ch in ("gbp", "google", "gmb"):
            slot = "google"
        elif ch in ("instagram", "facebook"):
            prefix = "ig" if ch == "instagram" else "fb"
            slot = "reel" if fmt == "reel" else f"{prefix}_{'story' if fmt == 'story' else 'feed'}"
        else:
            continue
        if slot not in out:
            out.append(slot)
    return out


def day_progress(entries: list[dict[str, Any]], split: dict[str, int], first: date, last: date,
                 shares: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Per day from first to last: target, made, waiting, and each slot.

    `shares` are story reshares (story_queue.shares): each is one made placement in its story slot, shown
    separately as "reshared" so the count can be told apart from what was scheduled.
    """
    days: dict[str, dict[str, dict[str, int]]] = {}
    for e in entries:
        day = str(e.get("date") or "")[:10]
        for slot in slots_of(e):
            c = days.setdefault(day, {}).setdefault(slot, {"done": 0, "waiting": 0})
            if e.get("view") == "scheduled" and not e.get("making"):
                c["done"] += 1
            else:
                c["waiting"] += 1
    for sh in shares or []:
        c = days.setdefault(str(sh.get("date") or "")[:10], {}).setdefault(str(sh.get("slot")), {"done": 0, "waiting": 0})
        c["done"] += 1
        c["reshared"] = c.get("reshared", 0) + 1
    out: dict[str, Any] = {}
    d = first
    while d <= last:
        counts = days.get(d.isoformat(), {})
        slots, done, ready, reshared = [], 0, 0, 0
        for slot, target in split.items():
            c = counts.get(slot, {"done": 0, "waiting": 0})
            c = {"reshared": 0, **c}
            reshared += c["reshared"]
            slots.append({"slot": slot, "label": SLOT_LABELS[slot], "target": target, **c})
            # A slot's extra posts never count towards another slot's gap.
            done += min(c["done"], target)
            ready += min(c["done"] + c["waiting"], target)
        out[d.isoformat()] = {"target": sum(split.values()), "done": done, "waiting": ready - done,
                              "reshared": reshared, "slots": slots}
        d += timedelta(days=1)
    return out
