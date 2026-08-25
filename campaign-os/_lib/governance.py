"""
governance.py — Governance, Permissions & Decision Integrity.

Hierarchy enforced:
  OBSERVE
   ↓
  VALIDATE
   ↓
  INTERPRET
   ↓
  RECOMMEND
   ↓
  HUMAN DECISION
   ↓
  EXECUTE
   ↓
  RECORD
   ↓
  REVIEW OUTCOME

Principles:
  - The OS may observe, analyse, recommend, prepare — AUTOMATICALLY
  - The OS may EXECUTE only with explicit human approval OR explicit
    automation policy that matches
  - By default PAUSE/REDUCE/INCREASE/KILL/SCALE/RETIRE/CHANGE POSITIONING
    all require human approval
  - Every decision creates an immutable record of what was known at that
    moment (decision integrity)
  - Decision ≠ Execution. A decision is a human choice; execution is
    the external action that follows
  - Action receipts record every external change with before/after
  - Conflicts between subsystem recommendations are surfaced
  - Decision Quality is tracked so the OS can learn whether decisions
    were made with enough information
  - Disagreements are learning opportunities, not errors
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple


# ─── Data paths ─────────────────────────────────────────────────────────
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
GOVERNANCE_DIR = os.path.join(DATA_DIR, "governance")
DECISIONS_DIR = os.path.join(DATA_DIR, "decisions")
RECEIPTS_DIR = os.path.join(DATA_DIR, "receipts")
OUTCOMES_DIR = os.path.join(DATA_DIR, "outcomes")
os.makedirs(GOVERNANCE_DIR, exist_ok=True)
os.makedirs(DECISIONS_DIR, exist_ok=True)
os.makedirs(RECEIPTS_DIR, exist_ok=True)
os.makedirs(OUTCOMES_DIR, exist_ok=True)


# ─── Permission levels ──────────────────────────────────────────────────
PERM_READ = 0
PERM_RECOMMEND = 1
PERM_PREPARE = 2
PERM_LIMITED_AUTOPILOT = 3
PERM_HUMAN_ONLY = 4

PERM_LABELS = {
    PERM_READ: ("READ", "Read data"),
    PERM_RECOMMEND: ("RECOMMEND", "Create recommendations"),
    PERM_PREPARE: ("PREPARE", "Prepare changes (campaigns, budgets, bets) — but not execute"),
    PERM_LIMITED_AUTOPILOT: ("LIMITED AUTOPILOT", "Execute only actions covered by explicit rules"),
    PERM_HUMAN_ONLY: ("HUMAN ONLY", "Always requires approval"),
}

PERM_DESCRIPTIONS = {
    PERM_READ: "Inspect data only.",
    PERM_RECOMMEND: "Create recommendations and decision cards.",
    PERM_PREPARE: "Prepare: campaign changes, draft budgets, new bets, calendar changes, ad recommendations — but not execute them.",
    PERM_LIMITED_AUTOPILOT: "Execute only actions covered by explicit automation policies.",
    PERM_HUMAN_ONLY: "Always requires human approval. Use for: changing positioning, retiring a major market move, approving major spend increases, deleting strategic history, changing North Star, killing major campaigns.",
}


# ─── Action authority defaults ──────────────────────────────────────────
# Every action has a default minimum permission level required.
# Default: HUMAN ONLY for anything material.
ACTION_AUTHORITY = {
    # name → {perm_required, default_authority, reversible, affects_external}
    "PAUSE": {"perm_required": PERM_HUMAN_ONLY, "default_authority": "human", "reversible": True, "affects_external": True, "category": "operational"},
    "RESUME": {"perm_required": PERM_LIMITED_AUTOPILOT, "default_authority": "policy", "reversible": True, "affects_external": True, "category": "operational"},
    "HOLD": {"perm_required": PERM_LIMITED_AUTOPILOT, "default_authority": "policy", "reversible": True, "affects_external": False, "category": "internal"},
    "REDUCE_BUDGET": {"perm_required": PERM_HUMAN_ONLY, "default_authority": "human", "reversible": True, "affects_external": True, "category": "spend"},
    "INCREASE_BUDGET": {"perm_required": PERM_HUMAN_ONLY, "default_authority": "human", "reversible": True, "affects_external": True, "category": "spend"},
    "SCALE": {"perm_required": PERM_HUMAN_ONLY, "default_authority": "human", "reversible": True, "affects_external": True, "category": "spend"},
    "REFINE": {"perm_required": PERM_HUMAN_ONLY, "default_authority": "human", "reversible": True, "affects_external": True, "category": "strategic"},
    "KILL": {"perm_required": PERM_HUMAN_ONLY, "default_authority": "human", "reversible": False, "affects_external": True, "category": "strategic"},
    "RETIRE": {"perm_required": PERM_HUMAN_ONLY, "default_authority": "human", "reversible": False, "affects_external": True, "category": "strategic"},
    "APPROVE_BET": {"perm_required": PERM_HUMAN_ONLY, "default_authority": "human", "reversible": False, "affects_external": False, "category": "strategic"},
    "CHANGE_POSITIONING": {"perm_required": PERM_HUMAN_ONLY, "default_authority": "human", "reversible": False, "affects_external": False, "category": "strategic"},
    "CHANGE_NORTH_STAR": {"perm_required": PERM_HUMAN_ONLY, "default_authority": "human", "reversible": False, "affects_external": False, "category": "strategic"},
    "DELETE_HISTORY": {"perm_required": PERM_HUMAN_ONLY, "default_authority": "human", "reversible": False, "affects_external": False, "category": "destructive"},
    "LINK_TO_BET": {"perm_required": PERM_PREPARE, "default_authority": "recommend", "reversible": True, "affects_external": False, "category": "internal"},
    "FIX_MEASUREMENT": {"perm_required": PERM_PREPARE, "default_authority": "recommend", "reversible": False, "affects_external": True, "category": "measurement"},
}


# ─── Hierarchy ──────────────────────────────────────────────────────────
HIERARCHY = [
    "OBSERVE",
    "VALIDATE",
    "INTERPRET",
    "RECOMMEND",
    "HUMAN DECISION",
    "EXECUTE",
    "RECORD",
    "REVIEW OUTCOME",
]


# ─── Storage ────────────────────────────────────────────────────────────
def _policies_path(brand_id: str) -> str:
    return os.path.join(GOVERNANCE_DIR, f"{brand_id}.json")


def _receipts_path(brand_id: str) -> str:
    return os.path.join(RECEIPTS_DIR, f"{brand_id}.json")


def _outcomes_path(brand_id: str) -> str:
    return os.path.join(OUTCOMES_DIR, f"{brand_id}.json")


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def load_policies(brand_id: str) -> Dict[str, Any]:
    path = _policies_path(brand_id)
    if not os.path.isfile(path):
        return {"brand": brand_id, "policies": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"brand": brand_id, "policies": []}


def save_policies(brand_id: str, doc: Dict[str, Any]) -> None:
    with open(_policies_path(brand_id), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, default=str)


def load_receipts(brand_id: str) -> Dict[str, Any]:
    path = _receipts_path(brand_id)
    if not os.path.isfile(path):
        return {"brand": brand_id, "receipts": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"brand": brand_id, "receipts": []}


def save_receipts(brand_id: str, doc: Dict[str, Any]) -> None:
    with open(_receipts_path(brand_id), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, default=str)


def load_outcomes(brand_id: str) -> Dict[str, Any]:
    path = _outcomes_path(brand_id)
    if not os.path.isfile(path):
        return {"brand": brand_id, "outcomes": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"brand": brand_id, "outcomes": []}


def save_outcomes(brand_id: str, doc: Dict[str, Any]) -> None:
    with open(_outcomes_path(brand_id), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, default=str)


# ─── Permission check ───────────────────────────────────────────────────
def authority_required(action: str) -> Dict[str, Any]:
    """What level of authority is required to execute this action?"""
    if action not in ACTION_AUTHORITY:
        # Unknown action: require HUMAN ONLY by default
        return {
            "action": action,
            "mode": "HUMAN_ONLY",
            "reason": "Unknown action — human approval required.",
            "reversible": False,
            "perm_required": PERM_HUMAN_ONLY,
            "category": "unknown",
        }
    spec = ACTION_AUTHORITY[action]
    return {
        "action": action,
        "mode": "HUMAN_ONLY" if spec["default_authority"] == "human" else "POLICY_REQUIRED",
        "reason": (
            f"{action} requires human approval by default. Category: {spec['category']}. "
            f"Reversible: {spec['reversible']}. Affects external: {spec['affects_external']}."
        ),
        "reversible": spec["reversible"],
        "affects_external": spec["affects_external"],
        "perm_required": spec["perm_required"],
        "category": spec["category"],
    }


# ─── Automation Policies ────────────────────────────────────────────────
def add_policy(
    brand_id: str,
    *,
    rule: str,
    scope: str,
    action: str,
    expires: Optional[str] = None,
    notify: str = "immediately",
    description: Optional[str] = None,
    created_by: str = "christelle",
) -> Dict[str, Any]:
    """Add an explicit automation policy.

    Without a matching policy, the OS cannot auto-act.
    """
    spec = ACTION_AUTHORITY.get(action, {})
    if spec.get("perm_required", PERM_HUMAN_ONLY) == PERM_HUMAN_ONLY:
        # Even with a policy, certain actions cannot be authorised
        return {"ok": False, "error": f"{action} is HUMAN_ONLY and cannot be granted to an automation policy."}

    policy = {
        "id": str(uuid.uuid4())[:8],
        "rule": rule,
        "scope": scope,
        "action": action,
        "expires": expires,
        "notify": notify,
        "description": description or rule,
        "created_by": created_by,
        "created_at": _now_iso(),
        "status": "active",
    }
    doc = load_policies(brand_id)
    doc.setdefault("policies", []).append(policy)
    save_policies(brand_id, doc)
    return {"ok": True, "policy": policy}


def remove_policy(brand_id: str, policy_id: str) -> Dict[str, Any]:
    doc = load_policies(brand_id)
    before = len(doc.get("policies", []))
    doc["policies"] = [p for p in doc.get("policies", []) if p.get("id") != policy_id]
    save_policies(brand_id, doc)
    return {"ok": True, "removed": before - len(doc.get("policies", []))}


def find_matching_policy(brand_id: str, action: str, scope: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find an active policy that authorises this action.

    A policy matches if:
      - It's active
      - It's not expired
      - Its action equals the requested action
      - Its scope matches the requested scope (or has '*')
    """
    doc = load_policies(brand_id)
    now = _dt.datetime.now(_dt.timezone.utc)
    for p in doc.get("policies", []):
        if p.get("status") != "active":
            continue
        if p.get("action") != action:
            continue
        # Check expiry
        expires = p.get("expires")
        if expires:
            try:
                exp_d = _dt.datetime.fromisoformat(expires[:19])
                if exp_d < now:
                    continue
            except Exception:
                pass
        # Check scope
        pol_scope = p.get("scope", "")
        if pol_scope == "*" or pol_scope == scope:
            return p
        # Wildcard match
        if pol_scope.endswith("/*") and scope and scope.startswith(pol_scope[:-2]):
            return p
    return None


