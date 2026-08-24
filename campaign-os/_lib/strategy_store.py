"""
strategy_store.py — Brand Strategy layer for Campaign OS.

This is the big-picture view above the marketing calendar. Built for
Christelle's vision (2026-08-24):

  "I want to open a company profile and understand what we believe,
   what we're betting on, what the data is telling us, what changed
   our minds, and what we're doing next."

Design pillars:
  1. Two workhorses — marketing vs advertising — share strategy but
     run on different swimlanes. They are NOT the same thing.
  2. Every bet has visible reasoning: hypothesis, evidence for,
     evidence against, what would prove it, what would kill it,
     next action. No silent ideas.
  3. Lessons feed forward — a worked lesson can be promoted to a bet;
     a disproved one retires. The OS remembers.
  4. The trend over time is the interesting bit. Weekly snapshots
     record evidence-as-of for each move, so a thesis can be seen
     strengthening, flat, weakening, or disproved.

Schema lives at:
    data/strategy/<brand_id>.json

A second file holds the time series:
    data/strategy/<brand_id>_trend.json
"""

from __future__ import annotations

import json
import os
import uuid
import datetime
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
_DATA_DIR = _REPO_ROOT / "data"
_STRATEGY_DIR = _DATA_DIR / "strategy"

_DATA_DIR_RUNTIME = Path(os.environ.get("DATA_DIR", str(_DATA_DIR)))
_STRATEGY_DIR_RUNTIME = _DATA_DIR_RUNTIME / "strategy"

_STRATEGY_DIR.mkdir(parents=True, exist_ok=True)
_STRATEGY_DIR_RUNTIME.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _today() -> str:
    return datetime.date.today().isoformat()


def _strategy_path(brand_id: str, kind: str = "main") -> Path:
    """kind: 'main' = strategy doc, 'trend' = trend snapshots."""
    base = _STRATEGY_DIR_RUNTIME
    bundled = _STRATEGY_DIR
    suffix = "" if kind == "main" else "_trend"
    filename = f"{brand_id}{suffix}.json"
    runtime_path = base / filename
    if runtime_path.exists():
        return runtime_path
    bundled_path = bundled / filename
    if bundled_path.exists():
        return bundled_path
    return runtime_path


# Workhorse types — what lane a record belongs to.
# Both lanes share strategy and evidence; they don't share KPIs or tactics.
WORKHORSE_TYPES = {"marketing", "advertising"}

# Evidence categories (shared across both workhorses)
EVIDENCE_CATEGORIES = {
    "worked": "Real data shows this is working",
    "underperformed": "Real data shows this is underperforming the threshold",
    "disproved": "Real data disproves the underlying assumption",
    "retry_with_different_approach": "Worth trying again with a different angle",
    "data_suggests_test_next": "The data points to something we haven't tested",
}

# Trend signals — the four states a thesis can be in
TREND_STATES = {"strengthening", "flat", "weakening", "disproved"}


def _empty_strategy(brand_id: str) -> dict:
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
    path = _strategy_path(brand_id)
    if not path.exists():
        return _empty_strategy(brand_id)
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return _empty_strategy(brand_id)


def save_strategy(strategy: dict, brand_id: str = None) -> str:
    bid = brand_id or strategy.get("brand_id", "swing-shack")
    strategy["brand_id"] = bid
    strategy["updated_at"] = _now_iso()
    path = _STRATEGY_DIR_RUNTIME / f"{bid}.json"
    with open(path, "w") as f:
        json.dump(strategy, f, indent=2, default=str)
    return str(path)


def load_trend(brand_id: str = "swing-shack") -> dict:
    """Weekly trend snapshots — what the evidence said at that point."""
    path = _strategy_path(brand_id, "trend")
    if not path.exists():
        return {"brand_id": brand_id, "snapshots": []}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"brand_id": brand_id, "snapshots": []}


def save_trend(trend: dict, brand_id: str = None) -> str:
    bid = brand_id or trend.get("brand_id", "swing-shack")
    trend["brand_id"] = bid
    path = _STRATEGY_DIR_RUNTIME / f"{bid}_trend.json"
    with open(path, "w") as f:
        json.dump(trend, f, indent=2, default=str)
    return str(path)


# ─── Snapshotting ─────────────────────────────────────────────────────

def snapshot_evidence(brand_id: str = "swing-shack", snapshot_date: str = None) -> dict:
    """Take a snapshot of evidence_for / evidence_against counts per move/bet.
    Called weekly by cron or manually via 'snapshot now' button."""
    snapshot_date = snapshot_date or _today()
    s = load_strategy(brand_id)
    trend = load_trend(brand_id)

    snap = {
        "date": snapshot_date,
        "iso_week": datetime.datetime.fromisoformat(snapshot_date).isocalendar()[:2],
        "moves": {},
        "bets": {},
        "aggregate": {
            "evidence_for_total": sum(len(m.get("evidence_for", [])) for m in s.get("market_moves", [])),
            "evidence_against_total": sum(len(m.get("evidence_against", [])) for m in s.get("market_moves", [])),
            "lessons_total": len(s.get("lessons", [])),
            "lessons_invalid": sum(1 for l in s.get("lessons", []) if not l.get("still_valid", True)),
        }
    }

    for m in s.get("market_moves", []):
        snap["moves"][m["id"]] = {
            "evidence_for": len(m.get("evidence_for", [])),
            "evidence_against": len(m.get("evidence_against", [])),
            "title": m.get("title", ""),
            "status": m.get("status", ""),
        }

    for b in s.get("bets", []):
        snap["bets"][b["id"]] = {
            "evidence_for": len(b.get("evidence", [])),
            "title": b.get("title", ""),
            "status": b.get("status", ""),
        }

    trend.setdefault("snapshots", []).append(snap)
    # Keep last 52 weeks
    trend["snapshots"] = trend["snapshots"][-52:]
    save_trend(trend, brand_id)
    return trend


