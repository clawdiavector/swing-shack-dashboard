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
P12A_ANALYSIS_VERSION = "p12a-v0.2"

# Vision model — gpt-4o-mini supports image_url input.
P12A_VISION_MODEL = os.environ.get("CREATIVE_GENOME_VISION_MODEL", "gpt-4o-mini")

# Persistent paths (volume-backed on Railway)
P12A_DIR = Path(os.environ.get("DATA_DIR", "/data")) / "campaign-os" / "intelligence" / "creative-genome"
P12A_OBSERVATIONS = P12A_DIR / "observations.jsonl"
P12A_FRAMES_DIR = P12A_DIR / "frames"
P12A_CACHE = P12A_DIR / "cache.jsonl"  # {asset_id, content_hash, analysis_version, observation_id}

# ─── Initial observation schema ────────────────────────────────────────────
# Strictly visual. Each field has {value, confidence}. Unknown stays null
# for boolean / integer fields and "unknown" (enum) for categorical.

# Boolean fields: value is native bool or None (null)
P12A_BOOLEAN_FIELDS = [
    "human_present",
    "golf_club_present",
    "golf_ball_present",
    "screen_visible",
    "indoor",
    "outdoor",
    "text_overlay",
    "logo_visible",
    "face_visible",
    "golfer_present",
    "golf_bag_present",
    "golfer_swinging",
    "golfer_putting",
    "simulator_environment",
    "product_closeup",
    "human_dominant",
    "product_dominant",
    "environment_dominant",
]

# Integer fields: native int or None
P12A_INTEGER_FIELDS = [
    "people_count",
]

# Categorical fields (enum, may include "unknown")
P12A_CATEGORICAL_FIELDS = {
    "shot_type":          {"close_up", "medium", "wide", "mixed", "unknown"},
    "dominant_subject":   {"human", "product", "environment", "text", "mixed",
                           "unknown"},
}

# Combined schema (in order) — used by the model prompt + validator
P12A_OBSERVATION_FIELDS = P12A_BOOLEAN_FIELDS + P12A_INTEGER_FIELDS + list(
    P12A_CATEGORICAL_FIELDS.keys()
)


def _vision_system_prompt() -> str:
    """System prompt for blind visual observation.
    Explicitly forbids the model from using any caption / filename / context."""
    bools_list = ", ".join(P12A_BOOLEAN_FIELDS)
    ints_list = ", ".join(P12A_INTEGER_FIELDS)
    cats_list = ", ".join(
        f"{k}={sorted(v)}" for k, v in P12A_CATEGORICAL_FIELDS.items()
    )
    return (
        "You are a blind visual observer. You can ONLY see the image(s) "
        "provided.\n\n"
        "DO NOT use any caption, filename, hashtags, post text, campaign "
        "name, service name, product name, performance data, or historical "
        "classification. You will not be given any of those. Only the image.\n\n"
        "Return a single JSON object with the following schema. Each field "
        "is an object {value, confidence, visual_evidence}.\n\n"
        f"BOOLEAN FIELDS ({bools_list}):\n"
        '  value: true | false | null  (null = UNKNOWN, do NOT guess)\n'
        '  confidence: "high" | "medium" | "low"\n'
        '  visual_evidence: short string describing what you SAW.\n\n'
        f"INTEGER FIELDS ({ints_list}):\n"
        '  value: integer >= 0 OR null. People count only. null = unclear.\n\n'
        f"CATEGORICAL FIELDS ({cats_list}):\n"
        '  value: one of the listed enum values (or "unknown" if unclear).\n\n'
        "Rules:\n"
        '- DO NOT GUESS. If you genuinely cannot tell, value MUST be null '
        '(or "unknown" for categorical).\n'
        '- confidence MUST be "low" when you are unsure, "medium" when you '
        'are reasonably confident, "high" when the feature is clearly '
        'present OR clearly absent.\n'
        '- visual_evidence MUST describe what you saw, not what you '
        'inferred.\n'
        '- People: human_present=true if any person visible; '
        'golfer_present=true if you can tell they are a golfer (golf attire, '
        'holding a club, etc.); face_visible=true if their face is shown.\n'
        '- Composition: human_dominant / product_dominant / '
        'environment_dominant / text_dominant are NOT mutually exclusive. '
        'Set the ones that are clearly true; leave the others false.\n'
        '- shot_type: "close_up" (face/hand or product detail), "medium" '
        '(waist-up or full club), "wide" (full body / environment dominant), '
        '"mixed" (unclear which).\n\n'
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


def _download_image_raw(url: str, max_bytes: int = 12_000_000,
                          timeout: int = 30) -> Tuple[Optional[bytes], Optional[str]]:
    """Download image URL as raw bytes. Returns (bytes, content_type) or
    (None, error_string). Uses real browser user-agent for IG CDN."""
    user_agents = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "curl/8.4.0",
    ]
    last_err = None
    for ua in user_agents:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": ua,
                "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.5",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read(max_bytes + 1)
                if len(data) > max_bytes:
                    return None, f"image too large ({len(data)} > {max_bytes})"
                ctype = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                if not ctype.startswith("image/"):
                    last_err = f"not an image (content-type={ctype})"
                    continue
                return data, ctype
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = f"download error ({ua[:20]}): {type(e).__name__}: {e}"
            continue
    return None, last_err or "all user-agents failed"