# ─── Authority check ────────────────────────────────────────────────────
def check_authority(
    brand_id: str,
    action: str,
    *,
    scope: Optional[str] = None,
    human_approved: bool = False,
) -> Dict[str, Any]:
    """Check whether the OS has authority to execute an action.

    Returns:
      {
        can_execute: bool,
        mode: 'human_approved' | 'policy_authorised' | 'blocked',
        reason: str,
        reversible: bool,
        authority_source: 'human' | 'policy' | None,
      }
    """
    spec = authority_required(action)
    # Human-only actions: require human_approved=True
    if spec.get("perm_required", PERM_HUMAN_ONLY) == PERM_HUMAN_ONLY:
        if human_approved:
            return {
                "can_execute": True,
                "mode": "human_approved",
                "reason": f"Action authorised by human approval.",
                "reversible": spec.get("reversible", False),
                "affects_external": spec.get("affects_external", True),
                "authority_source": "human",
                "policy": None,
            }
        return {
            "can_execute": False,
            "mode": "blocked",
            "reason": f"{action} requires explicit human approval. OS cannot auto-act.",
            "reversible": spec.get("reversible", False),
            "affects_external": spec.get("affects_external", True),
            "authority_source": None,
            "policy": None,
        }
    # POLICY_REQUIRED actions: need a matching active policy
    policy = find_matching_policy(brand_id, action, scope)
    if policy:
        return {
            "can_execute": True,
            "mode": "policy_authorised",
            "reason": f"Active automation policy '{policy.get('rule')}' authorises this action.",
            "reversible": spec.get("reversible", False),
            "affects_external": spec.get("affects_external", True),
            "authority_source": "policy",
            "policy": policy,
        }
    return {
        "can_execute": False,
        "mode": "blocked",
        "reason": f"{action} requires either human approval or an explicit automation policy. None found.",
        "reversible": spec.get("reversible", False),
        "affects_external": spec.get("affects_external", True),
        "authority_source": None,
        "policy": None,
    }


