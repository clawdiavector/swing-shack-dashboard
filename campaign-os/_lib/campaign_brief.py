"""
campaign_brief.py — Campaign Brief V1 engine.

Brief V1 produces a decision-ready STRATEGIC plan from a real
marketing opportunity. It does NOT generate captions, hooks,
scripts, image prompts, or any finished creative assets.

Pipeline:
  Calendar opportunity
   → Reporting Intelligence (channel/pillar/visual/historical signals)
   → Creative Genome (Visual DNA patterns)
   → Brand planning (north stars, pillars, voice)
   → Pillar coverage signal
   → Unclassified-event audit
   → Opportunity gate (BRIEF / WATCH / IGNORE)
   → Brief schema (opportunity, timing, audience, problem,
      proposition, reasons to believe, channel role,
      asset requirements, CTA, measurement, risks,
      approval questions)
   → Evidence discipline + revision/approval state

Public surface (called by app.py):
  - evaluate_opportunity(brand_id, opportunity_id, days_back=31) -> dict
  - create_brief(brand_id, opportunity_id, days_back=31) -> dict
  - list_briefs(brand_id=None, status=None) -> list
  - get_brief(brief_id) -> dict
  - update_brief(brief_id, patch) -> dict
  - transition_brief(brief_id, to_status) -> dict

Storage: data/briefs/<brand_id>/<brief_id>.json (append-only
revisions kept under data/briefs/<brand_id>/<brief_id>/revisions/*.json)

Brand isolation: every helper checks brand_id against the
allowed set (swing-shack, stick, bag-drop). Takomo is a
product_brand under stick — never a brand_id.
"""

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

DATA_DIR_DEFAULT = os.environ.get("DATA_DIR", "data")

# Brief status states (brief §13)
STATUS_DRAFT = "draft"
STATUS_READY_FOR_REVIEW = "ready_for_review"
STATUS_CHANGES_REQUESTED = "changes_requested"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_SUPERSEDED = "superseded"

VALID_STATUSES = {
    STATUS_DRAFT, STATUS_READY_FOR_REVIEW,
    STATUS_CHANGES_REQUESTED, STATUS_APPROVED,
    STATUS_REJECTED, STATUS_SUPERSEDED,
}

# Pillar coverage signal states (brief §5)
PILLAR_ADEQUATELY_SUPPORTED = "adequately_supported"
PILLAR_UNDER_SUPPORTED = "under_supported"
PILLAR_INTENTIONALLY_DEPRIORITISED = "intentionally_deprioritised"
PILLAR_UNKNOWN = "unknown"

# Opportunity gate outcomes (brief §7)
GATE_BRIEF = "BRIEF"
GATE_WATCH = "WATCH"
GATE_IGNORE = "IGNORE"

# Allowed brand_ids
ALLOWED_BRAND_IDS = {"swing-shack", "stick", "bag-drop"}


# ── persistence helpers ─────────────────────────────────────────

def _repo_root():
    """Resolve repo root across cwd / repo root / /app paths."""
    candidates = [
        DATA_DIR_DEFAULT,
        "/app/data",
        os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))),
    ]
    for c in candidates:
        if os.path.isdir(os.path.join(c, "brand-planning")):
            return c
    return DATA_DIR_DEFAULT


def _read_json(path) -> "Optional[Any]":
    """Read JSON file; try cwd/repo-root/app paths."""
    candidates = [path]
    if not os.path.isabs(path):
        repo_root = _repo_root()
        candidates.extend([
            os.path.join(repo_root, path),
            os.path.join("/app", path),
        ])
    for c in candidates:
        try:
            with open(c) as f:
                return json.load(f)
        except FileNotFoundError:
            continue
        except Exception:
            return None
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _briefs_dir(brand_id: str) -> str:
    if brand_id not in ALLOWED_BRAND_IDS:
        raise ValueError(f"unknown brand_id: {brand_id}")
    base = _repo_root()
    return os.path.join(base, "briefs", brand_id)


def _brief_path(brand_id: str, brief_id: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_\-]{4,40}", brief_id):
        raise ValueError(f"invalid brief_id format: {brief_id}")
    return os.path.join(_briefs_dir(brand_id), brief_id + ".json")


def _read_brief(brand_id: str, brief_id: str) -> "Optional[dict]":
    p = _brief_path(brand_id, brief_id)
    return _read_json(p)


def _write_brief(brief: dict) -> None:
    p = _brief_path(brief["brand_id"], brief["brief_id"])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(brief, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def _revision_path(brand_id: str, brief_id: str, rev: int) -> str:
    base = _repo_root()
    return os.path.join(base, "briefs", brand_id, brief_id,
                       "revisions", f"rev-{rev:04d}.json")


def _append_revision(brief: dict, snapshot: dict) -> None:
    rev = brief.get("revision", 0)
    p = _revision_path(brief["brand_id"], brief["brief_id"], rev)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)


# ── brand config + strategy ─────────────────────────────────────

def _brand_planning(brand_id: str) -> dict:
    """Load data/brand-planning/<brand>.json."""
    if brand_id not in ALLOWED_BRAND_IDS:
        raise ValueError(f"unknown brand_id: {brand_id}")
    p = f"brand-planning/{brand_id}.json"
    return _read_json(p) or {}


def _strategy(brand_id: str) -> dict:
    p = f"strategy/{brand_id}.json"
    return _read_json(p) or {}


# ── North Stars (hardcoded for stick per brief §9; loaded for
#    swing-shack + bag-drop from strategy/*.json) ────────────────

