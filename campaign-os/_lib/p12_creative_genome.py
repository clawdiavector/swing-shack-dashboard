"""
P1.2 Slice A — Blind IMAGE visual observation.

Strictly observational. The vision model receives ONLY the image (and
the schema it must fill in). It does NOT receive:

- caption
- hashtags
- filename
- campaign
- service / topic
- product name
- performance
- WIN score
- historical classification

The model returns a small structured JSON observation. Unknown stays
UNKNOWN.

Persistence: /data/campaign-os/intelligence/creative-genome/observations.jsonl
Cache key: (asset_id, content_hash, analysis_version) — re-runs only if
the asset changed OR the analysis version bumped.

This is intentionally the smallest viable vertical slice. Everything
else (Pass B inference, video, clustering, fatigue, ingredient
analysis, WIN profiles, white-space, get_visual_context) comes in
later slices.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_LOG = logging.getLogger(__name__)

# Schema version — bump to invalidate the cache.
P12A_ANALYSIS_VERSION = "p12a-v0.1"

# Vision model — gpt-4o-mini supports image_url input.
P12A_VISION_MODEL = os.environ.get("CREATIVE_GENOME_VISION_MODEL", "gpt-4o-mini")

# Persistent paths (volume-backed on Railway)
P12A_DIR = Path(os.environ.get("DATA_DIR", "/data")) / "campaign-os" / "intelligence" / "creative-genome"
P12A_OBSERVATIONS = P12A_DIR / "observations.jsonl"
P12A_FRAMES_DIR = P12A_DIR / "frames"
P12A_CACHE = P12A_DIR / "cache.jsonl"  # {asset_id, content_hash, analysis_version, observation_id}

# ─── Initial observation schema ────────────────────────────────────────────
# Strictly visual. Every field has {value, confidence}. Unknown stays UNKNOWN.

P12A_OBSERVATION_FIELDS = [
    "human_present",          # true | false | unknown
    "people_count",           # 0 | 1 | 2 | "3+" | unknown
    "golf_club_present",      # true | false | unknown
    "golf_ball_present",      # true | false | unknown
    "screen_visible",         # true | false | unknown  (TrackMan screen, sim display, monitor)
    "indoor",                 # true | false | unknown
    "outdoor",                # true | false | unknown
    "text_overlay",           # true | false | unknown
    "logo_visible",           # true | false | unknown
    "shot_type",              # close_up | medium | wide | unknown
    "dominant_subject",       # human | product | environment | text | mixed | unknown
]


def _vision_system_prompt() -> str:
    """System prompt for blind visual observation.
    Explicitly forbids the model from using any caption / filename / context."""
    fields_list = ", ".join(P12A_OBSERVATION_FIELDS)
    return (
        "You are a blind visual observer. You can ONLY see the image(s) "
        "provided.\n\n"
        "DO NOT use any caption, filename, hashtags, post text, campaign "
        "name, service name, product name, performance data, or historical "
        "classification. You will not be given any of those. Only the image.\n\n"
        "For each field below, return a strict JSON object:\n"
        f"{fields_list}\n\n"
        "Each field must have exactly:\n"
        '  "value": <one of the allowed values for that field>\n'
        '  "confidence": <"high" | "medium" | "low">\n'
        '  "visual_evidence": <short string describing what you SAW — '
        'e.g. "A torso wearing a black polo holding a driver", or "no '
        'humans visible in frame">\n\n'
        "Rules:\n"
        '- If a feature is genuinely unclear, value MUST be "unknown". '
        'NEVER guess.\n'
        '- indoor/outdoor: pick "unknown" if it cannot be told.\n'
        '- human_present: "true" only if you can see a person; "false" '
        'if not.\n'
        '- people_count: "0" | "1" | "2" | "3+" | "unknown".\n'
        '- shot_type: "close_up" (head/hand or product detail), "medium" '
        '(waist-up or full club), "wide" (full body / environment '
        'dominant), "unknown".\n'
        '- dominant_subject: pick the single subject that dominates the '
        'frame, or "mixed" / "unknown".\n\n'
        "Return ONLY the JSON object, no commentary, no markdown."
    )


def _vision_user_prompt() -> str:
    return (
        "Observe the image(s) above. Return a single JSON object with the "
        "schema specified."
    )


def _resolve_openai_key() -> Optional[str]:
    env = os.environ.get("OPENAI_API_KEY")
    if env:
        return env.strip()
    try:
        from _lib.image_gen_router import _resolve_openai_key as _r
        return _r() if _r() else None
    except Exception:
        return None


def _ensure_dirs() -> None:
    P12A_DIR.mkdir(parents=True, exist_ok=True)
    P12A_FRAMES_DIR.mkdir(parents=True, exist_ok=True)


def _download_image_to_b64(url: str, max_bytes: int = 8_000_000,
                            timeout: int = 30) -> Tuple[Optional[str], Optional[str]]:
    """Download an image URL and return (base64_data_url, content_hash) or
    (None, error_string)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "campaign-os/p12a"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(max_bytes + 1)
            if len(data) > max_bytes:
                return None, f"image too large ({len(data)} > {max_bytes})"
            ctype = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
            if not ctype.startswith("image/"):
                return None, f"not an image (content-type={ctype})"
            b64 = base64.b64encode(data).decode("ascii")
            content_hash = hashlib.sha256(data).hexdigest()[:16]
            data_url = f"data:{ctype};base64,{b64}"
            return data_url, content_hash
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        return None, f"download error: {type(e).__name__}: {e}"


