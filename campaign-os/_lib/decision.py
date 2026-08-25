"""
decision.py — Decision & Action Layer.

The OS's principle:
  DATA -> ANALYTICS -> STRATEGY -> PORTFOLIO -> CALENDAR -> ADVERTISING -> AUDIT
  -> DECISION QUEUE

This module is the last layer. The Morning Brief becomes the chief of
staff: it pulls every place in the OS that has a genuine human choice
and asks for the decision.

Discipline:
  - INFORMATION is not a decision
  - ATTENTION is not a decision
  - Only include items where a real human choice exists
  - Every card shows WHAT / WHY NOW / EVIDENCE / BOUNDARY /
    COST OF WAITING / RECOMMENDATION + Actions
  - OS can detect, calculate, recommend, but human must decide
  - Every decision records context + reason → replay history
  - Disagreements are remembered so future analysis knows retention
    was deliberate, not forgotten
  - Deferred decisions come back when their wait-condition is met
  - Decision Debt surfaces repeatedly postponed decisions
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import uuid
from typing import Any, Dict, List, Optional


# ─── Data path ─────────────────────────────────────────────────────────
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
DECISIONS_DIR = os.path.join(DATA_DIR, "decisions")
os.makedirs(DECISIONS_DIR, exist_ok=True)


# ─── Priority levels ────────────────────────────────────────────────────
PRIORITY_DECIDE_NOW = "decide_now"     # due, money at risk, blocked
PRIORITY_THIS_WEEK = "this_week"      # needs decision before week ends
PRIORITY_WATCH = "watch"              # visible but no action yet

PRIORITY_LABELS = {
    PRIORITY_DECIDE_NOW: ("DECIDE NOW", "decide-now"),
    PRIORITY_THIS_WEEK: ("THIS WEEK", "this-week"),
    PRIORITY_WATCH: ("WATCH", "watch"),
}

# ─── Status ─────────────────────────────────────────────────────────────
STATUS_OPEN = "open"                  # needs decision
STATUS_DECIDED = "decided"            # human decided
STATUS_DEFERRED = "deferred"          # explicitly deferred, comes back later
STATUS_DISAGREED = "disagreed"        # human chose differently
STATUS_BLOCKED = "blocked"            # cannot decide, dependency broken
STATUS_AUTO_RESOLVED = "auto_resolved"  # OS resolved (only for safe things)


# ─── Action types ──────────────────────────────────────────────────────
# These are the verbs a human can choose from. The set varies per source,
# but the canonical set is:
ACTION_REFINE = "REFINE"
ACTION_SCALE = "SCALE"
ACTION_HOLD = "HOLD"
ACTION_KILL = "KILL"
ACTION_PAUSE = "PAUSE"
ACTION_KEEP = "KEEP"
ACTION_DEFER = "DEFER"
ACTION_DISAGREE = "DISAGREE"
ACTION_FIX_MEASUREMENT = "FIX_MEASUREMENT"
ACTION_LINK = "LINK"
ACTION_REVIEW = "REVIEW"
ACTION_OPEN_STRATEGY = "OPEN_STRATEGY"
ACTION_OPEN_ADVERTISING = "OPEN_ADVERTISING"
ACTION_OPEN_PORTFOLIO = "OPEN_PORTFOLIO"
ACTION_OPEN_DATA_HEALTH = "OPEN_DATA_HEALTH"


# ─── Authority boundary ─────────────────────────────────────────────────
# OS can auto-act on these:
SAFE_AUTO_ACTIONS = {ACTION_PAUSE, ACTION_HOLD}

# These ALWAYS need human approval:
HUMAN_ONLY_ACTIONS = {
    ACTION_KILL, ACTION_SCALE, ACTION_REFINE,
    "RETIRE", "APPROVE_BET", "CHANGE_POSITIONING",
}


# ─── Storage ────────────────────────────────────────────────────────────
def _decisions_path(brand_id: str) -> str:
    return os.path.join(DECISIONS_DIR, f"{brand_id}.json")


def load_decisions(brand_id: str) -> Dict[str, Any]:
    """Load the decision log + open queue for a brand."""
    path = _decisions_path(brand_id)
    if not os.path.isfile(path):
        return {"brand": brand_id, "open": [], "history": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"brand": brand_id, "open": [], "history": []}


def save_decisions(brand_id: str, doc: Dict[str, Any]) -> None:
    path = _decisions_path(brand_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, default=str)


# ─── Decision card shape ───────────────────────────────────────────────
import hashlib

def _stable_id(source: str, ctx: Dict[str, Any]) -> str:
    """Deterministic decision id based on source + context. Same situation
    = same id, so the human can record a decision and the OS won't lose
    track of which card it was for."""
    sig = json.dumps({"src": source, "ctx": ctx}, sort_keys=True, default=str)
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()[:8]


def new_decision(
    *,
    source: str,                 # 'strategy' | 'advertising' | 'portfolio' | ...
    priority: str,
    what: str,                   # WHAT?
    why_now: str,                # WHY NOW?
    evidence: List[str],         # EVIDENCE
    boundary: str,               # BOUNDARY (what we don't know)
    cost_of_waiting: str,        # COST OF WAITING
    recommendation: str,         # OS recommendation
    actions: List[Dict[str, str]],  # [{label, action, opens?}]
    context: Optional[Dict[str, Any]] = None,
    blocked_by: Optional[str] = None,
    blocked_reason: Optional[str] = None,
    link: Optional[str] = None,
    confidence: str = "medium",
    brand_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a new decision card."""
    return {
        "id": _stable_id(source, context or {}),
        "source": source,
        "priority": priority,
        "what": what,
        "why_now": why_now,
        "evidence": evidence,
        "boundary": boundary,
        "cost_of_waiting": cost_of_waiting,
        "recommendation": recommendation,
        "actions": actions,
        "context": context or {},
        "blocked_by": blocked_by,
        "blocked_reason": blocked_reason,
        "link": link,
        "confidence": confidence,
        "status": STATUS_BLOCKED if blocked_by else STATUS_OPEN,
        "created_at": _now_iso(),
        "brand_id": brand_id,
    }


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# ─── Candidate detection ───────────────────────────────────────────────
# Each *_candidates() function returns a list of decision cards.
# They are pulled from the live OS state (strategy, spend, audit,
# portfolio, integrity). Each one checks whether the item has a real
# human choice; otherwise it stays as INFORMATION, not a decision.