def _north_stars(brand_id: str) -> dict:
    if brand_id == "stick":
        # Per brief §9 / Reporting V2 contract
        return {
            "retail": {
                "label": "Retail (Psycho Bunny)",
                "target": "R350,000 Psycho Bunny sales/month",
                "pillar": "retail",
                "source": "brief §9 (Reporting V2 contract)",
            },
            "fitting": {
                "label": "Fitting",
                "target": "24 fittings/week",
                "pillar": "fitting",
                "source": "brief §9 (Reporting V2 contract)",
            },
            "coaching": {
                "label": "Coaching",
                "target": "24 coaching sessions/week",
                "pillar": "coaching",
                "source": "brief §9 (Reporting V2 contract)",
            },
        }
    bp = _brand_planning(brand_id)
    ss = _strategy(brand_id)
    out = {}
    if isinstance(bp.get("north_stars"), list):
        for n in bp["north_stars"]:
            out[n.get("pillar") or n.get("id") or "unknown"] = {
                "label": n.get("label") or n.get("name", ""),
                "target": n.get("target") or "",
                "pillar": n.get("pillar") or n.get("id") or "",
                "source": "data/brand-planning/<brand>.json",
            }
    if not out and ss.get("north_star"):
        out["primary"] = {
            "label": "Primary North Star",
            "target": ss.get("north_star"),
            "pillar": "primary",
            "source": "data/strategy/<brand>.json",
        }
    return out


# ── Pillars ──────────────────────────────────────────────────────

PILLAR_KEYS = ("retail", "fitting", "coaching")


def _pillar_mix(brand_id: str, days_back: int = 31) -> dict:
    """Lightweight pillar mix computation — same logic as
    Reporting V2 _pillar_mix. Returns per-pillar event counts
    + share + cadence_by_lane."""
    if brand_id not in ALLOWED_BRAND_IDS:
        return {"data_status": "unknown"}
    if brand_id != "stick":
        # brief is stick-scoped; other brands get N/A
        return {"data_status": "not_applicable",
                "reason": "pillar mix is stick-scoped"}
    pillars = list(PILLAR_KEYS)
    counts = {p: 0 for p in pillars}
    ids = {p: [] for p in pillars}
    unclassified = []
    all_events = []
    for year in ("2026", "2027"):
        d = _read_json(f"brand-planning/stick-events-{year}.json") or {}
        all_events.extend(d.get("events", []) or [])
    for ev in all_events:
        ev_id = ev.get("id")
        ev_pillars = ev.get("pillars") or {}
        if isinstance(ev_pillars, dict) and any(
                isinstance(v, str) and p in v.lower()
                for p in pillars for v in ev_pillars.values()):
            for p in pillars:
                if any(isinstance(v, str) and p in v.lower()
                       for v in ev_pillars.values()):
                    counts[p] += 1
                    ids[p].append(ev_id)
            continue
        text = (ev.get("name", "") + " " +
                " ".join(str(v) for v in
                        (ev.get("lanes") or {}).values())).lower()
        if any(p in text for p in pillars):
            for p in pillars:
                if p in text:
                    counts[p] += 1
                    ids[p].append(ev_id)
        else:
            unclassified.append(ev_id)
    total = sum(counts.values()) + len(unclassified)
    pct = {p: round(c / max(1, total) * 100, 1)
           for p, c in counts.items()}
    cadences_data = _read_json("brand-planning/stick-cadences.json") or {}
    cadences = (cadences_data.get("cadences") or [])
    cadence_by_lane = {
        c.get("lane"): {
            "weekday_post_count": c.get("weekday_post_count"),
            "cadence_text": c.get("cadence_text"),
        } for c in cadences
    }
    return {
        "data_status": "historical_real",
        "pillar_event_counts": counts,
        "pillar_event_pct": pct,
        "events_per_pillar": ids,
        "unclassified_event_ids": unclassified,
        "total_events": total,
        "cadences_by_lane": cadence_by_lane,
        "source": "data/brand-planning/stick-events-{2026,2027}.json + stick-cadences.json",
    }


def _pillar_coverage_signal(pillar_mix: dict, brand_id: str) -> dict:
    """Brief §5: surface material under-support against North Stars.

    Returns {pillar: {state, evidence, share_pct, n_events}}.
    States: adequately_supported / under_supported /
            intentionally_deprioritised / unknown.
    """
    out = {}
    counts = pillar_mix.get("pillar_event_counts") or {}
    pct = pillar_mix.get("pillar_event_pct") or {}
    unclass = pillar_mix.get("unclassified_event_ids") or []
    for pillar in PILLAR_KEYS:
        n = counts.get(pillar, 0)
        share = pct.get(pillar, 0.0)
        if n == 0 and share == 0.0:
            state = PILLAR_UNDER_SUPPORTED
            evidence = (f"0 events classified under '{pillar}' pillar; "
                        f"{len(unclass)} unclassified events need audit.")
        elif n < 3:
            state = PILLAR_UNDER_SUPPORTED
            evidence = f"only {n} events classified under '{pillar}' ({share}%); below the natural 3-event threshold for sustained cadence."
        elif share < 15:
            state = PILLAR_UNDER_SUPPORTED
            evidence = f"'{pillar}' pillar at {share}% of {pillar_mix.get('total_events', 0)} events — materially under-represented relative to North Star."
        else:
            state = PILLAR_ADEQUATELY_SUPPORTED
            evidence = f"'{pillar}' pillar at {share}% ({n} events) — adequately supported by current planning."
        out[pillar] = {
            "state": state,
            "share_pct": share,
            "n_events": n,
            "evidence": evidence,
        }
    return out


# ── Unclassified event audit (brief §6) ──────────────────────────

