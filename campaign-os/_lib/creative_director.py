"""
creative_director.py — Brand-aware prompt compiler + reference-led creation.

The Campaign OS is the Creative Director. Krea is the engine.
This module is the layer in between:

  - Retrieves the brand context (visual philosophy, palette, archetypes,
    typography, voice, negative-prompt rules)
  - Retrieves the reference DNA (if a reference image is supplied)
  - Retrieves the product/service info (if a product is supplied)
  - Composes a structured MASTER PROMPT with explicit sections:
        1. JOB         — what is being created
        2. BRAND       — only the relevant brand character
        3. SUBJECT     — who/what is the hero
        4. REFERENCE   — what should be taken from references
        5. PRESERVE    — what must NOT change (product fidelity)
        6. COMPOSITION — camera/framing/layout
        7. ENVIRONMENT
        8. LIGHTING
        9. MATERIAL/TEXTURE
        10. HUMAN DIRECTION (if relevant)
        11. CAMERA
        12. OUTPUT STYLE
        13. FORMAT
        14. BRAND EXCLUSIONS
        15. MODEL-SPECIFIC INSTRUCTIONS

  - Composes a NEGATIVE / PRESERVATION prompt from:
        - Global quality rules (no distorted hands, no fake logos, etc.)
        - Brand rules (what the brand never looks like)
        - Product rules (what must NOT change)
        - Reference rules (don't copy exact pixels)
        - Model-specific failure modes

  - Chooses a model recommendation (AUTO) when the caller asks for
    one, based on the job's capability requirements (text-to-image,
    product-fidelity, photorealism, illustration, typography, speed, cost).

Built 2026-08-31 to satisfy user directive sections 5, 6, 7, 8, 9, 10,
11, 19. All output is JSON-serialisable so the UI can render the
"show me the prompt + negative before generation" view.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger("campaign_os.creative_director")

# ── Capability matrix for Krea model selection ───────────────────────
# Each capability maps a job requirement to a model property.
# Updated 2026-08-31 from the Krea model schema cache.
# Capability matrix. Higher = better. The router scores against requirements
# weighted by JOB TYPE (apparel / equipment / poster / video).
_MODEL_CAPABILITIES = {
    # image models — 'verified: True' means Krea's MCP accepts generate_image calls.
    # Live-verified 2026-08-31. Models without verified: True returned
    # 'Unsupported image model' from Krea's upstream.
    "bfl/flux-1-dev":           {"category": "image", "fidelity": 0.7, "photorealism": 0.8, "speed": 0.5, "typography": 0.3, "ref_image": False, "edit": False, "verified": False, "material": 0.7, "lighting": 0.7, "composition": 0.7, "human": 0.5},
    "bfl/flux-1.1-pro":         {"category": "image", "fidelity": 0.85, "photorealism": 0.85, "speed": 0.7, "typography": 0.4, "ref_image": False, "edit": False, "verified": True, "material": 0.8, "lighting": 0.85, "composition": 0.85, "human": 0.75},
    "bfl/flux-1.1-pro-ultra":   {"category": "image", "fidelity": 0.9, "photorealism": 0.92, "speed": 0.5, "typography": 0.5, "ref_image": False, "edit": False, "verified": True, "material": 0.9, "lighting": 0.9, "composition": 0.9, "human": 0.85},
    "bfl/flux-1-kontext-dev":   {"category": "image", "fidelity": 0.9, "photorealism": 0.7, "speed": 0.5, "typography": 0.4, "ref_image": False, "edit": True, "edit_only": True, "verified": True, "material": 0.7, "lighting": 0.7, "composition": 0.75, "human": 0.65},
    "xai/grok-imagine-2":       {"category": "image", "fidelity": 0.7, "photorealism": 0.75, "speed": 0.8, "typography": 0.4, "ref_image": False, "verified": False, "material": 0.7, "lighting": 0.7, "composition": 0.7, "human": 0.6},
    "openai/gpt-image-2":       {"category": "image", "fidelity": 0.8, "photorealism": 0.85, "speed": 0.6, "typography": 0.85, "ref_image": True, "edit": True, "verified": False, "material": 0.8, "lighting": 0.85, "composition": 0.85, "human": 0.8},
    "openai/gpt-image":         {"category": "image", "fidelity": 0.75, "photorealism": 0.8, "speed": 0.6, "typography": 0.8, "ref_image": True, "edit": True, "verified": False, "material": 0.75, "lighting": 0.8, "composition": 0.8, "human": 0.75},
    "ideogram/ideogram-3":      {"category": "image", "fidelity": 0.75, "photorealism": 0.7, "speed": 0.7, "typography": 0.95, "ref_image": True, "verified": True, "material": 0.7, "lighting": 0.75, "composition": 0.8, "human": 0.65},
    "black-forest-labs/flux-3-video": {"category": "video", "fidelity": 0.85, "photorealism": 0.85, "speed": 0.4, "duration_max": 15, "ref_image": True},
    "bytedance/seedance-2":     {"category": "video", "fidelity": 0.85, "photorealism": 0.8, "speed": 0.6, "duration_max": 15, "ref_image": True, "audio": True},
    "bytedance/seedance-2-fast": {"category": "video", "fidelity": 0.8, "photorealism": 0.75, "speed": 0.85, "duration_max": 15, "ref_image": True, "audio": True},
    "bytedance/seedance-2-5":   {"category": "video", "fidelity": 0.85, "photorealism": 0.85, "speed": 0.5, "duration_max": 15, "ref_image": True, "audio": True},
    "kling/kling-3.0":          {"category": "video", "fidelity": 0.8, "photorealism": 0.85, "speed": 0.5, "duration_max": 10, "ref_image": True, "audio": False},
    "kling/kling-1":            {"category": "video", "fidelity": 0.75, "photorealism": 0.8, "speed": 0.6, "duration_max": 10, "ref_image": False},
    "minimax/hailuo-2.3":       {"category": "video", "fidelity": 0.8, "photorealism": 0.85, "speed": 0.6, "duration_max": 10, "ref_image": True},
    "google/gemini-omni-flash": {"category": "video", "fidelity": 0.75, "photorealism": 0.8, "speed": 0.8, "duration_max": 8, "ref_image": True},
    "xai/grok-video":           {"category": "video", "fidelity": 0.7, "photorealism": 0.75, "speed": 0.7, "duration_max": 10, "ref_image": False},
    "google/gemini-2.5-flash-image": {"category": "image", "fidelity": 0.75, "photorealism": 0.8, "speed": 0.9, "typography": 0.6, "ref_image": True, "edit": True, "material": 0.75, "lighting": 0.8, "composition": 0.8, "human": 0.7},
    "google/gemini-3-pro-image": {"category": "image", "fidelity": 0.85, "photorealism": 0.9, "speed": 0.5, "typography": 0.7, "ref_image": True, "edit": True, "material": 0.85, "lighting": 0.9, "composition": 0.9, "human": 0.85},
}


# ── Global quality negatives — apply to EVERY generation ────────────
GLOBAL_NEGATIVES = [
    "no distorted hands", "no extra fingers", "no malformed anatomy",
    "no duplicated objects", "no warped perspective", "no text in the image",
    "no fake logos", "no AI-hallucinated brand names", "no watermarks",
    "no garbled text", "no artificial plastic skin", "no impossible reflections",
    "no blown-out highlights", "no crushed shadows without detail",
]


# ── Golf-specific negatives ────────────────────────────────────────
GOLF_NEGATIVES = [
    "no bent golf shaft", "no warped club head", "no incorrect club face angle",
    "no missing grip", "no fake brand markings", "no imaginary brand names on equipment",
    "no club without a hosel", "no grip wrapped over a the wrong way",
    "no missing club markings", "no overlapping golf balls", "no floating ball",
    "no logo drift", "no spelled-wrong brand name", "no half-rendered club face",
]


# ── Brand-specific exclusions (filled per brand) ───────────────────
BRAND_EXCLUSIONS = {
    "swing-shack": [
        "no generic luxury aesthetic", "no neon", "no stock-photo golf",
        "no cliche country club", "no fake trackman HUD", "no trophy shots",
        "no cart-path-only", "no all-white 'luxury minimal' aesthetic",
        "no amateur studio backdrops", "no AI-generated faces",
    ],
    "stick": [
        "no luxury aesthetic", "no soft pastel", "no editorial family photography",
        "no sentimentality", "no stadium-style hype", "no mockery",
        "no golf-cliché", "no punching at the reader", "no fitness-magazine colour grading",
    ],
    "bag-drop": [
        "no unboxing luxury", "no pristine show-room", "no fake scarcity language",
        "no stock-photo thrift", "no thrift-store poverty aesthetic",
        "no bargain-bin language", "no 'cheap deals' framing",
    ],
}


_PROMPT_MIN_CHARS = 400
_PROMPT_MAX_CHARS = 1200
_SECTION_ORDER = (
    "JOB",
    "BRAND",
    "SUBJECT",
    "REFERENCE",
    "PRODUCT",
    "COMPOSITION",
    "LIGHTING",
    "CAMERA",
    "OUTPUT STYLE",
    "NEGATIVE",
)
_OUTPUT_STYLE_DEFAULT = (
    "photograph, no text, no logo, no watermark, no UI"
)


def compose_prompt(
    *,
    brand_id: str,
    job: str,
    subject: Optional[str] = None,
    reference_dna: Optional[dict] = None,
    product_service_item: Optional[dict] = None,
    composition: Optional[Dict[str, str]] = None,
    environment: Optional[str] = None,
    lighting: Optional[str] = None,
    material_texture: Optional[str] = None,
    human_direction: Optional[str] = None,
    camera: Optional[str] = None,
    output_style: Optional[str] = None,
    format_aspect: Optional[str] = None,
    angle: Optional[str] = None,
    pillar_name: Optional[str] = None,
    calendar_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Compose a structured master prompt + negative from brand context.

    Returns a dict with:
      master_prompt : str      — the composed prompt (sections separated)
      negative_prompt : str    — the composed negative
      sections : list[dict]    — each labelled section, for the UI
      model_routing : dict     — recommended model + reasoning
      brand_id : str
    """
    # 1) Brand context — read the bible + palette + archetypes
    brand_ctx = _load_brand_context(brand_id)

    sections: list[dict[str, str]] = []

    if job and job.strip():
        sections.append({"key": "JOB", "content": f"You are creating: {job.strip()}"})

    brand_block = _build_brand_block(brand_ctx, brand_id)
    if brand_block.strip():
        sections.append({"key": "BRAND", "content": brand_block})

    subject_block = _build_subject_block(
        subject=subject,
        angle=angle,
        pillar_name=pillar_name,
        calendar_title=calendar_title,
        brand_ctx=brand_ctx,
        human_direction=human_direction,
        environment=environment,
        material_texture=material_texture,
    )
    if subject_block.strip():
        sections.append({"key": "SUBJECT", "content": subject_block})

    if reference_dna:
        ref_block = _build_reference_block(reference_dna)
        if ref_block.strip():
            sections.append({"key": "REFERENCE", "content": ref_block})

    if product_service_item:
        product_block = build_preserve_block(product_service_item)
        if product_block.strip():
            sections.append({"key": "PRODUCT", "content": product_block})

    comp_content = ""
    if composition:
        comp_content = "; ".join(f"{k}: {v}" for k, v in composition.items() if v)
    if not comp_content:
        comp_content = _default_composition(brand_ctx)
    if comp_content.strip():
        sections.append({"key": "COMPOSITION", "content": comp_content})

    light_content = (lighting or "").strip() or _default_lighting(brand_ctx)
    if light_content:
        sections.append({"key": "LIGHTING", "content": light_content})

    if camera and camera.strip():
        sections.append({"key": "CAMERA", "content": camera.strip()})

    out_style = (output_style or _OUTPUT_STYLE_DEFAULT).strip()
    sections.append({"key": "OUTPUT STYLE", "content": out_style})

    negative_prompt = build_negative_prompt(
        brand_id=brand_id,
        reference_dna=reference_dna,
        product_service_item=product_service_item,
        brand_ctx=brand_ctx,
    )
    if negative_prompt.strip():
        sections.append({"key": "NEGATIVE", "content": negative_prompt})

    sections = _order_sections(sections)
    master_prompt, sections = _fit_master_prompt_length(sections, brand_ctx)

    # Model routing — pick based on the job's capability requirements
    requirements = _infer_requirements(
        job=job,
        reference_dna=reference_dna,
        product_service_item=product_service_item,
        format_aspect=format_aspect,
    )
    routing = recommend_model(requirements)

    return {
        "brand_id": brand_id,
        "master_prompt": master_prompt,
        "negative_prompt": negative_prompt,
        "sections": sections,
        "model_routing": routing,
        "requirements": requirements,
    }


