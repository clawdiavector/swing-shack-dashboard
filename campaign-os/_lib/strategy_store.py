"""
strategy_store.py — Brand Strategy layer for Campaign OS.

Built 2026-08-24 per Christelle's request:
  "I want the OS to think bigger. Marketing and advertising should feel
  like two separate workhorses, each doing a different job but feeding
  the same strategy."

This module owns the Strategy layer — the big-picture view that sits
ABOVE the calendar. It's organised as:

  1. north_star         — the single sentence the brand is moving toward
  2. market_moves       — 3-5 strategic plays over a year (the "Ogilvy" view)
  3. bets               — quarter/month-horizon bets that execute the moves
                           (each links to a campaign in campaign-data.json)
  4. lessons            — strategic memory: worked / underperformed /
                           disproved / retry-with-different-approach /
                           data-suggests-test-next — every claim cited

The strategy file lives at:
    data/strategy/<brand_id>.json

It is a STATEFUL document. Lessons persist across weeks. They are not
regenerated each render — they accumulate. A lesson that was true last
quarter and is still validated by this week's data stays; one that the
data has disproved gets marked `still_valid: false`.

This is the data-led marketing OS layer Christelle asked for: strategy
visible, decisions have context, you can see not only what we're doing
but WHY we're doing it.
"""

from __future__ import annotations

import json
import os
import uuid
import datetime
from pathlib import Path
from typing import Any, Optional

# Repo-relative resolution
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]  # campaign-os/_lib/ -> campaign-os/ -> repo root
_DATA_DIR = _REPO_ROOT / "data"
_STRATEGY_DIR = _DATA_DIR / "strategy"

# Allow override for Railway persistent volume mount
_DATA_DIR_RUNTIME = Path(os.environ.get("DATA_DIR", str(_DATA_DIR)))
_STRATEGY_DIR_RUNTIME = _DATA_DIR_RUNTIME / "strategy"

_STRATEGY_DIR.mkdir(parents=True, exist_ok=True)
_STRATEGY_DIR_RUNTIME.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _strategy_path(brand_id: str) -> Path:
    """Resolve the strategy file path. Prefer runtime (Railway volume) over repo."""
    runtime = _STRATEGY_DIR_RUNTIME / f"{brand_id}.json"
    if runtime.exists():
        return runtime
    bundled = _STRATEGY_DIR / f"{brand_id}.json"
    if bundled.exists():
        return bundled
    # Default to runtime for new files
    return runtime


def _empty_strategy(brand_id: str) -> dict:
    """Scaffold for a brand without a strategy yet."""
    return {
        "brand_id": brand_id,
        "north_star": "",
        "north_star_metric": "",
        "positioning": "",
        "market_moves": [],
        "bets": [],
        "lessons": [],
        "updated_at": _now_iso(),
    }


def load_strategy(brand_id: str = "swing-shack") -> dict:
    """Read the strategy document for a brand. Returns empty scaffold if missing."""
    path = _strategy_path(brand_id)
    if not path.exists():
        return _empty_strategy(brand_id)
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return _empty_strategy(brand_id)


def save_strategy(strategy: dict, brand_id: str = None) -> str:
    """Persist the strategy document. Returns the saved path."""
    bid = brand_id or strategy.get("brand_id", "swing-shack")
    strategy["brand_id"] = bid
    strategy["updated_at"] = _now_iso()
    path = _STRATEGY_DIR_RUNTIME / f"{bid}.json"
    with open(path, "w") as f:
        json.dump(strategy, f, indent=2, default=str)
    return str(path)


# ─── Mutations ───────────────────────────────────────────────────────

def upsert_north_star(brand_id: str, north_star: str, north_star_metric: str = "", positioning: str = "") -> dict:
    s = load_strategy(brand_id)
    s["north_star"] = north_star
    if north_star_metric:
        s["north_star_metric"] = north_star_metric
    if positioning:
        s["positioning"] = positioning
    save_strategy(s, brand_id)
    return s


def upsert_market_move(brand_id: str, move: dict) -> dict:
    """market_moves are the year-horizon strategic plays."""
    s = load_strategy(brand_id)
    move.setdefault("id", str(uuid.uuid4())[:8])
    move.setdefault("horizon", "year")
    move.setdefault("status", "planned")
    move.setdefault("evidence_for", [])
    move.setdefault("evidence_against", [])
    move.setdefault("campaign_ids", [])
    move["updated_at"] = _now_iso()

    # Upsert by id
    existing = next((i for i, m in enumerate(s["market_moves"]) if m.get("id") == move["id"]), None)
    if existing is not None:
        s["market_moves"][existing] = move
    else:
        s["market_moves"].append(move)
    save_strategy(s, brand_id)
    return s


def upsert_bet(brand_id: str, bet: dict) -> dict:
    """bets are quarter/month-horizon bets that execute market_moves."""
    s = load_strategy(brand_id)
    bet.setdefault("id", str(uuid.uuid4())[:8])
    bet.setdefault("horizon", "quarter")
    bet.setdefault("status", "planned")
    bet.setdefault("evidence", [])
    bet["updated_at"] = _now_iso()

    existing = next((i for i, b in enumerate(s["bets"]) if b.get("id") == bet["id"]), None)
    if existing is not None:
        s["bets"][existing] = bet
    else:
        s["bets"].append(bet)
    save_strategy(s, brand_id)
    return s


