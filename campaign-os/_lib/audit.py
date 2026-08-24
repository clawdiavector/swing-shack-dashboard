"""
audit.py — Full audit layer for Campaign OS.

The audit is the immune system. It walks every item in the OS — every
campaign, bet, market move, content idea, recurring theme, lesson,
SEO opportunity, evergreen post, draft hook, ad — and asks six
questions:

  1. Is it current?
  2. Does it still support strategy?
  3. Has it actually worked?
  4. Has the idea been overused?
  5. Is there a better version now?
  6. What should happen next?

Each item gets:
  - An audit_status: keep | update | scale | retest | pause | retire | delete
  - An audit_score: 0-100
  - A reason_for_existence: free-text "Why is this still here?"
  - A next_action: one concrete thing to do

Audit decisions flow into strategic memory as lessons. Retired
items stay searchable in history with their reason.

The audit runs:
  - Monthly (full, heavy cron)
  - On Monday morning (light, only items that changed)
  - On demand (whenever Christelle asks "why is this still here?")
"""

from __future__ import annotations

import json
import os
import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict
from collections import defaultdict

import sys
HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE))

from strategy_store import (
    load_strategy,
    save_strategy,
    load_trend,
    upsert_lesson,
    get_decision_queue,
    compute_strategy_density,
)

AUDIT_STATUSES = ["keep", "update", "scale", "retest", "pause", "retire", "delete"]

# Status → concrete next action
STATUS_ACTIONS = {
    "keep": "Run unchanged — re-audit in 30 days.",
    "update": "Rewrite before next use — facts/offer/creative/positioning changed.",
    "scale": "Add three new executions next month.",
    "retest": "Try again with a new hook, audience, or angle.",
    "pause": "Remove from active calendar for 60 days.",
    "retire": "Remove from current strategy. Keep historical record.",
    "delete": "Pure clutter — remove entirely.",
}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


# ─── Item discovery ──────────────────────────────────────────────────

def discover_all_items(brand_id: str = "swing-shack") -> List[Dict[str, Any]]:
    """Walk every item in the OS: market moves, bets, campaigns,
    recurring themes, content ideas, lessons. Returns a flat list
    of dicts with {item_id, item_type, item, meta} for auditing."""
    s = load_strategy(brand_id)
    items = []

    # Market moves
    for m in s.get("market_moves", []):
        items.append({
            "item_id": m["id"],
            "item_type": "market_move",
            "title": m.get("title", ""),
            "workhorse": m.get("workhorse", "marketing"),
            "status": m.get("status", ""),
            "horizon": m.get("horizon", "year"),
            "created_at": m.get("created_at") or m.get("updated_at"),
            "updated_at": m.get("updated_at"),
            "links_to_market_move": None,
            "campaign_id": m.get("campaign_id"),
            "evidence_for": m.get("evidence_for", []),
            "evidence_against": m.get("evidence_against", []),
            "milestones": m.get("milestones", []),
            "raw": m,
        })

    # Bets
    for b in s.get("bets", []):
        items.append({
            "item_id": b["id"],
            "item_type": "bet",
            "title": b.get("title", ""),
            "workhorse": b.get("workhorse", "marketing"),
            "status": b.get("status", ""),
            "horizon": b.get("horizon", "quarter"),
            "created_at": b.get("created_at") or b.get("updated_at"),
            "updated_at": b.get("updated_at"),
            "links_to_market_move": b.get("links_to_market_move"),
            "campaign_id": b.get("campaign_id"),
            "evidence": b.get("evidence", []),
            "milestones": b.get("milestones", []),
            "execution_log": b.get("execution_log", []),
            "content_themes": b.get("content_themes", []),
            "experiments": b.get("experiments", []),
            "watch_metrics": b.get("watch_metrics", []),
            "start_date": b.get("start_date"),
            "target_end_date": b.get("target_end_date"),
            "review_date": b.get("review_date"),
            "decision_date": b.get("decision_date"),
            "decision": b.get("decision"),
            "raw": b,
        })

    # Campaigns (from campaign-data.json)
    cd = _load_campaign_data()
    if isinstance(cd, dict):
        for cid, c in cd.get("campaigns", {}).items():
            identity = c.get("identity", {}) or {}
            items.append({
                "item_id": cid,
                "item_type": "campaign",
                "title": identity.get("name", cid),
                "workhorse": identity.get("workhorse", "marketing"),
                "status": identity.get("status", ""),
                "horizon": identity.get("horizon", "quarter"),
                "created_at": identity.get("createdAt"),
                "updated_at": identity.get("updatedAt"),
                "links_to_market_move": None,
                "campaign_id": cid,
                "raw": c,
            })

    # Recurring content themes (from campaign-data.json recurringThemes)
    if isinstance(cd, dict):
        for theme_id, theme in (cd.get("recurringThemes") or {}).items():
            items.append({
                "item_id": theme_id,
                "item_type": "recurring_theme",
                "title": theme.get("name", theme_id),
                "workhorse": theme.get("workhorse", "marketing"),
                "status": "active",
                "horizon": "evergreen",
                "created_at": theme.get("createdAt"),
                "raw": theme,
            })

    # Content ideas (campaign-data.json ideas array)
    if isinstance(cd, dict):
        for i, idea in enumerate(cd.get("ideas") or []):
            items.append({
                "item_id": f"idea-{i}",
                "item_type": "content_idea",
                "title": idea.get("title", f"Idea #{i}"),
                "workhorse": idea.get("workhorse", "marketing"),
                "status": idea.get("status", "draft"),
                "horizon": "idea",
                "created_at": idea.get("createdAt"),
                "raw": idea,
            })

    # Lessons (treated as items too — they need to be acted on or retired)
    for l in s.get("lessons", []):
        items.append({
            "item_id": l["id"],
            "item_type": "lesson",
            "title": l.get("claim", "")[:100],
            "workhorse": l.get("workhorse", "marketing"),
            "status": "acted_on" if l.get("promoted_to_bet_id") else ("invalid" if not l.get("still_valid", True) else "active"),
            "horizon": "evergreen",
            "created_at": l.get("learned_at"),
            "raw": l,
        })

    return items


