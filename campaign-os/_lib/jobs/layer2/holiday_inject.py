"""Deterministic SA public holiday inject into marketing calendar records."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from ..errors import describe_exception

TZ_SAST = ZoneInfo("Africa/Johannesburg")

# Fixed civil dates — re-declared locally (not imported from UI helpers).
_FIXED_SA_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "New Year's Day"),
    (3, 21, "Human Rights Day"),
    (4, 27, "Freedom Day"),
    (5, 1, "Workers' Day"),
    (6, 16, "Youth Day"),
    (8, 9, "National Women's Day"),
    (9, 24, "Heritage Day"),
    (12, 16, "Day of Reconciliation"),
    (12, 25, "Christmas Day"),
    (12, 26, "Day of Goodwill"),
)

_BRAND_RETAIL_PILLAR: dict[str, str] = {
    "stick": "stick-retail",
    "bag-drop": "bags-retail",
    "swing-shack": "ss-membership",
}


@dataclass(frozen=True)
class HolidayOccurrence:
    """One injectable public-holiday occurrence."""

    title: str
    observed: dt.date
    statutory: dt.date | None = None


def _easter_sunday(year: int) -> dt.date:
    """Anonymous Gregorian algorithm — stdlib only."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def _observed_public_holiday(statutory: dt.date) -> HolidayOccurrence:
    """Apply SA Public Holidays Act Sunday→Monday observed rule."""
    if statutory.weekday() == 6:
        return HolidayOccurrence(
            title="",
            observed=statutory + dt.timedelta(days=1),
            statutory=statutory,
        )
    return HolidayOccurrence(title="", observed=statutory, statutory=None)


def _fixed_holidays_for_year(year: int) -> list[HolidayOccurrence]:
    out: list[HolidayOccurrence] = []
    for month, day, title in _FIXED_SA_HOLIDAYS:
        statutory = dt.date(year, month, day)
        occ = _observed_public_holiday(statutory)
        out.append(
            HolidayOccurrence(
                title=title,
                observed=occ.observed,
                statutory=occ.statutory,
            )
        )
    easter = _easter_sunday(year)
    good_friday = easter - dt.timedelta(days=2)
    family_day = easter + dt.timedelta(days=1)
    out.append(HolidayOccurrence(title="Good Friday", observed=good_friday))
    out.append(HolidayOccurrence(title="Family Day", observed=family_day))
    return out


def horizon_years(*, today: dt.date | None = None) -> tuple[int, ...]:
    """Current calendar year and next — rolling horizon."""
    ref = today or dt.datetime.now(TZ_SAST).date()
    return (ref.year, ref.year + 1)


def sa_public_holidays_for_years(years: tuple[int, ...]) -> list[HolidayOccurrence]:
    """All SA public holidays for the given years."""
    rows: list[HolidayOccurrence] = []
    for year in years:
        rows.extend(_fixed_holidays_for_year(year))
    return rows


def _holiday_pillar_id(brand_id: str, cfg: dict[str, Any]) -> str | None:
    pillars = cfg.get("pillars") or []
    preferred = _BRAND_RETAIL_PILLAR.get(brand_id)
    pillar_ids = [p.get("pillar_id") for p in pillars if p.get("pillar_id")]
    if preferred and preferred in pillar_ids:
        return preferred
    for pid in pillar_ids:
        if "retail" in pid.lower():
            return pid
    return pillar_ids[0] if pillar_ids else None


def _build_record(
    *,
    brand_id: str,
    holiday: HolidayOccurrence,
    pillar_id: str,
) -> dict[str, Any]:
    observed_iso = holiday.observed.isoformat()
    year = holiday.observed.year
    record: dict[str, Any] = {
        "type": "moment",
        "title": holiday.title,
        "calendar_year": year,
        "event_date": observed_iso,
        "event_start": observed_iso,
        "event_end": observed_iso,
        "source_origin": "deterministic_calendar",
        "date_confidence": "confirmed_date",
        "event_lifecycle": "upcoming",
        "status": "candidate",
        "pillars": [pillar_id],
        "source_urls": [],
        "source_type": "holiday",
        "created_by": "holiday_inject",
        "brand_id": brand_id,
    }
    if holiday.statutory is not None:
        record["statutory_date"] = holiday.statutory.isoformat()
    return record


def run(*, today: dt.date | None = None) -> dict[str, Any]:
    """Inject SA public holidays for all configured operating brands."""
    try:
        from _lib.marketing_calendar import (  # noqa: PLC0415
            VALID_BRAND_IDS,
            load_brand_config,
            upsert_event,
        )

        years = horizon_years(today=today)
        holidays = sa_public_holidays_for_years(years)
        created = 0
        noop = 0
        updated = 0
        brands_processed: list[str] = []

        for brand_id in VALID_BRAND_IDS:
            cfg = load_brand_config(brand_id)
            if not cfg.get("configured"):
                continue
            pillar_id = _holiday_pillar_id(brand_id, cfg)
            if not pillar_id:
                continue
            brands_processed.append(brand_id)
            for holiday in holidays:
                record = _build_record(
                    brand_id=brand_id,
                    holiday=holiday,
                    pillar_id=pillar_id,
                )
                result = upsert_event(brand_id, record)
                action = result.get("action")
                if action == "created":
                    created += 1
                elif action == "noop":
                    noop += 1
                elif action == "updated":
                    updated += 1

        return {
            "ok": True,
            "created": created,
            "noop": noop,
            "updated": updated,
            "brands": brands_processed,
            "years": list(years),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": describe_exception(exc)}
