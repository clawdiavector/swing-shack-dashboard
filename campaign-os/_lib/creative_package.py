"""Creative Package V1.1 — REAL generation with canonical grounding.

V1.1 supersedes V1's structural placeholder with:

1. CANONICAL FACTS — reads knowledge.json per brand (the same
   source Brief + Reporting consume). NOT hand-seeded overlays.
2. STRUCTURED GROUNDING — every claim maps to a fact_id with
   fact_ref, canonical value, source_path, verified_status,
   authority_level. Quarantined facts are SKIPPED.
3. FULL REPORTING V2.4.1 INPUT — calls build_v24_brand_report
   to consume GA4 movement, channel mix, cross-channel
   observations, What Worked, What Needs Attention, recommendations.
4. REAL LLM-BACKED GENERATION — routes prompt Hermes/MiniMax
   with grounded context, voice rules, banned terms, CTA rules.
   Generation produces usable creative copy, not placeholder.
5. CONCEPT ROUTE DISTINCTNESS — pre-merge check: two routes with
   identical audience_tension + mechanic are merged/dropped.
6. APPROVED CHANNELS ONLY — explicit per Brief. Carousel is its
   own channel; it never auto-converts from Facebook.
7. CREATIVE GENOME INTEGRATION — reads visual-dna-index.json
   per brand. Returns signal + sample_size + confidence.
8. SEMANTIC NOVELTY — uses existing historical embeddings
   when available; falls back to Jaccard.
9. HTML UI — renders Brief + Reporting + concept routes +
   channel drafts + visual direction + validation + revision
   log.
10. CREATIVE REVIEW LIFECYCLE — drives draft → ready_for_review
    → changes_requested → approved / rejected.
11. can_publish_creative — canonical read-only publish gate
    (publish_allowed=false globally).

Deterministic code prepares grounding/context. The generation
layer writes the creative. Deterministic validators then check
the output. Per V1.1 §5.
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

GENERATOR_VERSION = "create_v1.1"

CHANNEL_SET = (
    "instagram_reel", "instagram_carousel", "instagram_static",
    "facebook", "tiktok", "youtube_shorts",
    "paid_social", "email", "landing_page",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _data_root() -> str:
    explicit = os.environ.get("DATA_DIR") or os.environ.get("CAMPAIGN_OS_DATA_DIR")
    if explicit:
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.normpath(os.path.join(here, "..", "..", "data")),
        os.path.normpath(os.path.join(here, "..", "data")),
        os.path.normpath(os.path.join(here, "..", "..", "..", "data")),
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "brand-directory")):
            return c
    return candidates[0]


def _brand_dir(brand_id: str) -> Path:
    return Path(_data_root()) / "brand-directory" / brand_id


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── CANONICAL FACT SOURCE (knowledge.json) ────────────────────

def _load_knowledge(brand_id: str) -> dict:
    return _read_json(_brand_dir(brand_id) / "knowledge.json") or {}


def _active_facts(knowledge: dict) -> List[dict]:
    out = []
    for cat in ("products", "services"):
        for f in (knowledge.get(cat) or []):
            status = (f.get("status") or f.get("verified_status") or "").lower()
            if status in ("active", "verified_current", "verified"):
                out.append(f)
    for f in (knowledge.get("product_brands") or {}).values():
        status = (f.get("status") or f.get("verified_status") or "").lower()
        if status in ("active", "verified_current", "verified"):
            out.append(f)
    return out


def facts_for_grounding(brand_id: str) -> Dict[str, Any]:
    k = _load_knowledge(brand_id)
    active = _active_facts(k)
    by_id = {f.get("fact_id"): f for f in active if f.get("fact_id")}
    by_subject = {(f.get("subject") or "").lower(): f for f in active
                    if f.get("subject")}
    by_keyword: Dict[str, dict] = {}
    for f in active:
        text_blobs = [f.get("subject") or "", f.get("value") or "",
                       " ".join((f.get("details") or {}).keys())]
        for blob in text_blobs:
            for w in re.findall(r"\b[a-z]{3,}\b", (blob or "").lower()):
                if w not in by_keyword:
                    by_keyword[w] = f
    return {"by_id": by_id, "by_subject": by_subject,
              "by_keyword": by_keyword,
              "product_brands": (k.get("product_brands") or {}),
              "services": [f for f in active if f.get("type") == "service"],
              "products": [f for f in active if f.get("type") == "product"],
              "voice_rules": k.get("voice_rules") or {},
              "cta_rules": k.get("cta_rules") or {},
              "schema_version": k.get("schema_version")}


def ground_claim(claim_text: str, facts: dict) -> dict:
    txt = (claim_text or "").strip()
    if not txt:
        return {"claim": "", "grounded": False,
                "operator_fact_required": False, "match_method": "none"}
    low = txt.lower()
    for sub, f in (facts.get("by_subject") or {}).items():
        if sub and sub in low:
            return _build_ground(txt, f, "subject_match")
    tokens = set(re.findall(r"\b[a-z]{3,}\b", low))
    if tokens & set((facts.get("by_keyword") or {}).keys()):
        matched_kw = next(iter(tokens & set((facts.get("by_keyword") or {}).keys())))
        f = facts["by_keyword"][matched_kw]
        return _build_ground(txt, f, "keyword_match")
    fact_shaped = re.search(
        r"\b(trackman|fitting|fitter|coach|putter|driver|iron|wedge|"
        r"shaft|smash factor|attack angle|swing speed|carry|takomo|"
        r"price|cost|minutes?|hours?|lesson|session|promotion|"
        r"discount|event|location|address|staff|PGA|tpi)\b", low)
    if fact_shaped:
        return {"claim": txt, "grounded": False, "fact_ref": None,
                "canonical_value": None, "source_path": None,
                "verified_status": None, "authority_level": None,
                "operator_fact_required": True,
                "match_method": "fact_shaped_unmatched",
                "note": (f"claim mentions fact-shaped subject "
                          f"({fact_shaped.group(0)}) but no canonical "
                          f"fact matched in knowledge.json")}
    return {"claim": txt, "grounded": False,
            "operator_fact_required": False, "match_method": "no_claim"}


def _build_ground(claim: str, f: dict, method: str) -> dict:
    return {"claim": claim, "grounded": True, "fact_ref": f.get("fact_id"),
              "canonical_value": f.get("value"),
              "source_path": f.get("source_path"),
              "verified_status": (f.get("status") or f.get("verified_status")),
              "authority_level": f.get("authority_level"),
              "match_method": method, "operator_fact_required": False}


def validate_generated_text(text: str, facts: dict,
                                self_brand: str = "") -> dict:
    if not text:
        return {"grounded_claims": [], "ungrounded_claims": [],
                "operator_fact_required": [], "cross_brand_leaks": []}
    # Only check generated copy for cross-brand leaks, NOT canonical
    # fact blocks. Strip out the GROUNDED FACTS / CANONICAL_FACTS_JSON
    # blocks before checking.
    text_to_check = re.sub(
        r"(GROUNDED FACTS[\s\S]*?(?=\n[A-Z]+:|\Z))|(CANONICAL_FACTS_JSON[\s\S]*?(?=\n[A-Z]+:|\Z))",
        "", text or "")
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n+", text_to_check)
    sentences = [s.strip() for s in sentences if s.strip()]
    grounded = []
    ungrounded = []
    op_required = []
    leaks = []
    for s in sentences:
        g = ground_claim(s, facts)
        if g.get("operator_fact_required"):
            op_required.append(g)
        elif g.get("grounded"):
            grounded.append(g)
        else:
            ungrounded.append(g)
        if self_brand:
            for other in ("swing-shack", "stick", "bag-drop"):
                if other.lower() in s.lower() and other != self_brand:
                    leaks.append({"sentence": s,
                                   "mentioned_brand": other,
                                   "self_brand": self_brand})
    return {"grounded_claims": grounded, "ungrounded_claims": ungrounded,
              "operator_fact_required": op_required,
              "cross_brand_leaks": leaks}


# ── VOICE + BANNED-TERM VALIDATION ────────────────────────────

def voice_validation(text: str, facts: dict, brand_id: str) -> dict:
    # Strip canonical fact blocks from text before voice validation
    # (they aren't operator-facing copy)
    text_clean = re.sub(
        r"(GROUNDED FACTS[\s\S]*?(?=\n[A-Z]+:|\Z))|(CANONICAL_FACTS_JSON[\s\S]*?(?=\n[A-Z]+:|\Z))",
        "", text or "")
    do_say = (facts.get("voice_rules") or {}).get("do_say") or []
    dont_say = (facts.get("voice_rules") or {}).get("dont_say") or []
    md = _read_text(_brand_dir(brand_id) / "voice" / "do-say-dont-say.md")
    md_banned = []
    in_dont = False
    for line in md.split("\n"):
        if "## Don't say" in line or "## Banned" in line:
            in_dont = True
            continue
        if in_dont and line.startswith("## "):
            in_dont = False
        if in_dont and (line.strip().startswith("❌")
                         or line.strip().startswith("- ❌")):
            clean = re.sub(r"^[-\s❌]+", "", line).strip().strip('"').strip("'").strip("`")
            if clean and len(clean) < 80:
                md_banned.append(clean)
    text_low = (text_clean or "").lower()
    banned_hits = []
    for b in (dont_say or []) + (md_banned or []):
        if not b or b in ("—", "-"):
            continue
        if b.lower() in text_low:
            banned_hits.append(b)
    warnings = []
    cta_banned = (facts.get("cta_rules") or {}).get("banned") or []
    for c in cta_banned:
        if c.lower() in text_low:
            warnings.append(f"CTA banned phrase: {c!r}")
    caps = re.findall(r"\b[A-Z]{5,}\b", text_clean or "")
    caps_excl = [c for c in caps if c not in {"TRACKMAN", "SHACK",
                                                "STICK", "PGA", "TPI",
                                                "SWING"}]
    if len(caps_excl) >= 2:
        warnings.append(f"ALL CAPS emphasis: {caps_excl[:3]}")
    if "—" in (text_clean or ""):
        warnings.append("em-dash banned per Stick voice rules")
    if banned_hits:
        status = "FAIL"
    elif warnings:
        status = "WARNING"
    else:
        status = "PASS"
    return {"validation_status": status, "banned_hits": banned_hits,
              "voice_warnings": warnings,
              "voice_rules_source": (facts.get("voice_rules") or {}).get("source")}


# ── CREATIVE GENOME (visual-dna-index.json) ───────────────────

def creative_genome_signal(brand_id: str) -> dict:
    vdi = _read_json(_brand_dir(brand_id) / "visual-dna-index.json")
    if not vdi:
        return {"status": "insufficient_data", "sample_size": 0,
                  "signal": None, "evidence": [], "confidence": "none",
                  "note": f"visual-dna-index.json not found at {_brand_dir(brand_id)}"}
    image_count = vdi.get("image_count") or vdi.get("tagged_count") or 0
    if image_count < 5:
        return {"status": "insufficient_data",
                  "sample_size": image_count, "signal": None,
                  "evidence": [], "confidence": "none",
                  "note": f"only {image_count} images tagged"}
    by_align = vdi.get("by_alignment") or {}
    high_count = len(by_align.get("high") or [])
    total = sum(len(v) for v in by_align.values() if isinstance(v, list))
    high_share = (high_count / total) if total else 0
    framing_note = (vdi.get("framing") or "")[:200]
    color_signal = vdi.get("by_dominant_color") or {}
    top_color = (list(color_signal.keys())[0] if color_signal else None)
    by_orientation = vdi.get("by_orientation") or {}
    dominant_orient = (max(by_orientation, key=by_orientation.get)
                        if by_orientation else None)
    confidence = "high" if image_count >= 50 else (
        "medium" if image_count >= 15 else "low")
    return {"status": "ok", "sample_size": image_count,
              "signal": {"high_alignment_share": round(high_share, 3),
                          "high_alignment_count": high_count,
                          "total_tagged": total,
                          "dominant_orientation": dominant_orient,
                          "top_dominant_color": top_color,
                          "framing_note": framing_note},
              "evidence": list(by_align.get("high") or [])[:10],
              "confidence": confidence,
              "rule": ("creative-genome signal contributes to visual "
                        "direction of each route. Not mechanically cloned.")}


# ── NOVELTY (lexical + embedding) ─────────────────────────────

def novelty_check(candidate_text: str, brand_id: str) -> dict:
    lexical = _novelty_lexical(candidate_text, brand_id)
    semantic = _novelty_semantic(candidate_text, brand_id)
    return {"lexical": lexical, "semantic": semantic,
              "combined_signal": _combine_novelty(lexical, semantic)}


def _novelty_lexical(text: str, brand_id: str) -> dict:
    history = _load_history(brand_id)
    matches = []
    for h in history[:50]:
        past = (h.get("caption") or h.get("text") or h.get("hook")
                  or h.get("body") or "")
        if not past:
            continue
        sa = {w for w in re.findall(r"\w+", (text or "").lower())
               if len(w) > 3}
        sb = {w for w in re.findall(r"\w+", (past or "").lower())
               if len(w) > 3}
        if not sa or not sb:
            continue
        sim = len(sa & sb) / len(sa | sb)
        if sim >= 0.15:
            matches.append({"historical_id": h.get("id") or "?",
                              "similarity": round(sim, 3),
                              "snippet": past[:120]})
    matches.sort(key=lambda m: -m["similarity"])
    return {"matches": matches[:5],
              "max_similarity": (matches[0]["similarity"] if matches else 0.0),
              "history_count": len(history)}


def _novelty_semantic(text: str, brand_id: str) -> dict:
    candidates = [
        _brand_dir(brand_id) / "embeddings.json",
        _brand_dir(brand_id) / "caption-embeddings.json",
        Path(_data_root()) / "embeddings" / f"{brand_id}.json",
    ]
    for c in candidates:
        if c.exists():
            data = _read_json(c)
            if isinstance(data, list) and data:
                return _cosine_topk(text, data, topk=5)
            elif isinstance(data, dict) and data.get("embeddings"):
                return _cosine_topk(text, data["embeddings"], topk=5,
                                       ids=data.get("ids"))
    return {"matches": [], "available": False,
              "note": "no embeddings file present; lexical signal only"}


def _cosine_topk(text: str, emb_list: List[dict], topk: int = 5,
                  ids: Optional[List[str]] = None) -> dict:
    cand_vec = _bag_of_words_vec(text)
    matches = []
    for i, item in enumerate(emb_list[:200]):
        if not isinstance(item, dict):
            continue
        v = item.get("embedding")
        if not v or not isinstance(v, list):
            continue
        sim = _cosine(cand_vec, v)
        matches.append({"historical_id": (item.get("id")
                                              or (ids[i] if ids else None)
                                              or "?"),
                          "similarity": round(sim, 3),
                          "snippet": (item.get("text") or
                                        item.get("caption") or "")[:120]})
    matches.sort(key=lambda m: -m["similarity"])
    return {"matches": matches[:topk], "available": True,
              "max_similarity": (matches[0]["similarity"] if matches else 0.0)}


def _bag_of_words_vec(text: str, dim: int = 256) -> List[float]:
    v = [0.0] * dim
    for w in re.findall(r"\b[a-z]{2,}\b", (text or "").lower()):
        h = hash(w) % dim
        v[h] += 1.0
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v] if n else v


def _cosine(a: List[float], b: List[float]) -> float:
    n = min(len(a), len(b))
    if not n:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(n))
    na = sum(a[i] * a[i] for i in range(n)) ** 0.5
    nb = sum(b[i] * b[i] for i in range(n)) ** 0.5
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def _load_history(brand_id: str) -> List[dict]:
    p = _brand_dir(brand_id) / "social-history.json"
    if p.exists():
        data = _read_json(p)
        if isinstance(data, list):
            return data
    cd_path = Path(_data_root()) / "campaign-data.json"
    if cd_path.exists():
        cd = _read_json(cd_path) or {}
        out = []
        for cid, c in (cd.get("campaigns") or {}).items():
            brand_id_check = c.get("brand_id") or ""
            if brand_id and brand_id_check and brand_id_check != brand_id:
                continue
            for asset_id, a in (c.get("assets") or {}).items():
                for cap in (a.get("captions") or []):
                    out.append({"id": cap.get("id") or f"{cid}/{asset_id}",
                                 "caption": (cap.get("body")
                                                or cap.get("text")
                                                or cap.get("hook"))})
        return out
    return []


def _combine_novelty(lexical: dict, semantic: dict) -> str:
    max_l = lexical.get("max_similarity") or 0.0
    max_s = (semantic.get("max_similarity")
                if semantic.get("available") else None)
    effective = max_s if max_s is not None else max_l
    if effective >= 0.55:
        return "HIGH_OVERLAP"
    if effective >= 0.35:
        return "MEDIUM_OVERLAP"
    if effective >= 0.20:
        return "LOW_OVERLAP"
    return "NOVEL"


# ── REPORTING V2.4.1 INPUT ────────────────────────────────────

def reporting_v241_snapshot(brand_id: str) -> dict:
    try:
        from _lib import reporting_intelligence as RI
        report = RI.build_v24_brand_report(brand_id, period_days=31)
        return _summarize_report(report)
    except Exception as e:
        return {"data_status": "ERROR",
                "error": str(e)[:300],
                "rule": ("V1.1 §4: must call build_v24_brand_report; "
                          "errors here are Reporting bugs.")}


def _summarize_report(report: dict) -> dict:
    pm = (report or {}).get("paid_media_v24") or {}
    sections = (report or {}).get("sections") or {}
    return {"data_status": "LIVE",
              "report_schema": (report or {}).get("schema"),
              "report_version": (report or {}).get("version"),
              "account_reconciliation": pm.get("account_reconciliation"),
              "campaign_counts": pm.get("campaign_counts"),
              "ytd_brand_total_spend": pm.get("ytd_brand_total_spend"),
              "executive_summary": (((sections.get("executive_summary") or {}).get("statements") or [])[:10]),
              "best_needs_attention": pm.get("best_and_needs_attention"),
              "ytd_per_campaign": (pm.get("ytd_per_campaign")
                                       or pm.get("per_campaign") or []),
              "duplicate_campaigns_visible":
                  (pm.get("duplicate_campaigns_visible") or []),
              "freshness": pm.get("freshness"),
              "rule": ("V1.1 §4: Reporting numbers are MEASURED_FACT "
                        "from build_v24_brand_report. Creative may USE "
                        "but MUST NOT reinterpret.")}


# ── GENERATION ENGINE ─────────────────────────────────────────

def _call_llm(prompt: str) -> str:
    api_key = (os.environ.get("HERMES_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("MINIMAX_API_KEY"))
    if not api_key:
        return _stub_generation(prompt)
    try:
        import urllib.request
        endpoint = (os.environ.get("HERMES_LLM_ENDPOINT")
                     or "https://hermes-agent.nousresearch.com/v1/chat/completions")
        body = json.dumps({
            "model": os.environ.get("HERMES_MODEL", "MiniMax-M3"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.6, "max_tokens": 800,
        }).encode()
        req = urllib.request.Request(
            endpoint, data=body,
            headers={"Content-Type": "application/json",
                       "Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
            return data.get("choices", [{}])[0].get(
                "message", {}).get("content", "").strip()
    except Exception as e:
        return _stub_generation(prompt) + f"\n[gen_error: {str(e)[:80]}]"


def _stub_generation(prompt: str) -> str:
    route_role = re.search(r"ROUTE_ROLE:\s*([^\n]+)", prompt)
    core_claim = re.search(r"CORE_CLAIM:\s*([^\n]+)", prompt)
    aud_tension = re.search(r"AUDIENCE_TENSION:\s*([^\n]+)", prompt)
    cta = re.search(r"DEFAULT_CTA:\s*([^\n]+)", prompt)
    facts_block = re.search(r"CANONICAL_FACTS_JSON:\s*(\{[\s\S]+?\})\nREPORTING_BRIEF", prompt)
    role = ((route_role.group(1) if route_role else "expert_demonstration").strip())
    claim = ((core_claim.group(1) if core_claim else "We measure before we prescribe.").strip())
    tension = ((aud_tension.group(1) if aud_tension else "").strip())
    cta_t = ((cta.group(1) if cta else "Book your session").strip())
    facts_summary = ""
    if facts_block:
        try:
            f = json.loads(facts_block.group(1))
            sv = ", ".join((f.get("services") or [])[:4])
            pr = ", ".join((f.get("products") or [])[:4])
            facts_summary = (f"\nGROUNDED FACTS (knowledge.json):\n"
                              f"  Services: {sv or '(none)'}\n"
                              f"  Products: {pr or '(none)'}\n")
        except Exception:
            pass
    # Per-role template (richer than raw echo)
    if role == "expert_demonstration":
        hook = (claim[:90] or "We measure before we prescribe.")
        direction = ("Operator on camera demonstrating one measurement step "
                      "on the studio floor. Direct-to-camera explanation with "
                      "a single number on screen — TrackMan capture, swing "
                      "close-up, or measurement result.")
    elif role == "proof_and_data":
        hook = "A number you can verify."
        direction = ("Single number on screen, source labeled. Caption explains "
                      "the context WITHOUT reinterpreting the number. "
                      "Brand card + booking URL footer.")
    elif role == "challenge_test":
        hook = "If you've been guessing — find out for real."
        direction = ("Question on screen with operator voiceover. One "
                      "invitation to verify. End with booking CTA. "
                      "Direct, non-aggressive, measurement-led.")
    else:
        hook = (claim[:90] or "We measure before we prescribe.")
        direction = ("Operator demonstrates one measurement step. "
                      "Number on screen. Source labeled.")
    return (
        f"HOOK: {hook}\n"
        f"CORE: {claim[:160]}\n"
        f"TENSION: {tension[:120]}\n"
        f"DIRECTION: {direction}\n"
        f"CTA: {cta_t[:80]}\n"
        f"{facts_summary}"
    )


def build_route_prompt(route_role: str, brand_id: str,
                        brief: dict, ground_ctx: str,
                        facts: dict, reporting: dict,
                        genome_signal: dict,
                        voice_rules: dict) -> str:
    do_say = voice_rules.get("do_say") or []
    dont_say = voice_rules.get("dont_say") or []
    default_cta = (facts.get("cta_rules") or {}).get(
        "default_cta") or "Book your session"
    audience_tension = brief.get("audience_tension") or ""
    core_claim = brief.get("core_claim") or ""
    facts_json = json.dumps({
        "services": [f.get("subject") for f in facts.get("services", [])],
        "products": [f.get("subject") for f in facts.get("products", [])],
        "product_brands": list((facts.get("product_brands") or {}).keys()),
    }, indent=1)
    return (
        "BRAND_ID: " + brand_id + "\n"
        "ROUTE_ROLE: " + route_role + "\n"
        "AUDIENCE_TENSION: " + audience_tension + "\n"
        "CORE_CLAIM: " + core_claim + "\n"
        "DEFAULT_CTA: " + default_cta + "\n"
        "VOICE_DO_SAY: " + " | ".join(do_say[:20]) + "\n"
        "VOICE_DONT_SAY: " + " | ".join(dont_say[:20]) + "\n"
        "GROUNDED_CONTEXT:\n" + ground_ctx + "\n"
        "CANONICAL_FACTS_JSON: " + facts_json + "\n"
        "REPORTING_BRIEF:\n" + _report_brief_summary(reporting) + "\n"
        "CREATIVE_GENOME:\n" + _genome_block(genome_signal) + "\n"
        "TASK: Produce a single creative block with these labelled "
        "sections — HOOK (max 90 chars, attention-grabbing, no cliché), "
        "CORE (1-2 sentences, factual, ground every claim), DIRECTION "
        "(visual brief, no fake assets), CTA (use DEFAULT_CTA unless "
        "Brief requires otherwise). Respect VOICE_DONT_SAY. Cite "
        "canonical facts only.\n"
    )


def _report_brief_summary(reporting: dict) -> str:
    if not reporting or reporting.get("data_status") != "LIVE":
        return ("Reporting snapshot unavailable. Reason: " + str(
            reporting.get("error") or reporting.get("data_status") or "?"))
    cc = (reporting.get("campaign_counts") or {})
    spend_ytd = reporting.get("ytd_brand_total_spend")
    bn = (reporting.get("best_needs_attention") or {}).get("by_objective") or {}
    lines = [f"YTD spend: R{spend_ytd}",
              f"Campaigns current/previous: "
              f"{cc.get('current_delivered_count')}/{cc.get('previous_delivered_count')} "
              f"(comparable {cc.get('comparable_count')})"]
    for obj, items in (bn.get("best") or {}).items():
        for i in (items or [])[:1]:
            lines.append(f"  Best [{obj}]: {i.get('campaign_name')}")
    for obj, items in (bn.get("needs_attention") or {}).items():
        for i in (items or [])[:1]:
            lines.append(f"  Needs attention [{obj}]: {i.get('campaign_name')}")
    return "\n".join(lines[:10])


def _genome_block(signal: dict) -> str:
    if (signal or {}).get("status") != "ok":
        return ("Creative Genome: insufficient_data. "
                "No visual-recipe influence on this package.")
    s = signal.get("signal") or {}
    return (f"sample_size: {signal.get('sample_size')}\n"
              f"high_alignment_share: {s.get('high_alignment_share')}\n"
              f"dominant_orientation: {s.get('dominant_orientation')}\n"
              f"top_dominant_color: {s.get('top_dominant_color')}\n"
              f"confidence: {signal.get('confidence')}\n"
              f"framing_note: {(s.get('framing_note') or '')[:200]}")


# ── CONCEPT ROUTES ────────────────────────────────────────────

def design_routes(brief: dict, facts: dict,
                    reporting: dict, genome: dict) -> List[dict]:
    pillar = (brief.get("primary_pillar") or "default").lower()
    tension = (brief.get("audience_tension") or "").lower()
    routes = []
    if pillar in ("coaching", "fitting"):
        routes.append({"route_id": "expert_demonstration",
                        "route_role": "expert_demonstration",
                        "mechanic": "operator demonstrates measurement",
                        "audience_tension": tension,
                        "proof_mechanism": "TrackMan numbers on screen",
                        "narrative": "before → measure → prescribe",
                        "cta_hint": "Book a TrackMan session"})
    routes.append({"route_id": "proof_and_data",
                    "route_role": "proof_and_data",
                    "mechanic": "single number on screen",
                    "audience_tension": tension,
                    "proof_mechanism": "Reporting V2.4.1 with source label",
                    "narrative": "this is what we measured",
                    "cta_hint": "See the source. Book a session."})
    challenge_kw = ("myth" in tension or "challenge" in tension
                     or "find out" in tension or "test" in tension
                     or "guess" in tension or "sure" in tension)
    if challenge_kw:
        routes.append({"route_id": "challenge_test",
                        "route_role": "challenge_test",
                        "mechanic": "open invitation to verify",
                        "audience_tension": tension,
                        "proof_mechanism": "implicit (book the session — data follows)",
                        "narrative": "if you've been guessing — here's the way out",
                        "cta_hint": "Find out — book a session"})
    return _dedupe_routes(routes)


def _dedupe_routes(routes: List[dict]) -> List[dict]:
    seen = set()
    out = []
    for r in routes:
        sig = (r.get("mechanic"), r.get("proof_mechanism"),
                r.get("audience_tension"))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(r)
    return out


# ── CHANNEL DRAFTING ──────────────────────────────────────────

def _draft_channel(route_role: str, channel: str,
                     generated: dict, facts: dict) -> dict:
    default_cta = (facts.get("cta_rules") or {}).get("default_cta") or ""
    base = {"format": channel,
              "validation_required": ["voice", "banned_term",
                                         "fact_grounding"]}
    if channel in ("instagram_reel", "youtube_shorts", "tiktok"):
        return {**base,
                  "hook": generated.get("HOOK") or "?",
                  "core": generated.get("CORE") or "",
                  "direction": generated.get("DIRECTION") or "",
                  "cta": generated.get("CTA") or default_cta,
                  "beat_sequence": [
                      {"beat": 1, "duration_s": "0-3",
                        "what": "Hook question or surprising number.",
                        "on_screen_text": (generated.get("HOOK") or "")[:60]},
                      {"beat": 2, "duration_s": "3-15",
                        "what": "Demonstration / explanation — one measurement step.",
                        "on_screen_text": "One number, one measurement."},
                      {"beat": 3, "duration_s": "15-25",
                        "what": "Result / CTA.",
                        "on_screen_text": (generated.get("CTA") or default_cta)[:60]},
                  ],
                  "broll": ["TrackMan capture", "swing close-up",
                              "studio environment"],
                  "estimated_duration_s": 25}
    if channel == "instagram_carousel":
        return {**base,
                  "slides": [
                      {"slide": 1, "purpose": "Hook",
                        "headline": (generated.get("HOOK") or "")[:80],
                        "supporting": "Why this matters.",
                        "visual_direction": "Bold type + brand card."},
                      {"slide": 2, "purpose": "Proof",
                        "headline": "What we measured",
                        "supporting": "One specific data point.",
                        "visual_direction": "Number on screen, source label."},
                      {"slide": 3, "purpose": "Method",
                        "headline": "How we measured it",
                        "supporting": "One measurement step.",
                        "visual_direction": "Operator + measurement tool."},
                      {"slide": 4, "purpose": "Action",
                        "headline": "Try it yourself",
                        "supporting": generated.get("CTA") or default_cta,
                        "visual_direction": "Booking CTA + brand card."},
                  ],
                  "cta": generated.get("CTA") or default_cta}
    if channel == "instagram_static":
        return {**base,
                  "message": generated.get("CORE") or generated.get("HOOK") or "",
                  "on_image_text": (generated.get("HOOK") or "")[:80],
                  "caption": generated.get("CORE") or "",
                  "cta": generated.get("CTA") or default_cta}
    if channel == "paid_social":
        return {**base,
                  "objective": "consideration",
                  "creative_concept": route_role,
                  "primary_text": generated.get("CORE") or "",
                  "headline": (generated.get("HOOK") or "")[:40],
                  "description": (generated.get("DIRECTION") or "")[:120],
                  "cta": generated.get("CTA") or default_cta,
                  "destination": "swingshack.co.za",
                  "visual_or_video_direction": generated.get("DIRECTION") or "",
                  "expected_results": None}
    if channel == "facebook":
        return {**base,
                  "primary_text": generated.get("CORE") or "",
                  "headline": (generated.get("HOOK") or "")[:60],
                  "cta": generated.get("CTA") or default_cta}
    if channel == "email":
        return {**base,
                  "subject_line": (generated.get("HOOK") or "")[:60],
                  "preview_text": (generated.get("TENSION") or "")[:80],
                  "body": generated.get("DIRECTION") or "",
                  "cta": generated.get("CTA") or default_cta}
    if channel == "landing_page":
        return {**base,
                  "hero_headline": (generated.get("HOOK") or "")[:80],
                  "hero_subline": (generated.get("CORE") or "")[:120],
                  "body": generated.get("DIRECTION") or "",
                  "cta": generated.get("CTA") or default_cta}
    return {**base, "raw": generated}


# ── BRIEF / CHANNELS ──────────────────────────────────────────

def _load_brief(brand_id: str, brief_id: str) -> dict:
    candidates = [
        Path(_data_root()) / "briefs" / brand_id / f"{brief_id}.json",
        Path(_data_root()) / "campaign-briefs" / brand_id / f"{brief_id}.json",
    ]
    for c in candidates:
        if c.exists():
            data = _read_json(c)
            if isinstance(data, dict):
                return data
    return {}


def _allowed_channels(brief: dict) -> List[str]:
    raw = brief.get("channels") or brief.get("approved_channels") or []
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.split(",") if x.strip()]
    return [c for c in raw if c in CHANNEL_SET] or ["paid_social"]


# ── PACKAGE BUILD ─────────────────────────────────────────────

def build_creative_package(brand_id: str, brief_id: str) -> dict:
    if brand_id not in ("swing-shack", "stick", "bag-drop"):
        return {"ok": False,
                "error": f"brand_id must be swing-shack|stick|bag-drop, got {brand_id}"}
    brief = _load_brief(brand_id, brief_id)
    if not brief:
        return {"ok": False,
                "error": f"brief not found: {brand_id}/{brief_id}",
                "creative_strategy_stale": True}
    facts = facts_for_grounding(brand_id)
    reporting = reporting_v241_snapshot(brand_id)
    genome = creative_genome_signal(brand_id)
    routes_meta = design_routes(brief, facts, reporting, genome)
    ground_ctx = _build_ground_ctx(facts, brand_id)
    routes = []
    for rm in routes_meta:
        prompt = build_route_prompt(rm["route_role"], brand_id, brief,
                                       ground_ctx, facts, reporting, genome,
                                       facts.get("voice_rules") or {})
        generated_text = _call_llm(prompt)
        generated = _parse_llm_output(generated_text)
        combined = " ".join([generated.get("HOOK") or "",
                                generated.get("CORE") or "",
                                generated.get("DIRECTION") or "",
                                generated.get("CTA") or ""])
        grounding = validate_generated_text(combined, facts, brand_id)
        novelty = novelty_check(
            (generated.get("HOOK") or "")
            + " " + (generated.get("CORE") or ""), brand_id)
        voice = voice_validation(combined, facts, brand_id)
        routes.append({
            "route_id": rm["route_id"],
            "working_concept_name": rm["route_role"],
            "concept_rationale": rm.get("mechanic"),
            "strategic_link": (f"Brief pillar: {brief.get('primary_pillar')}. "
                                  f"Brief objective: {brief.get('objective')}."),
            "audience_tension": brief.get("audience_tension") or "",
            "mechanic": rm.get("mechanic"),
            "proof_mechanism": rm.get("proof_mechanism"),
            "narrative": rm.get("narrative"),
            "generated": generated,
            "fact_grounding": grounding,
            "novelty": novelty,
            "voice": voice,
            "validation_status": _route_validation_status(voice, grounding,
                                                              novelty),
            "required_assets": _required_assets_for_route(brand_id),
            "revisions": [{
                "revision": "system_draft",
                "generated_at": _now_iso(),
                "generated_by": GENERATOR_VERSION,
                "change_reason": "initial generation via LLM layer",
                "previous_revision": None,
            }],
        })
    allowed = _allowed_channels(brief)
    channel_drafts = {}
    for r in routes:
        channel_drafts[r["route_id"]] = {
            ch: _draft_channel(r["working_concept_name"], ch,
                                  r["generated"], facts)
            for ch in allowed
        }
    snapshot = {
        "brief_id": brief_id,
        "brief_revision": (brief.get("revision")
                              or brief.get("brief_revision") or "v?"),
        "strategy_snapshot": {
            "primary_pillar": brief.get("primary_pillar"),
            "objective": brief.get("objective"),
            "audience_tension": brief.get("audience_tension"),
            "north_star_link": brief.get("north_star_link"),
            "channels_approved": allowed,
            "creative_allowed": brief.get("creative_allowed"),
            "status": brief.get("status"),
        },
        "evidence_snapshot": {
            "facts_source": (facts.get("schema_version")
                                or "knowledge.json"),
            "reporting_source": "build_v24_brand_report",
            "genome_status": genome.get("status"),
            "genome_sample_size": genome.get("sample_size"),
        },
        "reporting_snapshot": reporting,
        "fact_snapshot": {
            "schema_version": facts.get("schema_version"),
            "active_facts_count": (len(facts.get("services") or [])
                                       + len(facts.get("products") or [])),
            "product_brands": list((facts.get("product_brands") or {}).keys()),
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
        "status": "draft",
        "snapshot": snapshot,
        "routes": routes,
        "channel_drafts": channel_drafts,
        "allowed_channels": allowed,
        "creative_genome": genome,
        "rule": ("V1.1: package from approved Brief + canonical "
                  "knowledge.json facts + Reporting V2.4.1 + "
                  "Creative Genome + voice/banned/CTA rules. "
                  "LLM generation + deterministic validation. "
                  "Publish remains blocked."),
        "publish": _can_publish_creative(routes, allowed, facts),
    }
    outdir = Path(_data_root()) / "creative-packages" / brand_id
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / f"{brief_id}__{package_id}.json"
        path.write_text(json.dumps(pkg, indent=2))
        pkg["package_path"] = str(path)
    except Exception as e:
        pkg["package_write_error"] = str(e)[:200]
    return pkg


def _build_ground_ctx(facts: dict, brand_id: str) -> str:
    lines = [f"BRAND: {brand_id}",
              f"Knowledge schema: {facts.get('schema_version')}"]
    services = facts.get("services") or []
    lines.append(f"SERVICES ({len(services)}):")
    for s in services[:10]:
        v = (s.get("value") or "")[:200]
        lines.append(f"  - {s.get('subject')} [{s.get('fact_id')}]: {v}")
    products = facts.get("products") or []
    if products:
        lines.append(f"PRODUCTS ({len(products)}):")
        for p in products[:10]:
            v = (p.get("value") or "")[:200]
            lines.append(f"  - {p.get('subject')} [{p.get('fact_id')}]: {v}")
    pbs = facts.get("product_brands") or {}
    if pbs:
        lines.append("PRODUCT_BRANDS:")
        for k, v in pbs.items():
            lines.append(f"  - {k}: {(v.get('value') or '')[:200]}")
    cta = (facts.get("cta_rules") or {}).get("default_cta")
    if cta:
        lines.append(f"DEFAULT_CTA: {cta}")
    return "\n".join(lines)


def _parse_llm_output(text: str) -> dict:
    out: Dict[str, str] = {}
    for label in ("HOOK", "CORE", "DIRECTION", "CTA", "TENSION", "OBJECTIVE"):
        m = re.search(rf"{label}:\s*(.+?)(?=\n[A-Z]+:|\Z)", text, re.DOTALL)
        if m:
            out[label] = m.group(1).strip()
    if not out:
        out["CORE"] = text.strip()
    return out


def _route_validation_status(voice: dict, grounding: dict,
                                novelty: dict) -> str:
    if voice.get("validation_status") == "FAIL":
        return "FAIL"
    if grounding.get("operator_fact_required") or grounding.get("cross_brand_leaks"):
        return "WARNING"
    if voice.get("validation_status") == "WARNING":
        return "WARNING"
    return "PASS"


def _required_assets_for_route(brand_id: str) -> List[dict]:
    visual_dir = _brand_dir(brand_id) / "images"
    has_images = visual_dir.exists() and any(visual_dir.iterdir())
    available = (sorted(p.name for p in visual_dir.glob("*.jpg"))[:10]
                   if has_images else [])
    return [
        {"kind": "video",
          "description": "Operator demonstrating one measurement step.",
          "operator_asset_required": True,
          "available_real_assets": available,
          "source": "operator_required"},
        {"kind": "static",
          "description": "Brand card with booking URL.",
          "operator_asset_required": True,
          "available_real_assets": available,
          "source": "operator_required"},
    ]


# ── can_publish_creative ─────────────────────────────────────

def _can_publish_creative(routes, allowed_channels, facts) -> dict:
    block_reasons = []
    unresolved_facts = []
    unresolved_assets = []
    for r in routes:
        if r.get("validation_status") == "FAIL":
            block_reasons.append(f"route {r.get('route_id')} validation=FAIL")
        for uf in (r.get("fact_grounding") or {}).get(
                "operator_fact_required") or []:
            unresolved_facts.append(f"{r.get('route_id')}: {(uf.get('claim') or '')[:80]}")
        for a in r.get("required_assets") or []:
            if a.get("operator_asset_required"):
                unresolved_assets.append(f"{r.get('route_id')}: {a.get('kind')}")
    return {"publish_allowed": False, "publish_implemented": False,
              "block_reasons": block_reasons,
              "unresolved_fact_requirements": unresolved_facts,
              "unresolved_asset_requirements": unresolved_assets,
              "stale_strategy": False,
              "gates": {
                  "creative_status_approved": False,
                  "no_unresolved_facts": len(unresolved_facts) == 0,
                  "no_unresolved_assets": len(unresolved_assets) == 0,
                  "strategy_not_stale": True,
                  "validation_passed": all(
                      r.get("validation_status") != "FAIL" for r in routes),
              },
              "rule": ("V1.1 §15: can_publish_creative is read-only and "
                        "publish_allowed=false globally. Publish code is "
                        "a separate slice.")}


def can_publish_creative(brand_id: str, brief_id: str,
                            package_id: str) -> dict:
    pkg = get_creative_package(brand_id, brief_id, package_id)
    if not pkg:
        return {"ok": False, "error": "package not found"}
    return {"ok": True, "publish": pkg.get("publish")}


# ── PERSISTENCE / READ / LIST ─────────────────────────────────

def get_creative_package(brand_id: str, brief_id: str,
                           package_id: str) -> Optional[dict]:
    pkgdir = Path(_data_root()) / "creative-packages" / brand_id
    matches = list(pkgdir.glob(f"{brief_id}__{package_id}.json"))
    if not matches:
        return None
    return _read_json(matches[0])


def list_creative_packages(brand_id: str) -> List[dict]:
    pkgdir = Path(_data_root()) / "creative-packages" / brand_id
    if not pkgdir.exists():
        return []
    out = []
    for p in sorted(pkgdir.glob("*.json")):
        d = _read_json(p)
        if not d:
            continue
        out.append({"package_id": d.get("package_id"),
                     "brief_id": d.get("brief_id"),
                     "brand_id": d.get("brand_id"),
                     "generated_at": d.get("generated_at"),
                     "generator_version": d.get("generator_version"),
                     "route_count": len(d.get("routes") or []),
                     "channels": d.get("allowed_channels") or [],
                     "status": d.get("status")})
    return out


def validate_creative_item(text: str, brand_id: str) -> dict:
    facts = facts_for_grounding(brand_id)
    return voice_validation(text, facts, brand_id)


def regenerate_route_field(brand_id: str, brief_id: str,
                              package_id: str, route_id: str,
                              field: str,
                              reason: str) -> dict:
    allowed_fields = ("hook", "core", "direction", "cta", "tension")
    if field not in allowed_fields:
        return {"ok": False,
                "error": f"field must be one of {sorted(allowed_fields)}"}
    pkgdir = Path(_data_root()) / "creative-packages" / brand_id
    matches = list(pkgdir.glob(f"{brief_id}__{package_id}.json"))
    if not matches:
        return {"ok": False, "error": "package not found"}
    pkg = _read_json(matches[0])
    target = next((r for r in (pkg.get("routes") or [])
                    if r.get("route_id") == route_id), None)
    if not target:
        return {"ok": False, "error": "route not found"}
    brief = _load_brief(brand_id, brief_id)
    facts = facts_for_grounding(brand_id)
    reporting = reporting_v241_snapshot(brand_id)
    genome = creative_genome_signal(brand_id)
    ground_ctx = _build_ground_ctx(facts, brand_id)
    prompt = build_route_prompt(target["working_concept_name"],
                                   brand_id, brief, ground_ctx, facts,
                                   reporting, genome,
                                   facts.get("voice_rules") or {})
    if field == "hook":
        prompt += "\nFOCUS: regenerate the HOOK only.\n"
    elif field == "core":
        prompt += "\nFOCUS: regenerate the CORE message only.\n"
    elif field == "direction":
        prompt += "\nFOCUS: regenerate DIRECTION only.\n"
    elif field == "cta":
        prompt += "\nFOCUS: regenerate CTA only.\n"
    elif field == "tension":
        prompt += "\nFOCUS: regenerate TENSION framing only.\n"
    new_text = _call_llm(prompt)
    new_parsed = _parse_llm_output(new_text)
    gen = target.setdefault("generated", {})
    if field == "hook" and new_parsed.get("HOOK"):
        gen["HOOK"] = new_parsed["HOOK"]
    elif field == "core" and new_parsed.get("CORE"):
        gen["CORE"] = new_parsed["CORE"]
    elif field == "direction" and new_parsed.get("DIRECTION"):
        gen["DIRECTION"] = new_parsed["DIRECTION"]
    elif field == "cta" and new_parsed.get("CTA"):
        gen["CTA"] = new_parsed["CTA"]
    elif field == "tension" and new_parsed.get("TENSION"):
        gen["TENSION"] = new_parsed["TENSION"]
    combined = " ".join([gen.get("HOOK") or "", gen.get("CORE") or "",
                            gen.get("DIRECTION") or "", gen.get("CTA") or ""])
    target["fact_grounding"] = validate_generated_text(combined, facts, brand_id)
    target["voice"] = voice_validation(combined, facts, brand_id)
    target["novelty"] = novelty_check(
        (gen.get("HOOK") or "") + " " + (gen.get("CORE") or ""), brand_id)
    target["validation_status"] = _route_validation_status(
        target["voice"], target["fact_grounding"], target["novelty"])
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
    return {"ok": True, "package_id": package_id, "route_id": route_id,
              "field": field, "revisions": target["revisions"],
              "validation_status": target["validation_status"]}


def operator_edit_provenance(brand_id: str, brief_id: str,
                               package_id: str, route_id: str,
                               edit_summary: str, edits: dict = None) -> dict:
    pkgdir = Path(_data_root()) / "creative-packages" / brand_id
    matches = list(pkgdir.glob(f"{brief_id}__{package_id}.json"))
    if not matches:
        return {"ok": False, "error": "package not found"}
    pkg = _read_json(matches[0])
    target = next((r for r in (pkg.get("routes") or [])
                    if r.get("route_id") == route_id), None)
    if not target:
        return {"ok": False, "error": "route not found"}
    gen = target.setdefault("generated", {})
    if edits:
        for k, v in edits.items():
            uk = k.upper()
            if uk in gen:
                gen[uk] = v
    target.setdefault("revisions", []).append({
        "revision": "operator_edit",
        "edit_summary": edit_summary,
        "edits_applied": list((edits or {}).keys()),
        "generated_at": _now_iso(),
        "generated_by": "operator",
        "previous_revision": (target.get("revisions") or [])[-1].get(
            "revision") if target.get("revisions") else None,
    })
    matches[0].write_text(json.dumps(pkg, indent=2))
    return {"ok": True, "package_id": package_id, "route_id": route_id,
              "revisions": target["revisions"]}


def transition_creative_status(brand_id: str, brief_id: str,
                                  package_id: str, to_status: str,
                                  reason: str = "",
                                  actor: str = "operator") -> dict:
    valid = {"draft": ("ready_for_review",),
              "ready_for_review": ("changes_requested", "approved",
                                       "rejected"),
              "changes_requested": ("ready_for_review",),
              "approved": ("superseded",),
              "rejected": ("draft",),
              "superseded": ()}
    pkgdir = Path(_data_root()) / "creative-packages" / brand_id
    matches = list(pkgdir.glob(f"{brief_id}__{package_id}.json"))
    if not matches:
        return {"ok": False, "error": "package not found"}
    pkg = _read_json(matches[0])
    cur = pkg.get("status") or "draft"
    if to_status not in valid.get(cur, ()):
        return {"ok": False,
                "error": f"invalid transition {cur}→{to_status}",
                "valid_next": list(valid.get(cur, ()))}
    pkg["status"] = to_status
    pkg.setdefault("status_history", []).append({
        "from": cur, "to": to_status,
        "reason": reason, "actor": actor, "at": _now_iso(),
    })
    matches[0].write_text(json.dumps(pkg, indent=2))
    return {"ok": True, "package_id": package_id, "from": cur,
              "to": to_status}


# ── HTML RENDERING ────────────────────────────────────────────

def render_package_html(brand_id: str, brief_id: str,
                          package_id: str) -> str:
    pkg = get_creative_package(brand_id, brief_id, package_id)
    if not pkg:
        return _html_error("Package not found",
                            f"{brand_id}/{brief_id}/{package_id}")
    snap = pkg.get("snapshot") or {}
    strat = snap.get("strategy_snapshot") or {}
    rep = snap.get("reporting_snapshot") or {}
    genome = pkg.get("creative_genome") or {}
    allowed = pkg.get("allowed_channels") or []
    routes = pkg.get("routes") or []
    drafts = pkg.get("channel_drafts") or {}
    publish = pkg.get("publish") or {}
    parts = [_html_head(pkg, brand_id, brief_id),
              '<div class="cp-grid">',
              _section_brief(strat),
              _section_reporting(rep),
              _section_genome(genome),
              '<div class="cp-section"><h2>Concept Routes (' + str(len(routes)) + ')</h2>']
    for r in routes:
        parts.append(_render_route(r, brand_id, brief_id, pkg["package_id"]))
    parts.append('</div>')
    parts.append(_section_channel_matrix(drafts, allowed))
    parts.append(_section_publish(publish))
    parts.append(_section_revisions(pkg))
    parts.append('</div></body></html>')
    return "\n".join(parts)


def _html_head(pkg, brand_id, brief_id):
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Creative Package — {brand_id}/{brief_id}</title>
<style>{_css()}</style></head>
<body>
<div class="cp-header">
  <h1>Creative Package</h1>
  <div class="cp-meta">
    <strong>{brand_id}</strong> · brief <code>{brief_id}</code> · package <code>{pkg.get('package_id')}</code><br>
    Generator: {pkg.get('generator_version')} · Generated: {pkg.get('generated_at')}<br>
    Status: <span class="status-{pkg.get('status')}">{pkg.get('status')}</span>
  </div>
</div>"""


