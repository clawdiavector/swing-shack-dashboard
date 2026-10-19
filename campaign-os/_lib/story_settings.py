"""Per-brand settings for the daily Stories set and the month-grid stock lines.

Stored as data/brand-directory/<brand>/story-settings.json in the data root (not
in git, so a change made on the Stories page is kept on this server). Missing
file or bad values fall back to the defaults, so the page always has something
to show.

  daily_on        {brand id: true/false} for brands listed under "daily" in
                  story-brands.json (Psycho Bunny for Stick). Default on.
  stock_stories   how many stock stories a day (0 to 3). Default 1.
  stock_every_days  one stock line on the month grid every N days (1 to 7). Default 2.

Service, retail and golf-moment slots stay at one each a day.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

DEFAULTS: Dict[str, Any] = {"daily_on": {}, "stock_stories": 1, "stock_every_days": 2}
STOCK_STORIES_RANGE = (0, 3)
STOCK_EVERY_RANGE = (1, 7)


def _path(brand_id: str) -> Path:
    from _lib.marketing_lanes import _data_root
    return _data_root() / "brand-directory" / brand_id / "story-settings.json"


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def clean(raw: Any, daily_ids: list[str]) -> Dict[str, Any]:
    """Only known keys, clamped to range. daily_on keeps only brands that are daily."""
    raw = raw if isinstance(raw, dict) else {}
    daily_raw = raw.get("daily_on") if isinstance(raw.get("daily_on"), dict) else {}
    return {
        "daily_on": {i: bool(daily_raw.get(i, True)) for i in daily_ids},
        "stock_stories": _clamp(raw.get("stock_stories"), *STOCK_STORIES_RANGE, DEFAULTS["stock_stories"]),
        "stock_every_days": _clamp(raw.get("stock_every_days"), *STOCK_EVERY_RANGE, DEFAULTS["stock_every_days"]),
    }


def read(brand_id: str, daily_ids: list[str]) -> Dict[str, Any]:
    try:
        raw = json.loads(_path(brand_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    return clean(raw, daily_ids)


def write(brand_id: str, changes: Dict[str, Any], daily_ids: list[str]) -> Dict[str, Any]:
    """Merge the changes in, clamp, save, and return what is now stored."""
    current = read(brand_id, daily_ids)
    merged = {
        "daily_on": {**current["daily_on"], **{k: bool(v) for k, v in (changes.get("daily_on") or {}).items()
                                               if k in daily_ids}},
        "stock_stories": changes.get("stock_stories", current["stock_stories"]),
        "stock_every_days": changes.get("stock_every_days", current["stock_every_days"]),
    }
    cleaned = clean(merged, daily_ids)
    p = _path(brand_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    tmp.replace(p)
    return cleaned