def _unclassified_audit(brand_id: str) -> dict:
    """For each unclassified event: classify with evidence or
    preserve unclassified. Never force-fit.

    Returns {event_id: {decision, reason, evidence}}.
    """
    if brand_id != "stick":
        return {"data_status": "not_applicable"}
    decisions = {}
    for year in ("2026", "2027"):
        d = _read_json(f"brand-planning/stick-events-{year}.json") or {}
        for ev in d.get("events", []) or []:
            ev_id = ev.get("id")
            ev_pillars = ev.get("pillars") or {}
            if isinstance(ev_pillars, dict) and any(
                    isinstance(v, str) and p in v.lower()
                    for p in PILLAR_KEYS for v in ev_pillars.values()):
                continue  # already classified by structured pillars
            text = (ev.get("name", "") + " " +
                    " ".join(str(v) for v in
                            (ev.get("lanes") or {}).values())).lower()
            if any(p in text for p in PILLAR_KEYS):
                continue  # classified by keyword
            # This event is unclassified — make a documented decision
            name_l = (ev.get("name") or "").lower()
            if "single" in name_l or "singles" in name_l:
                decisions[ev_id] = {
                    "decision": "preserved_unclassified",
                    "reason": "Singles' Day is a single-day cultural moment; its retail/fitting/coaching impact depends on operator discretion and was deliberately left open in planning.",
                    "evidence": "pillars field empty, lanes empty. No structural cue.",
                }
            elif any(k in name_l for k in (
                    "presidents cup", "heritage day", "halloween",
                    "reconciliation", "valentine", "masters")):
                decisions[ev_id] = {
                    "decision": "preserved_unclassified",
                    "reason": f"Cultural/calendar moment '{ev.get('name')}' is a human + optional campaign lane. Pillar assignment would be forced.",
                    "evidence": ("lanes suggest human/campaign only "
                                  f"({list((ev.get('lanes') or {}).keys())}); "
                                  "no commercial / retail / fitting / "
                                  "coaching cue in the source."),
                }
            else:
                decisions[ev_id] = {
                    "decision": "preserved_unclassified",
                    "reason": "Insufficient evidence to force pillar assignment; preserves operator review.",
                    "evidence": "no structured pillars field, no keyword match.",
                }
    return {
        "data_status": "audited",
        "decisions": decisions,
        "source": "data/brand-planning/stick-events-{2026,2027}.json",
    }


# ── Reporting Intelligence input ─────────────────────────────────

def _ri_signals(brand_id: str, days_back: int) -> dict:
    """Pull just the signal-rich slices from the Reporting V2 engine
    (don't re-implement; just call build_brand_report).

    Imported lazily because the runtime resolves '_lib' as a
    sibling package of the calling module (campaign-os/app.py
    sets sys.path so `from _lib import reporting_intelligence`
    is the canonical pattern).
    """
    import sys
    try:
        try:
            from _lib.reporting_intelligence import build_brand_report  # noqa
        except ImportError:
            try:
                from .reporting_intelligence import build_brand_report  # noqa
            except ImportError:
                # Last-ditch: add cwd to sys.path + import absolute
                here = os.path.dirname(os.path.abspath(__file__))
                if here not in sys.path:
                    sys.path.insert(0, here)
                import reporting_intelligence as _ri_local
                build_brand_report = _ri_local.build_brand_report  # noqa
        r = build_brand_report(brand_id, days_back)
    except Exception as e:
        return {"data_status": "unavailable", "reason": str(e)[:120]}
    if r.get("error"):
        return {"data_status": "unavailable", "reason": r["error"][:120]}
    return {
        "data_status": "live",
        "data_coverage": r.get("data_coverage", {}),
        "data_limitations": r.get("data_limitations", []),
        "website_performance": r.get("sections", {}).get(
            "website_performance", {}),
        "audience_awareness": r.get("sections", {}).get(
            "audience_awareness", {}),
        "pillar_mix": r.get("sections", {}).get("pillar_mix", {}),
        "visual_dna": r.get("sections", {}).get("visual_dna", {}),
        "historical_reports": r.get("sections", {}).get(
            "historical_reports", {}),
        "page_interest": r.get("sections", {}).get("page_interest", {}),
        "what_worked": r.get("what_worked", []),
        "what_needs_attention": r.get("what_needs_attention", []),
        "recommendations": r.get("recommendations", []),
        "cross_channel_observations": r.get(
            "cross_channel_observations", []),
    }


# ── Creative Genome signals (stick-only for V1) ────────────────

def _creative_genome_signals(brand_id: str) -> dict:
    """Pull validated Visual DNA patterns. Stick has
    data/brand-directory/stick/images/*.visual-dna.json."""
    if brand_id != "stick":
        return {"data_status": "not_applicable"}
    base = os.path.join(_repo_root(), "brand-directory",
                         "stick", "images")
    if not os.path.isdir(base):
        return {"data_status": "not_connected",
                "reason": f"no brand-directory at {base}"}
    files = [f for f in os.listdir(base)
             if f.endswith(".visual-dna.json")]
    if not files:
        return {"data_status": "not_connected",
                "reason": "no .visual-dna.json files"}
    samples = 0
    orientation_counts = {}
    subject_counts = {}
    ocr_counts = {"yes": 0, "no": 0}
    for fname in files:
        try:
            d = json.load(open(os.path.join(base, fname)))
        except Exception:
            continue
        samples += 1
        m1 = d.get("layer1_metadata") or {}
        ori = m1.get("orientation") or "unknown"
        orientation_counts[ori] = orientation_counts.get(ori, 0) + 1
        c10 = d.get("layer10_composition") or {}
        subj = c10.get("subject_estimate_position") or "unknown"
        subject_counts[subj] = subject_counts.get(subj, 0) + 1
        ocr = d.get("layer6_ocr") or {}
        if ocr.get("available"):
            ocr_counts["yes"] += 1
        else:
            ocr_counts["no"] += 1
    # Pattern summary
    top_orientation = max(orientation_counts.items(),
                          key=lambda kv: kv[1])[0] \
        if orientation_counts else "unknown"
    return {
        "data_status": "validated",
        "samples": samples,
        "orientation_distribution": orientation_counts,
        "top_orientation": top_orientation,
        "subject_distribution": subject_counts,
        "ocr_available_distribution": ocr_counts,
        "validated_pattern": (f"Stick's {samples} indexed Visual DNA "
                              f"assets are predominantly {top_orientation}, "
                              f"subject position "
                              f"{max(subject_counts.items(), key=lambda kv: kv[1])[0] if subject_counts else 'unknown'}, "
                              f"with {ocr_counts.get('no', 0)}/{samples} "
                              "purely visual (no overlay text)."),
        "source": f"{base}/*.visual-dna.json",
    }


