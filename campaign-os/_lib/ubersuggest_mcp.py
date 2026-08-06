"""
ubersuggest_mcp.py — Ubersuggest MCP (Model Context Protocol) wrapper.

Ubersuggest exposes SEO tools via an MCP server that speaks JSON-RPC over
HTTPS at `https://ubersuggest-mcp.neilpatelapi.com/mcp`. Authentication is
OAuth 2.0 + PKCE — NOT a static Bearer token. Tokens are obtained via:

    1. Dynamic Client Registration (DCR): POST /register → client_id (public)
    2. Authorization Code + PKCE: GET /authorize in a browser → ?code=…
       in a loopback /callback URL
    3. Token exchange: POST /token → access_token + refresh_token
    4. Refresh: POST /token with grant_type=refresh_token → new access_token

This module is read-only — no mutations. It raises typed exceptions when
the upstream fails, so the route layer can return 503-with-hint instead of
500.

Reference: MCP JSON-RPC schema at /mcp, OAuth discovery at
/.well-known/oauth-authorization-server. Built 2026-08-06 from
UBERSUGGEST-MCP-DISCOVERY-2026-08-06.md.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_LOG = logging.getLogger("campaign_os.ubersuggest_mcp")

# ── Server endpoints (live-probed 2026-08-06) ────────────────────────────

ISSUER = "https://ubersuggest-mcp.neilpatelapi.com/"
MCP_ENDPOINT = "https://ubersuggest-mcp.neilpatelapi.com/mcp"
DISCOVERY_ENDPOINT = "https://ubersuggest-mcp.neilpatelapi.com/.well-known/oauth-authorization-server"
AUTHORIZE_ENDPOINT = "https://ubersuggest-mcp.neilpatelapi.com/authorize"
TOKEN_ENDPOINT = "https://ubersuggest-mcp.neilpatelapi.com/token"
REGISTER_ENDPOINT = "https://ubersuggest-mcp.neilpatelapi.com/register"

# Documented scopes. Ubersuggest grants based on the user's plan tier,
# not what we ask for — so we request all of them and accept whatever
# the consent screen says.
DEFAULT_SCOPES = (
    "profile domain keywords serp backlinks site_audit content projects utility"
)

# Public client_id (one for everyone, per /register response 2026-08-06).
DEFAULT_CLIENT_ID = "ubersuggest-mcp"

# Token file location — outside the repo, siblings to other credentials.
# IMPORTANT: absolute path. `~` resolves differently depending on the
# sandbox (heidi profile, Railway, macOS user) — we always want the same
# file regardless of which shell runs the script.
DEFAULT_TOKEN_FILE = (
    "/Users/fivefriday/.openclaw-instance2/workspace/"
    "clients/swing-shack/credentials/ubersuggest-api.json"
)


# ── Typed exceptions (mirrors meta_api.py pattern) ───────────────────────

class UbersuggestAuthError(Exception):
    """Token missing, expired, revoked, or refresh failed.

    Maps to HTTP 503 in route handlers, with a setup-portal-style `hint`.
    """

    def __init__(self, message: str, upstream: Optional[dict] = None):
        super().__init__(message)
        self.upstream = upstream or {}


class UbersuggestUpstreamError(Exception):
    """Other 4xx/5xx from Ubersuggest MCP."""

    def __init__(self, message: str, upstream: Optional[dict] = None, code: Optional[int] = None):
        super().__init__(message)
        self.upstream = upstream or {}
        self.code = code


class UbersuggestNetworkError(Exception):
    """DNS, TLS, timeout — couldn't reach the server."""


# ── Credential resolution ───────────────────────────────────────────────

def ubersuggest_credentials_present() -> bool:
    """True iff the OAuth token file exists and contains an access_token."""
    path = _read_token_path()
    if not path or not os.path.exists(path):
        return False
    try:
        data = Path(path).read_text()
        parsed = json.loads(data)
        return bool(parsed.get("access_token"))
    except (OSError, ValueError):
        return False