def _load_campaign_data() -> Optional[dict]:
    """Load campaign-data.json from either runtime or bundled locations."""
    for path_str in [
        os.environ.get("DATA_DIR", "") + "/campaign-data.json",
        str(Path(__file__).resolve().parents[2] / "data" / "campaign-data.json"),
    ]:
        if not path_str or path_str == "/campaign-data.json":
            continue
        try:
            with open(path_str) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
    return None


# ─── 6-question audit per item ──────────────────────────────────────

def audit_item(item: Dict[str, Any], brand_id: str = "swing-shack") -> Dict[str, Any]:
    """Run the 6-question audit on a single item. Returns:
      {
        'item_id', 'item_type', 'title',
        'audit_status': one of 7 buckets,
        'audit_score': 0-100,
        'answers': {q1: ..., q2: ..., q3: ..., q4: ..., q5: ..., q6: ...},
        'reason_for_existence': str,
        'next_action': str,
        'flags': [list of issues found]
      }
    """
    answers = {}
    flags = []

    # ── Q1: Is it current? ──────────────────────────────────────
    q1 = _check_currency(item)
    answers["current"] = q1
    if q1.get("stale"):
        flags.append({"code": q1.get("stale_code"), "detail": q1.get("reason")})

    # ── Q2: Does it still support strategy? ────────────────────
    q2 = _check_strategy_support(item, brand_id)
    answers["strategy_support"] = q2
    if not q2.get("supports_strategy"):
        flags.append({"code": "orphaned_activity", "detail": q2.get("reason")})

    # ── Q3: Has it actually worked? ────────────────────────────
    q3 = _check_performance(item, brand_id)
    answers["performance"] = q3
    if q3.get("underperforms"):
        flags.append({"code": "underperforms", "detail": q3.get("reason")})

    # ── Q4: Has the idea been overused? ────────────────────────
    q4 = _check_fatigue(item, brand_id)
    answers["fatigue"] = q4
    if q4.get("fatigued"):
        flags.append({"code": q4.get("fatigue_type"), "detail": q4.get("reason")})

    # ── Q5: Is there a better version now? ─────────────────────
    q5 = _check_better_version(item, brand_id)
    answers["better_version"] = q5
    if q5.get("newer_better"):
        flags.append({"code": "newer_better_available", "detail": q5.get("reason")})

    # ── Q6: What should happen next? ───────────────────────────
    q6 = _classify_and_score(item, answers, flags)
    answers["classification"] = q6

    audit_status = q6["audit_status"]
    audit_score = q6["audit_score"]

    return {
        "item_id": item["item_id"],
        "item_type": item["item_type"],
        "title": item["title"],
        "workhorse": item.get("workhorse", "marketing"),
        "audit_status": audit_status,
        "audit_score": audit_score,
        "answers": answers,
        "reason_for_existence": q6.get("reason_for_existence", ""),
        "next_action": STATUS_ACTIONS.get(audit_status, ""),
        "flags": flags,
        "audited_at": _now_iso(),
    }


