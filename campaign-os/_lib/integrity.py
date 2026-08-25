"""
integrity.py — Data Integrity & Measurement Health.

This module is the OS's truth-discipline. It runs BEFORE any
strategy reasoning and reports honestly about what the data
actually supports.

Christelle's hierarchy:
  DATA
  -> IS THE DATA TRUSTWORTHY?
  -> WHAT DOES IT PROVE?
  -> WHAT MIGHT IT MEAN?
  -> WHAT SHOULD WE DO?

Never reverse that order.

The module is silent when healthy. It only speaks up when
something could materially change the conclusions we draw.
"""

from __future__ import annotations

import json
import os
import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple
from collections import defaultdict

import sys
HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE))

from strategy_store import load_strategy
from spend import load_spend, detect_orphaned_spend, strategic_efficiency

# Severity
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# Evidence layers — the order the OS can claim
EVIDENCE_LAYERS = ["attention", "traffic", "intent", "lead", "booking", "revenue"]
LAYER_LABELS = {
    "attention": "Attention",
    "traffic": "Traffic",
    "intent": "Intent (booking-page visits)",
    "lead": "Leads",
    "booking": "Bookings",
    "revenue": "Revenue",
}

# Default currency for the SA market
DEFAULT_CURRENCY = "ZAR"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def _data_dir() -> Path:
    runtime = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime


def _integrity_path() -> Path:
    return _data_dir() / "integrity-state.json"


def _load_integrity_state() -> dict:
    path = _integrity_path()
    if not path.exists():
        return {"measurement_gaps": [], "anomaly_flags": [], "evidence_corrections": [], "last_run": None, "last_run_clean": True}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"measurement_gaps": [], "anomaly_flags": [], "evidence_corrections": [], "last_run": None, "last_run_clean": True}


def _save_integrity_state(state: dict) -> None:
    state["last_run"] = _now_iso()
    with open(_integrity_path(), "w") as f:
        json.dump(state, f, indent=2, default=str)


# ─── Reconciliation (severity-graded) ────────────────────────────────

