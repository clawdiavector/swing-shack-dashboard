"""
spend.py — Paid advertising spend layer.

This is the Money brain of the OS. The discipline:
  - Every paid campaign must link to North Star → Move → Bet
  - Strategic Efficiency has 5 separate layers (Effort / Spend /
    Attention / Intent / Outcome) — never merged into one score
  - Cost metrics only computed where valid (no R0, no infinite)
  - Platform efficiency ≠ strategic efficiency (cheap ≠ useful)
  - Attribution discipline: separate platform / GA4 / UTM / CRM
    sources; show disagreements; confidence rating per claim
  - Budget burn vs evidence maturity tracked separately

Attribution confidence levels:
  HIGH: UTM / campaign ID survives through booking or CRM
  MEDIUM: Reliable session attribution, booking path incomplete
  LOW: Platform-reported conversion only, or inferred

Recommendation strength follows attribution confidence.
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

from strategy_store import load_strategy, save_strategy, upsert_lesson
from evidence import Claim, LAYERS, LAYER_LANGUAGE

# Attribution source types
ATTRIBUTION_SOURCES = {"platform", "ga4", "utm", "crm", "booking_system"}
ATTRIBUTION_CONFIDENCE = {"high", "medium", "low"}

# Cost metric definitions — only valid when required inputs exist
COST_METRIC_VALIDATORS = {
    "cpm":         {"needs": ["impressions", "spend"],     "output_layer": "impression"},
    "cpc":         {"needs": ["clicks", "spend"],          "output_layer": "click"},
    "cost_per_visit": {"needs": ["visits", "spend"],      "output_layer": "visit"},
    "cpl":         {"needs": ["leads", "spend"],           "output_layer": "lead"},
    "cpa":         {"needs": ["bookings", "spend"],        "output_layer": "booking"},
    "roas":        {"needs": ["revenue", "spend"],         "output_layer": "revenue"},
}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def _data_dir() -> Path:
    runtime = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime


def _spend_path(brand_id: str) -> Path:
    return _data_dir() / f"spend-{brand_id}.json"


def _empty_spend_doc(brand_id: str) -> dict:
    return {
        "brand_id": brand_id,
        "campaigns": [],
        "creatives": [],
        "updated_at": _now_iso(),
    }


def load_spend(brand_id: str = "swing-shack") -> dict:
    path = _spend_path(brand_id)
    if not path.exists():
        return _empty_spend_doc(brand_id)
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OS):
        return _empty_spend_doc(brand_id)


def save_spend(doc: dict, brand_id: str = None) -> str:
    bid = brand_id or doc.get("brand_id", "swing-shack")
    doc["brand_id"] = bid
    doc["updated_at"] = _now_iso()
    path = _spend_path(bid)
    with open(path, "w") as f:
        json.dump(doc, f, indent=2, default=str)
    return str(path)


# ─── Campaign record ─────────────────────────────────────────────────

def record_campaign(
    brand_id: str,
    campaign_id: str,
    platform: str,
    spend_rands: float,
    period_start: str,
    period_end: str,
    strategy_link: Dict[str, str] = None,
    attribution_source: str = "platform",
    attribution_confidence: str = "low",
    performance: Dict[str, Any] = None,
    name: str = None,
    status: str = "active",
) -> dict:
    """Record or update a paid campaign's spend for a period.

    strategy_link: {strategy_link.bet_id, strategy_link.move_id, strategy_link.market_move}
                  Required for non-orphan classification.
    performance: {impressions, clicks, visits, leads, bookings, revenue}
                 Each with attribution_source if separate.
    """
    if attribution_source not in ATTRIBUTION_SOURCES:
        raise ValueError(f"attribution_source must be one of {ATTRIBUTION_SOURCES}")
    if attribution_confidence not in ATTRIBUTION_CONFIDENCE:
        raise ValueError(f"attribution_confidence must be one of {ATTRIBUTION_CONFIDENCE}")

    doc = load_spend(brand_id)
    perf = performance or {}

    # Find existing
    existing = next((c for c in doc["campaigns"] if c["campaign_id"] == campaign_id and c["period_start"] == period_start), None)
    if existing:
        existing["spend_rands"] = spend_rands
        existing["performance"] = perf
        existing["attribution_source"] = attribution_source
        existing["attribution_confidence"] = attribution_confidence
        if strategy_link is not None:
            existing["strategy_link"] = strategy_link
        existing["status"] = status
        existing["updated_at"] = _now_iso()
    else:
        campaign = {
            "campaign_id": campaign_id,
            "name": name or campaign_id,
            "platform": platform,
            "spend_rands": spend_rands,
            "period_start": period_start,
            "period_end": period_end,
            "strategy_link": strategy_link or {},
            "attribution_source": attribution_source,
            "attribution_confidence": attribution_confidence,
            "performance": perf,
            "status": status,
            "recorded_at": _today(),
            "updated_at": _now_iso(),
        }
        doc["campaigns"].append(campaign)

    save_spend(doc, brand_id)
    return doc


def record_creative(
    brand_id: str,
    campaign_id: str,
    creative_id: str,
    spend_rands: float,
    performance: Dict[str, Any] = None,
    name: str = None,
) -> dict:
    """Record a creative within a campaign."""
    doc = load_spend(brand_id)
    perf = performance or {}

    creative = {
        "creative_id": creative_id,
        "campaign_id": campaign_id,
        "name": name or creative_id,
        "spend_rands": spend_rands,
        "performance": perf,
        "recorded_at": _today(),
    }

    # Replace if exists
    doc["creatives"] = [c for c in doc["creatives"] if c["creative_id"] != creative_id]
    doc["creatives"].append(creative)

    save_spend(doc, brand_id)
    return doc


# ─── Orphaned spend ─────────────────────────────────────────────────

def detect_orphaned_spend(brand_id: str = "swing-shack", period_start: str = None, period_end: str = None) -> List[Dict[str, Any]]:
    """Paid campaigns without a strategy_link to a bet or move.
    Returns orphans with spend total + actions (Link / Review / Pause)."""
    doc = load_spend(brand_id)
    orphans = []
    for c in doc.get("campaigns", []):
        if c.get("status") not in ("active", "running"):
            continue
        link = c.get("strategy_link") or {}
        if not (link.get("bet_id") or link.get("market_move")):
            orphans.append({
                "campaign_id": c["campaign_id"],
                "name": c.get("name", c["campaign_id"]),
                "platform": c["platform"],
                "spend_rands": c.get("spend_rands", 0),
                "period_start": c.get("period_start"),
                "period_end": c.get("period_end"),
                "message": f"R{c.get('spend_rands', 0):.0f} spent with no link to an active strategic bet.",
                "actions": ["link", "review", "pause"],
            })
    return orphans


# ─── Cost metrics — only compute where valid ─────────────────────────

def compute_cost_metrics(performance: Dict[str, Any], spend_rands: float) -> Dict[str, Any]:
    """Return only the cost metrics whose inputs exist. Never R0 or infinite."""
    out = {}
    for metric, spec in COST_METRIC_VALIDATORS.items():
        if "spend" not in spec["needs"]:
            continue
        # Both inputs must exist + be non-zero
        inputs = {k: performance.get(k) for k in spec["needs"] if k != "spend"}
        missing = [k for k, v in inputs.items() if v is None or v == 0]
        if missing:
            out[metric] = {"valid": False, "reason": f"missing required inputs: {missing}"}
            continue
        spend = spend_rands
        if spend <= 0:
            out[metric] = {"valid": False, "reason": "spend is zero or missing"}
            continue
        if metric == "roas":
            value = performance["revenue"] / spend
        else:
            # cost = spend / count
            count = next(iter(inputs.values()))
            value = spend / count
        out[metric] = {"valid": True, "value": round(value, 2), "layer": spec["output_layer"]}
    return out


def infer_strongest_layer(performance: Dict[str, Any]) -> Optional[str]:
    """Given performance data, return the strongest evidence layer we can claim."""
    for layer in ["revenue", "booking", "lead", "visit", "click", "engagement", "impression"]:
        key = layer + "s" if layer != "engagement" else "engagement_rate"
        if layer == "engagement":
            if performance.get("engagement_rate") or performance.get("engagements"):
                return layer
        elif performance.get(key):
            return layer
    return None


# ─── "What did R1 buy us?" ───────────────────────────────────────────

def what_did_r1_buy(campaign: Dict[str, Any]) -> Claim:
    """Staged attribution: per R spent, what did the campaign produce at each layer?
    Only show stages we can actually attribute. State the evidence boundary.
    """
    spend = campaign.get("spend_rands", 0)
    perf = campaign.get("performance", {})
    if not spend or spend <= 0:
        return Claim(
            statement=f"No spend recorded for campaign '{campaign.get('name', campaign.get('campaign_id', '?'))}'.",
            evidence_layer="impression", sources=[], confidence="low",
            recommended_action="Record spend + performance data to enable this view.",
        )

    r_per_impression = perf.get("impressions", 0) / spend if perf.get("impressions") else None
    r_per_click = perf.get("clicks", 0) / spend if perf.get("clicks") else None
    r_per_visit = perf.get("visits", 0) / spend if perf.get("visits") else None
    r_per_lead = perf.get("leads", 0) / spend if perf.get("leads") else None
    r_per_booking = perf.get("bookings", 0) / spend if perf.get("bookings") else None

    # Build the staged ladder — only show what we can attribute
    ladder = []
    if r_per_impression: ladder.append(("impressions", perf["impressions"]))
    if r_per_click: ladder.append(("clicks", perf["clicks"]))
    if r_per_visit: ladder.append(("booking-page visits", perf["visits"]))
    if r_per_lead: ladder.append(("leads", perf["leads"]))
    if r_per_booking: ladder.append(("bookings", perf["bookings"]))

    # Strongest evidence layer
    strongest = infer_strongest_layer(perf)

    # Build statement
    lines = [f"R{spend:.0f} invested produced approximately:"]
    for label, value in ladder:
        lines.append(f"- {value} {label}")
    if r_per_visit and not r_per_booking:
        lines.append("")
        lines.append("Evidence currently reaches booking intent.")
        lines.append("Cannot yet claim: this campaign converts.")
    elif r_per_booking:
        lines.append("")
        lines.append("Evidence currently reaches booking.")
    elif r_per_click:
        lines.append("")
        lines.append("Evidence currently stops at traffic.")
    else:
        lines.append("")
        lines.append("Evidence stops at the visibility layer.")

    return Claim(
        statement="\n".join(lines),
        evidence_layer=strongest or "impression",
        sources=[{
            "source": f"spend-{campaign.get('brand_id', 'swing-shack')}.json",
            "value": f"spend={spend}, {perf}",
            "as_of": campaign.get("period_end", _today()),
        }],
        confidence={"revenue": "high", "booking": "high", "lead": "medium", "visit": "medium", "click": "low", "engagement": "low", "impression": "low"}.get(strongest or "impression", "low"),
        recommended_action=(
            "Continue measuring; promote to stronger claims once higher-layer data exists."
            if strongest in ("impression", "engagement", "click")
            else "Review efficiency; consider scaling if evidence is conclusive."
        ),
        why_not_stronger=f"We have data only up to '{strongest or 'impression'}'.",
    )


# ─── Strategic Efficiency per bet ────────────────────────────────────

def strategic_efficiency(brand_id: str, bet_id: str) -> Dict[str, Any]:
    """Build the 5-layer efficiency panel for a single bet.

    Layers are reported SEPARATELY — never merged.
    """
    s = load_strategy(brand_id)
    bet = next((b for b in s.get("bets", []) if b["id"] == bet_id), None)
    if not bet:
        return {"error": "bet not found"}

    doc = load_spend(brand_id)

    # Layer 1: EFFORT — count themes/posts/lp/emails in this bet
    effort = {
        "posts_planned": len(bet.get("content_themes", [])) or 0,
        "themes": bet.get("content_themes", []),
        "experiments": len(bet.get("experiments", [])) or 0,
        "milestones": len(bet.get("milestones", [])) or 0,
        "watch_metrics": bet.get("watch_metrics", []),
        "status": bet.get("status", ""),
    }

    # Layer 2: SPEND — total paid investment linked to this bet
    spend_total = 0
    spend_by_platform = defaultdict(float)
    spend_by_source = defaultdict(float)
    spend_by_confidence = defaultdict(float)
    spend_campaigns = []
    for c in doc.get("campaigns", []):
        link = c.get("strategy_link") or {}
        if link.get("bet_id") == bet_id:
            s_amt = c.get("spend_rands", 0)
            spend_total += s_amt
            spend_by_platform[c["platform"]] += s_amt
            spend_by_source[c.get("attribution_source", "platform")] += s_amt
            spend_by_confidence[c.get("attribution_confidence", "low")] += s_amt
            spend_campaigns.append(c["campaign_id"])

    spend = {
        "total_rands": round(spend_total, 2),
        "by_platform": dict(spend_by_platform),
        "by_attribution_source": dict(spend_by_source),
        "by_attribution_confidence": dict(spend_by_confidence),
        "linked_campaigns": spend_campaigns,
    }

    # Aggregate performance across linked campaigns
    agg_perf = defaultdict(float)
    for c in doc.get("campaigns", []):
        link = c.get("strategy_link") or {}
        if link.get("bet_id") == bet_id:
            for k, v in (c.get("performance") or {}).items():
                try:
                    agg_perf[k] += float(v)
                except (TypeError, ValueError):
                    pass

    # Layer 3: ATTENTION (impressions / reach / engagement)
    attention = {
        "impressions": int(agg_perf.get("impressions", 0)),
        "reach": int(agg_perf.get("reach", 0)),
        "video_views": int(agg_perf.get("video_views", 0)),
        "engagement_rate_pct": agg_perf.get("engagement_rate") or None,
    }

    # Layer 4: INTENT (clicks, visits, form starts)
    intent = {
        "link_clicks": int(agg_perf.get("clicks", 0)),
        "landing_page_sessions": int(agg_perf.get("visits", 0)),
        "booking_page_visits": int(agg_perf.get("booking_visits", 0) or agg_perf.get("visits", 0)),
        "form_starts": int(agg_perf.get("form_starts", 0)),
    }

    # Layer 5: OUTCOME (leads, bookings, revenue)
    outcome = {
        "leads": int(agg_perf.get("leads", 0)),
        "bookings": int(agg_perf.get("bookings", 0)),
        "revenue_rands": agg_perf.get("revenue") or None,
    }

    # Cost metrics (only valid ones)
    cost = compute_cost_metrics(dict(agg_perf), spend_total)

    # Evidence ladder — the visual
    evidence_ladder = _build_evidence_ladder(agg_perf)

    # Strongest supported claim
    strongest_layer = evidence_ladder["strongest_layer"]
    can_claim = LAYER_LANGUAGE.get(strongest_layer, "earns visibility")
    cannot_claim = LAYER_LANGUAGE.get(_next_layer(strongest_layer), "")

    # Platform efficiency vs strategic efficiency
    platform_efficient = bool(cost.get("cpc", {}).get("valid") or cost.get("cpm", {}).get("valid"))
    strategic_layer = _strongest_outcome_layer(agg_perf)
    if platform_efficient and strategic_layer in ("impression", "engagement", "click"):
        separation = "platform_efficient_strategic_unproven"
        manager_read = (
            f"This campaign is efficient at buying traffic. "
            f"We do not yet know whether that traffic produces bookings."
        )
    elif platform_efficient and strategic_layer in ("visit", "lead"):
        separation = "platform_efficient_strategic_promising"
        manager_read = "Efficient on the platform. Booking intent is real but conversion is unmeasured."
    elif platform_efficient and strategic_layer in ("booking", "revenue"):
        separation = "platform_and_strategic_efficient"
        manager_read = "Efficient on the platform AND produces bookings."
    else:
        separation = "platform_data_missing"
        manager_read = "Platform efficiency: insufficient data. Add spend + impressions/clicks."

    return {
        "bet_id": bet_id,
        "bet_title": bet.get("title", ""),
        "strategy": {
            "hypothesis": bet.get("hypothesis", ""),
            "what_proves_it": bet.get("what_proves_it", ""),
            "what_kills_it": bet.get("what_kills_it", ""),
            "next_action": bet.get("next_action", ""),
        },
        "effort": effort,
        "spend": spend,
        "attention": attention,
        "intent": intent,
        "outcome": outcome,
        "cost": cost,
        "evidence_ladder": evidence_ladder,
        "strongest_supported_claim": f"This campaign {can_claim}.",
        "cannot_yet_claim": f"This campaign {cannot_claim}." if cannot_claim else None,
        "platform_vs_strategic": {
            "verdict": separation,
            "manager_read": manager_read,
            "platform_efficient": platform_efficient,
            "strongest_outcome_layer": strategic_layer,
        },
    }


def _build_evidence_ladder(perf: Dict[str, Any]) -> Dict[str, Any]:
    """Build the ✓ / — ladder visualisation. Strongest layer wins."""
    ladder = []
    layer_inputs = {
        "attention": (perf.get("impressions") or perf.get("reach") or perf.get("engagement_rate")),
        "traffic": perf.get("clicks"),
        "intent": perf.get("visits") or perf.get("booking_visits") or perf.get("form_starts"),
        "lead": perf.get("leads"),
        "booking": perf.get("bookings"),
        "revenue": perf.get("revenue"),
    }
    strongest_layer = None
    for layer, value in layer_inputs.items():
        present = bool(value and value != 0)
        ladder.append({"layer": layer, "present": present, "value": value if present else None})
        if present and (strongest_layer is None or LAYERS.get(layer, 0) > LAYERS.get(strongest_layer, 0)):
            strongest_layer = layer

    # Map "traffic" → "click" for the language
    strongest_for_claim = strongest_layer
    if strongest_for_claim == "traffic":
        strongest_for_claim = "click"

    return {
        "rungs": ladder,
        "strongest_layer": strongest_for_claim or "impression",
    }


def _next_layer(current: str) -> Optional[str]:
    current_rank = LAYERS.get(current, 0)
    for layer, rank in sorted(LAYERS.items(), key=lambda x: x[1]):
        if rank == current_rank + 1:
            return layer
    return None


def _strongest_outcome_layer(perf: Dict[str, Any]) -> str:
    """Returns 'impression' / 'engagement' / 'click' / 'visit' / 'lead' / 'booking' / 'revenue'."""
    if perf.get("revenue"): return "revenue"
    if perf.get("bookings"): return "booking"
    if perf.get("leads"): return "lead"
    if perf.get("visits") or perf.get("booking_visits"): return "visit"
    if perf.get("clicks"): return "click"
    if perf.get("engagement_rate") or perf.get("engagements"): return "engagement"
    return "impression"


# ─── Spend vs strategic priority ────────────────────────────────────

def spend_vs_priority(brand_id: str, period_start: str = None, period_end: str = None) -> Dict[str, Any]:
    """For each strategic area, show priority vs spend share.
    Flags HIGH priority / LOW spend and LOW priority / HIGH spend.
    """
    s = load_strategy(brand_id)
    doc = load_spend(brand_id)

    # Map each bet to its strategic area
    area_to_bets = defaultdict(list)
    for b in s.get("bets", []):
        text_blob = (b.get("title", "") + " " + " ".join(b.get("content_themes", [])) + " " + (b.get("primary_kpi") or "")).lower()
        from portfolio import classify_strategic_areas
        for area in classify_strategic_areas(text_blob):
            area_to_bets[area].append(b)

    # Compute priority per area (heuristic: presence of in_flight bets)
    area_priority = {}
    for area, bets in area_to_bets.items():
        in_flight = [b for b in bets if b.get("status") == "in_flight"]
        if in_flight:
            area_priority[area] = "high"
        elif any(b.get("status") == "planned" for b in bets):
            area_priority[area] = "medium"
        else:
            area_priority[area] = "low"

    # Compute spend per area via strategy_link
    area_spend = defaultdict(float)
    total_spend = 0
    for c in doc.get("campaigns", []):
        if c.get("status") not in ("active", "running"):
            continue
        spend = c.get("spend_rands", 0)
        total_spend += spend
        link = c.get("strategy_link") or {}
        bet_id = link.get("bet_id")
        if bet_id:
            bet = next((b for b in s.get("bets", []) if b["id"] == bet_id), None)
            if bet:
                text_blob = (bet.get("title", "") + " " + " ".join(bet.get("content_themes", []))).lower()
                from portfolio import classify_strategic_areas
                for area in classify_strategic_areas(text_blob):
                    area_spend[area] += spend

    # Compute share
    matrix = []
    all_areas = set(area_priority.keys()) | set(area_spend.keys())
    for area in all_areas:
        priority = area_priority.get(area, "low")
        spend = area_spend.get(area, 0)
        share = round(100 * spend / max(total_spend, 1)) if total_spend > 0 else 0
        flag = None
        if priority == "high" and share < 10:
            flag = "high_priority_low_spend"
        elif priority in ("low", "medium") and share >= 40:
            flag = "low_priority_high_spend"
        elif priority == "medium" and share >= 50:
            flag = "spend_concentration"
        matrix.append({
            "area": area,
            "priority": priority,
            "spend_rands": round(spend, 2),
            "spend_share_pct": share,
            "flag": flag,
            "manager_read": _priority_vs_spend_read(priority, share, flag),
        })
    matrix.sort(key=lambda m: -m["spend_rands"])

    return {
        "total_spend": round(total_spend, 2),
        "matrix": matrix,
    }


def _priority_vs_spend_read(priority: str, share: int, flag: Optional[str]) -> str:
    if flag == "high_priority_low_spend":
        return f"{priority.title()} priority area but only {share}% of paid spend. Review whether organic effort is sufficient or this is a deliberate balance."
    if flag == "low_priority_high_spend":
        return f"{priority.title()} priority area receiving {share}% of paid spend. Spend concentration may be deliberate or accidental."
    if flag == "spend_concentration":
        return f"{priority.title()} priority area receiving {share}% of paid spend. Spend concentration warning."
    if share == 0:
        return f"{priority.title()} priority area, no paid spend."
    return f"{priority.title()} priority area, {share}% of paid spend."


# ─── Spend concentration ─────────────────────────────────────────────

def spend_concentration_warnings(brand_id: str) -> List[Dict[str, Any]]:
    """If any bet gets >50% of monthly spend, flag with context."""
    doc = load_spend(brand_id)
    s = load_strategy(brand_id)

    # Sum spend by bet for the current month
    today = datetime.date.today()
    month_start = today.replace(day=1).isoformat()
    spend_by_bet = defaultdict(float)
    for c in doc.get("campaigns", []):
        if c.get("status") not in ("active", "running"):
            continue
        if c.get("period_start", "") < month_start:
            continue
        link = c.get("strategy_link") or {}
        if link.get("bet_id"):
            spend_by_bet[link["bet_id"]] += c.get("spend_rands", 0)

    total = sum(spend_by_bet.values())
    if total <= 0:
        return []

    warnings = []
    for bet_id, spend in spend_by_bet.items():
        share = 100 * spend / total
        if share < 50:
            continue
        bet = next((b for b in s.get("bets", []) if b["id"] == bet_id), None)
        if not bet:
            continue

        # Context: priority, evidence maturity, age, decision date, outcome layer
        evidence_maturity = "early" if (datetime.date.today() - datetime.date.fromisoformat((bet.get("start_date") or _today())[:10])).days < 14 else "established"
        try:
            decision_d = datetime.date.fromisoformat((bet.get("decision_date") or "")[:10]) if bet.get("decision_date") else None
            days_to_decision = (decision_d - datetime.date.today()).days if decision_d else None
        except (ValueError, TypeError):
            days_to_decision = None
        outcome_layer = _strongest_outcome_layer({})  # would need perf data

        warnings.append({
            "bet_id": bet_id,
            "title": bet.get("title", ""),
            "spend_share_pct": round(share, 1),
            "spend_rands": round(spend, 2),
            "context": {
                "evidence_maturity": evidence_maturity,
                "days_to_decision": days_to_decision,
                "status": bet.get("status", ""),
                "campaign_age_days": (datetime.date.today() - datetime.date.fromisoformat((bet.get("start_date") or _today())[:10])).days,
            },
            "verdict": "deliberate_conviction_or_accidental_concentration",
            "question": f"{share:.0f}% of monthly spend supports one bet. Is this deliberate conviction or accidental concentration?",
        })
    return warnings


# ─── Budget burn vs evidence maturity ────────────────────────────────

def budget_burn_vs_maturity(brand_id: str, bet_id: str) -> Dict[str, Any]:
    """% of budget spent vs evidence maturity vs decision date vs outcome layer."""
    s = load_strategy(brand_id)
    doc = load_spend(brand_id)
    bet = next((b for b in s.get("bets", []) if b["id"] == bet_id), None)
    if not bet:
        return {"error": "bet not found"}

    # Find budget allocation in bet
    budget_allocated = bet.get("budget_rands", 0) or 0

    # Sum spent
    spent = 0
    linked_campaigns = []
    for c in doc.get("campaigns", []):
        link = c.get("strategy_link") or {}
        if link.get("bet_id") == bet_id:
            spent += c.get("spend_rands", 0)
            linked_campaigns.append(c["campaign_id"])

    burn_pct = round(100 * spent / max(budget_allocated, 1)) if budget_allocated else None

    # Evidence maturity: weeks since start
    try:
        start_d = datetime.date.fromisoformat((bet.get("start_date") or _today())[:10])
        weeks_active = (datetime.date.today() - start_d).days / 7
    except (ValueError, TypeError):
        weeks_active = 0
    if weeks_active < 2:
        maturity = "early"
    elif weeks_active < 6:
        maturity = "establishing"
    else:
        maturity = "established"

    # Decision date distance
    try:
        decision_d = datetime.date.fromisoformat((bet.get("decision_date") or "")[:10]) if bet.get("decision_date") else None
        days_to_decision = (decision_d - datetime.date.today()).days if decision_d else None
    except (ValueError, TypeError):
        days_to_decision = None

    # Outcome layer reached (via performance)
    agg_perf = defaultdict(float)
    for c in doc.get("campaigns", []):
        if c.get("strategy_link", {}).get("bet_id") == bet_id:
            for k, v in (c.get("performance") or {}).items():
                try:
                    agg_perf[k] += float(v)
                except (TypeError, ValueError):
                    pass
    outcome_layer = _strongest_outcome_layer(dict(agg_perf))

    # Recommendation
    recommendation = ""
    if burn_pct is None or budget_allocated == 0:
        recommendation = "No budget allocated. Set a budget allocation for this bet to enable burn tracking."
    elif burn_pct >= 70 and maturity == "early" and outcome_layer in ("impression", "engagement", "click"):
        recommendation = f"Consider slowing spend — {burn_pct}% of budget spent while evidence is still limited to the {outcome_layer} layer."
    elif burn_pct >= 70 and outcome_layer in ("visit", "lead"):
        recommendation = f"{burn_pct}% of budget spent, evidence at the {outcome_layer} layer. Consider pausing or refining until booking data exists."
    elif burn_pct < 30 and maturity == "established":
        recommendation = f"Only {burn_pct}% of budget spent despite being {maturity}. Consider whether the test is being given enough time."
    elif burn_pct < 50 and outcome_layer in ("lead", "visit", "booking"):
        recommendation = f"{burn_pct}% of budget spent, evidence at the {outcome_layer} layer. Continue the test; insufficient reason to scale yet."
    else:
        recommendation = f"{burn_pct}% budget spent, evidence at the {outcome_layer} layer. Continue normally."

    return {
        "bet_id": bet_id,
        "bet_title": bet.get("title", ""),
        "budget_allocated_rands": budget_allocated,
        "spent_rands": round(spent, 2),
        "burn_pct": burn_pct,
        "evidence_maturity": maturity,
        "weeks_active": round(weeks_active, 1),
        "days_to_decision": days_to_decision,
        "outcome_layer": outcome_layer,
        "linked_campaigns": linked_campaigns,
        "recommendation": recommendation,
    }


# ─── Creative-level evidence ────────────────────────────────────────

def creative_efficiency(brand_id: str, campaign_id: str) -> Dict[str, Any]:
    """For each creative in a campaign: spend + perf + evidence layer + recommendation."""
    doc = load_spend(brand_id)
    campaign = next((c for c in doc["campaigns"] if c["campaign_id"] == campaign_id), None)
    if not campaign:
        return {"error": "campaign not found"}

    creatives = [c for c in doc.get("creatives", []) if c["campaign_id"] == campaign_id]
    if not creatives:
        return {"campaign_id": campaign_id, "creatives": [], "message": "No creative-level data recorded yet."}

    out = []
    for c in creatives:
        perf = c.get("performance", {})
        cost = compute_cost_metrics(perf, c.get("spend_rands", 0))
        layer = infer_strongest_layer(perf)
        out.append({
            "creative_id": c["creative_id"],
            "name": c.get("name", c["creative_id"]),
            "spend_rands": c.get("spend_rands", 0),
            "performance": perf,
            "cost": cost,
            "evidence_layer": layer,
            "evidence_layer_label": LAYER_LANGUAGE.get(layer, "earns visibility"),
        })

    # Manager read: best cost-per-visit by default
    sorted_by_visit = sorted(out, key=lambda c: c["cost"].get("cost_per_visit", {}).get("value", float("inf")) if c["cost"].get("cost_per_visit", {}).get("valid") else float("inf"))
    best = sorted_by_visit[0] if sorted_by_visit else None
    worst = sorted_by_visit[-1] if sorted_by_visit else None
    manager_read = None
    if best and worst and best["creative_id"] != worst["creative_id"]:
        best_visit = best["performance"].get("visits") or best["performance"].get("booking_visits") or 0
        worst_visit = worst["performance"].get("visits") or worst["performance"].get("booking_visits") or 0
        if best_visit > 0 and worst_visit > 0 and best["spend_rands"] > 0 and worst["spend_rands"] > 0:
            ratio = (worst["cost"]["cost_per_visit"]["value"] / best["cost"]["cost_per_visit"]["value"]) if best["cost"]["cost_per_visit"]["valid"] and worst["cost"]["cost_per_visit"]["valid"] else None
            if ratio and ratio >= 2:
                manager_read = f"{best['name']} creates {ratio:.1f}× more booking visits per Rand than {worst['name']}."

    # Per-creative recommendation
    for c in out:
        if not c["performance"].get("visits") and not c["performance"].get("booking_visits"):
            c["recommendation"] = "HOLD — evidence stops at click layer."
        elif c["cost"].get("cost_per_visit", {}).get("valid") and best and c["creative_id"] == best["creative_id"]:
            c["recommendation"] = "SCALE — best cost-per-visit."
        elif c["cost"].get("cost_per_visit", {}).get("valid") and worst and c["creative_id"] == worst["creative_id"]:
            c["recommendation"] = "REDUCE / STOP — worst cost-per-visit."
        else:
            c["recommendation"] = "CONTINUE — gathering evidence."

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.get("name", campaign_id),
        "creatives": out,
        "manager_read": manager_read,
    }


# ─── Attribution disagreements ───────────────────────────────────────

def attribution_disagreements(brand_id: str) -> List[Dict[str, Any]]:
    """When platform-reported, GA4-attributed, UTM-attributed, CRM-attributed
    numbers disagree on the same metric, surface the disagreement."""
    doc = load_spend(brand_id)
    # For each campaign, compare performance numbers if multiple attribution sources exist
    # This requires performance.attribution_source on each metric, which we don't currently enforce.
    # For now, return an empty list — the discipline is in place to add it as data comes in.
    return []


# ─── Marketing ↔ Advertising handoff ─────────────────────────────────

def marketing_advertising_handoff(brand_id: str) -> Dict[str, Any]:
    """Find organic evidence that hasn't been paid-distributed, and paid learnings
    that haven't been tested organically."""
    s = load_strategy(brand_id)
    doc = load_spend(brand_id)
    handoffs = []

    # Organic themes with high engagement but no paid distribution
    organic_perf = _load_json("ig-analytics.json") or {}
    paid_themes = set()
    for c in doc.get("campaigns", []):
        for theme in (c.get("strategy_link", {}).get("themes") or []):
            paid_themes.add(theme.lower())

    if isinstance(organic_perf, dict):
        clusters = organic_perf.get("posts") or organic_perf.get("data") or []
        cluster_metrics = defaultdict(lambda: {"reach": 0, "engagement": 0, "count": 0})
        for p in clusters:
            cluster = (p.get("topic_cluster") or p.get("cluster") or "").lower()
            if not cluster:
                continue
            cluster_metrics[cluster]["reach"] += p.get("reach", 0)
            cluster_metrics[cluster]["engagement"] += p.get("engagement_rate", 0) or p.get("engagement", 0)
            cluster_metrics[cluster]["count"] += 1
        for cluster, m in sorted(cluster_metrics.items(), key=lambda x: -x[1]["reach"]):
            avg = m["engagement"] / max(m["count"], 1)
            if avg >= 3.0 and cluster and cluster not in paid_themes:
                handoffs.append({
                    "direction": "organic_to_paid",
                    "topic": cluster,
                    "organic_engagement_pct": round(avg, 2),
                    "post_count": m["count"],
                    "summary": f"Organic {cluster} content averages {avg:.2f}% engagement but no paid distribution exists for this theme.",
                    "suggested_action": "Create controlled advertising test on this theme.",
                })

    # Paid learnings that haven't been tested organically
    paid_learnings = []
    for c in doc.get("campaigns", []):
        link = c.get("strategy_link") or {}
        bet_id = link.get("bet_id")
        if not bet_id:
            continue
        perf = c.get("performance", {})
        if not (perf.get("visits") or perf.get("booking_visits")):
            continue
        # Cheap cost-per-visit
        cpc_valid = c.get("spend_rands", 0) > 0 and perf.get("visits", 0) > 0
        if cpc_valid:
            cpv = c["spend_rands"] / perf["visits"]
            if cpv < 20:  # arbitrary threshold for "cheap"
                paid_learnings.append({
                    "campaign_id": c["campaign_id"],
                    "name": c.get("name", c["campaign_id"]),
                    "cost_per_visit_rands": round(cpv, 2),
                    "visits": perf["visits"],
                })
    if paid_learnings:
        for pl in paid_learnings[:3]:
            handoffs.append({
                "direction": "paid_to_organic",
                "campaign_id": pl["campaign_id"],
                "name": pl["name"],
                "cost_per_visit_rands": pl["cost_per_visit_rands"],
                "summary": f"Paid campaign '{pl['name']}' drives booking visits at R{pl['cost_per_visit_rands']}/visit — consider testing the angle organically.",
                "suggested_action": "Lift the winning paid angle into organic content.",
            })

    return {"handoffs": handoffs}


