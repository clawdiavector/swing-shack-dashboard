"""L5 retry_failed_images — auto-enqueue operator moments and reset bad image rows."""

from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..layer1._io import atomic_write, read_json, utc_now_iso
from _lib.brand_validate import validate_brand_id

from .draft_assets import (
    CAPTION_EST_USD,
    IMAGE_EST_USD,
    _PHOTO_EQUIV,
    _moment_has_composed,
    _moment_has_image,
    _parse_inbox_ref,
    _read_queue,
    _write_queue,
)

HORIZON_DAYS = 14
MAX_IMAGE_RETRIES = 3
_RETRY_COUNT_KEY = "image_retry_count"
_ENQUEUE_REASON = "auto-image-retry"


def _data_dir():
    from pathlib import Path

    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _today_sast() -> date:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Africa/Johannesburg")
    except Exception:  # noqa: BLE001
        tz = timezone.utc
    return datetime.now(tz).date()


def _horizon_dates(*, start: date | None = None, days: int = HORIZON_DAYS) -> set[str]:
    base = start or _today_sast()
    return {(base + timedelta(days=offset)).isoformat() for offset in range(days)}


def _record_go_live(record: dict[str, Any]) -> str | None:
    for key in ("event_date", "event_start", "event_window_start"):
        raw = record.get(key)
        if raw and isinstance(raw, str):
            return raw[:10]
    return None


def _skip_auto_moment(record: dict[str, Any]) -> bool:
    if str(record.get("created_by") or "") == "holiday_inject":
        return True
    source = str(record.get("source_type") or "").lower()
    if source in ("deterministic",):
        return True
    if str(record.get("source_origin") or "") == "deterministic_calendar":
        return True
    return False


def _calendar_item_id(brand_id: str, record: dict[str, Any]) -> str | None:
    cal_id = str(record.get("calendar_id") or record.get("event_key") or "").strip()
    if not cal_id:
        return None
    return f"calendar_candidate:{brand_id}:{cal_id}"