def build_preserve_block(product_service_item: dict) -> str:
    """Generate the PRESERVE block for a product.

    Used to tell the AI: this product's geometry, color, material,
    proportions, model details, visible markings, handedness, and
    logo placement must not change.
    """
    name = product_service_item.get("name", "")
    category = product_service_item.get("category", "")
    description = product_service_item.get("description", "")
    rules = [
        "PRESERVE EXACTLY (do not modify):",
        "- product geometry: silhouette, head shape, sole, hosel",
        "- product colorway: every accent, line, finish",
        "- material: every visible surface (steel, carbon, rubber, polymer)",
        "- proportions: scale relative to other reference products",
        "- model details: vents, ports, screws, weighting, badge placement",
        "- visible markings: loft, brand stamp, serial number",
        "- correct handedness: right-hand / left-hand orientation",
        "- logo placement: every visible logo in its correct position",
        "- product branding: every word/mark on the product must remain",
        "",
        "If the supplied reference image does not match the product",
        "description, ERROR toward the reference image (which is canonical).",
    ]
    if name:
        rules.insert(0, f"Product hero: {name} ({category})")
    if description:
        rules.insert(1, f"Description: {description[:300]}")
    return "\n".join(rules)


def build_negative_prompt(
    *,
    brand_id: str,
    reference_dna: Optional[dict] = None,
    product_service_item: Optional[dict] = None,
    brand_ctx: Optional[dict] = None,
) -> str:
    """Compose the negative prompt from global + brand + product + reference rules.

    Most Krea chat-completion image models don't have a separate
    negative_prompt field — they consume it as part of the user
    message. We return a clean comma-separated list the caller can
    inject wherever it fits.
    """
    parts = list(GLOBAL_NEGATIVES) + list(GOLF_NEGATIVES)
    parts.extend(BRAND_EXCLUSIONS.get(brand_id, []))
    bible = (brand_ctx or {}).get("bible") or {}
    for item in bible.get("anti_patterns") or bible.get("negative_prompts") or []:
        if isinstance(item, str) and item.strip():
            parts.append(item.strip())
    if reference_dna:
        parts.append("do not copy the exact reference pixel-for-pixel")
        parts.append("do not reuse the exact same composition as the reference")
    if product_service_item:
        parts.extend([
            "do not redesign the product",
            "do not alter the logo",
            "do not change the product colour",
            "do not invent product markings",
            "do not change the product's model designation",
            "do not change handedness",
        ])
    return ", ".join(parts)