def compute_trend_signal(brand_id: str = "swing-shack", record_id: str = None, record_type: str = "move") -> dict:
    """Look at the trend snapshots and return the current state.
    For each move/bet: compare last 4 weeks of evidence_for vs evidence_against.
    """
    trend = load_trend(brand_id)
    snapshots = trend.get("snapshots", [])
    if len(snapshots) < 2:
        return {"signal": "flat", "history": [], "reason": "Not enough history (need 2+ weekly snapshots)."}

    key = "moves" if record_type == "move" else "bets"
    history = []
    for snap in snapshots[-12:]:
        if record_id in snap.get(key, {}):
            history.append({
                "date": snap["date"],
                "evidence_for": snap[key][record_id].get("evidence_for", 0),
                "evidence_against": snap[key][record_id].get("evidence_against", 0),
            })

    if len(history) < 2:
        return {"signal": "flat", "history": history, "reason": "Need 2+ snapshots for this record."}

    # Compare net signal over recent history
    # Take last 4 vs prior 4 (if available)
    recent = history[-4:] if len(history) >= 4 else history
    earlier = history[:-4] if len(history) > 4 else []

    recent_net = sum(h.get("evidence_for", 0) - h.get("evidence_against", 0) for h in recent)
    earlier_net = sum(h.get("evidence_for", 0) - h.get("evidence_against", 0) for h in earlier) if earlier else recent_net

    delta = recent_net - earlier_net
    current_net = recent[-1].get("evidence_for", 0) - recent[-1].get("evidence_against", 0)

    if current_net <= -3 or (delta < -2 and earlier_net > 0):
        signal = "disproved"
        reason = f"Evidence net dropped to {current_net}; thesis is failing the data test."
    elif delta >= 2:
        signal = "strengthening"
        reason = f"Evidence net grew +{delta} over recent weeks."
    elif delta <= -2:
        signal = "weakening"
        reason = f"Evidence net dropped {delta} over recent weeks."
    else:
        signal = "flat"
        reason = f"Evidence net holding steady at {current_net}."

    return {
        "signal": signal,
        "reason": reason,
        "history": history,
        "recent_net": recent_net,
        "earlier_net": earlier_net,
        "delta": delta,
        "current_net": current_net,
    }


# ─── Upserts ──────────────────────────────────────────────────────────

def upsert_north_star(brand_id: str, north_star: str = None, north_star_metric: str = None, positioning: str = None) -> dict:
    s = load_strategy(brand_id)
    if north_star is not None:
        s["north_star"] = north_star
    if north_star_metric is not None:
        s["north_star_metric"] = north_star_metric
    if positioning is not None:
        s["positioning"] = positioning
    save_strategy(s, brand_id)
    return s


def upsert_market_move(brand_id: str, move: dict) -> dict:
    """market_moves are year-horizon strategic plays.
    workhorse: 'marketing' | 'advertising' — which lane owns this."""
    s = load_strategy(brand_id)
    move.setdefault("id", str(uuid.uuid4())[:8])
    move.setdefault("horizon", "year")
    move.setdefault("workhorse", "marketing")  # default
    move.setdefault("status", "planned")
    move.setdefault("evidence_for", [])
    move.setdefault("evidence_against", [])
    move.setdefault("campaign_ids", [])
    # New fields per the brief
    move.setdefault("hypothesis", "")
    move.setdefault("what_proves_it", "")
    move.setdefault("what_kills_it", "")
    move.setdefault("next_action", "")
    # Strategic calendar fields
    move.setdefault("review_date", "")  # when we re-examine the move
    move.setdefault("decision_date", "")  # when we must decide keep/change/kill
    move.setdefault("milestones", [])  # [{date, type, label}]
    move["updated_at"] = _now_iso()
    if move.get("workhorse") not in WORKHORSE_TYPES:
        move["workhorse"] = "marketing"

    existing = next((i for i, m in enumerate(s["market_moves"]) if m.get("id") == move["id"]), None)
    if existing is not None:
        s["market_moves"][existing] = move
    else:
        s["market_moves"].append(move)
    save_strategy(s, brand_id)
    return s