def _candidate_strategy(s, brand_id: str) -> List[Dict[str, Any]]:
    """Bets that are approaching their decision date."""
    out: List[Dict[str, Any]] = []
    today = _dt.date.today()
    for b in s.get("bets", []):
        status = b.get("status")
        if status in ("retired", "won", "lost", "killed"):
            continue
        dd = b.get("decision_date")
        if not dd:
            continue
        try:
            dd_d = _dt.datetime.fromisoformat(dd[:10]).date()
        except Exception:
            continue
        days = (dd_d - today).days
        # Only surface if decision date is within 30 days OR overdue
        if days > 30:
            continue
        # Skip if status already has a recent decision record (replay)
        priority = PRIORITY_DECIDE_NOW if days <= 7 else PRIORITY_THIS_WEEK
        rec = "REFINE" if b.get("trend") == "weakening" else (
            "SCALE" if b.get("trend") == "strengthening" else "HOLD"
        )
        cost = "Decision date approaching"
        if days < 0:
            cost = f"Decision was due {-days}d ago. Continuing without deciding means the bet silently drifts."
            priority = PRIORITY_DECIDE_NOW
        out.append(new_decision(
            source="strategy",
            priority=priority,
            what=b.get("title", "Untitled bet"),
            why_now=f"Decision date {dd_d.isoformat()} ({days}d from today).",
            evidence=[
                f"Trend: {b.get('trend', 'unknown')}",
                f"Evidence net: {b.get('evidence_net', '?')}",
                f"Links to move: {b.get('links_to_market_move', '—')}",
            ],
            boundary=b.get("evidence_against") or "We don't know whether this bet will continue to hold.",
            cost_of_waiting=cost,
            recommendation=rec,
            confidence=b.get("confidence", "medium"),
            actions=[
                {"label": "Refine", "action": ACTION_REFINE},
                {"label": "Scale", "action": ACTION_SCALE},
                {"label": "Hold", "action": ACTION_HOLD},
                {"label": "Kill", "action": ACTION_KILL},
                {"label": "Open Strategy", "action": ACTION_OPEN_STRATEGY, "link": f"/strategy?brand={brand_id}&record={b['id']}"},
            ],
            context={"bet_id": b.get("id"), "decision_date": dd},
            brand_id=brand_id,
        ))
    return out


