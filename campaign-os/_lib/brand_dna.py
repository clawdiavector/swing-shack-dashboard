"""
brand_dna.py — Brand-aware DNA loader + prompt builder for image generation.

Loads the full visual identity of a brand (palette + archetypes + bible-visual +
top reference images + learned signals) into a single "BrandContext" dict that
the image gen router can use to constrain generation to actual on-brand output.

Why this exists (2026-08-12):
  Before this module, the image gen layer injected the "brand recipe" as a
  4-word soft hint appended to the tail of the user prompt. The model read the
  user prompt first, generated generic stock-photo golf, then politely ignored
  the tail. Outputs were visibly off-brand.

  This module replaces that with a HARD, multi-layer brand constraint:
    1. Real hex colors from palette/brand.json (not just color names)
    2. Creative direction from bible-visual.json (the canonical source of truth)
    3. Archetype-aware canvas spec from visual-spec/archetypes.json
    4. A hard negative prompt banning stock-photo telltales
    5. Top-N reference images passed as actual image_url chunks (visual anchors)
    6. A system message for chat completions providers (OpenRouter multimodal)

The bible-visual.json file is currently a structured PLACEHOLDER. Once
Christelle fills in the actual creative direction, the module picks it up
automatically — no code change required.

Public API:
  load_brand_context(brand_id) -> BrandContext
  build_image_messages(brand_ctx, user_prompt, *, include_references=True) -> list[dict]
  build_negative_prompt(brand_ctx) -> str
  build_system_message(brand_ctx) -> str
  build_recipe_summary(brand_ctx) -> dict  (for the UI Recipe panel)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_LOG = logging.getLogger("campaign_os.brand_dna")

# Repo-root / data convention (matches _lib/brand_directory.py)
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
_BRAND_DIR = _REPO_ROOT / "data" / "brand-directory"

# How many top-scoring reference images to inject as visual anchors.
# Nano Banana handles 1-4 image inputs well; more than that gets expensive
# and dilutes the anchor effect. 3 is a good default.
MAX_REFERENCE_IMAGES = 3

# Hard negative prompt — what we never want the model to produce.
# Banned regardless of user prompt.
_DEFAULT_NEGATIVE = (
    "Avoid: generic stock photography, white seamless studio backgrounds, "
    "professional studio lighting on isolated products, perfectly centred "
    "symmetrical product shots, watermarks, stock-photo smiles, "
    "people facing directly into camera, generic landscape backgrounds, "
    "cartoon or illustrated styles, cluttered busy frames with no clear "
    "focal point, oversaturated HDR look, AI-fingerprint artefacts."
)


@dataclass
class BrandContext:
    """All the visual identity for one brand, loaded and ready to use."""

    brand_id: str
    palette: dict = field(default_factory=dict)        # {primary:{hex,name}, accent:..., ...}
    archetypes: list[dict] = field(default_factory=list)  # list of archetype spec dicts
    bible: dict = field(default_factory=dict)          # bible-visual.json content (creative direction)
    top_references: list[dict] = field(default_factory=list)  # [{filename, score, dominant, ...}]
    summary: str = ""                                  # human-readable 1-2 line summary
    sources: dict = field(default_factory=dict)        # which files actually loaded
    warnings: list[str] = field(default_factory=list)  # missing pieces

    @property
    def ok(self) -> bool:
        """True if we have at least palette + bible (or palette + archetypes)."""
        return bool(self.palette) and (bool(self.bible) or bool(self.archetypes))


# ── Loaders ────────────────────────────────────────────────────────────


def _safe_read_json(path: Path) -> Optional[dict]:
    try:
        if not path.exists():
            return None
        with path.open() as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError) as e:
        _LOG.warning("could not read %s: %s", path, e)
        return None


def _load_palette(brand_path: Path) -> dict:
    """Read palette/brand.json — returns the full palette dict (incl. supporting)."""
    data = _safe_read_json(brand_path / "palette" / "brand.json")
    if not data:
        return {}
    return data.get("palette", {}) or {}


def _load_archetypes(brand_path: Path) -> list[dict]:
    """Read visual-spec/archetypes.json — returns list of archetype spec dicts."""
    data = _safe_read_json(brand_path / "visual-spec" / "archetypes.json")
    if not data:
        return []
    arche = data.get("archetypes")
    return arche if isinstance(arche, list) else []


def _load_bible(brand_path: Path) -> dict:
    """Read bible-visual.json — the creative direction source of truth.

    NOTE: As of 2026-08-12 this file is a STRUCTURED PLACEHOLDER. The
    placeholder has explicit TODOs for Christelle to fill in. The module
    still loads it and uses whatever's there — empty values just produce
    less constrained output. Once she fills in the bible, the next
    generation picks it up automatically.
    """
    data = _safe_read_json(brand_path / "bible-visual.json")
    if not data:
        return {}
    return data


def _load_top_references(brand_path: Path, n: int = MAX_REFERENCE_IMAGES) -> list[dict]:
    """Read visual-dna-index.json and return the top-N scoring images.

    Each entry has: {filename, dna_path, score, luminance, dominant, passes}.
    We use the actual image file (NOT the .visual-dna.json) when sending as
    image_url chunks to the model.
    """
    data = _safe_read_json(brand_path / "visual-dna-index.json")
    if not data:
        return []
    by_filename = data.get("by_filename", {}) or {}
    entries = list(by_filename.values())
    # Sort by score desc, take top N
    entries.sort(key=lambda e: e.get("score", 0), reverse=True)
    top = entries[:n]
    # The index doesn't store `filename` directly — derive it from `dna_path`
    # (which is the .visual-dna.json sidecar path; the actual image lives next
    # to it with .jpg or .png extension). Try common extensions in order.
    images_dir = brand_path / "images"
    _IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")
    for e in top:
        dna_path = e.get("dna_path", "")
        if not dna_path:
            continue
        base = dna_path.rsplit("/", 1)[-1]
        if not base.endswith(".visual-dna.json"):
            continue
        stem = base[: -len(".visual-dna.json")]
        # Try each known image extension
        for ext in _IMG_EXTS:
            candidate = images_dir / (stem + ext)
            if candidate.exists():
                e["filename"] = stem + ext  # surface for the UI recipe panel
                e["_image_path"] = str(candidate)
                break
    # Drop entries we couldn't resolve an image path for
    top = [e for e in top if e.get("_image_path")]
    return top


# ── Public loaders ─────────────────────────────────────────────────────


def load_brand_context(brand_id: str, base_dir: Optional[Path] = None) -> BrandContext:
    """Load the full visual identity of a brand into a BrandContext.

    Safe to call with any brand_id. Missing files produce empty fields, not
    errors. The returned BrandContext.ok flag tells callers whether we have
    enough to constrain generation meaningfully.
    """
    base = base_dir or _BRAND_DIR
    brand_path = base / brand_id

    warnings: list[str] = []
    sources: dict[str, bool] = {}

    palette = _load_palette(brand_path)
    sources["palette/brand.json"] = bool(palette)
    if not palette:
        warnings.append("palette/brand.json missing — colour constraints will be loose")

    archetypes = _load_archetypes(brand_path)
    sources["visual-spec/archetypes.json"] = bool(archetypes)
    if not archetypes:
        warnings.append("visual-spec/archetypes.json missing — no archetype guidance")

    bible = _load_bible(brand_path)
    sources["bible-visual.json"] = bool(bible)
    if not bible:
        warnings.append("bible-visual.json missing — no creative direction loaded (PLACEHOLDER)")
    elif bible.get("_placeholder"):
        warnings.append(
            "bible-visual.json is a PLACEHOLDER — fill in TODOs for tighter brand constraints"
        )

    top_refs = _load_top_references(brand_path)
    sources["visual-dna-index.json"] = bool(top_refs)
    if not top_refs:
        warnings.append("visual-dna-index.json missing — no visual reference anchors")

    # Build a one-line summary for the UI Recipe panel
    pal = palette.get("primary", {}) if isinstance(palette, dict) else {}
    pal_name = pal.get("name") or pal.get("hex") or "unknown primary"
    summary = (
        f"{brand_id}: primary {pal_name}; "
        f"{len(archetypes)} archetype(s); "
        f"{len(top_refs)} top ref(s); "
        f"bible={'set' if bible and not bible.get('_placeholder') else 'placeholder' if bible else 'missing'}"
    )

    return BrandContext(
        brand_id=brand_id,
        palette=palette,
        archetypes=archetypes,
        bible=bible,
        top_references=top_refs,
        summary=summary,
        sources=sources,
        warnings=warnings,
    )


# ── Prompt builders ────────────────────────────────────────────────────


def build_system_message(brand_ctx: BrandContext) -> str:
    """Build a chat-completions 'system' message for image generation.

    This is the strongest signal in a chat-completions call. The model treats
    it as instructions, not suggestions. We use it to:
      1. Tell the model what brand it's designing for
      2. Anchor the model on the actual palette + creative direction
      3. Ban the off-brand stuff
    """
    if not brand_ctx.ok:
        # Not enough context to constrain — fall back to a generic "try your best"
        return (
            "You are a creative director for a premium golf brand. "
            "Produce visually striking, moody, indoor-studio-feel imagery. "
            "Avoid generic stock photography. Follow the user's prompt exactly."
        )

    parts: list[str] = []

    # 1. Brand identity
    bible = brand_ctx.bible or {}
    brand_voice = bible.get("voice") or bible.get("tone") or "premium, confident, data-driven"
    parts.append(
        f"You are designing for {brand_ctx.brand_id}, a premium indoor golf studio in Johannesburg, SA. "
        f"Brand voice: {brand_voice}."
    )

    # 2. Visual philosophy (from bible if set, else fall back to placeholder text)
    philosophy = bible.get("visual_philosophy") or bible.get("philosophy")
    if philosophy and isinstance(philosophy, str) and len(philosophy) >= 20:
        parts.append(f"Visual philosophy: {philosophy}")
    else:
        parts.append(
            "Visual philosophy: prefer moody, low-key studio lighting over flat studio white. "
            "Prefer in-the-moment swing/launch feels over posed product photography. "
            "Prefer data overlays and TrackMan-style cues over generic copy."
        )

    # 3. Palette — actual hex codes
    pal = brand_ctx.palette
    if pal:
        primary = pal.get("primary", {})
        accent = pal.get("accent", {})
        neutral_dark = pal.get("neutral_dark", {})
        neutral_light = pal.get("neutral_light", {})
        parts.append(
            f"Use the brand palette as your colour anchor: "
            f"primary {primary.get('hex', '')} ({primary.get('name', '')}), "
            f"accent {accent.get('hex', '')} ({accent.get('name', '')}), "
            f"background neutral_dark {neutral_dark.get('hex', '')} ({neutral_dark.get('name', '')}), "
            f"text neutral_light {neutral_light.get('hex', '')} ({neutral_light.get('name', '')}). "
            f"Stick close to these hex values — do not drift to stock-photo teal/green or bright orange."
        )

    # 4. Look-and-feel keywords from bible (the part Christelle fills in)
    # Filter out TODO / placeholder strings so they don't leak into the prompt
    def _is_real_value(x: Any) -> bool:
        s = str(x).strip() if x is not None else ""
        if not s or len(s) < 3:
            return False
        low = s.lower()
        return not (
            low.startswith("todo")
            or low.startswith("examples")
            or "delete and replace" in low
            or low in ("n/a", "na", "none", "null", "-", "—", "tbd", "...")
        )

    keywords = bible.get("look_and_feel_keywords") or bible.get("keywords")
    real_keywords: list[str] = []
    if isinstance(keywords, list):
        real_keywords = [k for k in keywords if _is_real_value(k)]
    elif isinstance(keywords, str) and _is_real_value(keywords):
        real_keywords = [keywords]
    if real_keywords:
        parts.append(f"Look and feel: {', '.join(real_keywords)}.")

    # 5. Negative — non-negotiable
    parts.append(f"NEVER produce: {_DEFAULT_NEGATIVE}")

    return "\n\n".join(parts)


def build_negative_prompt(brand_ctx: BrandContext) -> str:
    """Build a hard negative prompt (caller decides whether the model supports it).

    Most chat-completions image models don't have a separate negative-prompt
    field — they consume it as part of the user message. We return a clean
    list the caller can inject wherever it fits.
    """
    neg = [_DEFAULT_NEGATIVE]

    # Brand-specific exclusions from the bible
    bible = brand_ctx.bible or {}
    bible_neg = bible.get("negative_prompts") or bible.get("avoid")
    if isinstance(bible_neg, list):
        neg.extend(
            str(x) for x in bible_neg
            if x and not str(x).strip().lower().startswith("todo")
            and "delete and replace" not in str(x).lower()
        )
    elif isinstance(bible_neg, str) and bible_neg.strip():
        low = bible_neg.lower()
        if not low.startswith("todo") and "delete and replace" not in low:
            neg.append(bible_neg)

    return " ".join(neg)


def _read_reference_b64(image_path: str) -> Optional[str]:
    """Read an image file and base64-encode it for an image_url data URL."""
    try:
        p = Path(image_path)
        if not p.exists():
            return None
        import base64
        raw = p.read_bytes()
        # MIME guess from extension
        ext = p.suffix.lower()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png" if ext == ".png" else "image/jpeg"
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except OSError as e:
        _LOG.warning("could not read reference image %s: %s", image_path, e)
        return None


def build_image_messages(
    brand_ctx: BrandContext,
    user_prompt: str,
    *,
    include_references: bool = True,
    extra_reference_paths: Optional[list[str]] = None,
) -> list[dict]:
    """Build the chat-completions 'messages' payload for image generation.

    Returns a list ready to drop into messages=[...]:
      [
        {"role": "system", "content": "..."},         # hard brand constraints
        {"role": "user",   "content": [                # multimodal content
            {"type": "text", "text": "..."},           # the user prompt + brand context
            {"type": "image_url", "image_url": {"url": "data:..."}},  # ref 1
            {"type": "image_url", "image_url": {"url": "data:..."}},  # ref 2
            ...
        ]}
      ]

    For models/providers that don't support multimodal content, callers can
    flatten the text portion with flatten_to_text() below.
    """
    messages: list[dict] = []

    # System message — hard constraints
    if brand_ctx.ok:
        messages.append({"role": "system", "content": build_system_message(brand_ctx)})

    # User message — the actual ask, plus any reference images
    user_text_parts: list[str] = [user_prompt.strip()]

    # Reinforce negative at the end of the user message too (belt + braces)
    if brand_ctx.ok:
        user_text_parts.append("")
        user_text_parts.append(f"BRAND CONSTRAINTS: {build_system_message(brand_ctx)}")
        user_text_parts.append("")
        user_text_parts.append(f"AVOID: {build_negative_prompt(brand_ctx)}")

    user_text = "\n".join(user_text_parts)

    content: list[dict] = [{"type": "text", "text": user_text}]

    # Reference image chunks
    if include_references:
        # Use top reference images from the brand context
        for ref in brand_ctx.top_references:
            ipath = ref.get("_image_path")
            if not ipath:
                continue
            data_url = _read_reference_b64(ipath)
            if data_url:
                content.append({"type": "image_url", "image_url": {"url": data_url}})

        # Plus any extras the caller explicitly added
        for ep in extra_reference_paths or []:
            data_url = _read_reference_b64(ep)
            if data_url:
                content.append({"type": "image_url", "image_url": {"url": data_url}})

    messages.append({"role": "user", "content": content})
    return messages


def flatten_to_text(messages: list[dict]) -> list[dict]:
    """Flatten multimodal messages to text-only (for providers that don't support images).

    Keeps the system message + concatenates all text content from the user
    message. Drops image chunks (caller should warn if it does this).
    """
    flat: list[dict] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if isinstance(content, str):
            flat.append({"role": role, "content": content})
        elif isinstance(content, list):
            text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
            flat.append({"role": role, "content": "\n".join(p for p in text_parts if p)})
    return flat


def build_recipe_summary(brand_ctx: BrandContext) -> dict:
    """Build a small summary dict for the UI Recipe panel.

    Returns a JSON-serialisable dict with everything the UI needs to show
    "what the model was told" without leaking raw prompt text or keys.
    """
    pal = brand_ctx.palette
    primary = pal.get("primary", {}) if isinstance(pal, dict) else {}
    accent = pal.get("accent", {}) if isinstance(pal, dict) else {}

    bible = brand_ctx.bible or {}
    return {
        "brand_id": brand_ctx.brand_id,
        "ok": brand_ctx.ok,
        "summary": brand_ctx.summary,
        "warnings": brand_ctx.warnings,
        "sources": brand_ctx.sources,
        "palette": {
            "primary": {"hex": primary.get("hex"), "name": primary.get("name")},
            "accent": {"hex": accent.get("hex"), "name": accent.get("name")},
        },
        "bible_loaded": bool(bible) and not bible.get("_placeholder"),
        "bible_placeholder": bool(bible.get("_placeholder")),
        "bible_philosophy": bible.get("visual_philosophy") or bible.get("philosophy") or "",
        "bible_keywords": bible.get("look_and_feel_keywords") or bible.get("keywords") or [],
        "archetypes_count": len(brand_ctx.archetypes),
        "reference_images_used": [
            {
                "filename": r.get("filename"),
                "score": r.get("score"),
                "dominant": r.get("dominant"),
            }
            for r in brand_ctx.top_references
        ],
        "system_message_preview": (build_system_message(brand_ctx)[:400] + "…") if brand_ctx.ok else "",
    }