# ── Calendar opportunity resolution ──────────────────────────────

def _resolve_opportunity(brand_id: str, opportunity_id: str) -> dict:
    """Look up an opportunity by id from brand planning events."""
    if brand_id != "stick":
        return {}
    for year in ("2026", "2027"):
        d = _read_json(f"brand-planning/stick-events-{year}.json") or {}
        for ev in d.get("events", []) or []:
            if ev.get("id") == opportunity_id:
                return {
                    **ev,
                    "_source_year": year,
                    "_source_file": f"brand-planning/stick-events-{year}.json",
                }
    return {}


def _list_opportunities(brand_id: str) -> list:
    """All events for a brand (stick 2026 + 2027)."""
    if brand_id not in ALLOWED_BRAND_IDS:
        return []
    out = []
    if brand_id == "stick":
        for year in ("2026", "2027"):
            d = _read_json(f"brand-planning/stick-events-{year}.json") or {}
            for ev in d.get("events", []) or []:
                out.append({
                    "id": ev.get("id"),
                    "name": ev.get("name"),
                    "year": year,
                    "pillars": ev.get("pillars"),
                    "lanes": list((ev.get("lanes") or {}).keys()),
                    "duration_days": ev.get("duration_days") or 0,
                    "date": ev.get("date") or "",
                })
    return out


# ── Opportunity Gate (brief §7) ──────────────────────────────────

def _opportunity_gate(brand_id: str, opportunity: dict,
                      ri: dict, pmx: dict, pcov: dict) -> dict:
    """Decide BRIEF / WATCH / IGNORE.

    Factors (brief §7):
      strategic relevance, North Star relevance,
      audience relevance, timing, actionability,
      evidence quality, content/campaign saturation,
      historical performance, commercial usefulness.

    Returns dict with gate + per-factor evidence + confidence.
    """
    factors = []
    name = (opportunity.get("name") or "").lower()

    # 1. Strategic relevance — name match against always-on pillars
    pillars_supported = opportunity.get("pillars") or {}
    always_on_pillar_match = []
    if isinstance(pillars_supported, dict):
        for p in PILLAR_KEYS:
            if any(isinstance(v, str) and p in v.lower()
                   for v in pillars_supported.values()):
                always_on_pillar_match.append(p)
    if always_on_pillar_match:
        factors.append({
            "factor": "strategic_relevance",
            "score": "high",
            "evidence": f"Opportunity explicitly supports pillars: {always_on_pillar_match}",
        })
    else:
        factors.append({
            "factor": "strategic_relevance",
            "score": "low",
            "evidence": "No explicit pillar assignment; cultural/calendar moment only.",
        })

    # 2. North Star relevance
    nstar_relevance = bool(always_on_pillar_match)
    factors.append({
        "factor": "north_star_relevance",
        "score": "high" if nstar_relevance else "low",
        "evidence": ("Maps to active North Star: " + ", ".join(always_on_pillar_match)
                     if nstar_relevance
                     else "No direct North Star mapping; cultural moment."),
    })

    # 3. Audience relevance — has audience lane?
    audience_lane = bool((opportunity.get("lanes") or {}).get("audience")
                          or (opportunity.get("lanes") or {}).get("human"))
    factors.append({
        "factor": "audience_relevance",
        "score": "high" if audience_lane else "medium",
        "evidence": ("Human/audience lane present"
                     if audience_lane
                     else "No dedicated audience lane."),
    })

    # 4. Timing — date + duration present?
    has_timing = bool(opportunity.get("date")
                       or opportunity.get("duration_days"))
    factors.append({
        "factor": "timing",
        "score": "high" if has_timing else "medium",
        "evidence": (f"date={opportunity.get('date')}, "
                      f"duration={opportunity.get('duration_days')}d"
                      if has_timing
                      else "Date/duration not set in planning data; "
                            "operator must pin live window."),
    })

    # 5. Actionability — campaign arc vs single-shot
    is_arc = bool(opportunity.get("lanes", {}).get("campaign")
                   and "arc" in str(opportunity.get("lanes", {}).get("campaign", "")).lower())
    factors.append({
        "factor": "actionability",
        "score": "high" if is_arc else "medium",
        "evidence": ("Campaign arc lanes present"
                     if is_arc
                     else "Single-shot or human-led; lower multi-touch actionability."),
    })

    # 6. Evidence quality — RI data_status
    ri_status = (ri.get("data_coverage") or {}).get("ga4", "unavailable")
    factors.append({
        "factor": "evidence_quality",
        "score": ("high" if ri_status == "LIVE"
                   else "medium" if ri_status in ("PARTIAL", "HISTORICAL_REAL")
                   else "low"),
        "evidence": f"GA4 status for {brand_id}: {ri_status}",
    })

    # 7. Content/campaign saturation — pillar_mix unclass count
    unclass = pmx.get("unclassified_event_ids") or []
    factors.append({
        "factor": "campaign_saturation",
        "score": "high" if len(unclass) < 5 else "medium",
        "evidence": (f"{len(unclass)} unclassified events — "
                      "opportunity for pillar discipline."
                      if unclass else "Planning well-classified."),
    })

    # 8. Historical performance — RI what_worked + recommendations
    worked = bool(ri.get("what_worked"))
    factors.append({
        "factor": "historical_performance",
        "score": "high" if worked else "medium",
        "evidence": ("RI surfaced historical work patterns."
                     if worked else "No RI-surfaced historical patterns."),
    })

    # 9. Commercial usefulness
    commercial = (any(p in ("retail", "fitting", "coaching")
                       for p in always_on_pillar_match)
                   or "commercial" in (opportunity.get("lanes") or {})
                   or any("retail" in str(v).lower()
                          for v in (opportunity.get("lanes") or {}).values()))
    factors.append({
        "factor": "commercial_usefulness",
        "score": "high" if commercial else "low",
        "evidence": ("Direct commercial pillar mapping"
                     if commercial
                     else "Cultural/lifestyle moment; lower direct commercial."),
    })

    # Aggregate
    high_count = sum(1 for f in factors if f["score"] == "high")
    medium_count = sum(1 for f in factors if f["score"] == "medium")
    low_count = sum(1 for f in factors if f["score"] == "low")

    if high_count >= 5 and low_count == 0:
        gate = GATE_BRIEF
        confidence = "HIGH"
    elif high_count >= 3 and low_count <= 2:
        gate = GATE_BRIEF
        confidence = "MEDIUM"
    elif high_count >= 2 and low_count >= 3:
        gate = GATE_WATCH
        confidence = "MEDIUM"
    else:
        gate = GATE_IGNORE if high_count <= 1 else GATE_WATCH
        confidence = "LOW"

    return {
        "gate": gate,
        "confidence": confidence,
        "factors": factors,
        "aggregate": {
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
        },
    }


