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


def day_progress(entries: list[dict[str, Any]], split: dict[str, int], first: date, last: date) -> dict[str, Any]:
    """Per day from first to last: target, made, waiting, and each slot."""
    days: dict[str, dict[str, dict[str, int]]] = {}
    for e in entries:
        day = str(e.get("date") or "")[:10]
        for slot in slots_of(e):
            c = days.setdefault(day, {}).setdefault(slot, {"done": 0, "waiting": 0})
            if e.get("view") == "scheduled" and not e.get("making"):
                c["done"] += 1
            else:
                c["waiting"] += 1
    out: dict[str, Any] = {}
    d = first
    while d <= last:
        counts = days.get(d.isoformat(), {})
        slots, done, ready = [], 0, 0
        for slot, target in split.items():
            c = counts.get(slot, {"done": 0, "waiting": 0})
            slots.append({"slot": slot, "label": SLOT_LABELS[slot], "target": target, **c})
            # A slot's extra posts never count towards another slot's gap.
            done += min(c["done"], target)
            ready += min(c["done"] + c["waiting"], target)
        out[d.isoformat()] = {"target": sum(split.values()), "done": done, "waiting": ready - done, "slots": slots}
        d += timedelta(days=1)
    return out