def reconcile(brand_id: str = "swing-shack") -> Dict[str, Any]:
    """Severity-graded reconciliation. Returns issues list grouped by severity.

    Critical: data corruption / commercial conclusions unreliable
    High: could materially affect strategic decisions
    Medium: measurement weakness limiting conclusions
    Low: clean-up issue
    """
    issues = []
    doc = load_spend(brand_id)
    s = load_strategy(brand_id)
    campaigns = [c for c in doc.get("campaigns", []) if c.get("status") in ("active", "running")]

    valid_bet_ids = {b["id"] for b in s.get("bets", [])}

    # Stale bet links (HIGH)
    for c in campaigns:
        link = c.get("strategy_link") or {}
        bet_id = link.get("bet_id")
        if bet_id and bet_id not in valid_bet_ids:
            issues.append({
                "code": "stale_bet_link",
                "severity": "high",
                "campaign_id": c.get("campaign_id"),
                "title": f"{c.get('name', c.get('campaign_id'))} links to retired bet ID",
                "detail": f"Campaign '{c.get('campaign_id')}' links to bet '{bet_id}' which no longer exists.",
                "impact": "Affected conclusions: " + ", ".join(_affected_conclusions(c, "stale_bet_link")),
                "spend_at_risk": c.get("spend_rands", 0),
                "recommended_action": "Relink campaign before using these figures for scale/hold decision.",
                "actions": ["relink", "review", "ignore_temporarily"],
            })

    # Duplicate campaigns (CRITICAL)
    seen_ids = {}
    for c in campaigns:
        cid = c.get("campaign_id")
        if cid in seen_ids:
            issues.append({
                "code": "duplicate_campaign",
                "severity": "critical",
                "campaign_id": cid,
                "title": f"Campaign '{cid}' is counted twice",
                "detail": f"Total duplicated spend: R{seen_ids[cid].get('spend_rands', 0) + c.get('spend_rands', 0):,.0f}.",
                "impact": "Spend totals inflated. Affected conclusions: portfolio balance, monthly spend, allocation %.",
                "spend_at_risk": seen_ids[cid].get("spend_rands", 0) + c.get("spend_rands", 0),
                "recommended_action": "Deduplicate before using for any commercial decision.",
            })
        seen_ids[cid] = c

    # Attribution confidence mismatch (MEDIUM)
    for c in campaigns:
        source = c.get("attribution_source", "")
        conf = c.get("attribution_confidence", "")
        if source == "platform" and conf == "high":
            issues.append({
                "code": "attribution_confidence_too_high",
                "severity": "medium",
                "campaign_id": c.get("campaign_id"),
                "title": f"Platform-attributed campaign '{c.get('name', c.get('campaign_id'))}' marked high confidence",
                "detail": "Platform-reported attribution should be low/medium confidence, not high.",
                "impact": "Affected conclusions: per-campaign confidence, cost-per-booking claims.",
                "recommended_action": "Downgrade confidence to medium until UTM/GA4 confirms.",
            })

    # Orphaned spend (HIGH — paid money without strategy)
    orphans = detect_orphaned_spend(brand_id)
    for o in orphans:
        issues.append({
            "code": "orphaned_spend",
            "severity": "high",
            "campaign_id": o.get("campaign_id"),
            "title": f"Orphaned spend — {o.get('name', o.get('campaign_id'))}",
            "detail": f"R{o.get('spend_rands', 0):,.0f} spent with no link to an active strategic bet.",
            "impact": "Affected conclusions: portfolio balance, strategic efficiency, monthly ROI summary.",
            "spend_at_risk": o.get("spend_rands", 0),
            "recommended_action": "Link to strategy, review, or pause.",
            "actions": ["link", "review", "pause"],
        })

    # Currency integrity (HIGH)
    for c in campaigns:
        cur = c.get("currency", "ZAR")
        if cur != DEFAULT_CURRENCY:
            issues.append({
                "code": "currency_integrity",
                "severity": "high",
                "campaign_id": c.get("campaign_id"),
                "title": f"Campaign '{c.get('campaign_id')}' records non-ZAR currency",
                "detail": f"Currency is {cur}, default is {DEFAULT_CURRENCY}.",
                "impact": "Totals would be inflated/deflated if mixed. Affected conclusions: total spend, ROAS, monthly review.",
                "recommended_action": "Add explicit exchange-rate-as-of-date and convert to ZAR.",
            })

    # Date range integrity (MEDIUM)
    for c in campaigns:
        ps = c.get("period_start")
        pe = c.get("period_end")
        if ps and pe:
            try:
                s_d = datetime.date.fromisoformat(ps[:10])
                e_d = datetime.date.fromisoformat(pe[:10])
                if e_d < s_d:
                    issues.append({
                        "code": "invalid_period_range",
                        "severity": "medium",
                        "campaign_id": c.get("campaign_id"),
                        "title": f"Campaign '{c.get('campaign_id')}' has period_end before period_start",
                        "detail": f"start={ps}, end={pe}",
                        "impact": "Performance numbers would be miscalculated.",
                        "recommended_action": "Correct period_end date.",
                    })
            except (ValueError, TypeError):
                pass

    # Sort by severity
    issues.sort(key=lambda i: -SEVERITY_RANK.get(i.get("severity", "low"), 0))

    return {
        "checked_at": _now_iso(),
        "issues": issues,
        "issue_count": len(issues),
        "critical_count": sum(1 for i in issues if i.get("severity") == "critical"),
        "high_count": sum(1 for i in issues if i.get("severity") == "high"),
        "medium_count": sum(1 for i in issues if i.get("severity") == "medium"),
        "low_count": sum(1 for i in issues if i.get("severity") == "low"),
        "is_clean": len(issues) == 0,
    }


def _affected_conclusions(campaign: dict, code: str) -> List[str]:
    """Translate a technical code into which strategic conclusions are at risk."""
    if code == "stale_bet_link":
        return ["strategic efficiency for this bet", "monthly spend allocation", "portfolio balance"]
    return ["portfolio balance", "monthly review"]


# ─── Anomaly sanity checks ───────────────────────────────────────────