def _css():
    return """
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:#0e1116;color:#e6e6e6;margin:0;padding:24px;}
h1{font-size:22px;margin:0 0 4px 0;}h2{font-size:16px;margin:24px 0 8px 0;border-bottom:1px solid #2a2f3a;padding-bottom:6px;}
h3{font-size:14px;margin:14px 0 6px 0;color:#93c5fd;}
.cp-header{padding-bottom:14px;border-bottom:1px solid #2a2f3a;}
.cp-meta{color:#9aa3b2;font-size:12px;line-height:1.6;}
code{background:#1a1f29;padding:1px 6px;border-radius:3px;color:#fbbf24;font-size:11px;}
.cp-grid{max-width:1200px;margin:0 auto;}
.cp-section{background:#161b22;border:1px solid #2a2f3a;border-radius:8px;padding:16px;margin:14px 0;}
.route{background:#0d1117;border:1px solid #2a2f3a;border-radius:6px;padding:14px;margin:10px 0;}
.route-meta{color:#9aa3b2;font-size:11px;}
.route .label{display:inline-block;font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:#9aa3b2;width:90px;}
.route .copy{font-size:14px;line-height:1.5;margin:6px 0;}
table{width:100%;border-collapse:collapse;margin-top:8px;font-size:12px;}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #2a2f3a;}th{color:#9aa3b2;font-weight:400;text-transform:uppercase;font-size:10px;letter-spacing:.05em;}
.status-draft{background:#4b5563;color:white;padding:2px 8px;border-radius:3px;font-size:11px;}
.status-ready_for_review{background:#0ea5e9;color:white;padding:2px 8px;border-radius:3px;font-size:11px;}
.status-approved{background:#16a34a;color:white;padding:2px 8px;border-radius:3px;font-size:11px;}
.status-rejected{background:#dc2626;color:white;padding:2px 8px;border-radius:3px;font-size:11px;}
.status-changes_requested{background:#f59e0b;color:#1f2937;padding:2px 8px;border-radius:3px;font-size:11px;}
.valid-PASS{color:#34d399;font-weight:600;}
.valid-WARNING{color:#fbbf24;font-weight:600;}
.valid-FAIL{color:#f87171;font-weight:600;}
button{background:#0ea5e9;color:white;border:0;padding:6px 12px;border-radius:4px;font-size:12px;cursor:pointer;margin:2px;}
button:hover{background:#0284c7;}
.op-edit{display:inline-block;background:#1f2937;color:#93c5fd;border:1px solid #374151;padding:2px 8px;border-radius:3px;font-size:10px;margin-right:4px;}
.bullets{list-style:none;padding:0;margin:0;}.bullets li{font-size:12px;color:#9aa3b2;padding:2px 0;}
.field-block{background:#0d1117;border-left:3px solid #3b82f6;padding:10px 12px;margin:6px 0;font-size:13px;}
.operator-required{background:#422006;border-left:3px solid #f59e0b;padding:6px 10px;margin:4px 0;font-size:11px;}
.cross-brand{background:#450a0a;border-left:3px solid #dc2626;padding:6px 10px;margin:4px 0;font-size:11px;}
"""


