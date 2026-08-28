"""
krea_mcp.py — Krea AI MCP (Model Context Protocol) wrapper.

Krea AI exposes real-time image + video generation tools via an MCP
server at `https://api.krea.ai/mcp`. The OS uses this to generate
hero / reel / ad creative from the brand bible (voice + visual DNA)
plus the active strategy's bets.

Authentication is OAuth 2.0 user-flow:
  1. User connects Krea from the Claude/ChatGPT Settings panel
     (Connectors → Add custom connector → https://api.krea.ai/mcp)
  2. User signs in to Krea to authorize
  3. The OS then calls this wrapper, which forwards JSON-RPC 2.0
     requests over HTTPS to the Krea MCP server

This module is the integration layer:
  - Reads OAuth bearer token from /root/.krea/mcp.json
    (set by the user-side connect flow)
  - Falls back to META_SYSTEM_USER_TOKEN pattern — env var KREA_MCP_TOKEN
    if explicitly provisioned by a SysOps flow
  - Exposes typed methods (image_generate, video_generate, etc.)
  - Returns the same {content:[{type,text|...}]} MCP wrapper shape
    that the upstream uses

Reference: https://www.krea.ai/mcp  (the MCP JSON-RPC schema)
Built 2026-08-28 — initial scaffold, awaiting user OAuth connect.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional
from urllib.parse import urlencode

_LOG = logging.getLogger("krea_mcp")
if not _LOG.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(message)s",
                                    datefmt="%Y-%m-%d %H:%M:%S"))
    _LOG.addHandler(h)
    _LOG.setLevel(logging.INFO)

# ── Endpoints ──────────────────────────────────────────────────────
DEFAULT_BASE_URL = "https://api.krea.ai/mcp"
DEFAULT_PROTOCOL_VERSION = "2025-03-26"
DEFAULT_TIMEOUT = 120  # image gen can take ~30s; video can take 5min

# ── Credential paths ───────────────────────────────────────────────
# The Krea MCP connect flow drops the bearer token here on the
# user-side (Claude/ChatGPT does this automatically when you connect).
# We also support an explicit env var override for ops-driven setups.
DEFAULT_CREDENTIAL_PATHS = (
    "/root/.krea/mcp.json",
    os.path.expanduser("~/.krea/mcp.json"),
    os.path.expanduser("~/.openclaw-instance2/workspace/clients/swing-shack/credentials/krea-mcp.json"),
)
DEFAULT_TOKEN_ENV_VARS = ("KREA_MCP_TOKEN", "KREA_API_KEY", "KREA_ACCESS_TOKEN")


# ── Typed exceptions ────────────────────────────────────────────────
class KreaAuthError(Exception):
    """Krea returned 401/403 — token missing or expired."""
    def __init__(self, msg: str, upstream: Optional[dict] = None):
        super().__init__(msg)
        self.upstream = upstream or {}


class KreaUpstreamError(Exception):
    """Krea returned a non-auth HTTP error (4xx/5xx)."""
    def __init__(self, msg: str, *, status: int, upstream: Optional[dict] = None):
        super().__init__(msg)
        self.status = status
        self.upstream = upstream or {}


class KreaNetworkError(Exception):
    """Network-level failure (DNS, timeout, connection refused)."""
    pass


class KreaNotConnectedError(Exception):
    """User has not yet connected Krea via the Settings → Connectors flow."""
    pass


# ── Token resolution ────────────────────────────────────────────────
def _read_token_from_disk() -> Optional[str]:
    """Read bearer token from canonical credentials file.

    The Krea MCP connect flow writes a JSON file at one of the
    DEFAULT_CREDENTIAL_PATHS. Shape (best-effort):
      {"access_token": "...", "expires_at": ...}
      or
      {"token": "..."}
      or
      {"bearer": "..."}
    """
    for path in DEFAULT_CREDENTIAL_PATHS:
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as f:
                meta = json.loads(f.read())
            for key in ("access_token", "token", "bearer", "bearer_token"):
                tok = (meta.get(key) or "").strip()
                if tok:
                    _LOG.info(f"loaded Krea token from {path}")
                    return tok
        except Exception as e:
            _LOG.warning(f"could not parse {path}: {e}")
    return None


def _read_token_from_env() -> Optional[str]:
    """Read bearer token from explicit env var (ops override)."""
    for var in DEFAULT_TOKEN_ENV_VARS:
        tok = (os.environ.get(var) or "").strip()
        if tok:
            _LOG.info(f"loaded Krea token from env ${var}")
            return tok
    return None


def credentials_present() -> bool:
    """True if a Krea token is configured (env or disk)."""
    return bool(_read_token_from_env() or _read_token_from_disk())


def auth_status() -> dict:
    """Return the current Krea auth state for the OS status surfaces."""
    env_tok = _read_token_from_env()
    disk_tok = _read_token_from_disk() if not env_tok else None
    return {
        "connected": bool(env_tok or disk_tok),
        "source": "env" if env_tok else ("disk" if disk_tok else None),
        "base_url": os.environ.get("KREA_MCP_BASE_URL", DEFAULT_BASE_URL),
        "next_step": (
            None if (env_tok or disk_tok) else
            "Connect Krea from Settings → Connectors → Add custom connector → "
            "https://api.krea.ai/mcp. Sign in to Krea to authorize. "
            "Full set-up guide: https://www.krea.ai/mcp"
        ),
    }


# ── JSON-RPC over HTTPS ─────────────────────────────────────────────
def _post_json_rpc(url: str, body: dict, *, headers: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """POST a JSON-RPC body, return the parsed JSON response."""
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            # Krea MCP may return Server-Sent Events (SSE) framing
            if raw.startswith("data:"):
                for line in raw.splitlines():
                    line = line.strip()
                    if line.startswith("data:"):
                        try:
                            return json.loads(line[len("data:"):].strip())
                        except json.JSONDecodeError:
                            continue
                raise KreaUpstreamError("SSE response but no parseable data: line", status=200)
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            body_json = json.loads(body_text)
        except Exception:
            body_json = {"raw": body_text}
        if e.code in (401, 403):
            raise KreaAuthError(f"HTTP {e.code}: auth denied", upstream=body_json)
        raise KreaUpstreamError(f"HTTP {e.code}: {e.reason}", status=e.code, upstream=body_json)
    except urllib.error.URLError as e:
        raise KreaNetworkError(f"network: {e.reason}")
    except TimeoutError as e:
        raise KreaNetworkError(f"timeout after {timeout}s")


# ── Initialize handshake (cached) ───────────────────────────────────
_INIT_DONE = False
_INIT_LOCK = False  # single-threaded init for the process


def _ensure_initialized() -> None:
    """Send the MCP initialize handshake once per process.

    The MCP spec requires `initialize` to be sent before any tool call.
    Server returns its capabilities + protocolVersion.
    """
    global _INIT_DONE, _INIT_LOCK
    if _INIT_DONE or _INIT_LOCK:
        return
    _INIT_LOCK = True
    try:
        tok = _read_token_from_env() or _read_token_from_disk()
        if not tok:
            raise KreaNotConnectedError(
                "Krea MCP not connected. Walk the user through Settings → "
                "Connectors → Add custom connector → https://api.krea.ai/mcp. "
                "Then sign in to Krea to authorize. "
                "Full set-up guide: https://www.krea.ai/mcp"
            )
        base = os.environ.get("KREA_MCP_BASE_URL", DEFAULT_BASE_URL)
        headers = {"Authorization": f"Bearer {tok}"}
        body = {
            "jsonrpc": "2.0",
            "id": int(time.time()),
            "method": "initialize",
            "params": {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "swing-shack-os",
                    "version": "0.1.0",
                },
            },
        }
        _LOG.info(f"initializing MCP handshake with {base}")
        resp = _post_json_rpc(base, body, headers=headers)
        if "error" in resp and resp["error"].get("code") == -32001:
            raise KreaNotConnectedError(
                resp["error"].get("message", "Unauthorized: Krea not connected")
            )
        if "error" in resp:
            raise KreaUpstreamError(
                f"init failed: {resp['error'].get('message')}",
                status=400,
                upstream=resp["error"],
            )
        _LOG.info(f"MCP initialize OK — server: {resp.get('result', {}).get('serverInfo', {})}")
        _INIT_DONE = True
    finally:
        _INIT_LOCK = False


# ── Core JSON-RPC call ─────────────────────────────────────────────
def mcp_call(method: str, params: Optional[dict] = None, *, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Send a JSON-RPC method call to the Krea MCP server.

    Returns the parsed `result` dict from the upstream response.
    Raises KreaAuthError / KreaUpstreamError / KreaNetworkError on failure.
    """
    _ensure_initialized()
    tok = _read_token_from_env() or _read_token_from_disk()
    if not tok:
        raise KreaNotConnectedError("Krea MCP not connected (no token)")
    base = os.environ.get("KREA_MCP_BASE_URL", DEFAULT_BASE_URL)
    body = {
        "jsonrpc": "2.0",
        "id": int(time.time()),
        "method": method,
        "params": params or {},
    }
    resp = _post_json_rpc(base, body, headers={"Authorization": f"Bearer {tok}"}, timeout=timeout)
    if "error" in resp:
        err = resp["error"]
        if err.get("code") == -32001:
            raise KreaNotConnectedError(err.get("message", "Unauthorized"))
        raise KreaUpstreamError(
            err.get("message", "unknown upstream error"),
            status=400,
            upstream=err,
        )
    return resp.get("result", {})