def detect_anomalies(brand_id: str = "swing-shack") -> List[Dict[str, Any]]:
    """Flag values that are implausibly extreme.
    Does not auto-reject; only marks for validation."""
    anomalies = []
    doc = load_spend(brand_id)
    s = load_strategy(brand_id)

    # Look at last week's history if available, else flag any obviously extreme values
    for c in doc.get("campaigns", []):
        perf = c.get("performance", {})
        spend = c.get("spend_rands", 0)
        if spend <= 0:
            continue
        cpm = (spend / perf["impressions"] * 1000) if perf.get("impressions", 0) > 0 else None
        cpc = (spend / perf["clicks"]) if perf.get("clicks", 0) > 0 else None
        bookings = perf.get("bookings", 0)
        revenue = perf.get("revenue", 0)
        ctr = (perf.get("clicks", 0) / perf["impressions"] * 100) if perf.get("impressions", 0) > 0 else None

        # CPC too low
        if cpc is not None and cpc < 0.10:
            anomalies.append({
                "type": "impossibly_low_cpc",
                "campaign_id": c.get("campaign_id"),
                "severity": "high",
                "title": f"Anomalously low CPC R{cpc:.2f} on {c.get('name', c.get('campaign_id'))}",
                "value": cpc,
                "possible_causes": ["duplicate clicks", "decimal error", "currency issue", "wrong date range", "bot traffic", "import bug"],
            })
        # CPC too high
        if cpc is not None and cpc > 500:
            anomalies.append({
                "type": "impossibly_high_cpc",
                "campaign_id": c.get("campaign_id"),
                "severity": "medium",
                "title": f"Anomalously high CPC R{cpc:.2f} on {c.get('name', c.get('campaign_id'))}",
                "value": cpc,
                "possible_causes": ["currency issue", "duplicate impression", "narrow targeting", "genuine spike"],
            })
        # CTR impossibly high
        if ctr is not None and ctr > 25:
            anomalies.append({
                "type": "impossibly_high_ctr",
                "campaign_id": c.get("campaign_id"),
                "severity": "high",
                "title": f"CTR of {ctr:.1f}% on {c.get('name', c.get('campaign_id'))}",
                "value": ctr,
                "possible_causes": ["duplicate events", "wrong click attribution", "bot traffic", "import bug"],
            })
        # Bookings count implausibly high vs spend
        if bookings and spend > 0:
            cpa = spend / bookings
            if cpa < 5 and bookings > 5:
                anomalies.append({
                    "type": "impossibly_low_cpa",
                    "campaign_id": c.get("campaign_id"),
                    "severity": "high",
                    "title": f"Bookings CPA R{cpa:.2f} on {c.get('name', c.get('campaign_id'))} — too good to be true?",
                    "value": cpa,
                    "possible_causes": ["duplicate booking events", "currency issue", "wrong attribution window", "import bug"],
                })
        # Revenue implausibly high
        if revenue and spend > 0:
            roas = revenue / spend
            if roas > 50:
                anomalies.append({
                    "type": "impossibly_high_roas",
                    "campaign_id": c.get("campaign_id"),
                    "severity": "critical",
                    "title": f"ROAS {roas:.0f}× on {c.get('name', c.get('campaign_id'))} — sanity check needed",
                    "value": roas,
                    "possible_causes": ["duplicate revenue events", "currency conversion error", "wrong attribution"],
                })

    return anomalies


# ─── Drift detection ─────────────────────────────────────────────────

def detect_drift(brand_id: str = "swing-shack") -> List[Dict[str, Any]]:
    """Compare this week vs last week. Surface only plausible-measurement-failure
    patterns, not performance changes."""
    # For a real implementation we'd persist weekly snapshots. For now, we use the
    # single snapshot we have + flag the absence of historical comparison as itself
    # an issue.
    state = _load_integrity_state()
    drift_items = []

    # Drift item: measurement lag without historical baseline
    drift_items.append({
        "type": "missing_baseline",
        "severity": "low",
        "title": "No weekly measurement baseline yet",
        "detail": "Drift detection needs 2+ weekly snapshots to compare. Currently have 1.",
        "impact": "Cannot distinguish 'marketing changed' from 'measurement changed' yet.",
        "recommended_action": "Continue running weekly. Drift detection activates after baseline established.",
    })

    return drift_items


# ─── Attribution disagreements ───────────────────────────────────────

