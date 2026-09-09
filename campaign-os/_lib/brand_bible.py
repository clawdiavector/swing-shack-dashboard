"""
brand_bible.py — Structured brand intelligence parser + retrieval.

Per user directive PHASE L-7:
  - Parse brand bible documents into structured fields:
      voice, visual_language, colours, typography, logo_rules,
      photography, product_fidelity, positive_prompts,
      negative_prompts, creative_properties, approved_examples,
      rejected_examples
  - Retrieve only the relevant subset for each job (not the whole doc)
  - Track Last updated

Brand bibles can be uploaded as:
  - markdown (auto-parsed into structured fields)
  - JSON (direct structured input)
  - free-form text (heuristic extraction)
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


STRUCTURED_FIELDS = [
    "voice", "visual_language", "colours", "typography",
    "logo_rules", "photography", "product_fidelity",
    "positive_prompts", "negative_prompts", "creative_properties",
    "approved_examples", "rejected_examples",
]


def _data_root() -> Path:
    from os import environ
    candidates = []
    bundled = environ.get("BUNDLED_DATA_DIR")
    if bundled:
        candidates.append(Path(bundled))
    candidates.append(Path(environ.get("DATA_DIR") or "/data/campaign-os"))
    candidates.append(Path(
        "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data"
    ))
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


def _bible_path(brand_id: str) -> Path:
    return _data_root() / "brand-directory" / brand_id / "bible-intelligence.json"


def get_bible(brand_id: str) -> Optional[Dict[str, Any]]:
    """Return the structured brand bible, or None if not yet uploaded."""
    p = _bible_path(brand_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def save_bible(brand_id: str, bible: Dict[str, Any], *, format: str = "structured") -> Dict[str, Any]:
    """Save a structured brand bible. Returns the saved bible with metadata."""
    p = _bible_path(brand_id)
    p.parent.mkdir(parents=True, exist_ok=True)

    # If format is "markdown", parse it
    if format == "markdown":
        parsed = parse_markdown_bible(bible.get("raw_markdown") or bible.get("raw") or "")
        bible = {**parsed, **bible}
        bible.pop("raw_markdown", None)
        bible.pop("raw", None)

    # If format is "freeform", heuristic-extract
    elif format == "freeform":
        raw = bible.get("raw_text") or bible.get("raw") or ""
        parsed = extract_from_freeform(raw)
        bible = {**parsed, **bible}
        bible.pop("raw_text", None)
        bible.pop("raw", None)

    bible.setdefault("brand_id", brand_id)
    bible["last_updated"] = datetime.utcnow().isoformat() + "Z"
    bible["format"] = format
    # Ensure all structured fields exist
    for f in STRUCTURED_FIELDS:
        bible.setdefault(f, [] if f in ("colours", "creative_properties", "approved_examples", "rejected_examples") else "")

    p.write_text(json.dumps(bible, indent=2, default=str))
    return bible


def parse_markdown_bible(md: str) -> Dict[str, Any]:
    """Parse a markdown brand bible into structured fields.

    Recognises sections by heading:
      ## Voice
      ## Visual Language
      ## Colours
      ## Typography
      ## Logo Rules
      ## Photography
      ## Product Fidelity
      ## Positive Prompts
      ## Negative Prompts
      ## Creative Properties
      ## Approved Examples
      ## Rejected Examples
    """
    out: Dict[str, Any] = {f: "" if f not in ("colours", "creative_properties", "approved_examples", "rejected_examples") else [] for f in STRUCTURED_FIELDS}
    sections = re.split(r"^##\s+", md, flags=re.MULTILINE)
    heading_to_field = {
        "voice": "voice", "voice & tone": "voice", "tone": "voice",
        "visual language": "visual_language", "visual": "visual_language", "look & feel": "visual_language",
        "colours": "colours", "colors": "colours", "colour palette": "colours", "color palette": "colours",
        "typography": "typography", "fonts": "typography", "type": "typography",
        "logo": "logo_rules", "logo rules": "logo_rules",
        "photography": "photography", "photo style": "photography", "imagery": "photography",
        "product fidelity": "product_fidelity", "product accuracy": "product_fidelity",
        "positive prompts": "positive_prompts", "what to do": "positive_prompts",
        "negative prompts": "negative_prompts", "what to avoid": "negative_prompts", "do not": "negative_prompts",
        "creative properties": "creative_properties", "recurring properties": "creative_properties",
        "approved examples": "approved_examples", "good examples": "approved_examples",
        "rejected examples": "rejected_examples", "bad examples": "rejected_examples",
    }
    for section in sections[1:]:
        lines = section.strip().split("\n", 1)
        if len(lines) < 2:
            continue
        heading, body = lines
        heading_key = heading.strip().lower()
        field = heading_to_field.get(heading_key)
        if not field:
            continue
        if field in ("colours", "creative_properties", "approved_examples", "rejected_examples"):
            # List field — split by lines / bullets
            items = [re.sub(r"^[-*]\s+", "", l).strip() for l in body.strip().split("\n") if l.strip()]
            out[field] = items
        else:
            out[field] = body.strip()
    return out


def extract_from_freeform(text: str) -> Dict[str, Any]:
    """Heuristic extraction from a freeform brand description."""
    out: Dict[str, Any] = {f: "" if f not in ("colours", "creative_properties", "approved_examples", "rejected_examples") else [] for f in STRUCTURED_FIELDS}
    text_low = text.lower()
    # Voice — look for tone adjectives
    voice_words = []
    for w in ["warm", "cold", "clinical", "knowledgeable", "curious", "witty", "sarcastic", "insider", "professional", "casual", "friendly", "authoritative"]:
        if w in text_low:
            voice_words.append(w)
    if voice_words:
        out["voice"] = "Tone: " + ", ".join(voice_words[:5])
    # Colours — look for hex codes and colour names
    hexes = re.findall(r"#[0-9a-fA-F]{6}", text)
    out["colours"] = list(set(hexes))[:10]
    # Negatives — look for "do not", "never", "avoid"
    negatives = []
    for line in text.split("\n"):
        if any(w in line.lower() for w in ["never", "avoid", "do not", "don't"]):
            negatives.append(line.strip())
    out["negative_prompts"] = "\n".join(negatives[:10])
    return out


def retrieve_for_job(brand_id: str, *, lane: str = "product", job_type: str = "apparel", product_category: str = "") -> Dict[str, Any]:
    """Return only the bible fields relevant to a specific job.

    Per user directive PHASE L-7: 'retrieve only what is relevant to each job'.
    Different lanes and job types get different subsets.
    """
    bible = get_bible(brand_id)
    if not bible:
        return {"brand_id": brand_id, "available": False, "fields": {}}

    out = {
        "brand_id": brand_id,
        "available": True,
        "last_updated": bible.get("last_updated"),
        "fields": {},
    }

    # Always-on: voice, visual_language, logo_rules
    out["fields"]["voice"] = bible.get("voice", "")
    out["fields"]["visual_language"] = bible.get("visual_language", "")
    out["fields"]["logo_rules"] = bible.get("logo_rules", "")
    out["fields"]["colours"] = bible.get("colours", [])

    # Lane-specific
    if lane == "product":
        out["fields"]["product_fidelity"] = bible.get("product_fidelity", "")
        out["fields"]["positive_prompts"] = bible.get("positive_prompts", "")
        out["fields"]["negative_prompts"] = bible.get("negative_prompts", "")
        out["fields"]["creative_properties"] = bible.get("creative_properties", [])
        if product_category in ("apparel", "polo", "pants", "shirt", "tee", "cap", "hoodie", "jacket"):
            out["fields"]["photography"] = bible.get("photography", "")
        if product_category in ("iron", "wedge", "putter", "driver", "shaft", "grip", "ball", "bag"):
            out["fields"]["photography"] = bible.get("photography", "")
    elif lane == "human":
        out["fields"]["voice"] = bible.get("voice", "")
        out["fields"]["photography"] = bible.get("photography", "")
        out["fields"]["positive_prompts"] = bible.get("positive_prompts", "")
    elif lane == "campaign":
        out["fields"]["voice"] = bible.get("voice", "")
        out["fields"]["visual_language"] = bible.get("visual_language", "")
        out["fields"]["creative_properties"] = bible.get("creative_properties", [])

    return out


def get_bible_meta(brand_id: str) -> Dict[str, Any]:
    """Return just the metadata (used in brand settings display)."""
    bible = get_bible(brand_id)
    if not bible:
        return {"brand_id": brand_id, "available": False}
    return {
        "brand_id": brand_id,
        "available": True,
        "last_updated": bible.get("last_updated"),
        "format": bible.get("format"),
        "field_counts": {f: len(bible.get(f, [])) if isinstance(bible.get(f), list) else (1 if bible.get(f) else 0) for f in STRUCTURED_FIELDS},
    }
