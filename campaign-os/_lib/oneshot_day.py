"""Operator action: enqueue one-shot image generation for a single calendar day."""

from __future__ import annotations

from typing import Any

from _lib.image_submit_quota import (
    oneshot_max_per_day,
    check_brand_oneshot_submit,
    max_images_per_day,
    oneshot_count_for_brand,
)
from _lib.jobs.layer5.draft_oneshot import OneshotCopyMissing, literal_line_for_card
from _lib.l5_create_enqueue import enqueue_create_actions
from _lib.marketing_calendar import canonical_records, render_mode_for_record
from _lib.ops_layers import brand_images_today


def enqueue_oneshot_day(*, brand_id: str, date: str, editor: str = "operator") -> dict[str, Any]:
    day = str(date)[:10]
    cap_info = brand_images_today(brand_id)
    cap_info = {
        **cap_info,
        "oneshot_today": oneshot_count_for_brand(brand_id),
        "oneshot_cap": oneshot_max_per_day(),
        "at_oneshot_cap": oneshot_count_for_brand(brand_id) >= oneshot_max_per_day(),
    }

    enqueued: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    oneshot_seen = 0
    started_at_oneshot_cap = oneshot_count_for_brand(brand_id) >= oneshot_max_per_day()
    os_ok_pre, _ = check_brand_oneshot_submit(brand_id)

    for record in canonical_records(brand_id):
        if str(record.get("status") or "").lower() not in ("approved", "candidate", "watchlist", ""):
            continue
        start = str(record.get("event_start") or record.get("event_date") or "")[:10]
        if start != day:
            continue
        cal_id = str(record.get("calendar_id") or record.get("event_key") or "")
        if not cal_id:
            continue
        item_id = f"calendar_candidate:{brand_id}:{cal_id}"
        mode = render_mode_for_record(record)
        if mode != "oneshot":
            skipped.append({"calendar_id": cal_id, "reason": "render_mode is template"})
            continue
        try:
            literal_line_for_card(brand_id, item_id, record)
        except OneshotCopyMissing as exc:
            skipped.append({"calendar_id": cal_id, "reason": str(exc)})
            continue
        if not os_ok_pre or oneshot_seen >= oneshot_max_per_day():
            skipped.append(
                {
                    "calendar_id": cal_id,
                    "reason": f"one-shot cap reached for {brand_id} ({cap_info['oneshot_today']}/{oneshot_max_per_day()})",
                }
            )
            continue
        actions = enqueue_create_actions(
            item_id=item_id,
            brand_id=brand_id,
            reason=f"oneshot-day:{editor}",
            phase="image",
        )
        if "draft_oneshot" in actions:
            enqueued.append({"calendar_id": cal_id, "item_id": item_id})
            oneshot_seen += 1
            os_ok_pre, _ = check_brand_oneshot_submit(brand_id)
        else:
            skipped.append({"calendar_id": cal_id, "reason": "not queued (cap or duplicate)"})

    cap_info = {
        **brand_images_today(brand_id),
        "oneshot_today": oneshot_count_for_brand(brand_id),
        "oneshot_cap": oneshot_max_per_day(),
        "at_oneshot_cap": oneshot_count_for_brand(brand_id) >= oneshot_max_per_day(),
        "max_images_per_day": max_images_per_day(),
    }

    if not enqueued and started_at_oneshot_cap:
        status = 429
    else:
        status = 200

    return {
        "ok": status == 200,
        "brand_id": brand_id,
        "date": day,
        "enqueued": enqueued,
        "skipped": skipped,
        "cap": cap_info,
        "http_status": status,
    }