def detect_attribution_disagreements(brand_id: str = "swing-shack") -> List[Dict[str, Any]]:
    """When the same metric has multiple values across sources (Meta / GA4 / CRM),
    surface ALL of them without averaging or choosing the biggest.
    Booking system = strongest available commercial evidence."""
    doc = load_spend(brand_id)
    disagreements = []

    # For each campaign with multi-source attribution, surface each source's view
    for c in doc.get("campaigns", []):
        # Performance.attribution_breakdown: optional dict of {source: value}
        breakdown = c.get("attribution_breakdown", {})
        if not breakdown or len(breakdown) < 2:
            continue

        items = []
        for source, value in breakdown.items():
            confidence = "low"
            if source == "booking_system" or source == "crm":
                confidence = "high"
            elif source == "ga4" or source == "utm":
                confidence = "medium"
            elif source == "platform":
                confidence = "low"

            items.append({
                "source": source,
                "value": value,
                "confidence": confidence,
                "what_it_means": {
                    "platform": "Platform self-reports. Often inflated by attribution window choice.",
                    "ga4": "Independent analytics. Reliable for traffic/intent; weaker for conversion.",
                    "utm": "URL-tagged. Reliable IF UTM survives the full booking path.",
                    "booking_system": "Confirmed commercial outcome. Strongest available evidence.",
                    "crm": "First-party customer record. Strongest evidence when UTM/campaign ID survives.",
                }.get(source, "Unknown source."),
            })

        # Sort by commercial weight
        items.sort(key=lambda x: -{"high": 3, "medium": 2, "low": 1}.get(x["confidence"], 0))

        disagreements.append({
            "campaign_id": c.get("campaign_id"),
            "name": c.get("name", c.get("campaign_id")),
            "metric": c.get("metric_under_disagreement", "conversions"),
            "sources": items,
            "strongest_evidence": items[0] if items else None,
            "manager_read": "The systems use different attribution models. Booking system is the strongest available evidence for confirmed commercial outcomes.",
        })

    return disagreements


# ─── Evidence chain health ───────────────────────────────────────────

def evidence_chain(brand_id: str, bet_id: str) -> Dict[str, Any]:
    """Show Meta → UTM → GA4 → Booking path with broken segments."""
    s = load_strategy(brand_id)
    doc = load_spend(brand_id)

    bet = next((b for b in s.get("bets", []) if b["id"] == bet_id), None)
    if not bet:
        return {"error": "bet not found"}

    # Linked campaigns
    campaigns = [c for c in doc.get("campaigns", []) if c.get("strategy_link", {}).get("bet_id") == bet_id]

    # Per-campaign chain check
    chains = []
    for c in campaigns:
        source = c.get("attribution_source", "")
        perf = c.get("performance", {})
        impressions = perf.get("impressions", 0)
        clicks = perf.get("clicks", 0)
        visits = perf.get("visits", 0) or perf.get("booking_visits", 0)
        bookings = perf.get("bookings", 0)

        # Chain status
        meta_ok = impressions > 0
        utm_ok = bool(c.get("utm_tags") or source in ("utm", "ga4"))
        ga4_ok = visits > 0
        booking_ok = bookings > 0

        chain_status = []
        chain_status.append({"node": "Meta", "ok": meta_ok, "value": impressions})
        chain_status.append({"node": "UTM", "ok": utm_ok, "value": "tags present" if utm_ok else "missing"})
        chain_status.append({"node": "GA4", "ok": ga4_ok, "value": visits})
        chain_status.append({"node": "Booking system", "ok": booking_ok, "value": bookings})

        # Find first broken segment
        broken_at = None
        for node in chain_status:
            if not node["ok"]:
                broken_at = node["node"]
                break

        if broken_at:
            overall = "BROKEN"
            last_valid = next((n["node"] for n in reversed(chain_status) if n["ok"]), None)
        elif all(n["ok"] for n in chain_status):
            overall = "HEALTHY"
            last_valid = "Booking system"
        else:
            overall = "PARTIAL"
            last_valid = next((n["node"] for n in reversed(chain_status) if n["ok"]), None)

        chains.append({
            "campaign_id": c.get("campaign_id"),
            "campaign_name": c.get("name", c.get("campaign_id")),
            "chain": chain_status,
            "overall": overall,
            "last_valid_layer": last_valid,
            "broken_at": broken_at,
        })

    # Bet-level summary
    if not chains:
        bet_status = "NO_SPEND"
        bet_last_valid = None
    elif any(c["overall"] == "BROKEN" for c in chains):
        bet_status = "BROKEN"
        bet_last_valid = next((c["last_valid_layer"] for c in chains if c["overall"] == "BROKEN"), "traffic")
    elif any(c["overall"] == "PARTIAL" for c in chains):
        bet_status = "PARTIAL"
        bet_last_valid = next((c["last_valid_layer"] for c in chains if c["overall"] == "PARTIAL"), "traffic")
    else:
        bet_status = "HEALTHY"
        bet_last_valid = "Booking system"

    return {
        "bet_id": bet_id,
        "bet_title": bet.get("title", ""),
        "overall": bet_status,
        "last_valid_layer": bet_last_valid,
        "chains": chains,
    }