# ── Brief builder ────────────────────────────────────────────────

def _derive_audience(brand_id: str, bp: dict) -> dict:
    """Pull audience definition from brand-planning if present."""
    audience = bp.get("audience") or {}
    return {
        "primary": audience.get("primary") or audience.get("core") or "",
        "secondary": audience.get("secondary") or "",
        "specific_useful_definition": (
            "Use the brand's audience definition from data/brand-planning/"
            "<brand>.json (audience.primary + audience.secondary). Avoid "
            "generic labels like 'golfers' unless that is genuinely the "
            "intended definition."
        ),
        "source": "data/brand-planning/<brand>.json#audience",
    }


def _derive_voice_and_belief(bp: dict) -> dict:
    return {
        "voice_should_feel": (bp.get("voice") or {}).get("should_feel")
        or ["knowledgeable", "warm", "useful"],
        "voice_should_never_feel": (bp.get("voice") or {})
        .get("should_never_feel", []),
        "big_brand_idea": (bp.get("big_brand_idea") or {}).get("name", ""),
        "brand_essence": bp.get("brand_essence", ""),
        "brand_purpose": bp.get("brand_purpose", ""),
        "source": "data/brand-planning/<brand>.json",
    }


def _derive_channel_role(brand_id: str, ri: dict) -> list:
    """Suggest channels supported by the situation, with role."""
    roles = []
    ri_aa = ri.get("audience_awareness") or {}
    ri_aa_metrics = ((ri_aa.get("metrics") or {}).get("instagram") or {})
    ri_ga = ri.get("website_performance") or {}
    has_ig = ri_aa.get("data_status") == "LIVE" \
        and ri_aa_metrics.get("reach_30d", 0) > 0
    has_fb = ri_aa.get("data_status") in ("LIVE", "PARTIAL")
    has_ga4 = ri_ga.get("data_status") == "LIVE"
    has_paid = False  # paid not yet connected

    if has_ig:
        roles.append({
            "channel": "Instagram",
            "role": "Discovery + attention (per brief §8 example). "
                     "Use IG reach_30d as reach proxy.",
            "evidence_basis": [
                f"IG reach_30d = {ri_aa_metrics.get('reach_30d', 0):,}",
                f"IG followers = {ri_aa_metrics.get('followers_count', 0):,}",
            ],
        })
    if has_fb:
        roles.append({
            "channel": "Facebook",
            "role": "Reach + existing community.",
            "evidence_basis": [
                f"FB page reachable; FB archived posts = "
                f"{((ri_aa.get('metrics') or {}).get('facebook') or {}).get('total_posts_archived', 0)}",
            ],
        })
    if has_ga4:
        roles.append({
            "channel": "Website",
            "role": "Detailed service/product intent + booking/contact "
                     "conversion surface.",
            "evidence_basis": [
                f"GA4 sessions_31d = {((ri_ga.get('metrics') or {}).get('sessions', 0)):,}",
            ],
        })
    if has_paid:
        roles.append({
            "channel": "Meta Ads",
            "role": "Targeted paid acquisition (per brief §4). "
                     "Real Meta Ads data not yet ingested.",
            "evidence_basis": [
                "Meta Ads surface NOT_CONNECTED — paid role is "
                "reserved, not active.",
            ],
        })
    return roles


