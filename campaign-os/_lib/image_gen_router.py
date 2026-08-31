"""
image_gen_router.py — Unified image generation + edit router for Campaign OS.

Single source of truth for all image ops in Campaign OS. Replaces ad-hoc
calls to OpenAI gpt-image-1 and gives every section (insights, hooks, meme
lord, billboards, captions, headlines, ctas, hashtagseo, performance,
campaigns, publish, review, imagegen, visualizer) the same wiring.

Three providers supported:
- openai       → POST https://api.openai.com/v1/images/generations (gpt-image-1)
- openrouter   → POST https://openrouter.ai/api/v1/chat/completions
                 (Nano Banana for both generate AND edit; gpt-5-image-mini
                 for the cheapest path; Nano Banana Pro for hero quality)

The router picks the provider via CAMPAIGN_OS_IMAGE_PROVIDER env var
(default: openrouter). The model is picked via CAMPAIGN_OS_IMAGE_MODEL
(default: google/gemini-2.5-flash-image). For per-request override, callers
pass `model=` to generate_image() / edit_image().

Credential resolution mirrors ubersuggest_mcp.py / meta_api.py:
- env var OPENROUTER_API_KEY (preferred) OR
- env var OPENROUTER_API_KEY_FILE (points to chmod-600 JSON) OR
- canonical fallback ~/.openclaw-instance2/workspace/clients/swing-shack/credentials/openrouter-api.json

Cost discipline: every call returns cost_estimate_usd from the upstream
usage payload when available; we never invent numbers. Edits where the
caller asked for "preserve logo / preserve text exactly" are flagged in the
return dict so the SPA can warn the user (the Nano Banana logo-drift
footgun is documented in the openrouter-image-edit SKILL.md).

Brand recipe injection: pass `brand_recipe=` (dict) to have it merged into
the prompt context (palette, mood, primary object). The recipe is what makes
"give me a swing shack post" produce on-brand work instead of generic golf.

Outputs are persisted to data/brand-directory/<brand>/images/gen-<ts>.png
plus .meta.json metadata sidecar — same convention as visual_library_generate.

Usage examples:

    # Backend
    from _lib.image_gen_router import generate_image, edit_image
    result = generate_image(
        prompt="Mizuno iron close-up, yellow accent",
        brand_id="swing-shack",
        size="1024x1024",
    )
    edited = edit_image(
        source_bytes=open("/path/to/img.png", "rb").read(),
        instruction="Change background to swing-shack green (#0f3a2e)",
        brand_id="swing-shack",
    )
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_LOG = logging.getLogger("campaign_os.image_gen_router")


def _krea_credentials_present() -> bool:
    """True if Krea MCP bearer token is configured (env or disk)."""
    try:
        from _lib import krea_mcp as _krea
        return _krea.credentials_present()
    except Exception:
        return False


def _call_krea_generate(
    *,
    prompt: str,
    model: str,
    aspect_ratio: str = "1:1",
    extra: Optional[dict] = None,
    timeout_s: int = 120,
) -> dict:
    """Submit an image-generation job to Krea AI.

    Returns the parsed MCP tools/call response (job_id + status).
    Caller polls via krea_mcp.get_job(job_id) and writes the URL to disk.
    Maps provider-exception taxonomy:
      - KreaAuthError / KreaNotConnectedError → ImageGenAuthError
      - KreaUpstreamError (HTTP 4xx/5xx)     → ImageGenUpstreamError
      - KreaNetworkError                     → ImageGenNetworkError
    """
    try:
        from _lib import krea_mcp as _krea
    except ImportError:
        raise ImageGenAuthError("Krea client not importable from _lib")
    try:
        return _krea.image_generate(
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            extra=extra,
        )
    except _krea.KreaNotConnectedError as e:
        raise ImageGenAuthError(f"Krea not connected: {e}")
    except _krea.KreaAuthError as e:
        raise ImageGenAuthError(f"Krea auth error: {e}")
    except _krea.KreaUpstreamError as e:
        raise ImageGenUpstreamError(
            f"Krea error ({e.status}): {e}", upstream=e.upstream, code=e.status
        )
    except _krea.KreaNetworkError as e:
        raise ImageGenNetworkError(f"Krea network: {e}")


# ── Provider endpoints ────────────────────────────────────────────────

OPENAI_ENDPOINT = "https://api.openai.com/v1/images/generations"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
KREA_ENDPOINT = "https://api.krea.ai/mcp"  # JSON-RPC 2.0 over HTTPS

# ── Defaults ──────────────────────────────────────────────────────────

DEFAULT_PROVIDER = "openrouter"  # OpenRouter wins: same model handles gen + edit
DEFAULT_MODEL_GEN = "google/gemini-2.5-flash-image"  # "Nano Banana"
DEFAULT_MODEL_EDIT = "google/gemini-2.5-flash-image"
DEFAULT_MODEL_CHEAP = "openai/gpt-5-image-mini"
DEFAULT_MODEL_HERO = "google/gemini-3-pro-image"  # "Nano Banana Pro"

# Canonical credential file (matches the convention used for Meta/Ubersuggest)
DEFAULT_OPENAI_TOKEN_FILE = (
    "/Users/fivefriday/.openclaw-instance2/workspace/"
    "clients/swing-shack/credentials/openai-api.json"
)
DEFAULT_OPENROUTER_TOKEN_FILE = (
    "/Users/fivefriday/.openclaw-instance2/workspace/"
    "clients/swing-shack/credentials/openrouter-api.json"
)
DEFAULT_OUTPUT_BASE = "data/brand-directory"  # written under <brand>/images/

# Size normalization (Nano Banana emits 1024² native; gpt-image-1 accepts 1024²/1792²)
_VALID_SIZES = {"1024x1024", "1024x1792", "1792x1024", "1536x1024", "1024x1536"}


# ── Exceptions ────────────────────────────────────────────────────────


class ImageGenAuthError(Exception):
    """Token missing, rejected, or insufficient credit."""


class ImageGenUpstreamError(Exception):
    """Other 4xx/5xx from upstream."""

    def __init__(self, message: str, *, upstream: dict | None = None, code: int | None = None):
        super().__init__(message)
        self.upstream = upstream or {}
        self.code = code


class ImageGenNetworkError(Exception):
    """Timeout / DNS / connection error."""


class ImageGenBadRequest(Exception):
    """Caller-side error (empty prompt, bad size, etc.)."""


# ── Result types ──────────────────────────────────────────────────────


@dataclass
class GenResult:
    """Returned by generate_image(). The .path is set if save=True."""

    bytes: bytes
    mime: str
    model: str
    provider: str
    cost_estimate_usd: float
    prompt_used: str
    revised_prompt: Optional[str] = None
    saved_path: Optional[str] = None
    saved_sidecar_path: Optional[str] = None
    warning: Optional[str] = None  # e.g. "logo-preserve likely to drift"
    usage: dict = field(default_factory=dict)
    # NEW (2026-08-12): brand_dna recipe summary for the UI Recipe panel.
    # None if no brand was given or brand_dna wasn't loaded.
    brand_recipe: Optional[dict] = None
    # NEW (2026-08-31): Provider-issued async job id (e.g. Krea). Routes
    # the caller to /api/krea/job-status?id=... for follow-up polling.
    provider_job_id: Optional[str] = None


@dataclass
class EditResult:
    """Returned by edit_image()."""

    bytes: bytes
    mime: str
    model: str
    provider: str
    cost_estimate_usd: float
    instruction_used: str
    saved_path: Optional[str] = None
    saved_sidecar_path: Optional[str] = None
    warning: Optional[str] = None
    usage: dict = field(default_factory=dict)


# ── Auth resolution ───────────────────────────────────────────────────


def _resolve_openai_key() -> Optional[str]:
    """Read OPENAI_API_KEY from env, then from canonical fallback file.

    Mirrors ubersuggest_mcp.py pattern: env-var wins, then JSON file with
    either "api_key" or "access_token" field.
    """
    raw = os.environ.get("OPENAI_API_KEY")
    if raw and raw.strip():
        return raw.strip()
    p = os.environ.get("OPENAI_API_KEY_FILE") or DEFAULT_OPENAI_TOKEN_FILE
    if p and os.path.exists(p):
        try:
            with open(p) as f:
                data = json.load(f)
            k = (data.get("api_key") or data.get("access_token") or "").strip()
            return k or None
        except Exception as e:
            _LOG.warning("could not read OPENAI_API_KEY_FILE=%s: %s", p, e)
    return None


def _resolve_openrouter_key() -> Optional[str]:
    raw = os.environ.get("OPENROUTER_API_KEY")
    if raw and raw.strip():
        return raw.strip()
    p = os.environ.get("OPENROUTER_API_KEY_FILE") or DEFAULT_OPENROUTER_TOKEN_FILE
    if p and os.path.exists(p):
        try:
            with open(p) as f:
                data = json.load(f)
            k = (data.get("api_key") or data.get("access_token") or "").strip()
            return k or None
        except Exception as e:
            _LOG.warning("could not read OPENROUTER_API_KEY_FILE=%s: %s", p, e)
    return None


def openai_credentials_present() -> bool:
    return bool(_resolve_openai_key())


def openrouter_credentials_present() -> bool:
    return bool(_resolve_openrouter_key())


# ── MIME detection from file bytes (NOT filename!) ────────────────────


def _detect_mime(buf: bytes) -> str:
    if buf.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if buf.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if buf[:4] == b"RIFF" and buf[8:12] == b"WEBP":
        return "image/webp"
    if buf[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "application/octet-stream"


def _data_url(buf: bytes) -> str:
    return f"data:{_detect_mime(buf)};base64,{base64.b64encode(buf).decode('ascii')}"


# ── Cost guard ────────────────────────────────────────────────────────

# Per-call USD ceiling to prevent a runaway prompt from blowing the budget.
# Default 50¢ per call is enough for ~12 Nano Banana 1024² images or ~150
# gpt-5-image-mini images. Caller can override via `max_cost_usd=`.
DEFAULT_MAX_COST_USD = 0.50


# ── Brand-recipe prompt enhancement ──────────────────────────────────


# Words that trigger the "logo-preserve likely to drift" warning.
# Generative models do NOT preserve logo/wordmark pixels faithfully —
# they re-render text. If the user asks for one of these, we surface
# the warning instead of silently producing a logo-drift result.
_PRESERVE_TRIGGERS = re.compile(
    r"\b(preserve|keep|don.?t change|do not change|leave)\b.{0,30}\b(text|logo|wordmark|brand name|slogan|tagline)\b",
    re.IGNORECASE | re.DOTALL,
)


def _detect_logo_preserve_drift(instruction: str) -> bool:
    """True iff the instruction asks the model to preserve text/logo pixels."""
    return bool(_PRESERVE_TRIGGERS.search(instruction or ""))


def _compose_full_prompt(
    user_prompt: str,
    *,
    brand_id: Optional[str] = None,
    brand_recipe: Optional[dict] = None,
    reference_dnas: Optional[list[dict]] = None,
    product_service_items: Optional[list[dict]] = None,
    learned_signals: Optional[dict] = None,
) -> str:
    """Compose the final prompt by stacking all 4 context layers.

    Order (matters — each layer constrains the next):
      1. Learned WIN PROFILE         (self-improvement signal from feedback loop)
      2. Reference DNA fragments      (visual look the user pointed at)
      3. Product / service fragments  (what we're selling)
      4. Brand recipe summary        (palette + mood + object summary)
      5. User's raw prompt           (the specific ask, last word on subject)

    All layers are optional and degrade gracefully if missing.
    """
    parts: list[str] = [user_prompt.strip()]

    # Layer 4: brand recipe (always lowest priority — sets the brand safety net)
    recipe_enhanced = enhance_prompt_with_recipe(user_prompt, brand_recipe)
    if recipe_enhanced != user_prompt.strip():
        # Strip the user's prompt from the recipe-enhanced version — keep only the additions
        addition = recipe_enhanced[len(user_prompt.strip()):].lstrip(". ")
        if addition:
            parts.append(addition)

    # Layer 3: product/service items
    if product_service_items:
        for item in product_service_items:
            try:
                from _lib.product_service_library import item_to_prompt
                frag = item_to_prompt(item, max_chars=400)
                if frag:
                    parts.append(frag)
            except Exception:
                continue

    # Layer 2: reference DNAs
    if reference_dnas:
        try:
            from _lib.reference_dna import reference_dna_to_prompt
            for ref in reference_dnas:
                frag = reference_dna_to_prompt(ref)
                if frag:
                    parts.append(frag)
        except Exception:
            pass

    # Layer 1: learned signals — prepended LAST so it has first word on style
    if learned_signals and learned_signals.get("ready"):
        try:
            from _lib.feedback_loop import signals_to_prompt
            win_frag = signals_to_prompt(learned_signals)
            if win_frag:
                parts.append(win_frag)
        except Exception:
            pass

    joined = " ".join(parts)
    return joined if joined else user_prompt.strip()


def enhance_prompt_with_recipe(prompt: str, recipe: Optional[dict]) -> str:
    """Merge brand recipe DNA into the caller's prompt. Returns the new prompt.

    Recipe shape (matches visual_library_recipe /api output):
      {
        "palette": {"primary": "orange"},
        "mood":    {"primary": "cinematic"},
        "objects": {"primary": "golf ball"},
        "summary": "...",
        ...
      }
    Only fields that pass a quality filter (not "other", "neutral", "general")
    are appended, so we don't poison a good prompt with junk.
    """
    if not recipe or not isinstance(recipe, dict):
        return prompt

    parts = [prompt.strip()]
    pal = (recipe.get("palette") or {}).get("primary")
    if pal and pal not in ("other", "neutral", None):
        parts.append(f"dominant color: {pal}")
    mood = (recipe.get("mood") or {}).get("primary")
    if mood and mood not in ("neutral", None):
        parts.append(f"mood: {mood}")
    obj = (recipe.get("objects") or {}).get("primary")
    if obj and obj not in ("general", None):
        parts.append(f"subject: {obj}")
    summary = (recipe.get("summary") or "").strip()
    # Skip junk summaries — too short to be useful, or generic fillers
    _JUNK_SUMMARY = {"ok", "n/a", "na", "none", "null", "-", "—", "tbd", "todo", "..."}
    if summary and len(summary) >= 6 and summary.lower() not in _JUNK_SUMMARY:
        # Cap to 200 chars to avoid poisoning the prompt
        parts.append(f"brand context: {summary[:200]}")
    return ". ".join(parts)


# ── OpenAI direct (gpt-image-1) ──────────────────────────────────────


def _call_openai_generate(
    *,
    prompt: str,
    model: str,
    size: str,
    n: int,
    timeout_s: int = 120,
) -> dict:
    key = _resolve_openai_key()
    if not key:
        raise ImageGenAuthError(
            "OpenAI key not configured. Set OPENAI_API_KEY env var or "
            "OPENAI_API_KEY_FILE / canonical fallback "
            f"{DEFAULT_OPENAI_TOKEN_FILE}."
        )
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": n,
    }).encode("utf-8")
    req = Request(
        OPENAI_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "campaign-os/image-gen/1.0",
        },
    )
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"error": {"message": str(e), "code": e.code}}
        upstream = err_body.get("error", err_body)
        code = e.code
        msg = upstream.get("message", "")
        if code in (401, 403):
            raise ImageGenAuthError(f"OpenAI auth failed ({code}): {msg}") from e
        raise ImageGenUpstreamError(
            f"OpenAI error ({code}): {msg}", upstream=upstream, code=code
        ) from e
    except URLError as e:
        raise ImageGenNetworkError(f"network error reaching OpenAI: {e}") from e


# ── OpenRouter (chat completions for both gen + edit) ─────────────────


def _call_openrouter_multimodal(
    *,
    content_chunks: Optional[list] = None,
    messages: Optional[list] = None,
    model: str,
    timeout_s: int = 120,
    stream: bool = False,
) -> dict:
    """POST to OpenRouter's chat completions endpoint.

    Two calling conventions (mutually exclusive):
      - content_chunks: list of multimodal content chunks (text + image_url).
                        Sent as a single user message.
      - messages: full messages list (system + user etc). Lets callers send a
                  system message + multimodal user content. Takes precedence
                  when both are passed.

    Refactored 2026-08-12 to support brand_dna's system-message + reference
    image pattern (see _lib/brand_dna.py).
    """
    key = _resolve_openrouter_key()
    if not key:
        raise ImageGenAuthError(
            "OpenRouter key not configured. Set OPENROUTER_API_KEY env var or "
            "OPENROUTER_API_KEY_FILE / canonical fallback "
            f"{DEFAULT_OPENROUTER_TOKEN_FILE}."
        )
    if messages is None:
        if content_chunks is None:
            raise ImageGenBadRequest(
                "_call_openrouter_multimodal needs messages= or content_chunks="
            )
        messages = [{"role": "user", "content": content_chunks}]
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        OPENROUTER_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "campaign-os/image-gen/1.0",
        },
    )
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"error": {"message": str(e), "code": e.code}}
        upstream = err_body.get("error", err_body)
        code = e.code
        msg = upstream.get("message", "")
        if code in (401, 403):
            raise ImageGenAuthError(f"OpenRouter auth failed ({code}): {msg}") from e
        raise ImageGenUpstreamError(
            f"OpenRouter error ({code}): {msg}", upstream=upstream, code=code
        ) from e
    except URLError as e:
        raise ImageGenNetworkError(f"network error reaching OpenRouter: {e}") from e


def _extract_image_from_openrouter_response(resp: dict) -> tuple[bytes, str]:
    """Pull the output image bytes from a chat-completions image-capable response.

    Schema (verified 2026-08-06 for google/gemini-2.5-flash-image):
        choices[0].message.images[0].image_url.url = "data:image/png;base64,..."
    """
    try:
        msg = resp["choices"][0]["message"]
        images = msg.get("images") or []
        if images:
            data_url = images[0]["image_url"]["url"]
        else:
            # Fallback: scan message stringification for any data: URL
            fallback = json.dumps(msg)
            if "data:image" not in fallback:
                raise ImageGenUpstreamError(
                    "no image in response", upstream={"response": resp}
                )
            data_url = "data:image" + fallback.split("data:image", 1)[1].split('"', 1)[0]
    except (KeyError, IndexError) as e:
        raise ImageGenUpstreamError(
            f"unexpected OpenRouter response shape: {e}",
            upstream={"response": resp},
        )
    if "," not in data_url:
        raise ImageGenUpstreamError(
            f"image url missing data payload: {data_url[:80]}",
            upstream={"response": resp},
        )
    head, b64 = data_url.split(",", 1)
    mime = "image/png"
    if ":" in head and ";" in head:
        mime = head.split(":", 1)[1].split(";", 1)[0]
    return base64.b64decode(b64), mime


def _cost_from_usage(usage: dict) -> float:
    """Best-effort cost extraction. Never invents numbers — returns 0.0 if missing."""
    if not isinstance(usage, dict):
        return 0.0
    cost = usage.get("cost")
    if cost is not None:
        try:
            return float(cost)
        except (TypeError, ValueError):
            pass
    return 0.0


# ── Persistence (save to brand directory + sidecar) ──────────────────


def _persist(
    *,
    brand_id: Optional[str],
    raw: bytes,
    mime: str,
    sidecar: dict,
    output_base: str,
) -> tuple[Optional[str], Optional[str]]:
    """Save image + .meta.json sidecar under data/brand-directory/<brand>/images/.

    Returns (saved_path, sidecar_path). Both None if no brand_id given.
    Filename: gen-<brand>-<unix_ts>.png (or .jpg based on mime).
    """
    if not brand_id:
        return None, None

    # Sanitize brand_id (no path traversal)
    safe_brand = re.sub(r"[^a-zA-Z0-9_\-]", "", brand_id)[:64] or "default"
    ext = "png" if "png" in mime else "jpg" if "jpeg" in mime or "jpg" in mime else "png"
    ts = int(time.time())
    fname = f"gen-{safe_brand}-{ts}.{ext}"

    save_dir = Path(output_base) / safe_brand / "images"
    save_dir.mkdir(parents=True, exist_ok=True)
    fpath = save_dir / fname
    fpath.write_bytes(raw)

    sidecar_path = save_dir / f"{fname}.meta.json"
    sidecar["saved_at"] = ts
    sidecar["saved_filename"] = fname
    sidecar_path.write_text(json.dumps(sidecar, indent=2))

    return str(fpath), str(sidecar_path)


# ── Public API: generate_image ────────────────────────────────────────


def generate_image(
    prompt: str,
    *,
    brand_id: Optional[str] = None,
    brand_recipe: Optional[dict] = None,
    reference_dnas: Optional[list[dict]] = None,
    product_service_items: Optional[list[dict]] = None,
    learned_signals: Optional[dict] = None,
    size: str = "1024x1024",
    n: int = 1,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    save: bool = True,
    output_base: str = DEFAULT_OUTPUT_BASE,
    max_cost_usd: float = DEFAULT_MAX_COST_USD,
    timeout_s: int = 120,
) -> GenResult:
    """Generate an image. Brand-aware (recipe-injected) when brand_recipe supplied.

    Args:
        prompt: User's text prompt. Empty / whitespace-only raises ImageGenBadRequest.
        brand_id: When save=True, files land under <output_base>/<brand_id>/images/.
                  None = no save, bytes returned only.
        brand_recipe: Optional recipe dict from /api/visual-library/<brand>/recipe.
                      When supplied, palette/mood/objects/summary merge into the prompt.
        reference_dnas: List of Reference DNA dicts to inject as visual style cues.
                         Each gets converted to a prompt fragment via reference_dna_to_prompt().
        product_service_items: List of product/service dicts from product_service_library.
                               Each gets converted via item_to_prompt() and injected.
        learned_signals: Learned WIN PROFILE dict from feedback_loop.
                         When supplied and 'ready', the signals prepend to the prompt.
        size: One of "1024x1024" (default), "1024x1792" (vertical), "1792x1024" (landscape).
              Nano Banana emits 1024² native; non-square sizes may be padded/cropped.
        n: Number of images (1-4). OpenRouter routes are typically 1; n>1 requires OpenAI.
        model: Override the model. Defaults: OpenRouter → Nano Banana; OpenAI → gpt-image-1.
        provider: Override the provider ("openai" or "openrouter"). Default = env or openrouter.
        save: If True and brand_id given, write to disk + sidecar.
        max_cost_usd: Soft ceiling; if upstream returns cost above this we surface a warning.
        timeout_s: Per-request timeout.

    Returns:
        GenResult — bytes, mime, model, cost, saved_path, etc.
    """
    if not prompt or not prompt.strip():
        raise ImageGenBadRequest("prompt is empty")

    size = size if size in _VALID_SIZES else "1024x1024"
    n = max(1, min(4, int(n)))

    provider = (
        provider
        or os.environ.get("CAMPAIGN_OS_IMAGE_PROVIDER")
        or DEFAULT_PROVIDER
    ).strip().lower()

    if provider == "openai":
        model = model or "gpt-image-1"
        if not openai_credentials_present():
            raise ImageGenAuthError(
                "OpenAI key not configured. Set OPENAI_API_KEY env var or "
                "OPENAI_API_KEY_FILE / canonical fallback "
                f"{DEFAULT_OPENAI_TOKEN_FILE}."
            )
        enhanced = _compose_full_prompt(
            prompt,
            brand_id=brand_id,
            brand_recipe=brand_recipe,
            reference_dnas=reference_dnas,
            product_service_items=product_service_items,
            learned_signals=learned_signals,
        )

        # NEW (2026-08-12): When a brand is given, prepend the brand_dna system
        # message into the prompt. OpenAI gpt-image-1 doesn't support image
        # inputs OR a system role — but it does read the user prompt carefully,
        # so we lead with the brand context as the first thing the model sees.
        recipe_summary: dict = {}
        if brand_id:
            try:
                from _lib.brand_dna import (
                    load_brand_context,
                    build_system_message,
                    build_recipe_summary,
                )
                brand_ctx = load_brand_context(brand_id)
                if brand_ctx.ok:
                    sys_msg = build_system_message(brand_ctx)
                    enhanced = f"{sys_msg}\n\n---\n\nUSER REQUEST: {enhanced}"
                recipe_summary = build_recipe_summary(brand_ctx)
            except Exception as e:
                _LOG.warning("brand_dna wiring failed for OpenAI path %s: %s", brand_id, e)

        api_resp = _call_openai_generate(
            prompt=enhanced, model=model, size=size, n=n, timeout_s=timeout_s
        )
        items = api_resp.get("data") or []
        if not items:
            raise ImageGenUpstreamError(
                "no image data in OpenAI response",
                upstream={"response": api_resp},
            )
        # Use first item for bytes
        item = items[0]
        b64 = item.get("b64_json") or ""
        if not b64:
            raise ImageGenUpstreamError(
                "OpenAI response missing b64_json",
                upstream={"item": item},
            )
        raw = base64.b64decode(b64)
        mime = "image/png"  # gpt-image-1 always returns PNG
        revised = item.get("revised_prompt", "")
        cost = 0.0
        usage = {}
        return GenResult(
            bytes=raw,
            mime=mime,
            model=model,
            provider=provider,
            cost_estimate_usd=cost,
            prompt_used=enhanced,
            revised_prompt=revised,
            warning=None,
            usage=usage,
            brand_recipe=recipe_summary or None,
        )
    elif provider == "krea":
        # Live Krea path: async job submission. Caller polls
        # /api/krea/job-status?id=<provider_job_id>.
        if not _krea_credentials_present():
            raise ImageGenAuthError(
                "Krea MCP not connected. Drop KREA_MCP_TOKEN via "
                "/secret-drop?slot=krea_mcp_token or set KREA_MCP_TOKEN env var."
            )
        model = model or os.environ.get(
            "CAMPAIGN_OS_KREA_DEFAULT_MODEL", "bfl/flux-1.1-pro"
        )
        enhanced = _compose_full_prompt(
            prompt,
            brand_id=brand_id,
            brand_recipe=brand_recipe,
            reference_dnas=reference_dnas,
            product_service_items=product_service_items,
            learned_signals=learned_signals,
        )
        # Add brand context if available
        if brand_id:
            try:
                from _lib.brand_dna import (
                    load_brand_context,
                    build_system_message,
                    build_recipe_summary,
                )
                brand_ctx = load_brand_context(brand_id)
                if brand_ctx.ok:
                    sys_msg = build_system_message(brand_ctx)
                    enhanced = f"{sys_msg}\n\n---\n\nUSER REQUEST: {enhanced}"
                recipe_summary = build_recipe_summary(brand_ctx)
            except Exception as e:
                _LOG.warning("brand_dna wiring failed for Krea path %s: %s", brand_id, e)
        aspect_ratio = size.replace("x", ":")
        kresp = _call_krea_generate(
            prompt=enhanced,
            model=model,
            aspect_ratio=aspect_ratio,
            timeout_s=timeout_s,
        )
        # Krea returns the job_id in 3 places — top-level, content[0].text
        # JSON, and structuredContent. Try all three. Verified 2026-08-31.
        sc = kresp.get("structuredContent") or {}
        job_id = (
            kresp.get("job_id")
            or sc.get("job_id")
            or kresp.get("job", {}).get("job_id")
            or ""
        )
        return GenResult(
            bytes=b"",
            mime="image/png",
            model=model,
            provider="krea",
            cost_estimate_usd=0.0,
            prompt_used=enhanced,
            revised_prompt=None,
            warning=None,
            usage={"krea_job_id": job_id, "krea_response": kresp},
            brand_recipe=recipe_summary or None,
            provider_job_id=job_id,
        )

    elif provider == "openrouter":
        model = model or os.environ.get("CAMPAIGN_OS_IMAGE_MODEL") or DEFAULT_MODEL_GEN
        if not openrouter_credentials_present():
            raise ImageGenAuthError(
                "OpenRouter key not configured. Set OPENROUTER_API_KEY env var or "
                "OPENROUTER_API_KEY_FILE / canonical fallback "
                f"{DEFAULT_OPENROUTER_TOKEN_FILE}."
            )
        # Live-tested 2026-08-31: OpenRouter image routes (e.g. Nano Banana)
        # can return 402 Payment Required when credits run out. Build the
        # composed prompt here so we can retry through Krea if the OR call
        # surfaces that specific upstream error.
        _composed_for_or = _compose_full_prompt(
            prompt,
            brand_id=brand_id,
            brand_recipe=brand_recipe,
            reference_dnas=reference_dnas,
            product_service_items=product_service_items,
            learned_signals=learned_signals,
        )

        # Build the legacy enhanced prompt (Layer 4 brand recipe tail, etc.)
        enhanced = _compose_full_prompt(
            prompt,
            brand_id=brand_id,
            brand_recipe=brand_recipe,
            reference_dnas=reference_dnas,
            product_service_items=product_service_items,
            learned_signals=learned_signals,
        )

        # NEW (2026-08-12): When a brand is given, build a multimodal
        # message payload with a hard system message + reference image chunks.
        # Falls back to the legacy text-only path if brand_dna is unavailable.
        messages = None
        recipe_summary: dict = {}
        if brand_id:
            try:
                from _lib.brand_dna import (
                    load_brand_context,
                    build_image_messages,
                    flatten_to_text,
                    build_recipe_summary,
                )
                brand_ctx = load_brand_context(brand_id)
                msgs = build_image_messages(brand_ctx, enhanced)
                if brand_ctx.ok:
                    messages = msgs
                else:
                    # Not enough brand context — flatten to text (no images,
                    # no system message); better than nothing.
                    messages = flatten_to_text(msgs)
                recipe_summary = build_recipe_summary(brand_ctx)
            except Exception as e:
                _LOG.warning("brand_dna wiring failed for %s, falling back: %s", brand_id, e)

        if messages is None:
            # Legacy path: single text content chunk, no system message
            messages = [{"role": "user", "content": enhanced.strip()}]

        try:
            api_resp = _call_openrouter_multimodal(
                content_chunks=None,
                messages=messages,
                model=model,
                timeout_s=timeout_s,
            )
        except ImageGenUpstreamError as e:
            # Live-tested 2026-08-31: OR returned 402 Payment Required.
            # If Krea is connected, transparently fall through to Krea so
            # the caller never sees "your credits ran out".
            if e.code == 402 and _krea_credentials_present():
                _LOG.warning(
                    "OpenRouter returned 402 — falling back to Krea for %s", brand_id
                )
                _fallback_brand = brand_id or "swing-shack"
                _kresp = _call_krea_generate(
                    prompt=_composed_for_or,
                    model=os.environ.get("CAMPAIGN_OS_KREA_FALLBACK_MODEL", "bfl/flux-1.1-pro"),
                    aspect_ratio=size.replace("x", ":"),
                    timeout_s=timeout_s,
                )
                _sc = _kresp.get("structuredContent") or {}
                _job_id = (
                    _kresp.get("job_id")
                    or _sc.get("job_id")
                    or _kresp.get("job", {}).get("job_id")
                    or ""
                )
                return GenResult(
                    bytes=b"",
                    mime="image/png",
                    model=os.environ.get("CAMPAIGN_OS_KREA_FALLBACK_MODEL", "bfl/flux-1.1-pro"),
                    provider="krea",
                    cost_estimate_usd=0.0,
                    prompt_used=_composed_for_or,
                    revised_prompt=None,
                    warning=f"OpenRouter 402 — fell through to Krea. job_id={_job_id}",
                    usage={"krea_job_id": _job_id, "openrouter_error": e.upstream},
                    brand_recipe=recipe_summary or None,
                    provider_job_id=_job_id,
                )
            raise
        raw, mime = _extract_image_from_openrouter_response(api_resp)
        usage = api_resp.get("usage") or {}
        cost = _cost_from_usage(usage)
        if cost > max_cost_usd:
            _LOG.warning(
                "openrouter generate cost $%.4f exceeded max_cost_usd $%.4f for %s",
                cost, max_cost_usd, model,
            )
        return GenResult(
            bytes=raw,
            mime=mime,
            model=model,
            provider=provider,
            cost_estimate_usd=cost,
            prompt_used=enhanced,
            revised_prompt=None,
            warning=(
                f"Cost ${cost:.4f} exceeds soft ceiling ${max_cost_usd:.2f}"
                if cost > max_cost_usd
                else None
            ),
            usage=usage,
            brand_recipe=recipe_summary or None,
        )

    else:
        raise ImageGenBadRequest(
            f"unknown provider {provider!r}; expected 'openai' or 'openrouter'"
        )


def generate_image_with_persistence(
    *args,
    **kwargs,
) -> GenResult:
    """Like generate_image() but always persists (assumes brand_id provided).

    Convenience wrapper used by the Flask routes — they know they want a save.
    """
    result = generate_image(*args, **kwargs)
    sidecar = {
        "prompt": kwargs.get("prompt"),
        "prompt_used": result.prompt_used,
        "revised_prompt": result.revised_prompt,
        "model": result.model,
        "provider": result.provider,
        "cost_estimate_usd": result.cost_estimate_usd,
        "usage": result.usage,
        "warning": result.warning,
        "size": kwargs.get("size", "1024x1024"),
    }
    saved, sidecar_path = _persist(
        brand_id=kwargs.get("brand_id"),
        raw=result.bytes,
        mime=result.mime,
        sidecar=sidecar,
        output_base=kwargs.get("output_base", DEFAULT_OUTPUT_BASE),
    )
    if saved:
        # Patch up the GenResult with new fields
        result.saved_path = saved
        result.saved_sidecar_path = sidecar_path
    return result


# ── Public API: edit_image ────────────────────────────────────────────


def edit_image(
    source_bytes: bytes,
    instruction: str,
    *,
    brand_id: Optional[str] = None,
    extra_image_bytes: Optional[list[bytes]] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    save: bool = True,
    output_base: str = DEFAULT_OUTPUT_BASE,
    max_cost_usd: float = DEFAULT_MAX_COST_USD,
    timeout_s: int = 120,
) -> EditResult:
    """Edit `source_bytes` per `instruction`. Returns raw output PNG bytes.

    Args:
        source_bytes: Input image bytes (PNG / JPEG / WebP / GIF).
        instruction: Natural-language edit instruction. e.g.
                     "Change the background to swing-shack green."
        brand_id: When save=True, files land under <output_base>/<brand_id>/images/.
        extra_image_bytes: Optional list of additional reference images (style
                           transfer, brand-template overlay, etc.). Each is
                           appended as a separate `image_url` chunk.
        model: Override model. Default: google/gemini-2.5-flash-image (Nano Banana).
        provider: Override provider. Default: openrouter (the only path that supports
                  multimodal input; OpenAI direct does not support edit).
        save: If True and brand_id given, write to disk + sidecar.

    Returns:
        EditResult — bytes, mime, model, cost, saved_path, warning, etc.
    """
    if not source_bytes:
        raise ImageGenBadRequest("source_bytes is empty")
    if not instruction or not instruction.strip():
        raise ImageGenBadRequest("instruction is empty")

    provider = (
        provider
        or os.environ.get("CAMPAIGN_OS_IMAGE_PROVIDER")
        or DEFAULT_PROVIDER
    ).strip().lower()

    if provider != "openrouter":
        raise ImageGenBadRequest(
            f"provider {provider!r} does not support image edit. "
            "Use 'openrouter' (default) — OpenAI direct /v1/images/generations "
            "is text-to-image only."
        )

    model = model or os.environ.get("CAMPAIGN_OS_IMAGE_MODEL") or DEFAULT_MODEL_EDIT
    if not openrouter_credentials_present():
        raise ImageGenAuthError(
            "OpenRouter key not configured. Set OPENROUTER_API_KEY env var or "
            f"OPENROUTER_API_KEY_FILE / canonical fallback {DEFAULT_OPENROUTER_TOKEN_FILE}."
        )

    warning: Optional[str] = None
    if _detect_logo_preserve_drift(instruction):
        warning = (
            "Generative models re-render text — preserving logo / wordmark "
            "pixels is not reliable. For brand-asset edits, use client-side "
            "PIL recolour instead."
        )

    content: list = [
        {"type": "text", "text": instruction.strip()},
        {"type": "image_url", "image_url": {"url": _data_url(source_bytes)}},
    ]
    for extra in (extra_image_bytes or []):
        if extra:
            content.append({"type": "image_url", "image_url": {"url": _data_url(extra)}})

    api_resp = _call_openrouter_multimodal(
        content_chunks=content,
        model=model,
        timeout_s=timeout_s,
    )
    raw, mime = _extract_image_from_openrouter_response(api_resp)
    usage = api_resp.get("usage") or {}
    cost = _cost_from_usage(usage)
    if cost > max_cost_usd:
        _LOG.warning(
            "openrouter edit cost $%.4f exceeded max_cost_usd $%.4f for %s",
            cost, max_cost_usd, model,
        )

    result = EditResult(
        bytes=raw,
        mime=mime,
        model=model,
        provider=provider,
        cost_estimate_usd=cost,
        instruction_used=instruction.strip(),
        warning=(
            warning
            or (f"Cost ${cost:.4f} exceeds soft ceiling ${max_cost_usd:.2f}"
                if cost > max_cost_usd else None)
        ),
        usage=usage,
    )
    if save and brand_id:
        sidecar = {
            "operation": "edit",
            "instruction": instruction.strip(),
            "model": model,
            "provider": provider,
            "cost_estimate_usd": cost,
            "usage": usage,
            "warning": result.warning,
            "source_size_bytes": len(source_bytes),
        }
        saved, sidecar_path = _persist(
            brand_id=brand_id,
            raw=raw,
            mime=mime,
            sidecar=sidecar,
            output_base=output_base,
        )
        if saved:
            result.saved_path = saved
            result.saved_sidecar_path = sidecar_path
    return result


# ── Status companion (for /api/image/status) ──────────────────────────


def status_report() -> dict:
    """Lightweight status blurb for the SPA. Never echoes any key."""
    openai_ok = openai_credentials_present()
    openrouter_ok = openrouter_credentials_present()

    default_provider = (
        os.environ.get("CAMPAIGN_OS_IMAGE_PROVIDER") or DEFAULT_PROVIDER
    ).strip().lower()

    return {
        "configured": openrouter_ok or openai_ok,
        "providers": {
            "openai": {
                "configured": openai_ok,
                "model_default": "gpt-image-1",
                "supports_edit": False,
            },
            "openrouter": {
                "configured": openrouter_ok,
                "model_default_gen": DEFAULT_MODEL_GEN,
                "model_default_edit": DEFAULT_MODEL_EDIT,
                "model_cheap": DEFAULT_MODEL_CHEAP,
                "model_hero": DEFAULT_MODEL_HERO,
                "supports_edit": True,
            },
        },
        "active_provider": default_provider,
        "active_model": (
            os.environ.get("CAMPAIGN_OS_IMAGE_MODEL") or DEFAULT_MODEL_GEN
        ),
        "valid_sizes": sorted(_VALID_SIZES),
        "max_cost_default_usd": DEFAULT_MAX_COST_USD,
    }


# ── Smoke-test entry point ────────────────────────────────────────────


if __name__ == "__main__":  # pragma: no cover
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    print("image_gen_router status:")
    print(json.dumps(status_report(), indent=2))
    sys.exit(0)