# ─── Measurement debt ────────────────────────────────────────────────

def measurement_debt(brand_id: str = "swing-shack") -> Dict[str, Any]:
    """Per-layer status: Healthy / Partial / Broken / Unavailable.
    Plus the 'What would unlock the next claim?' action per layer."""
    state = _load_integrity_state()

    # Aggregate from spend + strategy data
    doc = load_spend(brand_id)
    s = load_strategy(brand_id)

    # Check each layer
    layer_status = {}

    # Attention: do campaigns have impressions?
    active = [c for c in doc.get("campaigns", []) if c.get("status") in ("active", "running")]
    attention_present = any(c.get("performance", {}).get("impressions", 0) > 0 for c in active)
    layer_status["attention"] = {"status": "Healthy" if attention_present else "Unavailable", "label": LAYER_LABELS["attention"]}

    # Traffic: clicks
    traffic_present = any(c.get("performance", {}).get("clicks", 0) > 0 for c in active)
    layer_status["traffic"] = {"status": "Healthy" if traffic_present else "Unavailable", "label": LAYER_LABELS["traffic"]}

    # Intent: visits / booking_visits / form_starts
    intent_present = any(c.get("performance", {}).get("visits", 0) > 0 or c.get("performance", {}).get("booking_visits", 0) > 0 for c in active)
    layer_status["intent"] = {"status": "Healthy" if intent_present else "Unavailable", "label": LAYER_LABELS["intent"]}

    # Leads: leads
    leads_present = any(c.get("performance", {}).get("leads", 0) > 0 for c in active)
    layer_status["lead"] = {"status": "Healthy" if leads_present else "Unavailable", "label": LAYER_LABELS["lead"]}

    # Bookings: bookings present? Tracking set up?
    bookings_present = any(c.get("performance", {}).get("bookings", 0) > 0 for c in active)
    bookings_tracked = any(c.get("attribution_source") in ("booking_system", "crm") for c in active)
    if bookings_present and bookings_tracked:
        layer_status["booking"] = {"status": "Healthy", "label": LAYER_LABELS["booking"]}
    elif bookings_present:
        layer_status["booking"] = {"status": "Partial", "label": LAYER_LABELS["booking"]}
    elif any(c.get("spend_rands", 0) > 0 for c in active):
        # Money is being spent but no booking data — broken
        layer_status["booking"] = {"status": "Broken", "label": LAYER_LABELS["booking"]}
    else:
        layer_status["booking"] = {"status": "Unavailable", "label": LAYER_LABELS["booking"]}

    # Revenue: requires revenue data + CRM
    revenue_present = any(c.get("performance", {}).get("revenue", 0) > 0 for c in active)
    layer_status["revenue"] = {"status": "Healthy" if revenue_present else "Unavailable", "label": LAYER_LABELS["revenue"]}

    # Manager read
    healthy_layers = [k for k, v in layer_status.items() if v["status"] == "Healthy"]
    broken_layers = [k for k, v in layer_status.items() if v["status"] in ("Broken", "Partial")]

    if broken_layers:
        names = ", ".join(layer_status[k]["label"] for k in broken_layers)
        manager_read = f"Marketing can currently optimise confidently for {', '.join(layer_status[k]['label'] for k in healthy_layers) if healthy_layers else 'nothing'}, but not for {names}."
    else:
        manager_read = f"Marketing can currently optimise confidently across all measured layers."

    # What would unlock the next claim?
    unlock = {}
    if layer_status["booking"]["status"] in ("Broken", "Unavailable") and active:
        unlock["booking"] = {
            "action": "Preserve utm_campaign / campaign ID through the booking confirmation event.",
            "impact": "Unlocks the 'this campaign converts' claim.",
        }
    if layer_status["revenue"]["status"] == "Unavailable":
        unlock["revenue"] = {
            "action": "Wire CRM revenue attribution back to campaign ID.",
            "impact": "Unlocks the 'this campaign drives revenue' claim.",
        }
    if layer_status["lead"]["status"] in ("Broken", "Unavailable"):
        unlock["lead"] = {
            "action": "Set up form submission tracking with UTM capture.",
            "impact": "Unlocks the 'this campaign generates leads' claim.",
        }

    # Score: Healthy layers / total
    weights = {"Healthy": 1.0, "Partial": 0.5, "Broken": 0.1, "Unavailable": 0.0}
    total_score = sum(weights.get(v["status"], 0) for v in layer_status.values())
    max_score = len(layer_status)
    score_pct = round(100 * total_score / max_score)

    return {
        "score_pct": score_pct,
        "verdict": "Healthy" if score_pct >= 80 else "Healthy with gaps" if score_pct >= 50 else "Unhealthy",
        "layers": layer_status,
        "manager_read": manager_read,
        "what_would_unlock_next_claim": unlock,
        "strategic_ceiling": layer_status["booking"]["status"],
    }