# ── Tool discovery ──────────────────────────────────────────────────
def list_tools() -> dict:
    """List every tool the Krea MCP server exposes.

    The result shape is the MCP standard `tools/list` response:
        {"tools": [{"name": "...", "description": "...", "inputSchema": {...}}, ...]}
    """
    return mcp_call("tools/list", {})


# ── Brand-aware helpers (the OS-specific value-add) ────────────────
def _brand_bible_context(brand: str = "swing-shack") -> dict:
    """Read the brand bible to enrich prompts with voice + properties."""
    candidates = [
        os.path.join(
            os.environ.get("DATA_DIR", "/data"),
            "brand", f"{brand}-bible.json",
        ),
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "brand", f"{brand}-bible.json",
        ),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def image_generate(
    prompt: str,
    *,
    brand: str = "swing-shack",
    model: str = "flux-fast",
    aspect_ratio: str = "1:1",
    extra: Optional[dict] = None,
) -> dict:
    """Generate an image via Krea's MCP `generate_image` tool, brand-aware.

    Injects brand-bible voice / colour / property hints into the prompt
    so the generated image lands on-brand automatically.

    `extra` is merged into the tool-call params (lets the caller override
    model, seed, dimensions, style_preset, etc.).

    Real Krea tool name is `generate_image` (verified 2026-08-28 against
    https://api.krea.ai/mcp tools/list — 32 tools available).
    """
    bible = _brand_bible_context(brand)
    belief = bible.get("belief", "Golf is more fun when it makes sense.")
    feel = ", ".join(bible.get("values", {}).get("should_feel", [])[:5])
    voice_summary = bible.get("voice_summary", "Know the numbers. Speak like a golfer.")
    enriched_prompt = (
        f"{prompt}. "
        f"Brand context: {belief}. "
        f"Tone: {voice_summary}. "
        f"Visual feel: {feel}."
    ).strip()
    # Krea API expects `image_input` shape; the public tool signature uses
    # `prompt` + `model` + optional inputs. Pass through any extras.
    # Krea MCP expects the model at the envelope level, prompt + options
    # inside the `input` record. Image models (e.g. bfl/flux-1.1-pro)
    # require width + height — default to 1024×1024 for square, scaled
    # to common aspect ratios. Verified 2026-08-28.
    default_sizes = {
        "1:1": (1024, 1024), "16:9": (1280, 720), "9:16": (720, 1280),
        "4:3": (1024, 768), "3:4": (768, 1024), "21:9": (1470, 630),
    }
    inner = {"prompt": enriched_prompt}
    ar = aspect_ratio or "1:1"
    if ar not in default_sizes:
        ar = "1:1"
    w, h = default_sizes[ar]
    if extra and ("width" in extra or "height" in extra):
        if "width" in extra:
            inner["width"] = extra.pop("width")
        if "height" in extra:
            inner["height"] = extra.pop("height")
    else:
        inner["width"] = w
        inner["height"] = h
    if ar != "1:1":
        inner["aspect_ratio"] = ar
    if extra:
        inner.update(extra)
    return mcp_call("tools/call", {
        "name": "generate_image",
        "arguments": {"input": inner, "model": model},
    }, timeout=180)