def recommend_model(requirements: Dict[str, Any]) -> Dict[str, Any]:
    """Score available models against the job's capability requirements.

    Job-type-aware weights (per user directive PHASE L-2):
      APPAREL (Style That Belongs / Fabric / Lifestyle):
        photorealism 0.25 + material 0.20 + lighting 0.15 +
        human 0.10 + composition 0.10 + fidelity 0.15 + speed 0.05
        typography = IGNORED (overlay layer adds headline + CTA)

      EQUIPMENT (Fit First / Geometry / Material):
        fidelity 0.40 + material 0.25 + photorealism 0.15 +
        lighting 0.10 + composition 0.10
        typography = IGNORED

      DESIGNED POSTER (where AI renders the headline + CTA itself):
        typography 0.40 + composition 0.25 + speed 0.20 +
        fidelity 0.15

      DEFAULT (no job type):
        fidelity 0.30 + photorealism 0.25 + speed 0.20 +
        typography 0.10 + composition 0.15

    ref_image: +0.15 (only counts if model supports it)
    edit_only: -0.50 (heavily penalised for text-to-image jobs)
    """
    category = requirements.get("category", "image")
    job_type = requirements.get("job_type", "default")
    overlay = requirements.get("overlay", True)  # whether deterministic overlay adds text

    # Build weight profile
    if job_type == "apparel":
        weights = {
            "fidelity": 0.15, "photorealism": 0.25, "material": 0.20,
            "lighting": 0.15, "human": 0.10, "composition": 0.10,
            "speed": 0.05, "typography": 0.0,
        }
    elif job_type == "equipment":
        weights = {
            "fidelity": 0.40, "photorealism": 0.15, "material": 0.25,
            "lighting": 0.10, "human": 0.0, "composition": 0.10,
            "speed": 0.0, "typography": 0.0,
        }
    elif job_type == "poster":
        weights = {
            "fidelity": 0.15, "photorealism": 0.0, "material": 0.0,
            "lighting": 0.0, "human": 0.0, "composition": 0.25,
            "speed": 0.20, "typography": 0.40,
        }
    else:
        weights = {
            "fidelity": 0.30, "photorealism": 0.25, "material": 0.0,
            "lighting": 0.0, "human": 0.0, "composition": 0.15,
            "speed": 0.20, "typography": 0.10,
        }

    scored = {}
    for mid, caps in _MODEL_CAPABILITIES.items():
        if caps.get("category") != category:
            continue
        score = 0.0
        reasons = []
        # Always-on base
        score += caps.get("fidelity", 0.5) * weights["fidelity"]
        score += caps.get("photorealism", 0.5) * weights["photorealism"]
        score += caps.get("material", 0.5) * weights["material"]
        score += caps.get("lighting", 0.5) * weights["lighting"]
        score += caps.get("human", 0.5) * weights["human"]
        score += caps.get("composition", 0.5) * weights["composition"]
        score += caps.get("speed", 0.5) * weights["speed"]
        if weights["typography"] > 0:
            score += caps.get("typography", 0.3) * weights["typography"]

        # Only flag typography dimension when:
        # - job_type is "poster" (designed, AI renders text) OR
        # - overlay is explicitly False (no deterministic overlay will be added)
        if requirements.get("typography") and not overlay and weights["typography"] == 0:
            # User requested text-rendering but overlay is on — penalise the
            # 'typography' capability need since the AI won't be expected to render text.
            pass

        if requirements.get("cinematic") and category == "video":
            score += 0.10
        if requirements.get("illustration"):
            score += 0.05
        if requirements.get("needs_ref_image"):
            if caps.get("ref_image"):
                score += 0.15
                reasons.append("supports reference images")
        if requirements.get("needs_edit"):
            if caps.get("edit"):
                score += 0.10
                reasons.append("supports edit mode")
        # NEW (2026-08-31): penalise edit-only models for text-to-image jobs.
        # Verified: bfl/flux-1-kontext-dev returned 400 'Flux Kontext requires
        # an input image' when called via generate_image. Edit-only models
        # belong on the edit endpoint, not the generate endpoint.
        if caps.get("edit_only"):
            score -= 0.5
            reasons.append("edit-only — not suitable for text-to-image")
        # NEW (2026-08-31): penalise unverified models. Verified 2026-08-31 that
        # google/gemini-3-pro-image returned 'Unsupported image model' from Krea's
        # upstream — it's listed by list_models but not callable.
        if not caps.get("verified", False):
            score -= 1.0
            reasons.append("unverified — Krea upstream doesn't accept")
        score += 0.10  # baseline
        scored[mid] = (score, reasons)

    if not scored:
        return {
            "recommended": "bfl/flux-1.1-pro",
            "why": ["no model matched; defaulting to a high-fidelity image model"],
            "alternative": None,
            "scores": {},
        }

    sorted_models = sorted(scored.items(), key=lambda x: -x[1][0])
    recommended, (top_score, top_reasons) = sorted_models[0]
    alternative = sorted_models[1][0] if len(sorted_models) > 1 else None
    return {
        "recommended": recommended,
        "why": top_reasons or [f"highest score {top_score:.2f} for the inferred requirements"],
        "alternative": alternative,
        "scores": {m: round(s, 3) for m, (s, _) in scored.items()},
    }