def _check_currency(item: Dict[str, Any]) -> Dict[str, Any]:
    """Q1: Is the item current? Check dates, seasonality, expired offers."""
    today = datetime.date.today()
    title_lower = (item.get("title") or "").lower()
    stale = False
    stale_code = None
    reason = ""

    # Seasonal check — common SA + golf season patterns
    seasonal_keywords = {
        "winter": {"months": {6, 7, 8}, "expired_months": {9, 10, 11, 12, 1, 2, 3, 4, 5}},
        "summer": {"months": {12, 1, 2}, "expired_months": {3, 4, 5, 6, 7, 8, 9, 10, 11}},
        "festive": {"months": {11, 12}, "expired_months": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}},
        "spring": {"months": {9, 10, 11}, "expired_months": {12, 1, 2, 3, 4, 5, 6, 7, 8}},
        "back-to-school": {"months": {1, 2}, "expired_months": set(range(3, 13))},
        "valentine": {"months": {2}, "expired_months": set(range(3, 13)) | {1}},
        "easter": {"months": {3, 4}, "expired_months": set(range(5, 13)) | {1, 2}},
        "mothers-day": {"months": {5}, "expired_months": set(range(6, 13)) | set(range(1, 5))},
    }

    for keyword, ranges in seasonal_keywords.items():
        if keyword in title_lower:
            if today.month in ranges["expired_months"]:
                stale = True
                stale_code = "seasonal_expired"
                reason = f"Seasonal '{keyword}' window passed (today is {today.strftime('%B')})."
            elif today.month in ranges["months"]:
                reason = f"In active '{keyword}' window."
            break

    # End-date check
    end_str = item.get("target_end_date") or item.get("end_date")
    if end_str:
        try:
            end_d = datetime.date.fromisoformat(end_str[:10])
            if end_d < today - datetime.timedelta(days=30):
                stale = True
                stale_code = stale_code or "ended_over_30d"
                reason = reason or f"End date {end_d.isoformat()} was over 30 days ago."
        except (ValueError, TypeError):
            pass

    return {"stale": stale, "stale_code": stale_code, "reason": reason, "current_month": today.month}


def _check_strategy_support(item: Dict[str, Any], brand_id: str) -> Dict[str, Any]:
    """Q2: Does the item still support strategy? Link to North Star → Move → Bet."""
    s = load_strategy(brand_id)
    supports_strategy = False
    reason = ""
    chain = []

    # Items directly linked to a market move
    if item.get("links_to_market_move"):
        move = next((m for m in s.get("market_moves", []) if m["id"] == item["links_to_market_move"]), None)
        if move:
            supports_strategy = True
            chain.append(f"Move: {move['title']}")
            chain.append("↓")
            chain.append(f"Bet: {item.get('title', '')}")
            reason = f"Directly supports market move '{move['title']}'."

    # Items that are market moves
    elif item["item_type"] == "market_move":
        supports_strategy = True
        chain.append(f"Move: {item.get('title', '')}")
        reason = "This IS a market move."

    # Items that are campaigns linked to a bet
    elif item["item_type"] == "campaign":
        # Find a bet that references this campaign
        linked_bet = next((b for b in s.get("bets", []) if b.get("campaign_id") == item["item_id"]), None)
        if linked_bet:
            supports_strategy = True
            move = next((m for m in s.get("market_moves", []) if m["id"] == linked_bet.get("links_to_market_move")), None)
            if move:
                chain.append(f"Move: {move['title']}")
                chain.append("↓")
                chain.append(f"Bet: {linked_bet['title']}")
                chain.append("↓")
                chain.append(f"Campaign: {item.get('title', '')}")
                reason = f"Linked to bet '{linked_bet['title']}' under move '{move['title']}'."
            else:
                chain.append(f"Bet: {linked_bet['title']}")
                chain.append("↓")
                chain.append(f"Campaign: {item.get('title', '')}")
                reason = f"Linked to bet '{linked_bet['title']}'."
        else:
            # Check if any bet references it via title
            title_lower = (item.get("title") or "").lower().split()[0]
            loose_match = next((b for b in s.get("bets", []) if title_lower and title_lower in (b.get("title") or "").lower()), None)
            if loose_match:
                supports_strategy = True
                chain.append(f"Bet: {loose_match['title']}")
                chain.append("↓")
                chain.append(f"Campaign: {item.get('title', '')}")
                reason = f"Likely linked to bet '{loose_match['title']}' (loose match)."

    # Items that are recurring themes — check if any active bet covers them
    elif item["item_type"] == "recurring_theme":
        theme_words = set((item.get("title") or "").lower().split())
        for b in s.get("bets", []):
            themes = set()
            for t in (b.get("content_themes") or []):
                themes.update(t.lower().split())
            if theme_words & themes:
                supports_strategy = True
                chain.append(f"Bet: {b['title']}")
                chain.append("↓")
                chain.append(f"Theme: {item.get('title', '')}")
                reason = f"Theme overlaps with bet '{b['title']}' content themes."
                break

    # Items that are content ideas
    elif item["item_type"] == "content_idea":
        supports_strategy = True  # ideas are by definition pre-strategy
        chain.append(f"Idea: {item.get('title', '')}")
        reason = "Pre-strategy idea — needs review before commitment."

    # Items that are lessons
    elif item["item_type"] == "lesson":
        supports_strategy = True
        chain.append(f"Lesson: {item.get('title', '')}")
        reason = "Strategic memory — feeds future strategy."

    if not supports_strategy and not reason:
        reason = "Could not find a strategic chain linking this item to a market move or bet."

    return {"supports_strategy": supports_strategy, "reason": reason, "chain": chain}


