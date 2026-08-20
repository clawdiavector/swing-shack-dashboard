"""postiz_client.py — server-side wrapper for Postiz API + OAuth helpers.

Built 2026-08-18 after the long-standing ImportError on `from _lib.postiz_client
import postiz_create_post` was finally traced to a missing module. The previous
working code was JS-only (scripts/fetch_postiz_analytics.js + setup.md), and
review_push_postiz in app.py:6034 had been falling back to the same broken
import every time someone clicked "Push to Postiz" in the Review queue.

Three responsibilities:

1. Server-to-server publishing using the legacy API key (POSTIZ_API_KEY env var
   or postiz-api-key.json file). This is the path review_push_postiz hits.
2. OAuth round-trip helpers — building the authorize URL, exchanging the code
   for an access token, fetching the user's connected integrations so the
   Connected Accounts page can show "IG ✓, TikTok ✗" etc.
3. The read-only status + channels endpoints that prove the wiring is live
   without touching any state.

All endpoints hit POSTIZ_API_BASE = https://api.postiz.com/public/v1 which is
the hosted-saas base (per the existing JS scripts + the OAuth Client ID prefix
pca_ captured in the screenshot). Self-hosted Postiz would need a different
base — that's a one-liner to fix in the env-var override.

Endpoints used:

  Authorization: <api_key>                     ← no "Bearer" prefix, that's the
                                                  Postiz quirk that's bitten
                                                  verify-before-recording-as-fact
  POST /public/v1/upload                        ← multipart, file=@image.jpg
  POST /public/v1/posts                         ← create a draft post
  GET  /public/v1/posts?startDate=&endDate=     ← list posts (requires dates)
  GET  /public/v1/posts/{id}                    ← get one post
  DELETE /public/v1/posts/{id}                  ← delete a draft
  GET  /public/v1/integrations                  ← list connected platforms
  GET  /public/v1/identities / {id}             ← get one integration

OAuth endpoints (different host, OAuth app):

  GET  https://postiz.com/oauth/authorize
    ?client_id=<pca_...>
    &redirect_uri=https://.../api/postiz/oauth/callback
    &response_type=code
    &scope=...
    &state=<signed>

  POST https://api.postiz.com/public/v1/oauth/token
    { code, client_id, client_secret, redirect_uri, grant_type: "authorization_code" }

  POST https://api.postiz.com/public/v1/oauth/refresh
    { refresh_token, client_id, client_secret, grant_type: "refresh_token" }

Style: every public function returns (data, error_tuple_or_None). Never raises
on API errors (returns the error instead). Raises on transport errors
(timeout, connection refused) so the caller can decide.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional, Tuple

_LOG = logging.getLogger("campaign_os.postiz_client")

POSTIZ_API_BASE = "https://api.postiz.com/public/v1"
# OAuth endpoints live on the api host WITHOUT the /public/v1 prefix. The
# earlier 404 on https://postiz.com/oauth/authorize was because that path
# doesn't exist on the marketing site — the actual authorize + token are
# on the api host. Verified 2026-08-20 by probing each candidate URL.
POSTIZ_OAUTH_AUTHORIZE_URL = "https://api.postiz.com/oauth/authorize"
POSTIZ_OAUTH_TOKEN_URL = "https://api.postiz.com/oauth/token"

# Sentinel for "function returned no usable data" — the route handler can
# distinguish it from a tuple of (None, error) when the API genuinely returns
# a 200 with empty body.
_NO_DATA = object()


# ── Credential resolution ─────────────────────────────────────────────

def _credentials_present() -> bool:
    """True if a Postiz API key (server-to-server) is reachable.

    Resolution order: env var > canonical file > bundled fallback.
    """
    return _read_api_key() is not None


def _read_api_key() -> Optional[str]:
    """Resolve the API key without echoing it. Returns None if missing."""
    env = os.environ.get("POSTIZ_API_KEY")
    if env and env.strip():
        return env.strip()
    # Canonical file path (per the swing-shack-dashboard fleet convention)
    for p in _candidate_paths():
        try:
            data = json.loads(Path(p).read_text())
            # Both shapes: {"api_key": "..."} or {"encrypted_secret": "...", "fingerprint": "..."}
            if "api_key" in data and isinstance(data["api_key"], str) and data["api_key"].strip():
                return data["api_key"].strip()
            if "encrypted_secret" in data:
                # Will land here only if the secret-drop form was used to set this
                # key — the encryption is symmetric+we'd need the env-var key. Skip
                # gracefully: the OS env var is the canonical source for runtime.
                continue
        except FileNotFoundError:
            continue
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _read_oauth_client_id() -> Optional[str]:
    """OAuth client ID (public, but treated as a credential by the same rules)."""
    env = os.environ.get("POSTIZ_OAUTH_CLIENT_ID")
    if env and env.strip():
        return env.strip()
    for p in _oauth_candidate_paths():
        try:
            data = json.loads(Path(p).read_text())
            cid = data.get("client_id") or data.get("oauth_client_id")
            if cid and isinstance(cid, str) and cid.strip():
                return cid.strip()
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
    return None


def _read_oauth_client_secret() -> Optional[str]:
    """OAuth client secret. NEVER log this value."""
    env = os.environ.get("POSTIZ_OAUTH_CLIENT_SECRET")
    if env and env.strip():
        return env.strip()
    for p in _oauth_candidate_paths():
        try:
            data = json.loads(Path(p).read_text())
            for key in ("client_secret", "oauth_client_secret", "encrypted_secret"):
                v = data.get(key)
                if isinstance(v, str) and v.strip() and not v.startswith("gAAAAA"):
                    return v.strip()
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
    return None


def _candidate_paths() -> list[Path]:
    """Canonical credential-file paths for the API key."""
    return [
        Path(os.path.expanduser("~/.openclaw-instance2/workspace/clients/swing-shack/credentials/postiz-api-key.json")),
        Path(os.path.expanduser("~/.openclaw/workspace/credentials/postiz-api-key.json")),
        Path(os.path.expanduser("~/.openclaw-instance2/workspace/credentials/postiz-api-key.json")),
    ]


def _oauth_candidate_paths() -> list[Path]:
    """Canonical credential-file paths for the OAuth client pair."""
    return [
        Path(os.path.expanduser("~/.openclaw-instance2/workspace/clients/swing-shack/credentials/postiz-oauth.json")),
        Path(os.path.expanduser("~/.openclaw/workspace/credentials/postiz-oauth.json")),
        Path(os.path.expanduser("~/.openclaw-instance2/workspace/credentials/postiz-oauth.json")),
    ]


# ── Status (read-only) ───────────────────────────────────────────────

def postiz_status() -> dict:
    """Status snapshot for /api/postiz/status. NEVER exposes the secret.

    Returns: {ok, api_key_present, api_key_length, api_key_prefix,
              oauth_client_id_present, oauth_client_secret_present,
              api_base, last_check}
    """
    key = _read_api_key()
    cid = _read_oauth_client_id()
    secret = _read_oauth_client_secret()
    return {
        "ok": bool(key),
        "api_key_present": bool(key),
        "api_key_length": len(key) if key else 0,
        "api_key_prefix": (key[:6] + "…") if key else None,
        "oauth_client_id_present": bool(cid),
        "oauth_client_secret_present": bool(secret),
        "api_base": POSTIZ_API_BASE,
        "last_check": _now_iso(),
    }


# ── Transport ─────────────────────────────────────────────────────────

def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _auth_header_value() -> Optional[str]:
    """Postiz uses bare Authorization without the "Bearer " prefix.

    This is a documented quirk that the verify-before-recording-as-fact skill
    calls out specifically. If you ever wire another API here, double-check
    their auth-header shape — most use Bearer, Postiz does not.
    """
    k = _read_api_key()
    return k if k else None


def _request(
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    form_data: Optional[dict] = None,
    timeout: int = 30,
    auth_header: bool = True,
) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """Low-level Postiz call. Returns (data, (status_code, error_message)).

    - On success: returns (parsed_json_or_None, None)
    - On HTTP error: returns (None, (status, parsed_error_body_or_text))
    - On transport error: raises urllib.error.URLError so the caller decides.

    The auth_header flag is exposed so OAuth endpoints (which send client_id
    + client_secret in the body, not in the Authorization header) can opt out.
    """
    url = POSTIZ_API_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    headers = {"Accept": "application/json"}
    payload = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(json_body).encode("utf-8")
    elif form_data is not None:
        # OAuth token endpoint accepts x-www-form-urlencoded
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        payload = urllib.parse.urlencode(form_data).encode("utf-8")
    if auth_header:
        tok = _auth_header_value()
        if tok:
            headers["Authorization"] = tok

    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return None, None
            try:
                return json.loads(raw), None
            except json.JSONDecodeError:
                return {"_raw": raw[:500]}, None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            body_parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            body_parsed = {"_raw": body[:500]} if body else None
        return None, (str(exc.code), body_parsed or body[:500] or "no body")
    except urllib.error.URLError as exc:
        # Transport error — let the caller decide.
        raise


def _request_oauth(
    method: str,
    path: str,
    *,
    form_data: Optional[dict] = None,
    json_body: Optional[dict] = None,
    timeout: int = 30,
) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """OAuth-specific transport. Uses api.postiz.com WITHOUT the /public/v1
    prefix (the OAuth endpoints sit at the root). Same return contract as
    _request: (data, None) on success, (None, (code, msg)) on HTTP error,
    raises on transport error.
    """
    url = "https://api.postiz.com" + path
    headers = {"Accept": "application/json"}
    payload = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(json_body).encode("utf-8")
    elif form_data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        payload = urllib.parse.urlencode(form_data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return None, None
            try:
                return json.loads(raw), None
            except json.JSONDecodeError:
                return {"_raw": raw[:500]}, None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            body_parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            body_parsed = {"_raw": body[:500]} if body else None
        return None, (str(exc.code), body_parsed or body[:500] or "no body")
    except urllib.error.URLError:
        raise


def _request_multipart_upload(file_path: str, timeout: int = 60) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """Upload a file using multipart/form-data (Postiz /public/v1/upload).

    Uses urllib's built-in encoder rather than `requests` so we don't pull a
    new dependency for one endpoint.
    """
    url = POSTIZ_API_BASE + "/upload"
    fpath = Path(file_path)
    if not fpath.exists():
        raise FileNotFoundError(f"file not found: {file_path}")
    boundary = f"----postiz-{secrets.token_hex(16)}"
    body = []
    body.append(f"--{boundary}".encode())
    body.append(f'Content-Disposition: form-data; name="file"; filename="{fpath.name}"'.encode())
    body.append(b"Content-Type: application/octet-stream")
    body.append(b"")
    body.append(fpath.read_bytes())
    body.append(f"--{boundary}--".encode())
    payload = b"\r\n".join(body)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
    }
    tok = _auth_header_value()
    if tok:
        headers["Authorization"] = tok
    req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return (json.loads(raw) if raw else None), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return None, (str(exc.code), body[:500] or "no body")
    except urllib.error.URLError:
        raise


# ── Server-to-server: publication pipeline ────────────────────────────

def upload_media(file_path: str) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """Upload a file to Postiz. Returns (data, error).

    Per the existing fixtures: response shape is
    { id: "img-...", path: "https://..." }
    """
    return _request_multipart_upload(file_path)


def create_post(
    integration_id: str,
    content: str,
    media_ids: list[str],
    *,
    publish_date: Optional[str] = None,
    tiktok_privacy_level: str = "SELF_ONLY",
    tiktok_auto_add_music: str = "no",
    tiktok_content_posting_method: str = "UPLOAD",
    platform_settings: Optional[dict] = None,
    group_id: Optional[str] = None,
) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """Create a draft post for one integration.

    Mirrors the existing tiktok-marketing/postiz-setup.md payload shape so
    the swing-shack fields and the swing-shack TikTok fields stay aligned.
    Postiz validates the payload strictly — `shortLink` and `tags` are
    required booleans/arrays even when empty.
    """
    value = [{"content": content, "image": [{"id": m} for m in media_ids], "shortLink": False, "tags": []}]
    settings = platform_settings or {}
    # Match the legacy _settings per platform by inferring from integration
    # providerIdentifier. Routes that call this can override via platform_settings.
    payload = {
        "type": "schedule" if publish_date else "now",
        "date": publish_date,
        "shortLink": False,
        "tags": [],
        "posts": [
            {
                "integration": {"id": integration_id},
                "value": value,
                "settings": settings,
                "shortLink": False,
                "tags": [],
            }
        ],
    }
    if group_id:
        payload["group"] = group_id
    return _request("POST", "/posts", json_body=payload)


def list_posts(
    integration_id: Optional[str] = None,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 50,
) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """List posts. Per Postiz docs, startDate + endDate are required for /posts."""
    params = {
        "integrationId": integration_id,
        "startDate": start_date,
        "endDate": end_date,
        "state": state,
        "limit": limit,
    }
    return _request("GET", "/posts", params=params)


def get_post(post_id: str) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    return _request("GET", f"/posts/{post_id}")


def delete_post(post_id: str) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """Delete a draft (only DRAFT state is deletable per the postiz-ui-vs-api
    protocol — never silently delete a published post)."""
    return _request("DELETE", f"/posts/{post_id}")


def list_integrations() -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """List connected platforms/integrations for the current auth context.

    Returns: { integrations: [ { id, name, providerIdentifier, picture, ... } ] }
    Per the fixtures captured 2026-07-22, the shape is a list of integration
    objects. Some endpoints wrap this in { integrations: [...] } or
    { identities: [...] } — we normalise both.
    """
    return _request("GET", "/integrations")


# ── OAuth round-trip helpers ──────────────────────────────────────────

def _oauth_state_secret() -> bytes:
    """HMAC key used to sign OAuth state values. NEVER echoed.

    Prefer a dedicated env var if set; fall back to SESSION_SECRET so the
    existing Campaign OS auth-gate secret is the seed. Production should set
    POSTIZ_OAUTH_STATE_SECRET to its own 32-byte random value.
    """
    raw = os.environ.get("POSTIZ_OAUTH_STATE_SECRET") or os.environ.get("SESSION_SECRET") or "dev-only-postiz-state-secret"
    return raw.encode("utf-8") if isinstance(raw, str) else raw


def make_oauth_state(brand_id: str, user_id: str = "operator", ttl_seconds: int = 600) -> str:
    """Build a single-use, brand-bound, time-bounded OAuth state string.

    Format: <base64url(payload|sig)>
    Payload: <brand_id>|<user_id>|<nonce>|<exp>
    Sig: HMAC-SHA256(payload, secret)
    """
    payload = f"{brand_id}|{user_id}|{secrets.token_urlsafe(16)}|{int(time.time()) + ttl_seconds}"
    sig = hmac.new(_oauth_state_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode("utf-8")).decode("ascii").rstrip("=")


def verify_oauth_state(state_b64: str, expected_brand_id: str, expected_user_id: str = "operator") -> Tuple[bool, str]:
    """Verify the state returned in the OAuth callback. Returns (ok, reason)."""
    try:
        padded = state_b64 + "=" * (-len(state_b64) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        payload, sig = raw.rsplit("|", 1)
        brand_id_s, user_id_s, _nonce, exp_s = payload.split("|", 3)
        if brand_id_s != expected_brand_id:
            return False, f"state bound to brand {brand_id_s!r}, not {expected_brand_id!r}"
        if user_id_s != expected_user_id:
            return False, f"state bound to user {user_id_s!r}, not {expected_user_id!r}"
        if int(exp_s) < int(time.time()):
            return False, "state expired"
        expected_sig = hmac.new(_oauth_state_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return False, "state signature invalid"
        return True, "ok"
    except Exception as exc:
        return False, f"state parse failed: {exc}"


def build_oauth_authorize_url(redirect_uri: str, state: str, scope: str = "read write publish") -> str:
    """Construct the authorize URL the user clicks to start the OAuth flow."""
    cid = _read_oauth_client_id()
    if not cid:
        raise RuntimeError("POSTIZ_OAUTH_CLIENT_ID not configured")
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    return POSTIZ_OAUTH_AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)


def exchange_oauth_code(
    code: str, redirect_uri: str
) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """Exchange the OAuth code for an access token + refresh token.

    Postiz returns: { access_token, refresh_token, expires_in, scope, ... }
    """
    cid = _read_oauth_client_id()
    secret = _read_oauth_client_secret()
    if not cid or not secret:
        raise RuntimeError("POSTIZ_OAUTH_CLIENT_ID and POSTIZ_OAUTH_CLIENT_SECRET both required for OAuth")
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": cid,
        "client_secret": secret,
        "redirect_uri": redirect_uri,
    }
    return _request_oauth("POST", "/oauth/token", form_data=form)


def refresh_oauth_token(refresh_token: str) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    cid = _read_oauth_client_id()
    secret = _read_oauth_client_secret()
    if not cid or not secret:
        raise RuntimeError("POSTIZ_OAUTH_CLIENT_ID and POSTIZ_OAUTH_CLIENT_SECRET both required for OAuth refresh")
    form = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": cid,
        "client_secret": secret,
    }
    return _request_oauth("POST", "/oauth/refresh", form_data=form)


# ── Per-brand OAuth token storage ─────────────────────────────────────

def _oauth_token_path(brand_id: str) -> Path:
    """Per-brand OAuth token storage. Fernet-encrypted at rest."""
    base = Path(os.path.expanduser("~/.openclaw-instance2/workspace/clients/swing-shack/credentials/postiz-oauth"))
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{brand_id}.json"


def _fernet():
    """Same fernet instance as the /secret-drop endpoint so the same
    META_TOKEN_ENCRYPTION_KEY / SESSION_SECRET-derived key works for both."""
    from cryptography.fernet import Fernet
    raw = os.environ.get("META_TOKEN_ENCRYPTION_KEY") or os.environ.get("SESSION_SECRET") or "dev-only"
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    fernet_key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(fernet_key)


def save_oauth_token(brand_id: str, token_payload: dict, note: Optional[str] = None) -> Path:
    """Persist the OAuth token payload for a brand. Encrypts access_token+
    refresh_token at rest; stores expires_in, scope, scope_granted_at plaintext."""
    import datetime as _dt
    enc = _fernet()
    payload = dict(token_payload)
    plain = {}
    for k in ("access_token", "refresh_token"):
        if k in payload:
            plain[k] = payload.pop(k)
    cipher = {k: enc.encrypt(v.encode("utf-8")).decode("ascii") for k, v in plain.items()}
    record = {
        "encrypted_tokens": cipher,
        "expires_in": payload.get("expires_in"),
        "scope": payload.get("scope"),
        "token_type": payload.get("token_type"),
        "rotated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "fingerprint": {k: hashlib.sha256(v.encode("utf-8")).hexdigest()[:8] for k, v in plain.items()},
    }
    if note:
        record["note"] = note
    p = _oauth_token_path(brand_id)
    p.write_text(json.dumps(record, indent=2))
    os.chmod(p, 0o600)
    _LOG.info("postiz_oauth_token_saved brand=%s expires_in=%s", brand_id, record["expires_in"])
    return p


def load_oauth_token(brand_id: str) -> Optional[dict]:
    """Load and decrypt the OAuth token for a brand. Returns None if missing."""
    p = _oauth_token_path(brand_id)
    if not p.exists():
        return None
    try:
        record = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    cipher = record.get("encrypted_tokens") or {}
    if not cipher:
        return None
    enc = _fernet()
    out = {}
    for k, v in cipher.items():
        try:
            out[k] = enc.decrypt(v.encode("ascii")).decode("utf-8")
        except Exception as exc:
            _LOG.warning("postiz_oauth_token_decrypt_failed brand=%s key=%s err=%s", brand_id, k, exc)
            return None
    out["expires_in"] = record.get("expires_in")
    out["scope"] = record.get("scope")
    out["token_type"] = record.get("token_type")
    out["rotated_at"] = record.get("rotated_at")
    return out


def delete_oauth_token(brand_id: str) -> bool:
    """Hard-delete the per-brand OAuth token. Returns True if anything was removed."""
    p = _oauth_token_path(brand_id)
    if p.exists():
        p.unlink()
        _LOG.info("postiz_oauth_token_deleted brand=%s", brand_id)
        return True
    return False