def _infer_requirements(
    *,
    job: str,
    reference_dna: Optional[dict],
    product_service_item: Optional[dict],
    format_aspect: Optional[str],
    job_type: Optional[str] = None,
    overlay: bool = True,
) -> Dict[str, Any]:
    """Map a job description to the capabilities required.

    Returns a dict that `recommend_model` consumes to score models:
      category : 'image' | 'video'
      job_type : 'apparel' | 'equipment' | 'poster' | 'default'
      overlay  : whether the deterministic brand-overlay layer will add
                 the headline + CTA + logo on top of the AI visual
      product_fidelity, photorealism, speed, typography, ...
    """
    job_low = (job or "").lower()
    is_video = any(w in job_low for w in (
        "video", "reel", "clip", "motion", "animate",
        "cinematic", "8-second", "8 second",
    ))

    # Auto-detect job_type from product category if not explicit
    if not job_type:
        cat = (product_service_item or {}).get("category", "").lower()
        name = (product_service_item or {}).get("name", "").lower()
        if any(w in cat + " " + name for w in ("pant", "polo", "shirt", "tee", "apparel", "shoe", "cap", "hat", "umbrella", "hoodie", "jacket")):
            job_type = "apparel"
        elif any(w in cat + " " + name for w in ("iron", "wedge", "wood", "driver", "putter", "shaft", "grip", "ball", "club", "bag", "equipment")):
            job_type = "equipment"
        elif any(w in job_low for w in ("poster", "flyer", "banner", "infographic", "advert", "logo reveal")):
            job_type = "poster"
        else:
            job_type = "default"

    # When overlay is ON, the AI doesn't need to render text — typography
    # capability is irrelevant for model selection. The deterministic overlay
    # adds the real brand headline + CTA + logo afterwards.
    typography_needed = (
        any(w in job_low for w in ("text", "headline", "title", "wordmark", "typography"))
        or any(w in job_low for w in ("logo", "design"))  # only if AI is rendering the logo
    ) and not overlay

    reqs: Dict[str, Any] = {
        "category": "video" if is_video else "image",
        "job_type": job_type,
        "overlay": overlay,
        "product_fidelity": bool(product_service_item),
        "photorealism": any(w in job_low for w in (
            "photo", "realistic", "real", "lifestyle",
            "studio", "product shot", "editorial",
        )) or job_type in ("apparel", "equipment"),
        "speed": any(w in job_low for w in (
            "quick", "fast", "social", "story",
        )),
        "typography": typography_needed,
        "illustration": any(w in job_low for w in (
            "illustrat", "drawing", "cartoon", "sketch",
            "concept art", "art",
        )),
        "cinematic": any(w in job_low for w in (
            "cinematic", "motion", "8-second", "8 second",
            "film", "movie",
        )),
        "needs_ref_image": bool(reference_dna),
        "needs_edit": any(w in job_low for w in (
            "edit", "restyle", "swap", "replace",
            "recolour", "background swap",
        )),
    }
    return reqs


