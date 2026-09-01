"""
Product-Creative Brief Generator
================================

Resolves a calendar/scheduled product post into a complete creative brief:
- Product identity (name, brand, family, SKU, colour, size, price)
- Product brand profile (visual direction, voice, colour cues, photography)
- Store brand overlay (Stick, Swing Shack, Bag Drop — voice, typography, layout)
- Reference selection: primary (product image) → secondary (product brand refs) → tertiary (store refs)
- Master prompt with [JOB]/[STORE]/[PRODUCT BRAND]/[PRODUCT]/[PRESERVE] structure
- Negative / Preservation prompt
- Krea model recommendation

Per heidi.txt directive (2026-09-01):
"DO NOT BUILD A SEPARATE IMAGE GENERATOR. The product calendar should
naturally feed the Creative Director we already built."

This module is the bridge between propose_product_calendar() and the
Creative Director's recommend_model() / build prompts.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Optional
from datetime import datetime

# ────────────────────────────────────────────────────────────────────────────
# Brand / currency configuration
# ────────────────────────────────────────────────────────────────────────────

BRAND_CONFIG = {
    "stick": {
        "name": "Stick",
        "currency": "ZAR",
        "currency_symbol": "R",
        "voice": "Know the numbers. Speak like a golfer.",
        "tag": "performance-driven, modern, technical",
        "store_brand_type": "marketing",
        "logo_asset": "stick-logo.svg",
    },
    "swing-shack": {
        "name": "Swing Shack",
        "currency": "ZAR",
        "currency_symbol": "R",
        "voice": "South African indoor golf, TrackMan-led, measurement-first.",
        "tag": "knowledgeable, curious, warm, useful, witty",
        "store_brand_type": "marketing",
        "logo_asset": "swing-shack-logo.svg",
    },
    "bag-drop": {
        "name": "The Bag Drop",
        "currency": "ZAR",
        "currency_symbol": "R",
        "voice": "Putt the swing aside. Have fun with the gear.",
        "tag": "playful, gear-curious, culture-led",
        "store_brand_type": "marketing",
        "logo_asset": "bag-drop-logo.svg",
    },
    "takomo": {
        "name": "Takomo",
        "currency": "EUR",  # Takomo is Finnish, retail in EUR primarily
        "currency_symbol": "€",
        "voice": "Performance-led equipment. Made by players who test every detail.",
        "tag": "technical, minimal, equipment-first",
        "store_brand_type": "equipment",  # equipment manufacturer (not retail)
        "logo_asset": "takomo-logo.svg",
    },
}


def get_brand_config(brand_id: str) -> dict:
    """Get brand configuration. Defaults to ZAR if brand unknown."""
    return BRAND_CONFIG.get(
        brand_id,
        {
            "name": brand_id,
            "currency": "ZAR",
            "currency_symbol": "R",
            "voice": "",
            "tag": "",
            "store_brand_type": "marketing",
            "logo_asset": None,
        },
    )


def format_price(price: Optional[float], brand_id: str) -> str:
    """Format a price for display in the brand's currency."""
    if price is None or price == 0:
        return ""
    cfg = get_brand_config(brand_id)
    symbol = cfg["currency_symbol"]
    if symbol == "R":
        # South African convention: R1,499 / R12,999 / R899
        if price >= 1000:
            return f"R{int(round(price)):,}".replace(",", ",")
        return f"R{int(round(price))}"
    elif symbol == "€":
        return f"€{price:,.2f}".rstrip("0").rstrip(".")
    elif symbol == "$":
        return f"${price:,.2f}".rstrip("0").rstrip(".")
    else:
        return f"{symbol}{int(round(price)):,}"


# ────────────────────────────────────────────────────────────────────────────
# Price buckets — derived dynamically from the catalogue
# (Per user directive: NOT hard-coded American ranges.)
# ────────────────────────────────────────────────────────────────────────────