def _candidate_advertising(spend_doc, brand_id: str) -> List[Dict[str, Any]]:
    """Orphan spend, concentration, burn-vs-maturity."""
    out: List[Dict[str, Any]] = []
    campaigns = spend_doc.get("campaigns", []) or []
    total = sum(c.get("spend_rands", 0) for c in campaigns)
    if total == 0:
        return out

    # Orphan spend
    for c in campaigns:
        bet_id = c.get("strategy_link", {}).get("bet_id") or c.get("bet_id")
        if not bet_id and c.get("status") in ("active", "running"):
            spend = c.get("spend_rands", 0)
            out.append(new_decision(
                source="advertising",
                priority=PRIORITY_DECIDE_NOW if spend > 1000 else PRIORITY_THIS_WEEK,
                what=f"{c.get('name') or c.get('campaign_name') or 'Untitled campaign'}",
                why_now=f"R{spend:,.0f} spent with no active strategic link.",
                evidence=[
                    f"Platform: {c.get('platform', 'unknown')}",
                    f"Spend: R{spend:,.0f}",
                    f"Status: {c.get('status', 'unknown')}",
                ],
                boundary="Without a strategic link, we cannot tell whether this spend supports any of our bets.",
                cost_of_waiting=f"Continuing to spend R{spend:,.0f}/month without a strategy link means money is leaving without strategic accountability.",
                recommendation="PAUSE",
                confidence="high",
                actions=[
                    {"label": "Pause", "action": ACTION_PAUSE},
                    {"label": "Link to bet", "action": ACTION_LINK},
                    {"label": "Keep", "action": ACTION_KEEP},
                    {"label": "Open Advertising", "action": ACTION_OPEN_ADVERTISING, "link": f"/strategy?brand={brand_id}&view=spend"},
                ],
                context={"campaign_id": c.get("campaign_id") or c.get("id"), "spend": spend},
                brand_id=brand_id,
            ))

    # Spend concentration (>50% to one bet)
    by_bet: Dict[str, float] = {}
    for c in campaigns:
        if c.get("status") not in ("active", "running"):
            continue
        bid = c.get("strategy_link", {}).get("bet_id") or c.get("bet_id") or "unallocated"
        by_bet[bid] = by_bet.get(bid, 0) + c.get("spend_rands", 0)
    for bet_id, amt in by_bet.items():
        if bet_id == "unallocated":
            continue
        share = amt / total if total else 0
        if share > 0.5 and amt > 1000:
            out.append(new_decision(
                source="advertising",
                priority=PRIORITY_THIS_WEEK,
                what=f"{int(share*100)}% of monthly paid spend supports one bet",
                why_now=f"R{amt:,.0f} of R{total:,.0f} (={int(share*100)}%) is going to a single strategic bet.",
                evidence=[f"Bet: {bet_id}", f"Total monthly spend: R{total:,.0f}"],
                boundary="We don't know yet whether this concentration is deliberate conviction or accidental.",
                cost_of_waiting=f"Without review, R{amt:,.0f}/month could be running without active oversight.",
                recommendation="REVIEW",
                confidence="medium",
                actions=[
                    {"label": "Review", "action": ACTION_REVIEW},
                    {"label": "Agree (deliberate)", "action": ACTION_KEEP},
                    {"label": "Rebalance", "action": ACTION_LINK},
                ],
                context={"bet_id": bet_id, "share": share},
                brand_id=brand_id,
            ))

    return out


