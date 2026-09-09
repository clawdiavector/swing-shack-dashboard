"""
evidence.py — Evidence Boundary Layer.

The system-wide rule Christelle specified:

  "The OS may only recommend as strongly as the evidence allows."

  engagement → "earns attention"
  clicks     → "drives site traffic"
  visits     → "creates booking intent"
  bookings   → "converts"

Every recommendation in the OS must declare which layer of evidence
it speaks to. Never promote a claim to a stronger layer without data.

The discipline:
  - Every output (insight, brief item, opportunity card, recommendation)
    is wrapped in a 'Claim' that has a max_strength.
  - The claim strength is the WEAKEST layer the data proves.
  - Recommendations cite sources + as_of dates.
  - Confidence is derived from evidence quality, not narrative.
"""

from __future__ import annotations

import json
import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict

# ─── Evidence layers (in increasing strength) ────────────────────────────
LAYERS = {
    "impression": 1,    # saw it (impressions / reach)
    "engagement": 2,    # interacted (likes / comments / saves / engagement rate)
    "click": 3,         # clicked through (CTR / link clicks)
    "visit": 4,         #landed on a key page (booking-page visits)
    "lead": 5,          # expressed intent (form fill, DMs, calls)
    "booking": 6,       # commercial outcome (completed bookings)
    "revenue": 7,       # revenue attribution
}

LAYER_LANGUAGE = {
    "impression": "earns visibility",
    "engagement": "earns attention",
    "click": "drives site traffic",
    "visit": "creates booking intent",
    "lead": "generates qualified leads",
    "booking": "converts",
    "revenue": "drives revenue",
}


def today_iso() -> str:
    return datetime.date.today().isoformat()


# ─── Claim class — every recommendation is one ─────────────────────────────

class Claim:
    """Wraps a recommendation with explicit evidence boundaries."""

    def __init__(self,
                 statement: str,
                 evidence_layer: str,
                 sources: List[Dict[str, str]],
                 confidence: str = "medium",
                 interpretation: str = "",
                 recommended_action: str = "",
                 why_not_stronger: str = ""):
        if evidence_layer not in LAYERS:
            raise ValueError(f"evidence_layer must be one of {list(LAYERS)}")
        self.statement = statement
        self.evidence_layer = evidence_layer
        self.sources = sources  # [{source, value, as_of}]
        self.confidence = confidence
        self.interpretation = interpretation
        self.recommended_action = recommended_action
        self.why_not_stronger = why_not_stronger

    @property
    def language_strength(self) -> str:
        return LAYER_LANGUAGE.get(self.evidence_layer, "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "statement": self.statement,
            "evidence_layer": self.evidence_layer,
            "language_strength": self.language_strength,
            "sources": self.sources,
            "confidence": self.confidence,
            "interpretation": self.interpretation,
            "recommended_action": self.recommended_action,
            "why_not_stronger": self.why_not_stronger or f"We have data only up to '{self.evidence_layer}'. Cannot claim '{LAYER_LANGUAGE.get(self._next_layer(), '')}' without further evidence.",
        }

    def _next_layer(self) -> str:
        current_rank = LAYERS.get(self.evidence_layer, 0)
        for layer, rank in sorted(LAYERS.items(), key=lambda x: x[1]):
            if rank == current_rank + 1:
                return layer
        return self.evidence_layer

    def to_markdown(self) -> str:
        d = self.to_dict()
        md = []
        md.append(f"**Signal:** {d['statement']}")
        if d['sources']:
            src_str = "; ".join(f"{s.get('source', '?')}: {s.get('value', '?')} ({s.get('as_of', '?')})" for s in d['sources'][:3])
            md.append(f"**Why:** {src_str}")
        if d['interpretation']:
            md.append(f"**Interpretation:** {d['interpretation']}")
        md.append(f"**Confidence:** {d['confidence']} ({d['language_strength']})")
        if d['recommended_action']:
            md.append(f"**Recommended action:** {d['recommended_action']}")
        if d['why_not_stronger']:
            md.append(f"_Boundary:_ {d['why_not_stronger']}")
        return "\n".join(md)


