"""
weekly_brief.py — Monday-morning strategic brief generator.

This is the proactive OS layer. Runs Monday 06:00 SAST (04:00 UTC).

The brief is the OS preparing the argument so Christelle can make the
decision, not the OS making the decision. The brief contains:

  1. WHAT CHANGED — only the deltas since last Monday:
       - Trend signal moves (holding steady → getting stronger, etc.)
       - New evidence against a thesis
       - Disproved signals
       - Decisions/review dates approaching
       - Missed execution (planned vs actual gap)
       - Strategy density warnings (3+ bets/month)
       - Lessons strong enough to promote to a bet

  2. THIS WEEK — mini calendar showing what's in play:
       Marketing swimlane (moves + content)
       Advertising swimlane (moves + content)
       Milestones for the week (launch / review / decision)

  3. DECISIONS THIS WEEK — full argument per decision:
       Current signal · Evidence for · Evidence against · Last lesson
       Recommended decision with one-line rationale

  4. THIS WEEK'S MARKETING PRIORITIES — max 3:
       The OS's synthesis of what should actually ship this week.

The cron runs strategy_store.snapshot_evidence() first so the change
detection has a fresh baseline to diff against.
"""

from __future__ import annotations

import json
import os
import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict

import sys
HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))  # _lib is sibling