def upsert_bet(brand_id: str, bet: dict) -> dict:
    """bets are quarter/month-horizon executions of a market_move.
    workhorse: 'marketing' | 'advertising'."""
    s = load_strategy(brand_id)
    bet.setdefault("id", str(uuid.uuid4())[:8])
    bet.setdefault("horizon", "quarter")
    bet.setdefault("workhorse", "marketing")
    bet.setdefault("status", "planned")
    bet.setdefault("evidence", [])
    bet.setdefault("linked_lesson_ids", [])  # lessons that informed this bet
    bet.setdefault("calendar_post_ids", [])  # posts in calendar that serve this
    bet.setdefault("hypothesis", "")
    bet.setdefault("what_proves_it", "")
    bet.setdefault("what_kills_it", "")
    bet.setdefault("next_action", "")
    # Strategic calendar fields
    bet.setdefault("review_date", "")  # mid-bet check-in
    bet.setdefault("decision_date", "")  # when we must decide SCALE/REFINE/RETRY/KILL
    bet.setdefault("decision", None)  # {outcome, decided_at, note} — populated by decision endpoint
    bet.setdefault("milestones", [])  # [{date, type, label}]
    bet.setdefault("execution_log", [])  # [{date, planned, actual, note}] — plan vs actual
    bet.setdefault("content_themes", [])  # content themes planned for this bet
    bet.setdefault("experiments", [])  # [{name, start, end, status}] A/B tests within the bet
    bet.setdefault("watch_metrics", [])  # metrics watched weekly for this bet
    bet["updated_at"] = _now_iso()
    if bet.get("workhorse") not in WORKHORSE_TYPES:
        bet["workhorse"] = "marketing"

    existing = next((i for i, b in enumerate(s["bets"]) if b.get("id") == bet["id"]), None)
    if existing is not None:
        s["bets"][existing] = bet
    else:
        s["bets"].append(bet)
    save_strategy(s, brand_id)
    return s


def upsert_lesson(brand_id: str, lesson: dict) -> dict:
    if lesson.get("category") not in EVIDENCE_CATEGORIES:
        raise ValueError(f"lesson.category must be one of {list(EVIDENCE_CATEGORIES)}")
    s = load_strategy(brand_id)
    lesson.setdefault("id", str(uuid.uuid4())[:8])
    lesson.setdefault("still_valid", True)
    lesson.setdefault("evidence", [])
    lesson.setdefault("workhorse", "marketing")  # which lane produced this lesson
    lesson.setdefault("promoted_to_bet_id", None)  # if scaled, points to the new bet
    if "learned_at" not in lesson:
        lesson["learned_at"] = _today()

    existing = next((i for i, l in enumerate(s["lessons"]) if l.get("id") == lesson["id"]), None)
    if existing is not None:
        s["lessons"][existing] = lesson
    else:
        s["lessons"].append(lesson)
    save_strategy(s, brand_id)
    return s


def promote_lesson_to_bet(brand_id: str, lesson_id: str, bet_payload: dict) -> dict:
    """The lesson becomes a new bet. The new bet carries the lesson
    in linked_lesson_ids + adds the lesson's claim as initial evidence."""
    s = load_strategy(brand_id)
    lesson = next((l for l in s["lessons"] if l["id"] == lesson_id), None)
    if not lesson:
        raise ValueError(f"lesson {lesson_id} not found")

    # Default the new bet to the lesson's workhorse + category
    bet_payload.setdefault("workhorse", lesson.get("workhorse", "marketing"))
    bet_payload.setdefault("hypothesis", f"From lesson: {lesson['claim']}")
    bet_payload.setdefault("linked_lesson_ids", [lesson_id])
    if "evidence" not in bet_payload:
        bet_payload["evidence"] = list(lesson.get("evidence", []))

    new_bet = upsert_bet(brand_id, bet_payload)
    # Mark the lesson as promoted
    for l in s["lessons"]:
        if l["id"] == lesson_id:
            l["promoted_to_bet_id"] = new_bet["bets"][-1]["id"]
            break
    save_strategy(s, brand_id)
    return new_bet


def mark_lesson_invalid(brand_id: str, lesson_id: str) -> dict:
    s = load_strategy(brand_id)
    for l in s.get("lessons", []):
        if l.get("id") == lesson_id:
            l["still_valid"] = False
            l["invalidated_at"] = _today()
            break
    save_strategy(s, brand_id)
    return s


def retire_market_move(brand_id: str, move_id: str, reason: str = "") -> dict:
    """Retire (don't delete — keep for history) a market move."""
    s = load_strategy(brand_id)
    for m in s.get("market_moves", []):
        if m.get("id") == move_id:
            m["status"] = "retired"
            m["retired_at"] = _today()
            if reason:
                m["retired_reason"] = reason
            break
    save_strategy(s, brand_id)
    return s


def retire_bet(brand_id: str, bet_id: str, reason: str = "") -> dict:
    s = load_strategy(brand_id)
    for b in s.get("bets", []):
        if b.get("id") == bet_id:
            b["status"] = "retired"
            b["retired_at"] = _today()
            if reason:
                b["retired_reason"] = reason
            break
    save_strategy(s, brand_id)
    return s


def delete_strategy_record(brand_id: str, record_type: str, record_id: str) -> dict:
    s = load_strategy(brand_id)
    key = {"market_move": "market_moves", "bet": "bets", "lesson": "lessons"}.get(record_type)
    if not key:
        raise ValueError(f"record_type must be market_move|bet|lesson, got {record_type}")
    s[key] = [r for r in s.get(key, []) if r.get("id") != record_id]
    save_strategy(s, brand_id)
    return s


def link_bet_to_market_move(brand_id: str, bet_id: str, market_move_id: str) -> dict:
    s = load_strategy(brand_id)
    for b in s.get("bets", []):
        if b.get("id") == bet_id:
            b["links_to_market_move"] = market_move_id
            b["updated_at"] = _now_iso()
            break
    for m in s.get("market_moves", []):
        if m.get("id") == market_move_id:
            if bet_id not in m.get("campaign_ids", []):
                m.setdefault("campaign_ids", []).append(bet_id)
            m["updated_at"] = _now_iso()
            break
    save_strategy(s, brand_id)
    return s