# ─── Helpers to derive the strongest honest claim ──────────────────────────────

def claim_from_evidence(data: Dict[str, Any], topic: str) -> Claim:
    """Given evidence data, derive the strongest honest claim.

    data: {
      'impressions': int,
      'engagement_rate': float (pct),
      'clicks': int,
      'visits_to_booking_page': int,
      'leads': int,
      'bookings': int,
      'revenue': float,
      'sources': [{source, value, as_of}]
    }
    """
    sources = data.get("sources") or []
    bookings = data.get("bookings", 0)
    revenue = data.get("revenue", 0)
    leads = data.get("leads", 0)
    visits = data.get("visits_to_booking_page", 0)
    clicks = data.get("clicks", 0)
    engagement = data.get("engagement_rate", 0)
    impressions = data.get("impressions", 0)

    if revenue and bookings:
        layer = "revenue"
        statement = f"{topic} drives revenue ({int(revenue)} ZAR attributed from {int(bookings)} bookings)."
        recommended = f"Scale {topic} — revenue evidence is the strongest available."
    elif bookings:
        layer = "booking"
        statement = f"{topic} converts ({int(bookings)} bookings attributed)."
        recommended = f"Scale {topic} — booking evidence is conclusive."
    elif leads:
        layer = "lead"
        statement = f"{topic} generates qualified leads ({int(leads)})."
        recommended = f"Test scaling {topic}; leads don't guarantee bookings yet."
    elif visits:
        layer = "visit"
        statement = f"{topic} creates booking intent ({int(visits)} booking-page visits)."
        recommended = f"Continue {topic}; booking intent is real but conversion is unmeasured."
    elif clicks:
        layer = "click"
        statement = f"{topic} drives site traffic ({int(clicks)} clicks)."
        recommended = f"Continue testing {topic}; clicks don't yet prove intent."
    elif engagement:
        layer = "engagement"
        statement = f"{topic} earns attention ({engagement}% engagement)."
        recommended = f"Hold judgment; engagement doesn't prove downstream intent."
    elif impressions:
        layer = "impression"
        statement = f"{topic} earns visibility ({int(impressions)} impressions)."
        recommended = f"Await stronger data; impressions are the weakest layer."
    else:
        layer = "impression"
        statement = f"No direct evidence for {topic}."
        recommended = f"Gather engagement data before any conclusion."

    return Claim(
        statement=statement,
        evidence_layer=layer,
        sources=sources,
        confidence=("high" if layer in ("booking", "revenue") else
                    "medium" if layer in ("visit", "lead") else
                    "low"),
        recommended_action=recommended,
    )


# ─── Discipline: never claim beyond the evidence ──────────────────────────────

def safe_claim(topic: str, current_layer: str, target_layer: str) -> Claim:
    """If we have evidence at current_layer, we may only claim up to that.
    Returns a Claim saying we cannot conclude target_layer yet."""
    return Claim(
        statement=f"We have {LAYER_LANGUAGE.get(current_layer, '?')} data for {topic}, not {LAYER_LANGUAGE.get(target_layer, '?')}.",
        evidence_layer=current_layer,
        sources=[],
        confidence="low" if LAYERS.get(current_layer, 0) < LAYERS.get(target_layer, 0) else "high",
        recommended_action=f"Continue measuring; promote to {target_layer} claim once {target_layer} data exists.",
        why_not_stronger=f"Cannot claim '{LAYER_LANGUAGE.get(target_layer, '')}' without {target_layer} data.",
    )


# ─── Portfolio observation builder (with explicit boundaries) ────────────────