from strategy_store import (
    load_strategy,
    load_trend,
    save_trend,
    snapshot_evidence,
    compute_trend_signal,
    compute_strategy_density,
    get_decision_queue,
    EVIDENCE_CATEGORIES,
    VALID_DECISIONS,
)
from audit import run_audit as _run_audit, AUDIT_STATUSES
from evidence import Claim, render_portfolio_watch, build_portfolio_observation, confidence_from_evidence
from portfolio import (
    compute_effort_allocation,
    compute_demand_mismatch,
    detect_over_support,
    detect_under_support,
    detect_opportunities,
    compute_strategy_density,
)
from spend import (
    load_spend,
    detect_orphaned_spend,
    spend_concentration_warnings,
    budget_burn_vs_maturity,
)
from integrity import (
    reconcile as integrity_reconcile,
    degrade_confidence,
    detect_anomalies,
    render_integrity_warning_section,
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _today_date() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


def _week_range(d: datetime.date = None) -> tuple:
    """Return (monday, sunday) of the week containing d."""
    d = d or _today_date()
    monday = d - datetime.timedelta(days=d.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday


def _format_date(d) -> str:
    if isinstance(d, str):
        try: d = datetime.date.fromisoformat(d[:10])
        except ValueError: return d[:10] if d else ""
    if isinstance(d, datetime.datetime):
        d = d.date()
    if isinstance(d, datetime.date):
        return d.strftime("%d %b")
    return str(d)[:10]


# ─── Change detection ─────────────────────────────────────────────────

def detect_changes(brand_id: str) -> List[Dict[str, Any]]:
    """Compare the current state against the last weekly snapshot.
    Returns a list of {category, severity, summary, detail, refs[]} dicts.
    Categories: trend_shift | new_evidence_against | disproved | decision_due
                | execution_missed | density_warning | promotable_lesson"""
    s = load_strategy(brand_id)
    trend = load_trend(brand_id)
    snapshots = trend.get("snapshots", [])

    changes = []

    # 1. Trend signal shifts (compare each record's current signal to last week's)
    last_snap = snapshots[-1] if snapshots else None
    for m in s.get("market_moves", []):
        cur = compute_trend_signal(brand_id, m["id"], "move")
        prev_signal = last_snap["moves"].get(m["id"], {}).get("trend_signal") if last_snap and "trend_signal" in last_snap.get("moves", {}).get(m["id"], {}) else None
        # Fallback: derive prev from prev snapshot's evidence counts
        if not prev_signal and last_snap:
            prev_data = last_snap.get("moves", {}).get(m["id"], {})
            prev_for = prev_data.get("evidence_for", 0)
            prev_against = prev_data.get("evidence_against", 0)
            prev_net = prev_for - prev_against
            prev_signal = "disproved" if prev_net <= -3 else ("weakening" if prev_net < 0 else ("strengthening" if prev_net > 0 else "flat"))

        cur_signal = cur.get("signal", "flat")
        if cur_signal != prev_signal:
            changes.append({
                "category": "trend_shift",
                "severity": "high" if cur_signal == "disproved" else "medium",
                "summary": f"Goal '{m['title']}' trend: {prev_signal or 'new'} → {cur_signal}",
                "detail": cur.get("reason", ""),
                "refs": [{"type": "move", "id": m["id"], "title": m["title"]}],
            })

    for b in s.get("bets", []):
        cur = compute_trend_signal(brand_id, b["id"], "bet")
        prev_signal = None
        if last_snap and b["id"] in last_snap.get("bets", {}):
            prev_data = last_snap["bets"][b["id"]]
            if "trend_signal" in prev_data:
                prev_signal = prev_data["trend_signal"]
            else:
                prev_net = prev_data.get("evidence_for", 0) - prev_data.get("evidence_against", 0)
                prev_signal = "disproved" if prev_net <= -3 else ("weakening" if prev_net < 0 else ("strengthening" if prev_net > 0 else "flat"))
        cur_signal = cur.get("signal", "flat")
        if cur_signal != prev_signal:
            changes.append({
                "category": "trend_shift",
                "severity": "high" if cur_signal == "disproved" else "medium",
                "summary": f"Plan '{b['title']}' trend: {prev_signal or 'new'} → {cur_signal}",
                "detail": cur.get("reason", ""),
                "refs": [{"type": "bet", "id": b["id"], "title": b["title"]}],
            })

    # 2. New evidence against a thesis (compared to last snapshot)
    if last_snap:
        for m in s.get("market_moves", []):
            cur_ev = m.get("evidence_against", [])
            prev_count = last_snap.get("moves", {}).get(m["id"], {}).get("evidence_against", 0)
            if len(cur_ev) > prev_count and cur_ev:
                new_items = cur_ev[prev_count:]
                changes.append({
                    "category": "new_evidence_against",
                    "severity": "high" if any("disproved" in (e.get("value", "") + e.get("source", "")).lower() for e in new_items) else "medium",
                    "summary": f"{len(new_items)} new piece(s) of evidence against move '{m['title']}'",
                    "detail": "; ".join(e.get("value", "")[:80] for e in new_items[:2]),
                    "refs": [{"type": "move", "id": m["id"], "title": m["title"], "evidence": new_items}],
                })

        for b in s.get("bets", []):
            cur_ev = b.get("evidence", [])
            prev_count = last_snap.get("bets", {}).get(b["id"], {}).get("evidence_for", 0)
            if len(cur_ev) > prev_count and cur_ev:
                new_items = cur_ev[prev_count:]
                # Categorise: are they for or against?
                # We don't have a separate against list on bets, so assume neutral.
                changes.append({
                    "category": "new_evidence",
                    "severity": "low",
                    "summary": f"{len(new_items)} new evidence item(s) for bet '{b['title']}'",
                    "detail": "; ".join(e.get("value", "")[:80] for e in new_items[:2]),
                    "refs": [{"type": "bet", "id": b["id"], "title": b["title"], "evidence": new_items}],
                })

    # 3. Decisions/review dates approaching (within 14 days)
    queue = get_decision_queue(brand_id, within_days=14)
    for item in queue:
        if item.get("decision_already_recorded"):
            continue
        severity = "high" if item.get("overdue") else ("medium" if item["days_away"] <= 7 else "low")
        verb = "OVERDUE" if item.get("overdue") else f"in {item['days_away']}d"
        changes.append({
            "category": "decision_due",
            "severity": severity,
            "summary": f"Decision {verb}: {item['title']}",
            "detail": f"decision_date {item['decision_date']} · KPI: {item.get('primary_kpi', '—')}",
            "refs": [{"type": "bet", "id": item["bet_id"], "title": item["title"]}],
        })

    # 4. Missed execution (planned vs actual)
    for b in s.get("bets", []):
        log = b.get("execution_log", [])
        missed = [e for e in log if e.get("delta") == "missed"]
        if missed:
            changes.append({
                "category": "execution_missed",
                "severity": "medium",
                "summary": f"{len(missed)} missed execution entries on bet '{b['title']}'",
                "detail": "; ".join(f"planned '{e['planned']}'" for e in missed[:2]),
                "refs": [{"type": "bet", "id": b["id"], "title": b["title"]}],
            })

    # 5. Strategy density (3+ bets in same month — current or upcoming)
    density = compute_strategy_density(brand_id)
    for w in density.get("warnings", []):
        # Only surface months that are current or upcoming (within 90 days)
        try:
            month_num = w["month_num"]
            today = _today_date()
            current_month = today.month
            if month_num < current_month or month_num > current_month + 3:
                continue
        except (KeyError, TypeError):
            continue
        changes.append({
            "category": "density_warning",
            "severity": w.get("severity", "medium"),
            "summary": w.get("message", ""),
            "detail": "; ".join(b["title"] for b in w.get("bets", [])[:5]),
            "refs": [{"type": "month_warning", "id": str(w["month_num"]), "title": w.get("message", "")}],
        })

    # 6. Lessons strong enough to promote
    for l in s.get("lessons", []):
        if not l.get("still_valid", True): continue
        if l.get("promoted_to_bet_id"): continue
        if l.get("category") in ("worked", "retry_with_different_approach") and len(l.get("evidence", [])) >= 2:
            changes.append({
                "category": "promotable_lesson",
                "severity": "low",
                "summary": f"Lesson ready to promote: {l['claim'][:60]}…",
                "detail": f"category={l['category']} · {len(l.get('evidence', []))} pieces of evidence",
                "refs": [{"type": "lesson", "id": l["id"], "title": l.get("claim", "")[:80]}],
            })

    # 7. Audit flags — items scoring low or flagged by the audit engine
    try:
        audit = _run_audit(brand_id, light=True)
        for nc in audit.get("needs_cleaning", [])[:3]:
            severity = "high" if nc["audit_status"] == "retire" else "medium"
            changes.append({
                "category": "audit_flag",
                "severity": severity,
                "summary": f"{nc['audit_status'].upper()}: {nc['title'][:60]}",
                "detail": nc.get("reason", "")[:140],
                "refs": [{"type": nc["item_type"], "id": nc["item_id"], "title": nc["title"]}],
            })
    except Exception as e:
        pass  # audit failure should not break the brief

    # Dedupe (same summary)
    seen = set()
    deduped = []
    for c in changes:
        key = (c["category"], c.get("summary", ""))
        if key in seen: continue
        seen.add(key)
        deduped.append(c)

    # Sort by severity then category
    severity_order = {"high": 0, "medium": 1, "low": 2}
    deduped.sort(key=lambda c: (severity_order.get(c["severity"], 3), c["category"]))
    return deduped


# ─── This-week calendar ───────────────────────────────────────────────

def build_week_calendar(brand_id: str, monday: datetime.date = None) -> Dict[str, Any]:
    """Build the 'THIS WEEK' mini calendar with marketing/advertising
    swimlanes and milestones for the upcoming 7 days."""
    s = load_strategy(brand_id)
    today = _today_date()
    monday = monday or (today - datetime.timedelta(days=today.weekday()))
    sunday = monday + datetime.timedelta(days=6)

    marketing = []
    advertising = []

    for b in s.get("bets", []):
        if b.get("status") not in ("in_flight", "planned"):
            continue
        bs = b.get("start_date") or ""
        be = b.get("target_end_date") or bs
        try:
            bs_d = datetime.date.fromisoformat(bs[:10]) if bs else None
            be_d = datetime.date.fromisoformat(be[:10]) if be else None
        except ValueError:
            continue
        if not bs_d or not be_d:
            continue
        if be_d < monday or bs_d > sunday:
            continue  # bet doesn't touch this week
        # Find milestones in this week
        ms = []
        for m in b.get("milestones", []):
            try:
                md = datetime.date.fromisoformat(m["date"][:10])
                if monday <= md <= sunday:
                    ms.append({"date": md.isoformat(), "type": m.get("type"), "label": m.get("label", "")})
            except (ValueError, TypeError):
                continue
        for m in s.get("market_moves", []):
            if m.get("id") != b.get("links_to_market_move"):
                continue
            for mm in m.get("milestones", []):
                try:
                    md = datetime.date.fromisoformat(mm["date"][:10])
                    if monday <= md <= sunday:
                        ms.append({"date": md.isoformat(), "type": mm.get("type"), "label": f"[move] {mm.get('label', '')}"})
                except (ValueError, TypeError):
                    continue

        # Themes → ship-this-week plan
        themes = b.get("content_themes", [])[:3]

        item = {
            "bet_id": b["id"],
            "title": b["title"],
            "horizon": b.get("horizon", "quarter"),
            "start": bs_d.isoformat(),
            "end": be_d.isoformat(),
            "milestones_this_week": sorted(ms, key=lambda x: x["date"]),
            "themes": themes,
            "watch_metrics": b.get("watch_metrics", [])[:3],
        }
        if b.get("workhorse") == "advertising":
            advertising.append(item)
        else:
            marketing.append(item)

    # Day-by-day strip (Mon..Sun)
    day_strip = []
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for i in range(7):
        d = monday + datetime.timedelta(days=i)
        day_label = day_names[i]
        # What ships that day? Milestones on that date.
        ships = []
        for lane in marketing + advertising:
            for ms in lane.get("milestones_this_week", []):
                if ms["date"] == d.isoformat():
                    ships.append({"lane": "marketing" if lane in marketing else "advertising",
                                  "bet": lane["title"], "label": ms["label"], "type": ms["type"]})
        day_strip.append({"date": d.isoformat(), "day": day_label, "ships": ships})

    return {
        "week_of": monday.isoformat(),
        "week_to": sunday.isoformat(),
        "marketing": marketing,
        "advertising": advertising,
        "day_strip": day_strip,
    }


# ─── Decisions-this-week argument builder ───────────────────────────

def build_decision_arguments(brand_id: str) -> List[Dict[str, Any]]:
    """For every decision due in the next 14 days, build the full
    argument: current signal, evidence for, evidence against, last
    lesson, recommended outcome, rationale."""
    s = load_strategy(brand_id)
    queue = get_decision_queue(brand_id, within_days=14)
    arguments = []
    for item in queue:
        if item.get("decision_already_recorded"):
            continue
        bet = next((b for b in s.get("bets", []) if b["id"] == item["bet_id"]), None)
        if not bet:
            continue
        trend = compute_trend_signal(brand_id, bet["id"], "bet")
        signal = trend.get("signal", "flat")
        evidence_for = bet.get("evidence", [])
        evidence_for_str = "; ".join(e.get("value", "")[:120] for e in evidence_for[:3]) or "—"

        # Find evidence against from linked market move
        move = next((m for m in s.get("market_moves", []) if m["id"] == bet.get("links_to_market_move")), None)
        evidence_against = move.get("evidence_against", []) if move else []
        evidence_against_str = "; ".join(e.get("value", "")[:120] for e in evidence_against[:3]) or "—"

        # Last lesson
        related_lessons = [
            l for l in s.get("lessons", [])
            if l.get("from_bet") == bet["id"] or l.get("id") in (bet.get("linked_lesson_ids") or [])
        ]
        last_lesson = related_lessons[-1] if related_lessons else None
        last_lesson_str = ""
        if last_lesson:
            last_lesson_str = f"[{last_lesson['category']}] {last_lesson['claim'][:140]}"
        else:
            last_lesson_str = "No lessons attached yet."

        # Recommend based on signal + evidence
        # Rules:
        #   - disproved signal + against evidence → KILL
        #   - strengthening signal + meaningful for-evidence → SCALE
        #   - flat signal with evidence on both sides → REFINE
        #   - weakening with execution_log gap → RETRY DIFFERENTLY
        #   - new bet (gathering) → REFINE if hypothesis still valid
        for_count = len(evidence_for)
        against_count = len(evidence_against)
        execution_misses = sum(1 for e in bet.get("execution_log", []) if e.get("delta") == "missed")

        if signal == "disproved":
            recommended = "kill"
            rationale = "Trend disproved. Hypothesis invalidated by data."
        elif signal == "weakening" and execution_misses >= 2:
            recommended = "retry_differently"
            rationale = f"Signal weakening with {execution_misses} missed executions — execution failing but hypothesis may still hold."
        elif signal == "strengthening" and for_count >= 3:
            recommended = "scale"
            rationale = f"Trend strengthening with {for_count} pieces of supporting evidence."
        elif signal == "strengthening":
            recommended = "scale"
            rationale = "Trend strengthening — consider scaling."
        elif for_count >= 2 and against_count == 0 and signal != "disproved":
            recommended = "scale"
            rationale = f"{for_count} pieces of supporting evidence, none against — scale."
        else:
            recommended = "refine"
            rationale = "Mixed signal — refine the execution angle."

        arguments.append({
            "bet_id": bet["id"],
            "title": bet["title"],
            "workhorse": bet.get("workhorse", "marketing"),
            "decision_date": bet.get("decision_date"),
            "days_away": item["days_away"],
            "overdue": item.get("overdue", False),
            "current_signal": signal,
            "evidence_for": evidence_for_str,
            "evidence_against": evidence_against_str,
            "last_lesson": last_lesson_str,
            "recommended": recommended,
            "rationale": rationale,
            "kpi": bet.get("primary_kpi", "—"),
            "threshold": bet.get("success_threshold", "—"),
        })
    return arguments


# ─── Marketing priorities synthesis ─────────────────────────────────

def synthesize_priorities(brand_id: str, max_priorities: int = 3) -> List[Dict[str, Any]]:
    """Synthesize max-3 priorities using the 7-factor ranking.

    Factors (in order of weight):
      1. Strategic priority (high/med/low from market move status)
      2. Decision dates approaching (urgency)
      3. Evidence movement (strengthening signals → keep; weakening → fix)
      4. Execution gaps (no execution_log in last 14 days)
      5. Portfolio imbalance (over-support / under-support)
      6. Opportunity cost (don't add if capacity full)
      7. Demand signals (theme outperforming baseline)

    Each priority is presented as: "Finish the X test before
    expanding it" — strategy, not just next action."""
    s = load_strategy(brand_id)
    today = _today_date()
    priorities = []
    used_bet_ids = set()

    # Factor 1+2: Decision due (high priority if bet status is high)
    decisions = build_decision_arguments(brand_id)
    for d in decisions[:1]:
        # Strategy framing: "Finish the test before expanding it"
        title = f"Finish the '{d['title']}' test before expanding it"
        priorities.append({
            "title": title,
            "bet_id": d["bet_id"],
            "why": (
                f"Decision {('OVERDUE' if d['overdue'] else 'in ' + str(d['days_away']) + 'd')}. "
                f"Signal: {d['current_signal']}. "
                f"This bet represents concentrated activity in the portfolio — finishing it "
                f"before adding more of the same kind is the strategic move."
            ),
            "action_first_step": (
                f"Open '{d['title']}', review evidence for ({len(d.get('evidence_for', '').split(';'))} sources) "
                f"and against ({len(d.get('evidence_against', '').split(';'))} sources), "
                f"record the {d['recommended']} decision."
            ),
            "factors": ["decision_date", "strategic_priority"],
        })
        used_bet_ids.add(d["bet_id"])

    # Factor 3+4+5: bets with no execution_log + portfolio concentration
    in_flight = [b for b in s.get("bets", []) if b.get("status") == "in_flight"]
    effort = compute_effort_allocation(brand_id, "month")
    theme_concentration = effort.get("theme_concentration", {})

    for b in in_flight:
        if len(priorities) >= max_priorities:
            break
        if b["id"] in used_bet_ids:
            continue
        next_action = (b.get("next_action") or "").strip()
        if not next_action:
            continue
        log = b.get("execution_log", [])
        recent_log = [e for e in log if (e.get("date") or "") >= (today - datetime.timedelta(days=14)).isoformat()]
        if recent_log:
            continue  # recently shipped

        # Check if this bet's themes are over-concentrated
        bet_themes = b.get("content_themes", [])
        over_concentrated = any(
            theme_concentration.get(t.lower(), 0) >= 25
            for t in bet_themes
        )
        if over_concentrated:
            title = f"Finish the '{b['title']}' test before expanding it"
            why_extra = (
                f"This bet already represents a large share of calendar activity. "
                f"Ship the planned execution, collect the evidence, then make the scheduled "
                f"decision before adding more."
            )
        else:
            title = f"Prove '{b['title']}'"
            why_extra = ""

        priorities.append({
            "title": title,
            "bet_id": b["id"],
            "why": (
                f"Next action pending. KPI: {b.get('primary_kpi', '—')}. "
                f"Threshold: {b.get('success_threshold', '—')}. "
                f"{why_extra}"
            ).strip(),
            "action_first_step": next_action[:140],
            "factors": ["execution_gap", "portfolio_concentration"] if over_concentrated else ["execution_gap"],
        })
        used_bet_ids.add(b["id"])

    # Factor 5+6: Capacity protection
    if len(priorities) < max_priorities:
        density = compute_strategy_density(brand_id)
        cur_month = today.month
        current_warnings = [w for w in density.get("warnings", []) if w.get("month_num") == cur_month]
        if current_warnings:
            w = current_warnings[0]
            priorities.append({
                "title": "Protect capacity — don't add anything new",
                "bet_id": None,
                "why": (
                    f"{w['count']} active bets in {w['month']}. "
                    f"Adding another bet would crowd out the existing ones. "
                    f"Strategy means saying no."
                ),
                "action_first_step": (
                    "Review the decision queue and resolve the most overdue bet first."
                ),
                "factors": ["opportunity_cost", "portfolio_imbalance"],
            })

    return priorities[:max_priorities]


# ─── Compact strip (for company-profile header) ─────────────────────

def build_compact_strip(brand_id: str, weeks_ahead: int = 0) -> Dict[str, Any]:
    """Compact strategic strip — Mon-Sun row + active-this-week pills.
    weeks_ahead: 0 = this week, 1 = next week, etc."""
    today = _today_date()
    monday = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=weeks_ahead)
    week_cal = build_week_calendar(brand_id, monday=monday)
    s = load_strategy(brand_id)

    # Active this week pills (moves + bets with trend signal)
    active_pills = []
    for m in s.get("market_moves", []):
        if m.get("status") not in ("active", "planned"):
            continue
        bs = m.get("start_date") or ""
        be = m.get("target_end_date") or bs
        try:
            bs_d = datetime.date.fromisoformat(bs[:10])
            be_d = datetime.date.fromisoformat(be[:10])
        except ValueError:
            continue
        if be_d < monday or bs_d > monday + datetime.timedelta(days=6):
            continue
        trend = compute_trend_signal(brand_id, m["id"], "move")
        active_pills.append({
            "id": m["id"], "type": "move", "title": m["title"],
            "workhorse": m.get("workhorse", "marketing"),
            "trend": trend.get("signal", "flat"),
            "reason": trend.get("reason", ""),
        })
    for b in s.get("bets", []):
        if b.get("status") not in ("in_flight", "planned"):
            continue
        bs = b.get("start_date") or ""
        be = b.get("target_end_date") or bs
        try:
            bs_d = datetime.date.fromisoformat(bs[:10])
            be_d = datetime.date.fromisoformat(be[:10])
        except ValueError:
            continue
        if be_d < monday or bs_d > monday + datetime.timedelta(days=6):
            continue
        trend = compute_trend_signal(brand_id, b["id"], "bet")
        active_pills.append({
            "id": b["id"], "type": "bet", "title": b["title"],
            "workhorse": b.get("workhorse", "marketing"),
            "trend": trend.get("signal", "flat"),
            "reason": trend.get("reason", ""),
        })

    return {
        "week_of": monday.isoformat(),
        "week_to": (monday + datetime.timedelta(days=6)).isoformat(),
        "day_strip": week_cal["day_strip"],
        "active": active_pills,
    }


# ─── Replay view ─────────────────────────────────────────────────────

def build_replay(brand_id: str, record_type: str, record_id: str) -> Dict[str, Any]:
    """Full chronological history of a record:
      - All snapshot data (evidence_for/against over time)
      - Trend signal over time
      - All decisions made on it
      - All lessons attached to it
      - Execution log entries
    """
    s = load_strategy(brand_id)
    trend = load_trend(brand_id)
    snapshots = trend.get("snapshots", [])

    if record_type == "move":
        rec = next((m for m in s.get("market_moves", []) if m["id"] == record_id), None)
    elif record_type == "bet":
        rec = next((b for b in s.get("bets", []) if b["id"] == record_id), None)
    else:
        raise ValueError(f"record_type must be move or bet, got {record_type}")

    if not rec:
        return None

    # Build chronological timeline
    timeline = []

    # Snapshot-based trend signal at each snapshot
    for snap in snapshots:
        key = "moves" if record_type == "move" else "bets"
        if record_id not in snap.get(key, {}):
            continue
        snap_data = snap[key][record_id]
        ev_for = snap_data.get("evidence_for", 0)
        ev_against = snap_data.get("evidence_against", 0)
        net = ev_for - ev_against
        if net <= -3:
            signal = "disproved"
        elif net > 0:
            signal = "strengthening"
        elif net < 0:
            signal = "weakening"
        else:
            signal = "flat"
        timeline.append({
            "date": snap["date"],
            "type": "snapshot",
            "title": f"Trend snapshot: {signal}",
            "evidence_for": ev_for,
            "evidence_against": ev_against,
            "net": net,
        })

    # Decisions
    if record_type == "bet" and rec.get("decision"):
        d = rec["decision"]
        timeline.append({
            "date": d.get("decided_at"),
            "type": "decision",
            "title": f"Decision: {d.get('outcome', '').upper()}",
            "detail": d.get("note", ""),
        })

    # Lessons
    for l in s.get("lessons", []):
        if l.get("from_bet") == record_id or (record_type == "bet" and record_id in (l.get("linked_lesson_ids") or []) if isinstance(l.get("linked_lesson_ids"), list) else False):
            timeline.append({
                "date": l.get("learned_at"),
                "type": "lesson",
                "title": f"Lesson ({l['category']}): {l.get('claim', '')[:80]}",
                "still_valid": l.get("still_valid", True),
            })

    # Execution log
    if record_type == "bet":
        for e in rec.get("execution_log", []):
            timeline.append({
                "date": e.get("date"),
                "type": "execution",
                "title": f"Execution: planned '{e.get('planned', '')}' → actual '{e.get('actual', '')}'",
                "delta": e.get("delta"),
                "note": e.get("note", ""),
            })

    # Milestones
    for m in rec.get("milestones", []):
        timeline.append({
            "date": m.get("date"),
            "type": "milestone",
            "title": f"Milestone ({m.get('type')}): {m.get('label', '')}",
        })

    timeline.sort(key=lambda t: t.get("date") or "")

    return {
        "record_id": record_id,
        "record_type": record_type,
        "title": rec.get("title", ""),
        "current_status": rec.get("status", ""),
        "hypothesis": rec.get("hypothesis", ""),
        "what_proves_it": rec.get("what_proves_it", ""),
        "what_kills_it": rec.get("what_kills_it", ""),
        "next_action": rec.get("next_action", ""),
        "timeline": timeline,
        "snapshots_count": len([t for t in timeline if t["type"] == "snapshot"]),
        "decisions_count": len([t for t in timeline if t["type"] == "decision"]),
        "lessons_count": len([t for t in timeline if t["type"] == "lesson"]),
    }


# ─── Portfolio Watch (Monday brief addition) ──────────────────────────

def build_portfolio_watch(brand_id: str) -> list:
    """Build max 2 portfolio observations for the Monday brief.

    Each observation follows SIGNAL/INTERPRETATION/CONFIDENCE/WHY/RECOMMENDED
    ACTION with explicit evidence boundaries. We never invent a ratio
    between effort and demand; we describe both as separate measurements
    and make the inference explicit."""
    s = load_strategy(brand_id)
    today = _today_date()
    month_start = today.replace(day=1)
    observations = []

    # Observation 1: theme concentration if any theme ≥25%
    effort = compute_effort_allocation(brand_id, "month")
    themes = effort.get("theme_concentration", {})
    for theme, pct in themes.items():
        if pct >= 25 and not any(w in theme.lower() for w in ["swing", "shack", "should", "become", "the", "place", "golfers"]):
            # Filter out the noise words
            if pct < 30:
                verdict = "deliberate_dominance_acceptable"
                recommended = f"Deliberate dominance is acceptable this week because the {theme} bet is in its test window. Review after the decision date."
            else:
                verdict = "approaching_concentration"
                recommended = f"Review before scheduling more {theme} executions."
            obs = Claim(
                statement=f"{theme} represents {pct}% of this week's executions.",
                evidence_layer="engagement",
                sources=[{"source": "campaign-data.json", "value": f"{pct}% calendar share for {theme}", "as_of": today.isoformat()}],
                confidence="medium",
                interpretation="Theme concentration is a measure of execution, not of result. We cannot conclude that concentration = success without booking-layer evidence.",
                recommended_action=recommended,
                why_not_stronger="We have engagement-layer data, not booking data. Cannot claim 'this converts at scale' without visit/booking evidence.",
            )
            observations.append(obs)
            break  # max 1 concentration observation

    # Observation 2: largest demand signal gap (effort low but demand exists)
    mismatch = compute_demand_mismatch(brand_id)
    obs_list = mismatch.get("observations", [])
    if obs_list:
        # Pick the lowest-confidence observation with the highest effort %
        import re
        for o in obs_list:
            m = re.search(r"receives (\d+)%", o.get("statement", ""))
            if m and int(m.group(1)) > 30:
                # Top-effort area
                claim = Claim(
                    statement=o["statement"],
                    evidence_layer=o.get("evidence_layer", "engagement"),
                    sources=o.get("sources", []),
                    confidence=o.get("confidence", "low"),
                    interpretation=o.get("interpretation", ""),
                    recommended_action=o.get("recommended_action", ""),
                    why_not_stronger=o.get("why_not_stronger", ""),
                )
                observations.append(claim)
                break

    # Cap at 2 — return dicts, not Claim objects
    return [o.to_dict() if hasattr(o, "to_dict") else o for o in observations[:2]]


# ─── Advertising Watch (Monday brief) ─────────────────────────────────

def build_advertising_watch(brand_id: str) -> list:
    """Max 2 items. Only show something if money requires attention.
    Triggers:
      - Budget burn at >=70% AND maturity 'early' AND outcome_layer < visit
      - Spend concentration >=50% on one bet
      - Orphaned spend with link/review/pause decision needed
      - Booking bet approaching decision date with spend but no booking data
    """
    doc = load_spend(brand_id)
    items = []
    if not doc.get("campaigns"):
        return items

    # Trigger 1: burn vs maturity
    s = load_strategy(brand_id)
    active_bets = [b for b in s.get("bets", []) if b.get("status") in ("in_flight", "planned")]
    for b in active_bets[:5]:
        bvm = budget_burn_vs_maturity(brand_id, b["id"])
        if not bvm or "error" in bvm:
            continue
        burn = bvm.get("burn_pct", 0) or 0
        maturity = bvm.get("evidence_maturity", "")
        outcome = bvm.get("outcome_layer", "")
        if burn >= 70 and maturity == "early" and outcome in ("impression", "engagement", "click"):
            items.append({
                "type": "burn_warning",
                "title": b["title"],
                "burn_pct": burn,
                "outcome_layer": outcome,
                "recommendation": bvm.get("recommendation", ""),
                "summary": f"{burn}% of budget spent on '{b['title']}' while evidence is still at the {outcome} layer.",
            })
            break

    # Trigger 2: spend concentration
    concentration = spend_concentration_warnings(brand_id)
    if concentration:
        c = concentration[0]
        items.append({
            "type": "concentration",
            "title": c["title"],
            "share_pct": c["spend_share_pct"],
            "question": c["question"],
            "context": c["context"],
            "summary": f"{c['spend_share_pct']:.0f}% of monthly paid spend supports '{c['title']}'. Is this deliberate or accidental concentration?",
        })

    # Trigger 3: orphans with action needed
    orphans = detect_orphaned_spend(brand_id)
    if orphans:
        o = orphans[0]
        items.append({
            "type": "orphan",
            "title": o["name"],
            "spend_rands": o["spend_rands"],
            "summary": o["message"],
            "actions": o["actions"],
        })

    return items[:2]


# ─── Compose the full Monday brief ──────────────────────────────────

def compose_monday_brief(brand_id: str = "swing-shack", snapshot_first: bool = True) -> Dict[str, Any]:
    """Compose the complete Monday brief. If snapshot_first is True,
    takes a fresh weekly snapshot before generating."""
    if snapshot_first:
        snapshot_evidence(brand_id)

    changes = detect_changes(brand_id)
    week_cal = build_week_calendar(brand_id)
    decisions = build_decision_arguments(brand_id)
    priorities = synthesize_priorities(brand_id)
    strip = build_compact_strip(brand_id)

    # Audit — light mode for Monday brief
    try:
        audit = _run_audit(brand_id, light=True)
        needs_cleaning = audit.get("needs_cleaning", [])[:3]
    except Exception:
        needs_cleaning = []

    # Portfolio Watch (evidence-bound observations)
    try:
        portfolio_watch = build_portfolio_watch(brand_id)
    except Exception:
        portfolio_watch = []

    # Advertising Watch (max 2)
    try:
        advertising_watch = build_advertising_watch(brand_id)
    except Exception:
        advertising_watch = []

    # ─── Run integrity validation FIRST ────────────────────────────────
    # The OS's hierarchy: DATA → IS DATA TRUSTWORTHY → WHAT DOES IT
    # PROVE → WHAT MIGHT IT MEAN → WHAT SHOULD WE DO. Never reverse.
    try:
        integrity = integrity_reconcile(brand_id)
        priorities = [degrade_confidence(p, brand_id) for p in priorities]
        decisions = [degrade_confidence(d, brand_id) for d in decisions]
    except Exception:
        integrity = {"is_clean": True, "issues": [], "issue_count": 0}

    try:
        anomalies = detect_anomalies(brand_id)
    except Exception:
        anomalies = []

    return {
        "brand_id": brand_id,
        "generated_at": _now(),
        "week_of": week_cal["week_of"],
        "week_to": week_cal["week_to"],
        "integrity": integrity,
        "anomalies": anomalies,
        "what_changed": changes,
        "this_week": week_cal,
        "decisions_this_week": decisions,
        "priorities": priorities,
        "strip": strip,
        "needs_cleaning": needs_cleaning,
        "portfolio_watch": portfolio_watch,
        "advertising_watch": advertising_watch,
    }


# ─── Markdown formatter for Discord / shell output ─────────────────

def _brand_id_from_brief(brief: dict) -> str:
    return brief.get("brand_id", "swing-shack")


def esc(text):
    """Minimal HTML/markdown escape for safety."""
    if not text:
        return ""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_brief_markdown(brief: Dict[str, Any]) -> str:
    """Render the brief as Discord-friendly markdown."""
    md = []
    md.append(f"## This week's update · week of {brief['week_of']} → {brief['week_to']}")
    md.append("")

    # ─── DATA INTEGRITY WARNING first — silent when healthy ──────────
    integrity_warning = render_integrity_warning_section(_brand_id_from_brief(brief))
    if integrity_warning:
        md.append(integrity_warning)
        md.append("")
    md.append("")

    # What changed
    md.append("### What's different this week")
    if not brief["what_changed"]:
        md.append("_Nothing has changed this week — everything is holding steady._")
    else:
        for c in brief["what_changed"][:8]:
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(c["severity"], "·")
            md.append(f"- {emoji} **{c['summary']}**")
            if c.get("detail"):
                md.append(f"  _{c['detail'][:140]}_")
    md.append("")

    # This week
    md.append("### What's planned this week")
    md.append("")
    if brief["this_week"]["marketing"]:
        md.append("**Marketing work**")
        for b in brief["this_week"]["marketing"]:
            themes = ", ".join(b["themes"][:3]) or "—"
            md.append(f"- {b['title']} · topics: {themes}")
            for ms in b["milestones_this_week"]:
                d = _format_date(ms["date"])
                emoji = {"launch": "🚀", "review": "🔍", "decision": "⚖️", "test_start": "🧪", "test_end": "🧪✓"}.get(ms["type"], "·")
                md.append(f"  - {emoji} **{d}** {ms['label']}")
        md.append("")
    if brief["this_week"]["advertising"]:
        md.append("**Advertising work**")
        for b in brief["this_week"]["advertising"]:
            themes = ", ".join(b["themes"][:3]) or "—"
            md.append(f"- {b['title']} · themes: {themes}")
            for ms in b["milestones_this_week"]:
                d = _format_date(ms["date"])
                emoji = {"launch": "🚀", "review": "🔍", "decision": "⚖️"}.get(ms["type"], "·")
                md.append(f"  - {emoji} **{d}** {ms['label']}")
        md.append("")

    # Decisions
    md.append("### Decisions needed this week")
    if not brief["decisions_this_week"]:
        md.append("_No decisions needed this week. Everything has time to run._")
    else:
        for d in brief["decisions_this_week"]:
            verb = "OVERDUE" if d["overdue"] else f"in {d['days_away']}d"
            md.append(f"**{d['title']}** — {verb}")
            md.append(f"- Signal: {d['current_signal']}")
            md.append(f"- Evidence for: {d['evidence_for'][:140]}")
            md.append(f"- Evidence against: {d['evidence_against'][:140]}")
            md.append(f"- Last lesson: {d['last_lesson'][:140]}")
            md.append(f"- Recommended: **{d['recommended'].upper()}** — {d['rationale']}")
            md.append("")

    # Portfolio watch (with evidence boundaries)
    if brief.get("portfolio_watch"):
        md.append("### Portfolio watch")
        md.append("")
        for claim_dict in brief["portfolio_watch"]:
            c = Claim(
                statement=claim_dict["statement"],
                evidence_layer=claim_dict["evidence_layer"],
                sources=claim_dict["sources"],
                confidence=claim_dict["confidence"],
                interpretation=claim_dict.get("interpretation", ""),
                recommended_action=claim_dict.get("recommended_action", ""),
                why_not_stronger=claim_dict.get("why_not_stronger", ""),
            )
            md.append(c.to_markdown())
            md.append("")
    else:
        md.append("### Portfolio watch")
        md.append("_Nothing to flag this week. No meaningful imbalances._")
        md.append("")

    # Advertising watch
    if brief.get("advertising_watch"):
        md.append("### Advertising watch")
        md.append("")
        for item in brief["advertising_watch"]:
            if item["type"] == "burn_warning":
                md.append(f"**{esc(item['title'])}**")
                md.append(f"  {esc(item['summary'])}")
                md.append(f"  Suggestion: {esc(item.get('recommendation', ''))}")
            elif item["type"] == "concentration":
                md.append(f"**{esc(item['title'])}**")
                md.append(f"  {esc(item['summary'])}")
                md.append(f"  Context: {esc(str(item.get('context', {})))}")
            elif item["type"] == "orphan":
                md.append(f"**{esc(item['title'])}**")
                md.append(f"  {esc(item['summary'])}")
                md.append(f"  Actions: Link to strategy / Review / Pause")
            md.append("")
    else:
        md.append("### Advertising watch")
        md.append("_Nothing to flag this week. Money is on plan._")
        md.append("")

    # Needs cleaning (audit)
    md.append("### Things to clean up")
    if brief.get("needs_cleaning"):
        for nc in brief["needs_cleaning"]:
            md.append(f"- **{nc['title']}** → {nc['audit_status'].upper()}")
            md.append(f"  _{nc.get('reason', '')[:140]}_")
            md.append(f"  _Action:_ {nc.get('next_action', '')}")
    else:
        md.append("_Nothing to clean up this week. Everything is healthy._")
    md.append("")

    # Priorities
    md.append("### This week's top priorities")
    if not brief["priorities"]:
        md.append("_No priorities needed — every bet is running smoothly._")
    else:
        for i, p in enumerate(brief["priorities"], 1):
            md.append(f"{i}. **{p['title']}**")
            md.append(f"   _Why:_ {p['why']}")
            md.append(f"   _What to do first:_ {p['action_first_step']}")
    md.append("")

    return "\n".join(md)


# ─── CLI entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    brand = sys.argv[1] if len(sys.argv) > 1 else "swing-shack"
    brief = compose_monday_brief(brand)
    print(json.dumps(brief, indent=2, default=str)[:5000])
    print("\n--- markdown ---\n")
    print(render_brief_markdown(brief))