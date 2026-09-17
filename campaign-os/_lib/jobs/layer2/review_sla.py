"""Count review inbox and calendar candidates breaching the review SLA."""

from __future__ import annotations

import datetime
from typing import Any

from ..errors import describe_exception
from ..layer1._io import atomic_write, utc_now_iso

OUTPUT = "review-sla.json"
SCHEMA = "campaign-os/review-sla/v1"
SLA_HOURS = 24


def _parse_iso(value: str | None) -> datetime.datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _age_hours(value: str | None, *, now: datetime.datetime) -> float | None:
    parsed = _parse_iso(value)
    if parsed is None:
        return None
    return (now - parsed).total_seconds() / 3600.0


def _bucket_item(
    item: dict[str, Any],
    *,
    source: str,
    ts_field: str,
    now: datetime.datetime,
) -> tuple[str, dict[str, Any]]:
    age_h = _age_hours(item.get(ts_field), now=now)
    row = {
        "source": source,
        "id": str(
            item.get("assetId")
            or item.get("calendar_id")
            or item.get("event_key")
            or item.get("title")
            or ""
        ),
        "brand": str(item.get("brand") or item.get("brand_id") or ""),
        "title": str(item.get("name") or item.get("title") or ""),
        "updated_at": item.get(ts_field),
        "age_hours": round(age_h, 2) if age_h is not None else None,
    }
    if age_h is None:
        return "unknown_age", row
    if age_h >= SLA_HOURS:
        return "breached", row
    return "fresh", row


def _calendar_candidates() -> list[dict[str, Any]]:
    from _lib.marketing_calendar import VALID_BRAND_IDS, canonical_records  # noqa: PLC0415

    out: list[dict[str, Any]] = []
    for brand_id in VALID_BRAND_IDS:
        for record in canonical_records(brand_id):
            if record.get("status") != "candidate":
                continue
            enriched = dict(record)
            enriched.setdefault("brand_id", brand_id)
            out.append(enriched)
    return out


def run() -> dict[str, Any]:
    """Write review-sla.json with inbox + calendar SLA breaches."""
    try:
        from _lib import intelligence  # noqa: PLC0415

        now = datetime.datetime.now(datetime.timezone.utc)
        inbox = intelligence.review_inbox()
        pending = inbox.get("pending") or []

        inbox_breached: list[dict[str, Any]] = []
        inbox_unknown: list[dict[str, Any]] = []
        for item in pending:
            if not isinstance(item, dict):
                continue
            bucket, row = _bucket_item(item, source="review_inbox", ts_field="updatedAt", now=now)
            if bucket == "breached":
                inbox_breached.append(row)
            elif bucket == "unknown_age":
                inbox_unknown.append(row)

        candidates = _calendar_candidates()
        calendar_breached: list[dict[str, Any]] = []
        calendar_unknown: list[dict[str, Any]] = []
        for record in candidates:
            ts_field = "last_verified"
            if not record.get(ts_field):
                ts_field = "created_at"
            bucket, row = _bucket_item(record, source="calendar", ts_field=ts_field, now=now)
            if bucket == "breached":
                calendar_breached.append(row)
            elif bucket == "unknown_age":
                calendar_unknown.append(row)

        payload = {
            "schema": SCHEMA,
            "generated_at": utc_now_iso(),
            "sla_hours": SLA_HOURS,
            "summary": {
                "inbox_pending": len(pending),
                "inbox_breached": len(inbox_breached),
                "inbox_unknown_age": len(inbox_unknown),
                "calendar_pending": len(candidates),
                "calendar_breached": len(calendar_breached),
                "calendar_unknown_age": len(calendar_unknown),
                "total_breached": len(inbox_breached) + len(calendar_breached),
            },
            "inbox_breached": inbox_breached,
            "calendar_breached": calendar_breached,
            "unknown_age": inbox_unknown + calendar_unknown,
        }

        atomic_write(OUTPUT, payload)
        return {"ok": True, "rows": payload["summary"]["total_breached"]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": describe_exception(exc)}