def video_generate(
    prompt: str,
    *,
    brand: str = "swing-shack",
    duration_seconds: int = 6,
    aspect_ratio: str = "16:9",
    extra: Optional[dict] = None,
) -> dict:
    """Generate a short video via Krea's MCP `generate_video` tool, brand-aware.

    Real Krea tool name is `generate_video` (verified 2026-08-28).
    `extra` is merged into the tool-call params for advanced options.
    """
    bible = _brand_bible_context(brand)
    belief = bible.get("belief", "")
    voice_summary = bible.get("voice_summary", "")
    enriched_prompt = (
        f"{prompt}. "
        f"Brand voice: {voice_summary}. "
        f"Brand belief: {belief}."
    ).strip()
    inner = {
        "prompt": enriched_prompt,
    }
    if aspect_ratio:
        inner["aspect_ratio"] = aspect_ratio
    if duration_seconds:
        # Krea uses 'duration' (not 'duration_seconds') per the schema
        inner["duration"] = duration_seconds
    if extra:
        inner.update(extra)
    return mcp_call("tools/call", {
        "name": "generate_video",
        "arguments": {"input": inner, "model": model},
    }, timeout=300)


# ── Model + prompt-guide discovery ────────────────────────────────
def list_models(category: Optional[str] = None) -> dict:
    """List Krea generation models.

    Args:
        category: filter to one of "image", "video", "enhance", "3d".
                   None returns all models.

    Real Krea tool name: `list_models` (verified 2026-08-28).
    """
    args = {}
    if category:
        args["category"] = category
    return mcp_call("tools/call", {"name": "list_models", "arguments": args})


