"""Live publish adapter — Postiz (only when PUBLISH_MODE=live)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from _lib import publish_sandbox as sandbox
from _lib.postiz_client import create_post, list_integrations, postiz_status, upload_media
from _lib.publish_image import resolve_queue_upload_path


def _integration_for_platform(integrations: list[dict[str, Any]], platform: str) -> Optional[str]:
    want = (platform or "instagram").strip().lower()
    for it in integrations:
        if not isinstance(it, dict):
            continue
        provider = str(it.get("providerIdentifier") or it.get("provider") or it.get("type") or "").lower()
        name = str(it.get("name") or "").lower()
        if want in (provider, name) or want in provider or want in name:
            return str(it.get("id") or it.get("_id") or "") or None
    if integrations:
        first = integrations[0]
        return str(first.get("id") or first.get("_id") or "") or None
    return None


def _normalize_integrations(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for key in ("integrations", "identities", "items"):
            chunk = raw.get(key)
            if isinstance(chunk, list):
                return [x for x in chunk if isinstance(x, dict)]
    return []


def _media_ids_for_row(row: dict[str, Any]) -> list[str]:
    media_ids: list[str] = []
    resolved = resolve_queue_upload_path(row)
    if resolved is None:
        upload_path = str(row.get("image_path") or row.get("image_url") or "")
        if upload_path.startswith("/uploads/"):
            base = os.environ.get("ASSET_MEDIA_DIR") or str(sandbox._data_dir() / "uploads")
            upload_path = os.path.join(base, os.path.basename(upload_path))
        elif upload_path.startswith("http://") or upload_path.startswith("https://"):
            return media_ids
        if upload_path and os.path.isfile(upload_path):
            resolved = Path(upload_path)
    if resolved is None or not resolved.is_file():
        return media_ids
    data, err = upload_media(str(resolved))
    if not err and isinstance(data, dict):
        mid = data.get("id") or data.get("mediaId")
        if mid:
            media_ids.append(str(mid))
    return media_ids


def _dispatch_row_live(row: dict[str, Any], integrations: list[dict[str, Any]]) -> tuple[dict[str, Any], Optional[str]]:
    if not row.get("human_approved"):
        return {}, "human_approved required"
    key = str(row.get("idempotency_key") or "")
    if not key:
        return {}, "idempotency_key required"

    existing = sandbox._receipt_index().get(key)
    if existing:
        return existing, None

    platform = str(row.get("platform") or "instagram")
    integration_id = _integration_for_platform(integrations, platform)
    if not integration_id:
        return {}, f"no Postiz integration for platform={platform!r}"

    caption = str(row.get("caption") or row.get("caption_preview") or "").strip()
    if not caption:
        return {}, "empty caption"

    media_ids = _media_ids_for_row(row)
    publish_date = row.get("would_publish_at")
    if publish_date and not str(publish_date).endswith("Z"):
        publish_date = str(publish_date)

    result, err = create_post(
        integration_id=integration_id,
        content=caption,
        media_ids=media_ids,
        publish_date=str(publish_date) if publish_date else None,
    )
    if err:
        return {}, f"postiz create_post: {err[0]} {err[1][:200] if err[1] else ''}"

    postiz_id = None
    if isinstance(result, dict):
        postiz_id = result.get("id") or (result.get("post") or {}).get("id")
    if not postiz_id:
        return {}, "no postiz id returned"

    receipt = {
        "schema": sandbox.RECEIPT_SCHEMA,
        "mode": "live",
        "inbox_item_id": row.get("inbox_item_id"),
        "brand_id": row.get("brand_id"),
        "channel": row.get("channel", "postiz"),
        "platform": platform,
        "idempotency_key": key,
        "human_approved_at": row.get("human_approved_at"),
        "dispatched_at": sandbox._utc_now_iso(),
        "postiz_post_id": str(postiz_id),
        "caption_preview": caption[:120],
        "would_publish_at": row.get("would_publish_at"),
    }
    sandbox._append_jsonl(sandbox._receipts_path(), receipt)
    return receipt, None


def dispatch_pending() -> dict[str, Any]:
    """Process human-approved pending queue rows via Postiz."""
    sandbox.ensure_sandbox_layout()
    st = postiz_status()
    if not (st.get("configured") or st.get("ok") or st.get("api_key_present")):
        return {
            "ok": False,
            "mode": "live",
            "error": "Postiz not configured — connect via Connected Accounts / OAuth",
        }

    raw, int_err = list_integrations()
    if int_err:
        return {"ok": False, "mode": "live", "error": f"list_integrations: {int_err[0]}"}
    integrations = _normalize_integrations(raw)
    if not integrations:
        return {"ok": False, "mode": "live", "error": "no Postiz integrations connected"}

    queue_view = sandbox.list_queue(limit=200)
    targets = [
        it for it in (queue_view.get("items") or [])
        if it.get("human_approved") and str(it.get("status") or "") == "pending"
    ]

    rows = sandbox._read_jsonl(sandbox._queue_path())
    dispatched = 0
    refused = 0
    skipped = 0
    errors: list[str] = []

    updated_rows: list[dict[str, Any]] = []
    target_keys = {str(t.get("idempotency_key") or "") for t in targets}

    for row in rows:
        if row.get("status") != "pending":
            updated_rows.append(row)
            continue
        key = str(row.get("idempotency_key") or "")
        if key not in target_keys:
            if not row.get("human_approved"):
                skipped += 1
            updated_rows.append(row)
            continue
        enriched = next((t for t in targets if str(t.get("idempotency_key") or "") == key), row)
        receipt, err = _dispatch_row_live(enriched, integrations)
        if err:
            refused += 1
            errors.append(f"{key}: {err}")
            updated_rows.append(row)
            continue
        sandbox._stamp_queue_row_dispatched(row, receipt)
        dispatched += 1
        updated_rows.append(row)

    sandbox._rewrite_jsonl(sandbox._queue_path(), updated_rows)
    return {
        "ok": True,
        "mode": "live",
        "dispatched": dispatched,
        "refused": refused,
        "skipped_unapproved": skipped,
        "errors": errors[:20],
        "writes": ["publish-sandbox/queue.jsonl", "publish-sandbox/receipts.jsonl"],
    }