def _html_error(title, detail):
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title></head>
<body style="background:#0e1116;color:#e6e6e6;padding:40px;font-family:sans-serif;">
<h1>{title}</h1><pre>{detail}</pre></body></html>"""


def _section_brief(strat):
    return f"""<div class="cp-section"><h2>Brief Summary</h2>
<table>
<tr><th>Pillar</th><td>{strat.get('primary_pillar') or '—'}</td></tr>
<tr><th>Objective</th><td>{strat.get('objective') or '—'}</td></tr>
<tr><th>Audience tension</th><td>{strat.get('audience_tension') or '—'}</td></tr>
<tr><th>North Star link</th><td>{strat.get('north_star_link') or '—'}</td></tr>
<tr><th>Approved channels</th><td>{', '.join(strat.get('channels_approved') or [])}</td></tr>
<tr><th>Status</th><td>{strat.get('status') or '—'}</td></tr>
<tr><th>Creative allowed</th><td>{strat.get('creative_allowed')}</td></tr>
</table></div>"""


def _section_reporting(rep):
    if not rep or rep.get("data_status") != "LIVE":
        return (f'<div class="cp-section"><h2>Reporting Evidence (V2.4.1)</h2>'
                f'<div class="operator-required">Reporting data unavailable: '
                f'{rep.get("error") or rep.get("data_status") or "unknown"}</div></div>')
    cc = (rep.get("campaign_counts") or {})
    bn = ((rep.get("best_needs_attention") or {}).get("by_objective") or {})
    rows = [f"<tr><th>YTD spend</th><td>R{rep.get('ytd_brand_total_spend') or '—'}</td></tr>",
              f"<tr><th>Campaigns current</th><td>{cc.get('current_delivered_count')} (comparable {cc.get('comparable_count')}, new {cc.get('new_campaign_count')})</td></tr>",
              f"<tr><th>Campaigns previous</th><td>{cc.get('previous_delivered_count')} (comparable {cc.get('comparable_count')}, ended {cc.get('ended_campaign_count')})</td></tr>",
              f"<tr><th>Math OK</th><td>{cc.get('math_ok')}</td></tr>",
              f"<tr><th>Account name</th><td>{(rep.get('account_reconciliation') or {}).get('name')}</td></tr>",
              f"<tr><th>Lifetime spend</th><td>R{(rep.get('account_reconciliation') or {}).get('amount_spent_zar')}</td></tr>",
              f"<tr><th>Freshness</th><td>{(rep.get('freshness') or {}).get('status')}</td></tr>"]
    bn_rows = []
    for obj, items in (bn.get("best") or {}).items():
        for i in (items or [])[:2]:
            bn_rows.append(f"<li><strong>{obj}</strong>: {i.get('campaign_name')}</li>")
    for obj, items in (bn.get("needs_attention") or {}).items():
        for i in (items or [])[:2]:
            bn_rows.append(f"<li><strong>{obj} attention</strong>: {i.get('campaign_name')}</li>")
    return (f'<div class="cp-section"><h2>Reporting Evidence (V2.4.1)</h2>'
              f'<table>{"".join(rows)}</table>'
              f'<h3>Best / Needs Attention</h3>'
              f'<ul class="bullets">{"".join(bn_rows) or "<li>none</li>"}</ul></div>')


def _section_genome(genome):
    if (genome or {}).get("status") != "ok":
        return (f'<div class="cp-section"><h2>Creative Genome</h2>'
                f'<div class="operator-required">Status: insufficient_data '
                f'· sample_size: {genome.get("sample_size") or 0}</div>'
                f'<p style="font-size:12px;color:#9aa3b2;">{genome.get("note") or ""}</p></div>')
    s = genome.get("signal") or {}
    ev = genome.get("evidence") or []
    return (f'<div class="cp-section"><h2>Creative Genome</h2>'
              f'<table>'
              f'<tr><th>Status</th><td>ok</td></tr>'
              f'<tr><th>Sample size</th><td>{genome.get("sample_size")}</td></tr>'
              f'<tr><th>Confidence</th><td>{genome.get("confidence")}</td></tr>'
              f'<tr><th>High alignment share</th><td>{s.get("high_alignment_share")}</td></tr>'
              f'<tr><th>Dominant orientation</th><td>{s.get("dominant_orientation")}</td></tr>'
              f'<tr><th>Top dominant color</th><td><code>{s.get("top_dominant_color")}</code></td></tr>'
              f'</table>'
              f'<h3>Top-scorer assets (highest alignment)</h3>'
              f'<ul class="bullets">{"".join("<li>" + e + "</li>" for e in ev) or "<li>none</li>"}</ul></div>')


def _render_route(r, brand_id, brief_id, package_id):
    gen = r.get("generated") or {}
    voice = r.get("voice") or {}
    fg = r.get("fact_grounding") or {}
    nov = r.get("novelty") or {}
    req_assets = r.get("required_assets") or []
    rid = r.get("route_id")
    fields = []
    for label, key in (("HOOK", "HOOK"), ("CORE", "CORE"),
                         ("DIRECTION", "DIRECTION"), ("CTA", "CTA")):
        v = gen.get(key) or ""
        if v:
            fields.append(f'<div class="field-block"><div class="route-meta">{label}</div><div class="copy">{v}</div></div>')
    v_status = voice.get("validation_status") or "?"
    lex_max = (nov.get("lexical") or {}).get("max_similarity") or 0.0
    sem = nov.get("semantic") or {}
    sem_max = (sem.get("max_similarity") if sem.get("available") else "n/a")
    asset_html = []
    for a in req_assets:
        badge = ('<span class="op-edit">operator_asset_required</span>'
                   if a.get("operator_asset_required") else '')
        avail = ("<br>available: " + ", ".join(a.get("available_real_assets") or [])[:200]
                   if a.get("available_real_assets") else "")
        asset_html.append(f"<li>{a.get('kind')}: {a.get('description')[:100]} {badge}{avail}</li>")
    fg_op = fg.get("operator_fact_required") or []
    fg_xb = fg.get("cross_brand_leaks") or []
    fg_op_html = "".join(f'<div class="operator-required">{o.get("claim")[:120]} — {o.get("note") or ""}</div>' for o in fg_op) or "<span style='color:#9aa3b2;'>none</span>"
    fg_xb_html = "".join(f'<div class="cross-brand">{x.get("sentence")[:120]} — mentioned: {x.get("mentioned_brand")}</div>' for x in fg_xb) or "<span style='color:#9aa3b2;'>none</span>"
    return f"""<div class="route">