def _read_token_path() -> Optional[str]:
    """Read the token file path from env (UBERSUGGEST_TOKEN_FILE) or default.

    Env var takes precedence so multiple sandboxes can coexist; the default
    matches the sibling credentials folder.
    """
    return os.environ.get("UBERSUGGEST_TOKEN_FILE") or DEFAULT_TOKEN_FILE


def _read_token_meta() -> dict:
    """Read full token file (expires_at, refreshed_at, etc.) as dict."""
    path = _read_token_path()
    if not path or not os.path.exists(path):
        return {}
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def _read_access_token() -> Optional[str]:
    """Read the access_token value from disk. None if not configured."""
    meta = _read_token_meta()
    tok = meta.get("access_token")
    if tok:
        return str(tok).strip()
    return None


def _read_refresh_token() -> Optional[str]:
    """Read the refresh_token value from disk. None if not configured."""
    meta = _read_token_meta()
    tok = meta.get("refresh_token")
    if tok:
        return str(tok).strip()
    return None


def write_token_file(
    *,
    access_token: str,
    refresh_token: Optional[str] = None,
    expires_in: Optional[int] = None,
    scope: Optional[str] = None,
    token_type: str = "Bearer",
    extra: Optional[dict] = None,
) -> str:
    """Atomic write of the token file with 0600 permissions.

    Returns the path written to. Writes a tmp file + rename so a concurrent
    reader never sees a half-written file.
    """
    path = _read_token_path()
    if not path:
        raise RuntimeError("UBERSUGGEST_TOKEN_FILE not configured and no default")

    now = int(time.time())
    payload = {
        "access_token": access_token.strip(),
        "token_type": token_type,
        "refreshed_at": now,
        "obtained_at": now,
    }
    if refresh_token is not None:
        payload["refresh_token"] = refresh_token.strip()
    if expires_in is not None:
        payload["expires_in"] = int(expires_in)
        payload["expires_at"] = now + int(expires_in)
    if scope is not None:
        payload["scope"] = scope
    if extra:
        payload.update(extra)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".ubersuggest-", suffix=".json", dir=os.path.dirname(path)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise
    _LOG.info("wrote Ubersuggest token file %s (scope=%s, expires_in=%s)",
              path, scope, expires_in)
    return path


def is_token_expired(within_seconds: int = 300) -> bool:
    """True if the saved access_token expires within `within_seconds`.

    Used by the wrapper to decide whether to refresh before a call. If
    `expires_at` is missing/unparseable, returns True (fail safe).
    """
    meta = _read_token_meta()
    expires_at = meta.get("expires_at")
    if not isinstance(expires_at, (int, float)):
        return True
    return (time.time() + within_seconds) >= expires_at


# ── OAuth helpers (used by the OAuth dance script, not this wrapper) ─────

def fetch_discovery() -> dict:
    """GET /.well-known/oauth-authorization-server — RFC 8414 metadata."""
    req = Request(DISCOVERY_ENDPOINT, headers={"User-Agent": "campaign-os/ubersuggest/1.0"})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def dynamic_client_register() -> dict:
    """POST /register (RFC 7591) — returns the public client config."""
    body = json.dumps({}).encode("utf-8")
    req = Request(
        REGISTER_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "campaign-os/ubersuggest/1.0",
        },
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def exchange_code_for_token(
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    client_id: str = DEFAULT_CLIENT_ID,
) -> dict:
    """POST /token with grant_type=authorization_code → access+refresh tokens."""
    body = urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }).encode("utf-8")
    return _post_token(body)


def refresh_access_token(
    *,
    refresh_token: Optional[str] = None,
    client_id: str = DEFAULT_CLIENT_ID,
) -> dict:
    """POST /token with grant_type=refresh_token → new access+refresh tokens."""
    if refresh_token is None:
        meta = _read_token_meta()
        refresh_token = meta.get("refresh_token")
    if not refresh_token:
        raise UbersuggestAuthError(
            "no refresh_token saved — run `python3 scripts/ubersuggest_oauth.py`"
        )
    body = urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }).encode("utf-8")
    return _post_token(body)


