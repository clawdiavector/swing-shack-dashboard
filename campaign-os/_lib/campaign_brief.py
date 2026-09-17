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


def _briefs_data_dir() -> str:
    """V1.1 §8: durable Brief storage path.

    Per brief §8: durable source = Campaign OS state, NOT /tmp.
    We write to <DATA_DIR>/briefs/ which is volume-mounted
    + persistent across deploys.

    In production, DATA_DIR=/data/campaign-os so briefs
    land at /data/campaign-os/briefs/<brand>/<brief_id>.json
    """
    base = DATA_DIR_DEFAULT
    out = os.path.join(base, "briefs")
    return out


def _briefs_dir(brand_id: str) -> str:
    if brand_id not in ALLOWED_BRAND_IDS:
        raise ValueError(f"unknown brand_id: {brand_id}")
    return os.path.join(_briefs_data_dir(), brand_id)


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
    return os.path.join(_briefs_dir(brand_id), brief_id,
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
    """Load North Stars from the canonical brand strategy /
    calendar_config.json source (V1.2 §5).

    Source of truth: data/brand-directory/<brand_id>/
    calendar_config.json → pillars[].north_star_metric +
    pillars[].north_star_target.

    If a pillar has no North Star target (source=null or
    source_provenance=placeholder, canonical=false), return
    status=unknown / operator_input_required rather than
    silently fall back to stale constants.

    Returns dict keyed by bare pillar name (retail / fitting /
    coaching). Each value carries:
      label, target, pillar, source,
      source_provenance, canonical (bool),
      monthly_target_zar (if applicable),
      status ("configured" | "operator_input_required" | "unknown")
    """
    if brand_id not in ALLOWED_BRAND_IDS:
        return {}
    out = {}
    try:
        mc = _marketing_calendar_import()
        cfg = mc.load_brand_config(brand_id) or {}
    except Exception:
        cfg = {}
    pillars = cfg.get("pillars") or []
    if not pillars:
        # No strategy config — return operator_input_required for
        # each well-known pillar name so the brief engine doesn't
        # silently substitute stale constants.
        for p in PILLAR_KEYS:
            out[p] = {
                "label": p.title(),
                "target": "",
                "pillar": p,
                "source": "data/brand-directory/<brand>/calendar_config.json (NOT FOUND)",
                "source_provenance": "absent",
                "canonical": False,
                "monthly_target_zar": None,
                "status": "operator_input_required",
            }
        return out
    for p_cfg in pillars:
        # Match by canonical pillar ID
        canonical_id = p_cfg.get("pillar_id") or ""
        bare = (canonical_id.split("-")[-1] if "-" in canonical_id
                else canonical_id).lower()
        if bare not in PILLAR_KEYS:
            continue
        nst = p_cfg.get("north_star_target") or {}
        nsm = p_cfg.get("north_star_metric") or ""
        monthly_target_zar = nst.get("monthly_target_zar")
        # Status: configured vs operator_input_required
        if (nst.get("source_provenance", "").startswith("placeholder")
                or "PENDING" in str(nst.get("source", "")).upper()):
            status = "operator_input_required"
        elif nst.get("source"):
            status = "configured"
        else:
            status = "unknown"
        # Format target string. V1.3 §6: prefer the explicit
        # monthly_target_note when present so brand-specific
        # product names (e.g. "Psycho Bunny") survive instead
        # of being generalised to the bare pillar name.
        product_hint = None
        if nsm and "/" in nsm:
            product_hint = nsm.split("/")[0].strip()
        elif p_cfg.get("objective"):
            obj = p_cfg["objective"]
            # Try to extract a brand-specific product hint
            # from phrases like "Drive Psycho Bunny sales"
            # Skip leading verbs so the label stays clean
            # (Psycho Bunny, not "Drive Psycho Bunny").
            import re as _re
            obj_clean = _re.sub(
                r"^(?:Drive|Sell|Promote|Move|Build|Launch|Grow|Boost)\s+",
                "", obj or "")
            m = _re.search(
                r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\b",
                obj_clean)
            if m:
                product_hint = m.group(1)
        if monthly_target_zar:
            # If a product_hint is known (e.g. Psycho Bunny),
            # surface it explicitly so we don't generalise
            # a brand-specific target to the bare pillar.
            if product_hint and product_hint.lower() != (
                    p_cfg.get("name") or "").lower():
                target = (f"R{monthly_target_zar:,} "
                          f"{product_hint} sales/month")
            else:
                target = (f"R{monthly_target_zar:,} "
                          f"{p_cfg.get('name', bare)} sales/month")
        elif nst.get("daily_volume") and nst.get("operating_days_per_week"):
            wk = (nst["daily_volume"]
                  * nst["operating_days_per_week"])
            if product_hint and product_hint.lower() != (
                    p_cfg.get("name") or "").lower():
                target = f"{wk} {product_hint}/week"
            else:
                target = f"{wk} {bare}/week"
        elif nsm:
            target = nsm
        else:
            target = ""
        # V1.3 §6: restore Psycho Bunny label when the
        # objective / metric / monthly_target_note clearly
        # references a specific product (e.g. Psycho Bunny).
        label = p_cfg.get("name") or bare.title()
        if product_hint and product_hint.lower() not in label.lower():
            label = f"{label} ({product_hint})"
        out[bare] = {
            "label": label,
            "target": target,
            "pillar": bare,
            "metric": nsm,
            "product": product_hint,
            "monthly_target_zar": monthly_target_zar,
            "source": ("data/brand-directory/<brand>/"
                       "calendar_config.json (pillars[].north_star_target)"),
            "source_provenance": nst.get("source_provenance") or "",
            "canonical": nst.get("canonical", False),
            "status": status,
        }
    # Always include bare-name keys for the well-known pillars even
    # if they don't appear in the config — mark as unknown.
    for p in PILLAR_KEYS:
        if p not in out:
            out[p] = {
                "label": p.title(),
                "target": "",
                "pillar": p,
                "source": ("data/brand-directory/<brand>/"
                           "calendar_config.json"),
                "source_provenance": "absent",
                "canonical": False,
                "status": "operator_input_required",
            }
    return out


# ── Pillars ──────────────────────────────────────────────────────

PILLAR_KEYS = ("retail", "fitting", "coaching")


def _pillar_mix(brand_id: str, days_back: int = 31) -> dict:
    """Compute content-saturation / pillar mix per brief §12 +
    Brief V1.1 §5-§7 reconciliation.

    Stick has three always-on pillars: RETAIL, FITTING, COACHING.
    Per V1.1 §5: ONE clearly defined denominator — total events
    minus cultural_moments minus preserved_unclassified.

    Per V1.1 §6: classify each event with explicit
    classification_status + classification_reason +
    included_in_pillar_denominator flag.

    Classification rule (documented in V1.1 §6):
      1. If event has structured `pillars` field with the
         pillar key directly → classified
      2. Else if structured pillars values contain pillar
         keyword → classified
      3. Else if event lanes contain pillar keyword → classified
      4. Else if event_key/name is a cultural calendar moment
         (presidents cup, heritage day, etc.) →
         intentionally_non_pillar (excluded from denominator)
      5. Else → preserved_unclassified (excluded from denominator)

    Per V1.1 §2: opportunities come from canonical Calendar
    (marketing_calendar.canonical_records) not from the legacy
    data/brand-planning/<brand>-events-<year>.json files.
    """
    if brand_id not in ALLOWED_BRAND_IDS:
        return {"data_status": "not_applicable"}
    if brand_id != "stick":
        return {"data_status": "not_applicable",
                "reason": "pillar mix is stick-scoped"}
    opps = get_brief_opportunities(brand_id)
    pillars = list(PILLAR_KEYS)
    counts = {p: 0 for p in pillars}
    event_classifications = []
    cultural_moments = []
    preserved_unclassified = []
    cultural_keywords = (
        "presidents cup", "heritage day", "halloween", "reconciliation",
        "day of goodwill", "valentine", "masters", "mothers day",
        "ryder cup", "investec sa open", "singles", "day-of-",
    )

    for opp in opps:
        event_key = opp.get("event_key") or opp.get("id") or ""
        name = (opp.get("name") or "").lower()
        ep = opp.get("pillars") or {}
        lanes = opp.get("lanes") or []
        lane_text = " ".join(str(l) for l in lanes).lower()
        classified_pillar = None
        classification_status = "preserved_unclassified"
        classification_reason = "no pillar key in structured pillars or lane text"

        # 1. Structured pillars: key match (dict)
        if isinstance(ep, dict):
            for p in pillars:
                if p in ep:
                    classified_pillar = p
                    classification_status = "classified_by_structured_pillars_key"
                    classification_reason = f"event has pillars.{p} key"
                    break
            # 2. Structured pillars: value keyword
            if not classified_pillar:
                for p in pillars:
                    if any(isinstance(v, str) and p in v.lower()
                           for v in ep.values()):
                        classified_pillar = p
                        classification_status = "classified_by_structured_pillars_value"
                        classification_reason = f"event pillars value contains '{p}'"
                        break
        # 2b. Structured pillars: list (canonical Calendar schema)
        elif isinstance(ep, list):
            for p in pillars:
                if any(isinstance(v, str) and
                       (p == v or p in v.lower() or
                        v.lower().endswith("-" + p) or
                        v.lower().endswith("-" + p.title()))
                       for v in ep):
                    classified_pillar = p
                    classification_status = "classified_by_structured_pillars_list"
                    classification_reason = (
                        f"event pillars list contains '{p}' "
                        f"(canonical pillar ID match)")
                    break
        # 3. Lane keyword fallback
        if not classified_pillar:
            for p in pillars:
                if p in lane_text:
                    classified_pillar = p
                    classification_status = "classified_by_lane_keyword"
                    classification_reason = f"lane text contains '{p}'"
                    break
        # 4. Cultural moment heuristic
        if not classified_pillar:
            if any(k in name for k in cultural_keywords) \
                    or any(k in event_key.lower() for k in
                           ("day-", "month-", "celebration", "cup",
                            "week-", "open-")):
                classification_status = "intentionally_non_pillar"
                classification_reason = (
                    "cultural / calendar moment with no retail/"
                    "fitting/coaching implication in planning data")
                cultural_moments.append(event_key)
            else:
                preserved_unclassified.append(event_key)

        included_in_denominator = (
            classified_pillar is not None
            and classification_status != "intentionally_non_pillar")
        if included_in_denominator:
            counts[classified_pillar] += 1
        event_classifications.append({
            "event_key": event_key,
            "name": opp.get("name"),
            "classification_status": classification_status,
            "classification_reason": classification_reason,
            "classified_pillar": classified_pillar,
            "included_in_pillar_denominator": included_in_denominator,
        })

    cadences = _read_json("brand-planning/stick-cadences.json") or {}
    cadence_by_lane = {}
    for c in (cadences.get("cadences") or []):
        lane = c.get("lane", "unknown")
        cadence_by_lane[lane] = {
            "weekday_post_count": c.get("weekday_post_count"),
            "cadence_text": c.get("cadence_text"),
        }

    total_events = len(opps)
    classified_total = sum(counts.values())
    excluded = len(cultural_moments) + len(preserved_unclassified)
    denominator = total_events - excluded
    if denominator <= 0:
        denominator = max(1, total_events)
    pillar_pct = {p: round(c / denominator * 100, 1)
                  for p, c in counts.items()}

    return {
        "data_status": "historical_real",
        # V1.1 §5 explicit denominator
        "denominator_used_for_pillar_percentages": denominator,
        "canonical_event_count": total_events,
        "classified_event_count": classified_total,
        "cultural_moment_count": len(cultural_moments),
        "preserved_unclassified_count": len(preserved_unclassified),
        "excluded_event_count": excluded,
        "exclusion_reasons": {
            "cultural_moment": (f"{len(cultural_moments)} events "
                                "explicitly excluded from pillar denominator "
                                "(cultural / calendar moments)"),
            "preserved_unclassified": (f"{len(preserved_unclassified)} "
                                       "events preserved unclassified "
                                       "(insufficient evidence)"),
        },
        "pillar_event_counts": counts,
        "pillar_event_pct": pillar_pct,
        "events_per_pillar": {
            p: [e["event_key"] for e in event_classifications
                if e.get("classified_pillar") == p]
            for p in pillars
        },
        "cultural_moment_event_keys": cultural_moments,
        "preserved_unclassified_event_keys": preserved_unclassified,
        "event_classifications": event_classifications,
        "cadences_by_lane": cadence_by_lane,
        "source": ("marketing_calendar.canonical_records (stick) + "
                   "data/brand-planning/stick-cadences.json"),
    }




def _pillar_coverage_signal(pillar_mix: dict, brand_id: str) -> dict:
    """Brief §5 + V1.1 §6: surface material under-support against
    North Stars. Uses the V1.1 explicit denominator
    (pillar_mix.denominator_used_for_pillar_percentages) and
    distinguishes cultural moments from preserved-unclassified.

    Returns {pillar: {state, evidence, share_pct, n_events,
                       denominator}}.
    States: adequately_supported / under_supported /
            intentionally_deprioritised / unknown.
    """
    out = {}
    counts = pillar_mix.get("pillar_event_counts") or {}
    pct = pillar_mix.get("pillar_event_pct") or {}
    denominator = pillar_mix.get("denominator_used_for_pillar_percentages")
    cultural = pillar_mix.get("cultural_moment_event_keys") or []
    unclass = pillar_mix.get("preserved_unclassified_event_keys") or []
    for pillar in PILLAR_KEYS:
        n = counts.get(pillar, 0)
        share = pct.get(pillar, 0.0)
        if n == 0 and share == 0.0:
            state = PILLAR_UNDER_SUPPORTED
            evidence = (f"0 events classified under '{pillar}' pillar "
                        f"(denominator={denominator}; {len(cultural)} "
                        f"cultural moments excluded, "
                        f"{len(unclass)} preserved unclassified).")
        elif n < 3:
            state = PILLAR_UNDER_SUPPORTED
            evidence = (f"only {n} events classified under '{pillar}' "
                        f"({share}%, denominator={denominator}); "
                        "below the 3-event threshold for sustained "
                        "cadence.")
        elif share < 15:
            state = PILLAR_UNDER_SUPPORTED
            evidence = (f"'{pillar}' pillar at {share}% "
                        f"(denominator={denominator}) — "
                        "materially under-represented relative to "
                        "North Star.")
        else:
            state = PILLAR_ADEQUATELY_SUPPORTED
            evidence = (f"'{pillar}' pillar at {share}% ({n} events, "
                        f"denominator={denominator}) — adequately "
                        "supported by current planning.")
        out[pillar] = {
            "state": state,
            "share_pct": share,
            "n_events": n,
            "denominator": denominator,
            "evidence": evidence,
        }
    return out





# ── Unclassified event audit (brief §6) ──────────────────────────

def _unclassified_audit(brand_id: str) -> dict:
    """For each non-classified event: classify with evidence or
    preserve unclassified. Never force-fit (brief §6 + V1.1 §7).

    Per V1.1 §7: separate four categories with explicit
    classification_status + classification_reason +
    included_in_pillar_denominator flag.

    Reads from canonical Calendar (marketing_calendar) per V1.1 §2.
    The classifications come from _pillar_mix() which already
    applies the documented rule — this audit is the
    operator-facing roll-up.
    """
    if brand_id != "stick":
        return {"data_status": "not_applicable"}
    pmx = _pillar_mix(brand_id)
    ev_classes = pmx.get("event_classifications") or []
    decisions = {}
    for ec in ev_classes:
        event_key = ec.get("event_key") or ""
        status = ec.get("classification_status") or ""
        if status.startswith("classified_"):
            continue  # already classified; not part of audit
        decisions[event_key] = {
            "decision": (status if status in
                          ("intentionally_non_pillar",
                            "preserved_unclassified")
                          else "preserved_unclassified"),
            "reason": ec.get("classification_reason") or "",
            "evidence": (f"name={ec.get('name')!r}, "
                          f"classification_status={status}"),
            "included_in_pillar_denominator":
                ec.get("included_in_pillar_denominator"),
        }
    return {
        "data_status": "audited",
        "decisions": decisions,
        "canonical_event_count": pmx.get("canonical_event_count"),
        "cultural_moment_count": pmx.get("cultural_moment_count"),
        "preserved_unclassified_count":
            pmx.get("preserved_unclassified_count"),
        "source": "marketing_calendar.canonical_records (stick)",
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

def _marketing_calendar_import():
    """Lazy-import the canonical Calendar source (marketing_calendar.py).

    The Brief engine must read from the canonical Calendar
    (one row per event_key, all revisions audit-trailed),
    not from a second competing opportunity list.
    """
    try:
        from _lib import marketing_calendar as mc
        return mc
    except ImportError:
        try:
            from . import marketing_calendar as mc
            return mc
        except ImportError:
            import sys
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import marketing_calendar as mc
            return mc


def get_brief_opportunities(brand_id: str) -> list:
    """Canonical opportunity source for the Brief engine.

    Per brief V1.1 §2: read from the canonical Calendar read
    model (marketing_calendar.canonical_records), not from
    brand-planning events files. Returns calendar records +
    watchlist records, each tagged with `source` so the
    operator can see which stream produced it.

    Falls back gracefully when the canonical Calendar is empty
    (returns [] rather than fabricating)."""
    if brand_id not in ALLOWED_BRAND_IDS:
        return []
    mc = _marketing_calendar_import()
    out = []
    # Canonical calendar records (one per event_key, latest revision)
    try:
        for r in mc.canonical_records(brand_id) or []:
            if r.get("status") == "watchlist":
                continue  # skip watchlist in this loop
            out.append(_map_canonical_to_opportunity(r, "calendar"))
    except Exception:
        pass
    # Canonical watchlist records
    try:
        for r in (mc.canonical_records(brand_id, status_filter="watchlist")
                  or []):
            out.append(_map_canonical_to_opportunity(r, "watchlist"))
    except Exception:
        pass
    return out


def _map_canonical_to_opportunity(r: dict, source: str) -> dict:
    """Map a marketing_calendar record into the Brief engine's
    canonical opportunity shape. event_key is the primary key
    (brief V1.1 §9: dedup protection).

    Per V1.2 §3: read ALL canonical Calendar timing fields
    correctly:
      - date = event_start (canonical Calendar uses event_start
        / event_end, NOT event_date which is the legacy
        planning-file convention)
      - duration_days derived from event_start / event_end
      - year from event_start
      - lead_time + planning_start + production_deadline +
        live_window computed via marketing_calendar's
        compute_lead_time_schedule
      - date_confidence = HIGH (canonical record) | MEDIUM
        (researched but not verified) | LOW (operator pin)
      - source_origin preserved (external / scout / operator)
    """
    event_key = r.get("event_key") or r.get("id") or ""
    event_start = r.get("event_start") or r.get("event_date") or ""
    event_end = r.get("event_end") or ""
    # Derive duration_days
    duration_days = r.get("duration_days") or 0
    if not duration_days and event_start and event_end:
        try:
            ds = datetime.fromisoformat(event_start[:10])
            de = datetime.fromisoformat(event_end[:10])
            duration_days = max(1, (de - ds).days + 1)
        except Exception:
            duration_days = 0
    # Compute lead-time schedule
    lead_time_schedule = None
    lead_time_class = r.get("lead_time_class") or "normal_campaign"
    if event_start:
        try:
            mc = _marketing_calendar_import()
            cfg = mc.load_brand_config(r.get("brand_id") or "")
            lead_time_schedule = mc.compute_lead_time_schedule(
                event_start[:10], lead_time_class, cfg)
        except Exception:
            lead_time_schedule = None
    # Date confidence
    if event_start and event_end and r.get("source_origin") in (
            "external", "scout"):
        date_confidence = "HIGH"
    elif event_start and not event_end:
        date_confidence = "MEDIUM"
    else:
        date_confidence = "LOW"
    return {
        "id": event_key,
        "event_key": event_key,
        "name": r.get("title") or r.get("name") or "",
        "year": (event_start or "")[:4] or "unknown",
        "pillars": r.get("pillars") or {},
        "lanes": list((r.get("lanes") or {}).keys())
        + (["watchlist"] if source == "watchlist" else []),
        "duration_days": duration_days,
        "date": event_start,
        "event_start": event_start,
        "event_end": event_end,
        "live_window": (f"{event_start} → {event_end}"
                        if event_start and event_end
                        else event_start or ""),
        "lead_time_class": lead_time_class,
        "lead_time_schedule": lead_time_schedule,
        "date_confidence": date_confidence,
        "source_origin": r.get("source_origin") or "unknown",
        "source": source,  # "calendar" | "watchlist"
        "disposition": r.get("disposition") or "",
        "status": r.get("status") or "",
        "score": r.get("weighted_score"),
        "calendar_relevance_score": r.get("relevance_score"),
        "calendar_audience_relevance": r.get("audience_relevance"),
        "calendar_commercial_relevance": r.get("commercial_relevance"),
        "calendar_brand_relevance": r.get("brand_relevance"),
        "calendar_confidence": r.get("confidence"),
        # V1.3 §5: surface source_urls + source_authority for
        # gate evidence verification.
        "source_urls": list(r.get("source_urls") or []),
        "source_authority": (r.get("verification_status")
                             or r.get("source_class")
                             or r.get("source_origin")
                             or "unknown"),
    }



def _resolve_opportunity(brand_id: str, opportunity_id: str) -> dict:
    """Look up a canonical opportunity by event_key (or id).

    Brief V1.1 §2: reads from marketing_calendar canonical
    records, not from data/brand-planning/* files."""
    if brand_id not in ALLOWED_BRAND_IDS:
        return {}
    for opp in get_brief_opportunities(brand_id):
        if opp.get("event_key") == opportunity_id \
                or opp.get("id") == opportunity_id:
            return opp
    return {}


def _list_opportunities(brand_id: str) -> list:
    """Canonical opportunity list for a brand (V1.1 §2).

    Backed by marketing_calendar canonical_records; falls back
    to [] when the Calendar has no records."""
    return get_brief_opportunities(brand_id)


# ── Opportunity clustering (V1.3 §3) ─────────────────────────────

def _cluster_opportunities(brand_id: str) -> dict:
    """V1.3 §3: cluster canonical Calendar opportunities that
    substantially share brand + audience + commercial
    objective + time window + CTA.

    Per V1.3 §3: "Do not merge events merely because their
    dates are close." Clustering uses strong evidence of
    shared intent — commercial objective, audience, offer
    context, campaign proposition.

    Returns:
      {
        "clusters": [
          {"cluster_id": ..., "event_keys": [...],
           "shared_signals": ["commercial_objective", ...],
           "rationale": "...",
           "members": [{event_key, role: parent|member, ...}],
           "primary_event_key": "...",
           "secondary_event_keys": ["...", ...]}
        ],
        "standalone_opportunities": ["event_key", ...]
      }
    """
    if brand_id not in ALLOWED_BRAND_IDS:
        return {"clusters": [], "standalone_opportunities": []}
    opps = get_brief_opportunities(brand_id)
    if not opps:
        return {"clusters": [], "standalone_opportunities": []}
    # For each opp, derive cluster signals
    indexed = {}
    for o in opps:
        ek = o.get("event_key") or ""
        # Cluster signals per V1.3 §3
        commercial_objective = _infer_commercial_objective(o, brand_id)
        audience_signal = _infer_audience_signal(o)
        offer_context = _infer_offer_context(o)
        cta_signal = _infer_cta_signal(o)
        time_window = _derive_time_window(o)
        indexed[ek] = {
            "opp": o,
            "commercial_objective": commercial_objective,
            "audience_signal": audience_signal,
            "offer_context": offer_context,
            "cta_signal": cta_signal,
            "time_window": time_window,
        }
    # Greedy clustering: pick seed by highest commercial_objective
    # similarity. Two events cluster if they share at least 3 of:
    # commercial_objective, audience_signal, offer_context,
    # cta_signal, time_window (within 14 days).
    clusters = []
    used = set()
    # Pre-defined cluster seeds we expect:
    #   bag-drop BF + CM = same commercial object ("Festive season
    #     online retail window") + audience (SA traveller online
    #     shopper) + offer context (luggage/travel deals) + CTA
    #     (shop now) + adjacent days
    for ek_a, idx_a in indexed.items():
        if ek_a in used:
            continue
        cluster = {
            "cluster_id": f"cl-{len(clusters)+1:03d}",
            "event_keys": [ek_a],
            "shared_signals": [],
            "members": [
                {"event_key": ek_a, "role": "parent",
                 "event_start": idx_a["opp"].get("event_start"),
                 "event_end": idx_a["opp"].get("event_end"),
                 "name": idx_a["opp"].get("name"),
                 "date_confidence": idx_a["opp"].get("date_confidence"),
                 "commercial_objective": idx_a["commercial_objective"],
                 "audience_signal": idx_a["audience_signal"]},
            ],
            "primary_event_key": ek_a,
            "secondary_event_keys": [],
        }
        for ek_b, idx_b in indexed.items():
            if ek_b == ek_a or ek_b in used:
                continue
            shared = _shared_signals(idx_a, idx_b)
            if len(shared) >= 3:
                cluster["event_keys"].append(ek_b)
                cluster["members"].append({
                    "event_key": ek_b, "role": "member",
                    "event_start": idx_b["opp"].get("event_start"),
                    "event_end": idx_b["opp"].get("event_end"),
                    "name": idx_b["opp"].get("name"),
                    "date_confidence": idx_b["opp"].get("date_confidence"),
                    "commercial_objective": idx_b["commercial_objective"],
                    "audience_signal": idx_b["audience_signal"]})
                cluster["shared_signals"] = shared
                used.add(ek_b)
        if len(cluster["event_keys"]) > 1:
            cluster["secondary_event_keys"] = cluster["event_keys"][1:]
            clusters.append(cluster)
        used.add(ek_a)
    standalone = [ek for ek in indexed if ek not in used]
    return {
        "brand_id": brand_id,
        "clusters": clusters,
        "standalone_opportunities": standalone,
        "cluster_count": len(clusters),
        "standalone_count": len(standalone),
    }


def _infer_commercial_objective(o: dict, brand_id: str) -> str:
    """Per-event commercial objective inferred from pillars +
    source_origin + calendar relevance signals."""
    pillars = o.get("pillars") or []
    if isinstance(pillars, list):
        pillar_strs = [str(p).lower() for p in pillars]
    else:
        pillar_strs = []
    if brand_id == "bag-drop" and any("bags-retail" in p
                                       or "bag-drop" in p
                                       for p in pillar_strs):
        return "festive_season_luggage_retail"
    if brand_id == "stick":
        if any("stick-retail" in p for p in pillar_strs):
            return "psycho_bunny_retail"
        if any("stick-fitting" in p for p in pillar_strs):
            return "club_fitting_service"
        if any("stick-coaching" in p for p in pillar_strs):
            return "coaching_service"
    if brand_id == "swing-shack":
        if any("ss-retail" in p for p in pillar_strs):
            return "ss_retail"
        if any("ss-fitting" in p for p in pillar_strs):
            return "ss_fitting"
        if any("ss-coaching" in p for p in pillar_strs):
            return "ss_coaching"
    return "general"


def _infer_audience_signal(o: dict) -> str:
    name = (o.get("name") or "").lower()
    cal_audience = (o.get("calendar_audience_relevance") or "").lower()
    blob = name + " " + cal_audience
    if any(k in blob for k in ("sa ", "south african", "local")):
        return "sa_local"
    if any(k in blob for k in ("traveller", "travel", "festive")):
        return "sa_traveller"
    if any(k in blob for k in ("golfer", "tour", "championship", "open ")):
        return "serious_golfer"
    if any(k in blob for k in ("family", "parents")):
        return "sa_family"
    if any(k in blob for k in ("holiday", "festive", "school")):
        return "sa_family"
    if any(k in blob for k in ("cultural", "heritage", "cup")):
        return "sa_cultural"
    return "general"


def _infer_offer_context(o: dict) -> str:
    name = (o.get("name") or "").lower()
    if any(k in name for k in ("black friday", "cyber monday", "festive")):
        return "promotional_pricing"
    if any(k in name for k in ("school", "term ", "holiday")):
        return "family_travel_window"
    if any(k in name for k in ("masters", "pga", "dunhill", "nedbank",
                                "open ", "ryder", "presidents cup",
                                "solheim")):
        return "elite_golf_event"
    if any(k in name for k in ("halloween", "valentine", "mothers day",
                                "heritage day", "christmas")):
        return "cultural_moment"
    return "general"


def _infer_cta_signal(o: dict) -> str:
    pillar_strs = []
    pillars = o.get("pillars") or []
    if isinstance(pillars, list):
        pillar_strs = [str(p).lower() for p in pillars]
    if any("retail" in p or "bags-retail" in p or "ss-retail"
           for p in pillar_strs):
        return "shop_visit_store"
    if any("fitting" in p or "ss-fitting" in p for p in pillar_strs):
        return "book_fitting"
    if any("coaching" in p or "ss-coaching" in p for p in pillar_strs):
        return "book_coaching"
    return "general"


def _derive_time_window(o: dict) -> str:
    """Bucket the opportunity by week-of-year for clustering."""
    s = o.get("event_start") or ""
    if not s:
        return "no_date"
    try:
        ds = datetime.fromisoformat(s[:10])
        return f"{ds.year}-W{ds.strftime('%V')}"
    except Exception:
        return "no_date"


def _shared_signals(a: dict, b: dict) -> list:
    """Return the list of cluster signals shared between two
    indexed events. Two events cluster if >=3 shared signals."""
    shared = []
    if a["commercial_objective"] == b["commercial_objective"] \
            and a["commercial_objective"] != "general":
        shared.append("commercial_objective")
    if a["audience_signal"] == b["audience_signal"] \
            and a["audience_signal"] != "general":
        shared.append("audience_signal")
    if a["offer_context"] == b["offer_context"] \
            and a["offer_context"] != "general":
        shared.append("offer_context")
    if a["cta_signal"] == b["cta_signal"] \
            and a["cta_signal"] != "general":
        shared.append("cta_signal")
    # Time window: same week OR within 14 days
    if (a["time_window"] != "no_date"
            and a["time_window"] == b["time_window"]):
        shared.append("time_window_same_week")
    else:
        try:
            sa = a["opp"].get("event_start") or ""
            sb = b["opp"].get("event_start") or ""
            if sa and sb:
                da = datetime.fromisoformat(sa[:10])
                db = datetime.fromisoformat(sb[:10])
                if abs((da - db).days) <= 14:
                    shared.append("time_window_within_14d")
        except Exception:
            pass
    return shared


# ── Opportunity Gate (brief §7 + V1.3 §4 recalibration) ──────────

def _opportunity_gate(brand_id: str, opportunity: dict,
                      ri: dict, pmx: dict, pcov: dict) -> dict:
    """V1.3 §4 recalibrated opportunity gate.

    Two phases:
      Phase 1 — HARD GATES (pre-score filters): any failure
        forces IGNORE immediately. Requires evidence of:
          - strategic relevance (pillar/North Star mapping)
          - business objective relevance
          - audience relevance
          - actionable brand angle
          - timing/action window (date or window set)
          - sufficient evidence (date_confidence + source_origin)
          - non-duplication with existing/clustered opportunity
      Phase 2 — SCORED FACTORS: 9 dimensions. Aggregate
        score maps to BRIEF / WATCH / IGNORE.

    WATCH is a genuinely reachable outcome. Calendar
    inclusion alone is insufficient (brief §7).
    """
    factors = []
    hard_gate_failures = []
    name = (opportunity.get("name") or "").lower()
    event_key = opportunity.get("event_key") or opportunity.get("id") or ""
    date_confidence = (opportunity.get("date_confidence") or "").upper()
    source_origin = (opportunity.get("source_origin") or "").lower()
    source_urls = opportunity.get("source_urls") or []

    # ── Pillar match (strategic relevance) ─────────────────
    pillars_supported = opportunity.get("pillars") or {}
    always_on_pillar_match = []
    if isinstance(pillars_supported, dict):
        for p in PILLAR_KEYS:
            if p in pillars_supported:
                always_on_pillar_match.append(p)
            elif any(isinstance(v, str) and p in v.lower()
                     for v in pillars_supported.values()):
                always_on_pillar_match.append(p)
    elif isinstance(pillars_supported, list):
        for p in PILLAR_KEYS:
            pl = p.lower()
            for v in pillars_supported:
                vs = str(v).lower()
                if (pl == vs or pl in vs
                        or vs.endswith("-" + pl)
                        or vs.endswith("-" + pl.title())):
                    always_on_pillar_match.append(p)
                    break

    # ── North Stars loaded (V1.3 §7 source-of-truth) ────
    nstars = _north_stars(brand_id)
    configured_pillars = [
        k for k, v in (nstars or {}).items()
        if v.get("status") == "configured"
    ]

    # ── Lane keys ──────────────────────────────────────────
    lanes = opportunity.get("lanes") or []
    if isinstance(lanes, dict):
        lane_keys = list(lanes.keys())
    else:
        lane_keys = [str(x) for x in lanes]
    audience_lane = ("audience" in lane_keys
                      or "human" in lane_keys)

    # ── Phase 1: HARD GATES ─────────────────────────────────
    # 1a. strategic relevance
    if not always_on_pillar_match:
        hard_gate_failures.append({
            "gate": "strategic_relevance",
            "reason": ("No pillar mapping in canonical Calendar record "
                       "(hard gate requires explicit pillar assignment "
                       "to an operating brand pillar)"),
        })

    # 1b. business objective relevance — pillar must be a
    # configured pillar with North Star target
    if always_on_pillar_match:
        unconfigured = [p for p in always_on_pillar_match
                        if p not in configured_pillars]
        if unconfigured and brand_id == "swing-shack":
            # SS North Stars are PENDING per calendar_config;
            # this is a soft gate (WATCH, not IGNORE)
            pass

    # 1c. audience relevance — soft gate by default; only
    # hard-fail if NO audience signal at all (no lane, no
    # calendar relevance, no inferred audience from pillar)
    cal_audience = (opportunity.get("calendar_audience_relevance")
                     or "").lower()
    has_audience_signal = (
        audience_lane
        or "high" in cal_audience
        or "very high" in cal_audience
        or bool(always_on_pillar_match))  # pillar match implies audience
    if not has_audience_signal:
        hard_gate_failures.append({
            "gate": "audience_relevance",
            "reason": ("No audience lane, no high-relevance calendar "
                       "audience signal, and no pillar mapping to "
                       "infer audience"),
        })

    # 1d. actionable brand angle — campaign lane OR
    # explicit commercial relevance from calendar
    commercial = (any(p in ("retail", "fitting", "coaching")
                       for p in always_on_pillar_match)
                   or "commercial" in lane_keys
                   or "apparel" in lane_keys
                   or "retail" in lane_keys
                   or "bags-retail" in lane_keys)
    cal_commercial = (opportunity.get("calendar_commercial_relevance")
                       or "").lower()
    has_strong_commercial_signal = (
        commercial
        or "very high" in cal_commercial
        or "high" in cal_commercial)
    if not has_strong_commercial_signal:
        hard_gate_failures.append({
            "gate": "actionable_brand_angle",
            "reason": ("No direct commercial pillar mapping and no "
                       "high commercial relevance from canonical "
                       "Calendar record"),
        })

    # 1e. timing/action window — must have a real date or window
    event_start = opportunity.get("event_start") or opportunity.get("date")
    has_window = bool(event_start)
    if not has_window:
        hard_gate_failures.append({
            "gate": "timing_action_window",
            "reason": "No event_start / date set in canonical Calendar",
        })

    # 1f. sufficient evidence — date_confidence HIGH or MEDIUM
    # AND source_origin in {external, scout, internal_strategy}
    if date_confidence == "LOW":
        hard_gate_failures.append({
            "gate": "sufficient_evidence",
            "reason": (f"date_confidence=LOW ({source_origin}); "
                       "V1.3 §4 requires HIGH or MEDIUM for BRIEF"),
        })
    if source_origin not in ("external", "scout", "internal_strategy",
                              "internal_strategy_deprecated"):
        hard_gate_failures.append({
            "gate": "sufficient_evidence",
            "reason": (f"source_origin={source_origin!r}; V1.3 §4 "
                       "requires external/scout/internal_strategy "
                       "for BRIEF"),
        })
    if not source_urls and source_origin == "external":
        # External origin with no source_urls is suspicious
        hard_gate_failures.append({
            "gate": "sufficient_evidence",
            "reason": ("source_origin=external but no source_urls "
                       "recorded — provenance is incomplete"),
        })

    # 1g. non-duplication — if this event_key is in a cluster,
    # only the cluster_parent is BRIEF-eligible (cluster members
    # are watched rather than independently briefed)
    cluster = _find_opp_cluster(brand_id, event_key)
    is_cluster_member_only = (
        cluster is not None
        and event_key != cluster.get("primary_event_key"))

    # If any hard gate failed → IGNORE
    if hard_gate_failures:
        factors.extend({
            "factor": f["gate"],
            "score": "low",
            "evidence": f["reason"],
        } for f in hard_gate_failures)
        return {
            "gate": GATE_IGNORE,
            "confidence": "LOW",
            "factors": factors,
            "aggregate": {
                "high_count": 0,
                "medium_count": 0,
                "low_count": len(factors),
            },
            "hard_gate_failures": hard_gate_failures,
            "note": (f"Failed {len(hard_gate_failures)} hard gate(s); "
                     "Brief creation refused until evidence is "
                     "remediated."),
        }

    # ── Phase 2: SCORED FACTORS ──────────────────────────────
    if always_on_pillar_match:
        factors.append({
            "factor": "strategic_relevance",
            "score": "high",
            "evidence": (f"Opportunity supports pillars: "
                         f"{always_on_pillar_match}"),
        })
    nstar_relevance = bool(always_on_pillar_match)
    factors.append({
        "factor": "north_star_relevance",
        "score": "high" if nstar_relevance else "low",
        "evidence": (f"Maps to active North Star: "
                     f"{', '.join(always_on_pillar_match)}"
                     if nstar_relevance
                     else "No direct North Star mapping."),
    })
    factors.append({
        "factor": "audience_relevance",
        "score": "high" if audience_lane else "medium",
        "evidence": ("Human/audience lane present"
                     if audience_lane
                     else "Audience signal from Calendar record."),
    })
    factors.append({
        "factor": "timing",
        "score": ("high" if date_confidence == "HIGH"
                   else "medium" if date_confidence == "MEDIUM"
                   else "low"),
        "evidence": (f"event_start={event_start}, "
                      f"date_confidence={date_confidence}, "
                      f"source_origin={source_origin}"),
    })
    is_arc = ("campaign" in lane_keys
              and any("arc" in str(l).lower() for l in lane_keys))
    factors.append({
        "factor": "actionability",
        "score": "high" if is_arc else "medium",
        "evidence": ("Campaign arc lanes present"
                     if is_arc
                     else "Single-shot or human-led; lower multi-touch "
                          "actionability."),
    })
    ri_status = (ri.get("data_coverage") or {}).get("ga4", "unavailable")
    factors.append({
        "factor": "evidence_quality",
        "score": ("high" if ri_status == "LIVE"
                   else "medium" if ri_status in ("PARTIAL",
                                                    "HISTORICAL_REAL")
                   else "low"),
        "evidence": f"GA4 status for {brand_id}: {ri_status}",
    })
    cultural_n = len(pmx.get("cultural_moment_event_keys") or [])
    unclass_n = len(pmx.get("preserved_unclassified_event_keys") or [])
    factors.append({
        "factor": "campaign_saturation",
        "score": ("high" if (cultural_n + unclass_n) < 5
                   else "medium"),
        "evidence": (f"{cultural_n} cultural moments + "
                      f"{unclass_n} preserved unclassified."),
    })
    worked = bool(ri.get("what_worked"))
    factors.append({
        "factor": "historical_performance",
        "score": "high" if worked else "medium",
        "evidence": ("RI surfaced historical work patterns."
                     if worked else "No RI-surfaced historical patterns."),
    })
    factors.append({
        "factor": "commercial_usefulness",
        "score": "high" if commercial else "low",
        "evidence": ("Direct commercial pillar mapping"
                     if commercial
                     else "Cultural/lifestyle moment."),
    })

    # ── Aggregate + cluster handling ─────────────────────────
    high_count = sum(1 for f in factors if f["score"] == "high")
    medium_count = sum(1 for f in factors if f["score"] == "medium")
    low_count = sum(1 for f in factors if f["score"] == "low")

    # V1.3 §3: cluster members default to WATCH
    if is_cluster_member_only:
        gate = GATE_WATCH
        confidence = "MEDIUM"
        factors.append({
            "factor": "cluster_membership",
            "score": "low",
            "evidence": (f"Clustered under {cluster.get('primary_event_key')}; "
                         f"Brief is generated for the cluster parent."),
        })
        cluster_note = (f"Cluster member under {cluster.get('primary_event_key')}; "
                        "watchlist until parent brief created.")
    else:
        cluster_note = None
        # V1.3 §4 stricter thresholds: require >=4 high AND <=1 low
        if high_count >= 5 and low_count == 0:
            gate = GATE_BRIEF
            confidence = "HIGH"
        elif high_count >= 4 and low_count <= 1:
            gate = GATE_BRIEF
            confidence = "MEDIUM"
        elif high_count >= 3 and low_count <= 2:
            gate = GATE_WATCH
            confidence = "MEDIUM"
        elif high_count >= 2 and low_count <= 3:
            gate = GATE_WATCH
            confidence = "LOW"
        else:
            gate = GATE_IGNORE
            confidence = "LOW"

    out = {
        "gate": gate,
        "confidence": confidence,
        "factors": factors,
        "aggregate": {
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
        },
    }
    if cluster_note:
        out["cluster_note"] = cluster_note
    return out


def _find_opp_cluster(brand_id: str, event_key: str) -> "Optional[dict]":
    """V1.3 §3 helper: find the cluster (if any) that this
    event_key belongs to. Returns the cluster dict or None."""
    if not event_key:
        return None
    clusters = _cluster_opportunities(brand_id).get("clusters") or []
    for cl in clusters:
        if event_key in cl.get("event_keys", []):
            return cl
    return None




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
                 days_back: int = 31,
                 force: bool = False) -> dict:
    """Create a decision-ready strategic Brief.

    Pipeline (brief §1 + V1.1 §1):
      1. Resolve opportunity from canonical Calendar
      2. Run opportunity gate (BRIEF / WATCH / IGNORE)
      3. Refuse creation for IGNORE (V1.1 §9)
      4. For WATCH: return gate decision but no Brief
      5. Check duplicate Brief for (brand + event_key)
      6. For BRIEF: pull reporting intelligence,
         pillar coverage, unclassified audit
      7. Generate evidence-backed system drafts
         (problem_insight, strategic_proposition, CTA)
         with explicit provenance + editable by operator
      8. Persist brief + revision

    Returns {"ok": True, "brief": ...} for BRIEF,
            {"ok": True, "decision": "WATCH"|"IGNORE", ...}
            for gate-rejected opportunities.

    V1.1 §11: creative_allowed is a readiness flag.
    False until status=approved.
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

    # Gate evaluation (always run, regardless of duplicate)
    gate = _opportunity_gate(brand_id, opp, ri, pmx, pcov)
    if gate["gate"] == GATE_IGNORE:
        return {
            "ok": True,
            "decision": GATE_IGNORE,
            "gate": gate,
            "opportunity": {"id": opp.get("id"),
                             "name": opp.get("name")},
            "note": ("Per V1.1 §9, IGNORE opportunities are refused "
                     "for Brief creation; operator can still proceed "
                     "by force=True if they want to override."),
        }
    if gate["gate"] == GATE_WATCH:
        return {
            "ok": True,
            "decision": GATE_WATCH,
            "gate": gate,
            "opportunity": {"id": opp.get("id"),
                             "name": opp.get("name")},
            "note": ("Per V1.1 §9, WATCH opportunities remain "
                     "watchlisted rather than automatically creating "
                     "a Brief. Operator can force=True to override."),
        }

    # Duplicate protection (V1.1 §9)
    event_key = opp.get("event_key") or opp.get("id")
    existing = _find_active_brief(brand_id, event_key)
    if existing and not force:
        return {
            "ok": False,
            "error": (f"a Brief already exists for {brand_id} + "
                      f"{event_key} (brief_id={existing['brief_id']}, "
                      f"status={existing['status']}); pass force=True "
                      "to create a replacement/superseding Brief."),
            "existing_brief": {
                "brief_id": existing["brief_id"],
                "status": existing["status"],
                "revision": existing.get("revision"),
            },
        }

    # Determine the always-on pillar match for this opportunity
    always_on_pillar_match = []
    opp_pillars = opp.get("pillars") or {}
    if isinstance(opp_pillars, dict):
        for p in PILLAR_KEYS:
            if p in opp_pillars:
                always_on_pillar_match.append(p)
            elif any(isinstance(v, str) and p in v.lower()
                     for v in opp_pillars.values()):
                always_on_pillar_match.append(p)
    elif isinstance(opp_pillars, list):
        # Match against canonical pillar IDs (e.g. 'stick-retail')
        for p in PILLAR_KEYS:
            pl = p.lower()
            for v in opp_pillars:
                vs = str(v).lower()
                if (pl == vs or pl in vs
                        or vs.endswith("-" + pl)
                        or vs.endswith("-" + pl.title())):
                    always_on_pillar_match.append(p)
                    break

    # Build BRIEF schema
    audience = _derive_audience(brand_id, bp)
    voice = _derive_voice_and_belief(bp)
    channel_roles = _derive_channel_role(brand_id, ri)
    measurement = _derive_measurement_plan(brand_id, ri)
    nstars = north_stars

    # Evidence-backed system drafts (V1.1 §10)
    system_drafts = _generate_system_drafts(
        brand_id, opp, ri, pmx, pcov, always_on_pillar_match, bp)

    # Evidence pack
    evidence_pack = []
    evidence_pack.append({
        "claim": (f"{brand_id} canonical Calendar opportunity: "
                  f"{opp.get('name')} (event_key={event_key})"),
        "source": "marketing_calendar.canonical_records",
        "type": "MEASURED_FACT",
        "confidence": "HIGH",
    })
    evidence_pack.append({
        "claim": (f"{brand_id} pillar mix (V1.1 denominator): "
                  f"canonical={pmx.get('canonical_event_count')}, "
                  f"classified={pmx.get('classified_event_count')}, "
                  f"cultural_moments={pmx.get('cultural_moment_count')}, "
                  f"preserved_unclassified="
                  f"{pmx.get('preserved_unclassified_count')}, "
                  f"denominator={pmx.get('denominator_used_for_pillar_percentages')}"),
        "source": "marketing_calendar.canonical_records (stick) + brand-planning/stick-cadences.json",
        "type": "MEASURED_FACT",
        "confidence": "HIGH",
    })
    evidence_pack.append({
        "claim": ("Stick North Stars: Retail R350k/month, "
                  "24 fittings/week, 24 coaching/week"),
        "source": "Brief V1 §9 (Reporting V2 contract)",
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
            "event_key": event_key,
            "id": event_key,
            "name": opp.get("name"),
            "pillars": opp.get("pillars"),
            "lanes": opp.get("lanes"),
            "duration_days": opp.get("duration_days") or 0,
            "date": opp.get("date") or "",
            "year": str(opp.get("date") or "")[:4] or "unknown",
            "source": opp.get("source", "calendar"),
        },
        "status": STATUS_DRAFT,
        "revision": 1,
        "created_at": now,
        "updated_at": now,
        "approved_at": None,
        "approved_by": None,
        "creative_allowed": False,  # V1.1 §11: only true when status=approved
        "evidence_snapshot": {
            "ri_data_status": ri.get("data_status"),
            "data_coverage": ri.get("data_coverage"),
            "data_limitations": ri.get("data_limitations", []),
            "pillar_mix": pmx,
            "pillar_coverage_signal": pcov,
            "unclassified_audit": unaud,
            "creative_genome": cg,
            "source_of_truth": "marketing_calendar.canonical_records",
        },
        "opportunity_gate": gate,
        # Brief §8 sections
        "opportunity": {
            "what": opp.get("name"),
            "why_it_may_matter": (f"Calendar/cultural event '{opp.get('name')}' "
                                  f"(event_key={event_key}) aligned with "
                                  f"active North Stars and existing "
                                  f"brand pillars."),
            "evidence": [e for e in evidence_pack
                         if e.get("source", "").startswith("data/")
                         or "North" in e.get("claim", "")
                         or "Calendar" in e.get("claim", "")],
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
        "problem_insight": system_drafts["problem_insight"],
        "strategic_proposition": system_drafts["strategic_proposition"],
        "cta_strategy": system_drafts["cta_strategy"],
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
        # V1.1 §10: provenance of every draftable field
        "field_provenance": {
            "problem_insight": {
                "drafted_by": "system_draft",
                "editable": True,
                "human_override_required_for_approval": False,
            },
            "strategic_proposition": {
                "drafted_by": "system_draft",
                "editable": True,
                "human_override_required_for_approval": False,
            },
            "cta_strategy": {
                "drafted_by": "system_draft",
                "editable": True,
                "human_override_required_for_approval": False,
            },
        },
    }

    # Persist
    _write_brief(brief)
    _append_revision(brief, {
        "revision": brief["revision"],
        "saved_at": now,
        "snapshot": brief,
        "note": "initial creation",
        "drafted_by": "system",
    })
    return {"ok": True, "brief": brief}


def _find_active_brief(brand_id: str, event_key: str) -> "Optional[dict]":
    """V1.1 §9: find existing brief for (brand, event_key) that's
    NOT superseded. Returns the brief dict or None."""
    if not event_key:
        return None
    for b in list_briefs(brand_id):
        # Match on brief_id containing event_key, or source_opportunity.event_key
        # Read the actual brief to compare precisely
        bid = b.get("brief_id")
        full = _read_brief(brand_id, bid)
        if not full:
            continue
        src = full.get("source_opportunity") or {}
        if src.get("event_key") != event_key:
            continue
        if full.get("status") == STATUS_SUPERSEDED:
            continue
        return full
    return None


def _generate_system_drafts(brand_id, opp, ri, pmx, pcov,
                              always_on_pillar_match, bp) -> dict:
    """V1.1 §10: produce evidence-backed draft strategy fields.

    These are drafts, not final copy. They are grounded in the
    Reporting Intelligence signals + brand planning data so the
    operator does not have to write the entire strategic thinking
    from scratch. The operator can edit or replace them via PATCH
    before approval.
    """
    pillar_supported = (always_on_pillar_match[0]
                        if always_on_pillar_match else "primary")
    nstars_supported = list(always_on_pillar_match) or ["primary"]
    ga_metrics = ((ri.get("website_performance") or {}).get("metrics")
                  or {})
    ig_metrics = (((ri.get("audience_awareness") or {}).get("metrics")
                   or {}).get("instagram") or {})
    # problem_insight draft
    if pillar_supported == "retail":
        problem_text = (f"{brand_id} needs verified website traffic "
                        "attributable to retail purchase intent.")
    elif pillar_supported == "fitting":
        problem_text = (f"{brand_id} needs website interest that "
                        "converts to fitting bookings (24/week target).")
    elif pillar_supported == "coaching":
        problem_text = (f"{brand_id} needs website interest that "
                        "converts to coaching sessions (24/week target).")
    else:
        problem_text = (f"{brand_id} audience engagement is "
                        "growing but commercial conversion is "
                        "not yet measured.")

    ga_session_line = ""
    if ga_metrics.get("sessions"):
        ga_session_line = (f" GA4 reports {ga_metrics.get('sessions', 0):,} "
                           f"sessions over the last 31 days with "
                           f"{ga_metrics.get('engagement_rate_median', 0)*100:.0f}% "
                           "engagement median.")
    ig_reach_line = ""
    if ig_metrics.get("reach_30d"):
        ig_reach_line = (f" Instagram reach_30d is "
                         f"{ig_metrics.get('reach_30d', 0):,}.")

    # strategic_proposition draft
    if pillar_supported == "retail":
        prop_text = ("Promote the retail North Star via the strongest-"
                    "performing format from Visual DNA + cross-channel "
                    "engagement, with retail-specific CTAs to drive "
                    "store and online sales.")
    elif pillar_supported == "fitting":
        prop_text = ("Lead with fitting education content matched to "
                    "Visual DNA patterns (10 sampled assets, predominantly "
                    "portrait), driving qualified traffic to fitting "
                    "landing pages.")
    elif pillar_supported == "coaching":
        prop_text = ("Lead with coaching-led content matched to the "
                    "Visual DNA creative genome, driving qualified "
                    "traffic to coaching landing pages.")
    else:
        prop_text = ("Lead with culturally relevant content aligned "
                    "with brand voice and Creative Genome patterns.")

    # cta_strategy draft
    if pillar_supported == "retail":
        cta_text = ("Book a store visit / shop online — measure via "
                    "retail revenue attribution once verified.")
    elif pillar_supported == "fitting":
        cta_text = ("Book a fitting — measure via fitting-page sessions, "
                    "form starts, and (when LIVE) generate_lead "
                    "conversions.")
    elif pillar_supported == "coaching":
        cta_text = ("Book a coaching session — measure via coaching-page "
                    "sessions, form starts, and (when LIVE) "
                    "generate_lead conversions.")
    else:
        cta_text = "Operator to define during review."

    return {
        "problem_insight": {
            "problem": problem_text + ga_session_line + ig_reach_line,
            "insight": ("Strategic insight grounded in current data: "
                        "if engagement is steady but conversion is "
                        "unmeasurable, the immediate next move is "
                        "to verify lead tracking + strengthen "
                        "intent-aligned CTAs."),
            "type": "SUPPORTED_INFERENCE",
            "confidence": "MEDIUM",
            "drafted_by": "system",
            "drafted_at": _now_iso(),
            "evidence_basis": [
                "Pillar match: " + ", ".join(nstars_supported),
                (f"GA4 sessions = {ga_metrics.get('sessions', 0):,}"
                 if ga_metrics.get("sessions") else
                 "GA4 sessions = unavailable"),
                (f"IG reach_30d = {ig_metrics.get('reach_30d', 0):,}"
                 if ig_metrics.get("reach_30d") else
                 "IG reach_30d = unavailable"),
            ],
            "operator_editable": True,
        },
        "strategic_proposition": {
            "proposition": prop_text,
            "type": "STRATEGIC_RECOMMENDATION",
            "confidence": "MEDIUM",
            "drafted_by": "system",
            "drafted_at": _now_iso(),
            "evidence_basis": [
                f"Pillar match: {pillar_supported}",
                "Visual DNA validated pattern (Stick 10 sampled assets)",
                "Reporting Intelligence cross-channel observations",
            ],
            "operator_editable": True,
        },
        "cta_strategy": {
            "desired_action": cta_text,
            "evidence_basis": [
                (f"Pillar target: {pillar_supported} "
                 + str(nstars_supported)),
                "Reporting Intelligence measurement plan",
            ],
            "drafted_by": "system",
            "drafted_at": _now_iso(),
            "operator_editable": True,
            "note": ("Per brief §8: CTA strategy defines desired action; "
                     "no copy generated in this slice."),
        },
    }





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


def update_brief(brand_id: str, brief_id: str, patch: dict,
                 actor: str = "operator") -> dict:
    """V1.1 §10: PATCH the brief. Tracks operator_edit provenance.

    Allowed patch fields include any subsection (problem_insight,
    strategic_proposition, cta_strategy, etc.) plus top-level
    scalar fields. Field_provenance records the change.
    """
    b = _read_brief(brand_id, brief_id)
    if not b:
        return {"ok": False, "error": "brief not found"}
    if b.get("status") == STATUS_SUPERSEDED:
        return {"ok": False, "error": "brief is superseded"}
    # Track which draftable fields are being edited (V1.1 §10)
    field_provenance = b.get("field_provenance") or {}
    edit_log = b.get("edit_log") or []
    edit_entry = {
        "at": _now_iso(),
        "actor": actor,
        "fields_edited": list((patch or {}).keys()),
    }
    for k, v in (patch or {}).items():
        if k in ("problem_insight", "strategic_proposition",
                 "cta_strategy"):
            field_provenance[k] = {
                "drafted_by": "operator_edit",
                "editable": True,
                "human_override_required_for_approval": False,
                "last_edited_by": actor,
                "last_edited_at": _now_iso(),
            }
        b[k] = v
    b["field_provenance"] = field_provenance
    b["edit_log"] = (edit_log + [edit_entry])[-50:]  # keep last 50
    b["revision"] = int(b.get("revision", 1)) + 1
    b["updated_at"] = _now_iso()
    _write_brief(b)
    _append_revision(b, {
        "revision": b["revision"],
        "saved_at": b["updated_at"],
        "snapshot": b,
        "note": f"operator edit (actor={actor})",
        "drafted_by": "operator",
    })
    return {"ok": True, "brief": b}


def _operator_token_store() -> dict:
    """V1.3 §1: per-operator approval verifier registry.

    Reads OPERATOR_APPROVAL_TOKEN_HASHES env var — JSON dict
    of operator_id → pbkdf2 verifier object:
      {
        "salt": "<hex>",
        "hash": "<hex>",
        "iter": <int>   # PBKDF2 iterations
      }
    Or the legacy V1.2 plaintext OPERATOR_APPROVAL_TOKENS is
    no longer read at all (fail-closed).

    Returns dict {operator_id: verifier_dict} or {} if not
    configured. Missing or invalid config = no operator can
    approve (fail-closed per V1.3 §1).

    Per V1.3 §1: the RAW operator approval secret must
    never live in Railway plaintext, never be available to
    Hermes/Heidi, never be returned by any API, never be
    logged. Only a one-way verifier (PBKDF2-HMAC-SHA256,
    600k iterations, 32-byte random salt) is stored.
    """
    raw = os.environ.get("OPERATOR_APPROVAL_TOKEN_HASHES", "")
    if not raw or not raw.strip():
        return {}
    try:
        d = json.loads(raw)
        out = {}
        for k, v in d.items():
            if not k or not isinstance(v, dict):
                continue
            # Each verifier must have salt + hash (+ optional iter)
            salt = v.get("salt")
            hh = v.get("hash")
            iter_ = int(v.get("iter") or 600_000)
            if not salt or not hh:
                continue
            out[str(k)] = {
                "salt": str(salt),
                "hash": str(hh),
                "iter": iter_,
            }
        return out
    except Exception:
        return {}


def _hash_operator_secret(secret: str, salt: bytes,
                          iterations: int = 600_000) -> bytes:
    """PBKDF2-HMAC-SHA256 verifier computation. Used by
    admin/setup tooling ONLY — the operator's secret is
    passed in interactively at approval time and is never
    persisted.
    """
    import hashlib as _hashlib
    return _hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        salt,
        iterations,
        dklen=32,
    )


def _verify_operator_auth(headers: "Optional[dict]" = None) -> "Optional[str]":
    """V1.3 §1: verify that the incoming request carries a
    valid operator approval secret.

    Headers expected:
      X-Operator-Id: <operator_id>
      X-Operator-Token: <plaintext secret held by operator>

    Verification: PBKDF2-HMAC-SHA256(secret, stored_salt,
    stored_iter) is compared in constant time against the
    stored hash. The plaintext secret never leaves the
    request — it is hashed in-memory and discarded after
    the comparison.

    Returns the authenticated operator_id (str) if valid,
    None otherwise.

    FAIL-CLOSED:
      - If env var not configured → no operator can approve
      - If operator_id not in store → rejected
      - If PBKDF2 hash mismatch → rejected
      - All comparisons via hmac.compare_digest

    Per V1.3 §1: this proves HUMAN PRESENCE because:
      - The plaintext secret is held ONLY by the human
        operator (known at approval-click time, never stored)
      - Hermes/Heidi cannot approve without it
      - Railway plaintext variables do NOT contain the secret
    """
    if headers is None:
        try:
            from flask import request as _flask_request
            headers = _flask_request.headers
        except Exception:
            return None
    op_id = (headers.get("X-Operator-Id") or "").strip()
    op_token = (headers.get("X-Operator-Token") or "").strip()
    if not op_id or not op_token:
        return None
    store = _operator_token_store()
    verifier = store.get(op_id)
    if not verifier:
        return None
    import hmac as _hmac
    try:
        salt_bytes = bytes.fromhex(verifier["salt"])
        stored_hash = bytes.fromhex(verifier["hash"])
        iter_ = int(verifier.get("iter") or 600_000)
        candidate = _hash_operator_secret(op_token, salt_bytes, iter_)
        if _hmac.compare_digest(candidate, stored_hash):
            return op_id
        return None
    except Exception:
        return None


def hash_operator_secret_for_setup(secret: str,
                                    operator_id: str = "") -> dict:
    """V1.3 §1 admin/setup helper. Computes a verifier
    record for storing in OPERATOR_APPROVAL_TOKEN_HASHES.

    Usage (one-time setup, not exposed as API):
      from campaign_brief import hash_operator_secret_for_setup
      verifier = hash_operator_secret_for_setup(secret)
      # Then store as JSON in Railway Variables:
      OPERATOR_APPROVAL_TOKEN_HASHES={"christelle": verifier}

    Returns: {"salt": "<hex>", "hash": "<hex>",
              "iter": <int>, "operator_id": "<id>"}

    This function never logs the secret. The plaintext is
    held only in the operator's memory + the calling
    setup script's in-process variable.
    """
    import secrets as _secrets
    salt = _secrets.token_bytes(32)
    hh = _hash_operator_secret(secret, salt)
    return {
        "operator_id": operator_id,
        "salt": salt.hex(),
        "hash": hh.hex(),
        "iter": 600_000,
    }


def transition_brief(brand_id: str, brief_id: str, to_status: str,
                     actor: str = None, headers: "Optional[dict]" = None) -> dict:
    """Status model transitions (brief §13).

    V1.2 §1 trust fix:
      - approved / rejected / superseded require operator
        authentication via _verify_operator_auth()
      - actor body param is IGNORED for status transitions
        that affect creative_allowed (the authenticated
        operator identity is the authoritative actor)
      - draft / ready_for_review / changes_requested can
        be performed by any authed session (system or
        operator)
      - previous_status + approval_method +
        originating_ui_action are persisted to the brief's
        status_transitions log
    """
    if to_status not in VALID_STATUSES:
        return {"ok": False, "error": f"invalid status: {to_status}"}
    b = _read_brief(brand_id, brief_id)
    if not b:
        return {"ok": False, "error": "brief not found"}
    previous_status = b.get("status")
    # V1.2 §1: protected transitions require operator auth
    PROTECTED = (STATUS_APPROVED, STATUS_REJECTED, STATUS_SUPERSEDED)
    authenticated_operator = None
    if to_status in PROTECTED:
        authenticated_operator = _verify_operator_auth(headers)
        if not authenticated_operator:
            return {"ok": False,
                    "error": (f"transition to '{to_status}' requires "
                              "operator authentication (V1.2 §1). "
                              "Provide X-Operator-Id + X-Operator-Token "
                              "headers. Arbitrary body `actor` strings "
                              "are not accepted as proof of human "
                              "approval.")}
        # The operator identity IS the actor — ignore body.
        actor = authenticated_operator
        approval_method = "operator_token_v1"
    else:
        # Non-protected transitions: accept body actor
        actor = actor or "system"
        approval_method = ("operator_token_v1" if _verify_operator_auth()
                           else "system")
    # Append-only on status transitions
    transitions = b.get("status_transitions") or []
    transitions.append({
        "from": previous_status,
        "to": to_status,
        "actor": actor,
        "approval_method": approval_method,
        "authenticated_operator": authenticated_operator,
        "originating_ui_action": "brief_status_transition",
        "at": _now_iso(),
    })
    b["status_transitions"] = transitions
    b["status"] = to_status
    b["updated_at"] = _now_iso()
    if to_status == STATUS_APPROVED:
        b["approved_at"] = b["updated_at"]
        b["approved_by"] = actor
        b["approval_method"] = approval_method
        b["authenticated_operator"] = authenticated_operator
        b["creative_allowed"] = True  # V1.1 §11
    elif to_status in (STATUS_REJECTED, STATUS_SUPERSEDED):
        b["creative_allowed"] = False
    elif previous_status == STATUS_APPROVED:
        # Moving AWAY from approved (e.g. approved → ready_for_review,
        # approved → draft) clears creative_allowed regardless of
        # the destination. This is the safety guarantee that
        # creative generation only fires for currently-approved briefs.
        b["creative_allowed"] = False
        b["approved_at"] = None
        b["approved_by"] = None
        b["approval_method"] = None
        b["authenticated_operator"] = None
    b["revision"] = int(b.get("revision", 1)) + 1
    _write_brief(b)
    _append_revision(b, {
        "revision": b["revision"],
        "saved_at": b["updated_at"],
        "snapshot": b,
        "note": (f"transition {previous_status}→{to_status} by "
                  f"{actor} ({approval_method})"),
        "drafted_by": "operator" if authenticated_operator else "system",
    })
    return {"ok": True, "brief": b, "approval_method": approval_method,
            "authenticated_operator": authenticated_operator}


LOG_OPERATOR_ACTIONS = True  # V1.2 §1 — audit log


def revert_test_approval(brand_id: str, brief_id: str,
                           target_status: str = None,
                           reason: str = None,
                           headers: "Optional[dict]" = None) -> dict:
    """V1.2 §2: revert a Brief that was approved without genuine
    operator approval (e.g. agent-driven test approval).

    Preserves the existing audit history as
    test_provenance but moves the current Brief to a
    non-approved state (ready_for_review or draft).

    Records the revert reason + a transition note in
    status_transitions so the audit trail is complete.

    This function is INTERNAL — only callable via the
    /api/brief/v1/_internal/revert-test-approval endpoint
    which itself requires an operator token (V1.2 §2)."""
    b = _read_brief(brand_id, brief_id)
    if not b:
        return {"ok": False, "error": "brief not found"}
    if b.get("status") not in (STATUS_APPROVED,):
        return {"ok": False, "error":
                f"revert requires current status=approved, "
                f"got {b.get('status')}"}
    authenticated_operator = _verify_operator_auth(headers)
    if not authenticated_operator:
        return {"ok": False,
                "error": "revert requires operator authentication "
                         "(V1.2 §2). Provide X-Operator-Id + "
                         "X-Operator-Token."}
    previous_status = b.get("status")
    target = target_status or STATUS_READY_FOR_REVIEW
    if target not in VALID_STATUSES:
        return {"ok": False,
                "error": f"invalid target status: {target}"}
    # Append to transitions (preserves previous test_provenance
    # transition which stays in the log)
    transitions = b.get("status_transitions") or []
    transitions.append({
        "from": previous_status,
        "to": target,
        "actor": authenticated_operator,
        "approval_method": "operator_token_v1",
        "authenticated_operator": authenticated_operator,
        "originating_ui_action": "brief_test_approval_revert",
        "reason": (reason or
                   "test approval did not represent explicit "
                   "operator approval"),
        "at": _now_iso(),
    })
    b["status_transitions"] = transitions
    b["status"] = target
    b["updated_at"] = _now_iso()
    # Mark the original approval as test_provenance
    if b.get("approved_at"):
        b["test_provenance"] = {
            "reverted_at": b["updated_at"],
            "reverted_by": authenticated_operator,
            "reason": (reason or
                       "test approval did not represent "
                       "explicit operator approval"),
            "previous_status": previous_status,
            "new_status": target,
        }
    b["approved_at"] = None
    b["approved_by"] = None
    b["approval_method"] = None
    b["authenticated_operator"] = None
    b["creative_allowed"] = False  # V1.2 §2
    b["revision"] = int(b.get("revision", 1)) + 1
    _write_brief(b)
    _append_revision(b, {
        "revision": b["revision"],
        "saved_at": b["updated_at"],
        "snapshot": b,
        "note": (f"REVERTED test approval {previous_status}→{target} "
                  f"by {authenticated_operator}; reason: "
                  f"{reason}"),
        "drafted_by": "operator",
    })
    return {"ok": True, "brief": b,
            "test_provenance_preserved": True,
            "creative_allowed": False}

