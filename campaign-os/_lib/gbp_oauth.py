"""gbp_oauth.py — Google OAuth round-trip for GBP (Google Business Profile).

Built 2026-08-20 to unblock the daily-post generator. The pattern is the
same as postiz_client.make_oauth_state / verify_oauth_state / save_*
on disk: signed state, brand-bound, Fernet-encrypted at rest, per-brand
token files.

What's NOT done in this module (real-world Google Cloud setup needed):
  - The OAuth client (737685980094-...) needs the GBP scope
    https://www.googleapis.com/auth/business.manage added to its allowed
    scopes on Google Cloud Console before the consent screen will accept
    GBP reads/writes. 5-minute task on https://console.cloud.google.com.

Once that's done, the OAuth dance here is the only thing the user has to
click — login, grant, land on /api/gbp/oauth/callback, token stored.

Endpoints used (verified from Google docs as of 2026-08-20):
  Authorization: https://accounts.google.com/o/oauth2/v2/auth
  Token:        https://oauth2.googleapis.com/token
  GBP API:      https://mybusinessbusinessinformation.googleapis.com/v1
                https://mybusinessaccountmanagement.googleapis.com/v1
                https://mybusiness.googleapis.com/v4

For the daily-post generator, the minimum scope set is:
  - openid (for refresh tokens)
  - https://www.googleapis.com/auth/userinfo.email (so we know which account)
  - https://www.googleapis.com/auth/business.manage (GBP full access)
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

_LOG = logging.getLogger("campaign_os.gbp_oauth")

# Google's documented OAuth endpoints
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# GBP API base hosts
GBP_BUSINESS_INFO_API = "https://mybusinessbusinessinformation.googleapis.com/v1"
GBP_ACCOUNT_MGMT_API = "https://mybusinessaccountmanagement.googleapis.com/v1"
GBP_CONTENT_API = "https://mybusiness.googleapis.com/v4"

# Scopes for the daily-post flow. openid + email are required for refresh
# tokens; business.manage is the only GBP scope that includes both read
# (insights) and write (posts).
GBP_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/business.manage",
]


# ── Credential resolution ─────────────────────────────────────────────

def gbp_oauth_credentials_present() -> bool:
    """True if the OAuth client config (client_id + client_secret) is reachable."""
    cid, _secret = _read_client_id_secret()
    return bool(cid)


def gbp_token_present(brand_id: str) -> bool:
    return _token_path(brand_id).exists()


def _read_client_id_secret() -> Tuple[Optional[str], Optional[str]]:
    """Resolve the OAuth client_id + client_secret.

    Resolution order:
      1. env vars GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET
      2. google-analytics.json canonical file (existing GA4 OAuth client)
    """
    cid = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if cid and secret:
        return cid, secret
    # Fallback: parse google-analytics.json (existing OAuth client)
    for p in [
        Path(os.path.expanduser("~/.openclaw-instance2/workspace/clients/swing-shack/credentials/google-analytics.json")),
        Path(os.path.expanduser("~/.openclaw/workspace/credentials/google-analytics.json")),
    ]:
        try:
            d = json.loads(p.read_text())
            return d.get("client_id"), d.get("client_secret")
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
    return None, None


def _token_path(brand_id: str) -> Path:
    # Resolution order (set 2026-08-20 so tokens survive Railway redeploys):
    #   1. GBP_TOKEN_DIR env var (specific override)
    #   2. DATA_DIR env var (Railway persistent volume, /data by default)
    #   3. Canonical local path on the Mac
    base_dir = os.environ.get("GBP_TOKEN_DIR") or os.environ.get("DATA_DIR")
    if base_dir:
        base = Path(base_dir) / "credentials" / "gbp"
    else:
        base = Path(os.path.expanduser("~/.openclaw-instance2/workspace/clients/swing-shack/credentials/gbp"))
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{brand_id}.json"


# ── State helpers (HMAC-signed, brand-bound, time-bounded) ───────────

def _state_secret() -> bytes:
    raw = os.environ.get("GBP_OAUTH_STATE_SECRET") or os.environ.get("SESSION_SECRET") or "dev-only-gbp-state"
    return raw.encode("utf-8") if isinstance(raw, str) else raw


def make_state(brand_id: str, user_id: str = "operator", ttl_seconds: int = 600) -> str:
    payload = f"{brand_id}|{user_id}|{secrets.token_urlsafe(16)}|{int(time.time()) + ttl_seconds}"
    sig = hmac.new(_state_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode("utf-8")).decode("ascii").rstrip("=")


def verify_state(state_b64: str, expected_brand_id: str, expected_user_id: str = "operator") -> Tuple[bool, str]:
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
        expected_sig = hmac.new(_state_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return False, "state signature invalid"
        return True, "ok"
    except Exception as exc:
        return False, f"state parse failed: {exc}"


def brand_from_state(state_b64: str) -> Optional[str]:
    """Recover the brand_id from a state value (used by the callback before verify)."""
    try:
        padded = state_b64 + "=" * (-len(state_b64) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        return raw.split("|", 1)[0]
    except Exception:
        return None


# ── Authorize URL + token exchange ───────────────────────────────────

def build_authorize_url(redirect_uri: str, state: str, scope: Optional[list] = None) -> str:
    cid, _ = _read_client_id_secret()
    if not cid:
        raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID not configured (or missing from google-analytics.json)")
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scope or GBP_SCOPES),
        "access_type": "offline",  # critical: gives us a refresh_token
        "prompt": "consent",       # force consent to re-issue refresh token
        "include_granted_scopes": "true",
        "state": state,
    }
    return GOOGLE_AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)


def exchange_code(code: str, redirect_uri: str) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    cid, secret = _read_client_id_secret()
    if not cid or not secret:
        raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET both required")
    form = {
        "code": code,
        "client_id": cid,
        "client_secret": secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    payload = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try: body = json.loads(body)
        except Exception: pass
        return None, (str(e.code), body if isinstance(body, dict) else body[:500])
    except urllib.error.URLError:
        raise


def refresh_access_token(refresh_token: str) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    cid, secret = _read_client_id_secret()
    if not cid or not secret:
        raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET both required")
    form = {
        "refresh_token": refresh_token,
        "client_id": cid,
        "client_secret": secret,
        "grant_type": "refresh_token",
    }
    payload = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try: body = json.loads(body)
        except Exception: pass
        return None, (str(e.code), body if isinstance(body, dict) else body[:500])
    except urllib.error.URLError:
        raise


# ── Per-brand token storage (Fernet-encrypted at rest) ────────────────

def _fernet():
    from cryptography.fernet import Fernet
    raw = os.environ.get("META_TOKEN_ENCRYPTION_KEY") or os.environ.get("SESSION_SECRET") or "dev-only"
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw).digest()))


def save_token(brand_id: str, token_payload: dict, google_account_email: Optional[str] = None, note: Optional[str] = None) -> Path:
    """Persist a per-brand GBP token. Encrypts access_token + refresh_token."""
    import datetime as _dt
    enc = _fernet()
    payload = dict(token_payload)
    plain = {}
    for k in ("access_token", "refresh_token", "id_token"):
        if k in payload:
            plain[k] = payload.pop(k)
    cipher = {k: enc.encrypt(v.encode("utf-8")).decode("ascii") for k, v in plain.items()}
    record = {
        "encrypted_tokens": cipher,
        "expires_in": payload.get("expires_in"),
        "token_type": payload.get("token_type"),
        "scope": payload.get("scope"),
        "rotated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "fingerprint": {k: hashlib.sha256(v.encode("utf-8")).hexdigest()[:8] for k, v in plain.items()},
    }
    if google_account_email:
        record["google_account_email"] = google_account_email
    if note:
        record["note"] = note
    p = _token_path(brand_id)
    p.write_text(json.dumps(record, indent=2))
    os.chmod(p, 0o600)
    _LOG.info("gbp_token_saved brand=%s expires_in=%s", brand_id, record["expires_in"])
    return p


def load_token(brand_id: str) -> Optional[dict]:
    """Load and decrypt a per-brand GBP token. None if missing or decrypt fails."""
    p = _token_path(brand_id)
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
            _LOG.warning("gbp_token_decrypt_failed brand=%s key=%s err=%s", brand_id, k, exc)
            return None
    out["expires_in"] = record.get("expires_in")
    out["scope"] = record.get("scope")
    out["token_type"] = record.get("token_type")
    out["rotated_at"] = record.get("rotated_at")
    out["google_account_email"] = record.get("google_account_email")
    return out


def delete_token(brand_id: str) -> bool:
    p = _token_path(brand_id)
    if p.exists():
        p.unlink()
        _LOG.info("gbp_token_deleted brand=%s", brand_id)
        return True
    return False


# ── GBP API helpers (Insights + Posts) ───────────────────────────────

def _request_google_api(method: str, url: str, access_token: str, *, json_body: Optional[dict] = None, timeout: int = 30) -> Tuple[Optional[Any], Optional[Tuple[str, str]]]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    payload = json.dumps(json_body).encode("utf-8") if json_body is not None else None
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return None, None
            try:
                return json.loads(raw), None
            except json.JSONDecodeError:
                return {"_raw": raw[:500]}, None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try: body = json.loads(body)
        except Exception: pass
        return None, (str(e.code), body if isinstance(body, dict) else body[:500])
    except urllib.error.URLError:
        raise


def list_gbp_accounts(access_token: str) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """List the Google accounts the user owns (or has access to)."""
    return _request_google_api("GET", f"{GBP_ACCOUNT_MGMT_API}/accounts", access_token)


def list_gbp_locations(access_token: str, account_name: str) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """List locations under a given account. account_name is the resource name, e.g. 'accounts/12345'."""
    return _request_google_api("GET", f"{account_name}/locations?readMask=name,title", access_token)


def gbp_status(brand_id: str = "swing-shack") -> dict:
    """Diagnostic snapshot for /api/gbp/status. NEVER echoes the token."""
    cid, _ = _read_client_id_secret()
    tok = load_token(brand_id)
    return {
        "ok": bool(cid) and bool(tok),
        "oauth_client_id_present": bool(cid),
        "oauth_client_id_prefix": (cid[:24] + "…") if cid else None,
        "scopes_requested": GBP_SCOPES,
        "token_present": bool(tok),
        "token_google_account": (tok or {}).get("google_account_email"),
        "token_rotated_at": (tok or {}).get("rotated_at"),
        "token_expires_in": (tok or {}).get("expires_in"),
        "token_fingerprint": ((tok or {}).get("fingerprint") or {}),
        "api_base": GBP_CONTENT_API,
    }
