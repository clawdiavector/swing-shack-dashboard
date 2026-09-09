"""
connection_status.py — Per-brand Postiz OAuth publishing readiness.

Returns a UI-ready status payload that separates:

  POSTIZ API   — the API key is wired (technical baseline)
  PUBLISHING   — per (brand, channel) whether that brand can actually
                 be published to right now

State machine (UI-side):
  POSTIZ_API_STATE:
    - "connected"   (green)   key + client id/secret present
    - "needs_setup" (amber)   partial config
    - "missing"     (red)     no config
  CHANNEL_STATE (per brand x channel):
    - "ready"       (green)   OAuth token present + integration live
    - "needs_oauth" (amber)   brand not yet connected via OAuth
    - "missing_api" (red)     no API key — connect Postiz first

Per user directive (PHASE L-1): split "Postiz connected" from
"actually publishable to brand X".
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# Channels we surface in the workspace
PUBLISHING_CHANNELS = ["instagram", "facebook", "tiktok", "x", "linkedin", "gbp"]


def _data_root() -> Path:
    candidates = []
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    if bundled:
        candidates.append(Path(bundled))
    candidates.append(Path(os.environ.get("DATA_DIR") or "/data/campaign-os"))
    candidates.append(Path(
        "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data"
    ))
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


def _brand_dir(brand_id: str) -> Path:
    d = _data_root() / "brand-directory" / brand_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _oauth_path(brand_id: str) -> Path:
    return _brand_dir(brand_id) / "postiz-oauth.json"


def save_oauth_connection(brand_id: str, channel: str, token_payload: dict) -> Path:
    """Persist a per-brand OAuth token after a successful Postiz OAuth dance.

    token_payload: {access_token, refresh_token, expires_at, integration_id, ...}
    """
    p = _oauth_path(brand_id)
    if p.exists():
        try:
            data = json.loads(p.read_text())
        except Exception:
            data = {"brand_id": brand_id, "channels": {}}
    else:
        data = {"brand_id": brand_id, "channels": {}, "updated_at": None}
    data["channels"][channel] = {
        **token_payload,
        "connected_at": datetime.utcnow().isoformat() + "Z",
    }
    data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    p.write_text(json.dumps(data, indent=2, default=str))
    return p


def remove_oauth_connection(brand_id: str, channel: Optional[str] = None) -> bool:
    """Remove a brand's OAuth connection. If channel is given, only that channel."""
    p = _oauth_path(brand_id)
    if not p.exists():
        return False
    if channel is None:
        p.unlink()
        return True
    data = json.loads(p.read_text())
    if channel in data.get("channels", {}):
        del data["channels"][channel]
        data["updated_at"] = datetime.utcnow().isoformat() + "Z"
        p.write_text(json.dumps(data, indent=2, default=str))
        return True
    return False


def get_brand_oauth(brand_id: str) -> dict:
    """Return the brand's OAuth token bag, or empty."""
    p = _oauth_path(brand_id)
    if not p.exists():
        return {"brand_id": brand_id, "channels": {}}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"brand_id": brand_id, "channels": {}}


def _postiz_api_state() -> str:
    """Check the Postiz API config state."""
    # Look at the env vars + credential files (mirrors postiz_client._read_*)
    api_key = (
        os.environ.get("POSTIZ_API_KEY")
        or os.environ.get("POSTIZ_API_TOKEN")
    )
    if not api_key:
        # Look at credentials dir
        for path in [
            Path.home() / ".openclaw-instance2" / "workspace" / "clients" / "swing-shack" / "credentials" / "postiz-api.json",
            Path("/data/postiz-api.json"),
        ]:
            if path.exists():
                try:
                    d = json.loads(path.read_text())
                    if d.get("api_key") or d.get("key"):
                        api_key = "from-file"
                        break
                except Exception:
                    pass
    cid = os.environ.get("POSTIZ_OAUTH_CLIENT_ID")
    secret = os.environ.get("POSTIZ_OAUTH_CLIENT_SECRET")
    if api_key and cid and secret:
        return "connected"
    if api_key or cid or secret:
        return "needs_setup"
    return "missing"


def get_connection_status(brand_id: Optional[str] = None) -> dict:
    """Build the full UI-ready connection status.

    If brand_id is provided, focuses on that brand.
    Otherwise returns a per-brand breakdown.

    Returns:
      {
        postiz_api: {state: "connected"|"needs_setup"|"missing", ...},
        publishing: {
          <brand_id>: {
            instagram: {state, integration_id?, expires_at?, ...},
            facebook:  {...},
            ...
          },
          ...
        },
        brands: [brand_id, ...]
      }
    """
    api_state = _postiz_api_state()
    # Per brand per channel
    brands = []
    if brand_id:
        brands = [brand_id]
    else:
        bd = _data_root() / "brand-directory"
        if bd.exists():
            brands = sorted([p.name for p in bd.iterdir() if p.is_dir()])

    publishing: Dict[str, Dict[str, Any]] = {}
    for b in brands:
        oauth = get_brand_oauth(b)
        channels = oauth.get("channels", {})
        per_channel: Dict[str, Any] = {}
        for ch in PUBLISHING_CHANNELS:
            if ch in channels:
                tok = channels[ch]
                # Determine state
                if api_state != "connected":
                    state = "missing_api"
                else:
                    expires_at = tok.get("expires_at")
                    if expires_at:
                        try:
                            exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                            if exp < datetime.now(exp.tzinfo):
                                state = "needs_oauth"  # expired
                            else:
                                state = "ready"
                        except Exception:
                            state = "ready"
                    else:
                        state = "ready"
                per_channel[ch] = {
                    "state": state,
                    "integration_id": tok.get("integration_id"),
                    "connected_at": tok.get("connected_at"),
                    "expires_at": tok.get("expires_at"),
                    "account_label": tok.get("account_label") or tok.get("username") or "",
                }
            else:
                per_channel[ch] = {"state": "needs_oauth"}
        publishing[b] = per_channel

    # Aggregate overall publishing state
    overall = "ready"
    if api_state != "connected":
        overall = "missing_api"
    else:
        any_brand_has_channel = False
        for b, chans in publishing.items():
            for c, info in chans.items():
                if info["state"] == "ready":
                    any_brand_has_channel = True
                    break
        if not any_brand_has_channel:
            overall = "needs_oauth"

    return {
        "postiz_api": {
            "state": api_state,
            "label": {
                "connected": "Connected",
                "needs_setup": "Partially configured",
                "missing": "Not configured",
            }.get(api_state, api_state),
        },
        "publishing_overall": overall,
        "publishing": publishing,
        "brands": brands,
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }


def oauth_init_url(brand_id: str, channel: str = "instagram") -> Optional[str]:
    """Return the OAuth init URL for a (brand, channel) — frontend uses this
    for the CONNECT button."""
    cid = os.environ.get("POSTIZ_OAUTH_CLIENT_ID")
    redirect = os.environ.get("POSTIZ_OAUTH_REDIRECT_URI") or "https://swing-shack-dashboard-production.up.railway.app/api/postiz/oauth/callback"
    if not cid:
        return None
    base = "https://api.postiz.com/oauth/authorize"
    return (
        f"{base}?client_id={cid}"
        f"&redirect_uri={redirect}"
        f"&response_type=code"
        f"&state={brand_id}:{channel}"
        f"&scope=channels.read+channels.write+integrations.read+integrations.write+publications.write"
    )