def _rows_for_item(rows: list[dict[str, Any]], item_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if _parse_inbox_ref(str(row.get("payload_ref") or "")) != item_id:
            continue
        out.append(row)
    return out


def _retry_count(row: dict[str, Any], *, item_id: str | None = None) -> int:
    from . import image_jobs_state  # noqa: PLC0415

    row_fallback: int | None = None
    try:
        row_fallback = max(0, int(row.get(_RETRY_COUNT_KEY) or 0))
    except (TypeError, ValueError):
        row_fallback = 0
    if item_id:
        return image_jobs_state.retry_count(item_id, row_fallback=row_fallback)
    return row_fallback or 0


def _spend_cap_blocks_enqueue(*, include_image: bool) -> bool:
    from _lib import llm_spend  # noqa: PLC0415

    est = CAPTION_EST_USD + (IMAGE_EST_USD if include_image else 0.0)
    allowed, _reason = llm_spend.check("text", est)
    if not allowed:
        return True
    if include_image:
        allowed_img, _reason_img = llm_spend.check("image", IMAGE_EST_USD)
        if not allowed_img:
            return True
    return False


def _image_daily_cap_blocks(brand_id: str) -> bool:
    from _lib.image_submit_quota import check_brand_image_submit  # noqa: PLC0415

    allowed, _reason = check_brand_image_submit(brand_id)
    return not allowed


def _waiting_owned_by_poller(item_id: str, row: dict[str, Any]) -> bool:
    from . import image_jobs_state  # noqa: PLC0415

    if str(row.get("status") or "").lower() != "waiting":
        return False
    entry = image_jobs_state.get_entry(item_id)
    if not entry:
        return False
    last = str(entry.get("last_status") or "running").lower()
    return last not in ("failed", "stale")


def _enqueue_actions_for_item(
    rows: list[dict[str, Any]],
    *,
    brand_id: str,
    item_id: str,
    actions: list[str],
) -> int:
    from _lib import ops_agents  # noqa: PLC0415

    added = 0
    item_hash = hashlib.sha1(item_id.encode()).hexdigest()[:12]
    existing = {
        (str(r.get("action") or ""), str(r.get("status") or "").lower())
        for r in _rows_for_item(rows, item_id)
    }
    for action in actions:
        status_key = (action, "pending")
        waiting_key = (action, "waiting")
        if status_key in existing or waiting_key in existing:
            continue
        if action == "draft_photo" and _image_daily_cap_blocks(brand_id):
            continue
        if action == "draft_photo" and any(
            (n, s) in existing for n in _PHOTO_EQUIV for s in ("pending", "waiting")
        ):
            continue
        agent = "cos-image" if action in ("draft_photo", "compose_post") else "cos-caption"
        row = ops_agents.normalise_enqueue(
            {
                "agent": agent,
                "brand": brand_id,
                "reason": _ENQUEUE_REASON,
                "action": action,
                "payload_ref": f"inbox/{item_id}",
                "dedupe_key": f"{action}-{item_hash}",
            }
        )
        row["layer"] = "L5"
        rows.append(row)
        existing.add(status_key)
        added += 1
    return added


def _actions_for_moment(brand_id: str, item_id: str) -> list[str]:
    from _lib.archetypes_v2 import select_archetype  # noqa: PLC0415
    from _lib.jobs.layer5.image_draft_context import primary_channel_for_item  # noqa: PLC0415

    primary = primary_channel_for_item(brand_id, item_id, fallback="instagram")
    if primary == "gbp":
        return ["draft_caption"]
    archetype = select_archetype(brand_id, item_id)
    actions = ["draft_caption"]
    if archetype.get("applies_to", {}).get("needs_photo", True):
        actions.append("draft_photo")
    actions.append("compose_post")
    return actions


def _reset_bad_image_rows(
    rows: list[dict[str, Any]],
    *,
    brand: str | None,
) -> int:
    reset = 0
    for row in rows:
        if str(row.get("action") or "") not in _PHOTO_EQUIV:
            continue
        if brand is not None and str(row.get("brand") or "") != brand:
            continue
        status = str(row.get("status") or "").lower()
        item_id = _parse_inbox_ref(str(row.get("payload_ref") or ""))
        if not item_id:
            continue
        if status == "waiting" and _waiting_owned_by_poller(item_id, row):
            continue
        if status not in ("done", "waiting"):
            continue
        try:
            brand_id = validate_brand_id(row.get("brand"))
        except ValueError:
            continue
        if _moment_has_composed(brand_id, item_id):
            continue
        if _retry_count(row, item_id=item_id) >= MAX_IMAGE_RETRIES:
            continue
        from . import image_jobs_state  # noqa: PLC0415

        row_fallback = row.get(_RETRY_COUNT_KEY)
        image_jobs_state.increment_retry(item_id, row_fallback=row_fallback)
        row.pop(_RETRY_COUNT_KEY, None)
        row["status"] = "pending"
        row.pop("note", None)
        reset += 1
    return reset


def _auto_enqueue_operator_moments(
    rows: list[dict[str, Any]],
    *,
    brand: str | None,
    horizon: set[str],
) -> int:
    from _lib.marketing_calendar import VALID_BRAND_IDS, canonical_records  # noqa: PLC0415

    enqueued = 0
    brands = [brand] if brand else list(VALID_BRAND_IDS)
    for brand_id in brands:
        try:
            brand_id = validate_brand_id(brand_id)
        except ValueError:
            continue
        for record in canonical_records(brand_id):
            if not isinstance(record, dict):
                continue
            if str(record.get("status") or "") != "approved":
                continue
            if str(record.get("source_type") or "") != "operator":
                continue
            if _skip_auto_moment(record):
                continue
            go_live = _record_go_live(record)
            if not go_live or go_live not in horizon:
                continue
            item_id = _calendar_item_id(brand_id, record)
            if not item_id:
                continue
            if _moment_has_composed(brand_id, item_id):
                continue
            actions = _actions_for_moment(brand_id, item_id)
            include_image = "draft_photo" in actions
            if _spend_cap_blocks_enqueue(include_image=include_image):
                continue
            enqueued += _enqueue_actions_for_item(
                rows,
                brand_id=brand_id,
                item_id=item_id,
                actions=actions,
            )
    return enqueued


def run(brand: str | None = None) -> dict[str, Any]:
    """Enqueue missing operator pairs and reset empty image queue rows."""
    if brand is not None:
        try:
            brand = validate_brand_id(brand)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    if _spend_cap_blocks_enqueue(include_image=True):
        return {
            "ok": True,
            "skipped_cap": True,
            "reason": "daily LLM spend cap reached",
            "enqueued": 0,
            "reset_pending": 0,
        }

    rows = _read_queue()
    if not rows and not read_json("agent-queue.json"):
        rows = []

    horizon = _horizon_dates()
    reset = _reset_bad_image_rows(rows, brand=brand)
    enqueued = _auto_enqueue_operator_moments(rows, brand=brand, horizon=horizon)

    if rows:
        _write_queue(rows)
    else:
        atomic_write(
            "agent-queue.json",
            {
                "schema": "campaign-os/agent-queue/v1",
                "generated_at": utc_now_iso(),
                "rows": [],
            },
        )

    return {
        "ok": True,
        "enqueued": enqueued,
        "reset_pending": reset,
        "horizon_days": HORIZON_DAYS,
    }