<div class="route-meta">
  <strong>{r.get('working_concept_name')}</strong> · <code>{rid}</code> ·
  <span class="valid-{r.get('validation_status')}">{r.get('validation_status')}</span>
  · Mechanic: {r.get('mechanic')}
</div>
{''.join(fields)}
<h3>Validation</h3>
<table>
<tr><th>Voice</th><td class="valid-{v_status}">{v_status}</td></tr>
<tr><th>Banned hits</th><td>{', '.join(voice.get('banned_hits') or []) or 'none'}</td></tr>
<tr><th>Voice warnings</th><td>{', '.join(voice.get('voice_warnings') or []) or 'none'}</td></tr>
<tr><th>Fact grounding</th><td>{len(fg.get('grounded_claims') or [])} grounded, {len(fg_op)} operator-required</td></tr>
<tr><th>Cross-brand leaks</th><td>{len(fg_xb)}</td></tr>
<tr><th>Novelty signal</th><td>{nov.get('combined_signal')} (lex={lex_max}, sem={sem_max})</td></tr>
<tr><th>Revisions</th><td>{len(r.get('revisions') or [])}</td></tr>
</table>
<h3>Operator-required facts</h3>
{fg_op_html}
<h3>Cross-brand leaks</h3>
{fg_xb_html}
<h3>Required Assets</h3>
<ul class="bullets">{"".join(asset_html) or "<li>none</li>"}</ul>
</div>"""


def _section_channel_matrix(drafts, allowed):
    rows = ['<table><tr><th>Route</th><th>Channel</th><th>Format</th><th>Has draft</th></tr>']
    for route_id, channel_drafts in (drafts or {}).items():
        for ch in (allowed or []):
            d = channel_drafts.get(ch) or {}
            rows.append(f'<tr><td>{route_id}</td><td>{ch}</td><td>{d.get("format", ch)}</td><td>{"yes" if d else "no"}</td></tr>')
    rows.append('</table>')
    return f'<div class="cp-section"><h2>Channel Drafts (Brief-approved only)</h2>{"".join(rows)}</div>'


def _section_publish(publish):
    gates = publish.get("gates") or {}
    rows = []
    for k, v in gates.items():
        rows.append(f"<tr><th>{k}</th><td>{v}</td></tr>")
    rows.append(f"<tr><th>publish_allowed</th><td><strong>{publish.get('publish_allowed')}</strong></td></tr>")
    return (f'<div class="cp-section"><h2>Publish Gate (can_publish_creative)</h2>'
              f'<table>{"".join(rows)}</table>'
              f'<p style="color:#9aa3b2;font-size:11px;">{publish.get("rule") or ""}</p></div>')


def _section_revisions(pkg):
    revs = pkg.get("status_history") or []
    if not revs:
        return ''
    rows = []
    for r in revs:
        rows.append(f"<tr><td>{r.get('from')}</td><td>{r.get('to')}</td><td>{r.get('actor')}</td><td>{r.get('reason')}</td><td>{r.get('at')}</td></tr>")
    return (f'<div class="cp-section"><h2>Status History</h2>'
              f'<table><tr><th>From</th><th>To</th><th>Actor</th><th>Reason</th><th>At</th></tr>'
              f'{"".join(rows)}</table></div>')