def upsert_lesson(brand_id: str, lesson: dict) -> dict:
    """lessons are strategic memory. Categories: worked, underperformed,
    disproved, retry_with_different_approach, data_suggests_test_next."""
    valid = {"worked", "underperformed", "disproved", "retry_with_different_approach", "data_suggests_test_next"}
    if lesson.get("category") not in valid:
        raise ValueError(f"lesson.category must be one of {valid}")
    s = load_strategy(brand_id)
    lesson.setdefault("id", str(uuid.uuid4())[:8])
    lesson.setdefault("still_valid", True)
    lesson.setdefault("evidence", [])
    if "learned_at" not in lesson:
        lesson["learned_at"] = _now_iso()[:10]

    existing = next((i for i, l in enumerate(s["lessons"]) if l.get("id") == lesson["id"]), None)
    if existing is not None:
        s["lessons"][existing] = lesson
    else:
        s["lessons"].append(lesson)
    save_strategy(s, brand_id)
    return s


def mark_lesson_invalid(brand_id: str, lesson_id: str) -> dict:
    """A lesson that the data has disproved. Keep it visible but mark invalid."""
    s = load_strategy(brand_id)
    for l in s.get("lessons", []):
        if l.get("id") == lesson_id:
            l["still_valid"] = False
            l["invalidated_at"] = _now_iso()[:10]
            break
    save_strategy(s, brand_id)
    return s


def delete_strategy_record(brand_id: str, record_type: str, record_id: str) -> dict:
    """Generic delete for market_move, bet, or lesson by id."""
    s = load_strategy(brand_id)
    key = {"market_move": "market_moves", "bet": "bets", "lesson": "lessons"}.get(record_type)
    if not key:
        raise ValueError(f"record_type must be market_move|bet|lesson, got {record_type}")
    s[key] = [r for r in s.get(key, []) if r.get("id") != record_id]
    save_strategy(s, brand_id)
    return s


# ─── View helpers ────────────────────────────────────────────────────

def get_market_moves_by_horizon(brand_id: str, horizon: str) -> list:
    s = load_strategy(brand_id)
    return [m for m in s.get("market_moves", []) if m.get("horizon") == horizon]


def get_active_bets(brand_id: str) -> list:
    s = load_strategy(brand_id)
    return [b for b in s.get("bets", []) if b.get("status") in ("planned", "in_flight")]


def get_lessons_by_category(brand_id: str, category: str = None) -> list:
    s = load_strategy(brand_id)
    lessons = s.get("lessons", [])
    if category:
        lessons = [l for l in lessons if l.get("category") == category]
    # Sort: invalid last
    return sorted(lessons, key=lambda l: (l.get("still_valid", True) is False, -(l.get("learned_at", "") or "")))


def link_bet_to_market_move(brand_id: str, bet_id: str, market_move_id: str) -> dict:
    """Connect a bet to the market move it executes."""
    s = load_strategy(brand_id)
    for b in s.get("bets", []):
        if b.get("id") == bet_id:
            b["links_to_market_move"] = market_move_id
            b["updated_at"] = _now_iso()
            break
    # Also link back on the market_move side
    for m in s.get("market_moves", []):
        if m.get("id") == market_move_id:
            if bet_id not in m.get("campaign_ids", []):
                m.setdefault("campaign_ids", []).append(bet_id)
            m["updated_at"] = _now_iso()
            break
    save_strategy(s, brand_id)
    return s


def seed_from_campaign_data(brand_id: str) -> dict:
    """Auto-scaffold initial market_moves + bets from existing campaign-data.json.
    Called once on first strategy page load so the board isn't empty."""
    s = load_strategy(brand_id)
    if s.get("bets") or s.get("market_moves"):
        return s  # already populated

    # Read campaign-data.json
    cd_path = _DATA_DIR / "campaign-data.json"
    if not cd_path.exists():
        cd_path = _DATA_DIR_RUNTIME / "campaign-data.json"
    if not cd_path.exists():
        return s

    try:
        cd = json.load(open(cd_path))
    except Exception:
        return s

    campaigns = cd.get("campaigns", {}) if isinstance(cd, dict) else {}
    if not campaigns:
        return s

    # Group active campaigns into one default market move
    move_id = str(uuid.uuid4())[:8]
    default_move = {
        "id": move_id,
        "title": "Active campaign portfolio",
        "thesis": "Auto-seeded from existing campaign-data.json. Edit to add real strategic thinking.",
        "horizon": "year",
        "start_date": datetime.date.today().isoformat(),
        "target_end_date": (datetime.date.today() + datetime.timedelta(days=365)).isoformat(),
        "status": "active",
        "owner": "christelle",
        "evidence_for": [],
        "evidence_against": [],
        "campaign_ids": [],
    }
    s["market_moves"].append(default_move)

    for cid, c in list(campaigns.items())[:8]:  # cap at 8 bets
        identity = c.get("identity", {}) or {}
        bet = {
            "id": str(uuid.uuid4())[:8],
            "campaign_id": cid,
            "title": identity.get("name", cid),
            "hypothesis": identity.get("goal", ""),
            "horizon": "quarter",
            "start_date": (identity.get("createdAt") or datetime.date.today().isoformat())[:10],
            "target_end_date": (datetime.date.today() + datetime.timedelta(days=90)).isoformat(),
            "primary_kpi": identity.get("primaryGoal", "Bookings"),
            "success_threshold": "",
            "status": "in_flight" if identity.get("status") == "active" else "planned",
            "evidence": [],
            "learned": "",
            "owner": identity.get("owner", "christelle"),
            "links_to_market_move": move_id,
        }
        s["bets"].append(bet)
        default_move["campaign_ids"].append(bet["id"])

    save_strategy(s, brand_id)
    return s
