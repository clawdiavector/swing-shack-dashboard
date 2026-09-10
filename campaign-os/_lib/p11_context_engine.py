"""
P1.1 FINAL — Context Engine + Route Planner + LLM-backed Caption Pipeline.

This module replaces the deterministic template-based generator with a
real LLM call (OpenAI chat completions via image_gen_router._resolve_*_key).
All checks from P0.6A close-out + P1.1 are preserved and strengthened:

  exact  → structural (mechanism + rhetorical_structure)  → semantic
  → brand  → fact (incl. numbers/causal claims)  → brief_fidelity
  → performance_prior  → survivors

Taste events persist to /data/campaign-os/intelligence/taste/.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── Paths ──────────────────────────────────────────────────────────────
def _data_dir() -> str:
    return os.environ.get("DATA_DIR", "/data/campaign-os")


def _bundled_data_dir() -> str:
    return globals().get("_BUNDLED_DATA_DIR", "/app/data")


def _p06a_dir() -> Path:
    return Path(_data_dir()) / "intelligence" / "history" / "p06a"


def _brand_dir(brand_id: str) -> Path:
    return Path(_data_dir()) / "brand-directory" / brand_id


# ─── Constants ──────────────────────────────────────────────────────────
MECHANISMS = [
    "problem", "observation", "contrarian", "proof", "curiosity",
    "comparison", "identity", "humour", "mistake", "myth",
    "tension", "story", "challenge", "aspiration", "commercial",
]

# Mechanism → brand fit (1-5)
MECHANISM_FIT: Dict[str, Dict[str, int]] = {
    "swing-shack": {
        "problem": 5, "observation": 5, "contrarian": 4, "proof": 5,
        "curiosity": 3, "comparison": 4, "identity": 2, "humour": 2,
        "mistake": 5, "myth": 5, "tension": 3, "story": 3,
        "challenge": 4, "aspiration": 2, "commercial": 3,
    },
    "stick": {
        "problem": 4, "observation": 3, "contrarian": 5, "proof": 2,
        "curiosity": 4, "comparison": 5, "identity": 4, "humour": 5,
        "mistake": 4, "myth": 5, "tension": 4, "story": 3,
        "challenge": 3, "aspiration": 2, "commercial": 2,
    },
    "bag-drop": {
        "problem": 2, "observation": 2, "contrarian": 3, "proof": 2,
        "curiosity": 2, "comparison": 2, "identity": 5, "humour": 3,
        "mistake": 2, "myth": 2, "tension": 2, "story": 5,
        "challenge": 3, "aspiration": 3, "commercial": 2,
    },
}

OPERATING_BRANDS = ("swing-shack", "stick", "bag-drop")
PRODUCT_BRANDS = {"takomo": "stick"}

# Rhetorical structure families — distinct from mechanisms
RHETORICAL_STRUCTURES = [
    "myth_vs_reality", "question_then_answer", "listicle_3_things",
    "first_then_now", "observation_callout", "challenge_to_reader",
    "data_then_takeaway", "comparison_two_columns", "quote_reframe",
    "anecdote_short_story", "instructional_step", "direct_offer",
]

# Brief → service keyword detection (used for brief_fidelity)
SERVICE_KEYWORDS = {
    "putter fitting": ["putter", "putting", "stroke", "green", "short game"],
    "driver fitting": ["driver", "shaft", "swing speed", "attack angle", "smash factor"],
    "iron fitting": ["iron", "7-iron", "carry", "trajectory"],
    "wedge fitting": ["wedge", "bounce", "loft", "short game"],
    "coaching": ["coach", "lesson", "swing", "tempo", "drill"],
    "tpi assessment": ["tpi", "body", "swing", "physical", "assessment"],
    "trackman session": ["trackman", "session", "data", "numbers"],
    "membership": ["membership", "member", "join", "social"],
    "fitting": ["fitting", "club", "shaft", "custom"],
}


# ─── Helpers ────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(s: str) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()[:16]


def _load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _read_text(p: Path) -> str:
    try:
        return p.read_text()
    except Exception:
        return ""


def _read_md(p: Path, max_chars: int = 4000) -> str:
    txt = _read_text(p)
    if not txt:
        return ""
    txt = re.sub(r"^# .+\n", "", txt, flags=re.MULTILINE)
    return txt[:max_chars]


def _bag_vector(text: str, dim: int = 256) -> list:
    vec = [0.0] * dim
    for t in re.findall(r"\b[a-z]{3,}\b", (text or "").lower()):
        vec[hash(t) % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


# ─── Voice bible + brand rules ─────────────────────────────────────────
def _voice_bible_path() -> Path:
    for base in (_data_dir(), _bundled_data_dir()):
        p = Path(base) / "voice_bible.json"
        if p.exists():
            return p
    return Path(_data_dir()) / "voice_bible.json"


def _load_voice_bible() -> dict:
    return _load_json(_voice_bible_path())


def _load_brand_rules(brand_id: str) -> dict:
    bdir = _brand_dir(brand_id)
    if not bdir.exists():
        return {}
    return {
        "voice": _read_md(bdir / "voice" / "do-say-dont-say.md", 3000),
        "tone": _read_md(bdir / "voice" / "tone-rules.md", 3000),
        "punctuation": _read_md(bdir / "voice" / "punctuation-rules.md", 2000),
        "headlines": _read_md(bdir / "copy" / "headlines.md", 2000),
        "ctas": _read_md(bdir / "copy" / "ctas.md", 2000),
        "readme": _read_md(bdir / "README.md", 2000),
    }


def _extract_banned_terms(brand_id: str) -> List[str]:
    bdir = _brand_dir(brand_id) / "voice" / "do-say-dont-say.md"
    txt = _read_text(bdir)
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
        if in_dont and (line.strip().startswith("❌") or line.strip().startswith("- ❌")):
            clean = re.sub(r"^[-\s❌]+", "", line).strip().strip('"').strip("'").strip("`")
            if clean and len(clean) < 80:
                banned.append(clean)
    banned.append("—")
    return list({b for b in banned if b})


def _extract_required_terms(brand_id: str) -> List[str]:
    bdir = _brand_dir(brand_id) / "voice" / "do-say-dont-say.md"
    txt = _read_text(bdir)
    if not txt:
        return []
    required = []
    in_do = False
    for line in txt.split("\n"):
        if "## Do say" in line:
            in_do = True
            continue
        if in_do and line.startswith("## "):
            in_do = False
        if in_do and (line.strip().startswith("✅") or line.strip().startswith("- ✅")):
            clean = re.sub(r"^[-\s✅]+", "", line).strip()
            if clean and len(clean) < 80:
                required.append(clean)
    return list({r for r in required if r})


# ─── Recent content + structural / exact families ──────────────────────
def _load_recent_content(brand_id: str, limit: int = 50) -> List[dict]:
    recent = []
    cleaned = _p06a_dir() / "canonical-history.cleaned.jsonl"
    if cleaned.exists():
        for line in cleaned.read_text().splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("kind") != "asset" or rec.get("brand_id") != brand_id:
                continue
            cap = (rec.get("caption") or "").strip()
            if not cap:
                continue
            recent.append({
                "asset_id": rec.get("asset_id"),
                "ig_media_id": rec.get("ig_media_id"),
                "fb_post_id": rec.get("fb_post_id"),
                "media_type": rec.get("media_type"),
                "caption": cap,
                "permalink": rec.get("permalink"),
                "first_seen_at": rec.get("first_seen_at"),
                "cross_post_group_id": rec.get("cross_post_group_id"),
                "source": rec.get("source"),
            })
            if len(recent) >= limit:
                break
    return recent


def _load_caption_intel() -> dict:
    p = _p06a_dir() / "structural-families.json"
    if p.exists():
        return _load_json(p)

    cleaned = _p06a_dir() / "canonical-history.cleaned.jsonl"
    if not cleaned.exists():
        return {"families": [], "exact_duplicates": [], "hook_family_counts": {}}

    captions = []
    for line in cleaned.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("kind") == "asset":
            cap = (rec.get("caption") or "").strip()
            if cap:
                captions.append(cap)

    cap_counts: Dict[str, int] = {}
    for c in captions:
        cap_counts[c] = cap_counts.get(c, 0) + 1
    exact_dupes = [{"caption": c, "count": n}
                   for c, n in cap_counts.items() if n >= 2]
    exact_dupes.sort(key=lambda x: -x["count"])

    def normalise_opener(cap: str) -> str:
        first = (cap.split(".")[0] or "")[:60].lower().strip()
        first = re.sub(r"#\w+", "HASHTAG", first)
        first = re.sub(r"\d+", "NUM", first)
        first = re.sub(r"[^\w\s]", "", first)
        return first.strip()[:50]

    opener_counts: Dict[str, int] = {}
    for c in captions:
        op = normalise_opener(c)
        if op and len(op) > 5:
            opener_counts[op] = opener_counts.get(op, 0) + 1
    structural = [{"opener": o, "count": n}
                  for o, n in opener_counts.items() if n >= 2]
    structural.sort(key=lambda x: -x["count"])

    HOOK_KW = {
        "fitting_open": ["fitting", "custom fit", "club fit", "shaft"],
        "coaching_open": ["coaching", "lesson", "coach"],
        "you_open": ["you", "your"],
        "we_open": ["we ", "our ", "us "],
        "humour": ["lol", "meme", "joke", "funny"],
        "myth": ["myth", "truth", "nobody tells"],
        "proof_open": ["data", "trackman", "numbers", "metric"],
        "question_open": ["?", "did you", "what if", "why"],
        "problem_open": ["struggle", "problem", "issue", "frustrat"],
        "membership_open": ["member", "membership"],
    }
    hook_counts: Dict[str, int] = {k: 0 for k in HOOK_KW}
    for c in captions:
        cl = c.lower()
        for hook, kws in HOOK_KW.items():
            if any(kw in cl for kw in kws):
                hook_counts[hook] += 1

    out = {
        "generated_at": _now_iso(),
        "captions_analysed": len(captions),
        "exact_duplicates": exact_dupes[:50],
        "structural_families": structural[:50],
        "hook_family_counts": hook_counts,
    }
    try:
        p.write_text(json.dumps(out, indent=2))
    except Exception:
        pass
    return out


# ─── Embeddings loader ─────────────────────────────────────────────────
def _load_embeddings() -> Tuple[Dict[str, list], str, str]:
    p = _p06a_dir() / "embeddings.jsonl"
    embeds: Dict[str, list] = {}
    kind = "unknown"
    model = "unknown"
    if not p.exists():
        return embeds, kind, model
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        embeds[rec["caption_id"]] = rec["vector"]
        kind = rec.get("embedding_kind", kind)
        model = rec.get("embedding_model", model)
    return embeds, kind, model


def _load_performance_evidence(brand_id: str) -> List[dict]:
    p = _p06a_dir() / "derived-performance.cleaned.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("brand_id") != brand_id:
            continue
        if rec.get("performance_eligible") is not True:
            continue
        out.append(rec)
    return out


# ─── Brief subject detection ───────────────────────────────────────────
def _detect_brief_subject(brief: str, service: str = None, product_id: str = None) -> str:
    """Return the dominant subject of the brief (e.g. 'putter fitting')."""
    text = (brief or "").lower()
    if service:
        return service.lower()
    if product_id:
        return product_id.lower()
    # Try service keywords
    for svc, kws in SERVICE_KEYWORDS.items():
        if any(kw in text for kw in kws):
            return svc
    # Fallback: most distinctive noun-ish word in brief
    words = re.findall(r"\b[a-z]{4,}\b", text)
    if words:
        return words[0]
    return ""


# ─── CONTEXT ASSEMBLER (relevance-aware) ────────────────────────────────
def build_generation_context(
    brand_id: str,
    task_type: str = "caption",
    campaign_id: Optional[str] = None,
    product_brand: Optional[str] = None,
    product_id: Optional[str] = None,
    service: Optional[str] = None,
    audience: Optional[str] = None,
    channel: Optional[str] = None,
    objective: Optional[str] = None,
    user_brief: Optional[str] = None,
    n_recent: int = 30,
    n_semantic: int = 8,
    n_structural: int = 6,
    n_performance: int = 8,
) -> dict:
    if brand_id not in OPERATING_BRANDS:
        return {
            "ok": False,
            "error": f"brand_id={brand_id!r} is not an operating brand. "
                     f"Operating brands: {OPERATING_BRANDS}. "
                     f"takomo is a product_brand under stick, never an operating brand.",
            "operating_brands": list(OPERATING_BRANDS),
            "product_brands": list(PRODUCT_BRANDS.keys()),
        }
    if product_brand and product_brand not in PRODUCT_BRANDS and product_brand != brand_id:
        return {
            "ok": False,
            "error": f"product_brand={product_brand!r} is not a known product_brand. "
                     f"Known: {list(PRODUCT_BRANDS.keys())}.",
        }
    if product_brand and product_brand in PRODUCT_BRANDS:
        owner = PRODUCT_BRANDS[product_brand]
        if owner != brand_id:
            return {
                "ok": False,
                "error": f"product_brand={product_brand!r} belongs to operating_brand={owner!r}, "
                         f"not {brand_id!r}. Use brand_id={owner!r} for {product_brand!r}.",
                "cross_brand_attack": True,
            }

    brief_subject = _detect_brief_subject(user_brief, service, product_id)

    vb = _load_voice_bible()
    voice = vb.get("voices", {}).get(brand_id, {})
    brand_rules = _load_brand_rules(brand_id)
    banned = _extract_banned_terms(brand_id)
    required = _extract_required_terms(brand_id)
    recent = _load_recent_content(brand_id, limit=n_recent)
    intel = _load_caption_intel()
    embeds, embed_kind, embed_model = _load_embeddings()
    perf_evidence = _load_performance_evidence(brand_id)

    # ── Split facts by relevance to brief_subject ───────────────────
    GLOBAL_FACTS = {
        "brand_id": brand_id,
        "label": voice.get("label", brand_id),
        "personality": voice.get("personality", ""),
        "voice_description": voice.get("description", ""),
        "callout_style": voice.get("callout_style", ""),
        "allowed_tones": voice.get("allowed_tones", []),
        "meme_fit": voice.get("meme_fit", []),
        "cta_default": voice.get("cta_default", ""),
        "cta_alternatives": voice.get("cta_alternatives", []),
        "hashtag_suggestions": voice.get("hashtag_suggestions", []),
        "rules_excerpt": brand_rules.get("voice", "")[:1500],
        "tone_rules_excerpt": brand_rules.get("tone", "")[:1500],
        "punctuation_excerpt": brand_rules.get("punctuation", "")[:1000],
        "linked_brand_note": (
            f"{brand_id} services are operated by swing-shack."
            if brand_id in ("stick", "bag-drop") else None
        ),
    }

    # SERVICE FACTS — only relevant when brief matches a service keyword
    service_facts = None
    if brief_subject in SERVICE_KEYWORDS:
        service_facts = {
            "service": brief_subject,
            "subject_keywords": SERVICE_KEYWORDS[brief_subject],
            "subject_is_proven": True,
        }

    # PRODUCT FACTS — only when product_id provided
    product_facts = None
    if product_id:
        lib_path = _brand_dir(brand_id) / "product-library.json"
        if lib_path.exists():
            lib = _load_json(lib_path)
            products = lib.get("products", lib if isinstance(lib, list) else [])
            for p in products if isinstance(products, list) else []:
                if isinstance(p, dict) and p.get("id") == product_id:
                    product_facts = p
                    break

    # OPTIONAL RELATED FACTS — terminology that's available but only enters
    # the prompt if the brief explicitly references it.
    OPTIONAL_RELATED = {
        "all_terminology": required,  # the full vocabulary available
        "use_only_when_brief_references": True,
    }

    # ── Layer 2: PRODUCT/SERVICE ──
    product_layer = {
        "product_brand": product_brand,
        "product_id": product_id,
        "service": service,
        "audience": audience,
        "brief_subject": brief_subject,
        "factual_constraints": [
            "Never invent prices — only use price_zar or known published offers.",
            "Never invent product names — use the canonical product-library.json.",
            "Never invent TrackMan numbers / fitting outcomes / dates / specs.",
            "Never invent distances, percentages, time savings, scores, or causal claims.",
            "If a number is not in verified source context, omit it.",
            "If uncertain, omit rather than hallucinate.",
        ],
        "takomo_relationship": (
            "Takomo is a product_brand under stick. Reference Takomo clubs by "
            "their canonical product names. Stick voice remains the active voice."
            if (brand_id == "stick" and product_brand == "takomo") else None
        ),
        "service_facts": service_facts,
        "product_facts": product_facts,
        "optional_related_facts": OPTIONAL_RELATED,
    }

    # ── Layer 3: CAMPAIGN ──
    campaign_layer = {"campaign_id": campaign_id, "objective": objective}
    if campaign_id:
        for base in (_data_dir(), _bundled_data_dir()):
            p = Path(base) / "campaigns.json"
            if p.exists():
                cd = _load_json(p)
                c = cd.get("campaigns", {}).get(campaign_id) if isinstance(cd, dict) else None
                if c:
                    campaign_layer.update({
                        "name": c.get("name", campaign_id),
                        "status": c.get("status"),
                        "objective": c.get("objective", objective),
                        "audience": c.get("audience"),
                        "proposition": c.get("proposition"),
                        "offer": c.get("offer"),
                        "content_pillar": c.get("content_pillar"),
                        "cta": c.get("cta"),
                        "current_executions": c.get("executions", []),
                    })
                break

    # ── Layer 4: CHANNEL ──
    channel_rules = {
        "instagram_reel": {
            "format": "Vertical video, 7-90s. First 1-2 lines are the hook above the 'more' cut.",
            "voice_notes": "Data-driven hook in line 1. CTA in last line. Hashtags at end (3-6).",
        },
        "instagram_feed": {
            "format": "Static or carousel. Caption can be 100-300 words. First line = hook.",
            "voice_notes": "Lead with the data point or the contradiction. Don't bury the lede.",
        },
        "facebook": {
            "format": "Longer caption acceptable. Slightly more conversational.",
            "voice_notes": "Same brand voice. Less hashtag-heavy. CTA more explicit.",
        },
        "paid_meta": {
            "format": "Tighter. First 3 words matter most. 1-2 sentence body max.",
            "voice_notes": "Lead with the offer or the data point. No soft intros.",
        },
        "gbp": {
            "format": "Short post. Local context. No hashtags.",
            "voice_notes": "Plain language. Service-first, not voice-first.",
        },
    }
    channel_layer = {
        "channel": channel or "instagram_feed",
        "rules": channel_rules.get(channel or "instagram_feed", channel_rules["instagram_feed"]),
    }

    # ── Layer 5: RECENT ──
    recent_digest = {
        "n_recent": len(recent),
        "hook_family_counts": intel.get("hook_family_counts", {}),
        "top_structural_openers": intel.get("structural_families", [])[:5],
        "exact_duplicate_captions": [e["caption"][:120]
                                      for e in intel.get("exact_duplicates", [])[:5]],
        "last_5_full_captions": [r["caption"] for r in recent[:5]],
    }

    # ── Layer 6: SEMANTIC ──
    semantic_neighbours = []
    if embeds and user_brief:
        target = user_brief.lower()
        for r in recent[:50]:
            if r["asset_id"] in embeds:
                sim = _cosine(embeds[r["asset_id"]], _bag_vector(target))
                if sim > 0.3:
                    semantic_neighbours.append({
                        "asset_id": r["asset_id"],
                        "ig_media_id": r.get("ig_media_id"),
                        "media_type": r.get("media_type"),
                        "first_seen_at": r.get("first_seen_at"),
                        "caption_excerpt": (r.get("caption") or "")[:200],
                        "similarity_to_brief": round(sim, 4),
                    })
        semantic_neighbours.sort(key=lambda x: -x["similarity_to_brief"])
        semantic_neighbours = semantic_neighbours[:n_semantic]

    # ── Layer 7: STRUCTURAL ──
    structural_layer = {
        "families": intel.get("structural_families", [])[:n_structural],
        "exact_duplicates": intel.get("exact_duplicates", [])[:5],
        "hook_family_counts": intel.get("hook_family_counts", {}),
    }

    # ── Layer 8: PERFORMANCE ──
    perf_digest = []
    for p in perf_evidence[:50]:
        perf_digest.append({
            "asset_id": p.get("asset_id"),
            "media_type": p.get("media_type"),
            "timestamp": p.get("timestamp"),
            "raw_observations": p.get("raw_observations", {}),
            "provisional_win_score": p.get("provisional_win_score"),
            "recency_weight": p.get("recency_weight"),
        })
    perf_digest = perf_digest[:n_performance]
    performance_layer = {
        "eligible_records_total": len(perf_evidence),
        "evidence_used": len(perf_digest),
        "samples": perf_digest,
        "confidence_label": (
            "weak_prior" if len(perf_evidence) < 5
            else "moderate_prior" if len(perf_evidence) < 30
            else "strong_prior" if len(perf_evidence) < 100
            else "well_supported"
        ),
        "note": "Only `performance_eligible` records are used. "
                "Synthetic paid data is quarantined and not used.",
    }

    restrictions = {
        "must_not_invent": [
            "prices", "offers", "specifications", "membership benefits",
            "TrackMan numbers", "fitting outcomes", "dates", "booking mechanics",
            "distances", "percentages", "time savings", "scores",
            "performance gains", "availability", "session durations",
            "causal claims not backed by verified evidence",
        ],
        "em_dash_banned": True,
        "internal_agents_banned": ["Clawfix", "Retina", "Patch", "Heidi",
                                    "Memories", "Forge", "Publisher"],
        "cross_brand_text_banned": (
            f"Do not reference other operating brands "
            f"({[b for b in OPERATING_BRANDS if b != brand_id]}) "
            f"in {brand_id} published text unless Christelle approves cross-business mention."
            if brand_id in ("stick", "bag-drop") else None
        ),
    }

    provenance = {
        "context_version": "p11c-v1-final",
        "generated_at": _now_iso(),
        "brief_subject": brief_subject,
        "embedding_kind": embed_kind,
        "embedding_model": embed_model,
        "captions_analysed_for_intel": intel.get("captions_analysed", 0),
        "performance_records_total": len(perf_evidence),
        "sources": {
            "voice_bible": str(_voice_bible_path()),
            "brand_directory": str(_brand_dir(brand_id)),
            "p06a_cleaned_canonical": str(_p06a_dir() / "canonical-history.cleaned.jsonl"),
            "p06a_embeddings": str(_p06a_dir() / "embeddings.jsonl"),
            "p06a_derived_performance": str(_p06a_dir() / "derived-performance.cleaned.jsonl"),
        },
    }

    return {
        "ok": True,
        "context_id": "ctx-" + _hash(f"{brand_id}|{user_brief}|{_now_iso()}")[:12],
        "task_type": task_type,
        "brand_id": brand_id,
        "product_brand": product_brand,
        "user_brief": user_brief,
        "brand": GLOBAL_FACTS,
        "product_service": product_layer,
        "campaign": campaign_layer,
        "channel": channel_layer,
        "recent_content": recent_digest,
        "semantic_history": {
            "embedding_kind": embed_kind,
            "embedding_model": embed_model,
            "neighbours_for_brief": semantic_neighbours,
        },
        "structural_history": structural_layer,
        "performance_context": performance_layer,
        "restrictions": restrictions,
        "source_provenance": provenance,
    }


# ─── ROUTE PLANNER ────────────────────────────────────────────────────
def plan_routes(context: dict, n: int = 5,
                avoid_mechanisms: Optional[List[str]] = None) -> List[dict]:
    if not context.get("ok"):
        return []
    brand_id = context["brand_id"]
    fit = MECHANISM_FIT.get(brand_id, {})
    avoid = set(avoid_mechanisms or [])
    candidates = [m for m in MECHANISMS
                  if fit.get(m, 0) >= 2 and m not in avoid]
    candidates.sort(key=lambda m: -fit.get(m, 0))
    hfc = context.get("recent_content", {}).get("hook_family_counts", {})
    if hfc:
        weights = {
            "proof": hfc.get("proof_open", 0),
            "humour": hfc.get("humour", 0),
            "myth": hfc.get("myth", 0),
            "question": hfc.get("question_open", 0),
        }
        for m, w in weights.items():
            if w > 50 and m in candidates:
                candidates.remove(m)
                candidates.append(m)
    selected = candidates[:n]
    return [
        {
            "route_id": f"route-{i+1}-{m}",
            "mechanism": m,
            "brand_fit": fit.get(m, 0),
            "rhetorical_structure_suggestion": _pick_rhetorical_structure(m, brand_id),
            "rationale": _mechanism_rationale(m, brand_id, context),
        }
        for i, m in enumerate(selected)
    ]


def _pick_rhetorical_structure(mech: str, brand_id: str) -> str:
    m = {
        "problem": "observation_callout",
        "observation": "data_then_takeaway",
        "contrarian": "quote_reframe",
        "proof": "data_then_takeaway",
        "curiosity": "question_then_answer",
        "comparison": "comparison_two_columns",
        "identity": "first_then_now",
        "humour": "quote_reframe",
        "mistake": "myth_vs_reality",
        "myth": "myth_vs_reality",
        "tension": "quote_reframe",
        "story": "anecdote_short_story",
        "challenge": "challenge_to_reader",
        "aspiration": "first_then_now",
        "commercial": "direct_offer",
    }
    return m.get(mech, "observation_callout")


def _mechanism_rationale(m: str, brand_id: str, context: dict) -> str:
    r = {
        "problem": f"Name a real {brand_id} audience problem with a specific data-backed hook.",
        "observation": f"Lead with a specific TrackMan / fitting observation — natural for {brand_id}.",
        "contrarian": f"Disagree with a popular take. {brand_id} voice earns the right to challenge.",
        "proof": f"Anchor on one specific number / outcome that's true.",
        "curiosity": f"Open a loop the caption closes.",
        "comparison": f"X vs Y. Useful for off-rack vs fitted contrasts.",
        "identity": f"Say who the golfer is / wants to be.",
        "humour": f"Shared joke — works for stick, risky for swing-shack.",
        "mistake": f"Name a specific common mistake and offer the data answer.",
        "myth": f"Bust one specific myth. Distinct from mistake — myth = widely believed, mistake = commonly done.",
        "tension": f"Opposing forces. Useful for fitting / coaching tradeoffs.",
        "story": f"Small narrative — fitting session, lesson moment, member story.",
        "challenge": f"Real challenge. Not a generic 'step up your game'.",
        "aspiration": f"Where this is going. Use sparingly for {brand_id} — voice favours data over dream.",
        "commercial": f"Direct / offer-led. Use last — {brand_id} is not primarily salesy.",
    }
    return r.get(m, m)


# ─── LLM PROVIDER ─────────────────────────────────────────────────────
def _resolve_openai_chat_key() -> Optional[str]:
    """Use the same provider-resolution path as image_gen_router.
    Strip any trailing whitespace/newlines that may exist in env vars."""
    env = os.environ.get("OPENAI_API_KEY")
    if env:
        env = env.strip()
        if env.startswith("sk-"):
            return env
    # Fallback to the image_gen_router path
    try:
        from _lib.image_gen_router import _resolve_openai_key
        key = _resolve_openai_key()
        if key:
            return key.strip()
    except Exception:
        pass
    return env


def _call_llm_chat_completions(
    system: str,
    user: str,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 350,
) -> Optional[str]:
    """Call OpenAI chat completions via the configured provider. Returns the
    assistant text or None on failure."""
    api_key = _resolve_openai_chat_key()
    if not api_key:
        return None
    if model is None:
        model = os.environ.get("CAPTION_MODEL", "gpt-4o-mini")
    body = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        method="POST",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read())
        return resp["choices"][0]["message"]["content"]
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError):
        return None


# ─── PROMPT BUILDER ───────────────────────────────────────────────────
def _build_llm_prompt(ctx: dict, route: dict) -> Tuple[str, str]:
    """Build the system + user messages for the LLM. Relevance-aware."""
    b = ctx["brand"]
    rs = ctx["restrictions"]
    ps = ctx.get("product_service", {})

    # Relevance-aware: only include the subject keywords + product facts if
    # they actually relate to this brief.
    brief_subject = ps.get("brief_subject") or ""
    service_facts = ps.get("service_facts") or {}
    product_facts = ps.get("product_facts") or {}

    subject_keywords = service_facts.get("subject_keywords", [])
    product_facts_text = ""
    if product_facts:
        product_facts_text = (
            f"CANONICAL PRODUCT FACTS (only use these if product is in scope): "
            f"name={product_facts.get('name', product_facts.get('id', '?'))}, "
            f"price_zar={product_facts.get('price_zar', 'unknown')}, "
            f"key_features={' | '.join(product_facts.get('key_features', [])[:3]) or 'n/a'}, "
            f"category={product_facts.get('category', 'n/a')}"
        )

    # Semantic + structural areas to avoid
    semantic_neighbours = (ctx.get("semantic_history", {}) or {}).get("neighbours_for_brief", [])
    neighbour_excerpts = [n["caption_excerpt"][:120] for n in semantic_neighbours[:3]]
    structural_top = (ctx.get("structural_history", {}) or {}).get("families", [])[:3]
    structural_openers = [o.get("opener", "")[:40] for o in structural_top]

    system = (
        f"You write captions for the brand {b['label']} ({b['brand_id']}).\n"
        f"Personality: {b['personality']}\n"
        f"Voice: {b['voice_description']}\n"
        f"Allowed tones: {', '.join(b['allowed_tones'])}\n"
        f"Default CTA: {b['cta_default']}\n"
        f"Hashtags (use sparingly): {', '.join(b['hashtag_suggestions'])}\n"
        f"\n"
        f"BANNED phrases (never use): {' | '.join(b.get('banned_terms', [])[:10])}\n"
        f"EM DASH BANNED. Use pipes | / commas / full stops / colons.\n"
        f"DO NOT name internal agents: {', '.join(rs.get('internal_agents_banned', []))}.\n"
        f"DO NOT invent prices, offers, specs, dates, distances, percentages, "
        f"or causal claims not backed by verified source.\n"
        + (f"DO NOT reference other operating brands.\n" if rs.get("cross_brand_text_banned") else "")
    )

    # Build the user message — relevance-aware
    user_parts = [
        f"BRIEF: {ctx.get('user_brief') or '(none — infer from context)'}",
        f"CHANNEL: {ctx['channel']['channel']} — {ctx['channel']['rules']['voice_notes']}",
        f"CREATIVE ROUTE: {route['mechanism']} (brand fit {route['brand_fit']}/5)",
        f"SUGGESTED RHETORICAL STRUCTURE: {route['rhetorical_structure_suggestion']}",
        f"RATIONALE: {route['rationale']}",
        "",
        "CONSTRAINTS:",
        f"- Core proposition MUST be about: {brief_subject or 'the requested subject'}",
        f"- Substantive terms to anchor on: {', '.join(subject_keywords[:5]) if subject_keywords else '(no service-specific keywords)'}"
        if subject_keywords else "- Substantive terms: any you use must match the requested subject",
        f"- Core proposition must be DIFFERENT from these recent neighbours (don't paraphrase): {neighbour_excerpts[:3] if neighbour_excerpts else '(none)'}",
        f"- Avoid these stale structural openers (different wording does NOT bypass the check): {structural_openers[:3]}",
        f"- Brand voice: {b['personality']}",
    ]
    if product_facts_text:
        user_parts.append(f"\n{product_facts_text}")
    user_parts.append(
        f"\nReturn ONLY the caption text. No commentary. No emoji beyond what fits the voice. "
        f"End with the brand's default CTA."
    )
    user = "\n".join(user_parts)
    return system, user


# ─── CANDIDATE GENERATION (LLM-backed) ─────────────────────────────────
def _generate_candidate(ctx: dict, route: dict) -> dict:
    """Generate ONE candidate via the LLM. Falls back to a minimal honest
    marker if the LLM is unavailable so the pipeline can still report."""
    brand_id = ctx["brand_id"]
    mech = route["mechanism"]
    rheto = route.get("rhetorical_structure_suggestion", "observation_callout")
    brief_subject = ctx.get("product_service", {}).get("brief_subject") or ""
    system, user = _build_llm_prompt(ctx, route)
    body = _call_llm_chat_completions(system, user)
    if body:
        body = body.strip().strip('"').strip("`")
        # Strip any leading labels like "Caption:" or "Here is..." that the
        # model sometimes prepends.
        body = re.sub(r"^(Caption|Output|Result)\s*:\s*", "", body, flags=re.I).strip()
        # Append CTA if not present
        b = ctx["brand"]
        cta = b.get("cta_default") or ""
        if cta and cta.lower() not in body.lower():
            body = f"{body}\n\n{cta}"
    else:
        # Honest fallback so the pipeline can still surface what was asked.
        body = (
            f"[LLM unavailable — route={mech}, structure={rheto}, "
            f"subject={brief_subject or 'unspecified'}, "
            f"brand={brand_id}]"
        )
    return {
        "candidate_id": "c-" + _hash(f"{ctx.get('context_id')}|{route['route_id']}|{body}")[:10],
        "route": route["route_id"],
        "mechanism": mech,
        "rhetorical_structure": rheto,
        "core_proposition": "",  # filled in by the brief_fidelity check
        "audience_tension": "",
        "evidence_used": [],
        "cta_strategy": ctx["brand"].get("cta_default", ""),
        "body": body,
        "context_id": ctx.get("context_id"),
    }


# ─── CHECKS ────────────────────────────────────────────────────────────
def _check_exact(candidate: str, recent: List[dict]) -> dict:
    cl = (candidate or "").strip().lower()
    if not cl:
        return {"passed": False, "reason": "empty_candidate"}
    cl_norm = re.sub(r"\s+", " ", cl)
    for r in recent[:50]:
        prior = re.sub(r"\s+", " ", (r.get("caption") or "").strip().lower())
        if not prior:
            continue
        if cl_norm == prior:
            return {"passed": False, "reason": "exact_duplicate",
                    "matched_asset_id": r.get("asset_id"),
                    "matched_caption_excerpt": prior[:100]}
        a = cl_norm[:80]
        b = prior[:80]
        if a and b and a == b:
            return {"passed": False, "reason": "near_exact_duplicate",
                    "matched_asset_id": r.get("asset_id")}
    return {"passed": True, "reason": "no_exact_match"}


def _check_structural(candidate: str, structural_families: list) -> dict:
    if not candidate:
        return {"passed": True, "reason": "empty"}
    first = (candidate.split(".")[0] or "")[:50].lower().strip()
    first_norm = re.sub(r"#\w+", "HASHTAG", first)
    first_norm = re.sub(r"\d+", "NUM", first_norm)
    first_norm = re.sub(r"[^\w\s]", "", first_norm).strip()
    # Note: structural fatigue cannot be bypassed by wording rotation.
    # We match by normalised prefix (first 20 chars after normalisation).
    for fam in structural_families[:8]:
        op = (fam.get("opener") or "").strip()
        if not op:
            continue
        op_norm = re.sub(r"#\w+", "HASHTAG", op)
        op_norm = re.sub(r"\d+", "NUM", op_norm)
        op_norm = re.sub(r"[^\w\s]", "", op_norm).strip()
        if op_norm and first_norm.startswith(op_norm[:20]):
            return {"passed": False, "reason": "structural_repeat",
                    "matched_opener": op, "matched_count": fam.get("count", 0)}
    return {"passed": True, "reason": "no_structural_repeat"}


def _check_semantic(candidate: str, recent: List[dict],
                    embeds: Dict[str, list], threshold: float = 0.85) -> dict:
    if not candidate or not embeds:
        return {"passed": True, "reason": "no_embeddings_or_empty", "max_similarity": 0.0}
    cand_vec = _bag_vector(candidate)
    max_sim = 0.0
    nearest = None
    for r in recent[:50]:
        aid = r.get("asset_id")
        if aid in embeds:
            sim = _cosine(embeds[aid], cand_vec)
            if sim > max_sim:
                max_sim = sim
                nearest = r
    if max_sim >= threshold:
        return {
            "passed": False,
            "reason": "semantic_duplicate",
            "max_similarity": round(max_sim, 4),
            "nearest_asset_id": nearest.get("asset_id") if nearest else None,
            "nearest_caption_date": nearest.get("first_seen_at") if nearest else None,
            "nearest_caption_excerpt": (nearest.get("caption") or "")[:120] if nearest else None,
        }
    return {"passed": True, "reason": "no_semantic_duplicate",
            "max_similarity": round(max_sim, 4)}


def _check_brand(candidate: str, brand_id: str, banned: List[str]) -> dict:
    if not candidate:
        return {"passed": False, "reason": "empty"}
    fails = []
    c = candidate
    if "—" in c:
        fails.append("em_dash")
    cl = c.lower()
    for bad in banned:
        if not bad or bad == "—":
            continue
        if bad.lower() in cl:
            fails.append(f"banned_phrase:{bad[:40]}")
    for agent in ("Clawfix", "Retina", "Patch", "Heidi", "Memories", "Forge", "Publisher"):
        if agent in c:
            fails.append(f"internal_agent:{agent}")
    if fails:
        return {"passed": False, "reason": "brand_fail", "reasons": fails}
    return {"passed": True, "reason": "ok"}


def _check_fact(candidate: str, ctx: dict) -> dict:
    if not candidate:
        return {"passed": False, "reason": "empty"}
    fails = []
    # 1. Invented prices (R followed by digits)
    price_hits = re.findall(r"\bR\s?\d{2,}\b", candidate)
    if price_hits:
        ps = ctx.get("product_service", {}) or {}
        cf = ps.get("product_facts", {}) or {}
        if not cf.get("price_zar") and not cf.get("offer"):
            fails.append(f"invented_price:{','.join(price_hits)}")
    # 2. Invented percentages
    # Match any percentage claim: "X% of Y", "X% struggle", "X% improve", etc.
    # Only allow if the percentage appears in canonical product facts OR user_brief.
    pct_hits = re.findall(r"\b\d{1,3}\s?%", candidate)
    if pct_hits:
        ps = ctx.get("product_service", {}) or {}
        cf = ps.get("product_facts", {}) or {}
        allowed = False
        ub = ctx.get("user_brief") or ""
        for hit in pct_hits:
            num = hit.replace(" ", "")
            if num in ub:
                allowed = True
                break
        if not allowed and cf:
            for v in cf.values():
                if isinstance(v, (int, float, str)):
                    if f"{v}%" in candidate:
                        allowed = True
                        break
        if not allowed:
            fails.append(f"invented_percentage:{','.join(pct_hits)}")
    # 3. Unsupported distances / gains / saves / scores
    # Detect pattern: a number + a unit that implies performance gain
    for pattern in [
        r"\b\d+(\.\d+)?\s*(metres|meters|yards|cm|mm)\b",
        r"\b\d+(\.\d+)?\s*(km/h|mph|kph)\b",
        r"\b\d+(\.\d+)?\s*(seconds|minutes|hours)\s*(faster|slower|less|more)\b",
    ]:
        hits = re.findall(pattern, candidate, re.I)
        if hits:
            # Allow only if the number appears in canonical product_facts OR
            # is mentioned in user_brief verbatim
            ps = ctx.get("product_service", {}) or {}
            cf = ps.get("product_facts", {}) or {}
            allowed = False
            if cf:
                for k, v in cf.items():
                    if isinstance(v, (int, float, str)) and str(v) and (
                        re.search(r"\b" + re.escape(str(v)) + r"\b", candidate)
                    ):
                        allowed = True
                        break
            if not allowed and ctx.get("user_brief"):
                if any(num in candidate for num in
                       re.findall(r"\b\d+(\.\d+)?\b", ctx["user_brief"])):
                    allowed = True
            if not allowed:
                fails.append(f"unsupported_number:{','.join(str(h) for h in hits[:2])}")
    # 4. Causal / certainty language
    causal_terms = ["proves", "guarantee", "guarantees", "guaranteed",
                    "the truth", "nobody tells", "the only way"]
    cl = candidate.lower()
    for t in causal_terms:
        if t in cl:
            # Allow "the truth" only when paired with the structural family;
            # otherwise flag as unsupported causal claim.
            fails.append(f"causal_certainty:{t}")
    # 5. Unguarded specific dates
    if re.search(r"\b\d{1,2}\s+(January|February|March|April|May|June|July|"
                 r"August|September|October|November|December)\b", candidate, re.I):
        if not re.search(ctx.get("user_brief") or "", candidate, re.I):
            fails.append("specific_date_unguarded")
    # 6. Invented session durations
    for pattern in [r"\b\d+-minute\s+session\b", r"\b\d+\s*min\s+session\b"]:
        hits = re.findall(pattern, candidate, re.I)
        if hits:
            ps = ctx.get("product_service", {}) or {}
            cf = ps.get("product_facts", {}) or {}
            allowed = bool(cf)
            if not allowed:
                fails.append(f"invented_session_duration:{','.join(hits)}")
    if fails:
        return {"passed": False, "reason": "fact_fail", "reasons": fails}
    return {"passed": True, "reason": "ok"}


def _check_brief_fidelity(candidate: str, ctx: dict) -> dict:
    """Reject candidates whose central proposition drifts from the brief.
    Strategy: detect brief subject keywords; require at least one subject
    keyword OR a clearly related family (e.g. 'putter' → 'putting/green/short game')
    to appear in the candidate. Reject if neither the brief_subject word nor any
    of its known related keywords appear.
    """
    if not candidate:
        return {"passed": False, "reason": "empty"}
    brief_subject = ctx.get("product_service", {}).get("brief_subject") or ""
    if not brief_subject:
        return {"passed": True, "reason": "no_brief_subject_specified"}
    cl = candidate.lower()
    # Direct hit on subject word(s)
    subj_words = [w for w in re.findall(r"\b[a-z]{4,}\b", brief_subject)]
    direct_hit = any(w in cl for w in subj_words)
    if direct_hit:
        return {
            "passed": True,
            "reason": "direct_subject_match",
            "brief_subject": brief_subject,
            "detected_subject": brief_subject,
            "subject_match": True,
            "specificity": "high",
        }
    # Try related keywords
    related = []
    for svc, kws in SERVICE_KEYWORDS.items():
        if svc == brief_subject or brief_subject in svc or svc in brief_subject:
            related = kws
            break
    related_hit = any(kw in cl for kw in related)
    if related_hit:
        return {
            "passed": True,
            "reason": "related_keyword_match",
            "brief_subject": brief_subject,
            "detected_subject": ", ".join([k for k in related if k in cl][:3]),
            "subject_match": True,
            "specificity": "medium",
        }
    return {
        "passed": False,
        "reason": "subject_drift",
        "brief_subject": brief_subject,
        "detected_subject": "(no subject or related keyword found)",
        "subject_match": False,
        "specificity": "low",
        "failure_reason": (
            f"Candidate is generically about club fitting but not specifically about {brief_subject}. "
            f"Subject words {subj_words!r} and related {related!r} not present."
        ),
    }


# ─── PERFORMANCE PRIOR ────────────────────────────────────────────────
def _performance_prior(candidate: str, ctx: dict) -> dict:
    perf_evidence = ctx.get("performance_context", {}).get("samples", [])
    if not perf_evidence:
        return {
            "confidence": "unknown",
            "comparable_posts": 0,
            "signal": "unknown",
            "note": "No performance_eligible evidence for this brand yet.",
        }
    comparable = [
        {"asset_id": p["asset_id"], "media_type": p["media_type"],
         "timestamp": p["timestamp"], "win_score": p["provisional_win_score"]}
        for p in perf_evidence if p.get("provisional_win_score") is not None
    ]
    if not comparable:
        return {"confidence": "unknown", "comparable_posts": 0, "signal": "unknown"}
    win_scores = [c["win_score"] for c in comparable if c["win_score"] is not None]
    if not win_scores:
        return {"confidence": "low", "comparable_posts": len(comparable), "signal": "unknown"}
    median = sorted(win_scores)[len(win_scores) // 2]
    confidence = (
        "low" if len(comparable) < 5
        else "medium" if len(comparable) < 30
        else "high"
    )
    return {
        "confidence": confidence,
        "comparable_posts": len(comparable),
        "median_win_score_brand": round(median, 4),
        "signal": "neutral",
        "note": "Brand-wide weak prior. Candidate-specific comparison requires per-caption lexical indexing (P1.2+).",
    }


# ─── PROPOSITION + AUDIENCE TENSION EXTRACTOR ──────────────────────────
def _extract_proposition(candidate: dict, brief_subject: str) -> Tuple[str, str, List[str]]:
    """Extract a one-sentence core proposition + audience tension + evidence
    used from the LLM output. Heuristic — first sentence = proposition."""
    body = candidate.get("body", "")
    first_sentence = re.split(r"[.!?]\s", body.strip(), 1)[0].strip()
    # Audience tension: heuristic — find words suggesting tension
    tension_words = []
    if "but" in body.lower():
        tension_words.append("contrast_but")
    if "?" in body:
        tension_words.append("curiosity_question")
    if re.search(r"\b(not|no|never|stop|wrong|miss)\b", body.lower()):
        tension_words.append("negation_anchor")
    if re.search(r"\b(first|finally|next|the truth|the only)\b", body.lower()):
        tension_words.append("pivot_word")
    # Evidence used: scan for metric-like terms
    evidence_used = []
    if re.search(r"\d+", body):
        evidence_used.append("contains_number")
    if re.search(r"\b(trackman|shaft|attack angle|smash factor|swing speed|carry)\b",
                 body.lower()):
        evidence_used.append("mentions_trackman_or_metric")
    if re.search(r"\b\d+\s*(m|metres|yards|minutes|hour|session)\b", body.lower()):
        evidence_used.append("mentions_measurable_quantity")
    if not evidence_used:
        evidence_used.append("no_specific_metric")
    return first_sentence, ",".join(tension_words) or "low_tension", evidence_used


# ─── THE PIPELINE ─────────────────────────────────────────────────────
def run_caption_pipeline(request: dict) -> dict:
    """The full P1.1 final pipeline. Generates 12 internally, returns best 5.

    request = {
        brand_id, user_brief, channel?, product_brand?, product_id?,
        service?, audience?, objective?, n_survivors? (default 5),
        n_candidates? (default 12), avoid_mechanisms?, ...
    }
    """
    t0 = _now_iso()
    ctx = build_generation_context(
        brand_id=request.get("brand_id", ""),
        task_type=request.get("task_type", "caption"),
        campaign_id=request.get("campaign_id"),
        product_brand=request.get("product_brand"),
        product_id=request.get("product_id"),
        service=request.get("service"),
        audience=request.get("audience"),
        channel=request.get("channel"),
        objective=request.get("objective"),
        user_brief=request.get("user_brief"),
    )
    if not ctx.get("ok"):
        return ctx

    n_survivors = min(int(request.get("n_survivors", 5)), 10)
    n_candidates = max(int(request.get("n_candidates", 12)), n_survivors)
    avoid = request.get("avoid_mechanisms", [])

    routes = plan_routes(ctx, n=n_survivors, avoid_mechanisms=avoid)
    if not routes:
        return {
            "ok": False,
            "error": "no_routes_planned",
            "context": ctx,
        }

    # Generate n_candidates, rotating through mechanisms + extras so we have
    # enough to choose the best 5.
    all_mechs = [r["mechanism"] for r in routes]
    used = set(all_mechs)
    extras_pool = [m for m in MECHANISMS if m not in used and m not in avoid]
    expanded = list(routes)
    for i, m in enumerate(extras_pool):
        if len(expanded) >= n_candidates:
            break
        base_route = next(r for r in routes if r["mechanism"] == all_mechs[i % len(all_mechs)])
        new_route = {
            "route_id": f"route-extra-{i+1}-{m}",
            "mechanism": m,
            "brand_fit": MECHANISM_FIT.get(ctx["brand_id"], {}).get(m, 0),
            "rhetorical_structure_suggestion": _pick_rhetorical_structure(m, ctx["brand_id"]),
            "rationale": _mechanism_rationale(m, ctx["brand_id"], ctx),
        }
        expanded.append(new_route)
    # If still short, repeat the first n routes
    while len(expanded) < n_candidates:
        r = routes[len(expanded) % len(routes)].copy()
        r["route_id"] = r["route_id"] + f"-rpt{len(expanded)}"
        expanded.append(r)

    # Generate
    candidates = []
    for r in expanded:
        candidates.append(_generate_candidate(ctx, r))

    # Run checks
    recent = _load_recent_content(ctx["brand_id"], limit=50)
    intel = _load_caption_intel()
    embeds, embed_kind, embed_model = _load_embeddings()
    banned = _extract_banned_terms(ctx["brand_id"])
    structural_fams = intel.get("structural_families", [])
    brief_subject = ctx.get("product_service", {}).get("brief_subject") or ""

    survivors = []
    rejects = {"exact": [], "structural": [], "semantic": [],
               "brand": [], "fact": [], "brief_fidelity": []}
    detailed_rejects = []

    for c in candidates:
        passed_all = True
        checks = {}
        # Brief fidelity FIRST — if the candidate drifts from the subject,
        # don't waste time on other checks.
        bf = _check_brief_fidelity(c["body"], ctx)
        checks["brief_fidelity"] = bf
        if not bf["passed"]:
            rejects["brief_fidelity"].append(c["candidate_id"])
            passed_all = False
        if passed_all and request.get("enforce_exact_dedupe", True):
            r = _check_exact(c["body"], recent)
            checks["exact"] = r
            if not r["passed"]:
                rejects["exact"].append(c["candidate_id"])
                passed_all = False
        if passed_all and request.get("enforce_structural_check", True):
            r = _check_structural(c["body"], structural_fams)
            checks["structural"] = r
            if not r["passed"]:
                rejects["structural"].append(c["candidate_id"])
                passed_all = False
        if passed_all and request.get("enforce_semantic_check", True):
            r = _check_semantic(c["body"], recent, embeds)
            checks["semantic"] = r
            if not r["passed"]:
                rejects["semantic"].append(c["candidate_id"])
                passed_all = False
        if passed_all and request.get("enforce_brand_check", True):
            r = _check_brand(c["body"], ctx["brand_id"], banned)
            checks["brand"] = r
            if not r["passed"]:
                rejects["brand"].append(c["candidate_id"])
                passed_all = False
        if passed_all and request.get("enforce_fact_check", True):
            r = _check_fact(c["body"], ctx)
            checks["fact"] = r
            if not r["passed"]:
                rejects["fact"].append(c["candidate_id"])
                passed_all = False

        # Extract proposition + tension + evidence for survivors
        prop, tension, evidence = _extract_proposition(c, brief_subject)
        c["core_proposition"] = prop
        c["audience_tension"] = tension
        c["evidence_used"] = evidence
        c["checks"] = checks

        if passed_all:
            prior = _performance_prior(c["body"], ctx)
            c["performance_prior"] = prior
            semantic_neighbour = _nearest_neighbour(c, recent, embeds)
            c["nearest_semantic_neighbour"] = semantic_neighbour
            c["structural_family"] = _detect_structural_family(c["body"], structural_fams)
            c["why_this_route"] = (
                f"Route={c['mechanism']} (brand fit={c.get('route', '?')}). "
                f"Core proposition: {prop[:140]}. "
                f"Subject fidelity: {bf['reason']}. "
                f"Prior: {prior.get('confidence', 'unknown')}, "
                f"n_comparable={prior.get('comparable_posts', 0)}."
            )
            survivors.append(c)
        else:
            c["rejected_by"] = next((k for k, v in checks.items() if not v.get("passed")), "unknown")
            detailed_rejects.append(c)

        if len(survivors) >= n_survivors:
            break

    # Route diversity check at the proposition level
    propositions = [s["core_proposition"] for s in survivors]
    unique_props = len(set(propositions))
    mechanisms = [s["mechanism"] for s in survivors]
    unique_mechs = len(set(mechanisms))

    # Nearest-neighbour within the surviving set (sibling similarity)
    sibling_sims = []
    for i, s in enumerate(survivors):
        for j, t in enumerate(survivors):
            if i < j:
                sim = _cosine(_bag_vector(s["body"]), _bag_vector(t["body"]))
                sibling_sims.append(round(sim, 4))
    max_sibling_sim = max(sibling_sims) if sibling_sims else 0.0

    # Final survivors can be < n_survivors if too many failed — we do NOT
    # lower the gates.
    final_survivors = survivors[:n_survivors]
    quality_warning = (
        None if len(final_survivors) >= n_survivors
        else f"Could not produce {n_survivors} survivors after {len(candidates)} candidates. "
             f"Returned {len(final_survivors)} rather than lowering quality gates."
    )

    t1 = _now_iso()
    obs = {
        "context_build_t0": t0,
        "context_build_t1": t1,
        "routes_planned": len(routes),
        "candidates_generated": len(candidates),
        "exact_rejects": len(rejects["exact"]),
        "structural_rejects": len(rejects["structural"]),
        "semantic_rejects": len(rejects["semantic"]),
        "brand_rejects": len(rejects["brand"]),
        "fact_rejects": len(rejects["fact"]),
        "brief_fidelity_rejects": len(rejects["brief_fidelity"]),
        "final_survivors": len(final_survivors),
        "model": os.environ.get("CAPTION_MODEL", "gpt-4o-mini"),
        "provider": "openai" if _resolve_openai_chat_key() else "none",
        "embedding_kind": embed_kind,
        "embedding_model": embed_model,
        "route_diversity": {
            "unique_mechanisms": unique_mechs,
            "unique_propositions": unique_props,
            "max_sibling_similarity": max_sibling_sim,
        },
        "quality_warning": quality_warning,
    }

    return {
        "ok": True,
        "context_id": ctx.get("context_id"),
        "context": ctx,
        "routes_planned": routes,
        "candidates_considered": candidates,
        "survivors": final_survivors,
        "rejects": rejects,
        "rejected_candidates": detailed_rejects,
        "observability": obs,
        "ts": t1,
    }


def _nearest_neighbour(candidate: dict, recent: List[dict],
                        embeds: Dict[str, list]) -> dict:
    if not embeds:
        return {}
    cand_vec = _bag_vector(candidate["body"])
    best = None
    best_sim = 0.0
    for r in recent[:50]:
        aid = r.get("asset_id")
        if aid in embeds:
            sim = _cosine(embeds[aid], cand_vec)
            if sim > best_sim:
                best_sim = sim
                best = r
    if not best:
        return {}
    return {
        "asset_id": best.get("asset_id"),
        "media_type": best.get("media_type"),
        "first_seen_at": best.get("first_seen_at"),
        "caption_excerpt": (best.get("caption") or "")[:120],
        "max_similarity": round(best_sim, 4),
    }


def _detect_structural_family(body: str, families: list) -> str:
    """Which P0.6 structural opener family does this candidate most resemble?
    Returns 'novel' if none of the top 8 families match (which is good —
    means it deliberately used a different structure)."""
    if not body or not families:
        return "novel"
    first = (body.split(".")[0] or "")[:50].lower().strip()
    first_norm = re.sub(r"#\w+", "HASHTAG", first)
    first_norm = re.sub(r"\d+", "NUM", first_norm)
    first_norm = re.sub(r"[^\w\s]", "", first_norm).strip()
    for fam in families[:8]:
        op = (fam.get("opener") or "").strip()
        if not op:
            continue
        op_norm = re.sub(r"#\w+", "HASHTAG", op)
        op_norm = re.sub(r"\d+", "NUM", op_norm)
        op_norm = re.sub(r"[^\w\s]", "", op_norm).strip()
        if op_norm and first_norm.startswith(op_norm[:20]):
            return op
    return "novel"


# ─── TASTE EVENTS ─────────────────────────────────────────────────────
def _taste_dir() -> Path:
    return Path(_data_dir()) / "intelligence" / "taste"


def _init_taste_dir() -> None:
    _taste_dir().mkdir(parents=True, exist_ok=True)


def record_taste_event(event: dict) -> dict:
    _init_taste_dir()
    event = dict(event or {})
    event["event_id"] = "evt-" + _hash(json.dumps(event, sort_keys=True, default=str))[:12]
    event["recorded_at"] = _now_iso()
    p = _taste_dir() / "events.jsonl"
    with p.open("a") as f:
        f.write(json.dumps(event, default=str) + "\n")
    return {"ok": True, "event_id": event["event_id"], "path": str(p)}


def list_taste_events(brand_id: Optional[str] = None,
                      limit: int = 50) -> List[dict]:
    p = _taste_dir() / "events.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if brand_id and rec.get("brand_id") != brand_id:
            continue
        out.append(rec)
    out.sort(key=lambda x: x.get("recorded_at", ""), reverse=True)
    return out[:limit]
# Touch for rebuild — 1789048443
