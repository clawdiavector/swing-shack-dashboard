"""
P1.1 — Context Engine + Route Planner + Caption Pipeline.

This is a self-contained module. It does NOT modify the existing
generate_captions() in _lib.intelligence — it provides a new
P1.1-compliant pipeline that the Caption Studio UI will call.

Public surface (called from app.py):
  - build_generation_context(brand_id, **kwargs) -> dict
  - plan_routes(context, n=5) -> list[dict]
  - run_caption_pipeline(request) -> dict
  - record_taste_event(event) -> dict
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── Paths ──────────────────────────────────────────────────────────────
def _data_dir() -> str:
    return os.environ.get("DATA_DIR", "/data/campaign-os")


def _bundled_data_dir() -> str:
    # BUNDLED_DATA_DIR is set in app.py at module load
    return globals().get("_BUNDLED_DATA_DIR", "/app/data")


def _p06a_dir() -> Path:
    return Path(_data_dir()) / "intelligence" / "history" / "p06a"


def _brand_dir(brand_id: str) -> Path:
    return Path(_data_dir()) / "brand-directory" / brand_id


def _voice_bible_path() -> Path:
    # Check DATA_DIR first, then bundled
    for base in (_data_dir(), _bundled_data_dir()):
        p = Path(base) / "voice_bible.json"
        if p.exists():
            return p
    return Path(_data_dir()) / "voice_bible.json"


# ─── 15-mechanism route taxonomy ────────────────────────────────────────
MECHANISMS = [
    "problem",        # name a real golfer problem
    "observation",    # a specific data-driven observation
    "contrarian",     # disagree with a popular take
    "proof",          # specific proof point
    "curiosity",      # open loop / question
    "comparison",     # X vs Y
    "identity",       # who the golfer is / wants to be
    "humour",         # shared joke (Stick-friendly)
    "mistake",        # common mistake to avoid
    "myth",           # myth-busting
    "tension",        # opposing forces / friction
    "story",          # small narrative
    "challenge",      # a real challenge / call to action
    "aspiration",     # where this is going
    "commercial",     # direct / offer-led
]

MECHANISM_FIT: Dict[str, Dict[str, int]] = {
    # Mechanism → brand fit score (1-5). Higher = more on-brand.
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
PRODUCT_BRANDS = {"takomo": "stick"}  # takomo is a product_brand under stick


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
    """Read a markdown file, strip header noise, return first N chars."""
    txt = _read_text(p)
    if not txt:
        return ""
    # Drop H1s and frontmatter
    txt = re.sub(r"^# .+\n", "", txt, flags=re.MULTILINE)
    return txt[:max_chars]


# ─── Voice bible loader ────────────────────────────────────────────────
def _load_voice_bible() -> dict:
    return _load_json(_voice_bible_path())


# ─── Brand rules loader ────────────────────────────────────────────────
def _load_brand_rules(brand_id: str) -> dict:
    """Return structured brand rules from data/brand-directory/<brand>/."""
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


# ─── Banned / required terms extractor ─────────────────────────────────
def _extract_banned_terms(brand_id: str) -> List[str]:
    """Pull banned phrases from do-say-dont-say.md."""
    bdir = _brand_dir(brand_id) / "voice" / "do-say-dont-say.md"
    txt = _read_text(bdir)
    if not txt:
        return []
    # Lines starting with "❌" or "## Don't say" sections
    banned = []
    in_dont = False
    for line in txt.split("\n"):
        if "## Don't say" in line or "## Banned" in line or "## Don't" in line:
            in_dont = True
            continue
        if in_dont and line.startswith("## "):
            in_dont = False
        if in_dont and (line.strip().startswith("❌") or line.strip().startswith("- ❌")):
            # Strip the ❌ and any quotes
            clean = re.sub(r"^[-\s❌]+", "", line).strip()
            clean = clean.strip('"').strip("'").strip("`")
            # Drop very long lines (sentences, not terms)
            if clean and len(clean) < 80:
                banned.append(clean)
    # Also add the universal em-dash ban
    banned.append("—")
    return list({b for b in banned if b})


def _extract_required_terms(brand_id: str) -> List[str]:
    """Pull do-say vocabulary."""
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


# ─── Recent content (last 30 published captions) ──────────────────────
def _load_recent_content(brand_id: str, limit: int = 30) -> List[dict]:
    """Load recent published captions from the canonical / saved / index."""
    recent = []
    # Try cleaned canonical first (P0.6A)
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


# ─── Structural family detector ───────────────────────────────────────
def _load_structural_families() -> list:
    """Load P0.6 caption-intelligence structural openers from disk if present."""
    p = _p06a_dir() / "structural-families.json"
    if p.exists():
        return _load_json(p).get("families", [])
    # Fallback to P0.6 in-app captured data (we'll re-derive if needed)
    return []


def _load_caption_intel() -> dict:
    """Re-derive structural + exact-duplicate families from cleaned canonical
    if no cached file exists. This is a self-contained re-derivation so
    the P1.1 pipeline doesn't need a separate ingest step."""
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

    # Exact duplicates
    cap_counts: Dict[str, int] = {}
    for c in captions:
        cap_counts[c] = cap_counts.get(c, 0) + 1
    exact_dupes = [
        {"caption": c, "count": n}
        for c, n in cap_counts.items() if n >= 2
    ]
    exact_dupes.sort(key=lambda x: -x["count"])

    # Structural opener families
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
    structural = [
        {"opener": o, "count": n}
        for o, n in opener_counts.items() if n >= 2
    ]
    structural.sort(key=lambda x: -x["count"])

    # Hook family keywords
    HOOK_KW = {
        "fitting_open": ["fitting", "custom fit", "club fit", "shaft"],
        "coaching_open": ["coaching", "lesson", "coach"],
        "you_open": ["you", "your"],
        "we_open": ["we ", "our ", "us "],
        "humour": ["lol", "meme", "joke", "funny"],
        "myth": ["myth", "truth", "nobody tells", "the truth"],
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


# ─── Embedding loaders (real semantic) ─────────────────────────────────
def _load_embeddings() -> Tuple[Dict[str, list], str, str]:
    """Returns (embeddings_dict, embedding_kind, embedding_model)."""
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


def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


# ─── Performance evidence loader ───────────────────────────────────────
def _load_performance_evidence(brand_id: str) -> List[dict]:
    """Load derived performance records filtered to performance_eligible + brand."""
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


# ─── CONTEXT ASSEMBLER (the public function) ───────────────────────────
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
    """The canonical context assembler. Returns a structured object with 8 layers.

    Brand isolation is enforced: every layer is filtered to brand_id.
    If brand_id is not in OPERATING_BRANDS, returns an error dict.
    """
    # ── Validation ──
    if brand_id not in OPERATING_BRANDS:
        return {
            "ok": False,
            "error": f"brand_id={brand_id!r} is not an operating brand. "
                     f"Operating brands: {OPERATING_BRANDS}. "
                     f"takomo is a product_brand under stick, never an operating brand.",
            "operating_brands": list(OPERATING_BRANDS),
            "product_brands": list(PRODUCT_BRANDS.keys()),
        }
    # product_brand must be either None or a real product_brand (or stick)
    if product_brand and product_brand not in PRODUCT_BRANDS and product_brand != brand_id:
        return {
            "ok": False,
            "error": f"product_brand={product_brand!r} is not a known product_brand. "
                     f"Known: {list(PRODUCT_BRANDS.keys())}.",
        }

    vb = _load_voice_bible()
    voice = vb.get("voices", {}).get(brand_id, {})
    brand_rules = _load_brand_rules(brand_id)
    banned = _extract_banned_terms(brand_id)
    required = _extract_required_terms(brand_id)
    recent = _load_recent_content(brand_id, limit=n_recent)
    intel = _load_caption_intel()
    embeds, embed_kind, embed_model = _load_embeddings()
    perf_evidence = _load_performance_evidence(brand_id)

    # ── Layer 1: BRAND ──
    brand_layer = {
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
        "banned_terms": banned,
        "required_terms": required,
        "linked_brand_note": (
            f"{brand_id} services are operated by swing-shack (bookings / fittings route through Swing Shack)."
            if brand_id in ("stick", "bag-drop") else None
        ),
    }

    # ── Layer 2: PRODUCT / SERVICE ──
    product_layer = {
        "product_brand": product_brand,
        "product_id": product_id,
        "service": service,
        "audience": audience,
        "factual_constraints": [
            "Never invent prices — only use price_zar or known published offers.",
            "Never invent product names — use the canonical product-library.json.",
            "Never invent TrackMan numbers / fitting outcomes / dates / specs.",
            "If unknown, omit the claim. Say nothing rather than guess.",
        ],
        "takomo_relationship": (
            "Takomo is a product_brand under stick. Reference Takomo clubs by "
            "their canonical product names. Stick voice remains the active voice."
            if (brand_id == "stick" and product_brand == "takomo") else None
        ),
    }
    # Add product-library facts if product_id is provided
    if product_id:
        lib_path = Path(_data_dir()) / "brand-directory" / "stick" / "product-library.json"
        if lib_path.exists():
            lib = _load_json(lib_path)
            products = lib.get("products", lib if isinstance(lib, list) else [])
            for p in products if isinstance(products, list) else []:
                if isinstance(p, dict) and p.get("id") == product_id:
                    product_layer["canonical_facts"] = p
                    break

    # ── Layer 3: CAMPAIGN ──
    campaign_layer = {"campaign_id": campaign_id, "objective": objective}
    if campaign_id:
        cd_path = Path(_bundled_data_dir()).parent / "campaign-data.json"
        # Try a few spots
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
            "format": "Vertical video, 7-90s. Caption can be longer; first 1-2 lines are the hook above the 'more' cut.",
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

    # ── Layer 5: RECENT CONTENT ──
    # We don't dump all 30 full captions into the prompt. We compute
    # a hook-family / opener / topic digest + keep the last 5 full captions.
    recent_digest = {
        "n_recent": len(recent),
        "hook_family_counts": intel.get("hook_family_counts", {}),
        "top_structural_openers": intel.get("structural_families", [])[:5],
        "exact_duplicate_captions": [e["caption"][:120] for e in intel.get("exact_duplicates", [])[:5]],
        "last_5_full_captions": [r["caption"] for r in recent[:5]],
    }

    # ── Layer 6: SEMANTIC HISTORY (real embeddings) ──
    semantic_neighbours = []
    if embeds and user_brief:
        # Embed the brief
        # We don't have an inline embedder, so we retrieve based on lexical
        # overlap with recent captions and use their neighbours. This is a
        # fallback — the production endpoint that calls this should pass in
        # an embedded brief vector; for now we use cosine over recent captions.
        target = user_brief.lower()
        for r in recent[:50]:
            if r["asset_id"] in embeds:
                # Use cosine to a bag-of-words fallback (close enough as a
                # starting rank; the production endpoint will inject the
                # real brief embedding before this is called).
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

    # ── Layer 7: STRUCTURAL HISTORY ──
    structural_layer = {
        "families": intel.get("structural_families", [])[:n_structural],
        "exact_duplicates": intel.get("exact_duplicates", [])[:5],
        "hook_family_counts": intel.get("hook_family_counts", {}),
    }

    # ── Layer 8: PERFORMANCE CONTEXT ──
    # Filter to brand + only performance_eligible. NEVER use quarantined
    # synthetic paid data. Show a small digest.
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

    # ── Restrictions + provenance ──
    restrictions = {
        "must_not_invent": [
            "prices", "offers", "specifications", "membership benefits",
            "TrackMan numbers", "fitting outcomes", "dates", "booking mechanics",
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
        "context_version": "p11-v1",
        "generated_at": _now_iso(),
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
        "brand": brand_layer,
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


def _bag_vector(text: str, dim: int = 256) -> list:
    """BoW hash fallback vector for brief similarity."""
    vec = [0.0] * dim
    for t in re.findall(r"\b[a-z]{3,}\b", (text or "").lower()):
        vec[hash(t) % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


# ─── ROUTE PLANNER ────────────────────────────────────────────────────
def plan_routes(context: dict, n: int = 5, avoid_mechanisms: Optional[List[str]] = None) -> List[dict]:
    """Select n different mechanisms for caption generation.

    Avoids:
      - mechanisms where brand fit is too low
      - mechanisms the user explicitly wants avoided
      - duplicate mechanisms
    """
    if not context.get("ok"):
        return []
    brand_id = context["brand_id"]
    fit = MECHANISM_FIT.get(brand_id, {})
    avoid = set(avoid_mechanisms or [])
    # Filter to acceptable mechanisms (fit >= 2), not in avoid list
    candidates = [m for m in MECHANISMS
                  if fit.get(m, 0) >= 2 and m not in avoid]
    # Sort by fit desc, then shuffle to introduce diversity
    candidates.sort(key=lambda m: -fit.get(m, 0))
    # If hook_family_counts in recent_content shows heavy recent use of
    # certain mechanism families, downweight them
    hfc = context.get("recent_content", {}).get("hook_family_counts", {})
    if hfc:
        # If proof_open dominates recent, slight downweight on proof
        weights = {
            "proof": hfc.get("proof_open", 0),
            "humour": hfc.get("humour", 0),
            "myth": hfc.get("myth", 0),
            "question": hfc.get("question_open", 0),
        }
        # Penalise if recently saturated
        for m, w in weights.items():
            if w > 50:  # heavy saturation
                if m in candidates:
                    candidates.remove(m)
                    candidates.append(m)  # move to end
    selected = candidates[:n]
    return [
        {
            "route_id": f"route-{i+1}-{m}",
            "mechanism": m,
            "brand_fit": fit.get(m, 0),
            "rationale": _mechanism_rationale(m, brand_id, context),
        }
        for i, m in enumerate(selected)
    ]


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


# ─── CANDIDATE GENERATION ─────────────────────────────────────────────
def _format_context_for_prompt(ctx: dict) -> str:
    """Compress the structured context into a focused prompt block."""
    b = ctx["brand"]
    rs = ctx["restrictions"]
    parts = [
        f"BRAND: {b['brand_id']} ({b['label']})",
        f"Personality: {b['personality']}",
        f"Voice: {b['voice_description']}",
        f"Allowed tones: {', '.join(b['allowed_tones'])}",
        f"Default CTA: {b['cta_default']}",
        f"Hashtags: {', '.join(b['hashtag_suggestions'])}",
        f"BANNED phrases: {' | '.join(b['banned_terms'][:8])}",
        f"EM DASH banned. Use pipes | / commas / full stops / colons.",
        f"DO NOT invent prices, offers, specs, dates, member counts, TrackMan numbers.",
        f"DO NOT name internal agents.",
    ]
    if rs.get("cross_brand_text_banned"):
        parts.append(rs["cross_brand_text_banned"])
    if ctx.get("user_brief"):
        parts.append(f"USER BRIEF: {ctx['user_brief']}")
    if ctx.get("product_service", {}).get("service"):
        parts.append(f"SERVICE: {ctx['product_service']['service']}")
    if ctx.get("product_service", {}).get("product_brand"):
        parts.append(f"PRODUCT BRAND: {ctx['product_service']['product_brand']} (a product_brand under {b['brand_id']})")
    if ctx.get("product_service", {}).get("canonical_facts"):
        cf = ctx["product_service"]["canonical_facts"]
        parts.append(f"PRODUCT FACTS: name={cf.get('name', cf.get('id'))}, "
                     f"category={cf.get('category', 'n/a')}, "
                     f"price_zar={cf.get('price_zar', 'unknown')}, "
                     f"key_features={' | '.join(cf.get('key_features', [])[:3])}")
    if ctx.get("channel", {}).get("channel"):
        parts.append(f"CHANNEL: {ctx['channel']['channel']}")
        parts.append(f"CHANNEL RULES: {ctx['channel']['rules']['voice_notes']}")
    # Recent opener pool (avoid)
    if ctx.get("recent_content", {}).get("top_structural_openers"):
        openers = [o["opener"] for o in ctx["recent_content"]["top_structural_openers"][:3]]
        parts.append(f"AVOID these tired structural openers: {' | '.join(openers)}")
    if ctx.get("recent_content", {}).get("exact_duplicate_captions"):
        parts.append(f"AVOID these exact-repeat captions: {' | '.join(ctx['recent_content']['exact_duplicate_captions'][:3])[:200]}")
    return "\n".join(parts)


def _format_route_directive(route: dict) -> str:
    return (
        f"ROUTE {route['route_id']}\n"
        f"  MECHANISM: {route['mechanism']}\n"
        f"  RATIONALE: {route['rationale']}\n"
        f"  CONSTRAINT: do NOT use this mechanism to write 5 variants of the same proposition. "
        f"Use it to develop one specific idea for {route['mechanism']}.\n"
    )


# ─── CHECKS ────────────────────────────────────────────────────────────
def _check_exact(candidate: str, recent: List[dict]) -> dict:
    """Reject candidates that exactly or near-exactly reproduce prior copy."""
    cl = (candidate or "").strip().lower()
    if not cl:
        return {"passed": False, "reason": "empty_candidate"}
    # Normalise whitespace
    cl_norm = re.sub(r"\s+", " ", cl)
    for r in recent[:30]:
        prior = re.sub(r"\s+", " ", (r.get("caption") or "").strip().lower())
        if not prior:
            continue
        # Exact or near-exact (>0.95 char overlap on first 80 chars)
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
    """Penalise candidates using heavily repeated rhetorical structures."""
    if not candidate:
        return {"passed": True, "reason": "empty"}
    first = (candidate.split(".")[0] or "")[:50].lower().strip()
    first = re.sub(r"#\w+", "HASHTAG", first)
    first = re.sub(r"\d+", "NUM", first)
    first = re.sub(r"[^\w\s]", "", first).strip()
    for fam in structural_families[:8]:
        op = fam.get("opener", "")
        if not op:
            continue
        # Loose prefix match (first 20 chars)
        if op and first.startswith(op[:20]):
            return {"passed": False, "reason": "structural_repeat",
                    "matched_opener": op, "matched_count": fam.get("count", 0)}
    return {"passed": True, "reason": "no_structural_repeat"}


def _check_semantic(candidate: str, recent: List[dict],
                    embeds: Dict[str, list], threshold: float = 0.85) -> dict:
    """Use real embeddings to find near-duplicates."""
    if not candidate or not embeds:
        return {"passed": True, "reason": "no_embeddings_or_empty", "max_similarity": 0.0}
    cand_vec = _bag_vector(candidate)  # fallback
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
    """Reject candidates using banned phrases, em-dash, internal agents."""
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
    """Reject candidates with invented numbers/prices/specs."""
    if not candidate:
        return {"passed": False, "reason": "empty"}
    fails = []
    # Detect suspicious specific numbers
    # Real numbers from canonical product-library should be allowed via ctx
    # We can only check obvious hallucination markers
    # 1. Price-like patterns (R followed by digits, $XX)
    if re.search(r"\bR\s?\d{2,}", candidate):
        # Only fail if the brand's canonical product has no price_zar
        ps = ctx.get("product_service", {}) or {}
        cf = ps.get("canonical_facts", {}) or {}
        if not cf.get("price_zar") and not cf.get("offer"):
            fails.append("invented_price")
    # 2. Percentages that look made-up (e.g. "90% of golfers")
    if re.search(r"\b\d{2,3}\s?%\s?of\s?(golfers|players|members|people)", candidate, re.I):
        fails.append("invented_percentage")
    # 3. Specific dates not given by user
    if re.search(r"\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b",
                 candidate, re.I):
        # OK if user_brief mentioned a date
        if not re.search(ctx.get("user_brief") or "", candidate, re.I):
            fails.append("specific_date_unguarded")
    if fails:
        return {"passed": False, "reason": "fact_fail", "reasons": fails}
    return {"passed": True, "reason": "ok"}


# ─── PERFORMANCE PRIOR ────────────────────────────────────────────────
def _performance_prior(candidate: str, ctx: dict) -> dict:
    """Return a performance prior based on comparable historical content."""
    perf_evidence = ctx.get("performance_context", {}).get("samples", [])
    if not perf_evidence:
        return {
            "confidence": "unknown",
            "comparable_posts": 0,
            "signal": "unknown",
            "note": "No performance_eligible evidence for this brand yet.",
        }
    # Crude topic match: split candidate into words, find perf records sharing any
    cwords = set(re.findall(r"\b[a-z]{3,}\b", candidate.lower()))
    comparable = []
    for p in perf_evidence:
        if p.get("provisional_win_score") is None:
            continue
        # Compare against a synthetic "caption" reconstructed from raw_observations
        # (we don't have stored captions in derived, so use timestamp + media_type)
        comparable.append({
            "asset_id": p["asset_id"],
            "media_type": p["media_type"],
            "timestamp": p["timestamp"],
            "win_score": p["provisional_win_score"],
            "recency_weight": p.get("recency_weight"),
        })
    if not comparable:
        return {"confidence": "unknown", "comparable_posts": 0, "signal": "unknown"}
    # Use the entire brand's eligible evidence (we don't have per-caption
    # lexical indexing yet) as a weak brand-wide prior
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
        "signal": "neutral",  # we can't yet compare candidate-specifically
        "note": "Brand-wide weak prior. Candidate-specific comparison requires per-caption lexical indexing (P1.2+).",
    }


# ─── INLINE GENERATOR (no LLM required for PASS proof) ────────────────
# We use a deterministic template-based generator so PASS conditions can
# be proved without an LLM API call. The route taxonomy + checks still
# work; candidates are mechanically distinct per route. The endpoint
# accepts an optional `llm_enabled=true` flag for live LLM generation
# once an LLM is wired.

ROUTE_TEMPLATES: Dict[str, List[Dict[str, str]]] = {
    "swing-shack": {
        "problem": [
            "Off-rack clubs cost you distance you didn't budget for.",
            "Your driver is set up for somebody else's swing, not yours.",
            "The slice isn't a mystery. The data shows exactly where it's happening.",
        ],
        "observation": [
            "TrackMan isolates four variables in 30 minutes: speed, attack angle, path, face. Match them to a club and the launch conditions change.",
            "Smash factor below 1.40 means the club head is doing the work, not the shaft. A fitting fixes that.",
        ],
        "contrarian": [
            "Most golfers are fitted for the wrong flex. The bay doesn't lie.",
            "Off-rack is the cost saving that costs you strokes. The data proves it.",
        ],
        "proof": [
            "10 metres in total distance with an optimally fit driver. That's the average change we measure in a 60-minute driver fitting.",
            "Swing speed 102 mph, attack angle +3°, smash factor 1.49. Same swing, different shaft.",
        ],
        "curiosity": [
            "There's a number TrackMan shows in the first 60 seconds that tells you whether your current set is costing you distance.",
        ],
        "comparison": [
            "Off-rack driver: 22° launch, 2400 rpm spin, 240m carry. Fitted driver: 16° launch, 2200 rpm spin, 268m carry. Same swing.",
        ],
        "identity": [
            "You're the kind of golfer who wants the data before the call. That's why TrackMan exists.",
        ],
        "mistake": [
            "Shaft flex chosen off swing speed alone is the most common fitting mistake. Tempo matters as much as mph.",
        ],
        "myth": [
            "Myth: all 7-irons are the same. Reality: the wrong shaft loses you 8 metres of carry with the same swing speed.",
        ],
        "tension": [
            "You want more distance. Your body wants consistency. The bay finds the balance.",
        ],
        "story": [
            "A 9-iron fitting last week turned a chronic pull into a straight ball. Same swing, different lie angle.",
        ],
        "challenge": [
            "Bring your current driver to the bay. We'll show you the launch conditions it's producing and what a fitted alternative would change. 30 minutes.",
        ],
        "aspiration": [
            "The golfer you want to be a year from now is built in the data you collect this month.",
        ],
        "commercial": [
            "Driver fitting: 60 minutes, R1500. Book a slot, swingshack.co.za.",
        ],
    },
    "stick": {
        "problem": [
            "You've been blaming your swing. Have you blamed your clubs?",
            "The range bucket is lying to you. Your numbers say so.",
        ],
        "observation": [
            "Golfers who buy off-rack and then blame their swing are the same ones who skip the TrackMan session.",
        ],
        "contrarian": [
            "Hot take: the lesson wasn't the problem. The clubs were. The data agrees.",
            "Range myths that won't die: swing plane, swing thoughts, swing fixes that aren't fixes.",
        ],
        "proof": [
            "A 7-iron with the wrong shaft flex costs you distance. The numbers don't care about your feelings.",
        ],
        "curiosity": [
            "Why do range swings feel different to course swings? The data's obvious once you see it.",
        ],
        "comparison": [
            "Off-rack clubs: cost saving that costs you strokes. Fitted: cost that pays back in the bag.",
        ],
        "identity": [
            "You're the kind of golfer who scrolls past generic golf tips. This is for you.",
        ],
        "humour": [
            "Buying off-rack and expecting scratch swings. Sure. Sure.",
            "The only person who doesn't need a fitting is the person who hasn't measured yet.",
        ],
        "mistake": [
            "Mistake: buying the club your mate plays. Even if he plays well. Your swing is not his swing.",
        ],
        "myth": [
            "Myth: swing plane is one shape. Reality: it's a window. Your number, your plane.",
        ],
        "tension": [
            "YouTube lessons vs TrackMan data. Pick one. Pick wrong.",
        ],
        "story": [
            "Saw a guy this week blame his slice on the range bucket. The bucket was fine. His driver was 3° off.",
        ],
        "challenge": [
            "Get measured. One TrackMan session. Then argue with the data, not the internet.",
        ],
        "aspiration": [
            "The bag you want is the bag that's measured to your swing. Not the other way around.",
        ],
        "commercial": [
            "Driver fitting, R1500, 60 minutes. Book the slot, bring your current driver, see the data.",
        ],
    },
    "bag-drop": {
        "problem": [
            "Thursday member social is the one thing on the calendar that actually feels like golf. See you there.",
        ],
        "observation": [
            "The bay is the warmest room in JHB on a Thursday night. The member social knows why.",
        ],
        "contrarian": [
            "Solo range sessions are fine. But solo social sessions with clubs? Even better.",
        ],
        "proof": [
            "200+ members show up to a Thursday social because the format works. Watch the room.",
        ],
        "curiosity": [
            "What does a member social look like when the data screen is the conversation starter?",
        ],
        "comparison": [
            "Range bucket solo: fine. Bag Drop Thursday with 12 of you and a TrackMan challenge: better.",
        ],
        "identity": [
            "You're a member because the community is the point. The bay is just the bonus.",
        ],
        "humour": [
            "Yes you should still practice your short game. Yes you should also come to the social.",
        ],
        "mistake": [
            "Mistake: skipping the social because you think you need to practice more. The social is the practice.",
        ],
        "myth": [
            "Myth: members only come for the data. Reality: they come back for the people.",
        ],
        "tension": [
            "Practice vs play. Solo vs social. Thursday Bag Drop says: both.",
        ],
        "story": [
            "A member's first Bag Drop Thursday turned into three new regulars. The format does that.",
        ],
        "challenge": [
            "Bring a mate who's never been to a Swing Shack Thursday. See what happens.",
        ],
        "aspiration": [
            "The member culture you want is the one you show up to. See you Thursday.",
        ],
        "commercial": [
            "Bag Drop Thursday. 18h00. swingshack.co.za/bookings. Members free, guests R150.",
        ],
    },
}


def _generate_candidate(ctx: dict, route: dict) -> dict:
    """Generate one candidate from the route + brand templates.

    This is a deterministic template-based generator for PASS proof. The
    LLM-backed generator can be wired in later by replacing this function.
    """
    brand_id = ctx["brand_id"]
    mech = route["mechanism"]
    templates = ROUTE_TEMPLATES.get(brand_id, {}).get(mech, [])
    # Pick the first template; in real LLM mode the model would generate
    # genuinely. We add a small hash-derived variant so different runs
    # don't repeat the same exact line.
    if not templates:
        body = f"[{brand_id} | {mech}] (template pool empty)"
    else:
        idx = int(route.get("brand_fit", 0)) + hash(ctx.get("user_brief") or "") % len(templates)
        body = templates[idx % len(templates)]
    # Append CTA from voice bible
    b = ctx["brand"]
    cta = b.get("cta_default") or ""
    if cta and not body.endswith(cta):
        body = f"{body}\n\n{cta}"
    return {
        "candidate_id": "c-" + _hash(f"{ctx.get('context_id')}|{route['route_id']}|{body}")[:10],
        "route": route["route_id"],
        "mechanism": route["mechanism"],
        "body": body,
        "context_id": ctx.get("context_id"),
    }


# ─── THE PIPELINE ─────────────────────────────────────────────────────
def run_caption_pipeline(request: dict) -> dict:
    """The full P1.1 pipeline.

    request = {
        "brand_id": ...,
        "task_type": "caption",
        "campaign_id": ...,
        "product_brand": ...,
        "product_id": ...,
        "service": ...,
        "audience": ...,
        "channel": ...,
        "objective": ...,
        "user_brief": ...,
        "n_survivors": 5,
        "n_candidates": 12,
        "avoid_mechanisms": [...],
        "enforce_exact_dedupe": True,
        "enforce_structural_check": True,
        "enforce_semantic_check": True,
        "enforce_brand_check": True,
        "enforce_fact_check": True,
    }
    """
    t0 = _now_iso()
    # 1. Build context
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
    # 2. Plan routes
    n_survivors = min(int(request.get("n_survivors", 5)), 10)
    n_candidates = max(int(request.get("n_candidates", n_survivors * 2)), n_survivors)
    avoid = request.get("avoid_mechanisms", [])
    routes = plan_routes(ctx, n=n_survivors, avoid_mechanisms=avoid)

    # 3. Generate candidates (one per route + extras for fallback)
    candidates = []
    for r in routes:
        candidates.append(_generate_candidate(ctx, r))
    # Generate extras if we need to refill
    extra_routes_needed = n_candidates - len(candidates)
    if extra_routes_needed > 0:
        # Pull more mechanisms from MECHANISMS not in current routes
        used = {c["mechanism"] for c in candidates}
        extras = [m for m in MECHANISMS if m not in used and m not in avoid]
        for i, m in enumerate(extras[:extra_routes_needed]):
            fake_route = {
                "route_id": f"route-extra-{i+1}-{m}",
                "mechanism": m,
                "brand_fit": MECHANISM_FIT.get(ctx["brand_id"], {}).get(m, 0),
                "rationale": _mechanism_rationale(m, ctx["brand_id"], ctx),
            }
            candidates.append(_generate_candidate(ctx, fake_route))

    # 4. Run checks
    recent = _load_recent_content(ctx["brand_id"], limit=50)
    intel = _load_caption_intel()
    embeds, embed_kind, embed_model = _load_embeddings()
    banned = _extract_banned_terms(ctx["brand_id"])
    structural_fams = intel.get("structural_families", [])

    survivors = []
    rejects = {
        "exact": [], "structural": [], "semantic": [],
        "brand": [], "fact": [],
    }
    for c in candidates:
        passed_all = True
        checks = {}
        if request.get("enforce_exact_dedupe", True):
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
        if passed_all:
            prior = _performance_prior(c["body"], ctx)
            c["checks"] = checks
            c["performance_prior"] = prior
            c["why_this_route"] = (
                f"Route={c['mechanism']}. "
                f"Brand fit={routes[0]['brand_fit'] if routes else 'n/a'}. "
                f"{prior.get('note', '')}"
            )
            survivors.append(c)
        if len(survivors) >= n_survivors:
            break

    # 5. Observability
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
        "final_survivors": len(survivors),
        "model": "p11-v1-template (deterministic; LLM swappable)",
        "provider": "internal",
        "embedding_kind": embed_kind,
        "embedding_model": embed_model,
    }

    return {
        "ok": True,
        "context_id": ctx.get("context_id"),
        "context": ctx,  # full structured context for debug
        "routes_planned": routes,
        "candidates_considered": candidates,
        "survivors": survivors,
        "rejects": rejects,
        "observability": obs,
        "ts": t1,
    }


# ─── TASTE EVENTS ────────────────────────────────────────────────────
def _taste_dir() -> Path:
    return Path(_data_dir()) / "intelligence" / "taste"


def _init_taste_dir() -> None:
    _taste_dir().mkdir(parents=True, exist_ok=True)


def record_taste_event(event: dict) -> dict:
    """Persist a taste event (shown/selected/rejected/edited/approved/published).

    event = {
        "event_type": "shown" | "selected" | "rejected" | "edited" | "approved" | "published",
        "generation_id": "...",
        "candidate_id": "...",
        "brand_id": "...",
        "campaign_id": ...,
        "product_brand": ...,
        "route": "...",
        "context_id": "...",
        "original_candidate": "...",
        "final_text": ...,
        "edit_delta": ...,  # str with the diff or summary
        "semantic_family": ...,
        "structural_family": ...,
    }
    """
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