# ─── Approval Preview ───────────────────────────────────────────────────
def build_approval_preview(
    brand_id: str,
    decision_id: str,
    action: str,
) -> Dict[str, Any]:
    """Build the 'YOU ARE ABOUT TO' approval preview.

    Shows:
      - Action
      - Target (campaign / bet / move / etc.)
      - Current state (spend, evidence, etc.)
      - Effect
      - OS recommendation
      - Confidence
      - Authority source (human / policy / blocked)
    """
    # Lazy import to avoid circular
    try:
        from decision import build_decision_queue
        q = build_decision_queue(brand_id)
        card = next((c for c in q.get("queue", []) if c.get("id") == decision_id), None)
    except Exception:
        card = None

    spec = authority_required(action)
    policy = find_matching_policy(brand_id, action) if spec.get("perm_required") != PERM_HUMAN_ONLY else None

    target = "Unknown"
    current = {}
    if card:
        target = card.get("what")
        current = {
            "source": card.get("source"),
            "evidence": card.get("evidence", []),
            "boundary": card.get("boundary"),
            "cost_of_waiting": card.get("cost_of_waiting"),
        }
        ctx = card.get("context") or {}
        if "spend" in ctx:
            current["current_spend_rands"] = ctx["spend"]
        if "campaign_id" in ctx:
            current["campaign_id"] = ctx["campaign_id"]
        if "bet_id" in ctx:
            current["bet_id"] = ctx["bet_id"]

    effect = {
        "PAUSE": "Campaign will stop delivering immediately. Ads will pause. Spend will stop accruing.",
        "RESUME": "Campaign will resume delivering. Spend will start.",
        "REDUCE_BUDGET": "Budget will decrease. May reduce delivery volume. Reversible.",
        "INCREASE_BUDGET": "Budget will increase. May increase delivery volume. Reversible.",
        "SCALE": "Campaign/initiative will scale up. Spend will increase. Reversible.",
        "KILL": "Campaign will be permanently killed. This cannot be automatically reversed.",
        "RETIRE": "Strategy will be retired. This cannot be automatically reversed.",
        "CHANGE_POSITIONING": "Brand positioning will change. This cannot be automatically reversed.",
        "APPROVE_BET": "New bet will be approved and added to strategy.",
        "CHANGE_NORTH_STAR": "North Star statement will change. This cannot be automatically reversed.",
    }
    eff = effect.get(action, f"{action} will be applied. Outcome depends on context.")

    return {
        "action": action,
        "target": target,
        "current_state": current,
        "effect": eff,
        "os_recommendation": card.get("recommendation") if card else "N/A",
        "confidence": card.get("confidence") if card else "medium",
        "authority_required": spec,
        "matching_policy": policy,
        "reversible": spec.get("reversible", False),
        "actions_available": ["Approve action", "Cancel", "Open campaign"] if card else ["Approve action", "Cancel"],
        "preview_text": (
            f"YOU ARE ABOUT TO {action}: {target}. "
            f"Current state: {json.dumps(current, default=str)[:200]}. "
            f"Effect: {eff}. "
            f"OS recommendation: {card.get('recommendation') if card else 'N/A'}. "
            f"Confidence: {card.get('confidence') if card else 'medium'}. "
            f"Reversible: {spec.get('reversible', False)}. "
            f"Authority source: {'policy' if policy else 'human approval required'}."
        ),
    }