def link_calendar_post_to_bet(brand_id: str, bet_id: str, post_id: str) -> dict:
    """Bidirectional: when a content piece is associated with a bet, link it.
    Called when scheduling posts through the calendar."""
    s = load_strategy(brand_id)
    for b in s.get("bets", []):
        if b.get("id") == bet_id:
            if post_id not in b.get("calendar_post_ids", []):
                b.setdefault("calendar_post_ids", []).append(post_id)
            b["updated_at"] = _now_iso()
            break
    save_strategy(s, brand_id)
    return s


# ─── Seeding ──────────────────────────────────────────────────────────


# ─── Strategic calendar helpers ───────────────────────────────────────

VALID_DECISIONS = {"scale", "refine", "retry_differently", "kill", "park"}
VALID_MILESTONE_TYPES = {"launch", "test_start", "test_end", "review", "decision", "peak", "seasonal", "product", "partnership"}


def log_decision(brand_id: str, bet_id: str, outcome: str, note: str = "") -> dict:
    """Record a SCALE/REFINE/RETRY/KILL decision on a bet.
    A 'kill' invalidates the bet (visible, not deleted).
    A 'scale' or 'refine' leaves the bet in flight but writes to strategic memory.
    A 'retry_differently' creates a new suggested bet tied to the old one."""
    if outcome not in VALID_DECISIONS:
        raise ValueError(f"outcome must be one of {VALID_DECISIONS}")
    s = load_strategy(brand_id)
    bet = next((b for b in s.get("bets", []) if b.get("id") == bet_id), None)
    if not bet:
        raise ValueError(f"bet {bet_id} not found")
    decision = {
        "outcome": outcome,
        "decided_at": _today(),
        "note": note,
    }
    bet["decision"] = decision
    bet["updated_at"] = _now_iso()
    if outcome == "kill":
        bet["status"] = "lost"
    elif outcome == "scale":
        bet["status"] = "won"
    elif outcome == "park":
        bet["status"] = "retired"

    # Always log a lesson from the decision — strategic memory
    lesson_category_map = {
        "scale": "worked",
        "refine": "data_suggests_test_next",
        "retry_differently": "retry_with_different_approach",
        "kill": "disproved",
        "park": "underperformed",
    }
    lesson = {
        "category": lesson_category_map[outcome],
        "claim": f"Bet '{bet['title']}' decision: {outcome}. {note}".strip(),
        "evidence": [{
            "source": "decision",
            "value": f"decision_date triggered outcome={outcome}; note={note[:120]}",
            "as_of": _today(),
        }],
        "from_bet": bet_id,
        "decision_outcome": outcome,
    }
    upsert_lesson(brand_id, lesson)
    return load_strategy(brand_id)


def append_execution_log(brand_id: str, bet_id: str, planned: str, actual: str, note: str = "") -> dict:
    """Record what actually shipped vs what was planned. Powers PLAN vs ACTUAL toggle."""
    s = load_strategy(brand_id)
    bet = next((b for b in s.get("bets", []) if b.get("id") == bet_id), None)
    if not bet:
        raise ValueError(f"bet {bet_id} not found")
    log_entry = {
        "date": _today(),
        "planned": planned,
        "actual": actual,
        "note": note,
        "delta": "matched" if actual == planned else ("partial" if actual and planned else "missed"),
    }
    bet.setdefault("execution_log", []).append(log_entry)
    bet["updated_at"] = _now_iso()
    save_strategy(s, brand_id)
    return s


def add_milestone(brand_id: str, record_type: str, record_id: str, date: str, type: str, label: str) -> dict:
    """Add a milestone marker (launch/test_start/test_end/review/decision/peak/seasonal/product/partnership)."""
    if type not in VALID_MILESTONE_TYPES:
        raise ValueError(f"type must be one of {VALID_MILESTONE_TYPES}")
    s = load_strategy(brand_id)
    key = "market_moves" if record_type == "move" else "bets"
    for r in s.get(key, []):
        if r.get("id") == record_id:
            r.setdefault("milestones", []).append({
                "date": date,
                "type": type,
                "label": label,
            })
            r["updated_at"] = _now_iso()
            break
    save_strategy(s, brand_id)
    return s