def _post_token(body: bytes) -> dict:
    """Shared POST /token handler. Raises typed exceptions on failure."""
    req = Request(
        TOKEN_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "campaign-os/ubersuggest/1.0",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"error": str(e), "code": e.code}
        err_code = e.code
        err_msg = err_body.get("error_description") or err_body.get("error") or ""
        if err_code in (400, 401) and "invalid_grant" in str(err_body.get("error", "")):
            raise UbersuggestAuthError(
                f"refresh failed — token revoked or expired. "
                f"Re-run `python3 scripts/ubersuggest_oauth.py`. "
                f"Upstream: {err_msg}",
                upstream=err_body,
            ) from e
        if err_code in (400, 401):
            raise UbersuggestAuthError(
                f"token endpoint rejected request ({err_code}): {err_msg}",
                upstream=err_body,
            ) from e
        raise UbersuggestUpstreamError(
            f"token endpoint error ({err_code}): {err_msg}",
            upstream=err_body,
            code=err_code,
        ) from e
    except URLError as e:
        raise UbersuggestNetworkError(f"network error reaching {TOKEN_ENDPOINT}: {e}") from e

    if "error" in data:
        raise UbersuggestAuthError(
            f"token endpoint returned error: {data.get('error_description', data['error'])}",
            upstream=data,
        )
    return data


def _normalize_token_response(data: dict) -> dict:
    """Map OAuth token-endpoint keys → write_token_file kwargs."""
    out = {"access_token": data.get("access_token", "")}
    if "refresh_token" in data:
        out["refresh_token"] = data["refresh_token"]
    if "expires_in" in data:
        out["expires_in"] = int(data["expires_in"])
    if "scope" in data:
        out["scope"] = data["scope"]
    if "token_type" in data:
        out["token_type"] = data["token_type"]
    return out


# ── MCP JSON-RPC caller ──────────────────────────────────────────────────

