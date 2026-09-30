"""
_lib/wp_publisher.py — WordPress REST adapter for Publish V1.

Brand isolation: the target is loaded from data/publishing-targets/<brand>.json,
keyed on operating_brand. The wp_api_base URL is taken from the target config —
never from caller input.

Auth: HTTP Basic with username + Application Password from env vars named in
the target config (wp_user_env, wp_app_password_env).

Idempotency: stage a draft with an existing_post_id → PUT /wp/v2/posts/<id>;
without → POST /wp/v2/posts. The CMS post id is returned for caller to persist.

Failure safety: any non-2xx response is recorded with the WP error body so the
audit log carries the actual CMS error.
"""
from __future__ import annotations
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from _lib.publish_v1 import load_publishing_target


def _wp_auth_header(target: dict) -> str | None:
    user_env = target.get("wp_user_env") or "WP_USER"
    pw_env = target.get("wp_app_password_env") or "WP_APP_PASSWORD"
    user = os.environ.get(user_env)
    pw = os.environ.get(pw_env)
    if not user or not pw:
        return None
    basic = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return f"Basic {basic}"


def _http(method: str, url: str, *, headers: dict, body: bytes | None = None, timeout: int = 30) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, method=method, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw or e.reason
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def send_to_cms(brand_id: str, payload: dict, *, existing_post_id: int | None = None) -> dict:
    """Stage a draft. Idempotent: existing_post_id → PUT, else POST.

    Returns {ok, cms_post_id, preview_url, edit_url, slug, ...}.
    """
    target = load_publishing_target(brand_id)
    if not target:
        return {"ok": False, "code": "TARGET_NOT_CONFIGURED", "error": f"no target for {brand_id!r}"}
    auth = _wp_auth_header(target)
    if not auth:
        return {"ok": False, "code": "CMS_AUTH_MISSING", "error": f"missing {target.get('wp_user_env')} or {target.get('wp_app_password_env')} env vars"}
    base = target.get("wp_api_base", "").rstrip("/")
    if not base:
        return {"ok": False, "code": "CMS_BASE_URL_MISSING", "error": "wp_api_base not configured"}

    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "CampaignOS-PublishV1/1.0",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if existing_post_id:
        url = f"{base}/posts/{existing_post_id}"
        status, data = _http("PUT", url, headers=headers, body=body)
    else:
        url = f"{base}/posts"
        status, data = _http("POST", url, headers=headers, body=body)

    if status not in (200, 201):
        return {"ok": False, "code": f"HTTP_{status}", "error": str(data)[:500], "http_status": status}

    if isinstance(data, dict):
        cms_id = data.get("id")
        slug = (data.get("slug") or {}).get("raw") if isinstance(data.get("slug"), dict) else data.get("slug")
        link = data.get("link")
        # WP edit URL: <wp_api_base>/../.. → /wp-admin/post.php?post=<id>&action=edit
        # We construct from the public URL by replacing /wp-json with /wp-admin
        edit_url = link.replace("/?p=", "/wp-admin/post.php?post=").replace("&post_type=post", "") if link else None
        if edit_url and "&action=edit" not in edit_url:
            edit_url = edit_url + ("&" if "?" in edit_url else "?") + "action=edit"
        # WP preview URL: ?preview=true
        preview_url = None
        if link:
            preview_url = link + ("&" if "?" in link else "?") + "preview=true"
        return {
            "ok": True,
            "cms_post_id": cms_id,
            "slug": slug,
            "live_url": link,
            "preview_url": preview_url,
            "edit_url": edit_url,
            "http_status": status,
        }
    return {"ok": False, "code": "BAD_RESPONSE", "error": "non-dict response from CMS"}


def publish_post(brand_id: str, cms_post_id: int) -> dict:
    """Push the staged draft to live. Idempotent: re-publishing an already-published
    post returns ok:true (WP returns 200 with same content).
    """
    target = load_publishing_target(brand_id)
    if not target:
        return {"ok": False, "code": "TARGET_NOT_CONFIGURED"}
    auth = _wp_auth_header(target)
    if not auth:
        return {"ok": False, "code": "CMS_AUTH_MISSING", "error": "missing WP creds env"}
    base = target.get("wp_api_base", "").rstrip("/")
    if not base:
        return {"ok": False, "code": "CMS_BASE_URL_MISSING"}
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "CampaignOS-PublishV1/1.0",
    }
    payload = json.dumps({"status": "publish"}).encode("utf-8")
    url = f"{base}/posts/{cms_post_id}"
    status, data = _http("PUT", url, headers=headers, body=payload)
    if status not in (200, 201):
        return {"ok": False, "code": f"HTTP_{status}", "error": str(data)[:500], "http_status": status}
    if isinstance(data, dict):
        return {
            "ok": True,
            "cms_post_id": data.get("id"),
            "slug": (data.get("slug") or {}).get("raw") if isinstance(data.get("slug"), dict) else data.get("slug"),
            "live_url": data.get("link"),
            "http_status": status,
        }
    return {"ok": False, "code": "BAD_RESPONSE", "error": "non-dict response"}


def test_target(brand_id: str) -> dict:
    """Diagnostic: confirm WP auth works + return canonical URL for the brand."""
    target = load_publishing_target(brand_id)
    if not target:
        return {"ok": False, "code": "TARGET_NOT_CONFIGURED"}
    auth = _wp_auth_header(target)
    if not auth:
        return {"ok": False, "code": "CMS_AUTH_MISSING", "error": "missing WP creds env"}
    base = target.get("wp_api_base", "").rstrip("/")
    headers = {
        "Authorization": auth,
        "Accept": "application/json",
        "User-Agent": "CampaignOS-PublishV1/1.0",
    }
    url = f"{base}/users/me"
    status, data = _http("GET", url, headers=headers)
    if status not in (200,):
        return {"ok": False, "code": f"HTTP_{status}", "error": str(data)[:300], "http_status": status}
    if isinstance(data, dict):
        return {
            "ok": True,
            "brand_id": brand_id,
            "wp_user_id": data.get("id"),
            "wp_user_slug": data.get("slug"),
            "wp_user_name": data.get("name"),
            "roles": data.get("roles", []),
            "cms_target": target.get("cms_target"),
            "wp_api_base": base,
        }
    return {"ok": False, "code": "BAD_RESPONSE", "error": "non-dict response"}
