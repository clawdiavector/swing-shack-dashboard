"""Schedule Postiz posts when a queue row is approved (live + CAMPAIGN_OS_POSTIZ_ON_APPROVE)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

_LOG = logging.getLogger("campaign_os.postiz_on_approve")

from _lib.brand_validate import validate_brand_id
from _lib import publish_sandbox as sandbox
from _lib.postiz_client import (
    create_post,
    delete_post,
    has_brand_key,
    scheduled_at_least,
)
from _lib.publish_mode import is_live_mode
from _lib import publish_live


def is_enabled() -> bool:
    raw = (os.environ.get("CAMPAIGN_OS_POSTIZ_ON_APPROVE") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _resolve_would_publish_at(row: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    when = str(row.get("would_publish_at") or "").strip()
    if when:
        return when, None
    event_date = str(row.get("event_date") or "").strip()
    derived = sandbox._would_publish_at_from_event_date(event_date)  # noqa: SLF001
    if derived:
        return derived, None
    return None, "would_publish_at missing — set schedule or event_date on the queue row"


_CLEAR_BUFFER = timedelta(minutes=2)


def _parse_postiz_scheduled_at(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clear_action_for_receipt(rec: dict[str, Any]) -> tuple[Literal["noop", "delete", "refuse"], Optional[str]]:
    """Whether un-approve may delete a Postiz post tied to this live receipt."""
    scheduled_raw = str(rec.get("postiz_scheduled_at") or "").strip()
    if not scheduled_raw:
        return "noop", None

    when = _parse_postiz_scheduled_at(scheduled_raw)
    if when is None:
        return "noop", None

    now = datetime.now(timezone.utc)
    if when <= now + _CLEAR_BUFFER:
        return "refuse", f"already sent to Postiz at {scheduled_raw}; cannot un-approve"

    return "delete", None


def _live_receipt_for_key(key: str) -> dict[str, Any] | None:
    rec = sandbox._receipt_index().get(key)  # noqa: SLF001
    if not rec:
        return None
    if str(rec.get("mode") or "") == "sandbox":
        return None
    return rec


def schedule_row_on_approve(row: dict[str, Any]) -> tuple[dict[str, Any], Optional[str]]:
    """Create a scheduled Postiz post for an approved row when gated on."""
    if not is_live_mode() or not is_enabled():
        return {}, None

    if not row.get("human_approved"):
        return {}, "human_approved required"

    key = str(row.get("idempotency_key") or "")
    if not key:
        return {}, "idempotency_key required"

    existing = _live_receipt_for_key(key)
    if existing:
        return existing, None

    try:
        brand_id = validate_brand_id(row.get("brand_id") or "")
    except ValueError as exc:
        return {}, str(exc)

    if not has_brand_key(brand_id):
        return {}, f"Postiz API key required for brand={brand_id!r} (no shared-key fallback)"

    planned, date_err = _resolve_would_publish_at(row)
    if date_err:
        return {}, date_err

    publish_date, _moved = scheduled_at_least(planned)
    enriched = sandbox.refresh_queue_row_from_draft(dict(row))
    caption = str(enriched.get("caption") or enriched.get("caption_preview") or "").strip()
    if not caption:
        return {}, "empty caption"
    has_image = bool(str(enriched.get("image_url") or enriched.get("image_path") or "").strip())
    if has_image:
        ok, pre_err = True, ""
    else:
        ok, pre_err = sandbox.preflight_queue_row(enriched)
    if not ok:
        return {}, f"preflight: {pre_err}"

    integrations_cache: dict[str, list[dict[str, Any]]] = {}
    integrations, load_err = publish_live._integrations_for_brand(brand_id, integrations_cache)
    if load_err:
        return {}, load_err

    platform = str(enriched.get("platform") or "instagram")
    integration_id = publish_live._integration_for_platform(integrations, platform)
    if not integration_id:
        return {}, f"no Postiz integration for platform={platform!r}"

    media = publish_live._media_for_row(enriched, brand_id=brand_id)

    result, err = create_post(
        integration_id=integration_id,
        content=caption,
        media=media,
        brand_id=brand_id,
        publish_date=publish_date,
        platform_settings={"post_type": "post"},
    )
    if err:
        return {}, f"postiz create_post: {err[0]}"

    postiz_id = None
    if isinstance(result, list) and result:
        result = result[0]
    if isinstance(result, dict):
        postiz_id = (
            result.get("id")
            or result.get("postId")
            or (result.get("post") or {}).get("id")
        )
    if not postiz_id:
        return {}, "no postiz id returned"

    receipt = {
        "schema": sandbox.RECEIPT_SCHEMA,
        "mode": "live",
        "inbox_item_id": enriched.get("inbox_item_id"),
        "brand_id": brand_id,
        "channel": enriched.get("channel", "postiz"),
        "platform": platform,
        "idempotency_key": key,
        "human_approved_at": enriched.get("human_approved_at"),
        "dispatched_at": sandbox._utc_now_iso(),  # noqa: SLF001
        "postiz_post_id": str(postiz_id),
        "caption_preview": caption[:120],
        "would_publish_at": planned,
        "postiz_scheduled_at": publish_date,
    }
    sandbox._append_jsonl(sandbox._receipts_path(), receipt)  # noqa: SLF001
    return receipt, None


def clear_postiz_on_unapprove(idempotency_key: str) -> tuple[dict[str, Any], Optional[str]]:
    """Delete a future schedule-on-approve Postiz post and drop that receipt only."""
    key = str(idempotency_key or "").strip()
    if not key:
        return {}, "idempotency_key required"

    rec = _live_receipt_for_key(key)
    if not rec:
        return {}, None

    action, refuse_err = _clear_action_for_receipt(rec)
    if action == "refuse":
        return {}, refuse_err
    if action == "noop":
        return {"cleared_postiz": False, "kept_receipt": True}, None

    postiz_id = str(rec.get("postiz_post_id") or "").strip()
    brand_id = str(rec.get("brand_id") or "")
    if not (postiz_id and is_live_mode() and has_brand_key(brand_id)):
        return {"cleared_postiz": False, "kept_receipt": True}, None

    _data, err = delete_post(postiz_id, brand_id=brand_id)
    if err:
        msg = err[1] if isinstance(err[1], str) else str(err[1])
        return {}, f"postiz delete_post: {err[0]} {msg[:120]}".strip()

    path = sandbox._receipts_path()  # noqa: SLF001
    rows = sandbox._read_jsonl(path)  # noqa: SLF001
    kept = [r for r in rows if str(r.get("idempotency_key") or "") != key]
    if len(kept) != len(rows):
        sandbox._rewrite_jsonl(path, kept)  # noqa: SLF001
    return {"removed_receipt": True, "postiz_post_id": postiz_id}, None