def _check_performance(item: Dict[str, Any], brand_id: str) -> Dict[str, Any]:
    """Q3: Has it actually worked? Pull real performance data and compare."""
    s = load_strategy(brand_id)
    underperforms = False
    reason = ""
    metrics = {}

    # Items with explicit evidence arrays
    evidence_for = item.get("evidence_for", [])
    evidence = item.get("evidence", [])

    if evidence_for or evidence:
        # Look at the trend snapshots for this item
        trend = load_trend(brand_id)
        snapshots = trend.get("snapshots", [])
        key = "moves" if item["item_type"] == "market_move" else "bets"
        item_id = item["item_id"]
        recent = [s for s in snapshots if item_id in s.get(key, {})]
        if recent:
            latest = recent[-1]
            ev_for = latest.get(key, {}).get(item_id, {}).get("evidence_for", 0)
            ev_against = latest.get(key, {}).get(item_id, {}).get("evidence_against", 0)
            net = ev_for - ev_against
            metrics["evidence_for_recent"] = ev_for
            metrics["evidence_against_recent"] = ev_against
            metrics["net"] = net
            if net <= -3:
                underperforms = True
                reason = f"Evidence net is {net} (≥3 against). Hypothesis is failing."

    # Bet-specific: check execution log for missed entries
    if item["item_type"] == "bet":
        log = item.get("execution_log", [])
        if log:
            misses = sum(1 for e in log if e.get("delta") == "missed")
            total = len(log)
            if total >= 3 and misses / total >= 0.6:
                underperforms = True
                reason = f"{misses}/{total} executions missed. Execution failing."

    # Lesson-specific: lessons acted on are useful; unacted lessons are noise
    if item["item_type"] == "lesson":
        if item.get("status") == "active" and not item.get("raw", {}).get("promoted_to_bet_id"):
            # Lesson has been around for >90 days with no action
            learned_at = item.get("created_at") or item.get("raw", {}).get("learned_at")
            if learned_at:
                try:
                    learned_d = datetime.date.fromisoformat(learned_at[:10])
                    if (datetime.date.today() - learned_d).days > 90:
                        underperforms = True
                        reason = f"Lesson learned {learned_at}, not yet acted on after 90 days."
                except (ValueError, TypeError):
                    pass

    return {"underperforms": underperforms, "reason": reason, "metrics": metrics}