def compute_strategy_density(brand_id: str, year: int = None) -> dict:
    """Detect when too many major bets are running in the same month.
    Returns: {month: count, warnings: [...]} — warnings flag months with 3+ bets."""
    import datetime as _dt
    s = load_strategy(brand_id)
    year = year or _dt.date.today().year
    by_month = {m: [] for m in range(1, 13)}

    for b in s.get("bets", []):
        if b.get("status") not in ("in_flight", "planned"):
            continue
        start = b.get("start_date") or _today()
        end = b.get("target_end_date") or start
        try:
            start_d = _dt.date.fromisoformat(start[:10])
            end_d = _dt.date.fromisoformat(end[:10])
        except (ValueError, TypeError):
            continue
        # Span the months this bet is active in
        cur = start_d
        while cur <= end_d:
            if cur.year == year:
                by_month[cur.month].append({
                    "id": b["id"],
                    "title": b["title"],
                    "workhorse": b.get("workhorse", "marketing"),
                })
            # Move to next month
            if cur.month == 12:
                cur = _dt.date(cur.year + 1, 1, 1)
            else:
                cur = _dt.date(cur.year, cur.month + 1, 1)
            if cur > end_d:
                break

    month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    density = {month_names[m]: len(by_month[m]) for m in range(1, 13)}
    warnings = []
    for m in range(1, 13):
        bets_in_month = by_month[m]
        if len(bets_in_month) >= 3:
            # Check if there are bets from BOTH workhorses (a real density risk)
            workhorses = set(b["workhorse"] for b in bets_in_month)
            severity = "high" if len(bets_in_month) >= 5 else "medium"
            warnings.append({
                "month": month_names[m],
                "month_num": m,
                "count": len(bets_in_month),
                "severity": severity,
                "workhorses": list(workhorses),
                "bets": [{"title": b["title"], "workhorse": b["workhorse"]} for b in bets_in_month],
                "message": f"{len(bets_in_month)} major bets active in {month_names[m]} — are we spreading attention too thin?",
            })

    return {"year": year, "density_by_month": density, "warnings": warnings}


def get_decision_queue(brand_id: str, within_days: int = 30) -> list:
    """Return bets whose decision_date is approaching or past.
    Used by the OS to prompt Christelle when a decision is due."""
    import datetime as _dt
    s = load_strategy(brand_id)
    today = _dt.date.today()
    queue = []
    for b in s.get("bets", []):
        if b.get("status") not in ("in_flight", "planned"):
            continue
        dec = b.get("decision_date")
        if not dec:
            continue
        try:
            dec_d = _dt.date.fromisoformat(dec[:10])
        except (ValueError, TypeError):
            continue
        days_away = (dec_d - today).days
        if days_away <= within_days:
            queue.append({
                "bet_id": b["id"],
                "title": b["title"],
                "decision_date": dec,
                "days_away": days_away,
                "overdue": days_away < 0,
                "decision_already_recorded": b.get("decision") is not None,
                "primary_kpi": b.get("primary_kpi"),
                "evidence_count": len(b.get("evidence", [])),
            })
    return sorted(queue, key=lambda x: x["days_away"])


def compute_plan_vs_actual(brand_id: str) -> dict:
    """Compare planned vs actual across all bets."""
    s = load_strategy(brand_id)
    out = {"bets": [], "totals": {"planned": 0, "actual": 0, "matched": 0, "partial": 0, "missed": 0}}
    for b in s.get("bets", []):
        log = b.get("execution_log", [])
        bet_summary = {
            "bet_id": b["id"],
            "title": b["title"],
            "planned_count": 0,
            "actual_count": 0,
            "entries": log,
        }
        for entry in log:
            if entry.get("planned"): bet_summary["planned_count"] += 1
            if entry.get("actual"): bet_summary["actual_count"] += 1
            for cat in ["matched", "partial", "missed"]:
                if entry.get("delta") == cat:
                    out["totals"][cat] += 1
        out["bets"].append(bet_summary)
    return out


def get_calendar_view(brand_id: str, view: str = "year", year: int = None, quarter: int = None, month: int = None) -> dict:
    """Return a calendar-structured view of all moves + bets + milestones + density warnings."""
    import datetime as _dt
    s = load_strategy(brand_id)
    today = _dt.date.today()
    year = year or today.year
    density = compute_strategy_density(brand_id, year)

    # Build timeline records
    timeline = {"moves": [], "bets": [], "milestones": []}

    for m in s.get("market_moves", []):
        timeline["moves"].append({
            "id": m["id"],
            "title": m["title"],
            "workhorse": m.get("workhorse", "marketing"),
            "status": m.get("status"),
            "start_date": m.get("start_date"),
            "target_end_date": m.get("target_end_date"),
            "review_date": m.get("review_date"),
            "decision_date": m.get("decision_date"),
            "milestones": m.get("milestones", []),
        })

    for b in s.get("bets", []):
        timeline["bets"].append({
            "id": b["id"],
            "title": b["title"],
            "workhorse": b.get("workhorse", "marketing"),
            "status": b.get("status"),
            "horizon": b.get("horizon", "quarter"),
            "links_to_market_move": b.get("links_to_market_move"),
            "start_date": b.get("start_date"),
            "target_end_date": b.get("target_end_date"),
            "review_date": b.get("review_date"),
            "decision_date": b.get("decision_date"),
            "decision": b.get("decision"),
            "milestones": b.get("milestones", []),
            "execution_log": b.get("execution_log", []),
            "content_themes": b.get("content_themes", []),
            "experiments": b.get("experiments", []),
            "watch_metrics": b.get("watch_metrics", []),
            "campaign_id": b.get("campaign_id"),
            "primary_kpi": b.get("primary_kpi"),
            "success_threshold": b.get("success_threshold"),
        })

    # Filter by view
    if view == "year":
        pass  # everything
    elif view == "quarter" and quarter:
        # Filter moves/bets that touch this quarter
        q_start_month = (quarter - 1) * 3 + 1
        q_end_month = quarter * 3
        timeline["moves"] = _filter_by_quarter(timeline["moves"], year, q_start_month, q_end_month)
        timeline["bets"] = _filter_by_quarter(timeline["bets"], year, q_start_month, q_end_month)
    elif view == "month" and month:
        timeline["moves"] = _filter_by_month(timeline["moves"], year, month)
        timeline["bets"] = _filter_by_month(timeline["bets"], year, month)
    elif view == "week":
        # Return current week's relevant items (last 7 days)
        week_ago = today - _dt.timedelta(days=7)
        timeline["bets"] = [b for b in timeline["bets"] if _in_window(b, week_ago, today + _dt.timedelta(days=7))]

    return {
        "view": view,
        "year": year,
        "quarter": quarter,
        "month": month,
        "today": today.isoformat(),
        "timeline": timeline,
        "density": density,
        "decision_queue": get_decision_queue(brand_id, within_days=30),
    }