def mcp_call(
    method: str,
    params: Optional[dict] = None,
    *,
    timeout: int = 30,
    auto_refresh: bool = True,
) -> dict:
    """Send a JSON-RPC 2.0 request to /mcp with the saved access token.

    `method` is e.g. "tools/list" or "tools/call".
    `params` is e.g. {"name": "keyword_overview", "arguments": {...}}.

    Auto-refresh: if the server returns 401 with "invalid_token", tries to
    refresh via grant_type=refresh_token and retries once. If the refresh
    fails, raises UbersuggestAuthError with a "re-authorize" hint.

    Returns the parsed `result` field. Raises:
      - UbersuggestAuthError: token missing/expired/revoked
      - UbersuggestUpstreamError: JSON-RPC error from the server
      - UbersuggestNetworkError: could not reach the server
    """
    if is_token_expired(within_seconds=60):
        if auto_refresh:
            _LOG.info("access token expires soon — refreshing before call")
            try:
                refreshed = refresh_access_token()
                write_token_file(**_normalize_token_response(refreshed))
            except UbersuggestAuthError:
                raise
        else:
            raise UbersuggestAuthError(
                "access token expired and auto_refresh=False. "
                "Run `python3 scripts/ubersuggest_oauth.py` to refresh, "
                "or pass auto_refresh=True."
            )

    token = _read_access_token()
    if not token:
        meta = _read_token_meta()
        path = _read_token_path()
        raise UbersuggestAuthError(
            f"Ubersuggest token not configured at {path}"
            f" — run `python3 scripts/ubersuggest_oauth.py` to authorize"
        )

    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000) % 100000,
        "method": method,
        "params": params or {},
    }

    def _do_call() -> dict:
        req = Request(
            MCP_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {token}",
                "User-Agent": "campaign-os/ubersuggest/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8"))
            except Exception:
                err_body = {"error": str(e), "code": e.code}
            if e.code == 401 and "invalid_token" in json.dumps(err_body).lower():
                raise _RetryableAuth(err_body)
            if e.code in (401, 403):
                raise UbersuggestAuthError(
                    f"MCP auth failed ({e.code}): {err_body.get('error_description', err_body)}",
                    upstream=err_body,
                ) from e
            raise UbersuggestUpstreamError(
                f"MCP error ({e.code}): {err_body}",
                upstream=err_body,
                code=e.code,
            ) from e
        except URLError as e:
            raise UbersuggestNetworkError(
                f"network error reaching {MCP_ENDPOINT}: {e}"
            ) from e
        try:
            outer = json.loads(raw)
        except ValueError:
            data_lines = [
                line[len("data: "):].strip()
                for line in raw.splitlines()
                if line.startswith("data: ")
            ]
            if not data_lines:
                raise UbersuggestUpstreamError(
                    f"MCP returned non-JSON, non-SSE response: {raw[:200]!r}"
                )
            outer = json.loads(data_lines[0])
        if "error" in outer:
            err = outer["error"]
            code = err.get("code")
            msg = err.get("message", "")
            if code in (-32001, -32002) or ("token" in msg.lower() and "expired" in msg.lower()):
                raise _RetryableAuth({"jsonrpc_error": err})
            raise UbersuggestUpstreamError(
                f"MCP returned error (code={code}): {msg}", upstream=err, code=code
            )
        return outer.get("result", outer)

    try:
        return _do_call()
    except _RetryableAuth as retry:
        if not auto_refresh:
            raise UbersuggestAuthError(
                "MCP returned invalid_token and auto_refresh=False",
                upstream=retry.upstream,
            ) from retry
        _LOG.info("MCP returned invalid_token — refreshing and retrying once")
        try:
            refreshed = refresh_access_token()
            write_token_file(**_normalize_token_response(refreshed))
        except UbersuggestAuthError as e:
            raise UbersuggestAuthError(
                "token expired and refresh failed. "
                "Re-run `python3 scripts/ubersuggest_oauth.py` to re-authorize.",
                upstream=e.upstream,
            ) from e
        meta = _read_token_meta()
        token = meta.get("access_token") or token
        return _do_call()


class _RetryableAuth(Exception):
    """Internal sentinel for 'try refresh + one retry'."""

    def __init__(self, upstream: dict):
        super().__init__(str(upstream))
        self.upstream = upstream


# ── Higher-level tool wrappers ───────────────────────────────────────────

def list_tools() -> dict:
    """GET the canonical tool list from /mcp (caches 24h on disk)."""
    cache_path = (
        "/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/"
        "credentials/ubersuggest-tools-cache.json"
    )
    if os.path.exists(cache_path):
        try:
            cached = json.loads(Path(cache_path).read_text())
            if (time.time() - cached.get("fetched_at", 0)) < 86400:
                return cached
        except (OSError, ValueError):
            pass

    result = mcp_call("tools/list")
    result["fetched_at"] = int(time.time())
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        Path(cache_path).write_text(json.dumps(result, indent=2))
    except OSError:
        pass
    return result


def keyword_overview(keyword: str, *, loc_id: int = 2840, lang: str = "en") -> dict:
    """`keyword_overview` — search volume, CPC, SEO difficulty, paid difficulty.

    Default loc_id (2840) is US; pass 2712 for South Africa / Johannesburg.
    """
    return mcp_call("tools/call", {
        "name": "keyword_overview",
        "arguments": {"keyword": keyword, "locId": loc_id, "lang": lang},
    })


def domain_overview(domain: str, *, country: int = 2840) -> dict:
    """`domain_overview` — headline domain metrics."""
    return mcp_call("tools/call", {
        "name": "domain_overview",
        "arguments": {"domain": domain, "country": country},
    })


