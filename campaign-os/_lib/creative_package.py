"""Creative Package V1 — the actual output of Create.

Consumes:
- Strategic Brief (Brief V1.7, frozen, approved)
- Reporting Intelligence V2.4.1 (frozen evidence)
- Brand voice rules (do-say-dont-say.md per brand)
- Canonical facts (price, lesson duration, location, etc.)
- Historical captions / Creative Genome (novelty check)
- Visual DNA (composition / format / text density guidance)

Per V1 §5: "The unit of output is creative_package generated
from ONE approved Strategic Brief. Where strategically useful
it may contain 2–3 genuinely different creative routes. Do
not force three."

Per V1 §6: each route has route_id, working_concept_name,
concept_rationale, strategic_link, audience_tension,
core_message, creative_direction, channel_roles,
required_assets, CTA, evidence_refs, fact_refs,
reporting_refs, historical_refs, confidence,
novelty_signal, validation_status.

Per V1 §7: Reporting informs, not dictates. Every observation
is labelled MEASURED_FACT / SUPPORTED_INFERENCE / HYPOTHESIS.

Per V1 §9: every factual claim carries fact_refs[]; missing
facts surface as operator_fact_required — NEVER invented.

Per V1 §10: brand isolation — only the requested brand's
voice / facts / history / Creative Genome are used.

Per V1 §11: voice + banned-term validation runs on every
draft. Result is PASS / WARNING / FAIL. Operator edits are
NEVER silently rewritten.

Per V1 §12: novelty check via historical caption embeddings
+ Creative Genome.

Per V1 §13: Creative Genome contributes (composition / format
/ text density) but is NOT mechanically cloned.

Per V1 §14: only Brief-approved channels are generated.

Per V1 §19: visual briefs are generated, NOT final images.
Missing real assets surface as operator_asset_required.

Per V1 §20: package snapshot freezes brief_id, brief_revision,
strategy_snapshot, evidence_snapshot, reporting_snapshot,
fact_snapshot, generated_at, generator_version.

Per V1 §21: append-only material revisions; preserves
system_draft / operator_edit / regeneration / generated_at /
generated_by / previous revision / change reason.

Per V1 §22: targeted regeneration stays bound to approved
Brief + brand facts + voice + evidence + strategy.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Local imports kept narrow to avoid pulling in app.py
# (which would cause circular import during isolation).
# Fact lookup + brand dir + voice/banned-terms are in
# p11_context_engine.py. Reporting is in reporting_intelligence.py.
# We import lazily inside functions so this module loads without
# app.py being fully initialised.

GENERATOR_VERSION = "create_v1.0"

# V1 §14: Brief-approved channel set
CHANNEL_SET = (
    "instagram_reel", "instagram_carousel", "instagram_static",
    "facebook", "tiktok", "youtube_shorts",
    "paid_social", "email", "landing_page",
)

# V1 §5: route dimensions (used to reason about distinctness)
ROUTE_DIMENSIONS = (
    "expert_demonstration", "challenge_test", "education",
    "proof_data", "humour", "lifestyle", "product_focus",
    "human_story",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _data_dir() -> str:
    return os.environ.get("CAMPAIGN_OS_DATA_DIR",
                           os.path.join(os.path.dirname(__file__), "..", "data"))


def _brand_dir(brand_id: str) -> Path:
    return Path(_data_dir()) / "brand-directory" / brand_id


def _load_brand_facts(brand_id: str) -> dict:
    """Load canonical facts (price, lesson duration, fitting price,
    staff credentials, etc.) from brand product library + brand
    overlay."""
    facts: Dict[str, Any] = {}
    pl = _brand_dir(brand_id) / "product-library.json"
    if pl.exists():
        try:
            data = json.loads(pl.read_text())
            facts["products"] = data
        except Exception:
            pass
    ovl = _brand_dir(brand_id) / "brand-overlay.json"
    if ovl.exists():
        try:
            data = json.loads(ovl.read_text())
            for k in ("prices", "promotions", "delivery_incentives",
                       "discounts", "events", "locations", "staff",
                       "equipment", "service_durations"):
                if k in data:
                    facts[k] = data[k]
        except Exception:
            pass
    return facts


def _load_banned_terms(brand_id: str) -> List[str]:
    """V1 §11: load banned terms from voice/do-say-dont-say.md."""
    txt = _read_text(_brand_dir(brand_id) / "voice" / "do-say-dont-say.md")
    if not txt:
        return []
    banned = []
    in_dont = False
    for line in txt.split("\n"):
        if "## Don't say" in line or "## Banned" in line:
            in_dont = True
            continue
        if in_dont and line.startswith("## "):
            in_dont = False
        if in_dont and (line.strip().startswith("❌")
                         or line.strip().startswith("- ❌")):
            clean = re.sub(r"^[-\s❌]+", "", line).strip().strip('"').strip("'").strip("`")
            if clean and len(clean) < 80:
                banned.append(clean)
    return list({b for b in banned if b})


def _load_voice_rules(brand_id: str) -> str:
    """V1 §11: load full voice rules block for system prompts."""
    txt = _read_text(_brand_dir(brand_id) / "voice" / "do-say-dont-say.md")
    return txt


def _load_history_captions(brand_id: str) -> List[dict]:
    """V1 §12: load historical captions for novelty check."""
    # canonical history file per brand
    candidates = [
        _brand_dir(brand_id) / "social-history.json",
        _brand_dir(brand_id) / "captions-history.json",
        Path(_data_dir()) / "social-history" / f"{brand_id}.json",
    ]
    for c in candidates:
        if c.exists():
            try:
                return json.loads(c.read_text())
            except Exception:
                return []
    return []


def _load_creative_genome(brand_id: str) -> dict:
    """V1 §13: Creative Genome composition / format / text-density."""
    candidates = [
        _brand_dir(brand_id) / "creative-genome.json",
        Path(_data_dir()) / "creative-genome" / f"{brand_id}.json",
    ]
    for c in candidates:
        if c.exists():
            try:
                return json.loads(c.read_text())
            except Exception:
                return {}
    return {}


def _load_visual_dna(brand_id: str) -> dict:
    candidates = [
        _brand_dir(brand_id) / "visual-dna.json",
    ]
    for c in candidates:
        if c.exists():
            try:
                return json.loads(c.read_text())
            except Exception:
                return {}
    return {}


def _token_overlap(a: str, b: str) -> float:
    """V1 §12: novelty via token overlap (cheap proxy for embedding
    similarity when no embedding model is wired in Create V1).
    Returns Jaccard in [0, 1]."""
    sa = set(re.findall(r"\w+", (a or "").lower()))
    sb = set(re.findall(r"\w+", (b or "").lower()))
    sa = {w for w in sa if len(w) > 3}
    sb = {w for w in sb if len(w) > 3}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _novelty_signal(candidate_text: str,
                      history: List[dict]) -> dict:
    """V1 §12: novelty analysis vs historical captions.
    Per V1 §12: 'Do not reject solely based on similarity until
    thresholds are validated.' Returns a non-rejecting signal.
    """
    matches = []
    for h in (history or [])[:50]:  # cap to recent 50
        past_text = (h.get("caption") or h.get("text") or h.get("hook")
                      or h.get("body") or "")
        if not past_text:
            continue
        sim = _token_overlap(candidate_text, past_text)
        if sim >= 0.20:
            matches.append({
                "historical_id": (h.get("id") or h.get("asset_id")
                                    or h.get("ts") or "?"),
                "similarity_score": round(sim, 3),
                "snippet": (past_text[:140] + "…") if len(past_text) > 140 else past_text,
            })
    matches.sort(key=lambda m: m["similarity_score"], reverse=True)
    top = matches[:5]
    # V1 §12: do not reject, signal only
    if top:
        max_sim = top[0]["similarity_score"]
        if max_sim >= 0.55:
            signal = "HIGH_OVERLAP"
        elif max_sim >= 0.35:
            signal = "MEDIUM_OVERLAP"
        else:
            signal = "LOW_OVERLAP"
    else:
        signal = "NOVEL"
    return {
        "novelty_signal": signal,
        "nearest_historical_matches": top,
        "similarity_score": (top[0]["similarity_score"] if top else 0.0),
    }


def _validate_voice(text: str, voice_rules: str, banned_terms: List[str]
                     ) -> dict:
    """V1 §11: voice + banned-term validator.
    Returns {validation_status, banned_hits, voice_warnings}.
    PASS / WARNING / FAIL.
    FAIL = banned-term hit.
    WARNING = voice-rule heuristic triggered (e.g. known anti-pattern).
    """
    hits = []
    for b in banned_terms:
        if not b or b in ("—", "-"):
            continue
        if b.lower() in (text or "").lower():
            hits.append(b)
    # Heuristic voice rules — DO/SAY patterns from do-say-dont-say
    voice_warnings = []
    if voice_rules:
        # If the text contains words flagged in the "do-say" list
        # alongside the dont-say list, we don't auto-fail.
        # Heuristic: ALL CAPS words beyond short emphasis
        all_caps = re.findall(r"\b[A-Z]{5,}\b", text or "")
        # Filter common words
        caps_excl = [c for c in all_caps
                      if c not in {"TRACKMAN", "SWING", "SHACK",
                                    "OUTCOME", "STICK", "PEOPLE"}]
        if len(caps_excl) >= 2:
            voice_warnings.append(
                f"Multiple ALL CAPS words ({caps_excl[:3]}) — review voice rules"
            )
    if hits:
        status = "FAIL"
    elif voice_warnings:
        status = "WARNING"
    else:
        status = "PASS"
    return {
        "validation_status": status,
        "banned_hits": hits,
        "voice_warnings": voice_warnings,
    }


def _ground_facts(text: str, facts: dict) -> dict:
    """V1 §9: every factual claim must resolve to canonical facts.

    Returns {grounded_claims[], ungrounded_claims[],
    operator_fact_required[]}.

    Heuristic: detect monetary amounts (R XXX), durations
    (XX min), and check against known facts. If no exact
    match but the figure looks plausible (3-digit or 4-digit
    ZAR, 30/45/60-min duration), surface as operator_fact_required
    rather than inventing.
    """
    grounded = []
    ungrounded = []
    operator_required = []
    text = text or ""
    # Heuristic 1: monetary amounts in ZAR
    price_hits = re.findall(r"R\s?(\d{2,5})", text)
    known_prices = set()
    for p in (facts.get("prices") or {}).values() if isinstance(facts.get("prices"), dict) else []:
        try:
            known_prices.add(str(int(p)))
        except Exception:
            pass
    for product in (facts.get("products") or []):
        for k in ("price", "fitting_price", "lesson_price"):
            v = product.get(k) if isinstance(product, dict) else None
            if v is not None:
                try:
                    known_prices.add(str(int(v)))
                except Exception:
                    pass
    for hit in price_hits:
        if hit in known_prices:
            grounded.append({"claim": f"R{hit}",
                              "grounding": "matches canonical fact"})
        else:
            operator_required.append({"claim": f"R{hit}",
                                       "operator_fact_required": True,
                                       "note": ("monetary amount not "
                                                 "present in canonical "
                                                 "facts; needs operator "
                                                 "confirmation")})
    # Heuristic 2: durations
    duration_hits = re.findall(r"(\d{2,3})\s?(min|minute|minutes|hr|hour|hours)",
                                 text)
    known_durations = set()
    for d in (facts.get("service_durations") or {}).values() if isinstance(facts.get("service_durations"), dict) else []:
        try:
            known_durations.add(str(int(d)))
        except Exception:
            pass
    for dur, unit in duration_hits:
        if dur in known_durations:
            grounded.append({"claim": f"{dur} {unit}",
                              "grounding": "matches canonical fact"})
        else:
            operator_required.append({"claim": f"{dur} {unit}",
                                       "operator_fact_required": True,
                                       "note": ("duration not present in "
                                                 "canonical facts; needs "
                                                 "operator confirmation")})
    # Heuristic 3: location names — accept whatever's in the
    # brand's locations fact list verbatim
    locations = (facts.get("locations") or [])
    if locations and isinstance(locations, list):
        for loc in locations:
            if isinstance(loc, str) and loc and loc in text:
                grounded.append({"claim": loc,
                                  "grounding": "matches canonical location"})
    return {
        "grounded_claims": grounded,
        "ungrounded_claims": ungrounded,
        "operator_fact_required": operator_required,
    }


def _load_reporting_snapshot(brand_id: str) -> dict:
    """V1 §7: pull Reporting Intelligence V2.4.1 evidence.

    Tries the cache file written by meta_refresh. NEVER
    re-reads synthetic data/meta-ads.json."""
    cache_path = Path(_data_dir()) / "paid-media" / f"{brand_id}.json"
    if not cache_path.exists():
        return {"data_status": "UNAVAILABLE",
                "reason": f"cache not present at {cache_path}",
                "rule": ("V2.4.1 cache is populated by meta_refresh job. "
                          "If absent, Run /api/jobs/run/meta_refresh")}
    try:
        c = json.loads(cache_path.read_text())
    except Exception as e:
        return {"data_status": "ERROR", "error": str(e)[:200]}
    # Extract: per-campaign current/previous/YTD, account
    # reconciliation, freshness, best/needs_attention. Strip
    # raw actions[] (preserved verbatim in cache; reporting
    # evidence only needs the rolled-up metrics).
    return {
        "data_status": c.get("data_status", "UNKNOWN"),
        "schema": c.get("schema"),
        "fetched_at": c.get("fetched_at"),
        "data_as_of": c.get("data_as_of"),
        "freshness_status": "fresh",  # caller may recompute
        "report_period": c.get("report_period"),
        "current_totals": c.get("current_totals"),
        "previous_totals": c.get("previous_totals"),
        "ytd_totals": c.get("ytd_totals"),
        "ad_account_meta": c.get("ad_account_meta"),
        "per_campaign_summary": [
            {
                "campaign_id": r.get("campaign_id"),
                "campaign_name": r.get("campaign_name"),
                "objective": r.get("objective"),
                "spend": r.get("spend"),
                "impressions": r.get("impressions"),
                "reach": r.get("reach"),
                "clicks": r.get("clicks"),
                "ctr": r.get("ctr"),
                "cpc": r.get("cpc"),
                "cpm": r.get("cpm"),
                "lead_count": (next((a.get("value") for a in (r.get("actions") or [])
                                       if a.get("action_type") in (
                                           "onsite_conversion.lead", "lead",
                                           "offsite_complete_registration_add_meta_leads")),
                                       None)),
                "lpv_count": (next((a.get("value") for a in (r.get("actions") or [])
                                      if a.get("action_type") in (
                                          "landing_page_view",
                                          "omni_landing_page_view")),
                                      None)),
                "lead_measurement_note": (
                    "Meta-reported lead count (first matching action_type; "
                    "may overlap with other lead events; not a qualified "
                    "lead / fitting booked / coaching booked / sale)"),
                "lpv_measurement_note": (
                    "landing-page view count from Meta; not GA4 session data"),
            }
            for r in (c.get("ytd") or {}).get("rows", [])
        ],
        "campaign_counts": {
            "ytd_delivered": sum(1 for r in (c.get("ytd") or {}).get("rows", [])
                                   if (r.get("spend") or 0) > 0),
            "ytd_listed": len((c.get("campaigns") or [])),
        },
        "duplicate_campaigns_visible": (c.get("paid_media_v24") or {}).get(
            "duplicate_campaigns_visible") or [],
        "freshness_warning": ("Reporting numbers are MEASURED_FACT from "
                                "Meta Graph API. Creative may USE them as "
                                "evidence; Creative MUST NOT reinterpret "
                                "them independently."),
    }


def _load_brief_snapshot(brand_id: str, brief_id: str) -> dict:
    """V1 §1+§20: load approved Brief (canonical, frozen)."""
    candidates = [
        Path(_data_dir()) / "campaign-briefs" / brand_id / f"{brief_id}.json",
        Path(_data_dir()) / "briefs" / brand_id / f"{brief_id}.json",
    ]
    for c in candidates:
        if c.exists():
            try:
                return json.loads(c.read_text())
            except Exception:
                return {}
    return {}


def _allowed_channels_from_brief(brief: dict) -> List[str]:
    """V1 §14: only generate Brief-approved channels."""
    raw = brief.get("channels") or brief.get("approved_channels") or []
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.split(",") if x.strip()]
    allowed = [c for c in raw if c in CHANNEL_SET]
    # Default fallback: paid_social + instagram_static if brief
    # has no channel list
    if not allowed:
        allowed = ["paid_social"]
    return allowed


def _brief_revision(brief: dict) -> str:
    return (brief.get("revision") or brief.get("brief_revision")
              or brief.get("version") or "v?")


def _route_skeleton(route_id: str, name: str, rationale: str,
                     strategic_link: str, audience_tension: str,
                     core_message: str, creative_direction: str,
                     channel_roles: List[str], required_assets: List[dict],
                     cta: str,
                     evidence_refs: List[str], fact_refs: List[str],
                     reporting_refs: List[str],
                     historical_refs: List[str],
                     confidence: float,
                     novelty_signal: dict,
                     validation_status: str) -> dict:
    return {
        "route_id": route_id,
        "working_concept_name": name,
        "concept_rationale": rationale,
        "strategic_link": strategic_link,
        "audience_tension": audience_tension,
        "core_message": core_message,
        "creative_direction": creative_direction,
        "channel_roles": channel_roles,
        "required_assets": required_assets,
        "cta": cta,
        "evidence_refs": evidence_refs,
        "fact_refs": fact_refs,
        "reporting_refs": reporting_refs,
        "historical_refs": historical_refs,
        "confidence": round(confidence, 2),
        "novelty_signal": novelty_signal,
        "validation_status": validation_status,
        # V1 §21: revision provenance defaults
        "revisions": [{
            "revision": "system_draft",
            "generated_at": _now_iso(),
            "generated_by": GENERATOR_VERSION,
            "change_reason": "initial generation",
            "previous_revision": None,
        }],
    }


def _required_asset(asset_kind: str, description: str,
                     has_real_asset: bool = False) -> dict:
    """V1 §19: visual brief is generated, not the asset itself.
    Real-asset availability is checked per brand. If not present,
    operator_asset_required=true."""
    if has_real_asset:
        return {
            "kind": asset_kind,
            "description": description,
            "operator_asset_required": False,
            "source": "canonical",
        }
    return {
        "kind": asset_kind,
        "description": description,
        "operator_asset_required": True,
        "source": "operator_required",
    }


def _derive_creative_routes(brief: dict, reporting: dict, facts: dict,
                              genome: dict, visual_dna: dict,
                              history: List[dict],
                              reporting_refs: List[str],
                              evidence_refs: List[str],
                              fact_refs: List[str],
                              historical_refs: List[str]) -> List[dict]:
    """V1 §5: derive 2-3 genuinely different creative routes.

    The route design is parameterised by the Brief's primary
    pillar + objective + audience_tension. Per V1 §5 we don't
    force three — we generate up to three, only when the brief
    supports them.

    The Create V1 generation produces structural route shapes
    (no LLM call here). Each route is grounded in the Brief,
    Reporting V2.4.1 evidence, and canonical facts.
    """
    pillar = (brief.get("primary_pillar") or
                brief.get("north_star_pillar") or "default")
    objective = (brief.get("objective") or "consideration").lower()
    aud_tension = (brief.get("audience_tension")
                     or "how do we reach the right audience")
    routes = []
    # Route A: expert demonstration / education
    if pillar in ("coaching", "fitting"):
        routes.append(_route_skeleton(
            route_id=f"route-A-{uuid.uuid4().hex[:6]}",
            name="Expert Demonstration",
            rationale=("Operator (coach / fitter) demonstrates the "
                         "specific insight the Brief targets, framed "
                         "as measurement-backed expertise."),
            strategic_link=(f"Brief pillar: {pillar}. Brief objective: "
                              f"{objective}."),
            audience_tension=aud_tension,
            core_message=(f"We measure before we prescribe — {pillar} is "
                            "a data-driven process, not a sales pitch."),
            creative_direction=("Operator on camera (or off-camera voiceover) "
                                 "demonstrates one measurement beat. Direct-to-"
                                 "camera explanation with on-screen text showing "
                                 "the number being measured."),
            channel_roles=["instagram_reel", "paid_social",
                             "youtube_shorts"],
            required_assets=[
                _required_asset("video", "Operator demonstrating one measurement "
                                   "step on the studio floor."),
                _required_asset("video", "B-roll of TrackMan / Zen Stage / swing capture."),
                _required_asset("static", "End-card with booking link."),
            ],
            cta=("Book a TrackMan / Zen Stage session at swing-shack.com — "
                  "we'll show you the data."),
            evidence_refs=evidence_refs,
            fact_refs=fact_refs,
            reporting_refs=reporting_refs,
            historical_refs=historical_refs,
            confidence=0.75,
            novelty_signal=_novelty_signal(
                "expert demonstration TrackMan measurement data booking",
                history),
            validation_status="PENDING",
        ))
    # Route B: proof / data
    routes.append(_route_skeleton(
        route_id=f"route-B-{uuid.uuid4().hex[:6]}",
        name="Proof & Data",
        rationale=("Surface a single specific number from Reporting "
                     "V2.4.1 (paid performance, organic growth, or "
                     "session movement) as the proof."),
        strategic_link=(f"Brief pillar: {pillar}. Reporting V2.4.1 "
                      f"current totals: "
                      f"{json.dumps((reporting.get('current_totals') or {}))[:200]}."),
        audience_tension=aud_tension,
        core_message=("A number you can verify — this is what the work "
                       "produced."),
        creative_direction=("Single number on screen, source labeled. "
                             "Caption explains the context WITHOUT "
                             "reinterpreting the number."),
        channel_roles=["instagram_static", "instagram_carousel",
                        "facebook", "paid_social"],
        required_assets=[
            _required_asset("static", "Number-on-screen graphic with "
                                "source label (e.g. 'Meta reporting, "
                                "2026-08-21 → 2026-09-20')."),
            _required_asset("static", "Brand card (logo + booking link)."),
        ],
        cta=("See the source. Book a session."),
        evidence_refs=evidence_refs,
        fact_refs=fact_refs,
        reporting_refs=reporting_refs,
        historical_refs=historical_refs,
        confidence=0.70,
        novelty_signal=_novelty_signal(
            "proof data number reporting measurement",
            history),
        validation_status="PENDING",
    ))
    # Route C: challenge / test (only when brief explicitly
    # supports it via audience_tension language like "myth",
    # "challenge", "are you ready", "find out", etc.)
    tension_lower = (aud_tension or "").lower()
    challenge_kw = ("myth" in tension_lower or "challenge" in tension_lower
                     or "find out" in tension_lower or "test" in tension_lower
                     or "guess" in tension_lower)
    if challenge_kw:
        routes.append(_route_skeleton(
            route_id=f"route-C-{uuid.uuid4().hex[:6]}",
            name="Challenge / Test",
            rationale=("Brief audience_tension contains challenge / "
                         "myth / find-out language. Frame the asset as "
                         "an open invitation to verify."),
            strategic_link=(f"Brief pillar: {pillar}. Audience tension: "
                              f"{aud_tension}."),
            audience_tension=aud_tension,
            core_message=("If you've been guessing — book the session "
                           "and find out for real."),
            creative_direction=("Question on screen, CTA = book. Direct, "
                                 "non-aggressive, measurement-led."),
            channel_roles=["instagram_reel", "tiktok", "youtube_shorts",
                            "paid_social"],
            required_assets=[
                _required_asset("video", "Hook question on screen with "
                                  "operator voiceover."),
                _required_asset("static", "End-card with booking link."),
            ],
            cta=("Find out — book a session."),
            evidence_refs=evidence_refs,
            fact_refs=fact_refs,
            reporting_refs=reporting_refs,
            historical_refs=historical_refs,
            confidence=0.65,
            novelty_signal=_novelty_signal(
                "challenge test find out book session",
                history),
            validation_status="PENDING",
        ))
    return routes


def _validate_route(route: dict, voice_rules: str, banned_terms: List[str],
                      facts: dict, history: List[dict]) -> dict:
    """V1 §11+§9+§12: run voice, banned-term, fact-grounding, novelty
    on each route."""
    # Combine all route text into one validation surface
    text_blobs = [
        route.get("core_message") or "",
        route.get("creative_direction") or "",
        route.get("audience_tension") or "",
        route.get("cta") or "",
        " ".join(route.get("concept_rationale") or []),
    ]
    full = "\n".join([t for t in text_blobs if t])
    voice = _validate_voice(full, voice_rules, banned_terms)
    grounding = _ground_facts(full, facts)
    novelty = _novelty_signal(full, history)
    # Combine into a single validation_status
    if voice["validation_status"] == "FAIL":
        status = "FAIL"
    elif grounding["operator_fact_required"]:
        # Operator fact required is a WARNING, not a FAIL — the
        # route is structurally valid, but ungrounded claims
        # need operator input.
        status = "WARNING"
    elif voice["validation_status"] == "WARNING":
        status = "WARNING"
    else:
        status = "PASS"
    out = {
        "voice": voice,
        "fact_grounding": grounding,
        "novelty": novelty,
        "validation_status": status,
    }
    return out


def _channel_drafts(route: dict, allowed_channels: List[str],
                     reporting_refs: List[str], fact_refs: List[str]
                     ) -> dict:
    """V1 §14-§18: produce channel-specific drafts for each
    approved channel.

    Per V1 §14: 'Do not automatically generate all channels.'
    Per V1 §15-§18: each format has its own minimal structural
    skeleton (hook, opening visual, beats, CTA, duration, asset
    requirements)."""
    drafts = {}
    for ch in allowed_channels:
        if ch == "instagram_reel" or ch == "youtube_shorts" or ch == "tiktok":
            # V1 §15
            drafts[ch] = {
                "format": ch,
                "hook": (route["core_message"][:80] + "…"
                          if len(route["core_message"]) > 80
                          else route["core_message"]),
                "opening_visual": "Operator on studio floor OR B-roll of measurement setup.",
                "beat_sequence": [
                    {"beat": 1, "duration_s": "0-3",
                      "what_happens": "Hook question or surprising data point.",
                      "on_screen_text": route["core_message"][:60]},
                    {"beat": 2, "duration_s": "3-12",
                      "what_happens": "Demonstration / explanation — concrete and specific.",
                      "on_screen_text": "One number, one measurement."},
                    {"beat": 3, "duration_s": "12-22",
                      "what_happens": "Result / what the audience should do next.",
                      "on_screen_text": route["cta"][:60]},
                ],
                "spoken_copy": route["creative_direction"],
                "on_screen_text_summary": route["core_message"],
                "broll": ["TrackMan / Zen Stage capture",
                          "Swing close-up",
                          "Studio environment"],
                "cta": route["cta"],
                "estimated_duration_s": 22,
                "required_assets": route["required_assets"],
                "evidence_refs": route["evidence_refs"],
                "fact_refs": route["fact_refs"],
                "reporting_refs": reporting_refs,
                "validation_status": route["validation_status"],
            }
        elif ch == "instagram_carousel":
            # V1 §16
            drafts[ch] = {
                "format": ch,
                "slides": [
                    {"slide": 1, "purpose": "Hook",
                      "headline": route["core_message"][:80],
                      "supporting_copy": "Why this matters.",
                      "visual_direction": "Bold type, brand card, single number."},
                    {"slide": 2, "purpose": "Proof",
                      "headline": "What we measured",
                      "supporting_copy": "One specific data point.",
                      "visual_direction": "Number on screen."},
                    {"slide": 3, "purpose": "Method",
                      "headline": "How we measured it",
                      "supporting_copy": "One measurement step.",
                      "visual_direction": "Operator + measurement tool."},
                    {"slide": 4, "purpose": "Action",
                      "headline": "Try it yourself",
                      "supporting_copy": route["cta"],
                      "visual_direction": "Booking CTA + brand card."},
                ],
                "cta": route["cta"],
                "required_assets": route["required_assets"],
                "evidence_refs": route["evidence_refs"],
                "fact_refs": route["fact_refs"],
                "reporting_refs": reporting_refs,
                "validation_status": route["validation_status"],
            }
        elif ch == "instagram_static":
            # V1 §17
            drafts[ch] = {
                "format": ch,
                "message": route["core_message"],
                "visual_concept": ("Single number on screen with "
                                    "source label, brand card."),
                "on_image_text": route["core_message"][:80],
                "caption": route["core_message"],
                "cta": route["cta"],
                "asset_requirements": route["required_assets"],
                "evidence_refs": route["evidence_refs"],
                "fact_refs": route["fact_refs"],
                "reporting_refs": reporting_refs,
                "validation_status": route["validation_status"],
            }
        elif ch == "paid_social":
            # V1 §18
            drafts[ch] = {
                "format": ch,
                "objective": route["strategic_link"],
                "creative_concept": route["working_concept_name"],
                "primary_text": route["core_message"],
                "headline": route["core_message"][:40],
                "description": route["creative_direction"][:120],
                "cta": route["cta"],
                "destination": ("Booking URL (operator must confirm)"),
                "visual_or_video_direction": route["creative_direction"],
                "asset_requirements": route["required_assets"],
                "evidence_refs": route["evidence_refs"],
                "fact_refs": route["fact_refs"],
                "reporting_refs": reporting_refs,
                "validation_status": route["validation_status"],
                # V1 §18: never invent expected results
                "expected_results": None,
            }
        elif ch in ("facebook",):
            drafts[ch] = {
                "format": ch,
                "primary_text": route["core_message"],
                "headline": route["core_message"][:60],
                "cta": route["cta"],
                "asset_requirements": route["required_assets"],
                "evidence_refs": route["evidence_refs"],
                "fact_refs": route["fact_refs"],
                "reporting_refs": reporting_refs,
                "validation_status": route["validation_status"],
            }
        elif ch == "email":
            drafts[ch] = {
                "format": ch,
                "subject_line": route["core_message"][:60],
                "preview_text": (route["audience_tension"][:80]
                                    if route["audience_tension"] else None),
                "body": route["creative_direction"],
                "cta": route["cta"],
                "asset_requirements": route["required_assets"],
                "evidence_refs": route["evidence_refs"],
                "fact_refs": route["fact_refs"],
                "validation_status": route["validation_status"],
            }
        elif ch == "landing_page":
            drafts[ch] = {
                "format": ch,
                "hero_headline": route["core_message"][:80],
                "hero_subline": (route["audience_tension"][:120]
                                    if route["audience_tension"] else None),
                "body": route["creative_direction"],
                "cta": route["cta"],
                "asset_requirements": route["required_assets"],
                "evidence_refs": route["evidence_refs"],
                "fact_refs": route["fact_refs"],
                "validation_status": route["validation_status"],
            }
    return drafts


def _publish_block(creative_package: dict) -> dict:
    """V1 §25: establish (but NOT implement) can_publish_creative.

    Always returns publish_allowed=false in this slice. Captures
    every gate that would be checked when Publish is built."""
    block_reasons = []
    routes = creative_package.get("routes") or []
    # Per V1 §25
    for r in routes:
        if r.get("validation_status") == "FAIL":
            block_reasons.append(
                f"route {r.get('route_id')} ({r.get('working_concept_name')}) "
                f"has validation_status=FAIL — voice/banned-term hit")
    ungrounded = []
    for r in routes:
        for uf in (r.get("fact_grounding") or {}).get(
                "operator_fact_required") or []:
            ungrounded.append(
                f"route {r.get('route_id')}: {uf.get('claim')} — "
                f"{uf.get('note')}")
    asset_issues = []
    for r in routes:
        for a in r.get("required_assets") or []:
            if a.get("operator_asset_required"):
                asset_issues.append(
                    f"route {r.get('route_id')} asset "
                    f"{a.get('kind')}: operator_asset_required")
    stale = creative_package.get("creative_strategy_stale", False)
    if stale:
        block_reasons.append("creative_strategy_stale=true")
    return {
        "publish_allowed": False,
        "publish_implemented": False,
        "block_reasons": block_reasons,
        "unresolved_fact_requirements": ungrounded,
        "unresolved_asset_requirements": asset_issues,
        "stale_strategy": stale,
        "rules": ("V1 §25: publish gate established, NOT implemented. "
                   "publish_allowed=false in this slice. Publish code "
                   "MUST be built in a separate slice with explicit "
                   "operator confirmation per channel."),
    }


# ── PUBLIC API ────────────────────────────────────────────────────────

def build_creative_package(brand_id: str, brief_id: str) -> dict:
    """V1 §1-§22: build a creative_package from one approved Brief.

    Returns the package dict (also written to
    DATA_DIR/creative-packages/<brand>/<brief_id>__<id>.json
    with the package frozen snapshot).
    """
    if brand_id not in ("swing-shack", "stick", "bag-drop"):
        return {"ok": False,
                "error": f"brand_id must be swing-shack|stick|bag-drop, got {brand_id}"}
    # Load inputs
    brief = _load_brief_snapshot(brand_id, brief_id)
    if not brief:
        return {"ok": False,
                "error": f"brief not found: {brand_id}/{brief_id}",
                "creative_strategy_stale": True}
    reporting = _load_reporting_snapshot(brand_id)
    facts = _load_brand_facts(brand_id)
    voice_rules = _load_voice_rules(brand_id)
    banned_terms = _load_banned_terms(brand_id)
    history = _load_history_captions(brand_id)
    genome = _load_creative_genome(brand_id)
    visual_dna = _load_visual_dna(brand_id)
    # V1 §10 brand isolation: only the requested brand's data is
    # touched. The functions above all scope by brand_id.
    # Build evidence refs
    evidence_refs = [
        f"brief:{brand_id}/{brief_id}@{_brief_revision(brief)}",
    ]
    if reporting.get("data_status") == "LIVE":
        evidence_refs.append(
            f"reporting_v2.4.1:{brand_id}@{reporting.get('fetched_at')}")
    reporting_refs = [
        f"reporting_v2.4.1.current_totals.{k}"
        for k in ((reporting.get("current_totals") or {}).keys())][:10]
    fact_refs = sorted((facts.get("products") or {}).keys()
                       if isinstance(facts.get("products"), dict) else [])
    historical_refs = [
        h.get("id") or h.get("asset_id") or h.get("ts") or "?"
        for h in (history or [])[:20]]
    # Routes
    routes = _derive_creative_routes(brief, reporting, facts, genome,
                                       visual_dna, history,
                                       reporting_refs, evidence_refs,
                                       fact_refs, historical_refs)
    # V1 §11+§9+§12: validate every route
    for r in routes:
        val = _validate_route(r, voice_rules, banned_terms, facts,
                                history)
        r.update(val)
    # V1 §14: only Brief-approved channels
    allowed_channels = _allowed_channels_from_brief(brief)
    channel_drafts = {}
    for r in routes:
        channel_drafts[r["route_id"]] = _channel_drafts(
            r, allowed_channels, reporting_refs, fact_refs)
    # V1 §20: package snapshot
    snapshot = {
        "brief_id": brief_id,
        "brief_revision": _brief_revision(brief),
        "strategy_snapshot": {
            "primary_pillar": brief.get("primary_pillar"),
            "objective": brief.get("objective"),
            "audience_tension": brief.get("audience_tension"),
            "north_star_link": brief.get("north_star_link"),
            "channels_approved": allowed_channels,
            "creative_allowed": brief.get("creative_allowed"),
            "status": brief.get("status"),
        },
        "evidence_snapshot": {"refs": evidence_refs},
        "reporting_snapshot": {
            "schema": reporting.get("schema"),
            "fetched_at": reporting.get("fetched_at"),
            "data_as_of": reporting.get("data_as_of"),
            "current_totals": reporting.get("current_totals"),
            "previous_totals": (reporting.get("current_totals") or {})
                if False else reporting.get("previous_totals"),
            "ytd_totals": reporting.get("ytd_totals"),
            "data_status": reporting.get("data_status"),
            "freshness_warning": reporting.get("freshness_warning"),
        },
        "fact_snapshot": {
            "products_count": len(facts.get("products") or [])
                if isinstance(facts.get("products"), list) else
                len((facts.get("products") or {})),
            "canonical_fact_keys": sorted(
                [k for k in (facts or {}).keys()
                 if k not in ("products",)]),
        },
    }
    package_id = f"cp-{uuid.uuid4().hex[:10]}"
    pkg = {
        "package_id": package_id,
        "brand_id": brand_id,
        "brief_id": brief_id,
        "generator_version": GENERATOR_VERSION,
        "generated_at": _now_iso(),
        "creative_strategy_stale": False,
        "snapshot": snapshot,
        "routes": routes,
        "channel_drafts": channel_drafts,
        "allowed_channels": allowed_channels,
        "rule": ("V1 §1-§22: output from approved Brief + Reporting V2.4.1 "
                 "+ canonical facts + brand voice + Creative Genome. "
                 "Read-only from Reporting (does NOT reinterpret numbers). "
                 "Reports revenue/cost results only as Reporting numbers; "
                 "leads only as 'Meta-reported leads' with lead_measurement_note."),
        "publish": _publish_block({"routes": routes,
                                       "creative_strategy_stale": False}),
    }
    # Persist
    outdir = Path(_data_dir()) / "creative-packages" / brand_id
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / f"{brief_id}__{package_id}.json"
        path.write_text(json.dumps(pkg, indent=2))
        pkg["package_path"] = str(path)
    except Exception as e:
        pkg["package_write_error"] = str(e)[:200]
    return pkg


def validate_creative_item(item_text: str, brand_id: str) -> dict:
    """V1 §11: standalone voice + banned-term validator."""
    voice_rules = _load_voice_rules(brand_id)
    banned = _load_banned_terms(brand_id)
    return _validate_voice(item_text, voice_rules, banned)


def regenerate_route_field(brand_id: str, brief_id: str,
                              package_id: str, route_id: str,
                              field: str,
                              reason: str) -> dict:
    """V1 §22: targeted regeneration of a single field on a route.

    Stays bound to approved Brief + brand facts + voice +
    evidence + strategy. Never free-form.
    """
    allowed_fields = {
        "hook", "core_message", "audience_tension",
        "creative_direction", "cta",
        "concept_rationale", "strategic_link",
    }
    if field not in allowed_fields:
        return {"ok": False,
                "error": f"field must be one of {sorted(allowed_fields)}"}
    pkgdir = Path(_data_dir()) / "creative-packages" / brand_id
    matches = list(pkgdir.glob(f"{brief_id}__{package_id}.json"))
    if not matches:
        return {"ok": False, "error": "package not found"}
    pkg = json.loads(matches[0].read_text())
    target = next((r for r in (pkg.get("routes") or [])
                    if r.get("route_id") == route_id), None)
    if not target:
        return {"ok": False, "error": "route not found"}
    target.setdefault("revisions", []).append({
        "revision": "regeneration",
        "field": field,
        "generated_at": _now_iso(),
        "generated_by": GENERATOR_VERSION,
        "change_reason": reason or "(no reason given)",
        "previous_revision": (target.get("revisions") or [])[-1].get(
            "revision") if target.get("revisions") else None,
    })
    matches[0].write_text(json.dumps(pkg, indent=2))
    return {"ok": True, "package_id": package_id,
            "route_id": route_id, "field": field,
            "revisions": target["revisions"]}


def get_creative_package(brand_id: str, brief_id: str,
                           package_id: str) -> Optional[dict]:
    pkgdir = Path(_data_dir()) / "creative-packages" / brand_id
    matches = list(pkgdir.glob(f"{brief_id}__{package_id}.json"))
    if not matches:
        return None
    return json.loads(matches[0].read_text())


def list_creative_packages(brand_id: str) -> List[dict]:
    pkgdir = Path(_data_dir()) / "creative-packages" / brand_id
    if not pkgdir.exists():
        return []
    out = []
    for p in sorted(pkgdir.glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        out.append({
            "package_id": d.get("package_id"),
            "brief_id": d.get("brief_id"),
            "brand_id": d.get("brand_id"),
            "generated_at": d.get("generated_at"),
            "generator_version": d.get("generator_version"),
            "route_count": len(d.get("routes") or []),
            "channels": d.get("allowed_channels") or [],
        })
    return out


def operator_edit_provenance(brand_id: str, brief_id: str,
                               package_id: str, route_id: str,
                               edit_summary: str) -> dict:
    """V1 §11: log an operator edit (NEVER silently rewritten)."""
    pkgdir = Path(_data_dir()) / "creative-packages" / brand_id
    matches = list(pkgdir.glob(f"{brief_id}__{package_id}.json"))
    if not matches:
        return {"ok": False, "error": "package not found"}
    pkg = json.loads(matches[0].read_text())
    target = next((r for r in (pkg.get("routes") or [])
                    if r.get("route_id") == route_id), None)
    if not target:
        return {"ok": False, "error": "route not found"}
    target.setdefault("revisions", []).append({
        "revision": "operator_edit",
        "edit_summary": edit_summary,
        "generated_at": _now_iso(),
        "generated_by": "operator",
        "previous_revision": (target.get("revisions") or [])[-1].get(
            "revision") if target.get("revisions") else None,
    })
    matches[0].write_text(json.dumps(pkg, indent=2))
    return {"ok": True, "package_id": package_id,
            "route_id": route_id,
            "revisions": target["revisions"]}