def _filter_by_quarter(records, year, q_start, q_end):
    import datetime as _dt
    out = []
    for r in records:
        s = r.get("start_date")
        e = r.get("target_end_date")
        if not s and not e:
            continue
        try:
            sd = _dt.date.fromisoformat((s or e)[:10])
            ed = _dt.date.fromisoformat((e or s)[:10])
        except (ValueError, TypeError):
            continue
        # Quarter spans year/Q_start/Q_end — does the record overlap?
        qsd = _dt.date(year, q_start, 1)
        qed = _dt.date(year, q_end, 28)
        if sd <= qed and ed >= qsd:
            out.append(r)
    return out


def _filter_by_month(records, year, month):
    import datetime as _dt
    out = []
    msd = _dt.date(year, month, 1)
    if month == 12:
        med = _dt.date(year + 1, 1, 1) - _dt.timedelta(days=1)
    else:
        med = _dt.date(year, month + 1, 1) - _dt.timedelta(days=1)
    for r in records:
        s = r.get("start_date")
        e = r.get("target_end_date")
        if not s and not e:
            continue
        try:
            sd = _dt.date.fromisoformat((s or e)[:10])
            ed = _dt.date.fromisoformat((e or s)[:10])
        except (ValueError, TypeError):
            continue
        if sd <= med and ed >= msd:
            out.append(r)
    return out


def _in_window(record, start, end):
    import datetime as _dt
    s = record.get("start_date")
    e = record.get("target_end_date")
    if not s and not e:
        return False
    try:
        sd = _dt.date.fromisoformat((s or e)[:10])
        ed = _dt.date.fromisoformat((e or s)[:10])
    except (ValueError, TypeError):
        return False
    return sd <= end and ed >= start