# ─── Data freshness ──────────────────────────────────────────────────

def data_freshness(brand_id: str = "swing-shack") -> List[Dict[str, Any]]:
    """Per-source 'last updated' indicator. Stale = reduces confidence."""
    state = _load_integrity_state()
    doc = load_spend(brand_id)

    # Each source has a last-update recorded in the doc
    sources = [
        {"source": "Meta Ads", "key": "meta_last_updated"},
        {"source": "GA4", "key": "ga4_last_updated"},
        {"source": "SEO", "key": "seo_last_updated"},
        {"source": "Spend records", "key": "spend_last_updated"},
        {"source": "Booking system", "key": "booking_last_updated"},
        {"source": "IG analytics", "key": "ig_last_updated"},
    ]

    # Try to read from various data files
    freshness = []
    today = datetime.date.today()

    for src in sources:
        last_updated = doc.get(src["key"]) or state.get(src["key"])
        age_days = None
        if last_updated:
            try:
                d = datetime.date.fromisoformat(last_updated[:10])
                age_days = (today - d).days
            except (ValueError, TypeError):
                age_days = None

        status = "fresh"
        if age_days is None:
            status = "unknown"
        elif age_days > 7:
            status = "stale"
        elif age_days > 2:
            status = "aging"

        freshness.append({
            "source": src["source"],
            "last_updated": last_updated,
            "age_days": age_days,
            "status": status,
        })

    # Special case: spend file gets current date on save
    spend_path = Path(__file__).resolve().parents[2] / "data" / f"spend-{brand_id}.json"
    if spend_path.exists():
        mtime = datetime.datetime.fromtimestamp(spend_path.stat().st_mtime).date()
        for f in freshness:
            if f["source"] == "Spend records":
                f["last_updated"] = mtime.isoformat()
                f["age_days"] = (today - mtime).days
                f["status"] = "fresh" if (today - mtime).days < 2 else "aging" if (today - mtime).days < 7 else "stale"

    return freshness


# ─── Data Health (overall score) ─────────────────────────────────────

def data_health(brand_id: str = "swing-shack") -> Dict[str, Any]:
    """Overall data health. Compact display for the company profile.
    Underlying issues matter more than the score."""
    recon = reconcile(brand_id)
    debt = measurement_debt(brand_id)
    freshness = data_freshness(brand_id)

    # Score: combine reconciliation cleanliness + debt score + freshness
    recon_score = 100
    for issue in recon["issues"]:
        sev = issue.get("severity", "low")
        if sev == "critical":
            recon_score -= 30
        elif sev == "high":
            recon_score -= 15
        elif sev == "medium":
            recon_score -= 5
        elif sev == "low":
            recon_score -= 1
    recon_score = max(0, recon_score)

    freshness_score = 100
    for f in freshness:
        if f["status"] == "stale":
            freshness_score -= 15
        elif f["status"] == "aging":
            freshness_score -= 5
        elif f["status"] == "unknown":
            freshness_score -= 5
    freshness_score = max(0, freshness_score)

    # Weighted overall
    overall = round(0.5 * recon_score + 0.3 * debt["score_pct"] + 0.2 * freshness_score)

    if overall >= 90:
        verdict = "Healthy"
    elif overall >= 70:
        verdict = "Healthy with gaps"
    elif overall >= 50:
        verdict = "Weakened"
    else:
        verdict = "Unhealthy"

    # Per-source status for the compact display
    per_source = []
    for f in freshness:
        per_source.append({
            "source": f["source"],
            "status": f["status"],
            "last_updated": f["last_updated"],
            "age_days": f["age_days"],
        })

    return {
        "score": overall,
        "verdict": verdict,
        "components": {
            "reconciliation": {"score": recon_score, "issues": recon["issue_count"]},
            "measurement_debt": {"score": debt["score_pct"], "ceiling": debt["strategic_ceiling"]},
            "freshness": {"score": freshness_score},
        },
        "per_source": per_source,
        "issues": recon["issues"],
        "manager_read": (
            "Marketing can currently trust this data for strategic decisions."
            if overall >= 80
            else f"Some recommendations should carry reduced confidence. {recon['issue_count']} issue(s) pending."
        ),
    }