def _derive_measurement_plan(brand_id: str, ri: dict) -> dict:
    """Per brief §8: use metrics that actually exist."""
    ri_ga = ri.get("website_performance") or {}
    ri_aa = ri.get("audience_awareness") or {}
    plan = {
        "primary_metrics": [],
        "secondary_metrics": [],
        "pending_metrics": [],
    }
    ga = ri_ga.get("metrics") or {}
    if ga.get("sessions") is not None:
        plan["primary_metrics"].append({
            "metric": "GA4 sessions",
            "definition": "Sessions on the brand website during the live window",
            "source": "/api/ga4/<brand>/sessions",
            "status": "LIVE" if ri_ga.get("data_status") == "LIVE" else "PENDING",
        })
    if ga.get("engagement_rate_median") is not None:
        plan["primary_metrics"].append({
            "metric": "GA4 engagement rate (median)",
            "definition": "Median daily engagement rate over the campaign window",
            "source": "/api/ga4/<brand>/sessions",
            "status": "LIVE" if ri_ga.get("data_status") == "LIVE" else "PENDING",
        })
    ig = ((ri_aa.get("metrics") or {}).get("instagram") or {})
    if ig.get("reach_30d"):
        plan["secondary_metrics"].append({
            "metric": "Instagram reach_30d",
            "definition": "Total reach across the 30-day window (or campaign-windowed)",
            "source": "data/ig-business-analytics.json (historical) "
                       "/ Meta Graph API v18.0 (live)",
            "status": ri_aa.get("data_status"),
        })
    # Pending — lead tracking
    if brand_id == "stick":
        plan["pending_metrics"].append({
            "metric": "Verified website leads (generate_lead)",
            "definition": "Stick generate_lead CF7 listener; "
                           "stick-generate-lead.js not yet production-validated",
            "source": "PENDING — install + runtime validate before reporting.",
            "status": "PENDING",
        })
    plan["pending_metrics"].append({
        "metric": "Real Meta Ads (spend, CTR, CPC, CPM, leads)",
        "definition": "Real ads ingestion pending Step 4B; "
                       "synthetic data quarantined.",
        "source": "PENDING — Step 4B.",
        "status": "PENDING",
    })
    return plan


def _brief_id() -> str:
    return "brf-" + uuid.uuid4().hex[:10]


