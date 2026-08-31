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
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger("campaign_os.creative_director")

# ── Capability matrix for Krea model selection ───────────────────────
# Each capability maps a job requirement to a model property.
# Updated 2026-08-31 from the Krea model schema cache.
_MODEL_CAPABILITIES = {
    # image models
    "bfl/flux-1-dev":           {"category": "image", "fidelity": 0.7, "photorealism": 0.8, "speed": 0.5, "typography": 0.3, "ref_image": False},
    "bfl/flux-1.1-pro":         {"category": "image", "fidelity": 0.85, "photorealism": 0.85, "speed": 0.7, "typography": 0.4, "ref_image": False},
    "bfl/flux-1.1-pro-ultra":   {"category": "image", "fidelity": 0.9, "photorealism": 0.9, "speed": 0.5, "typography": 0.5, "ref_image": False},
    "bfl/flux-1-kontext-dev":   {"category": "image", "fidelity": 0.9, "photorealism": 0.7, "speed": 0.5, "typography": 0.4, "ref_image": True, "edit": True},
    "xai/grok-imagine-2":       {"category": "image", "fidelity": 0.7, "photorealism": 0.75, "speed": 0.8, "typography": 0.4, "ref_image": False},
    "openai/gpt-image-2":       {"category": "image", "fidelity": 0.8, "photorealism": 0.85, "speed": 0.6, "typography": 0.85, "ref_image": True, "edit": True},
    "openai/gpt-image":         {"category": "image", "fidelity": 0.75, "photorealism": 0.8, "speed": 0.6, "typography": 0.8, "ref_image": True, "edit": True},
    "ideogram/ideogram-3":      {"category": "image", "fidelity": 0.75, "photorealism": 0.7, "speed": 0.7, "typography": 0.95, "ref_image": True},
    "black-forest-labs/flux-3-video": {"category": "video", "fidelity": 0.85, "photorealism": 0.85, "speed": 0.4, "duration_max": 15, "ref_image": True},
    "bytedance/seedance-2":     {"category": "video", "fidelity": 0.85, "photorealism": 0.8, "speed": 0.6, "duration_max": 15, "ref_image": True, "audio": True},
    "bytedance/seedance-2-fast": {"category": "video", "fidelity": 0.8, "photorealism": 0.75, "speed": 0.85, "duration_max": 15, "ref_image": True, "audio": True},
    "bytedance/seedance-2-5":   {"category": "video", "fidelity": 0.85, "photorealism": 0.85, "speed": 0.5, "duration_max": 15, "ref_image": True, "audio": True},
    "kling/kling-3.0":          {"category": "video", "fidelity": 0.8, "photorealism": 0.85, "speed": 0.5, "duration_max": 10, "ref_image": True, "audio": False},
    "kling/kling-1":            {"category": "video", "fidelity": 0.75, "photorealism": 0.8, "speed": 0.6, "duration_max": 10, "ref_image": False},
    "minimax/hailuo-2.3":       {"category": "video", "fidelity": 0.8, "photorealism": 0.85, "speed": 0.6, "duration_max": 10, "ref_image": True},
    "google/gemini-omni-flash": {"category": "video", "fidelity": 0.75, "photorealism": 0.8, "speed": 0.8, "duration_max": 8, "ref_image": True},
    "xai/grok-video":           {"category": "video", "fidelity": 0.7, "photorealism": 0.75, "speed": 0.7, "duration_max": 10, "ref_image": False},
    "google/gemini-2.5-flash-image": {"category": "image", "fidelity": 0.75, "photorealism": 0.8, "speed": 0.9, "typography": 0.6, "ref_image": True, "edit": True},
    "google/gemini-3-pro-image": {"category": "image", "fidelity": 0.85, "photorealism": 0.9, "speed": 0.5, "typography": 0.7, "ref_image": True, "edit": True},
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

    # 2) Section assembly — each block contributes only if non-empty
    sections = []

    # Section 1: Job
    if job:
        sections.append({"key": "JOB", "content": f"You are creating: {job.strip()}"})
    # Section 2: Brand
    brand_block = _build_brand_block(brand_ctx, brand_id)
    if brand_block:
        sections.append({"key": "BRAND", "content": brand_block})
    # Section 3: Subject
    if subject:
        sections.append({"key": "SUBJECT", "content": f"Hero subject: {subject.strip()}"})
    # Section 4: Reference relationship
    if reference_dna:
        ref_block = _build_reference_block(reference_dna)
        if ref_block:
            sections.append({"key": "REFERENCE_RELATIONSHIP", "content": ref_block})
    # Section 5: Preserve block (product fidelity)
    if product_service_item:
        preserve_block = build_preserve_block(product_service_item)
        sections.append({"key": "PRESERVE", "content": preserve_block})
    # Section 6: Composition
    if composition:
        comp = "; ".join(f"{k}: {v}" for k, v in composition.items() if v)
        if comp:
            sections.append({"key": "COMPOSITION", "content": comp})
    elif not composition:
        sections.append({"key": "COMPOSITION", "content": _default_composition(brand_ctx)})
    # Section 7: Environment
    if environment:
        sections.append({"key": "ENVIRONMENT", "content": environment.strip()})
    # Section 8: Lighting
    if lighting:
        sections.append({"key": "LIGHTING", "content": lighting.strip()})
    else:
        sections.append({"key": "LIGHTING", "content": _default_lighting(brand_ctx)})
    # Section 9: Material/texture
    if material_texture:
        sections.append({"key": "MATERIAL", "content": material_texture.strip()})
    # Section 10: Human direction
    if human_direction:
        sections.append({"key": "HUMAN", "content": human_direction.strip()})
    # Section 11: Camera
    if camera:
        sections.append({"key": "CAMERA", "content": camera.strip()})
    # Section 12: Output style
    if output_style:
        sections.append({"key": "OUTPUT STYLE", "content": output_style.strip()})
    # Section 13: Format
    if format_aspect:
        sections.append({"key": "FORMAT", "content": format_aspect.strip()})

    master_prompt = "\n\n".join(f"[{s['key']}]\n{s['content']}" for s in sections)

    # Build negative prompt
    negative_prompt = build_negative_prompt(
        brand_id=brand_id,
        reference_dna=reference_dna,
        product_service_item=product_service_item,
    )

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
) -> str:
    """Compose the negative prompt from global + brand + product + reference rules.

    Most Krea chat-completion image models don't have a separate
    negative_prompt field — they consume it as part of the user
    message. We return a clean comma-separated list the caller can
    inject wherever it fits.
    """
    parts = list(GLOBAL_NEGATIVES) + list(GOLF_NEGATIVES)
    parts.extend(BRAND_EXCLUSIONS.get(brand_id, []))
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

    Weights:
      product_fidelity  -> fidelity * 0.35
      photorealism      -> photorealism * 0.25
      speed             -> speed * 0.20
      typography        -> typography * 0.20
      cinematic (video) -> 0.10 (always-on for video jobs)
      ref_image needed  -> +0.15 (only counts if model supports it)
      edit needed       -> +0.10 (only counts if model supports edit mode)
      illustration      -> 0.05 if needed (small bonus)

    Returns:
      recommended: model id
      why: list[str]
      alternative: model id
      scores: dict[model_id, score]
    """
    category = requirements.get("category", "image")
    scored = {}
    for mid, caps in _MODEL_CAPABILITIES.items():
        if caps.get("category") != category:
            continue
        score = 0.0
        reasons = []
        if requirements.get("product_fidelity"):
            score += caps.get("fidelity", 0.5) * 0.35
            reasons.append(f"product fidelity (caps.fidelity={caps.get('fidelity', 0.5):.2f})")
        if requirements.get("photorealism"):
            score += caps.get("photorealism", 0.5) * 0.25
            reasons.append(f"photorealism ({caps.get('photorealism', 0.5):.2f})")
        if requirements.get("speed"):
            score += caps.get("speed", 0.5) * 0.20
            reasons.append(f"speed ({caps.get('speed', 0.5):.2f})")
        if requirements.get("typography"):
            score += caps.get("typography", 0.3) * 0.20
            reasons.append(f"typography ({caps.get('typography', 0.3):.2f})")
        if requirements.get("cinematic"):
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
) -> Dict[str, Any]:
    """Map a job description to the capabilities required.

    Returns a dict that `recommend_model` consumes to score models:
      category : 'image' | 'video'
      product_fidelity : bool
      photorealism : bool
      speed : bool
      typography : bool
      illustration : bool
      cinematic : bool
      needs_ref_image : bool
      needs_edit : bool
    """
    job_low = (job or "").lower()
    is_video = any(w in job_low for w in (
        "video", "reel", "clip", "motion", "animate",
        "cinematic", "8-second", "8 second",
    ))
    reqs: Dict[str, Any] = {
        "category": "video" if is_video else "image",
        "product_fidelity": bool(product_service_item),
        "photorealism": any(w in job_low for w in (
            "photo", "realistic", "real", "lifestyle",
            "studio", "product shot", "editorial",
        )),
        "speed": any(w in job_low for w in (
            "quick", "fast", "social", "story",
        )),
        "typography": any(w in job_low for w in (
            "text", "headline", "poster", "typography",
            "title", "logo", "wordmark",
        )),
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
def _load_brand_context(brand_id: str) -> dict:
    """Load brand bible + palette + archetypes from data/brand-directory."""
    candidates = [
        Path(f"/data/campaign-os/brand-directory/{brand_id}/bible-visual.json"),
        Path(f"/data/campaign-os/brand-directory/{brand_id}/palette/brand.json"),
        Path(f"/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data/brand-directory/{brand_id}/bible-visual.json"),
    ]
    ctx: dict = {"brand_id": brand_id, "bible": {}, "palette": {}, "archetypes": []}
    for path in candidates:
        if path.exists() and "bible" in path.name:
            try:
                ctx["bible"] = json.loads(path.read_text())
                break
            except Exception:
                continue
    palette_path = next((c for c in candidates if "palette" in c.name), None)
    if palette_path and palette_path.exists():
        try:
            ctx["palette"] = json.loads(palette_path.read_text())
        except Exception:
            pass
    return ctx


def _build_brand_block(brand_ctx: dict, brand_id: str) -> str:
    """Construct the BRAND section of the prompt from bible + palette."""
    parts = []
    bible = brand_ctx.get("bible", {})
    palette = brand_ctx.get("palette", {})
    if not bible.get("_placeholder"):
        vp = bible.get("visual_philosophy", "")
        if vp:
            parts.append(f"Visual philosophy: {vp}")
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