# ─── Confidence degradation ─────────────────────────────────────────

def degrade_confidence(recommendation: Dict[str, Any], brand_id: str = "swing-shack") -> Dict[str, Any]:
    """When measurement is broken, automatically reduce the confidence of a
    recommendation that relies on it. Mark the recommendation accordingly.

    Strategy: do not show an old High-confidence recommendation while its
    evidence chain is broken.
    """
    recon = reconcile(brand_id)
    debt = measurement_debt(brand_id)

    reasons_to_degrade = []

    # Check if the recommendation relies on a layer that's broken
    rel = recommendation.get("evidence_layer", "")
    if rel and rel in ("booking", "revenue"):
        if debt["layers"].get(rel, {}).get("status") in ("Broken", "Unavailable"):
            reasons_to_degrade.append(f"{rel.capitalize()} attribution is currently unavailable")

    # Check for high-severity issues affecting the relevant bet/campaign
    for issue in recon["issues"]:
        if issue.get("severity") in ("critical", "high"):
            rec_bet_id = recommendation.get("bet_id", "")
            rec_campaign_id = recommendation.get("campaign_id", "")
            if issue.get("bet_id") == rec_bet_id or issue.get("campaign_id") == rec_campaign_id:
                reasons_to_degrade.append(issue.get("title", issue.get("code", "")))

    if not reasons_to_degrade:
        return recommendation

    # Degrade confidence
    current = recommendation.get("confidence", "medium")
    new_confidence = current
    if current == "high":
        new_confidence = "medium"
    if reasons_to_degrade:
        new_confidence = "low"

    recommendation["confidence"] = new_confidence
    recommendation["confidence_degraded"] = True
    recommendation["confidence_degradation_reasons"] = reasons_to_degrade
    return recommendation


# ─── Measurement gap work-tracking ───────────────────────────────────

def add_measurement_gap(brand_id: str, problem: str, strategic_impact: str,
                       priority: str, owner: str = "unassigned") -> Dict[str, Any]:
    """Record a measurement gap as work to be tracked until resolved."""
    state = _load_integrity_state()
    gap = {
        "id": f"gap_{len(state.get('measurement_gaps', [])) + 1}_{_today()}",
        "problem": problem,
        "strategic_impact": strategic_impact,
        "priority": priority,  # critical / high / medium / low
        "owner": owner,
        "status": "open",
        "detected": _today(),
        "resolved": None,
        "age_days": 0,
    }
    state.setdefault("measurement_gaps", []).append(gap)
    _save_integrity_state(state)
    return gap


def resolve_measurement_gap(brand_id: str, gap_id: str, resolution_note: str = "") -> Dict[str, Any]:
    state = _load_integrity_state()
    for g in state.get("measurement_gaps", []):
        if g["id"] == gap_id:
            g["status"] = "resolved"
            g["resolved"] = _today()
            g["resolution_note"] = resolution_note
    _save_integrity_state(state)
    return {"ok": True}


def open_measurement_gaps(brand_id: str = "swing-shack") -> List[Dict[str, Any]]:
    state = _load_integrity_state()
    today = datetime.date.today()
    out = []
    for g in state.get("measurement_gaps", []):
        if g["status"] == "resolved":
            continue
        try:
            d = datetime.date.fromisoformat(g["detected"])
            g["age_days"] = (today - d).days
        except (ValueError, TypeError):
            g["age_days"] = 0
        out.append(g)
    return out


# ─── Historical integrity — corrections ──────────────────────────────