def seed_swing_shack_default(brand_id: str = "swing-shack", force: bool = False) -> dict:
    """First-run seed for swing-shack using the brief's example thesis."""
    s = load_strategy(brand_id)
    if s.get("market_moves") and not force:
        return s  # don't overwrite existing
    if force:
        # Wipe + reseed
        s = _empty_strategy(brand_id)

    s["north_star"] = "Make measurable golf improvement obvious and accessible in JHB."
    s["north_star_metric"] = "20 fitting bookings/month + 40% MoM IG engagement on coaching content."
    s["positioning"] = (
        "Indoor golf simulator + TrackMan fitting studio for serious JHB golfers who want "
        "measurable improvement, not range theory. We are the data-backed alternative to "
        "trial-and-error coaching."
    )

    # The year-horizon market move — the thesis Christelle wrote
    move_id = "mship-001"
    move = {
        "id": move_id,
        "title": "Own the serious golfer who wants measurable improvement",
        "thesis": (
            "Swing Shack should become the place golfers associate with data-backed improvement — "
            "fitting, TrackMan, coaching and equipment decisions based on evidence rather than "
            "guesswork."
        ),
        "horizon": "year",
        "workhorse": "marketing",
        "status": "active",
        "owner": "christelle",
        "start_date": "2026-08-01",
        "target_end_date": "2027-07-31",
        "hypothesis": (
            "If we consistently publish content where TrackMan numbers, fitting data, and "
            "before/after improvement are the heroes, then serious golfers will start to "
            "default to Swing Shack when they want to get measurably better."
        ),
        "what_proves_it": (
            "MoM growth in fitting bookings attributed to inbound IG/FB; organic search "
            "rankings for 'TrackMan fitting JHB' climbing; coaching content engagement "
            "rates exceeding industry baseline by 2x."
        ),
        "what_kills_it": (
            "If after 6 months of data-led content, fitting bookings are still flat or "
            "declining — the audience isn't actually shopping on data, we're optimising "
            "for the wrong persona."
        ),
        "next_action": (
            "Reposition next 4 TrackMan / coaching reels around before/after numbers, not "
            "lifestyle."
        ),
        "evidence_for": [
            {"source": "ga4-metrics.json", "value": "/bookings/ has 211 sessions last 28d — demand exists", "as_of": "2026-08-21"},
            {"source": "ig-analytics.json", "value": "coaching topic_cluster averages 3.2% engagement over 7 posts", "as_of": "2026-08-21"},
        ],
        "evidence_against": [
            {"source": "weekly-report", "value": "0 pieces of content shipped in last 7d — execution cadence gap", "as_of": "2026-08-21"},
        ],
        "campaign_ids": [],
    }
    s["market_moves"].append(move)

    # The bets — quarter-horizon executions of the move
    bets = [
        {
            "id": "bet-trackman",
            "links_to_market_move": move_id,
            "campaign_id": "trackman-intelligence",
            "title": "TrackMan authority content",
            "hypothesis": (
                "If we publish 4 TrackMan-data reels/month (ball flight, club speed, "
                "carry distance), then fitting bookings will rise because golfers will "
                "see Swing Shack as the only place to get this data."
            ),
            "horizon": "quarter",
            "workhorse": "marketing",
            "status": "in_flight",
            "primary_kpi": "Fitting bookings attributed to IG/FB",
            "success_threshold": "5+ bookings/month from IG/FB inbound",
            "what_proves_it": "5+ bookings attributed to TrackMan reels in next 30 days",
            "what_kills_it": "<2 bookings attributed after 4 reels shipped",
            "next_action": "Schedule first TrackMan reel: 2026-08-26",
            "owner": "christelle",
            "start_date": "2026-08-01",
            "target_end_date": "2026-10-31",
            "review_date": "2026-09-15",
            "decision_date": "2026-10-31",
            "milestones": [
                {"date": "2026-08-26", "type": "launch", "label": "First TrackMan reel"},
                {"date": "2026-09-15", "type": "review", "label": "Mid-bet review: 4 reels shipped?"},
                {"date": "2026-10-31", "type": "decision", "label": "SCALE/REFINE/RETRY/KILL?"},
            ],
            "content_themes": ["ball flight data", "club speed", "carry distance", "fitting outcome"],
            "experiments": [
                {"name": "Reel caption: data-first vs benefit-first", "start": "2026-08-26", "end": "2026-09-09", "status": "planned"},
            ],
            "watch_metrics": ["TrackMan reel reach", "Fitting bookings", "IG/FB inbound DMs"],
            "evidence": [],
            "calendar_post_ids": [],
            "linked_lesson_ids": [],
        },
        {
            "id": "bet-takomo",
            "links_to_market_move": move_id,
            "campaign_id": "takomo-101t",
            "title": "Takomo 101T custom-fit launch",
            "hypothesis": (
                "If we run a Takomo custom-fit launch that shows the before/after "
                "performance numbers (carry distance, dispersion), then serious "
                "budget-conscious golfers will book fittings."
            ),
            "horizon": "quarter",
            "workhorse": "marketing",
            "status": "in_flight",
            "primary_kpi": "Takomo fitting bookings",
            "success_threshold": "3 bookings in launch month",
            "what_proves_it": "3+ Takomo fittings booked in first 30 days post-launch",
            "what_kills_it": "0 bookings in 30 days → Takomo not the right launch vehicle",
            "next_action": "Confirm launch date with Takomo + draft first reel",
            "owner": "christelle",
            "start_date": "2026-09-01",
            "target_end_date": "2026-11-30",
            "review_date": "2026-10-15",
            "decision_date": "2026-11-30",
            "milestones": [
                {"date": "2026-09-15", "type": "product", "label": "Takomo 101T stock arrives"},
                {"date": "2026-09-20", "type": "launch", "label": "Public launch — first reel + GBP post"},
                {"date": "2026-10-15", "type": "review", "label": "30-day launch review"},
                {"date": "2026-11-30", "type": "decision", "label": "SCALE to other Takomo models or KILL?"},
            ],
            "content_themes": ["Takomo 101T specs", "before/after fitting", "carry distance gain", "dispersion tightening"],
            "experiments": [],
            "watch_metrics": ["Takomo bookings", "GBP calls", "IG saves on launch post"],
            "evidence": [],
            "calendar_post_ids": [],
            "linked_lesson_ids": [],
        },
        {
            "id": "bet-fitting-cta",
            "links_to_market_move": move_id,
            "campaign_id": "use-the-right-equipment-mq5l90bk",
            "title": "Booking-page retargeting on IG",
            "hypothesis": (
                "If we put a clear booking CTA on every IG post this month, we can "
                "convert the 211 warm /bookings/ sessions into actual bookings "
                "(currently no IG content pushes the booking page)."
            ),
            "horizon": "month",
            "workhorse": "advertising",
            "status": "in_flight",
            "primary_kpi": "Bookings from IG",
            "success_threshold": "5+ bookings attributed to IG in 30 days",
            "what_proves_it": "GA4 shows click-through from IG/FB to /bookings/ rising",
            "what_kills_it": "Bookings stay flat despite CTA on every post",
            "next_action": "Add 'Book a session' CTA to next 4 posts",
            "owner": "christelle",
            "start_date": "2026-08-24",
            "target_end_date": "2026-09-23",
            "review_date": "2026-09-09",
            "decision_date": "2026-09-23",
            "milestones": [
                {"date": "2026-08-26", "type": "test_start", "label": "CTA test begins — 4 posts"},
                {"date": "2026-09-09", "type": "review", "label": "Mid-test: clicks rising?"},
                {"date": "2026-09-23", "type": "decision", "label": "SCALE/REFINE/RETRY/KILL?"},
            ],
            "content_themes": ["club fitting CTA", "booking reminder", "session availability"],
            "experiments": [
                {"name": "CTA wording: 'Book now' vs 'Reserve your slot' vs 'See available times'", "start": "2026-08-26", "end": "2026-09-23", "status": "planned"},
            ],
            "watch_metrics": ["Booking-page sessions", "Social link clicks", "Booking CTA clicks", "Completed bookings"],
            "evidence": [
                {"source": "ga4-metrics.json", "value": "/bookings/ has 211 sessions but no IG retargeting", "as_of": "2026-08-21"},
            ],
            "calendar_post_ids": [],
            "linked_lesson_ids": [],
        },
        {
            "id": "bet-coaching-reels",
            "links_to_market_move": move_id,
            "campaign_id": "winter-golf",
            "title": "Coaching content — winter cadence",
            "hypothesis": (
                "Coaching topic_cluster already averages 3.2% engagement — if we ship "
                "3 reels/week through winter we can hit the 40% MoM engagement target "
                "and grow booking intent."
            ),
            "horizon": "quarter",
            "workhorse": "marketing",
            "status": "in_flight",
            "primary_kpi": "Coaching content engagement rate",
            "success_threshold": "≥4% engagement on coaching topic_cluster posts",
            "what_proves_it": "12 coaching reels shipped with median engagement ≥4%",
            "what_kills_it": "Engagement drops below 2.5% after 12 posts → coaching content not the lever",
            "next_action": "Lock 12-reel coaching schedule for Sept–Nov",
            "owner": "christelle",
            "start_date": "2026-08-24",
            "target_end_date": "2026-11-30",
            "review_date": "2026-10-01",
            "decision_date": "2026-11-30",
            "milestones": [
                {"date": "2026-09-01", "type": "launch", "label": "Coaching content calendar goes live"},
                {"date": "2026-10-01", "type": "review", "label": "6 reels in — engagement holding?"},
                {"date": "2026-11-30", "type": "decision", "label": "Continue / reduce / kill coaching cadence?"},
            ],
            "content_themes": ["swing fixes", "TrackMan coaching", "winter golf tips", "before/after improvement"],
            "experiments": [
                {"name": "Cadence: 3/week vs 2/week vs 1/week", "start": "2026-09-01", "end": "2026-10-11", "status": "planned"},
            ],
            "watch_metrics": ["Coaching reel engagement rate", "Coaching reel reach", "Profile visits", "Coaching bookings"],
            "evidence": [
                {"source": "ig-analytics.json", "value": "coaching topic_cluster averages 3.2% engagement over 7 posts", "as_of": "2026-08-21"},
            ],
            "calendar_post_ids": [],
            "linked_lesson_ids": [],
        },
    ]

    for b in bets:
        s["bets"].append(b)
        move["campaign_ids"].append(b["id"])

    save_strategy(s, brand_id)
    return s