def _check_fatigue(item: Dict[str, Any], brand_id: str) -> Dict[str, Any]:
    """Q4: Has the idea been overused? Detect repetition."""
    fatigued = False
    fatigue_type = None
    reason = ""

    # Recurring themes: check if any content_themes overlap heavily across multiple bets
    if item["item_type"] == "recurring_theme":
        s = load_strategy(brand_id)
        theme_lower = (item.get("title") or "").lower()
        similar = []
        for b in s.get("bets", []):
            for t in (b.get("content_themes") or []):
                if theme_lower in t.lower() or t.lower() in theme_lower:
                    similar.append(b["title"])
        if len(similar) >= 3:
            fatigued = True
            fatigue_type = "message_fatigue"
            reason = f"Theme appears across {len(similar)} bets: {', '.join(similar[:3])}. Risk of repetition."

    # Content ideas: similar titles → potential duplication
    if item["item_type"] == "content_idea":
        cd = _load_campaign_data()
        if isinstance(cd, dict):
            title_words = set((item.get("title") or "").lower().split())
            similar = []
            for other in cd.get("ideas") or []:
                if other is item.get("raw"):
                    continue
                other_words = set((other.get("title") or "").lower().split())
                if title_words and other_words:
                    overlap = len(title_words & other_words) / max(len(title_words | other_words), 1)
                    if overlap >= 0.5:
                        similar.append(other.get("title", ""))
            if len(similar) >= 2:
                fatigued = True
                fatigue_type = "creative_fatigue"
                reason = f"Similar ideas exist: {', '.join(similar[:2])}"

    # Bets: check if multiple active bets share the same campaign or KPI
    if item["item_type"] == "bet":
        s = load_strategy(brand_id)
        same_kpi = [b for b in s.get("bets", []) if b.get("id") != item["item_id"] and b.get("primary_kpi") == item.get("primary_kpi") and b.get("status") == "in_flight"]
        if len(same_kpi) >= 2:
            fatigued = True
            fatigue_type = "kpi_overlap"
            reason = f"{len(same_kpi) + 1} active bets share the KPI '{item.get('primary_kpi')}'."

    return {"fatigued": fatigued, "fatigue_type": fatigue_type, "reason": reason}


def _check_better_version(item: Dict[str, Any], brand_id: str) -> Dict[str, Any]:
    """Q5: Is there a better version now? Compare to newer evidence / ideas."""
    s = load_strategy(brand_id)
    newer_better = False
    reason = ""

    # Lessons in category 'worked' suggest a newer/better pattern
    if item["item_type"] == "recurring_theme":
        worked_lessons = [l for l in s.get("lessons", []) if l.get("category") == "worked" and l.get("still_valid", True)]
        for lesson in worked_lessons:
            claim_lower = (lesson.get("claim") or "").lower()
            theme_lower = (item.get("title") or "").lower()
            if any(word in claim_lower for word in theme_lower.split() if len(word) > 3):
                newer_better = True
                reason = f"Lesson ('{claim_lower[:80]}…') suggests newer approach for this theme."
                break

    # Bets with disproved status vs lessons that propose alternatives
    if item["item_type"] == "bet":
        if item.get("status") in ("lost", "killed"):
            disproved = [l for l in s.get("lessons", []) if l.get("category") == "disproved" and l.get("from_bet") == item["item_id"]]
            if disproved:
                newer_better = True
                reason = f"Lesson says: {disproved[-1].get('claim', '')[:120]}"

    # Campaigns superseded by newer campaigns (same audience, newer date)
    if item["item_type"] == "campaign":
        cd = _load_campaign_data()
        if isinstance(cd, dict):
            identity = (item.get("raw") or {}).get("identity", {}) or {}
            goal = (identity.get("goal") or "").lower()
            target_audience = (identity.get("targetAudience") or "").lower()
            newer_similar = []
            for cid, c in cd.get("campaigns", {}).items():
                if cid == item["item_id"]:
                    continue
                c_identity = (c.get("identity") or {})
                c_goal = (c_identity.get("goal") or "").lower()
                c_audience = (c_identity.get("targetAudience") or "").lower()
                c_created = c_identity.get("createdAt") or ""
                item_created = identity.get("createdAt") or ""
                if c_created > item_created and (
                    (goal and any(word in c_goal for word in goal.split() if len(word) > 4))
                    or (target_audience and target_audience in c_audience)
                ):
                    newer_similar.append(c_identity.get("name", cid))
            if newer_similar:
                newer_better = True
                reason = f"Newer campaign(s) target same audience: {', '.join(newer_similar[:2])}"

    return {"newer_better": newer_better, "reason": reason}