# ── Brand context loader (filesystem, read-only) ────────────────────
def _data_root() -> Path:
    candidates: list[Path] = []
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    if bundled:
        candidates.append(Path(bundled))
    candidates.append(Path(os.environ.get("DATA_DIR") or "/data/campaign-os"))
    repo_data = Path(__file__).resolve().parents[2] / "data"
    candidates.append(repo_data)
    for base in candidates:
        if base.exists():
            return base
    return candidates[0]


def _load_brand_context(brand_id: str) -> dict:
    """Load brand bible + palette from data/brand-directory (no placeholder skip)."""
    root = _data_root() / "brand-directory" / brand_id
    ctx: dict = {"brand_id": brand_id, "bible": {}, "palette": {}, "archetypes": []}
    bible_path = root / "bible-visual.json"
    if bible_path.is_file():
        try:
            ctx["bible"] = json.loads(bible_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    palette_path = root / "palette" / "brand.json"
    if palette_path.is_file():
        try:
            raw = json.loads(palette_path.read_text(encoding="utf-8"))
            ctx["palette"] = raw.get("palette", raw) if isinstance(raw, dict) else {}
        except Exception:
            pass
    return ctx


def _build_brand_block(brand_ctx: dict, brand_id: str) -> str:
    """Construct the BRAND section of the prompt from bible + palette."""
    parts = []
    bible = brand_ctx.get("bible", {})
    palette = brand_ctx.get("palette", {})
    phil = bible.get("philosophy") or bible.get("visual_philosophy") or ""
    if phil:
        parts.append(f"Philosophy: {phil}")
    rules = bible.get("composition_rules") or []
    rule_lines = [r for r in rules if isinstance(r, str) and r.strip()]
    if rule_lines:
        parts.append("Composition rules: " + "; ".join(rule_lines[:6]))
    people = bible.get("people_policy")
    if isinstance(people, str) and people.strip():
        parts.append(f"People: {people.strip()}")
    text_pol = bible.get("text_policy")
    if isinstance(text_pol, str) and text_pol.strip():
        parts.append(f"Text: {text_pol.strip()}")
    kw = bible.get("look_and_feel_keywords", [])
    kw_real = [k for k in kw if not str(k).lower().startswith("todo")]
    if kw_real:
        parts.append(f"Look + feel: {', '.join(kw_real[:10])}")
    # palette
    colors = []
    if isinstance(palette, dict):
        for k, v in palette.items():
            if isinstance(v, dict) and "hex" in v:
                colors.append(f"{v.get('name', k)} {v['hex']}")
            elif isinstance(v, str) and v.startswith("#"):
                colors.append(v)
    if colors:
        parts.append(f"Colour anchor: {', '.join(colors[:6])}")
    if not parts:
        parts.append(f"Brand: {brand_id} (canonical voice + visuals per brand bible)")
    return "\n".join(parts)


def _default_composition(brand_ctx: dict) -> str:
    """Default composition when caller didn't specify one."""
    return "Single subject in lower-third; subject area ≤ 55% of frame; generous negative space for headline; rule-of-thirds alignment"


def _default_lighting(brand_ctx: dict) -> str:
    """Default lighting when caller didn't specify one."""
    palette = brand_ctx.get("palette", {})
    accent = palette.get("accent", {}).get("name", "warm").lower()
    return (
        f"Moody, low-key studio lighting with {accent} accent pools. "
        "Single overhead light or soft directional side-light. "
        "No flat studio white, no harsh blown highlights."
    )


def _build_subject_block(
    *,
    subject: Optional[str],
    angle: Optional[str],
    pillar_name: Optional[str],
    calendar_title: Optional[str],
    brand_ctx: dict,
    human_direction: Optional[str],
    environment: Optional[str],
    material_texture: Optional[str],
) -> str:
    """Expand calendar angle into who / action / gear / setting."""
    lines: list[str] = []
    if subject and subject.strip():
        lines.append(f"Hero: {subject.strip()}")
    who = _infer_subject_field(angle, ("golfer", "coach", "member", "player", "fitter", "instructor"))
    action = _infer_subject_field(angle, ("mid-swing", "swing", "session", "fitting", "coaching", "celebrating"))
    gear = _infer_subject_field(angle, ("TrackMan", "driver", "iron", "club", "monitor", "simulator", "bay"))
    setting = _infer_subject_field(angle, ("indoor", "studio", "bay", "sim", "Johannesburg", "venue"))
    if calendar_title:
        lines.append(f"Moment: {calendar_title.strip()}")
    if pillar_name:
        lines.append(f"Pillar: {pillar_name.strip()}")
    if angle and angle.strip():
        lines.append(f"Angle: {angle.strip()}")
    if who:
        lines.append(f"Who: {who}")
    if action:
        lines.append(f"Action: {action}")
    if gear:
        lines.append(f"Gear: {gear}")
    if setting:
        lines.append(f"Setting: {setting}")
    if environment and environment.strip():
        lines.append(f"Environment: {environment.strip()}")
    if material_texture and material_texture.strip():
        lines.append(f"Materials: {material_texture.strip()}")
    if human_direction and human_direction.strip():
        lines.append(f"Human direction: {human_direction.strip()}")
    bible = brand_ctx.get("bible") or {}
    bias = bible.get("subject_bias") or {}
    toward = bias.get("lean_toward") or []
    if isinstance(toward, list) and toward:
        lines.append("Lean toward: " + ", ".join(str(t) for t in toward[:4]))
    return "\n".join(lines)


def _infer_subject_field(angle: Optional[str], keywords: tuple[str, ...]) -> str:
    if not angle:
        return ""
    low = angle.lower()
    hits = [k for k in keywords if k.lower() in low]
    if hits:
        return ", ".join(hits[:4])
    return ""


def _order_sections(sections: list[dict[str, str]]) -> list[dict[str, str]]:
    order_index = {k: i for i, k in enumerate(_SECTION_ORDER)}
    return sorted(sections, key=lambda s: order_index.get(s["key"], 99))


def _assemble_master_prompt(sections: list[dict[str, str]]) -> str:
    blocks = []
    for sec in sections:
        content = (sec.get("content") or "").strip()
        if content:
            blocks.append(f"[{sec['key']}]\n{content}")
    return "\n\n".join(blocks)


def _sections_from_master(master_prompt: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for chunk in re.split(r"\n\n(?=\[)", master_prompt.strip()):
        chunk = chunk.strip()
        if not chunk.startswith("["):
            continue
        m = re.match(r"\[([^\]]+)\]\n(.*)", chunk, re.DOTALL)
        if m:
            out.append({"key": m.group(1), "content": m.group(2).strip()})
    return _order_sections(out)


def _fit_master_prompt_length(
    sections: list[dict[str, str]],
    brand_ctx: dict,
) -> tuple[str, list[dict[str, str]]]:
    working = _order_sections([dict(s) for s in sections])

    def _rebuild() -> str:
        return _assemble_master_prompt(working)

    master = _rebuild()

    if len(master) < _PROMPT_MIN_CHARS:
        pad = (
            "35mm prime lens, shallow depth of field, subtle grain, "
            "premium sports campaign framing, overlay-safe margins."
        )
        cam = next((s for s in working if s["key"] == "CAMERA"), None)
        if cam:
            cam["content"] = f"{cam['content']} {pad}".strip()
        else:
            working.append({"key": "CAMERA", "content": pad})
        comp = next((s for s in working if s["key"] == "COMPOSITION"), None)
        if comp:
            comp["content"] = (
                f"{comp['content']} Reserve upper third for headline overlay; "
                "subject in lower two-thirds."
            )
        working = _order_sections(working)
        master = _rebuild()

    trim_targets = ("NEGATIVE", "SUBJECT", "BRAND", "COMPOSITION", "LIGHTING")
    while len(master) > _PROMPT_MAX_CHARS:
        trimmed = False
        for key in trim_targets:
            sec = next((s for s in working if s["key"] == key), None)
            if not sec or len(sec["content"]) <= 80:
                continue
            sec["content"] = sec["content"][: max(80, len(sec["content"]) * 2 // 3)].rstrip(" ,;")
            trimmed = True
            break
        if not trimmed:
            break
        working = _order_sections(working)
        master = _rebuild()

    if len(master) > _PROMPT_MAX_CHARS:
        master = master[:_PROMPT_MAX_CHARS].rstrip()

    return master, working


def _build_reference_block(reference_dna: dict) -> str:
    """Construct the REFERENCE_RELATIONSHIP section from a reference DNA."""
    parts = []
    palette = reference_dna.get("palette", {})
    dominant = palette.get("dominant_colors", [])
    if dominant:
        hexes = [c.get("hex", "") for c in dominant[:5]]
        parts.append(f"Reference colour anchor: {', '.join(hexes)}")
    luminance = palette.get("luminance_bucket")
    if luminance:
        parts.append(f"Reference luminance: {luminance}")
    composition = reference_dna.get("composition", {})
    subj = composition.get("subject_estimate_position")
    if subj:
        parts.append(f"Reference subject position: {subj}")
    orientation = reference_dna.get("orientation")
    if orientation:
        parts.append(f"Reference orientation: {orientation}")
    mood = reference_dna.get("mood")
    if mood:
        parts.append(f"Reference mood: {mood}")
    parts.append("Use the reference as a family aesthetic, NOT a pixel-for-pixel clone.")
    return "\n".join(parts)


# ── Direct API: reference-led creation ──────────────────────────────
def from_reference_and_product(
    *,
    brand_id: str,
    reference_dna: dict,
    product_service_item: dict,
    job: Optional[str] = None,
    format_aspect: str = "1:1",
) -> Dict[str, Any]:
    """Compose the canonical 'make me another one like this' pipeline.

    The reference-led creation flow:
      1. Load brand context
      2. Take reference DNA + product info
      3. Build a prompt that says "in the family of the reference,
         with this exact product"
      4. Build the preserve block
      5. Recommend a model
    Returns the same dict shape as compose_prompt().
    """
    job_default = (
        f"A new creative for the {brand_id} brand, clearly part of "
        f"the same family as the supplied reference, but with this "
        f"specific product as the hero."
    )
    return compose_prompt(
        brand_id=brand_id,
        job=job or job_default,
        subject=product_service_item.get("name", ""),
        reference_dna=reference_dna,
        product_service_item=product_service_item,
        format_aspect=format_aspect,
    )