def build_portfolio_observation(
    topic: str,
    effort_pct: float,
    demand_evidence: Dict[str, Any],
    sources: List[Dict[str, str]],
    downstream_evidence_layer: str = None,
) -> Claim:
    """Build a Claim-style observation for the portfolio.

    The discipline: effort % is a measurement, demand signals are
    another measurement, and we MUST NOT divide them or invent a
    ratio. We make the inference explicit and conditional.
    """
    has_demand = bool(demand_evidence.get("value"))
    downstream_layer = downstream_evidence_layer or "engagement"

    if not has_demand:
        return Claim(
            statement=f"{topic} represents {effort_pct}% of marketing effort. No demand-side evidence to confirm or deny this is appropriate.",
            evidence_layer="impression",  # effort is an activity count, not a result
            sources=sources,
            confidence="low",
            interpretation="Without demand data we cannot say if this is over- or under-supported.",
            recommended_action="Gather downstream evidence (visits, leads, bookings) before drawing conclusions.",
            why_not_stronger="Effort percentages are an activity measurement; comparing them to a demand metric is not a ratio.",
        )

    # Effort signal
    effort_signal = f"{topic} receives {effort_pct}% of active marketing effort."
    # Demand signal (kept separate)
    demand_label = demand_evidence.get("label") or "the relevant channel"
    demand_value = demand_evidence.get("value")
    demand_source = demand_evidence.get("source", "ga4")
    demand_signal = f"{demand_label} shows {demand_value} (source: {demand_source})."

    # Don't divide; describe the relationship explicitly
    if demand_value and demand_value > 0:
        interpretation = (
            f"Two separate measurements: {effort_signal} {demand_signal} "
            f"This is not a ratio; they measure different things. "
            f"The combination is informative but the inference depends on what we want to prove."
        )
    else:
        interpretation = effort_signal

    # Downstream test — if we only have engagement-layer evidence on the theme
    # we cannot conclude "this converts"; we must say "this earns attention".
    recommended = f"Hold judgment until {downstream_layer}-layer evidence exists for {topic}."

    # Confidence is evidence-quality-based, not narrative-based
    if downstream_layer in ("booking", "revenue"):
        confidence = "high"
    elif downstream_layer in ("visit", "lead"):
        confidence = "medium"
    else:
        confidence = "low"

    return Claim(
        statement=f"{topic}: effort {effort_pct}%; demand signal {demand_value} on {demand_source}.",
        evidence_layer=downstream_layer,
        sources=sources,
        confidence=confidence,
        interpretation=interpretation,
        recommended_action=recommended,
        why_not_stronger=(
            f"Effort and demand are separate measurements, not a ratio. "
            f"Without {downstream_layer}-layer outcome data, we cannot conclude conversion."
        ),
    )


# ─── Confidence-from-evidence helper ─────────────────────────────────────────

def confidence_from_evidence(sources: List[Dict[str, str]], n_unique_sources: int = 0) -> str:
    """Compute confidence from evidence quality, not narrative."""
    if not sources:
        return "low"
    if n_unique_sources == 0:
        n_unique_sources = len({s.get("source") for s in sources if s.get("source")})
    if n_unique_sources >= 3 and len(sources) >= 3:
        return "high"
    if n_unique_sources >= 2 or len(sources) >= 2:
        return "medium"
    return "low"


# ─── Markdown formatter for portfolio watch ───────────────────────────────────

def render_portfolio_watch(observations: List[Claim]) -> str:
    """Render the Portfolio Watch section. Max 2 observations per brief."""
    if not observations:
        return ""
    md = ["### Portfolio watch", ""]
    for i, claim in enumerate(observations[:2], 1):
        md.append(f"**{i}.**")
        md.append(claim.to_markdown())
        md.append("")
    return "\n".join(md)


# ─── Test ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    c = claim_from_evidence({
        "impressions": 1200,
        "engagement_rate": 3.2,
        "clicks": 80,
        "visits_to_booking_page": 35,
        "sources": [
            {"source": "ig-analytics.json", "value": "3.2% engagement, 80 clicks", "as_of": "2026-08-21"},
            {"source": "ga4-metrics.json", "value": "35 /bookings/ visits", "as_of": "2026-08-21"},
        ],
    }, "coaching reels")
    print(c.to_markdown())
    print()
    obs = build_portfolio_observation(
        topic="Conversion",
        effort_pct=57,
        demand_evidence={"label": "/bookings/ visits", "value": 211, "source": "ga4"},
        sources=[{"source": "campaign-data.json", "value": "4 bets tagged conversion", "as_of": "2026-08-21"}],
        downstream_evidence_layer="engagement",
    )
    print(obs.to_markdown())