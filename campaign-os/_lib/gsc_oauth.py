"""gsc_oauth.py — Google OAuth for Search Console (webmasters.readonly).

Per-brand operator tokens stored encrypted at rest under credentials/gsc/<brand>.json.
Falls back to default brand token then legacy default.json.
"""

from __future__ import annotations

import base64
import hashlib
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

_LOG = logging.getLogger("campaign_os.gsc_oauth")

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

GSC_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/webmasters.readonly",
]


def _default_brand_id() -> str:
    try:
        from _lib.jobs.layer1._io import _fallback_brand

        return _fallback_brand()
    except Exception:
        return "swing-shack"


def _normalize_brand(brand: str | None) -> str:
    return (brand or _default_brand_id()).strip() or "swing-shack"


def _token_key_candidates(brand: str | None) -> list[str]:
    bid = _normalize_brand(brand)
    default_bid = _default_brand_id()
    keys = [bid]
    if default_bid not in keys:
        keys.append(default_bid)
    if "default" not in keys:
        keys.append("default")
    return keys


def _credentials_dirs() -> list[Path]:
    dirs: list[Path] = []
    for key in ("DATA_DIR",):
        val = os.environ.get(key)
        if val:
            p = Path(val) / "credentials"
            if p not in dirs:
                dirs.append(p)
    for p in (
        Path(os.path.expanduser("~/.openclaw/workspace/credentials")),
        Path(os.path.expanduser("~/.openclaw-instance2/workspace/clients/swing-shack/credentials")),
    ):
        if p not in dirs:
            dirs.append(p)
    return dirs


def _read_client_id_secret() -> Tuple[Optional[str], Optional[str]]:
    cid = os.environ.get("GSC_OAUTH_CLIENT_ID") or os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    secret = os.environ.get("GSC_OAUTH_CLIENT_SECRET") or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if cid and secret:
        return cid, secret
    for base in _credentials_dirs():
        path = base / "google-search-console-oauth.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            web = data.get("web") or data.get("installed") or data
            cid = web.get("client_id") or data.get("client_id")
            secret = web.get("client_secret") or data.get("client_secret")
            if cid and secret:
                return cid, secret
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
    return None, None


def gsc_oauth_credentials_present() -> bool:
    cid, _ = _read_client_id_secret()
    return bool(cid)


def _token_dir() -> Path:
    base_dir = os.environ.get("GSC_TOKEN_DIR") or os.environ.get("DATA_DIR")
    if base_dir:
        base = Path(base_dir) / "credentials" / "gsc"
    else:
        base = Path(os.path.expanduser("~/.openclaw/workspace/credentials/gsc"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def _token_path(brand: str | None = None) -> Path:
    return _token_dir() / f"{_normalize_brand(brand)}.json"


def _state_secret() -> bytes:
    raw = os.environ.get("GSC_OAUTH_STATE_SECRET") or os.environ.get("SESSION_SECRET") or "dev-only-gsc-state"
    return raw.encode("utf-8") if isinstance(raw, str) else raw


def make_state(brand_id: str | None = None, user_id: str = "operator", ttl_seconds: int = 600) -> str:
    import hmac

    brand = _normalize_brand(brand_id)
    payload = f"gsc|{brand}|{user_id}|{secrets.token_urlsafe(16)}|{int(time.time()) + ttl_seconds}"
    sig = hmac.new(_state_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode("utf-8")).decode("ascii").rstrip("=")


def verify_state(state_b64: str, expected_user_id: str = "operator") -> Tuple[bool, str, str | None]:
    import hmac

    try:
        padded = state_b64 + "=" * (-len(state_b64) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        payload, sig = raw.rsplit("|", 1)
        channel, brand_id_s, user_id_s, _nonce, exp_s = payload.split("|", 4)
        if channel != "gsc":
            return False, f"state bound to {channel!r}, not gsc", None
        if user_id_s != expected_user_id:
            return False, f"state bound to user {user_id_s!r}, not {expected_user_id!r}", None
        if int(exp_s) < int(time.time()):
            return False, "state expired", None
        expected_sig = hmac.new(_state_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return False, "state signature invalid", None
        return True, "ok", brand_id_s
    except Exception as exc:
        return False, f"state parse failed: {exc}", None


def build_authorize_url(redirect_uri: str, state: str) -> str:
    cid, _ = _read_client_id_secret()
    if not cid:
        raise RuntimeError("GSC OAuth client_id not configured")
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GSC_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return GOOGLE_AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)


def exchange_code(code: str, redirect_uri: str) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    cid, secret = _read_client_id_secret()
    if not cid or not secret:
        raise RuntimeError("GSC OAuth client_id and client_secret both required")
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body)
        except Exception:
            pass
        return None, (str(exc.code), body if isinstance(body, dict) else body[:500])


def refresh_access_token(refresh_token: str) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    cid, secret = _read_client_id_secret()
    if not cid or not secret:
        raise RuntimeError("GSC OAuth client_id and client_secret both required")
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body)
        except Exception:
            pass
        return None, (str(exc.code), body if isinstance(body, dict) else body[:500])


def _fernet():
    from cryptography.fernet import Fernet

    raw = os.environ.get("META_TOKEN_ENCRYPTION_KEY") or os.environ.get("SESSION_SECRET") or "dev-only"
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw).digest()))