def _load_json(filename: str) -> Optional[dict]:
    for path_str in [
        os.environ.get("DATA_DIR", "") + f"/{filename}",
        str(Path(__file__).resolve().parents[2] / "data" / filename),
    ]:
        if not path_str or path_str == f"/{filename}":
            continue
        try:
            with open(path_str) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
    return None


# ─── Budget opportunity cost ────────────────────────────────────────

def budget_opportunity_cost(brand_id: str, proposed_budget_rands: float, proposed_bet_or_area: str = None) -> Dict[str, Any]:
    """Where does the proposed R come from? List current spend categories."""
    doc = load_spend(brand_id)
    total = 0
    by_category = defaultdict(float)
    for c in doc.get("campaigns", []):
        if c.get("status") not in ("active", "running"):
            continue
        spend = c.get("spend_rands", 0)
        total += spend
        link = c.get("strategy_link") or {}
        bet_id = link.get("bet_id")
        if bet_id:
            by_category[f"bet:{bet_id}"] += spend
        else:
            by_category["unassigned"] += spend

    # Sort by spend desc — these are the most likely to be displaced
    sorted_cats = sorted(by_category.items(), key=lambda x: -x[1])
    displacement_options = []
    half = proposed_budget_rands / 2
    for cat, spend in sorted_cats:
        if spend <= 0:
            continue
        # Suggest proportional reduction
        suggested_reduction = min(spend * 0.2, half)
        displacement_options.append({
            "category": cat,
            "current_spend": round(spend, 2),
            "suggested_reduction_rands": round(suggested_reduction, 2),
            "rationale": f"Reduce {cat} spend by 20% to free R{suggested_reduction:.0f}.",
        })
        if len(displacement_options) >= 5:
            break

    return {
        "current_total_spend_rands": round(total, 2),
        "proposed_budget_rands": proposed_budget_rands,
        "for_proposed": proposed_bet_or_area,
        "displacement_options": displacement_options,
        "options_summary": [
            "Reduce existing spend categories proportionally",
            "Add to total budget",
            "Don't run it",
        ],
    }


