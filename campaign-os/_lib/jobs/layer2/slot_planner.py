"""Plan empty calendar slots for configured brands (next 14 days)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..errors import describe_exception
from ..layer1._io import atomic_write, utc_now_iso

OUTPUT = "slot-planner.json"
HORIZON_DAYS = 14
SCHEMA = "campaign-os/slot-planner/v1"


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _horizon_dates(*, start: date | None = None, days: int = HORIZON_DAYS) -> list[str]:
    base = start or _today_utc()
    return [(base + timedelta(days=offset)).isoformat() for offset in range(days)]


def _record_dates(record: dict[str, Any]) -> set[str]:
    dates: set[str] = set()
    for key in (
        "event_date",
        "event_start",
        "event_window_start",
        "campaign_start",
        "campaign_end",
        "event_window_end",
    ):
        raw = record.get(key)
        if not raw or not isinstance(raw, str):
            continue
        dates.add(raw[:10])
    return dates


def _record_covers_pillar(record: dict[str, Any], pillar_id: str) -> bool:
    rec_pillar = record.get("pillar_id") or record.get("pillar")
    if not rec_pillar:
        return True
    return str(rec_pillar) == pillar_id


def _occupied_days(
    records: list[dict[str, Any]],
    *,
    pillar_id: str,
    horizon: set[str],
) -> set[str]:
    occupied: set[str] = set()
    for record in records:
        if record.get("status") == "watchlist":
            continue
        if not _record_covers_pillar(record, pillar_id):
            continue
        for day in _record_dates(record):
            if day in horizon:
                occupied.add(day)
    return occupied


def _planning_pillars(pillars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [p for p in pillars if p.get("always_active")]
    return active or list(pillars)


def run() -> dict[str, Any]:
    """Write slot-planner.json with empty pillar slots for the next 14 days."""
    try:
        from _lib.marketing_calendar import (  # noqa: PLC0415 — lazy import
            VALID_BRAND_IDS,
            load_brand_config,
            canonical_records,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"calendar module unavailable: {describe_exception(exc)}"}

    horizon = _horizon_dates()
    horizon_set = set(horizon)
    empty_slots: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for brand_id in VALID_BRAND_IDS:
        try:
            cfg = load_brand_config(brand_id)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{brand_id} config load failed: {describe_exception(exc)}"}

        pillars = cfg.get("pillars") or []
        if not cfg.get("configured") or not pillars:
            skipped.append({"brand": brand_id, "reason": "no calendar_config"})
            continue

        try:
            records = [
                r
                for r in canonical_records(brand_id)
                if r.get("status") != "watchlist"
            ]
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{brand_id} records failed: {describe_exception(exc)}"}

        for pillar in _planning_pillars(pillars):
            pillar_id = pillar.get("pillar_id") or pillar.get("name") or "unknown"
            pillar_name = pillar.get("name") or pillar_id
            occupied = _occupied_days(records, pillar_id=str(pillar_id), horizon=horizon_set)
            for day in horizon:
                if day not in occupied:
                    empty_slots.append(
                        {
                            "brand": brand_id,
                            "date": day,
                            "pillar_id": pillar_id,
                            "pillar_name": pillar_name,
                        }
                    )

    empty_slots.sort(key=lambda row: (row["brand"], row["date"], row["pillar_id"]))

    payload = {
        "schema": SCHEMA,
        "generated_at": utc_now_iso(),
        "horizon_days": HORIZON_DAYS,
        "empty_slots": empty_slots,
        "skipped": skipped,
        "summary": {
            "empty_slot_count": len(empty_slots),
            "brands_planned": len(VALID_BRAND_IDS) - len(skipped),
            "brands_skipped": len(skipped),
        },
    }
    atomic_write(OUTPUT, payload)
    return {"ok": True, "rows": len(empty_slots)}