def _candidate_portfolio(s, brand_id: str) -> List[Dict[str, Any]]:
    """Theme concentration / demand-content mismatch from portfolio view."""
    out: List[Dict[str, Any]] = []
    bets = [b for b in s.get("bets", []) if b.get("status") not in ("retired", "won", "lost", "killed")]
    if not bets:
        return out

    # Theme concentration: if one theme has >50% of active themes
    themes: Dict[str, int] = {}
    for b in bets:
        for t in b.get("content_themes", []) or []:
            themes[t] = themes.get(t, 0) + 1
    total = sum(themes.values())
    if total >= 3:
        top_theme, top_count = max(themes.items(), key=lambda kv: kv[1])
        share = top_count / total
        if share > 0.5:
            out.append(new_decision(
                source="portfolio",
                priority=PRIORITY_THIS_WEEK,
                what=f"{top_theme} concentration in active content",
                why_now=f"{top_theme}-related executions represent {int(share*100)}% of active themes.",
                evidence=[f"Top theme: {top_theme}", f"Active themes: {total}", f"Share: {int(share*100)}%"],
                boundary="Concentration is a measure of execution, not of result. We cannot conclude that concentration = success without booking-layer evidence.",
                cost_of_waiting=f"Continuing to concentrate {int(share*100)}% of content on {top_theme} may leave other strategic areas unsupported.",
                recommendation=f"Do not add another {top_theme} campaign until the current bet reaches its decision date.",
                confidence="medium",
                actions=[
                    {"label": "Agree", "action": ACTION_KEEP},
                    {"label": "Ignore", "action": ACTION_DEFER},
                    {"label": "Review Portfolio", "action": ACTION_OPEN_PORTFOLIO, "link": f"/strategy?brand={brand_id}"},
                ],
                context={"theme": top_theme, "share": share},
                brand_id=brand_id,
            ))

    return out


def _candidate_integrity(integrity_doc, brand_id: str) -> List[Dict[str, Any]]:
    """Critical / high integrity issues that block decisions."""
    out: List[Dict[str, Any]] = []
    issues = integrity_doc.get("issues", []) or []
    for issue in issues:
        if issue.get("severity") not in ("critical", "high"):
            continue
        # Skip advertising-orphan issues here — those come from candidate_advertising
        if issue.get("code") == "orphaned_spend":
            continue
        out.append(new_decision(
            source="data",
            priority=PRIORITY_DECIDE_NOW if issue.get("severity") == "critical" else PRIORITY_THIS_WEEK,
            what=issue.get("title", "Data integrity issue"),
            why_now=f"[{issue.get('severity', '?').upper()}] {issue.get('detail', '')}",
            evidence=issue.get("evidence", []) or [
                f"Code: {issue.get('code', 'unknown')}",
                f"Severity: {issue.get('severity', '?')}",
            ],
            boundary="Without fixing this, we cannot reliably measure the impact of any spend or content decision.",
            cost_of_waiting=f"Decisions made on unreliable data may lead to wasted spend or wrong scaling.",
            recommendation="FIX_MEASUREMENT",
            confidence="high",
            actions=[
                {"label": "Prioritise tracking fix", "action": ACTION_FIX_MEASUREMENT},
                {"label": "Accept limitation", "action": ACTION_KEEP},
                {"label": "Open Data Health", "action": ACTION_OPEN_DATA_HEALTH, "link": f"/strategy?brand={brand_id}&view=data-health"},
            ],
            context={"issue_code": issue.get("code")},
            blocked_by=issue.get("code"),
            blocked_reason=f"Until {issue.get('title', 'this issue')} is fixed, related decisions carry reduced confidence.",
            brand_id=brand_id,
        ))
    return out


def _candidate_measurement(integrity_doc, brand_id: str) -> List[Dict[str, Any]]:
    """Measurement gaps that block booking/revenue-layer decisions."""
    out: List[Dict[str, Any]] = []
    debt = integrity_doc.get("debt") or {}
    layers = debt.get("layers", {}) or {}
    booking = layers.get("booking") or layers.get("bookings") or {}
    if booking and booking.get("status") in ("Broken", "Unavailable"):
        out.append(new_decision(
            source="data",
            priority=PRIORITY_DECIDE_NOW,
            what="Booking-layer measurement broken",
            why_now=f"Bookings status: {booking.get('status', 'unknown')}. Evidence cannot currently reach the booking layer.",
            evidence=[
                f"Layer: Bookings",
                f"Status: {booking.get('status', 'unknown')}",
                f"Last valid layer: {integrity_doc.get('last_valid_layer', 'GA4')}",
            ],
            boundary="We cannot measure whether any campaign converts. SCALE/HOLD/KILL decisions on booking-driving campaigns are guesswork.",
            cost_of_waiting="Decisions about spend on booking-driving campaigns will be made without evidence.",
            recommendation="FIX_MEASUREMENT",
            confidence="high",
            actions=[
                {"label": "Fix measurement first", "action": ACTION_FIX_MEASUREMENT},
                {"label": "Accept limitation", "action": ACTION_KEEP},
                {"label": "Open Data Health", "action": ACTION_OPEN_DATA_HEALTH, "link": f"/strategy?brand={brand_id}&view=data-health"},
            ],
            blocked_by="booking_measurement_broken",
            blocked_reason="Decision quality is limited until booking measurement is repaired.",
            brand_id=brand_id,
        ))
    return out


