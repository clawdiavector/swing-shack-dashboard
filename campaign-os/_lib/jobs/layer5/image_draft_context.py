"""Image draft helpers — prompt from calendar context, browser URL from saved path."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def approved_calendar_records(brand_id: str) -> list[dict[str, Any]]:
    """canonical_records with a dict guard — marketing_calendar may raise on bad lines."""
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    try:
        records = canonical_records(brand_id)
    except Exception:  # noqa: BLE001 — caller decides; never abort the image path
        return []
    return [r for r in records if isinstance(r, dict)]


def build_image_prompt(*, brand_id: str, item_id: str) -> str:
    """Prompt from the approved calendar record; falls back to a generic literal."""
    fallback = f"Social image for approved inbox item {item_id}"
    if not item_id.startswith("calendar_candidate:"):
        return fallback
    key = item_id.split(":", 1)[1]
    if ":" not in key:
        return fallback
    rec_brand, cal_id = key.split(":", 1)
    if rec_brand != brand_id:
        return fallback

    for record in approved_calendar_records(brand_id):
        rid = str(record.get("calendar_id") or record.get("event_key") or "")
        if rid != cal_id:
            continue
        title = str(record.get("title") or record.get("name") or "").strip()
        pillar = str(record.get("pillar_id") or record.get("pillar") or "").strip()
        dates: list[str] = []
        for date_key in (
            "event_date",
            "event_start",
            "event_window_start",
            "campaign_start",
        ):
            raw = record.get(date_key)
            if raw and isinstance(raw, str):
                dates.append(raw[:10])
        parts = [p for p in (title, pillar, ", ".join(sorted(set(dates)))) if p]
        if parts:
            return f"Social image for {brand_id}: {' — '.join(parts)}"
        return fallback
    return fallback


def image_url_for(brand_id: str, saved_path: str | None) -> str | None:
    """/brand-images/<brand>/<basename> — mirrors app.py image generate preview_url."""
    if not saved_path:
        return None
    name = Path(saved_path).name
    if not name:
        return None
    return f"/brand-images/{brand_id}/{name}"