# ─── Execute with authority check ───────────────────────────────────────
def execute_decision(
    brand_id: str,
    decision_id: str,
    *,
    action: str,
    human_approved: bool,
    person: str = "christelle",
    reason: str = "",
    previous_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a decision through the full hierarchy.

    Hierarchy: VALIDATE → RECOMMEND → HUMAN DECISION → EXECUTE → RECORD
    Returns an action receipt if executed.
    """
    # 1. Validate authority
    auth = check_authority(brand_id, action, human_approved=human_approved)
    if not auth["can_execute"]:
        return {
            "ok": False,
            "mode": "blocked",
            "reason": auth["reason"],
            "authority_source": auth.get("authority_source"),
            "policy": auth.get("policy"),
        }

    # 2. Record the action receipt
    receipt = {
        "id": str(uuid.uuid4())[:8],
        "decision_id": decision_id,
        "action": action,
        "human_approved": human_approved,
        "authority_source": auth["authority_source"],
        "policy_id": (auth.get("policy") or {}).get("id"),
        "person": person,
        "reason": reason,
        "before_state": previous_state or {},
        "after_state": {},
        "executed_at": _now_iso(),
        "reversible": auth["reversible"],
        "reversed": False,
    }
    docs = load_receipts(brand_id)
    docs.setdefault("receipts", []).append(receipt)
    save_receipts(brand_id, docs)

    return {
        "ok": True,
        "mode": auth["mode"],
        "receipt": receipt,
        "authority_source": auth["authority_source"],
    }


# ─── Undo ───────────────────────────────────────────────────────────────
def undo_execution(brand_id: str, receipt_id: str, *, person: str = "christelle") -> Dict[str, Any]:
    """Undo a previously-executed action, if it was reversible."""
    docs = load_receipts(brand_id)
    receipt = next((r for r in docs.get("receipts", []) if r.get("id") == receipt_id), None)
    if not receipt:
        return {"ok": False, "error": "receipt not found"}
    if receipt.get("reversed"):
        return {"ok": False, "error": "already reversed"}
    if not receipt.get("reversible"):
        return {"ok": False, "error": "this action is irreversible and cannot be undone"}
    receipt["reversed"] = True
    receipt["reversed_by"] = person
    receipt["reversed_at"] = _now_iso()
    save_receipts(brand_id, docs)
    return {"ok": True, "receipt": receipt}


# ─── Conflict Detection ─────────────────────────────────────────────────
def detect_conflicts(brand_id: str) -> List[Dict[str, Any]]:
    """Detect when multiple OS subsystems recommend contradictory actions.

    Examples:
      - Advertising recommends SCALE Creative A
      - Portfolio says do not add more concentration
      - Strategy says TrackMan bet still immature

    Returns a list of conflict reports.
    """
    try:
        from decision import build_decision_queue
        queue = build_decision_queue(brand_id)
    except Exception:
        return []

    # Group decisions by target (bet_id, campaign_id, theme)
    by_target: Dict[str, List[Dict[str, Any]]] = {}
    for card in queue.get("queue", []):
        ctx = card.get("context") or {}
        target = ctx.get("bet_id") or ctx.get("theme") or "global"
        by_target.setdefault(target, []).append(card)

    conflicts: List[Dict[str, Any]] = []
    for target, cards in by_target.items():
        if len(cards) < 2:
            continue
        recs = [c.get("recommendation", "") for c in cards]
        # A conflict exists when recommendations disagree
        if len(set(recs)) > 1:
            # Find the action-level recommendations
            actions = set()
            for c in cards:
                r = c.get("recommendation", "").upper()
                if r in ("SCALE", "PAUSE", "KILL", "HOLD", "REFINE"):
                    actions.add(r)
            if "SCALE" in actions and ("PAUSE" in actions or "HOLD" in actions or "KILL" in actions):
                # SCALE vs PAUSE/HOLD/KILL = clear conflict
                conflicts.append({
                    "id": str(uuid.uuid4())[:8],
                    "target": target,
                    "subsystems": [c.get("source") for c in cards],
                    "recommendations": [(c.get("source"), c.get("recommendation"), c.get("what")) for c in cards],
                    "manager_read": (
                        "Multiple subsystems disagree on what to do with this bet. "
                        "The Decision Queue applies precedence: Data Integrity > Safety > "
                        "Strategic Decision > Portfolio > Commercial Evidence > Platform Efficiency. "
                        "Cheap efficiency never overrides strategic conflict."
                    ),
                    "recommended": "HOLD",
                    "confidence": "medium",
                    "precedence_applied": [
                        "1. DATA INTEGRITY",
                        "2. SAFETY / AUTHORITY",
                        "3. STRATEGIC DECISION",
                        "4. PORTFOLIO",
                        "5. COMMERCIAL EVIDENCE",
                        "6. PLATFORM EFFICIENCY",
                    ],
                })

    return conflicts


# ─── Decision Quality ───────────────────────────────────────────────────
def assess_decision_quality(
    brand_id: str,
    decision_id: str,
) -> Dict[str, Any]:
    """Score the decision-quality context for a specific decision card.

    Quality dimensions:
      - Data integrity healthy (data health score)
      - Evidence depth (which layers are valid)
      - Attribution confidence
      - Test maturity (age vs evidence)
      - Unresolved conflicts
      - Booking layer reach
    """
    try:
        from decision import build_decision_queue
        from integrity import data_health, measurement_debt, reconcile
        queue = build_decision_queue(brand_id)
        card = next((c for c in queue.get("queue", []) if c.get("id") == decision_id), None)
        if not card:
            return {"ok": False, "error": "decision not found"}

        # Pull integrity state
        integrity = reconcile(brand_id) or {}
        health = data_health(brand_id) or {}
        debt = measurement_debt(brand_id) or {}

        # Score
        scores = {}
        scores["data_integrity_healthy"] = health.get("score", 0) >= 70
        scores["booking_layer_reachable"] = (debt.get("layers", {}) or {}).get("bookings", {}).get("status") not in ("Broken", "Unavailable")
        scores["attribution_medium_or_high"] = (card.get("confidence") or "medium") in ("medium", "high")
        # Test maturity: if decision_date is set and within range
        dd = (card.get("context") or {}).get("decision_date")
        scores["test_mature"] = bool(dd)
        # Unresolved conflicts
        conflicts = detect_conflicts(brand_id)
        scores["no_unresolved_conflicts"] = not any(c.get("target") == (card.get("context") or {}).get("bet_id") for c in conflicts)

        strong_count = sum(1 for v in scores.values() if v)
        if strong_count >= 4:
            quality = "STRONG"
        elif strong_count >= 2:
            quality = "MODERATE"
        else:
            quality = "WEAK"

        return {
            "ok": True,
            "decision_id": decision_id,
            "quality": quality,
            "scores": scores,
            "strong_count": strong_count,
            "manager_read": (
                f"Decision quality: {quality}. "
                f"{strong_count}/5 dimensions satisfied. "
                + ("All key signals support a confident decision." if quality == "STRONG"
                   else "Some dimensions are weak — the OS will learn whether these decisions hold up."
                   if quality == "MODERATE"
                   else "Multiple dimensions are weak — this decision carries elevated uncertainty.")
            ),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Decision Outcome Review ────────────────────────────────────────────
def review_decision_outcome(brand_id: str, decision_id: str) -> Dict[str, Any]:
    """After a decision has been live for >= 14 days, compare actual
    outcomes to the original expectation.

    This creates a feedback loop so the OS learns whether decisions
    held up — not whether they were 'right' but whether they were
    supported by what happened.
    """
    try:
        from decision import load_decisions
        log = load_decisions(brand_id)
        history = log.get("history") or []
        entry = next((h for h in history if h.get("id") == decision_id), None)
        if not entry:
            return {"ok": False, "error": "decision not found in history"}

        decided_at = entry.get("decided_at")
        try:
            dt_decided = _dt.datetime.fromisoformat(decided_at[:19])
            dt_now = _dt.datetime.now(_dt.timezone.utc)
            days_elapsed = (dt_now - dt_decided).days
        except Exception:
            days_elapsed = 0

        if days_elapsed < 14:
            return {
                "ok": True,
                "ready": False,
                "days_elapsed": days_elapsed,
                "message": f"Outcome review ready after 14 days. {14 - days_elapsed} days remaining.",
            }

        # Compare actual outcome
        # In a real system this would pull spend, clicks, visits, etc.
        # For now we record the review and let the human compare.
        review = {
            "decision_id": decision_id,
            "decided_at": decided_at,
            "days_elapsed": days_elapsed,
            "original_decision": entry.get("decision"),
            "original_recommendation": entry.get("os_recommendation"),
            "reviewed_at": _now_iso(),
            "status": "ready_for_review",
            "verdict": None,  # Human completes this
        }
        docs = load_outcomes(brand_id)
        # Don't double-record
        docs["outcomes"] = [o for o in docs.get("outcomes", []) if o.get("decision_id") != decision_id]
        docs["outcomes"].append(review)
        save_outcomes(brand_id, docs)

        return {
            "ok": True,
            "ready": True,
            "review": review,
            "message": "Outcome review is ready. Manager reads actual vs expected and marks supported / reconsider.",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def mark_outcome(brand_id: str, decision_id: str, verdict: str, notes: str = "") -> Dict[str, Any]:
    """Human records the actual outcome of a previously-decided bet.

    verdicts:
      - 'evidence_supports': actual matched expectation
      - 'reconsider': actual diverged, decision may need revisiting
      - 'mixed': some supported, some did not
    """
    docs = load_outcomes(brand_id)
    review = next((o for o in docs.get("outcomes", []) if o.get("decision_id") == decision_id), None)
    if not review:
        return {"ok": False, "error": "outcome review not started yet"}
    review["verdict"] = verdict
    review["notes"] = notes
    review["marked_at"] = _now_iso()
    save_outcomes(brand_id, docs)

    # If the human disagreed and it proved correct, log it as learning
    if verdict == "evidence_supports":
        try:
            from decision import load_decisions
            log = load_decisions(brand_id)
            history = log.get("history") or []
            entry = next((h for h in history if h.get("id") == decision_id), None)
            if entry and entry.get("decision") == "DISAGREE":
                # Log learning
                docs_out = load_outcomes(brand_id)
                docs_out.setdefault("disagreement_lessons", []).append({
                    "decision_id": decision_id,
                    "what": entry.get("what"),
                    "human_choice": (entry.get("context") or {}).get("chosen_action"),
                    "outcome_verdict": verdict,
                    "notes": notes,
                    "logged_at": _now_iso(),
                    "learning": "Human context unavailable to the model materially affected this decision.",
                })
                save_outcomes(brand_id, docs_out)
        except Exception:
            pass

    return {"ok": True, "review": review}


# ─── Governance Status ──────────────────────────────────────────────────
def governance_status(brand_id: str) -> Dict[str, Any]:
    """Snapshot of the OS authority model for the brand."""
    policies = load_policies(brand_id).get("policies", [])
    active_policies = [p for p in policies if p.get("status") == "active"]
    receipts = load_receipts(brand_id).get("receipts", [])
    outcomes = load_outcomes(brand_id).get("outcomes", [])
    conflicts = detect_conflicts(brand_id)

    return {
        "brand": brand_id,
        "authority_model": {
            "observe": {"default": "automatic", "label": "Observe"},
            "analyse": {"default": "automatic", "label": "Analyse"},
            "recommend": {"default": "automatic", "label": "Recommend"},
            "prepare": {"default": "automatic", "label": "Prepare actions"},
            "execute": {
                "default": "human_approval",
                "label": "Execute spend/strategy changes",
                "icon": "🔒",
            },
        },
        "hierarchy": HIERARCHY,
        "permission_levels": [
            {"level": k, "label": v[0], "description": v[1]}
            for k, v in sorted(PERM_LABELS.items())
        ],
        "action_authority_defaults": ACTION_AUTHORITY,
        "active_policies_count": len(active_policies),
        "active_policies": active_policies,
        "receipts_count": len(receipts),
        "outcomes_recorded": len(outcomes),
        "conflicts_detected": len(conflicts),
        "generated_at": _now_iso(),
    }