def compute_price_buckets(items: list, brand_id: str) -> dict:
    """Compute price buckets dynamically from a list of {price} items.

    Returns:
        {
            "ranges": [(label, low, high), ...],
            "per_bucket": {"<label>": count, ...},
            "currency": "ZAR"
        }

    Strategy: pick log-spaced bucket edges that reflect the actual catalogue.
    For ZAR brands we use 500/1500/5000/15000 edges (typical SA golf retail).
    """
    cfg = get_brand_config(brand_id)
    currency = cfg["currency"]
    sym = cfg["currency_symbol"]

    # Filter to items with valid prices
    prices = sorted([float(i.get("price", 0)) for i in items if i.get("price", 0) > 0])

    if not prices:
        return {
            "ranges": [(f"all", 0, float("inf"))],
            "per_bucket": {},
            "currency": currency,
        }

    # Use currency-appropriate edge values
    if sym == "R":
        # ZAR: under-500, 500-1500, 1500-5000, 5000-15000, 15000+
        edges = [500, 1500, 5000, 15000]
    elif sym == "€":
        edges = [50, 150, 500, 1500]
    elif sym == "$":
        edges = [50, 150, 500, 1500]
    else:
        edges = [500, 1500, 5000, 15000]

    # Build labels
    ranges = [((f"under {sym}{edges[0]:,}"), 0, edges[0])]
    for i in range(len(edges) - 1):
        ranges.append((f"{sym}{edges[i]:,}-{sym}{edges[i+1]:,}", edges[i], edges[i+1]))
    ranges.append((f"{sym}{edges[-1]:,}+", edges[-1], float("inf")))

    # Per-bucket count
    per_bucket = {label: 0 for label, _, _ in ranges}
    for p in prices:
        for label, low, high in ranges:
            if low <= p < high:
                per_bucket[label] += 1
                break

    return {
        "ranges": ranges,
        "per_bucket": per_bucket,
        "currency": currency,
        "min_price": prices[0],
        "max_price": prices[-1],
        "median_price": prices[len(prices) // 2],
    }


def price_bucket_for(price: float, brand_id: str) -> str:
    """Return the price bucket label for a single price."""
    if price <= 0:
        return "no-price"
    cfg = get_brand_config(brand_id)
    sym = cfg["currency_symbol"]
    if sym == "R":
        if price < 500: return f"under {sym}500"
        if price < 1500: return f"{sym}500-{sym}1,500"
        if price < 5000: return f"{sym}1,500-{sym}5,000"
        if price < 15000: return f"{sym}5,000-{sym}15,000"
        return f"{sym}15,000+"
    elif sym == "€":
        if price < 50: return f"under €50"
        if price < 150: return f"€50-€150"
        if price < 500: return f"€150-€500"
        if price < 1500: return f"€500-€1,500"
        return f"€1,500+"
    else:
        if price < 50: return f"under {sym}50"
        if price < 150: return f"{sym}50-{sym}150"
        if price < 500: return f"{sym}150-{sym}500"
        return f"{sym}500+"


# ────────────────────────────────────────────────────────────────────────────
# Product brand profiles
# ────────────────────────────────────────────────────────────────────────────
# Per user directive (2026-09-01): store-brand (Stick) controls marketing
# treatment; product-brand (Takomo / PB / LAB / Vice / Sausage) controls
# product identity, colorway, materials, manufacturer aesthetic.

PRODUCT_BRAND_PROFILES = {
    "takomo": {
        "name": "Takomo",
        "category": "equipment",
        "visual_direction": "Modern, clean, performance-led, technically credible, product-focused, minimal, equipment first.",
        "tone": "Technical precision with quiet confidence. No fake-luxury theatre.",
        "colour_cues": ["#1a1a1a", "#c8a857", "#3a3a3a", "matte black + brass accent"],
        "photography_style": "Studio, neutral background, soft directional lighting, sharp product detail, no lifestyle theatrics, no fake props.",
        "product_fidelity_rules": [
            "iron head geometry exact",
            "topline preserved",
            "sole shape preserved",
            "cavity/back design preserved",
            "hosel preserved",
            "grooves preserved exactly",
            "finish preserved (matte / satin / polished)",
            "colour preserved exactly",
            "logo preserved",
            "model marking preserved",
            "badge position preserved",
            "shaft connection preserved",
            "handedness preserved",
            "proportions preserved",
            "material preserved",
            "no added screws, no invented weighting ports, no changed finish, no moved logo, no invented model names, no altered head shape, no impossible geometry",
        ],
        "approved_examples": [],
        "rejected_examples": [
            "fake grooves added or removed",
            "cavity design altered",
            "model name invented",
            "fake Takomo branding",
            "logo repositioned",
            "bent shaft",
            "impossible hosel geometry",
            "warped clubface",
            "duplicate club in one frame",
            "head shape altered",
        ],
    },
    "psycho bunny": {
        "name": "Psycho Bunny",
        "category": "apparel",
        "visual_direction": "Premium apparel, personality, fashion-forward, playful edge, polished, modern golf lifestyle.",
        "tone": "Confident, witty, modern, premium. Never try-hard.",
        "colour_cues": ["mono black/white", "brand red accent (#c5392f)", "athleisure palette"],
        "photography_style": "Studio + lifestyle mix, clean composition, garment detail close-ups, human or mannequin.",
        "product_fidelity_rules": [
            "garment cut preserved",
            "seam placement preserved",
            "waistband preserved",
            "pocket placement preserved",
            "colour preserved (no recolouring)",
            "pattern preserved",
            "logo placement preserved",
            "proportions preserved",
            "no added pockets, no changed waistband, no fake pattern, no warped fabric, no changed garment proportions",
        ],
        "approved_examples": [],
        "rejected_examples": [
            "garment recoloured",
            "added pockets or changed pocket placement",
            "fake Psycho Bunny logo",
            "warped fabric texture",
            "changed seam placement",
        ],
    },
    "l.a.b.": {
        "name": "L.A.B.",
        "category": "equipment",
        "visual_direction": "Technical, unconventional, putting-specific, performance conversation, product engineering.",
        "tone": "Engineering-focused, precise, unfussy.",
        "colour_cues": ["#0a0a0a", "machined silver", "anodised accents"],
        "photography_style": "Studio close-ups of head shape, hosel, alignment. High-detail product photography.",
        "product_fidelity_rules": [
            "head shape preserved",
            "alignment marks preserved",
            "hosel preserved",
            "shaft connection preserved",
            "no fake branding",
            "no invented alignment marks",
        ],
        "approved_examples": [],
        "rejected_examples": [
            "head shape altered",
            "fake L.A.B. alignment marks",
            "altered hosel",
            "fake shaft connection",
        ],
    },
    "vice": {
        "name": "Vice",
        "category": "equipment",
        "visual_direction": "Modern, bold, accessible golf culture, distinctive colour, contemporary.",
        "tone": "Bold without being loud. Confident, contemporary, accessible.",
        "colour_cues": ["vice green", "matte black", "white", "bold accent colours"],
        "photography_style": "Studio with coloured backgrounds, clean ball detail, in-flight when useful.",
        "product_fidelity_rules": [
            "ball colour preserved",
            "logo preserved",
            "dimple pattern preserved",
            "no fake branding",
        ],
        "approved_examples": [],
        "rejected_examples": [
            "fake dimples",
            "fake Vice logo",
            "recoloured ball",
        ],
    },
    "sausage putters": {
        "name": "Sausage Putters",
        "category": "equipment",
        "visual_direction": "Distinct personality, non-traditional, putting curiosity, product character.",
        "tone": "Quirky, characterful, conversation-starting.",
        "colour_cues": ["putter head specific (often black/silver combo)"],
        "photography_style": "Studio with personality — odd angles, strong shadows, product-as-hero.",
        "product_fidelity_rules": [
            "head shape preserved",
            "alignment marks preserved",
            "hosel preserved",
            "no fake branding",
        ],
        "approved_examples": [],
        "rejected_examples": [
            "head shape altered",
            "fake branding",
            "altered hosel",
        ],
    },
}


def detect_product_brand(product: dict) -> dict:
    """Resolve product_brand for a product record.

    Heuristic cascade:
    1. Explicit `product_brand` field
    2. Match the product name prefix against known product brand names
    3. Default to empty (caller decides)
    """
    if product.get("product_brand"):
        pb_key = product["product_brand"].lower().strip()
        if pb_key in PRODUCT_BRAND_PROFILES:
            return PRODUCT_BRAND_PROFILES[pb_key]
    if product.get("brand"):
        b_key = product["brand"].lower().strip()
        if b_key in PRODUCT_BRAND_PROFILES:
            return PRODUCT_BRAND_PROFILES[b_key]

    # Name-prefix matching
    name = (product.get("name") or "").lower()
    for key, profile in PRODUCT_BRAND_PROFILES.items():
        if key in name:
            return profile

    return {
        "name": product.get("product_brand") or product.get("brand") or "Unknown",
        "category": "equipment" if "club" in name or "iron" in name or "putter" in name or "ball" in name else "apparel",
        "visual_direction": "Use safe, neutral product imagery.",
        "tone": "Neutral, brand-consistent.",
        "colour_cues": [],
        "photography_style": "Studio, neutral background, product-detail forward.",
        "product_fidelity_rules": ["preserve product colour, geometry, logo, proportions"],
        "approved_examples": [],
        "rejected_examples": ["no fake branding", "no invented text"],
    }


# ────────────────────────────────────────────────────────────────────────────
# Reference picker
# Per user directive: ACTUAL PRODUCT REFERENCE > PRODUCT-BRAND REFS > STORE REFS
# ────────────────────────────────────────────────────────────────────────────

def pick_product_reference_images(product: dict, brand_id: str, max_count: int = 4) -> dict:
    """Select reference images for a product-led post.

    Hierarchy:
    1. PRIMARY: actual product reference image (uploaded, supplier, library)
    2. SECONDARY: product-brand visual references
    3. TERTIARY: store-brand (Stick/Swing Shack) creative references

    Returns:
        {
            "primary": [{url, kind, source, why_selected}, ...],
            "secondary": [...],
            "tertiary": [...],
            "missing_primary": bool,   # True when no real product reference exists
            "fallback_options": [...]  # actions user can take
        }
    """
    # Look up product references in the extended catalog
    primary = []
    missing_primary = False

    # Check product record for references
    product_refs = product.get("reference_images") or product.get("product_images") or []
    if not product_refs and product.get("image_url"):
        product_refs = [{"url": product["image_url"], "kind": "product", "source": "product_record"}]

    for ref in product_refs[:max_count]:
        primary.append({
            "url": ref.get("url") or ref,
            "kind": "product",
            "source": ref.get("source", "imported"),
            "why_selected": "exact product reference — controls geometry, colour, logo, proportions",
        })

    if not primary:
        missing_primary = True

    # Secondary: product brand references (from product brand profile.approved_examples)
    pb = detect_product_brand(product)
    secondary = []
    for ref in pb.get("approved_examples", [])[:max_count]:
        secondary.append({
            "url": ref.get("url"),
            "kind": "product-brand",
            "source": f"product brand: {pb['name']}",
            "why_selected": f"{pb['name']} visual identity — mood, material context, manufacturer aesthetic",
        })

    # Tertiary: store brand references (Stick brand bible / previous posts)
    # This would normally read from brand-bible.json + previous-creative.json
    # For now surface as a placeholder that caller can resolve.
    tertiary = []

    fallback_options = []
    if missing_primary:
        fallback_options = [
            {"label": "Upload image", "action": "open_uploader"},
            {"label": "Select existing reference", "action": "open_reference_picker"},
            {"label": "Use supplier image", "action": "open_supplier_lookup"},
            {"label": "Create non-product-render post", "action": "convert_to_non_product"},
        ]

    return {
        "primary": primary,
        "secondary": secondary,
        "tertiary": tertiary,
        "missing_primary": missing_primary,
        "fallback_options": fallback_options,
        "hierarchy_explanation": (
            "PRIMARY: actual product reference (controls geometry, colour, logo, proportions). "
            "SECONDARY: product-brand visual references (mood, material context, manufacturer aesthetic). "
            "TERTIARY: store-brand creative references (marketing treatment, typography, layout)."
        ),
    }


# ────────────────────────────────────────────────────────────────────────────
# Creative brief builder
# Per user directive: MASTER PROMPT auto-generated with [JOB][STORE][PRODUCT BRAND]
# etc. structure. NEGATIVE / PRESERVATION PROMPT auto-generated.
# ────────────────────────────────────────────────────────────────────────────

# Creative property → angle (extends what's already in marketing_lanes.PRODUCT_ANGLES)
ANGLE_TO_FRAMING = {
    "hero_product": "Hero product photography, studio clean, single hero shot.",
    "why_its_here": "Editorial frame: explain *why this product* is in the store rotation today.",
    "detail": "Macro detail shot, surface texture, badge visible, mark legible.",
    "who_its_for": "Lifestyle frame, model or hand interaction showing real use case.",
    "material": "Material-focused: show fabric weave / metal finish / construction quality.",
    "use_case": "On-course or in-bay use case — performance context.",
    "staff_pick": "Staff pick banner — expert endorsement framing.",
    "new_arrival": "New arrival banner — fresh-in-store framing.",
    "back_in_stock": "Back-in-stock banner — scarcity proof framing.",
    "limited_stock": "Limited stock banner — act-now framing.",
    "colour_variant": "Colourway frame — show the available palette.",
    "fit_performance": "Performance / fit frame — trackman data or measurement-led context.",
    "style": "Style frame — fashion-led composition, modern golf aesthetic.",
}


def build_master_prompt(
    product: dict,
    brand_id: str,
    creative_property: str = "why_its_here",
    angle: str = "hero_product",
) -> dict:
    """Build master prompt + negative/preservation prompt for a product post.

    Returns:
        {
            "master_prompt": str,
            "negative_prompt": str,
            "preserve_block": str,
            "creative_property": str,
            "angle": str,
            "framing": str,
            "context_block": str,
        }
    """
    cfg = get_brand_config(brand_id)
    pb = detect_product_brand(product)

    product_name = product.get("name", "Product")
    product_brand_name = pb["name"]
    store_brand_name = cfg["name"]
    category = pb.get("category", product.get("category", "equipment"))

    # ─── PRESERVE block — strict product fidelity
    preserve_rules = pb.get("product_fidelity_rules", [])
    preserve_block = "PRESERVE EXACTLY:\n" + "\n".join(f"- {r}" for r in preserve_rules)

    # ─── Product identity
    product_identity = f"""[PRODUCT]
{product_name}
SKU: {product.get('sku', '?')}
Variant: {product.get('colour', '')} {product.get('size', '')}
Category: {product.get('category', category)}
Family: {product.get('product_family', '?')}
Reference source: {product.get('supplier', '?')}
"""
    if product.get("price"):
        product_identity += f"Price: {format_price(product.get('price'), brand_id)}\n"

    # ─── Product-brand direction
    pb_block = f"""[PRODUCT BRAND]
{product_brand_name}

Visual direction: {pb.get('visual_direction', '')}
Tone: {pb.get('tone', '')}
Photography style: {pb.get('photography_style', '')}
Colour cues: {', '.join(pb.get('colour_cues', [])[:3])}
"""

    # ─── Store-brand direction
    store_block = f"""[STORE BRAND]
{store_brand_name}

Voice: {cfg.get('voice', '')}
Marketing character: {cfg.get('tag', '')}
Layout: {store_brand_name} editorial treatment — typography chosen and applied deterministically AFTER image generation, not baked into the image.
"""

    # ─── Creative property / angle
    property_block = f"""[CREATIVE PROPERTY]
{creative_property.replace("_", " ").title()}

Angle: {angle.replace("_", " ")}
Framing: {ANGLE_TO_FRAMING.get(angle, ANGLE_TO_FRAMING.get("hero_product"))}
"""

    # ─── Composition / background / lighting / camera / format
    composition_block = f"""[COMPOSITION]
Background: {pb.get('photography_style', 'Neutral studio with subtle gradient or textured backdrop')}
Lighting: Soft directional, product-shape-revealing, subtle reflection in floor if applicable
Camera: 85mm product / 50mm lifestyle, low DOF, product sharp
Material detail: Visible texture, surface finish, brand mark
Format: 1:1 for instagram-feed / 9:16 for stories
Space for {store_brand_name} overlay: negative space top-left or top, allow room for headline + CTA
"""

    # ─── Master prompt assembly
    master = f"""[JOB]
Generate a photographic image for a {store_brand_name} product post.

{product_identity}

{pb_block}

{store_block}

{property_block}

{composition_block}

Use the supplied product reference image(s) as the EXACT product reference.
{preserve_block}

Do NOT generate text, words, letters, numbers, signs, logos, watermarks, or typography of any kind.
Leave clean negative space for the {store_brand_name} headline, price, CTA, and logo to be added deterministically in post-production.
"""

    # ─── Negative / preservation prompt
    base_negative = (
        "no altered head geometry, no fake grooves, no fake model name, no fake logo, "
        "no changed handedness, no bent shaft, no impossible hosel, no invented screws, "
        "no warped clubface, no floating parts, no duplicate objects, no fake specifications, "
        "no fake store-brand logo, no generated typography, no nonsense text, no watermarks"
    )
    category_specific = ""
    if category == "apparel":
        category_specific = (
            ", no changed garment cut, no altered seam placement, no changed colour, "
            "no invented pockets, no changed waistband, no fake pattern, no warped fabric, "
            "no changed garment proportions"
        )
    elif category == "equipment":
        category_specific = (
            ", no changed head shape, no fake alignment marks, no altered hosel, "
            "no fake shaft connection, no invented branding"
        )

    negative = base_negative + category_specific

    # Product-specific additions
    rejected_examples = pb.get("rejected_examples", [])
    if rejected_examples:
        negative += ", " + ", ".join(rejected_examples[:8])

    # Product identity context (top of master)
    context_block = f"""[JOB] — {product_brand_name} {product_name} via {store_brand_name}
[CREATIVE PROPERTY] — {creative_property.replace("_", " ").title()}
[ANGLE] — {angle.replace("_", " ").title()}
"""

    return {
        "master_prompt": master.strip(),
        "negative_prompt": negative,
        "preserve_block": preserve_block,
        "creative_property": creative_property,
        "angle": angle,
        "framing": ANGLE_TO_FRAMING.get(angle, ""),
        "context_block": context_block,
        "product_brand": product_brand_name,
        "store_brand": store_brand_name,
        "category": category,
    }


# ────────────────────────────────────────────────────────────────────────────
# End-to-end: take a calendar item → return the FULL creative brief
# ────────────────────────────────────────────────────────────────────────────

def build_full_creative_brief(item: dict, brand_id: str) -> dict:
    """Take a calendar/lanes item and return the auto-generated creative brief.

    `item` must include:
      - product_id (resolve from extended catalog)
      - creative_property (optional, defaults to why_its_here)
      - angle (optional, defaults to hero_product)

    Returns:
        {
            "ok": True,
            "product": {...},                  # resolved product from catalog
            "product_brand": {...},           # detected product brand profile
            "store_brand": {...},             # store-brand config
            "currency": "ZAR",
            "formatted_price": "R1,499",
            "price_bucket": "R1,500-R5,000",
            "references": { primary, secondary, tertiary, missing_primary, fallback_options },
            "creative_brief": { master_prompt, negative_prompt, creative_property, angle, framing },
            "missing": bool,                  # True when no real product reference (DO NOT generate)
            "next_step": str,                 # suggested user action
        }
    """
    # Resolved lazily to avoid circular imports — marketing_lanes imports
    # product_creative_brief for propose_product_calendar.
    from .marketing_lanes import get_extended_product

    product_id = item.get("product_id")
    if not product_id:
        return {
            "ok": False,
            "error": "calendar item has no product_id — cannot build brief",
            "missing": True,
            "next_step": "tag this slot with a product and re-propose",
        }

    product = get_extended_product(brand_id, product_id) or {}
    if not product:
        return {
            "ok": False,
            "error": f"product {product_id} not found in extended catalog",
            "missing": True,
            "next_step": "import the product via the smart stock importer",
        }

    # Resolve product brand (Stick's "store brand" + product's manufacturer)
    pb = detect_product_brand(product)
    cfg = get_brand_config(brand_id)

    # References
    refs = pick_product_reference_images(product, brand_id)

    # Master + negative prompts
    creative_property = item.get("creative_property") or "why_its_here"
    angle = item.get("angle") or "hero_product"
    brief = build_master_prompt(product, brand_id, creative_property, angle)

    # Price
    formatted_price = format_price(product.get("price"), brand_id)
    bucket = price_bucket_for(product.get("price", 0) or 0, brand_id)

    missing_reference = refs["missing_primary"]

    return {
        "ok": True,
        "product": {
            "id": product.get("id"),
            "name": product.get("name"),
            "sku": product.get("sku"),
            "category": product.get("category"),
            "product_family": product.get("product_family"),
            "variant_raw": product.get("variant_raw"),
            "colour": product.get("colour"),
            "size": product.get("size"),
            "price": product.get("price"),
            "stock_quantity": product.get("stock_quantity"),
            "supplier": product.get("supplier"),
            "product_url": product.get("product_url"),
            "description": product.get("description"),
            "verified_features": product.get("verified_features") or [],
            "reference_images": refs["primary"],
        },
        "product_brand": {
            "name": pb["name"],
            "category": pb["category"],
            "visual_direction": pb["visual_direction"],
            "tone": pb["tone"],
            "colour_cues": pb["colour_cues"],
            "photography_style": pb["photography_style"],
            "product_fidelity_rules": pb["product_fidelity_rules"],
        },
        "store_brand": {
            "name": cfg["name"],
            "currency": cfg["currency"],
            "currency_symbol": cfg["currency_symbol"],
            "voice": cfg["voice"],
            "tag": cfg["tag"],
            "store_brand_type": cfg["store_brand_type"],
        },
        "currency": cfg["currency"],
        "currency_symbol": cfg["currency_symbol"],
        "formatted_price": formatted_price,
        "price_bucket": bucket,
        "references": refs,
        "creative_brief": brief,
        "missing_reference": missing_reference,
        "missing": missing_reference,
        "next_step": (
            "PRODUCT IMAGE REQUIRED — upload a real reference, select an existing one, or convert this slot to a non-product post"
            if missing_reference
            else "GENERATE CREATIVE — master prompt + negative prompt ready, Krea model chosen automatically by Creative Director"
        ),
    }