def _read_token_record(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    cipher = record.get("encrypted_tokens") or {}
    if not cipher:
        return None
    enc = _fernet()
    out: dict[str, Any] = {}
    for key, value in cipher.items():
        try:
            out[key] = enc.decrypt(value.encode("ascii")).decode("utf-8")
        except Exception as exc:
            _LOG.warning("gsc_token_decrypt_failed key=%s err=%s", key, exc)
            return None
    out["expires_in"] = record.get("expires_in")
    out["scope"] = record.get("scope")
    out["token_type"] = record.get("token_type")
    out["rotated_at"] = record.get("rotated_at")
    out["google_account_email"] = record.get("google_account_email")
    out["_token_path"] = str(path)
    return out


def save_token(
    token_payload: dict,
    *,
    brand: str | None = None,
    google_account_email: Optional[str] = None,
    note: Optional[str] = None,
) -> Path:
    import datetime as dt

    enc = _fernet()
    payload = dict(token_payload)
    plain: dict[str, str] = {}
    for key in ("access_token", "refresh_token", "id_token"):
        if key in payload:
            plain[key] = payload.pop(key)
    cipher = {k: enc.encrypt(v.encode("utf-8")).decode("ascii") for k, v in plain.items()}
    record: dict[str, Any] = {
        "encrypted_tokens": cipher,
        "expires_in": payload.get("expires_in"),
        "token_type": payload.get("token_type"),
        "scope": payload.get("scope"),
        "rotated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "fingerprint": {k: hashlib.sha256(v.encode("utf-8")).hexdigest()[:8] for k, v in plain.items()},
        "brand_id": _normalize_brand(brand),
    }
    if google_account_email:
        record["google_account_email"] = google_account_email
    if note:
        record["note"] = note
    path = _token_path(brand)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)
    _LOG.info("gsc_token_saved brand=%s expires_in=%s", record.get("brand_id"), record.get("expires_in"))
    return path


def load_token(brand: str | None = None) -> Optional[dict]:
    for key in _token_key_candidates(brand):
        tok = _read_token_record(_token_dir() / f"{key}.json")
        if tok:
            return tok
    return None


def delete_token(brand: str | None = None) -> bool:
    path = _token_path(brand)
    if path.exists():
        path.unlink()
        _LOG.info("gsc_token_deleted brand=%s", _normalize_brand(brand))
        return True
    return False


def get_access_token(brand: str | None = None) -> Optional[str]:
    """Return a valid access token, refreshing via refresh_token when present."""
    tok = load_token(brand=brand)
    if not tok:
        return None
    refresh = tok.get("refresh_token")
    brand_id = None
    token_path = tok.get("_token_path") or ""
    if token_path.endswith(".json"):
        brand_id = Path(token_path).stem
        if brand_id == "default":
            brand_id = _default_brand_id()
    if refresh:
        data, err = refresh_access_token(refresh)
        if data and data.get("access_token"):
            merged = {**tok, **data}
            if "refresh_token" not in data:
                merged["refresh_token"] = refresh
            save_token(
                merged,
                brand=brand_id or brand,
                google_account_email=tok.get("google_account_email"),
                note="auto-refresh",
            )
            return merged["access_token"]
        if err:
            _LOG.warning("gsc_refresh_failed err=%s", err)
    return tok.get("access_token")


def gsc_status(brand: str | None = None) -> dict:
    cid, _ = _read_client_id_secret()
    tok = load_token(brand=brand)
    return {
        "ok": bool(cid) and bool(tok),
        "brand_id": _normalize_brand(brand),
        "oauth_client_id_present": bool(cid),
        "oauth_client_id_prefix": (cid[:24] + "…") if cid else None,
        "scopes_requested": GSC_SCOPES,
        "token_present": bool(tok),
        "token_google_account": (tok or {}).get("google_account_email"),
        "token_rotated_at": (tok or {}).get("rotated_at"),
        "token_expires_in": (tok or {}).get("expires_in"),
    }