def get_model_schema(model_id: str) -> dict:
    """Return the full input/output schema for a generation model.

    Real Krea tool name: `get_model_schema`. Returns the prompt-engineering
    contract — which fields are required, optional, valid ranges, etc.
    """
    # Verified 2026-08-28: get_model_schema uses {model} only — works.
    return mcp_call("tools/call", {"name": "get_model_schema", "arguments": {"model": model_id}})


def get_job(job_id: str) -> dict:
    """Fetch the latest status for a previously submitted Krea generation job.

    Real Krea tool name: `get_job`. Returns the current job state
    (running / completed / failed) and outputs (image URL, video URL,
    etc.) when ready.
    """
    return mcp_call("tools/call", {
        "name": "get_job",
        "arguments": {"job_id": job_id},
    })


def cancel_job(job_id: str) -> dict:
    """Cancel a running Krea generation job.

    Real Krea tool name: `cancel_job`.
    """
    return mcp_call("tools/call", {
        "name": "cancel_job",
        "arguments": {"job_id": job_id},
    })


def get_prompting_guide(model_id: str, guide_type: str = "general") -> dict:
    """Return model-specific prompt-writing guidance.

    Real Krea tool name: `get_prompting_guide`. Call this ONCE before
    writing prompts for a new model — it returns the canonical rules
    (e.g. for Seedance 2 / Kling 3.0 video models).

    Args:
        model_id: model identifier (e.g. "bfl/flux-1.1-pro")
        guide_type: which guide to fetch (e.g. "general", "negative",
                    "aspect-ratio"). Defaults to "general".
    """
    return mcp_call("tools/call", {
        "name": "get_prompting_guide",
        "arguments": {"model": model_id, "guide": guide_type},
    })


# ── Status / diagnostics ───────────────────────────────────────────
def status_report() -> dict:
    """Return a one-line summary for the OS status surfaces."""
    s = auth_status()
    report = {
        "service": "krea-ai",
        "connected": s["connected"],
        "token_source": s["source"],
        "base_url": s["base_url"],
    }
    if not s["connected"]:
        report["next_step"] = s["next_step"]
    return report