# ─── Seed sample data for swing-shack ────────────────────────────────

def seed_sample_spend(brand_id: str = "swing-shack") -> dict:
    """Seed sample spend data so the UI shows real numbers.
    Dynamically links to whatever bet IDs exist in the live strategy."""
    doc = load_spend(brand_id)
    if doc.get("campaigns"):
        return doc

    # Look up live bet IDs by campaign_id or by title keyword
    s = load_strategy(brand_id)
    bets_list = s.get("bets", [])
    live_move = s["market_moves"][0]["id"] if s.get("market_moves") else "mship-001"

    def _find_find_bet(cid):
        """Find a bet by campaign_id match OR by title keyword."""
        # First: exact campaign_id match
        for b in bets_list:
            if b.get("campaign_id") == cid:
                return b["id"]
        # Fallback: title keyword match
        cid_lower = cid.lower()
        for b in bets_list:
            title_lower = (b.get("title") or "").lower()
            cid_words = cid_lower.replace("-", " ").split()
            if any(word in title_lower for word in cid_words if len(word) > 3):
                return b["id"]
        # Last resort: first bet
        return bets_list[0]["id"] if bets_list else "mship-001"

    today = datetime.date.today()
    month_start = today.replace(day=1).isoformat()
    month_end = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1).isoformat()

    sample = [
        {
            "campaign_id": "ig-warm-retarget-001",
            "name": "IG Warm Audience Retargeting — Booking Page",
            "platform": "meta",
            "spend_rands": 3900,
            "period_start": month_start,
            "period_end": month_end,
            "strategy_link": {"bet_id": _find_bet("use-the-right-equipment-mq5l90bk"), "move_id": live_move},
            "attribution_source": "platform",
            "attribution_confidence": "low",
            "performance": {
                "impressions": 145000,
                "reach": 82000,
                "clicks": 1280,
                "visits": 312,
                "leads": 0,
                "bookings": 0,
            },
            "status": "active",
        },
        {
            "campaign_id": "meta-trackman-awareness-001",
            "name": "Meta TrackMan Awareness — Cold Audience",
            "platform": "meta",
            "spend_rands": 5200,
            "period_start": month_start,
            "period_end": month_end,
            "strategy_link": {"bet_id": _find_bet("trackman-intelligence"), "move_id": live_move},
            "attribution_source": "platform",
            "attribution_confidence": "low",
            "performance": {
                "impressions": 220000,
                "reach": 145000,
                "clicks": 1450,
                "visits": 80,
                "leads": 0,
                "bookings": 0,
            },
            "status": "active",
        },
        {
            "campaign_id": "google-search-fitting-001",
            "name": "Google Search — Fitting Intent",
            "platform": "google",
            "spend_rands": 1800,
            "period_start": month_start,
            "period_end": month_end,
            "strategy_link": {"bet_id": _find_bet("takomo-101t"), "move_id": live_move},
            "attribution_source": "utm",
            "attribution_confidence": "medium",
            "performance": {
                "impressions": 38000,
                "reach": 0,
                "clicks": 240,
                "visits": 95,
                "leads": 4,
                "bookings": 0,
            },
            "status": "active",
        },
        {
            "campaign_id": "orphan-legacy-display-001",
            "name": "Display Network — Generic Brand Awareness",
            "platform": "google",
            "spend_rands": 1850,
            "period_start": month_start,
            "period_end": month_end,
            "strategy_link": {},  # ORPHAN
            "attribution_source": "platform",
            "attribution_confidence": "low",
            "performance": {
                "impressions": 95000,
                "reach": 72000,
                "clicks": 110,
                "visits": 0,
                "leads": 0,
                "bookings": 0,
            },
            "status": "active",
        },
    ]

    sample_creatives = [
        {
            "creative_id": "creative-trackman-cta",
            "campaign_id": "ig-warm-retarget-001",
            "name": "TrackMan CTA — Carousel",
            "spend_rands": 1820,
            "performance": {"clicks": 720, "visits": 198, "leads": 0, "bookings": 0},
        },
        {
            "creative_id": "creative-fitting-cta",
            "campaign_id": "ig-warm-retarget-001",
            "name": "Fitting CTA — Video",
            "spend_rands": 1450,
            "performance": {"clicks": 410, "visits": 88, "leads": 0, "bookings": 0},
        },
        {
            "creative_id": "creative-coaching-cta",
            "campaign_id": "ig-warm-retarget-001",
            "name": "Coaching CTA — Static",
            "spend_rands": 630,
            "performance": {"clicks": 150, "visits": 26, "leads": 0, "bookings": 0},
        },
    ]

    doc["campaigns"] = sample
    doc["creatives"] = sample_creatives
    save_spend(doc, brand_id)
    return doc