# ─── Queue builder ─────────────────────────────────────────────────────
def build_decision_queue(brand_id: str) -> Dict[str, Any]:
    """Aggregate decision candidates from across the OS.

    Returns:
      {
        brand, queue: [decisions...],
        counts: {decide_now, this_week, watch, blocked},
        generated_at: iso
      }
    """
    # Lazy-load live OS state
    from strategy_store import load_strategy
    from spend import load_spend
    from integrity import reconcile, measurement_debt

    strategy = load_strategy(brand_id) or {}
    spend_doc = load_spend(brand_id) or {}
    integrity_doc = reconcile(brand_id) or {}
    debt_doc = measurement_debt(brand_id) or {}
    # Inject debt into integrity_doc for _candidate_measurement
    integrity_doc_with_debt = dict(integrity_doc)
    integrity_doc_with_debt["debt"] = debt_doc
    integrity_doc_with_debt["last_valid_layer"] = (debt_doc or {}).get("last_valid_layer", "GA4")

    candidates: List[Dict[str, Any]] = []
    candidates += _candidate_strategy(strategy, brand_id)
    candidates += _candidate_advertising(spend_doc, brand_id)
    candidates += _candidate_portfolio(strategy, brand_id)
    candidates += _candidate_integrity(integrity_doc_with_debt, brand_id)
    candidates += _candidate_measurement(integrity_doc_with_debt, brand_id)

    # Hydrate 'since last review' for each
    log = load_decisions(brand_id)
    for card in candidates:
        card["since_last_review"] = _since_last_review(card, log)

    # Sort: DECIDE_NOW first, then THIS_WEEK, then WATCH
    order = {PRIORITY_DECIDE_NOW: 0, PRIORITY_THIS_WEEK: 1, PRIORITY_WATCH: 2}
    candidates.sort(key=lambda d: (order.get(d.get("priority"), 99), d.get("source", "")))

    counts = {
        "decide_now": sum(1 for c in candidates if c.get("priority") == PRIORITY_DECIDE_NOW),
        "this_week": sum(1 for c in candidates if c.get("priority") == PRIORITY_THIS_WEEK),
        "watch": sum(1 for c in candidates if c.get("priority") == PRIORITY_WATCH),
        "blocked": sum(1 for c in candidates if c.get("status") == STATUS_BLOCKED),
    }

    return {
        "brand": brand_id,
        "queue": candidates,
        "counts": counts,
        "generated_at": _now_iso(),
    }