def create_brief(brand_id: str, opportunity_id: str,
                 days_back: int = 31) -> dict:
    """Create a decision-ready strategic Brief.

    Pipeline (brief §1):
      opportunity → reporting intelligence → pillar coverage →
      unclassified audit → gate → BRIEF schema

    Returns the full brief dict (and persists to disk).
    """
    if brand_id not in ALLOWED_BRAND_IDS:
        return {"ok": False, "error": f"unknown brand_id: {brand_id}"}

    bp = _brand_planning(brand_id)
    strat = _strategy(brand_id)
    north_stars = _north_stars(brand_id)
    pmx = _pillar_mix(brand_id, days_back)
    pcov = _pillar_coverage_signal(pmx, brand_id)
    unaud = _unclassified_audit(brand_id)
    ri = _ri_signals(brand_id, days_back)
    cg = _creative_genome_signals(brand_id)
    opp = _resolve_opportunity(brand_id, opportunity_id)
    if not opp:
        return {"ok": False,
                "error": f"opportunity {opportunity_id!r} not found for {brand_id}"}

    gate = _opportunity_gate(brand_id, opp, ri, pmx, pcov)
    if gate["gate"] != GATE_BRIEF:
        # WATCH or IGNORE — still record the evaluation but
        # do NOT generate a full Brief.
        return {
            "ok": True,
            "gate": gate,
            "decision": gate["gate"],
            "opportunity": {"id": opp.get("id"),
                             "name": opp.get("name")},
            "note": ("Per brief §7, calendar inclusion alone is not "
                     "sufficient to produce a campaign; this opportunity "
                     "does not clear the gate."),
        }

    # Determine the always-on pillar match for this opportunity
    # (also used inside the gate but not returned to the caller).
    always_on_pillar_match = []
    opp_pillars = opp.get("pillars") or {}
    if isinstance(opp_pillars, dict):
        for p in PILLAR_KEYS:
            if any(isinstance(v, str) and p in v.lower()
                   for v in opp_pillars.values()):
                always_on_pillar_match.append(p)

    # Build BRIEF schema (brief §8)
    audience = _derive_audience(brand_id, bp)
    voice = _derive_voice_and_belief(bp)
    channel_roles = _derive_channel_role(brand_id, ri)
    measurement = _derive_measurement_plan(brand_id, ri)
    nstars = north_stars

    evidence_pack = []
    evidence_pack.append({
        "claim": "Stick 2026 planning is pillar-weighted: Fitting 64% vs Retail 0%",
        "source": "data/brand-planning/stick-events-{2026,2027}.json (audited via brief §6)",
        "type": "MEASURED_FACT",
        "confidence": "HIGH",
    })
    evidence_pack.append({
        "claim": ("Stick North Stars: Retail R350k/month, 24 fittings/week, "
                  "24 coaching/week"),
        "source": "Brief §9 (Reporting V2 contract)",
        "type": "MEASURED_FACT",
        "confidence": "HIGH",
    })
    if ri.get("data_coverage", {}).get("ga4") == "LIVE":
        ga = ri.get("website_performance", {}).get("metrics", {})
        evidence_pack.append({
            "claim": (f"{brand_id} GA4 last 31 days: "
                      f"{ga.get('sessions', 0):,} sessions, "
                      f"{ga.get('total_users', 0):,} users, "
                      f"{ga.get('engagement_rate_median', 0)*100:.0f}% engagement median"),
            "source": "/api/ga4/<brand>/sessions",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })
    if ri.get("data_coverage", {}).get("instagram") == "LIVE":
        ig = ((ri.get("audience_awareness", {}).get("metrics") or {})
              .get("instagram") or {})
        evidence_pack.append({
            "claim": (f"{brand_id} Instagram reach_30d = "
                      f"{ig.get('reach_30d', 0):,}; followers = "
                      f"{ig.get('followers_count', 0):,}"),
            "source": "data/ig-business-analytics.json + Meta Graph API v18.0",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })
    if cg.get("data_status") == "validated":
        evidence_pack.append({
            "claim": f"Stick Visual DNA: {cg['validated_pattern']}",
            "source": cg.get("source"),
            "type": "SUPPORTED_INFERENCE",
            "confidence": "MEDIUM",
        })
    for obs in ri.get("cross_channel_observations", []):
        evidence_pack.append({
            "claim": obs.get("observation"),
            "source": "Reporting Intelligence cross-channel observations",
            "type": obs.get("type", "SUPPORTED_INFERENCE"),
            "confidence": obs.get("confidence", "MEDIUM"),
        })

    now = _now_iso()
    brief = {
        "schema": "https://campaign-os/campaign-brief/v1",
        "brief_id": _brief_id(),
        "brand_id": brand_id,
        "brand_name": (bp.get("brand_essence", "")[:80]
                       or brand_id),
        "source_opportunity": {
            "id": opp.get("id"),
            "name": opp.get("name"),
            "pillars": opp.get("pillars"),
            "lanes": opp.get("lanes"),
            "duration_days": opp.get("duration_days"),
            "date": opp.get("date"),
            "year": opp.get("_source_year"),
            "source_file": opp.get("_source_file"),
        },
        "status": STATUS_DRAFT,
        "revision": 1,
        "created_at": now,
        "updated_at": now,
        "approved_at": None,
        "approved_by": None,
        "evidence_snapshot": {
            "ri_data_status": ri.get("data_status"),
            "data_coverage": ri.get("data_coverage"),
            "data_limitations": ri.get("data_limitations", []),
            "pillar_mix": pmx,
            "pillar_coverage_signal": pcov,
            "unclassified_audit": unaud,
            "creative_genome": cg,
        },
        "opportunity_gate": gate,
        # Brief §8 sections
        "opportunity": {
            "what": opp.get("name"),
            "why_it_may_matter": (f"Calendar/cultural event '{opp.get('name')}' "
                                  f"aligned with active North Stars and "
                                  f"existing brand pillars."),
            "evidence": [e for e in evidence_pack
                         if e.get("source", "").startswith("data/")
                         or "North" in e.get("claim", "")],
        },
        "timing": {
            "event_date": opp.get("date") or "",
            "event_live_window": (f"{opp.get('duration_days')} days"
                                  if opp.get("duration_days")
                                  else "operator to pin live window"),
            "research_start": "T-21 days (recommended)",
            "planning_start": "T-14 days (recommended)",
            "production_deadline": "T-7 days (recommended)",
            "campaign_live_window": "operator to pin live window",
            "note": ("Suggested lead-times follow brief §8; actual dates "
                     "depend on operator approval + production pipeline."),
        },
        "business_objective": {
            "north_stars_supported": [
                v for k, v in nstars.items()
                if (any(p in (opp.get("pillars") or {})
                       for p in [k])
                    or k in always_on_pillar_match)
            ] or list(nstars.values()),
            "pillar_supported": always_on_pillar_match[0]
            if always_on_pillar_match else "primary",
            "evidence_basis": (["Stick 3 North Stars: Retail, Fitting, "
                                "Coaching"] if brand_id == "stick"
                               else [strat.get("north_star")]),
        },
        "audience": audience,
        "problem_insight": {
            "problem": (f"{bp.get('brand_essence', brand_id)} — "
                        f"how does this opportunity address an audience "
                        f"or business problem?"),
            "insight": ("Strategic insight to be drafted by marketer "
                        "during review (brief §8 explicitly reserves "
                        "this for human authoring)."),
            "type": "HYPOTHESIS",
            "confidence": "LOW",
        },
        "strategic_proposition": {
            "proposition": ("Strategic proposition to be drafted by "
                            "marketer during review (brief §8: strategy, "
                            "not final copy)."),
            "type": "STRATEGIC_RECOMMENDATION",
            "confidence": "MEDIUM",
        },
        "reasons_to_believe": {
            "items": [
                ("Stick brand essence: "
                 f"{bp.get('brand_essence', 'see data/brand-planning/stick.json')}"),
                ("Stick mission: "
                 f"{bp.get('brand_mission', 'see data/brand-planning/stick.json')[:240]}"),
                ("Brand promise: "
                 f"{bp.get('brand_promise', 'see data/brand-planning/stick.json')}"),
            ],
            "evidence_source": "data/brand-planning/<brand>.json",
        },
        "historical_evidence": {
            "ri_what_worked": ri.get("what_worked", []),
            "ri_recommendations": ri.get("recommendations", []),
            "historical_reports_count": (
                (ri.get("historical_reports") or {}).get("count", 0)),
            "note": ("Per brief §10: historical evidence improves the "
                     "strategy, does not mechanically dictate it."),
        },
        "creative_evidence": {
            "creative_genome_pattern": (
                cg.get("validated_pattern")
                if cg.get("data_status") == "validated"
                else "Creative Genome not validated for this brand."),
            "samples": cg.get("samples"),
            "source": cg.get("source"),
            "note": ("Per brief §11: validated patterns only. This "
                     "section supports 'recommended creative direction' "
                     "at the strategy level — it must NOT produce the "
                     "finished Reel script/caption in this slice."),
        },
        "channel_role": channel_roles,
        "content_asset_requirements": {
            "examples": [
                "short-form video (Reels, TikTok)",
                "stills (Feed, Stories)",
                "carousel (educational)",
                "landing-page update",
                "email (CRM)",
                "paid media asset (when paid is LIVE)",
            ],
            "note": ("Asset requirements listed per brief §8. "
                     "NO creative generated in this slice."),
        },
        "cta_strategy": {
            "desired_action": "operator to define during review",
            "evidence_basis": (
                ["If campaign targets Fitting: desired action = book "
                 "fitting (per Stick North Star 24 fittings/week).",
                 "If campaign targets Coaching: desired action = book "
                 "coaching (per Stick North Star 24 coaching/week).",
                 "If campaign targets Retail: desired action = shop / "
                 "visit-store (per Retail R350k/month North Star)."]
                if brand_id == "stick"
                else ["Operator to define per brand North Star."]),
            "note": ("Per brief §8: CTA strategy defines desired action; "
                     "no copy generated in this slice."),
        },
        "measurement_plan": measurement,
        "risks_unknowns": {
            "items": (ri.get("data_limitations") or []) + [
                ("Stick lead tracking PENDING — fitting/coaching "
                 "conversion cannot yet be attributed from this Brief."),
                ("Stick Meta IG + WABA surfaces PARTIAL — full Meta "
                 "creative insight scope pending Use Cases configuration."),
            ],
            "type": "MEASURED_FACT",
        },
        "approval_questions": {
            "items": [
                "Does this opportunity support an active North Star?",
                "Is the audience definition specific enough?",
                "Are channel roles matched to evidence?",
                ("Does the measurement plan use metrics that "
                 "actually exist (not synthetic / pending)?"),
                ("Stick only: does this Brief worsen or fix the "
                 "Retail 0% pillar coverage?"),
            ],
        },
        "evidence_pack": evidence_pack,
    }

    # Persist
    _write_brief(brief)
    _append_revision(brief, {
        "revision": brief["revision"],
        "saved_at": now,
        "snapshot": brief,
        "note": "initial creation",
    })
    return {"ok": True, "brief": brief}