# ─── Markdown renderer for monthly meeting MONEY section ─────────────

def render_money_section(brand_id: str) -> str:
    """Render the MONEY section for the monthly meeting."""
    doc = load_spend(brand_id)
    s = load_strategy(brand_id)

    total_spend = sum(c.get("spend_rands", 0) for c in doc.get("campaigns", []) if c.get("status") in ("active", "running"))
    if total_spend <= 0:
        return "_No paid spend recorded yet._"

    # By area
    area_spend = defaultdict(float)
    for c in doc.get("campaigns", []):
        if c.get("status") not in ("active", "running"):
            continue
        link = c.get("strategy_link") or {}
        bet_id = link.get("bet_id")
        if bet_id:
            bet = next((b for b in s.get("bets", []) if b["id"] == bet_id), None)
            if bet:
                from portfolio import classify_strategic_areas
                text_blob = (bet.get("title", "") + " " + " ".join(bet.get("content_themes", []))).lower()
                for area in classify_strategic_areas(text_blob):
                    area_spend[area] += c.get("spend_rands", 0)

    md = []
    md.append(f"**Total paid spend this month:** R{total_spend:,.0f}")
    md.append("")
    md.append("**Where the money went (by strategic area):**")
    for area, spend in sorted(area_spend.items(), key=lambda x: -x[1]):
        share = round(100 * spend / total_spend)
        md.append(f"- {area}: R{spend:,.0f} ({share}%)")
    md.append("")

    # Highest claimable evidence layer across all paid campaigns
    all_perf = defaultdict(float)
    for c in doc.get("campaigns", []):
        if c.get("status") not in ("active", "running"):
            continue
        for k, v in (c.get("performance") or {}).items():
            try:
                all_perf[k] += float(v)
            except (TypeError, ValueError):
                pass
    strongest_layer = _strongest_outcome_layer(dict(all_perf))
    if strongest_layer in ("booking", "revenue"):
        md.append(f"**Strongest supported claim:** Paid spend produces bookings ({int(all_perf.get('bookings', 0))} bookings attributed).")
    elif strongest_layer == "lead":
        md.append(f"**Strongest supported claim:** Paid spend generates leads ({int(all_perf.get('leads', 0))} leads attributed). Cannot yet claim conversion.")
    elif strongest_layer == "visit":
        md.append(f"**Strongest supported claim:** Paid spend creates booking intent ({int(all_perf.get('visits', 0))} booking-page visits). Conversion unmeasured.")
    elif strongest_layer == "click":
        md.append(f"**Strongest supported claim:** Paid spend drives site traffic ({int(all_perf.get('clicks', 0))} clicks). Intent unmeasured.")
    else:
        md.append("**Strongest supported claim:** Paid spend earns visibility. No downstream evidence.")
    md.append("")

    # Concentration warnings
    concentration = spend_concentration_warnings(brand_id)
    if concentration:
        md.append("**Spend concentration warnings:**")
        for w in concentration:
            md.append(f"- {w['question']}")
        md.append("")

    return "\n".join(md)


if __name__ == "__main__":
    import sys
    brand = sys.argv[1] if len(sys.argv) > 1 else "swing-shack"
    seed_sample_spend(brand)
    doc = load_spend(brand)
    print(f"Campaigns recorded: {len(doc['campaigns'])}")
    print(f"Creatives recorded: {len(doc['creatives'])}")
    for c in doc["campaigns"]:
        print(f"  - {c['name']}: R{c['spend_rands']:.0f} on {c['platform']}")
    print()
    print("Orphans:")
    for o in detect_orphaned_spend(brand):
        print(f"  - {o['name']}: R{o['spend_rands']:.0f} - {o['message']}")