def _since_last_review(card: Dict[str, Any], log: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Compute what changed since the last human decision on this item."""
    ctx = card.get("context") or {}
    # Find a prior decision for the same bet/campaign/theme
    for h in (log.get("history") or [])[::-1]:
        h_ctx = h.get("context") or {}
        if (ctx.get("bet_id") and ctx.get("bet_id") == h_ctx.get("bet_id")) \
           or (ctx.get("campaign_id") and ctx.get("campaign_id") == h_ctx.get("campaign_id")) \
           or (ctx.get("theme") and ctx.get("theme") == h_ctx.get("theme")) \
           or (ctx.get("issue_code") and ctx.get("issue_code") == h_ctx.get("issue_code")):
            try:
                dt_then = _dt.datetime.fromisoformat(h["decided_at"][:19])
                dt_now = _dt.datetime.now(_dt.timezone.utc)
                days = (dt_now - dt_then).days
                return {
                    "since": h.get("decided_at"),
                    "decision_then": h.get("context", {}).get("chosen_action") or h.get("decision"),
                    "reason_then": h.get("reason", ""),
                    "days_ago": days,
                }
            except Exception:
                pass
    return None


# ─── Record a decision ──────────────────────────────────────────────────
def record_decision(
    brand_id: str,
    decision_id: str,
    *,
    action: str,
    reason: str,
    person: str = "christelle",
    confidence: Optional[str] = None,
    context_patch: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record a human decision on a candidate. Returns the recorded entry.

    Status mapping:
      - action in SAFE_AUTO_ACTIONS: status = decided (OS-executed)
      - action in DISAGREE flow: status = disagreed
      - action == DEFER: status = deferred (with wait condition)
      - else: status = decided
    """
    queue = build_decision_queue(brand_id)
    card = next((c for c in queue.get("queue", []) if c.get("id") == decision_id), None)
    if not card:
        # Try open queue
        log = load_decisions(brand_id)
        card = next((c for c in (log.get("open") or []) if c.get("id") == decision_id), None)
    if not card:
        return {"ok": False, "error": "decision not found"}

    status = STATUS_DECIDED
    if action == ACTION_DEFER:
        status = STATUS_DEFERRED
    elif action == ACTION_DISAGREE:
        status = STATUS_DISAGREED

    # Preserve the original context so future since_last_review lookups still match.
    merged_context = {**(card.get("context") or {})}
    merged_context["chosen_action"] = action  # Record what was chosen
    if context_patch:
        for k, v in context_patch.items():
            if v is not None:
                merged_context[k] = v
    entry = {
        "id": decision_id,
        "source": card.get("source"),
        "what": card.get("what"),
        "decision": action,
        "os_recommendation": card.get("recommendation"),
        "reason": reason,
        "person": person,
        "decided_at": _now_iso(),
        "evidence_at_decision": card.get("evidence"),
        "confidence": confidence or card.get("confidence"),
        "context": merged_context,
    }

    log = load_decisions(brand_id)
    log.setdefault("history", []).append(entry)
    # Remove from open queue if it was open
    log["open"] = [c for c in log.get("open", []) if c.get("id") != decision_id]
    save_decisions(brand_id, log)

    return {"ok": True, "status": status, "entry": entry}


def defer_decision(
    brand_id: str,
    decision_id: str,
    *,
    until: Optional[str] = None,
    wait_for_bookings: Optional[int] = None,
    wait_for_spend: Optional[float] = None,
    wait_for_measurement_fix: bool = False,
    reason: str = "",
    person: str = "christelle",
) -> Dict[str, Any]:
    """Record a deferral. The OS will surface this card again when the
    wait condition is met."""
    queue = build_decision_queue(brand_id)
    card = next((c for c in queue.get("queue", []) if c.get("id") == decision_id), None)
    if not card:
        return {"ok": False, "error": "decision not found"}

    wait_condition = {}
    if until:
        wait_condition["until"] = until
    if wait_for_bookings is not None:
        wait_condition["wait_for_bookings"] = wait_for_bookings
    if wait_for_spend is not None:
        wait_condition["wait_for_spend"] = wait_for_spend
    if wait_for_measurement_fix:
        wait_condition["wait_for_measurement_fix"] = True

    entry = {
        "id": decision_id,
        "source": card.get("source"),
        "what": card.get("what"),
        "decision": "DEFER",
        "os_recommendation": card.get("recommendation"),
        "reason": reason,
        "person": person,
        "decided_at": _now_iso(),
        "wait_condition": wait_condition,
        "evidence_at_decision": card.get("evidence"),
        "context": card.get("context") or {},
    }
    log = load_decisions(brand_id)
    log.setdefault("history", []).append(entry)
    log["deferred"] = [d for d in log.get("deferred", []) if d.get("id") != decision_id]
    log["deferred"].append(entry)
    save_decisions(brand_id, log)
    return {"ok": True, "entry": entry}


def disagree_with_os(
    brand_id: str,
    decision_id: str,
    *,
    chosen_action: str,
    reason: str,
    person: str = "christelle",
) -> Dict[str, Any]:
    """Record the human disagreeing with the OS recommendation."""
    return record_decision(
        brand_id,
        decision_id,
        action=ACTION_DISAGREE,
        reason=f"Chose {chosen_action} instead. {reason}".strip(),
        context_patch={"chosen_action": chosen_action},
        person=person,
    )


# ─── Decision Debt ─────────────────────────────────────────────────────
def decision_debt(brand_id: str) -> Dict[str, Any]:
    """Items that have been deferred and are now overdue (or about to be)."""
    log = load_decisions(brand_id)
    today = _dt.date.today()
    overdue: List[Dict[str, Any]] = []
    upcoming: List[Dict[str, Any]] = []
    for entry in (log.get("history") or []):
        if entry.get("decision") != "DEFER":
            continue
        wc = entry.get("wait_condition") or {}
        until = wc.get("until")
        if until:
            try:
                d = _dt.datetime.fromisoformat(until[:10]).date()
                days = (d - today).days
                rec = {
                    "what": entry.get("what"),
                    "source": entry.get("source"),
                    "due": until,
                    "days_overdue": -days if days < 0 else 0,
                    "days_until": days if days >= 0 else 0,
                    "reason": entry.get("reason", ""),
                }
                if days < 0:
                    overdue.append(rec)
                elif days <= 7:
                    upcoming.append(rec)
            except Exception:
                pass

    # Manager read
    if overdue:
        n = len(overdue)
        total_days = sum(d.get("days_overdue", 0) for d in overdue)
        manager_read = f"{n} decision{'s' if n != 1 else ''} overdue (avg {total_days // max(n, 1)} days). Some are quietly becoming permanent without a current decision."
    else:
        manager_read = "No overdue decisions."

    return {
        "brand": brand_id,
        "overdue": overdue,
        "upcoming": upcoming,
        "overdue_count": len(overdue),
        "manager_read": manager_read,
    }


# ─── Clear My Desk ─────────────────────────────────────────────────────
def clear_my_desk_sequence(brand_id: str) -> Dict[str, Any]:
    """Build a step-by-step sequence for clearing the desk.

    Skips items that already have a recent decision/defer (the OS knows
    they were handled). Returns:
      {
        brand, steps: [{order, decision_id, what, ...}],
        summary_template: "Desk clear. X decisions, Y deferred, Z measurement tasks."
      }
    """
    queue = build_decision_queue(brand_id)
    # Filter out items already decided/deferred within the last 7 days
    log = load_decisions(brand_id)
    handled_ids = set()
    for entry in (log.get("history") or [])[-20:]:
        try:
            dt_then = _dt.datetime.fromisoformat(entry["decided_at"][:19])
            if (_dt.datetime.now(_dt.timezone.utc) - dt_then).days < 7:
                ctx = entry.get("context", {}) or {}
                # Build the same stable id and skip it
                sid = _stable_id(entry.get("source", ""), ctx)
                handled_ids.add(sid)
        except Exception:
            pass

    candidates = [c for c in queue.get("queue", []) if c.get("id") not in handled_ids]
    ordered = [c for c in candidates if c.get("priority") == PRIORITY_DECIDE_NOW]
    if not ordered:
        ordered = [c for c in candidates if c.get("priority") == PRIORITY_THIS_WEEK]

    steps = []
    for i, card in enumerate(ordered, 1):
        steps.append({
            "order": i,
            "decision_id": card.get("id"),
            "what": card.get("what"),
            "priority": card.get("priority"),
            "source": card.get("source"),
            "why_now": card.get("why_now"),
            "evidence": card.get("evidence"),
            "boundary": card.get("boundary"),
            "cost_of_waiting": card.get("cost_of_waiting"),
            "recommendation": card.get("recommendation"),
            "confidence": card.get("confidence"),
            "actions": card.get("actions"),
            "blocked_by": card.get("blocked_by"),
            "blocked_reason": card.get("blocked_reason"),
            "since_last_review": card.get("since_last_review"),
        })

    summary = {
        "decisions_to_review": len(steps),
        "blocked_remaining": len(blocked_remain),
        "automated_actions": automated_count,
        "summary_template": (
            "DESK CLEAR\n"
            "{n} decisions reviewed.\n"
            "{blocked} blocked items remain.\n"
            "{auto} automated actions completed.\n"
            "End of queue."
        ),
    }

    return {
        "brand": brand_id,
        "steps": steps,
        "step_count": len(steps),
        "summary": summary,
        "blocked_remaining": blocked_remain,
        "automated_actions": automated_count,
    }


# ─── Authority check ───────────────────────────────────────────────────
def authority_boundary(action: str) -> Dict[str, Any]:
    """Return whether OS can auto-act, or human is required."""
    if action in SAFE_AUTO_ACTIONS:
        return {"mode": "OS_AUTO", "reason": f"{action} is a safe action the OS can execute."}
    if action in HUMAN_ONLY_ACTIONS:
        return {"mode": "HUMAN_REQUIRED", "reason": f"{action} is a strategic decision — human approval required."}
    return {"mode": "HUMAN_REQUIRED", "reason": "Action not in safe-auto list."}


# ─── Morning Brief integration ─────────────────────────────────────────
def morning_brief_top_three(brand_id: str) -> List[Dict[str, Any]]:
    """The 3 decisions the human most needs to see today.

    Sorts by priority, prefers DECIDE_NOW, falls back to THIS_WEEK.
    Returns a compact teaser for each — full card lives in /api/decisions/queue.
    """
    queue = build_decision_queue(brand_id)
    ordered = [c for c in queue.get("queue", []) if c.get("priority") == PRIORITY_DECIDE_NOW]
    if len(ordered) < 3:
        # Add THIS_WEEK
        ordered += [c for c in queue.get("queue", []) if c.get("priority") == PRIORITY_THIS_WEEK][:3-len(ordered)]
    top3 = []
    for c in ordered[:3]:
        top3.append({
            "id": c.get("id"),
            "what": c.get("what"),
            "source": c.get("source"),
            "recommendation": c.get("recommendation"),
            "why_now": c.get("why_now"),
            "blocked_by": c.get("blocked_by"),
            "priority": c.get("priority"),
            "confidence": c.get("confidence"),
            "actions": [a for a in c.get("actions", []) if a.get("action") not in (ACTION_OPEN_STRATEGY, ACTION_OPEN_ADVERTISING, ACTION_OPEN_PORTFOLIO, ACTION_OPEN_DATA_HEALTH)][:4],
        })
    return top3


def morning_brief_header(brand_id: str) -> Dict[str, Any]:
    """The very top of the Morning Brief — 'Good morning, BRAND' + counts.

    Reconciliation discipline:
      - needs_you = same collection that gets rendered as Top 3 cards
      - os_action = items the OS can safely act on (with active policy)
      - blocked = items blocked by broken evidence
      - The three counts NEVER mix
    """
    queue = build_decision_queue(brand_id)
    debt = decision_debt(brand_id)

    cards = queue.get("queue", [])

    # Try to import governance so we can accurately count OS-action items
    needs_you = []
    os_action = []
    blocked = []
    try:
        from governance import check_authority
        for c in cards:
            if c.get("status") == "blocked" or c.get("blocked_by"):
                blocked.append(c)
                continue
            # What action would the human take? Look at actions.
            # Use the first non-navigation action as the recommended one
            action = None
            for a in c.get("actions", []):
                act = a.get("action")
                if act and act not in (ACTION_OPEN_STRATEGY, ACTION_OPEN_ADVERTISING, ACTION_OPEN_PORTFOLIO, ACTION_OPEN_DATA_HEALTH):
                    action = act
                    break
            if not action:
                continue
            auth = check_authority(brand_id, action, human_approved=False)
            if auth.get("can_execute"):
                os_action.append(c)
            else:
                needs_you.append(c)
    except Exception:
        # Governance unavailable — fall back to: all non-blocked → needs_you
        for c in cards:
            if c.get("status") == "blocked" or c.get("blocked_by"):
                blocked.append(c)
            else:
                needs_you.append(c)

    brand_display = brand_id.replace("-", " ").title()
    n_needs = len(needs_you)
    n_os = len(os_action)
    n_blocked = len(blocked)
    n_overdue = debt.get("overdue_count", 0)

    if n_needs == 1:
        lead = "1 thing needs you today."
    elif n_needs > 1:
        lead = f"{n_needs} things need you today."
    else:
        lead = "Nothing needs you today."

    extras = []
    if n_os:
        extras.append(f"{n_os} OS action{'s' if n_os != 1 else ''}")
    if n_blocked:
        extras.append(f"{n_blocked} blocked")
    if n_overdue:
        extras.append(f"{n_overdue} overdue")
    if extras:
        lead += " " + " · ".join(extras) + "."

    return {
        "brand": brand_id,
        "greeting": f"Good morning — {brand_display}",
        "lead": lead,
        "counts": {
            "needs_you": n_needs,
            "os_action": n_os,
            "blocked": n_blocked,
            "watch": sum(1 for c in cards if c.get("priority") == "watch"),
        },
        "needs_you_count": n_needs,
        "os_action_count": n_os,
        "blocked_count": n_blocked,
        "decision_debt": n_overdue,
    }