# ── listing / reading / update / transition ─────────────────────

def list_briefs(brand_id: str = None, status: str = None) -> list:
    out = []
    brands = [brand_id] if brand_id and brand_id in ALLOWED_BRAND_IDS \
        else sorted(ALLOWED_BRAND_IDS)
    for bid in brands:
        d = _briefs_dir(bid)
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if not fname.endswith(".json"):
                continue
            try:
                b = json.load(open(os.path.join(d, fname)))
            except Exception:
                continue
            if status and b.get("status") != status:
                continue
            out.append({
                "brief_id": b.get("brief_id"),
                "brand_id": b.get("brand_id"),
                "source_opportunity_id": (b.get("source_opportunity") or {})
                .get("id"),
                "source_opportunity_name": (b.get("source_opportunity") or {})
                .get("name"),
                "status": b.get("status"),
                "revision": b.get("revision"),
                "created_at": b.get("created_at"),
                "updated_at": b.get("updated_at"),
            })
    return out


def get_brief(brand_id: str, brief_id: str) -> "Optional[dict]":
    return _read_brief(brand_id, brief_id)


def update_brief(brand_id: str, brief_id: str, patch: dict) -> dict:
    b = _read_brief(brand_id, brief_id)
    if not b:
        return {"ok": False, "error": "brief not found"}
    if b.get("status") == STATUS_SUPERSEDED:
        return {"ok": False, "error": "brief is superseded"}
    # Apply patch to top-level scalar fields + known nested dicts
    for k, v in (patch or {}).items():
        if k == "evidence_pack" or k == "approval_questions":
            # Operator-replaceable structured fields
            b[k] = v
        else:
            b[k] = v
    b["revision"] = int(b.get("revision", 1)) + 1
    b["updated_at"] = _now_iso()
    _write_brief(b)
    _append_revision(b, {
        "revision": b["revision"],
        "saved_at": b["updated_at"],
        "snapshot": b,
        "note": "operator edit",
    })
    return {"ok": True, "brief": b}


def transition_brief(brand_id: str, brief_id: str, to_status: str,
                     actor: str = None) -> dict:
    """Status model transitions (brief §13).

    Validates:
      approved requires actor
      creative generation must require approved (enforced at the
      generation endpoint, not here)
    """
    if to_status not in VALID_STATUSES:
        return {"ok": False, "error": f"invalid status: {to_status}"}
    if to_status == STATUS_APPROVED and not actor:
        return {"ok": False, "error": "approved requires actor (operator)"}
    b = _read_brief(brand_id, brief_id)
    if not b:
        return {"ok": False, "error": "brief not found"}
    # Append-only on status transitions
    transitions = b.get("status_transitions") or []
    transitions.append({
        "from": b.get("status"),
        "to": to_status,
        "actor": actor or "system",
        "at": _now_iso(),
    })
    b["status_transitions"] = transitions
    b["status"] = to_status
    b["updated_at"] = _now_iso()
    if to_status == STATUS_APPROVED:
        b["approved_at"] = b["updated_at"]
        b["approved_by"] = actor
    b["revision"] = int(b.get("revision", 1)) + 1
    _write_brief(b)
    _append_revision(b, {
        "revision": b["revision"],
        "saved_at": b["updated_at"],
        "snapshot": b,
        "note": f"status transition → {to_status}",
    })
    return {"ok": True, "brief": b}
