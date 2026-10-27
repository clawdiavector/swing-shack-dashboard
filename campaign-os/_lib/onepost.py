"""One post, N channel deliveries — shared channel and delivery state logic."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

COMING_SOON_CHANNELS = frozenset({"youtube"})
MAX_SEND_ATTEMPTS = 3
CHANNELS_LOCKED_STATES = frozenset({"released", "partly_posted", "send_failed", "posted"})
_FEED_IMAGE_PLATFORMS = frozenset({"facebook", "gbp", "youtube", "tiktok"})


def brand_channels(brand_id: str) -> list[str]:
    from _lib.publish_sandbox import (  # noqa: PLC0415
        _normalize_platform,
        intended_publish_channels,
        platform_allowed,
    )
    from _lib.brand_validate import validate_brand_id

    brand_id = validate_brand_id(brand_id)
    out: list[str] = []
    seen: set[str] = set()
    for ch in intended_publish_channels(brand_id):
        norm = _normalize_platform(str(ch))
        if norm in COMING_SOON_CHANNELS:
            continue
        if not platform_allowed(brand_id, norm):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def default_channels(brand_id: str) -> list[str]:
    from _lib.publish_sandbox import COMPOSE_PUBLISH_CHANNEL_EXCLUDE  # noqa: PLC0415

    return [ch for ch in brand_channels(brand_id) if ch not in COMPOSE_PUBLISH_CHANNEL_EXCLUDE]


def render_channels(brand_id: str) -> list[str]:
    _ = brand_id
    return ["instagram"]


def normalize_picked_channels(channels: list[str], brand_id: str) -> list[str]:
    from _lib.publish_sandbox import _normalize_platform  # noqa: PLC0415

    allowed = set(brand_channels(brand_id))
    out: list[str] = []
    seen: set[str] = set()
    for raw in channels:
        norm = _normalize_platform(str(raw))
        if norm in COMING_SOON_CHANNELS:
            raise ValueError(f"channel {norm!r} is not available yet")
        if norm not in allowed:
            raise ValueError(f"channel {norm!r} is not allowed for brand {brand_id!r}")
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    if not out:
        raise ValueError("at least one channel is required")
    return out


def picked_channels(
    asset: dict[str, Any] | None,
    *,
    brand_id: str,
    queue_rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    from _lib.publish_sandbox import _normalize_platform  # noqa: PLC0415

    if asset and isinstance(asset.get("channels"), list) and asset.get("channels"):
        return normalize_picked_channels([str(c) for c in asset["channels"]], brand_id)
    if queue_rows:
        picked = {
            _normalize_platform(str(r.get("platform") or ""))
            for r in queue_rows
            if str(r.get("status") or "") not in ("rejected", "skipped")
        }
        picked.discard("")
        if picked:
            return sorted(picked)
    return list(default_channels(brand_id))


def channels_locked_for_state(state: str) -> bool:
    return str(state or "") in CHANNELS_LOCKED_STATES


def _receipt_by_key(receipts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rec in receipts:
        key = str(rec.get("idempotency_key") or "")
        if key:
            out[key] = rec
    return out


def delivery_chip_status(
    row: dict[str, Any],
    receipt: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> str:
    from _lib import publish_sandbox  # noqa: PLC0415

    status = str(row.get("status") or "pending")
    if status == "skipped":
        return "skipped"
    if status == "failed":
        return "failed"
    if receipt:
        if str(receipt.get("mode") or "") == "sandbox":
            return "sandbox_only"
        return "posted"
    if status == "dispatched":
        return "posted"
    if not row.get("human_approved"):
        return "awaiting_approval"
    attempts = int(row.get("attempts") or 0)
    if status == "pending" and attempts > 0 and row.get("last_error"):
        return "sending"
    when = str(row.get("would_publish_at") or "")
    if status == "pending" and when and not publish_sandbox.row_is_due(when, now=now):
        return "queued"
    if status == "pending":
        return "queued"
    return status


def build_deliveries(
    *,
    brand_id: str,
    asset: dict[str, Any] | None,
    queue_rows: list[dict[str, Any]],
    receipts: list[dict[str, Any]],
    now: datetime | None = None,
) -> tuple[list[str], list[dict[str, Any]], dict[str, int]]:
    from _lib.publish_sandbox import _normalize_platform  # noqa: PLC0415

    now = now or datetime.now(timezone.utc)
    picked = picked_channels(asset, brand_id=brand_id, queue_rows=queue_rows)
    rec_by_key = _receipt_by_key(receipts)
    deliveries: list[dict[str, Any]] = []
    summary = {"picked": len(picked), "posted": 0, "failed": 0, "queued": 0}

    row_by_plat = {
        _normalize_platform(str(r.get("platform") or "")): r for r in queue_rows
    }
    for ch in picked:
        row = row_by_plat.get(ch) or {}
        key = str(row.get("idempotency_key") or "")
        receipt = rec_by_key.get(key)
        chip = delivery_chip_status(row, receipt, now=now)
        if chip == "posted":
            summary["posted"] += 1
        elif chip == "failed":
            summary["failed"] += 1
        elif chip in ("queued", "sending", "awaiting_approval", "sandbox_only"):
            summary["queued"] += 1
        ext = row.get("external_id")
        if not ext and receipt:
            ext = receipt.get("postiz_post_id") or receipt.get("sandbox_post_id")
        deliveries.append(
            {
                "channel": ch,
                "status": chip,
                "idempotency_key": key or None,
                "would_publish_at": row.get("would_publish_at"),
                "dispatched_at": row.get("dispatched_at") or (receipt or {}).get("dispatched_at"),
                "external_id": ext,
                "attempts": int(row.get("attempts") or 0),
                "last_error": row.get("last_error"),
            }
        )
    return picked, deliveries, summary


def derive_post_state_from_deliveries(
    *,
    picked: list[str],
    deliveries: list[dict[str, Any]],
    draft: dict[str, Any] | None,
    prior_state: str,
) -> tuple[str, str | None]:
    if not picked:
        return prior_state, None
    posted = sum(1 for d in deliveries if d.get("status") == "posted")
    failed = sum(1 for d in deliveries if d.get("status") == "failed")
    awaiting = sum(1 for d in deliveries if d.get("status") == "awaiting_approval")
    if posted == len(picked):
        return "posted", None
    if posted > 0 and posted < len(picked):
        failed_names = [
            d["channel"] for d in deliveries if d.get("status") == "failed"
        ]
        hint = f"Posted to {posted} of {len(picked)}"
        if failed_names:
            hint += f": {failed_names[0].title()} failed"
        return "partly_posted", hint
    if posted == 0 and failed > 0:
        err = next(
            (d.get("last_error") for d in deliveries if d.get("status") == "failed"),
            None,
        )
        short = str(err or "send failed")[:80]
        ch = next(
            (d["channel"] for d in deliveries if d.get("status") == "failed"),
            "channel",
        )
        return "send_failed", f"{ch} failed: {short}"
    if awaiting == 0 and any(
        d.get("status") in ("queued", "sending") for d in deliveries
    ):
        return "released", None
    if awaiting > 0 and any(
        d.get("status") in ("queued", "sending") for d in deliveries
    ):
        return "released", None
    if draft and draft.get("draft_bucket") == "approved":
        return "scheduled", None
    return prior_state, None