def _classify_and_score(item: Dict[str, Any], answers: Dict[str, Any], flags: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Q6: Classify into one of 7 buckets + score 0-100."""
    score = 100
    status = "keep"

    # Penalties
    if answers["current"].get("stale"):
        score -= 40
        status = "retire"
    if not answers["strategy_support"].get("supports_strategy"):
        score -= 30
        if status == "keep":
            status = "retire"
    if answers["performance"].get("underperforms"):
        score -= 25
        if status in ("keep", "scale"):
            status = "pause"
    if answers["fatigue"].get("fatigued"):
        score -= 15
        if status == "keep":
            status = "update"
    if answers["better_version"].get("newer_better"):
        score -= 10
        if status in ("keep", "scale"):
            status = "update"

    # Bonuses — proven performers get a boost
    perf = answers["performance"].get("metrics", {})
    if isinstance(perf, dict) and perf.get("net", 0) >= 3:
        score += 5
        if status == "keep" and not answers["fatigue"].get("fatigued"):
            status = "scale"

    # Lessons that have been acted on are good (closed loop)
    if item["item_type"] == "lesson":
        if item.get("raw", {}).get("promoted_to_bet_id"):
            score = min(score + 5, 100)
            status = "keep"

    # Bets with decisions are 'closed'
    if item["item_type"] == "bet" and item.get("decision"):
        score = max(score, 80)  # Decisions are valuable
        if item["decision"].get("outcome") in ("scale",):
            status = "scale"
        elif item["decision"].get("outcome") == "kill":
            status = "retire"

    # Items explicitly retired by user
    if item.get("status") in ("retired",):
        status = "retire"
        score = min(score, 30)

    # Clamp
    score = max(0, min(100, score))

    reason_for_existence = _build_reason_for_existence(item, answers)

    return {
        "audit_status": status,
        "audit_score": score,
        "reason_for_existence": reason_for_existence,
    }


def _build_reason_for_existence(item: Dict[str, Any], answers: Dict[str, Any]) -> str:
    """Build the 'why is this still here?' answer. Bullet list of reasons."""
    reasons = []
    s = load_strategy(item.get("_brand_id", "swing-shack"))

    chain = answers["strategy_support"].get("chain", [])
    if chain:
        reasons.append("→ ".join(chain))

    perf = answers["performance"].get("metrics", {})
    if isinstance(perf, dict) and perf.get("net", 0) > 0:
        reasons.append(f"{perf['net']} net pieces of evidence (for > against)")

    if answers["strategy_support"].get("supports_strategy"):
        ss = answers["strategy_support"].get("reason", "")
        if ss and ss not in reasons:
            reasons.append(ss)

    if item.get("execution_log"):
        recent_exec = [e for e in item["execution_log"] if (e.get("date") or "") >= (datetime.date.today() - datetime.timedelta(days=30)).isoformat()]
        if recent_exec:
            matched = sum(1 for e in recent_exec if e.get("delta") == "matched")
            reasons.append(f"{matched}/{len(recent_exec)} recent executions matched plan")

    if item.get("decision"):
        d = item["decision"]
        reasons.append(f"Decision: {d.get('outcome', '').upper()} on {d.get('decided_at', '')}")

    if not reasons:
        reasons.append("⚠ No strong reason to keep this active. Recommended: RETIRE.")

    return " · ".join(reasons)


# ─── Audit runner ─────────────────────────────────────────────────────

def run_audit(brand_id: str = "swing-shack", light: bool = False) -> Dict[str, Any]:
    """Run the audit on every item. Light mode skips heavy checks for Monday brief speed."""
    items = discover_all_items(brand_id)
    audited = []
    for item in items:
        result = audit_item(item, brand_id)
        audited.append(result)

    # Sort by score (worst first for visibility)
    audited.sort(key=lambda a: (a["audit_score"], a["item_type"]))

    # Classify summary
    by_status = defaultdict(list)
    for a in audited:
        by_status[a["audit_status"]].append(a)

    # Clutter report
    clutter = _build_clutter_report(audited, brand_id)

    # Items needing attention (top issues)
    needs_cleaning = []
    for a in audited:
        if a["audit_status"] in ("retire", "delete", "pause"):
            needs_cleaning.append({
                "item_id": a["item_id"],
                "item_type": a["item_type"],
                "title": a["title"],
                "audit_status": a["audit_status"],
                "audit_score": a["audit_score"],
                "reason": a["reason_for_existence"],
                "next_action": a["next_action"],
            })

    return {
        "brand_id": brand_id,
        "audit_date": _today(),
        "light_mode": light,
        "total_items": len(audited),
        "by_status": {k: len(v) for k, v in by_status.items()},
        "items": audited,
        "needs_cleaning": needs_cleaning[:3] if light else needs_cleaning,
        "clutter_report": clutter,
    }


def _build_clutter_report(audited: List[Dict[str, Any]], brand_id: str) -> Dict[str, Any]:
    """Categorise the audit results for the monthly STRATEGY CLUTTER REPORT."""
    total = len(audited)
    if total == 0:
        return {"total": 0, "linked": 0, "orphaned": 0, "stale_90d": 0,
                "duplicates": 0, "seasonal_expired": 0, "valid": 0,
                "recommendations": []}

    linked = sum(1 for a in audited if "→" in a["reason_for_existence"])
    orphaned = sum(1 for a in audited if a["audit_status"] == "retire" and "No strong reason" in a["reason_for_existence"])
    stale_90d = sum(1 for a in audited if a["audit_score"] < 30)
    duplicates = sum(1 for a in audited if any(f.get("code") in ("creative_fatigue", "message_fatigue", "kpi_overlap") for f in a.get("flags", [])))
    seasonal_expired = sum(1 for a in audited if any(f.get("code") == "seasonal_expired" for f in a.get("flags", [])))
    valid = sum(1 for a in audited if a["audit_status"] == "keep")

    # Recommendations
    recommendations = []
    if orphaned > 0:
        recommendations.append(f"Retire {orphaned} orphaned items — no strategic chain.")
    if duplicates > 0:
        recommendations.append(f"Resolve {duplicates} duplicates — pick the strongest version.")
    if seasonal_expired > 0:
        recommendations.append(f"Retire {seasonal_expired} expired seasonal items.")
    if stale_90d > 5:
        recommendations.append(f"{stale_90d} items score <30/100 — review for clean-up.")
    if not recommendations:
        recommendations.append("Strategy is clean. No clean-up required.")

    return {
        "total": total,
        "linked_to_strategy": linked,
        "orphaned": orphaned,
        "stale_or_low_score": stale_90d,
        "duplicates": duplicates,
        "seasonal_expired": seasonal_expired,
        "valid_keep": valid,
        "recommendations": recommendations,
    }


# ─── Why is this still here? ────────────────────────────────────────

def why_still_here(item_type: str, item_id: str, brand_id: str = "swing-shack") -> Dict[str, Any]:
    """One-shot answer to 'Why is this still here?' for a single item."""
    items = discover_all_items(brand_id)
    item = next((i for i in items if i["item_id"] == item_id and i["item_type"] == item_type), None)
    if not item:
        return {"ok": False, "error": "item not found"}
    result = audit_item(item, brand_id)
    return {
        "ok": True,
        "item": {"id": item_id, "type": item_type, "title": item["title"]},
        "audit_status": result["audit_status"],
        "audit_score": result["audit_score"],
        "reason_for_existence": result["reason_for_existence"],
        "next_action": result["next_action"],
        "flags": result["flags"],
    }


# ─── Audit decision → strategic memory ──────────────────────────────

def record_audit_decision(item_type: str, item_id: str, decision: str, note: str, brand_id: str = "swing-shack") -> Dict[str, Any]:
    """Record a KEEP/UPDATE/PAUSE/RETIRE/DELETE decision. Writes to strategic memory."""
    if decision not in AUDIT_STATUSES:
        raise ValueError(f"decision must be one of {AUDIT_STATUSES}")
    items = discover_all_items(brand_id)
    item = next((i for i in items if i["item_id"] == item_id and i["item_type"] == item_type), None)
    if not item:
        raise ValueError(f"item {item_type}/{item_id} not found")

    audit_decision = {
        "item_type": item_type,
        "item_id": item_id,
        "title": item["title"],
        "decision": decision,
        "note": note,
        "decided_at": _today(),
    }

    # Map audit decisions to lesson categories
    lesson_category_map = {
        "keep": None,            # don't pollute lessons
        "update": "data_suggests_test_next",
        "scale": "worked",
        "retest": "retry_with_different_approach",
        "pause": "underperformed",
        "retire": "disproved",
        "delete": "disproved",
    }

    s = load_strategy(brand_id)

    # Append to strategy's audit_decisions history
    s.setdefault("audit_decisions", []).append(audit_decision)
    save_strategy(s, brand_id)

    # If retire/pause/update, create a lesson for strategic memory
    cat = lesson_category_map[decision]
    if cat:
        lesson = {
            "category": cat,
            "claim": f"Audit decision on '{item['title']}': {decision.upper()}. {note}".strip(),
            "evidence": [{
                "source": "audit",
                "value": f"{item_type}/{item_id} audit decision {decision}; note: {note[:120]}",
                "as_of": _today(),
            }],
            "from_audit": f"{item_type}:{item_id}",
        }
        upsert_lesson(brand_id, lesson)

    # If retire, mark the item as retired in its source data
    _apply_audit_decision_to_source(item, decision, brand_id)

    return {
        "ok": True,
        "decision": audit_decision,
        "strategy": load_strategy(brand_id),
    }


def _apply_audit_decision_to_source(item: Dict[str, Any], decision: str, brand_id: str) -> None:
    """Apply the audit decision to the source data so it actually retires."""
    s = load_strategy(brand_id)
    if item["item_type"] == "market_move":
        for m in s.get("market_moves", []):
            if m["id"] == item["item_id"]:
                if decision == "retire":
                    m["status"] = "retired"
                elif decision == "pause":
                    m["status"] = "paused"
                m["updated_at"] = _now_iso()
                break
    elif item["item_type"] == "bet":
        for b in s.get("bets", []):
            if b["id"] == item["item_id"]:
                if decision == "retire":
                    b["status"] = "retired"
                elif decision == "pause":
                    b["status"] = "paused"
                b["updated_at"] = _now_iso()
                break
    save_strategy(s, brand_id)


# ─── Kill meeting generator ─────────────────────────────────────────

def kill_meeting(brand_id: str = "swing-shack") -> Dict[str, Any]:
    """Monthly kill meeting: surface weakest items for KEEP/UPDATE/PAUSE/RETIRE decisions."""
    audit = run_audit(brand_id)
    candidates = []

    # Items to surface:
    # - Any in retire/pause/delete
    # - Score < 50 (low health)
    # - Top 5 flags (most-flagged items)
    for a in audit["items"]:
        if a["audit_status"] in ("retire", "delete", "pause"):
            candidates.append({
                "item_id": a["item_id"],
                "item_type": a["item_type"],
                "title": a["title"],
                "audit_status": a["audit_status"],
                "audit_score": a["audit_score"],
                "flags": a["flags"],
                "reason_for_existence": a["reason_for_existence"],
                "next_action": a["next_action"],
                "why_surface": f"{a['audit_status'].upper()} (score {a['audit_score']}/100)",
            })
        elif a["audit_score"] < 40:
            candidates.append({
                "item_id": a["item_id"],
                "item_type": a["item_type"],
                "title": a["title"],
                "audit_status": a["audit_status"],
                "audit_score": a["audit_score"],
                "flags": a["flags"],
                "reason_for_existence": a["reason_for_existence"],
                "next_action": a["next_action"],
                "why_surface": f"Low score ({a['audit_score']}/100)",
            })

    # Dedupe by item_id+type
    seen = set()
    deduped = []
    for c in candidates:
        key = (c["item_type"], c["item_id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    deduped.sort(key=lambda c: (c["audit_score"], -len(c.get("flags", []))))

    return {
        "brand_id": brand_id,
        "generated_at": _now_iso(),
        "title": "WHAT SHOULD WE STOP DOING?",
        "subtitle": f"{len(deduped)} items on the table. The OS recommends action.",
        "candidates": deduped[:15],
        "clutter": audit["clutter_report"],
    }


# ─── Markdown render ────────────────────────────────────────────────

def render_audit_markdown(audit: Dict[str, Any], section: str = "summary") -> str:
    """Render audit results for Discord / shell output."""
    md = []

    if section in ("summary", "all"):
        md.append(f"## Strategy audit · {audit['audit_date']}")
        md.append(f"_Total items: {audit['total_items']}_")
        md.append("")
        md.append("**By status:**")
        for status in AUDIT_STATUSES:
            count = audit["by_status"].get(status, 0)
            if count:
                md.append(f"- {status.upper()}: {count}")
        md.append("")

    if section in ("clutter", "all"):
        c = audit["clutter_report"]
        md.append("### Strategy clutter report")
        md.append(f"- **{c['total']}** active ideas")
        md.append(f"- **{c['linked_to_strategy']}** directly support active bets")
        md.append(f"- **{c['orphaned']}** have no strategy link")
        md.append(f"- **{c['stale_or_low_score']}** have not been touched or score low")
        md.append(f"- **{c['duplicates']}** duplicate stronger ideas")
        md.append(f"- **{c['seasonal_expired']}** are seasonal and expired")
        md.append(f"- **{c['valid_keep']}** remain valid")
        md.append("")
        md.append("**Recommendations:**")
        for r in c["recommendations"]:
            md.append(f"- {r}")
        md.append("")

    if section == "needs_cleaning":
        md.append("### Needs cleaning")
        if not audit.get("needs_cleaning"):
            md.append("_Nothing needs cleaning this week. Strategy is healthy._")
        else:
            for nc in audit["needs_cleaning"]:
                md.append(f"- **{nc['title']}** → {nc['audit_status'].upper()}")
                md.append(f"  _Reason:_ {nc['reason'][:140]}")
                md.append(f"  _Action:_ {nc['next_action']}")
        md.append("")

    if section == "kill_meeting":
        # Used by the kill_meeting endpoint
        pass

    return "\n".join(md)


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    brand = sys.argv[1] if len(sys.argv) > 1 else "swing-shack"
    audit = run_audit(brand)
    print(render_audit_markdown(audit, "all"))