def _download_image_to_b64(url: str, max_bytes: int = 12_000_000,
                            timeout: int = 30) -> Tuple[Optional[str], Optional[str]]:
    """Legacy: download image URL and return (base64_data_url, content_hash)
    or (None, error_string). Backed by _download_image_raw."""
    raw, ctype_or_err = _download_image_raw(url, max_bytes, timeout)
    if not raw:
        return None, ctype_or_err
    content_hash = hashlib.sha256(raw).hexdigest()[:16]
    data_url = _bytes_to_data_url(raw, ctype_or_err or "image/jpeg")
    return data_url, content_hash


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


def _make_analysis_derivative(raw_bytes: bytes, asset_id: str,
                                content_hash: str,
                                max_dim: int = 1024,
                                quality: int = 80) -> Tuple[Optional[bytes], Dict[str, Any]]:
    """Create a downscaled analysis derivative of the source image.

    - Resize so the longer edge is <= max_dim (default 1024).
    - Re-encode as JPEG at the given quality.
    - Returns (derivative_bytes, stats) where stats records original size,
      derivative size, original dimensions, derivative dimensions, ratio.

    The derivative is disposable infrastructure — it exists to keep the
    vision request small. The original asset is preserved by the caller
    before calling this function.

    If Pillow cannot decode the image, returns (None, stats_with_error).
    """
    stats: Dict[str, Any] = {
        "source_bytes": len(raw_bytes),
        "max_dim": max_dim,
        "quality": quality,
    }
    try:
        from PIL import Image
        import io as _io
    except Exception as e:
        stats["error"] = f"PIL not available: {e}"
        return None, stats

    try:
        src = Image.open(_io.BytesIO(raw_bytes))
        stats["source_dimensions"] = [src.width, src.height]
        src.load()
        # Convert palette / RGBA to RGB
        if src.mode in ("RGBA", "LA", "P"):
            src = src.convert("RGB")
        # Resize
        if max(src.width, src.height) > max_dim:
            if src.width >= src.height:
                new_w = max_dim
                new_h = int(src.height * (max_dim / src.width))
            else:
                new_h = max_dim
                new_w = int(src.width * (max_dim / src.height))
            src = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
        stats["derivative_dimensions"] = [src.width, src.height]
        out = _io.BytesIO()
        src.save(out, format="JPEG", quality=quality, optimize=True)
        derivative = out.getvalue()
        stats["derivative_bytes"] = len(derivative)
        stats["compression_ratio"] = round(len(derivative) / max(1, len(raw_bytes)), 3)
        # Save derivative as a stable artifact for inspection
        deriv_path = P12A_FRAMES_DIR / f"{asset_id}__{content_hash}__derivative.jpg"
        deriv_path.write_bytes(derivative)
        stats["derivative_path"] = str(deriv_path)
        return derivative, stats
    except Exception as e:
        stats["error"] = f"PIL processing failed: {type(e).__name__}: {e}"
        return None, stats


def _bytes_to_data_url(data: bytes, content_type: str = "image/jpeg") -> str:
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{b64}"