def _save_frame(asset_id: str, content_hash: str, data_bytes: bytes) -> Optional[str]:
    """Save a stable frame copy under /data/.../creative-genome/frames/.
    Returns the saved path or None."""
    try:
        path = P12A_FRAMES_DIR / f"{asset_id}__{content_hash}.bin"
        if path.exists():
            return str(path)
        path.write_bytes(data_bytes)
        return str(path)
    except Exception as e:
        _LOG.warning("frame save failed: %s", e)
        return None


def _call_vision(data_url: str, asset_id: str, brand_id: str) -> Dict[str, Any]:
    """Send the image to OpenAI vision (gpt-4o-mini) and parse the JSON
    response. NO caption / context is sent."""
    api_key = _resolve_openai_key()
    if not api_key:
        return {"error": "no_openai_key"}

    payload = {
        "model": P12A_VISION_MODEL,
        "messages": [
            {"role": "system", "content": _vision_system_prompt()},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": _vision_user_prompt()},
            ]},
        ],
        "max_tokens": 800,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return {"error": f"openai_call_failed: {type(e).__name__}: {e}"}

    try:
        content = resp["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except Exception as e:
        return {"error": f"parse_failed: {e}", "raw": resp.get("choices", [{}])[0].get("message", {}).get("content", "")[:600]}

    return {"observation": parsed, "usage": resp.get("usage", {})}


def _validate_observation(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Make sure each field has value + confidence. Default missing fields to
    unknown so downstream can rely on the schema."""
    allowed_values = {
        "human_present":      {"true", "false", "unknown"},
        "people_count":       {"0", "1", "2", "3+", "unknown"},
        "golf_club_present":  {"true", "false", "unknown"},
        "golf_ball_present":  {"true", "false", "unknown"},
        "screen_visible":     {"true", "false", "unknown"},
        "indoor":             {"true", "false", "unknown"},
        "outdoor":            {"true", "false", "unknown"},
        "text_overlay":       {"true", "false", "unknown"},
        "logo_visible":       {"true", "false", "unknown"},
        "shot_type":          {"close_up", "medium", "wide", "unknown"},
        "dominant_subject":   {"human", "product", "environment", "text",
                                "mixed", "unknown"},
    }
    out = {}
    for field in P12A_OBSERVATION_FIELDS:
        raw = obs.get(field) or {}
        if not isinstance(raw, dict):
            raw = {}
        value = raw.get("value", "unknown")
        if value not in allowed_values[field]:
            value = "unknown"
        conf = raw.get("confidence", "low")
        if conf not in {"high", "medium", "low"}:
            conf = "low"
        evidence = (raw.get("visual_evidence") or "")[:240]
        out[field] = {
            "value": value,
            "confidence": conf,
            "visual_evidence": evidence,
        }
    return out


def _load_canonical_assets() -> List[Dict[str, Any]]:
    """Load canonical asset records (kind=asset) from the P0.6A cleaned
    canonical file."""
    try:
        # Path is defined in app.py (volume-backed)
        from app import _P06A_CLEAN_CANONICAL  # type: ignore
    except Exception:
        # Local dev fallback
        candidate = (
            Path(os.environ.get("DATA_DIR", "/data"))
            / "campaign-os" / "intelligence" / "history" / "p06a"
            / "canonical-history.cleaned.jsonl"
        )
        _P06A_CLEAN_CANONICAL = candidate  # type: ignore
    path = _P06A_CLEAN_CANONICAL  # type: ignore
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("kind") == "asset":
            out.append(r)
    return out


def _find_asset(asset_id: str) -> Optional[Dict[str, Any]]:
    for a in _load_canonical_assets():
        if a.get("asset_id") == asset_id:
            return a
    return None


def _resolve_image_url(asset: Dict[str, Any]) -> Optional[str]:
    """Find a usable image URL on the asset record, trying multiple field
    names. The canonical schema is loose so we look across common variants."""
    candidates = [
        "thumbnail_url", "media_url", "image_url",
        "preview_url", "url", "permalink", "display_url",
    ]
    for k in candidates:
        v = asset.get(k)
        if v and isinstance(v, str) and v.startswith(("http://", "https://", "data:")):
            return v
    # Also check nested dicts
    for k, v in (asset.get("media") or {}).items() if isinstance(asset.get("media"), dict) else []:
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            return v
    # And inside images[]
    images = asset.get("images") or []
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            return first.get("thumbnail_url") or first.get("url") or first.get("media_url")
        if isinstance(first, str):
            return first
    return None


def _cache_lookup(asset_id: str, content_hash: str,
                   analysis_version: str) -> Optional[Dict[str, Any]]:
    """Return the cached observation if (asset_id, content_hash, analysis_version)
    matches a previous run."""
    if not P12A_CACHE.exists():
        return None
    for line in P12A_CACHE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if (e.get("asset_id") == asset_id
                and e.get("content_hash") == content_hash
                and e.get("analysis_version") == analysis_version):
            return e
    return None


def _cache_write(asset_id: str, content_hash: str, analysis_version: str,
                 observation_id: str) -> None:
    with P12A_CACHE.open("a") as f:
        f.write(json.dumps({
            "asset_id": asset_id,
            "content_hash": content_hash,
            "analysis_version": analysis_version,
            "observation_id": observation_id,
            "cached_at": time.time(),
        }) + "\n")


def _append_observation(record: Dict[str, Any]) -> str:
    """Append the observation record to observations.jsonl and return its id."""
    _ensure_dirs()
    obs_id = f"obs_{int(time.time() * 1000)}_{record['asset_id']}"
    record = {"observation_id": obs_id, **record}
    with P12A_OBSERVATIONS.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return obs_id


def observe_visual_asset(asset_id: str, brand_id: str) -> Dict[str, Any]:
    """Slice A public entry point.

    1. Resolve the canonical asset.
    2. Download its image (thumbnail_url preferred, fall back to media_url).
    3. Send ONLY the image to the vision model (NO caption / context).
    4. Persist the observation.
    5. Return the observation + provenance.
    """
    _ensure_dirs()

    asset = _find_asset(asset_id)
    if not asset:
        return {"ok": False, "error": f"asset_id '{asset_id}' not in canonical"}

    asset_brand = asset.get("brand_id") or brand_id
    if asset_brand and asset_brand != brand_id:
        return {"ok": False, "error": f"brand mismatch: asset={asset_brand} request={brand_id}"}

    media_type = asset.get("media_type") or "unknown"
    # Slice A handles IMAGE and CAROUSEL_ALBUM (CAROUSEL gets a single representative
    # thumbnail). VIDEO comes in Slice D.
    if media_type not in ("IMAGE", "CAROUSEL_ALBUM"):
        return {"ok": False, "error": f"slice A supports IMAGE / CAROUSEL_ALBUM only (got {media_type})"}

    image_url = _resolve_image_url(asset)
    if not image_url:
        return {"ok": False, "error": "no thumbnail_url / media_url / image_url on asset", "asset_keys": list(asset.keys())}

    data_url, content_hash_or_err = _download_image_to_b64(image_url)
    if not data_url:
        return {"ok": False, "error": content_hash_or_err}
    content_hash: str = content_hash_or_err  # type: ignore[assignment]

    # Cache hit?
    cached = _cache_lookup(asset_id, content_hash, P12A_ANALYSIS_VERSION)
    if cached:
        return {
            "ok": True,
            "cached": True,
            "asset_id": asset_id,
            "brand_id": asset_brand,
            "media_type": media_type,
            "content_hash": content_hash,
            "analysis_version": P12A_ANALYSIS_VERSION,
            "observation_id": cached.get("observation_id"),
        }

    # Call the vision model
    t0 = time.time()
    api_result = _call_vision(data_url, asset_id, asset_brand)
    if "error" in api_result:
        return {"ok": False, "error": api_result["error"]}
    obs = _validate_observation(api_result.get("observation") or {})

    # Persist a stable frame copy (re-download would be needed; we don't
    # have raw bytes any more. Save the data_url as a small file so we can
    # inspect it later.)
    # NOTE: data_url is huge (base64); for now we save a tiny manifest
    # pointer. Slice D will do real frame extraction.
    frame_path = None

    record = {
        "asset_id": asset_id,
        "brand_id": asset_brand,
        "media_type": media_type,
        "analysis_version": P12A_ANALYSIS_VERSION,
        "vision_model": P12A_VISION_MODEL,
        "content_hash": content_hash,
        "image_url": image_url,
        "image_url_fingerprint": hashlib.sha256(image_url.encode()).hexdigest()[:16],
        "frame_path": frame_path,
        "analysis_kind": "visual_observation",
        "pass": "A",
        "context_inputs_forbidden": [
            "caption", "hashtags", "filename", "campaign", "service",
            "topic", "product_name", "performance", "win_score",
            "historical_classification",
        ],
        "context_inputs_actually_sent": ["image_url (data URL) only"],
        "observations": obs,
        "model_usage": api_result.get("usage") or {},
        "analysed_at": time.time(),
        "duration_ms": int((time.time() - t0) * 1000),
    }
    obs_id = _append_observation(record)
    _cache_write(asset_id, content_hash, P12A_ANALYSIS_VERSION, obs_id)

    return {
        "ok": True,
        "cached": False,
        "asset_id": asset_id,
        "brand_id": asset_brand,
        "media_type": media_type,
        "content_hash": content_hash,
        "analysis_version": P12A_ANALYSIS_VERSION,
        "vision_model": P12A_VISION_MODEL,
        "observation_id": obs_id,
        "observations": obs,
        "model_usage": api_result.get("usage") or {},
        "duration_ms": record["duration_ms"],
    }
