"""Zernio (zernio.com) client — Bag Drop's scheduler (3 Nov 2026).

Bag Drop has no Postiz key; its Facebook page and Instagram are connected to the
bagdropmarketing Zernio account instead. Same rules as Postiz:

  * the brand's own key only, `ZERNIO_API_KEY_<BRAND>` — never a shared key;
  * never "now": the publish time is at least 5 minutes ahead (`scheduled_at_least`);
  * media must be a public HTTPS URL, so the image is copied into the app's
    public `/asset-media/` folder first.

API (docs.zernio.com, read 3 Nov 2026): `POST /v1/posts` with `content`, `scheduledFor`,
`mediaItems` and `platforms` [{platform, accountId, platformSpecificData}]; stories are
`platformSpecificData: {"contentType": "story"}` on Instagram and Facebook and show no
caption. The new post's id is `post._id`. `POST /v1/posts/{id}/unpublish` cancels it.
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple

from _lib.postiz_client import scheduled_at_least

API_BASE = "https://zernio.com/api/v1"
DEFAULT_MEDIA_BASE = "https://swing-shack-dashboard-production.up.railway.app"

# Connected accounts on the bagdropmarketing Zernio profile (accounts_list, 2 Nov 2026).
# Not secret; the key is.
ACCOUNTS: dict[str, dict[str, str]] = {
    "bag-drop": {
        "instagram": "6ae495c429bfc60dc4f11e2d",  # the_bagdrop_za
        "facebook": "6ae4933b7c0b0a428ec6b173",   # The Bag Drop
    },
}


def _env_name(brand_id: str) -> str:
    return "ZERNIO_API_KEY_" + str(brand_id or "").upper().replace("-", "_")


def _key(brand_id: str) -> str:
    return (os.environ.get(_env_name(brand_id)) or "").strip()


def has_brand_key(brand_id: str | None) -> bool:
    """True only when this brand has its OWN Zernio key and known accounts."""
    return bool(brand_id) and bool(_key(brand_id)) and brand_id in ACCOUNTS


def public_media_url(path: str | Path) -> str:
    """Copy a local image into the app's public /asset-media/ folder; return its HTTPS URL."""
    src = Path(path)
    data_dir = os.environ.get("DATA_DIR")
    folder = Path(data_dir) / "asset-media" if data_dir else Path(__file__).resolve().parents[1] / "data" / "asset-media"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"zernio-{uuid.uuid4().hex[:12]}{src.suffix.lower() or '.jpg'}"
    shutil.copyfile(src, folder / name)
    base = (os.environ.get("ZERNIO_MEDIA_BASE_URL") or DEFAULT_MEDIA_BASE).rstrip("/")
    return f"{base}/asset-media/{name}"


def _request(method: str, path: str, brand_id: str, body: dict | None = None,
             idempotency_key: str | None = None) -> Tuple[Optional[dict], Optional[str]]:
    req = urllib.request.Request(
        API_BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {_key(brand_id)}", "Content-Type": "application/json"},
    )
    if idempotency_key:
        req.add_header("Idempotency-Key", idempotency_key)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200] if hasattr(exc, "read") else ""
        return None, f"zernio {exc.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"zernio unreachable: {exc}"
    try:
        return (json.loads(raw) if raw else {}), None
    except ValueError:
        return None, "zernio returned non-JSON"


def create_post(*, brand_id: str, content: str, image_url: str, publish_date: str | None,
                story: bool, idempotency_key: str | None = None) -> Tuple[Optional[dict], Optional[str]]:
    """Schedule one image on the brand's Instagram and Facebook. Returns (post, error)."""
    if not has_brand_key(brand_id):
        return None, f"{_env_name(brand_id)} not set (no shared-key fallback)"
    when, _moved = scheduled_at_least(publish_date)
    extra = {"platformSpecificData": {"contentType": "story"}} if story else {}
    body = {
        "content": content,
        "scheduledFor": when,
        "mediaItems": [{"type": "image", "url": image_url}],
        "platforms": [
            {"platform": platform, "accountId": account_id, **extra}
            for platform, account_id in ACCOUNTS[brand_id].items()
        ],
    }
    data, err = _request("POST", "/posts", brand_id, body, idempotency_key)
    if err:
        return None, err
    post = (data or {}).get("post") if isinstance(data, dict) else None
    if not isinstance(post, dict) or not post.get("_id"):
        return None, "no post id returned"
    post.setdefault("scheduledFor", when)
    return post, None


def unpublish_post(post_id: str, *, brand_id: str) -> Tuple[Optional[dict], Optional[str]]:
    """Cancel a scheduled post (it becomes a cancelled draft on Zernio)."""
    if not has_brand_key(brand_id):
        return None, f"{_env_name(brand_id)} not set"
    return _request("POST", f"/posts/{post_id}/unpublish", brand_id, {})