def _call_vision(data_url: str, asset_id: str, brand_id: str,
                 model: Optional[str] = None) -> Dict[str, Any]:
    """Send the image to OpenAI vision and parse the JSON response.
    NO caption / context is sent. Uses `model` if provided, else P12A_VISION_MODEL."""
    api_key = _resolve_openai_key()
    if not api_key:
        return {"error": "no_openai_key"}

    use_model = model or P12A_VISION_MODEL
    payload = {
        "model": use_model,
        "messages": [
            {"role": "system", "content": _vision_system_prompt()},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url,
                                                     # Use OpenAI's low-detail
                                                     # mode for cheaper
                                                     # classification when
                                                     # applicable. Set to
                                                     # "auto" if you want
                                                     # the model to choose.
                                                     "detail": "low"}},
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


def _validate_observation(obs: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Make sure each field has native-typed value + confidence.

    Returns (validated_observation, normalisation_warnings).
    Normalisation warnings are populated when the model returned something
    that had to be coerced (e.g. "true" string -> True bool, "0" string ->
    0 int, "unknown" -> null for boolean).

    Invalid outputs are normalised, never silently stored without trace.
    """
    warnings: List[str] = []

    def _coerce_bool(v: Any) -> Optional[bool]:
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("true", "yes", "1"):
                return True
            if s in ("false", "no", "0"):
                return False
            if s in ("unknown", "null", "none", "?"):
                return None
        return None  # unknown

    def _coerce_int(v: Any) -> Optional[int]:
        if v is None:
            return None
        if isinstance(v, int) and not isinstance(v, bool):
            return max(0, v)
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("unknown", "null", "none", "?", ""):
                return None
            # "3+" -> 3
            if s.endswith("+"):
                s = s[:-1]
            try:
                return max(0, int(s))
            except ValueError:
                return None
        return None

    def _coerce_enum(v: Any, allowed: set) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip().lower()
            if s in allowed:
                return s
            # Be lenient: "Unknown" -> "unknown"
            if s in ("unknown", "null", "none", "?"):
                return "unknown" if "unknown" in allowed else None
        return None

    def _coerce_confidence(v: Any) -> str:
        if isinstance(v, str) and v.lower() in {"high", "medium", "low"}:
            return v.lower()
        return "low"

    out: Dict[str, Any] = {}
    for field in P12A_BOOLEAN_FIELDS:
        raw = obs.get(field) or {}
        if not isinstance(raw, dict):
            raw = {}
            warnings.append(f"{field}: not an object, defaulted to unknown")
        v = _coerce_bool(raw.get("value"))
        if raw.get("value") not in (None, True, False) and v is None:
            warnings.append(f"{field}: value {raw.get('value')!r} normalised to null")
        out[field] = {
            "value": v,
            "confidence": _coerce_confidence(raw.get("confidence")),
            "visual_evidence": (raw.get("visual_evidence") or "")[:240],
        }

    for field in P12A_INTEGER_FIELDS:
        raw = obs.get(field) or {}
        if not isinstance(raw, dict):
            raw = {}
            warnings.append(f"{field}: not an object, defaulted to null")
        v = _coerce_int(raw.get("value"))
        if raw.get("value") is not None and v is None:
            warnings.append(f"{field}: value {raw.get('value')!r} normalised to null")
        out[field] = {
            "value": v,
            "confidence": _coerce_confidence(raw.get("confidence")),
            "visual_evidence": (raw.get("visual_evidence") or "")[:240],
        }

    for field, allowed in P12A_CATEGORICAL_FIELDS.items():
        raw = obs.get(field) or {}
        if not isinstance(raw, dict):
            raw = {}
            warnings.append(f"{field}: not an object, defaulted to unknown")
        v = _coerce_enum(raw.get("value"), allowed)
        if raw.get("value") is not None and v is None:
            warnings.append(f"{field}: value {raw.get('value')!r} not in enum, normalised to unknown")
        out[field] = {
            "value": v,
            "confidence": _coerce_confidence(raw.get("confidence")),
            "visual_evidence": (raw.get("visual_evidence") or "")[:240],
        }

    return out, warnings


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
    names. The canonical schema is loose so we look across common variants.
    `permalink` is explicitly excluded — it's a post page URL, not an image."""
    candidates = [
        "thumbnail_url", "media_url", "image_url",
        "preview_url", "display_url",
        # Note: 'url' and 'permalink' are EXCLUDED — permalink is the
        # Instagram post page, not the image. Generic 'url' is too ambiguous.
    ]
    for k in candidates:
        v = asset.get(k)
        if v and isinstance(v, str) and v.startswith(("http://", "https://")):
            # Quick heuristic: image URLs typically end in image extension
            # or come from CDN domains. Skip obvious post pages.
            if "instagram.com/p/" in v or "/p/" in v.split("?")[0]:
                continue
            return v
    # Also check nested dicts (non-post-page)
    for k, v in (asset.get("media") or {}).items() if isinstance(asset.get("media"), dict) else []:
        if isinstance(v, str) and v.startswith(("http://", "https://")) and "/p/" not in v:
            return v
    # And inside images[]
    images = asset.get("images") or []
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            return first.get("thumbnail_url") or first.get("url") or first.get("media_url")
        if isinstance(first, str) and "/p/" not in first:
            return first
    return None


def _resolve_image_url_via_meta(asset: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Fall back to Meta Graph API for IG-sourced assets. Returns
    (image_url, error_string). Requires the asset to carry an ig_media_id
    OR a numeric id we can use. Requires Meta credentials in env."""
    ig_media_id = asset.get("ig_media_id") or asset.get("source_media_id")
    # Some asset_ids are themselves numeric IG IDs (e.g. ig-18051415261918226)
    if not ig_media_id and str(asset.get("asset_id", "")).startswith("ig-"):
        ig_media_id = str(asset.get("asset_id"))[3:]
    if not ig_media_id or not ig_media_id.isdigit():
        return None, "no ig_media_id resolvable"
    # Pull token + account
    try:
        from _lib.meta_api import (
            _read_meta_access_token, _graph_get,
            MetaAuthError, MetaUpstreamError, MetaNetworkError,
        )
    except Exception as e:
        return None, f"meta_api import failed: {e}"
    token = _read_meta_access_token()
    if not token:
        return None, "no Meta access token"
    try:
        out = _graph_get(
            f"/{ig_media_id}",
            {"fields": "media_url,thumbnail_url,permalink"},
        )
        url = out.get("media_url") or out.get("thumbnail_url")
        if not url:
            return None, f"meta returned no media_url/thumbnail_url: {out}"
        return url, None
    except (MetaAuthError, MetaUpstreamError, MetaNetworkError) as e:
        return None, f"meta error: {type(e).__name__}: {e}"


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


def _load_observation_by_id(observation_id: str) -> Optional[Dict[str, Any]]:
    """Read one observation record from observations.jsonl by observation_id."""
    if not P12A_OBSERVATIONS.exists() or not observation_id:
        return None
    for line in P12A_OBSERVATIONS.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("observation_id") == observation_id:
            return rec
    return None


def observe_visual_asset(asset_id: str, brand_id: str,
                           use_derivative: bool = True,
                           max_dim: int = 1024,
                           quality: int = 80,
                           model: Optional[str] = None) -> Dict[str, Any]:
    """Slice B public entry point.

    Args:
      asset_id:       canonical asset id.
      brand_id:       brand scope (must match the asset's brand_id).
      use_derivative: if True, downscale + re-encode the image before
                      sending to the vision model (saves tokens). If False,
                      send the source bytes verbatim (for cost/quality
                      comparison tests).
      max_dim:        longest-edge cap for the derivative (default 1024).
      quality:        JPEG quality for the derivative (default 80).
      model:          override the default vision model.

    Returns the persisted observation record (ok=True) or a structured
    error (ok=False). All steps log warnings + persist the cache entry.
    """
    _ensure_dirs()

    asset = _find_asset(asset_id)
    if not asset:
        return {"ok": False, "error": f"asset_id '{asset_id}' not in canonical"}

    asset_brand = asset.get("brand_id") or brand_id
    if asset_brand and asset_brand != brand_id:
        return {"ok": False, "error": f"brand mismatch: asset={asset_brand} request={brand_id}"}

    media_type = asset.get("media_type") or "unknown"
    if media_type not in ("IMAGE", "CAROUSEL_ALBUM"):
        return {"ok": False, "error": f"slice A/B supports IMAGE / CAROUSEL_ALBUM only (got {media_type})"}

    image_url = _resolve_image_url(asset)
    image_url_source = "canonical_record"
    if not image_url:
        url, err = _resolve_image_url_via_meta(asset)
        if url:
            image_url = url
            image_url_source = "meta_graph_api"
        else:
            return {
                "ok": False,
                "error": "no usable image URL resolvable",
                "asset_keys": list(asset.keys()),
                "meta_attempt_error": err,
            }

    # Download source bytes
    raw, ctype_or_err = _download_image_raw(image_url)
    if not raw:
        return {
            "ok": False,
            "error": ctype_or_err or "image download failed",
            "image_url": image_url,
            "image_url_source": image_url_source,
        }
    source_content_hash = hashlib.sha256(raw).hexdigest()[:16]
    content_hash = source_content_hash  # backwards compat alias

    # Save source bytes as a stable artifact for inspection
    source_frame_path = _save_frame(asset_id, source_content_hash, raw)

    # Make analysis derivative (always — for inspection, even if not sent)
    derivative, deriv_stats = _make_analysis_derivative(
        raw, asset_id, source_content_hash,
        max_dim=max_dim, quality=quality,
    )

    # Cache key uses the SOURCE content hash (so derivative config doesn't
    # invalidate cache unnecessarily — we want one canonical observation
    # per asset content version).
    cached = _cache_lookup(asset_id, source_content_hash, P12A_ANALYSIS_VERSION)
    if cached:
        obs_id = cached.get("observation_id")
        existing = _load_observation_by_id(obs_id) if obs_id else None
        result = {
            "ok": True,
            "cached": True,
            "asset_id": asset_id,
            "brand_id": asset_brand,
            "media_type": media_type,
            "content_hash": source_content_hash,
            "analysis_version": P12A_ANALYSIS_VERSION,
            "vision_model": (existing or {}).get("vision_model") or (model or P12A_VISION_MODEL),
            "observation_id": obs_id,
            "derivative_stats": deriv_stats,
            "observations": (existing or {}).get("observations") or {},
            "normalisation_warnings": (existing or {}).get("normalisation_warnings") or [],
            "model_usage": None,  # no model call on cache hit
            "duration_ms": None,
        }
        return result

    # Choose what to send to the vision model
    if use_derivative and derivative:
        send_bytes = derivative
        send_source = "derivative"
        send_dimensions = deriv_stats.get("derivative_dimensions")
    else:
        send_bytes = raw
        send_source = "source"
        send_dimensions = None  # unknown — we didn't parse the source dims
    data_url = _bytes_to_data_url(send_bytes, "image/jpeg")

    # Call the vision model
    t0 = time.time()
    api_result = _call_vision(data_url, asset_id, asset_brand, model=model)
    if "error" in api_result:
        return {"ok": False, "error": api_result["error"]}
    obs, normalisation_warnings = _validate_observation(api_result.get("observation") or {})
    duration_ms = int((time.time() - t0) * 1000)

    record = {
        "asset_id": asset_id,
        "brand_id": asset_brand,
        "media_type": media_type,
        "analysis_version": P12A_ANALYSIS_VERSION,
        "vision_model": model or P12A_VISION_MODEL,
        "content_hash": source_content_hash,
        "image_url": image_url,
        "image_url_source": image_url_source,
        "image_url_fingerprint": hashlib.sha256(image_url.encode()).hexdigest()[:16],
        "source_frame_path": source_frame_path,
        "derivative_stats": deriv_stats,
        "image_sent_to_model": {
            "source": send_source,
            "bytes": len(send_bytes),
            "dimensions": send_dimensions,
        },
        "analysis_kind": "visual_observation",
        "pass": "A",
        "context_inputs_forbidden": [
            "caption", "hashtags", "filename", "campaign", "service",
            "topic", "product_name", "performance", "win_score",
            "historical_classification",
        ],
        "context_inputs_actually_sent": ["image_url (data URL) only"],
        "normalisation_warnings": normalisation_warnings,
        "observations": obs,
        "model_usage": api_result.get("usage") or {},
        "analysed_at": time.time(),
        "duration_ms": duration_ms,
    }
    obs_id = _append_observation(record)
    _cache_write(asset_id, source_content_hash, P12A_ANALYSIS_VERSION, obs_id)

    return {
        "ok": True,
        "cached": False,
        "asset_id": asset_id,
        "brand_id": asset_brand,
        "media_type": media_type,
        "content_hash": source_content_hash,
        "analysis_version": P12A_ANALYSIS_VERSION,
        "vision_model": model or P12A_VISION_MODEL,
        "image_url_source": image_url_source,
        "observation_id": obs_id,
        "observations": obs,
        "normalisation_warnings": normalisation_warnings,
        "model_usage": api_result.get("usage") or {},
        "duration_ms": duration_ms,
        "derivative_stats": deriv_stats,
    }