def backlinks_overview(domain: str) -> dict:
    """`backlinks_overview` — total backlinks, referring domains, domain authority."""
    return mcp_call("tools/call", {
        "name": "backlinks_overview",
        "arguments": {"domain": domain},
    })


def competitors(domain: str, *, loc_id: int = 2840, lang: str = "en") -> dict:
    """`competitors` — find organic competitors. Async on the backend (~30s)."""
    return mcp_call("tools/call", {
        "name": "competitors",
        "arguments": {"domain": domain, "locId": loc_id, "lang": lang},
    })


def auth_status() -> dict:
    """`auth_status` — confirm token is live and return account tier."""
    return mcp_call("tools/call", {"name": "auth_status", "arguments": {}})


def keyword_suggestions(keyword: str, *, loc_id: int = 2840, lang: str = "en",
                       limit: int = 25) -> dict:
    """`keyword_suggestions` — related keywords + search volume."""
    return mcp_call("tools/call", {
        "name": "keyword_suggestions",
        "arguments": {"keyword": keyword, "locId": loc_id, "lang": lang, "limit": limit},
    })


def site_audit(domain: str, *, crawl_max_pages: int = 150, recrawl: bool = False) -> dict:
    """`site_audit` — starts a site audit (Step 1 of 3, paid account only)."""
    return mcp_call("tools/call", {
        "name": "site_audit",
        "arguments": {
            "domain": domain,
            "crawlMaxPages": crawl_max_pages,
            "recrawl": recrawl,
        },
    })


def list_projects() -> dict:
    """`list_projects` — list tracked projects with their `has_brand` flag."""
    return mcp_call("tools/call", {"name": "list_projects", "arguments": {}})


def project_position_info(
    project_id: str, *, start_date: str, end_date: str,
    loc_id: Optional[int] = None, language: str = "en", device: str = "desktop",
) -> dict:
    """`project_position_info` — rank tracking per keyword per date.

    Returns the FULL report. status='ok' with old/new_position.position=null
    means the domain does NOT rank in top 100 — that's the final answer.
    """
    args: dict = {
        "project_id": project_id,
        "startDate": start_date,
        "endDate": end_date,
        "language": language,
        "device": device,
    }
    if loc_id is not None:
        args["locId"] = int(loc_id)
    return mcp_call("tools/call", {"name": "project_position_info", "arguments": args})


# ── Status companion (for the SPA) ───────────────────────────────────────

def status_report() -> dict:
    """Lightweight status blurb for /api/intel/ubersuggest/status."""
    if not ubersuggest_credentials_present():
        return {
            "configured": False,
            "reason": "no Ubersuggest token file at "
                      f"`{_read_token_path()}`. "
                      "Run `python3 scripts/ubersuggest_oauth.py` to authorize.",
        }
    meta = _read_token_meta()
    out = {
        "configured": True,
        "token_file": _read_token_path(),
        "refreshed_at": meta.get("refreshed_at"),
        "expires_at": meta.get("expires_at"),
        "scope": meta.get("scope"),
        "expires_in_seconds": (meta.get("expires_at", 0) - int(time.time()))
                              if meta.get("expires_at") else None,
    }
    try:
        tier_resp = auth_status()
        out["last_tier_check_at"] = int(time.time())
        if isinstance(tier_resp, dict):
            out["account_tier"] = str(tier_resp)[:120]
    except UbersuggestAuthError as e:
        out["tier_check_error"] = str(e)
    except UbersuggestNetworkError:
        pass
    return out


# ── PKCE helpers (RFC 7636) ──────────────────────────────────────────────

def generate_pkce_pair() -> tuple[str, str]:
    """Generate (code_verifier, code_challenge) per RFC 7636 for S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def generate_state() -> str:
    """Random base64url state parameter for CSRF protection on /authorize."""
    return base64.urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b"=").decode("ascii")