def seed_from_campaign_data(brand_id: str) -> dict:
    """Auto-scaffold initial market_moves + bets from existing campaign-data.json.
    Only used if seed_swing_shack_default hasn't been called yet."""
    s = load_strategy(brand_id)
    if s.get("bets") or s.get("market_moves"):
        return s

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

    move_id = str(uuid.uuid4())[:8]
    default_move = {
        "id": move_id,
        "title": "Active campaign portfolio",
        "thesis": "Auto-seeded from existing campaign-data.json. Edit to add real strategic thinking.",
        "horizon": "year",
        "workhorse": "marketing",
        "status": "active",
        "owner": "christelle",
        "evidence_for": [],
        "evidence_against": [],
        "campaign_ids": [],
        "hypothesis": "",
        "what_proves_it": "",
        "what_kills_it": "",
        "next_action": "",
    }
    s["market_moves"].append(default_move)

    for cid, c in list(campaigns.items())[:8]:
        identity = c.get("identity", {}) or {}
        bet = {
            "id": str(uuid.uuid4())[:8],
            "campaign_id": cid,
            "links_to_market_move": move_id,
            "title": identity.get("name", cid),
            "hypothesis": identity.get("goal", ""),
            "horizon": "quarter",
            "workhorse": "marketing",
            "status": "in_flight" if identity.get("status") == "active" else "planned",
            "primary_kpi": identity.get("primaryGoal", "Bookings"),
            "success_threshold": "",
            "what_proves_it": "",
            "what_kills_it": "",
            "next_action": "",
            "evidence": [],
            "calendar_post_ids": [],
            "linked_lesson_ids": [],
            "owner": identity.get("owner", "christelle"),
            "start_date": (identity.get("createdAt") or _today())[:10],
            "target_end_date": (datetime.date.today() + datetime.timedelta(days=90)).isoformat(),
        }
        s["bets"].append(bet)
        default_move["campaign_ids"].append(bet["id"])

    save_strategy(s, brand_id)
    return s


def get_market_moves_by_horizon(brand_id: str, horizon: str, workhorse: str = None) -> list:
    s = load_strategy(brand_id)
    out = [m for m in s.get("market_moves", []) if m.get("horizon") == horizon]
    if workhorse:
        out = [m for m in out if m.get("workhorse") == workhorse]
    return out


def get_bets_by_horizon(brand_id: str, horizon: str, workhorse: str = None) -> list:
    s = load_strategy(brand_id)
    out = [b for b in s.get("bets", []) if b.get("horizon") == horizon]
    if workhorse:
        out = [b for b in out if b.get("workhorse") == workhorse]
    return out


def get_active_bets(brand_id: str) -> list:
    s = load_strategy(brand_id)
    return [b for b in s.get("bets", []) if b.get("status") in ("planned", "in_flight")]


def get_lessons_by_category(brand_id: str, category: str = None) -> list:
    s = load_strategy(brand_id)
    lessons = s.get("lessons", [])
    if category:
        lessons = [l for l in lessons if l.get("category") == category]
    return sorted(lessons, key=lambda l: (l.get("still_valid", True) is False, -(l.get("learned_at", "") or "")))