def record_evidence_correction(brand_id: str, bet_id: str, metric: str,
                                original_value: Any, corrected_value: Any,
                                reason: str) -> Dict[str, Any]:
    """Never silently overwrite strategic history. Record the correction."""
    state = _load_integrity_state()
    correction = {
        "id": f"correction_{len(state.get('evidence_corrections', [])) + 1}_{_today()}",
        "bet_id": bet_id,
        "metric": metric,
        "original_value": original_value,
        "corrected_value": corrected_value,
        "reason": reason,
        "recorded_at": _now_iso(),
        "requires_decision_review": True,
    }
    state.setdefault("evidence_corrections", []).append(correction)
    _save_integrity_state(state)
    return correction


def list_corrections(brand_id: str = "swing-shack") -> List[Dict[str, Any]]:
    state = _load_integrity_state()
    return state.get("evidence_corrections", [])


# ─── Render for Monday brief ─────────────────────────────────────────

def render_integrity_warning_section(brand_id: str = "swing-shack") -> Optional[str]:
    """Returns the markdown for the DATA INTEGRITY WARNING section,
    or None if everything is healthy. Silent when healthy."""
    recon = reconcile(brand_id)
    if recon["is_clean"]:
        return None  # Silent

    issues = recon["issues"]
    if not issues:
        return None

    md = []
    md.append("## ⚠ DATA INTEGRITY WARNING")
    md.append("")
    # Show only critical / high + medium that blocks a decision
    relevant = [i for i in issues if i.get("severity") in ("critical", "high")]

    if not relevant:
        return None  # No critical/high — silent

    md.append(f"**{len(relevant)} issue(s) materially affecting conclusions.**")
    md.append("")

    for issue in relevant[:3]:  # Monday brief cap: 3
        md.append(f"### {issue.get('severity', '').title()} — {issue.get('title', '')}")
        md.append("")
        md.append(f"**Problem:** {issue.get('detail', '')}")
        md.append("")
        if issue.get("impact"):
            md.append(f"**Impact on strategy:** {issue['impact']}")
            md.append("")
        if issue.get("recommended_action"):
            md.append(f"**Recommended fix:** {issue['recommended_action']}")
            md.append("")
        if issue.get("actions"):
            md.append(f"**Actions:** {' / '.join(issue['actions'])}")
            md.append("")

    # Mark that affected recommendations carry reduced confidence
    md.append("_Affected recommendations in this brief carry reduced confidence._")
    md.append("")

    return "\n".join(md)


def render_measurement_health_section(brand_id: str = "swing-shack") -> str:
    """Render the MEASUREMENT HEALTH section for the monthly meeting."""
    debt = measurement_debt(brand_id)
    freshness = data_freshness(brand_id)

    md = []
    md.append("### Measurement health")
    md.append("")
    md.append(f"**Overall:** {debt['verdict']} ({debt['score_pct']}%)")
    md.append("")
    for layer_key, info in debt["layers"].items():
        status = info["status"]
        emoji = {"Healthy": "✓", "Partial": "~", "Broken": "✗", "Unavailable": "—"}.get(status, "—")
        md.append(f"- {emoji} **{info['label']}**: {status}")
    md.append("")
    md.append(f"**Manager read:** {debt['manager_read']}")
    md.append("")

    if debt["what_would_unlock_next_claim"]:
        md.append("**What would unlock the next claim:**")
        for layer, action_info in debt["what_would_unlock_next_claim"].items():
            md.append(f"- **{layer.capitalize()}**: {action_info['action']} _({action_info['impact']})_")
        md.append("")

    md.append("**Data freshness:**")
    for f in freshness:
        marker = "⚠" if f["status"] == "stale" else "✓" if f["status"] == "fresh" else "~"
        age = f"{f['age_days']}d ago" if f["age_days"] is not None else "unknown"
        md.append(f"- {marker} {f['source']}: {age}")
    md.append("")

    return "\n".join(md)


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Reconciliation ===")
    recon = reconcile("swing-shack")
    print(f"Issues: {recon['issue_count']}")
    for issue in recon["issues"]:
        print(f"  [{issue['severity']}] {issue['code']}: {issue['title']}")

    print("\n=== Anomalies ===")
    anomalies = detect_anomalies("swing-shack")
    for a in anomalies:
        print(f"  [{a['severity']}] {a['type']}: {a['title']}")

    print("\n=== Measurement Debt ===")
    debt = measurement_debt("swing-shack")
    print(f"Score: {debt['score_pct']}% — {debt['verdict']}")
    print(debt["manager_read"])

    print("\n=== Data Health ===")
    health = data_health("swing-shack")
    print(f"Score: {health['score']} — {health['verdict']}")