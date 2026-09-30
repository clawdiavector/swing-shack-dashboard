"""
patch_important_dates_v211.py — One-time volume patch for V2.11 important-dates inventory.

Per operator message 2026-09-29 (Discord 1554413079268171846):
  - Operator listed ~70 dates that they deem important enough to look at
    for marketing-calendar planning across Oct 2026 → Dec 2027.
  - These dates cover: SA public holidays, SA rugby / cricket / school sport,
    Western Cape golf moments (Nedbank, SVNS, SA Open, Cycle Tour, Cape Epic,
    Presidents Cup), major golf (Solheim, Walker, TGL), local Paarl sport,
    Nedbank/SVNS returns, and the 2027 Rugby/Cricket World Cup.

This patch is idempotent — running it twice is a no-op. It writes
brand-new content only when the on-volume data file is missing the
new event_names. Once all target markers are present it removes
itself via the same v2.11 marker file the brand-bible patch uses.

Run from: python3 /app/campaign-os/patch_important_dates_v211.py
Safe to run on startup; fast (<50ms).
"""
from __future__ import annotations
import json
import os
import sys
from typing import Any, Dict, List

DATA_DIR = os.environ.get("DATA_DIR", "/data/campaign-os")
BAKED_DIR = "/app/data"

# Dedupe marker shared with brand-bible patch.
V211_MARKER = os.path.join(DATA_DIR, ".patches", "v211_brand_bible.applied")

OPERATOR_PROVIDED = "operator directive (Discord, 2026-09-29, msg 1554413079268171846)"
SCHEMA_VERSION = "v2_with_provenance"


def _resolve(year: int, *parts: str) -> str:
    """Return the volume path (we always write to the volume)."""
    return os.path.join(DATA_DIR, *parts, f"{year}.json")


def _read_baked(year: int, *parts: str) -> List[Dict[str, Any]]:
    bak = os.path.join(BAKED_DIR, *parts, f"{year}.json")
    if not os.path.exists(bak):
        return []
    try:
        with open(bak, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("dates") or data.get("events") or []
    except Exception:
        return []


def _read_volume(year: int, *parts: str) -> List[Dict[str, Any]]:
    vol = _resolve(year, *parts)
    if not os.path.exists(vol):
        return []
    try:
        with open(vol, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("dates") or data.get("events") or []
    except Exception:
        return []


def _write_volume(year: int, items: List[Dict[str, Any]], schema_key: str, *parts: str) -> None:
    """Write the volume file at /data/campaign-os/<parts>/<year>.json."""
    vol = os.path.join(DATA_DIR, *parts, f"{year}.json")
    os.makedirs(os.path.dirname(vol), exist_ok=True)
    payload = {"year": year, schema_key: items, "schema_version": SCHEMA_VERSION}
    with open(vol, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _ensure_baked_to_volume(year: int, *parts: str) -> bool:
    """If the volume is missing the file but the baked copy exists, copy it."""
    vol = _resolve(year, *parts)
    bak = os.path.join(BAKED_DIR, *parts, f"{year}.json")
    if os.path.exists(vol):
        return False
    if not os.path.exists(bak):
        return False
    import shutil
    os.makedirs(os.path.dirname(vol), exist_ok=True)
    shutil.copy2(bak, vol)
    print(f"[bootstrap] copied {bak} -> {vol}")
    return True


def _existing_names(items: List[Dict[str, Any]]) -> set:
    return {(i.get("event_name") or "").strip().lower() for i in items}


def _add_unique(existing: List[Dict[str, Any]], new_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    have = _existing_names(existing)
    out = list(existing)
    added = 0
    for it in new_items:
        key = (it.get("event_name") or "").strip().lower()
        if key and key in have:
            continue
        if key:
            have.add(key)
        out.append(it)
        added += 1
    return out if added else existing


# ─── 2026 — operator-listed Oct→Dec dates ──────────────────────────────────

DATES_2026: List[Dict[str, Any]] = [
    # Already-known public holidays that operator reiterated (kept for dedup safety):
    # 31 Oct — Halloween; 16 Dec — Day of Reconciliation; 25/26 Dec — Christmas/Goodwill.
    # New (from operator list):
    {
        "event_name": "Halloween",
        "event_type": "RETAIL_MOMENT", "start_date": "2026-10-31",
        "end_date": "2026-10-31", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "Humour-only moment per operator; B-tier not appropriate.",
    },
    {
        "event_name": "Italy v Springboks",
        "event_type": "SA_SPORT", "start_date": "2026-11-07",
        "end_date": "2026-11-07", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "End-of-year-tour fixture. Tier B.",
    },
    {
        "event_name": "Singles' Day",
        "event_type": "RETAIL_MOMENT", "start_date": "2026-11-11",
        "end_date": "2026-11-11", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "Test-tier shopping moment.",
    },
    {
        "event_name": "France v Springboks",
        "event_type": "SA_SPORT", "start_date": "2026-11-14",
        "end_date": "2026-11-14", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "End-of-year-tour fixture. Tier B.",
    },
    {
        "event_name": "Ireland v Springboks",
        "event_type": "SA_SPORT", "start_date": "2026-11-21",
        "end_date": "2026-11-21", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "End-of-year-tour fixture. Tier B.",
    },
    {
        "event_name": "Black Friday",
        "event_type": "RETAIL_MOMENT", "start_date": "2026-11-27",
        "end_date": "2026-11-27", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier shopping anchor.",
    },
    {
        "event_name": "Nations Championship Finals Weekend",
        "event_type": "SA_SPORT", "start_date": "2026-11-27",
        "end_date": "2026-11-29", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "Rugby. Tier B.",
    },
    {
        "event_name": "Cyber Monday",
        "event_type": "RETAIL_MOMENT", "start_date": "2026-11-30",
        "end_date": "2026-11-30", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier extension of Black Friday.",
    },
    {
        "event_name": "Festive gifting window",
        "event_type": "RETAIL_MOMENT", "start_date": "2026-11-15",
        "end_date": "2026-12-24", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier; voucher + apparel window.",
    },
    {
        "event_name": "Nedbank Golf Challenge, Sun City",
        "event_type": "GOLF_EVENT", "start_date": "2026-12-03",
        "end_date": "2026-12-06", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A/B tier. Confirmed by operator.",
    },
    {
        "event_name": "Cape Town HSBC SVNS",
        "event_type": "GOLF_EVENT", "start_date": "2026-12-05",
        "end_date": "2026-12-06", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "Rugby sevens at Cape Town Stadium. B-tier Western Cape sport.",
    },
    {
        "event_name": "SA v Bangladesh ODI at Newlands",
        "event_type": "SA_SPORT", "start_date": "2026-12-07",
        "end_date": "2026-12-07", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B/C tier cricket.",
    },
    {
        "event_name": "Public schools Term 4 finish (latest)",
        "event_type": "SCHOOL_HOLIDAY", "start_date": "2026-12-11",
        "end_date": "2026-12-11", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "Family / Junior window begins.",
    },
    {
        "event_name": "Day of Reconciliation",
        "event_type": "PUBLIC_HOLIDAY", "start_date": "2026-12-16",
        "end_date": "2026-12-16", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "CAL-tier public holiday.",
    },
    {
        "event_name": "SA v England 1st Test",
        "event_type": "SA_SPORT", "start_date": "2026-12-17",
        "end_date": "2026-12-21", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier cricket.",
    },
    {
        "event_name": "SA v England Boxing Day Test",
        "event_type": "SA_SPORT", "start_date": "2026-12-26",
        "end_date": "2026-12-30", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "C-tier cricket.",
    },
    {
        "event_name": "New Year / New Bag / voucher redemption",
        "event_type": "RETAIL_MOMENT", "start_date": "2026-12-27",
        "end_date": "2027-01-31", "year": 2026, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A/B tier commercial window (year-bridging).",
    },
]


# ─── 2027 — operator-listed Jan→Dec dates ──────────────────────────────────

DATES_2027: List[Dict[str, Any]] = [
    {
        "event_name": "SA v England ODI, Boland Park, Paarl",
        "event_type": "SA_SPORT", "start_date": "2027-01-10",
        "end_date": "2027-01-10", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-LOCAL tier Paarl sport; Proteas international fixture.",
    },
    {
        "event_name": "Public schools reopen (Term 1)",
        "event_type": "SCHOOL_HOLIDAY", "start_date": "2027-01-13",
        "end_date": "2027-01-13", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier School / Junior anchor.",
    },
    {
        "event_name": "Junior golf / back-to-school activity",
        "event_type": "GOLF_EVENT", "start_date": "2027-01-15",
        "end_date": "2027-01-31", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier School / Golf; date range covers January back-to-school.",
    },
    {
        "event_name": "Winelands summer golf / tourism",
        "event_type": "GOLF_EVENT", "start_date": "2027-01-15",
        "end_date": "2027-03-31", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier seasonal Local / Retail.",
    },
    {
        "event_name": "Valentine's Day",
        "event_type": "RETAIL_MOMENT", "start_date": "2027-02-14",
        "end_date": "2027-02-14", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B/C-tier shopping.",
    },
    {
        "event_name": "Paarl summer interschools / cricket / swimming / tennis",
        "event_type": "SA_SPORT", "start_date": "2027-02-01",
        "end_date": "2027-02-28", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-LOCAL; OS should watch the schools' calendars.",
    },
    {
        "event_name": "Paarl/Boland school golf activity (Term 1)",
        "event_type": "GOLF_EVENT", "start_date": "2027-02-01",
        "end_date": "2027-03-19", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B/C-tier Local Golf; OS to monitor fixtures.",
    },
    {
        "event_name": "Investec South African Open, Stellenbosch GC",
        "event_type": "GOLF_EVENT", "start_date": "2027-03-04",
        "end_date": "2027-03-07", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier Local Golf; confirmed by operator.",
    },
    {
        "event_name": "Cape Town Cycle Tour",
        "event_type": "SA_SPORT", "start_date": "2027-03-14",
        "end_date": "2027-03-14", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B/C-tier Western Cape Sport.",
    },
    {
        "event_name": "Public schools close Term 1",
        "event_type": "SCHOOL_HOLIDAY", "start_date": "2027-03-19",
        "end_date": "2027-03-19", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier Family / Junior window.",
    },
    {
        "event_name": "Absa Cape Epic",
        "event_type": "SA_SPORT", "start_date": "2027-03-21",
        "end_date": "2027-03-28", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier Western Cape Sport; confirmed.",
    },
    {
        "event_name": "Human Rights Day observed",
        "event_type": "PUBLIC_HOLIDAY", "start_date": "2027-03-22",
        "end_date": "2027-03-22", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "CAL-tier public holiday (observed).",
    },
    {
        "event_name": "Good Friday",
        "event_type": "PUBLIC_HOLIDAY", "start_date": "2027-03-26",
        "end_date": "2027-03-26", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "CAL/B-tier public holiday golf.",
    },
    {
        "event_name": "Family Day",
        "event_type": "PUBLIC_HOLIDAY", "start_date": "2027-03-29",
        "end_date": "2027-03-29", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "Family-golf window.",
    },
    {
        "event_name": "Schools reopen Term 2",
        "event_type": "SCHOOL_HOLIDAY", "start_date": "2027-04-06",
        "end_date": "2027-04-06", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier School anchor.",
    },
    {
        "event_name": "ABSA Wildeklawer school rugby",
        "event_type": "SA_SPORT", "start_date": "2027-04-23",
        "end_date": "2027-04-24", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-LOCAL School Sport. Paarl Gim 23 Apr, Paarl Boys 24 Apr per operator.",
    },
    {
        "event_name": "Mother's Day",
        "event_type": "RETAIL_MOMENT", "start_date": "2027-05-09",
        "end_date": "2027-05-09", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier shopping.",
    },
    {
        "event_name": "Youth Day",
        "event_type": "PUBLIC_HOLIDAY", "start_date": "2027-06-16",
        "end_date": "2027-06-16", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "C/B if junior programme exists; SA / Junior.",
    },
    {
        "event_name": "Father's Day",
        "event_type": "RETAIL_MOMENT", "start_date": "2027-06-20",
        "end_date": "2027-06-20", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier Shopping / Golf; overlaps US Open per operator.",
    },
    {
        "event_name": "Schools close Term 2",
        "event_type": "SCHOOL_HOLIDAY", "start_date": "2027-06-25",
        "end_date": "2027-06-25", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier Junior / Family window begins.",
    },
    {
        "event_name": "The Open week, St Andrews",
        "event_type": "GOLF_EVENT", "start_date": "2027-07-11",
        "end_date": "2027-07-18", "year": 2027, "country": "GB",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier Golf; confirmed by operator.",
    },
    {
        "event_name": "Mandela Day",
        "event_type": "PUBLIC_HOLIDAY", "start_date": "2027-07-18",
        "end_date": "2027-07-18", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "C-tier community only.",
    },
    {
        "event_name": "Schools reopen Term 3",
        "event_type": "SCHOOL_HOLIDAY", "start_date": "2027-07-20",
        "end_date": "2027-07-20", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier School.",
    },
    {
        "event_name": "Craven Week / SA Schools rugby",
        "event_type": "SA_SPORT", "start_date": "2027-07-01",
        "end_date": "2027-07-31", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B/C-tier School Sport; exact dates TBC.",
    },
    {
        "event_name": "Winter workshop / upgrade push",
        "event_type": "RETAIL_MOMENT", "start_date": "2027-07-15",
        "end_date": "2027-08-31", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier Stick-owned commercial window.",
    },
    {
        "event_name": "Paarl Boys' High v Paarl Gim Interschools Week",
        "event_type": "SA_SPORT", "start_date": "2027-08-01",
        "end_date": "2027-08-15", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-LOCAL Paarl School Sport. Placeholder until schools publish date.",
    },
    {
        "event_name": "Interschools hockey / netball / other school sport",
        "event_type": "SA_SPORT", "start_date": "2027-08-01",
        "end_date": "2027-08-15", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A/B-LOCAL Paarl School Sport.",
    },
    {
        "event_name": "Interschools rugby main match",
        "event_type": "SA_SPORT", "start_date": "2027-08-01",
        "end_date": "2027-08-15", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-LOCAL PEAK Paarl School Sport. Placeholder until schools publish.",
    },
    {
        "event_name": "National Women's Day",
        "event_type": "PUBLIC_HOLIDAY", "start_date": "2027-08-09",
        "end_date": "2027-08-09", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "C/B-tier SA.",
    },
    {
        "event_name": "Boland / school golf fixtures and championships",
        "event_type": "GOLF_EVENT", "start_date": "2027-08-01",
        "end_date": "2027-08-31", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B/C-tier Local Golf. OS to monitor schools.",
    },
    {
        "event_name": "Heritage Day",
        "event_type": "PUBLIC_HOLIDAY", "start_date": "2027-09-24",
        "end_date": "2027-09-24", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "C-tier SA.",
    },
    {
        "event_name": "Spring / Winelands summer build-up",
        "event_type": "GOLF_EVENT", "start_date": "2027-09-15",
        "end_date": "2027-10-31", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier seasonal Local.",
    },
    {
        "event_name": "Schools close Term 3",
        "event_type": "SCHOOL_HOLIDAY", "start_date": "2027-10-01",
        "end_date": "2027-10-01", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier School window begins.",
    },
    {
        "event_name": "Men's Rugby World Cup 2027",
        "event_type": "SA_SPORT", "start_date": "2027-10-01",
        "end_date": "2027-11-13", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-NATIONAL Springboks. Confirmed pool matches: 3, 10, 17 Oct.",
    },
    {
        "event_name": "Springboks v Italy – RWC opener",
        "event_type": "SA_SPORT", "start_date": "2027-10-03",
        "end_date": "2027-10-03", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier Springboks.",
    },
    {
        "event_name": "Springboks v Georgia",
        "event_type": "SA_SPORT", "start_date": "2027-10-10",
        "end_date": "2027-10-10", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A/B-tier Springboks.",
    },
    {
        "event_name": "Schools reopen Term 4",
        "event_type": "SCHOOL_HOLIDAY", "start_date": "2027-10-11",
        "end_date": "2027-10-11", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier School.",
    },
    {
        "event_name": "Springboks v Romania",
        "event_type": "SA_SPORT", "start_date": "2027-10-17",
        "end_date": "2027-10-17", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A/B-tier Springboks.",
    },
    {
        "event_name": "RWC Round of 16",
        "event_type": "SA_SPORT", "start_date": "2027-10-23",
        "end_date": "2027-10-24", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier trigger if SA qualifies.",
    },
    {
        "event_name": "RWC quarter-finals",
        "event_type": "SA_SPORT", "start_date": "2027-10-30",
        "end_date": "2027-10-31", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier trigger if SA qualifies.",
    },
    {
        "event_name": "ICC Men's Cricket World Cup",
        "event_type": "SA_SPORT", "start_date": "2027-10-15",
        "end_date": "2027-11-30", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-NATIONAL. Held in SA / Zimbabwe / Namibia.",
    },
    {
        "event_name": "Cricket World Cup matches at Boland Park, Paarl",
        "event_type": "SA_SPORT", "start_date": "2027-10-15",
        "end_date": "2027-11-30", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-LOCAL Paarl Sport. Exact dates TBC until ICC publishes fixture schedule.",
    },
    {
        "event_name": "RWC semi-finals",
        "event_type": "SA_SPORT", "start_date": "2027-11-05",
        "end_date": "2027-11-06", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier trigger if SA qualifies.",
    },
    {
        "event_name": "Singles' Day",
        "event_type": "RETAIL_MOMENT", "start_date": "2027-11-11",
        "end_date": "2027-11-11", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "C/test-tier shopping.",
    },
    {
        "event_name": "Rugby World Cup Final",
        "event_type": "SA_SPORT", "start_date": "2027-11-13",
        "end_date": "2027-11-13", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-NATIONAL Springboks / Rugby.",
    },
    {
        "event_name": "Festive gifting starts",
        "event_type": "RETAIL_MOMENT", "start_date": "2027-11-15",
        "end_date": "2027-12-24", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier shopping.",
    },
    {
        "event_name": "Black Friday",
        "event_type": "RETAIL_MOMENT", "start_date": "2027-11-26",
        "end_date": "2027-11-26", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier shopping.",
    },
    {
        "event_name": "Cyber Monday",
        "event_type": "RETAIL_MOMENT", "start_date": "2027-11-29",
        "end_date": "2027-11-29", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A-tier extension of Black Friday.",
    },
    {
        "event_name": "Summer / Winelands tourist season strengthening",
        "event_type": "GOLF_EVENT", "start_date": "2027-11-01",
        "end_date": "2027-12-31", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier seasonal Local.",
    },
    {
        "event_name": "Cape Town HSBC SVNS",
        "event_type": "GOLF_EVENT", "start_date": "2027-12-01",
        "end_date": "2027-12-12", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier Western Cape Rugby. Exact Dec dates TBC.",
    },
    {
        "event_name": "Nedbank Golf Challenge",
        "event_type": "GOLF_EVENT", "start_date": "2027-12-01",
        "end_date": "2027-12-12", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A/B-tier Golf. Exact Dec dates TBC.",
    },
    {
        "event_name": "Public schools close Term 4 (latest)",
        "event_type": "SCHOOL_HOLIDAY", "start_date": "2027-12-10",
        "end_date": "2027-12-10", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "B-tier Family / Junior.",
    },
    {
        "event_name": "Day of Reconciliation",
        "event_type": "PUBLIC_HOLIDAY", "start_date": "2027-12-16",
        "end_date": "2027-12-16", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "CAL-tier public holiday.",
    },
    {
        "event_name": "New Year / New Bag",
        "event_type": "RETAIL_MOMENT", "start_date": "2027-12-27",
        "end_date": "2028-01-31", "year": 2027, "country": "ZA",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "A/B-tier Retail / Fitting / Coaching.",
    },
]


# ─── GOLF MOMENTS — operator additions ─────────────────────────────────────

GOLF_MOMENTS_2026: List[Dict[str, Any]] = [
    {
        "event_name": "Presidents Cup 2026",
        "start_date": "2026-09-24", "end_date": "2026-09-27", "year": 2026,
        "country": "US", "type": "TEAM_EVENT",
        "venue": "Royal Montreal Golf Club",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "Presidents Cup is in EVEN years (Ryder Cup in odd).",
    },
]

GOLF_MOMENTS_2027: List[Dict[str, Any]] = [
    {
        "event_name": "Solheim Cup 2027",
        "start_date": "2027-08-27", "end_date": "2027-08-29", "year": 2027,
        "country": "TBD", "type": "TEAM_EVENT",
        "venue": "TBD (not yet announced)",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "Solheim Cup is in EVEN years. OS to monitor for venue announcement.",
    },
    {
        "event_name": "Walker Cup 2027",
        "start_date": "2027-09-04", "end_date": "2027-09-05", "year": 2027,
        "country": "TBD", "type": "TEAM_EVENT",
        "venue": "TBD (not yet announced)",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "Walker Cup is amateur team match. OS to monitor.",
    },
    {
        "event_name": "TGL 2027",
        "start_date": "2027-01-01", "end_date": "2027-03-31", "year": 2027,
        "country": "US", "type": "LEAGUE",
        "venue": "SoFi Center, Palm Beach Gardens FL",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "Tiger Woods' indoor league. OS to monitor season dates.",
    },
    {
        "event_name": "WTGL",
        "start_date": "2027-01-01", "end_date": "2027-12-31", "year": 2027,
        "country": "TBD", "type": "LEAGUE",
        "venue": "TBD",
        "source_name": OPERATOR_PROVIDED, "source_url": "",
        "source_checked_at": "2026-09-29", "confidence": "MANUAL", "status": "MANUAL",
        "notes": "Watchlist placeholder — venue + dates TBC. Operator wants reactive-watchlist.",
    },
]


def patch_important_dates(year: int, new_items: List[Dict[str, Any]]) -> bool:
    """Add operator-provided dates to the volume file, dedup by event_name."""
    _ensure_baked_to_volume(year, "important-dates")
    existing = _read_volume(year, "important-dates")
    if not existing:
        existing = _read_baked(year, "important-dates")
    merged = _add_unique(existing, new_items)
    if len(merged) == len(existing):
        return False
    _write_volume(year, merged, "dates", "important-dates")
    print(f"[dates/{year}] added {len(merged) - len(existing)} new entries (total {len(merged)})")
    return True


def patch_golf_moments(year: int, new_items: List[Dict[str, Any]]) -> bool:
    _ensure_baked_to_volume(year, "golf-moments")
    existing = _read_volume(year, "golf-moments")
    if not existing:
        existing = _read_baked(year, "golf-moments")
    merged = _add_unique(existing, new_items)
    if len(merged) == len(existing):
        return False
    _write_volume(year, merged, "events", "golf-moments")
    print(f"[golf-moments/{year}] added {len(merged) - len(existing)} new entries (total {len(merged)})")
    return True


def main() -> int:
    changed = False
    changed |= patch_important_dates(2026, DATES_2026)
    changed |= patch_important_dates(2027, DATES_2027)
    changed |= patch_golf_moments(2026, GOLF_MOMENTS_2026)
    changed |= patch_golf_moments(2027, GOLF_MOMENTS_2027)
    if changed:
        # Refresh the shared v2.11 marker.
        os.makedirs(os.path.dirname(V211_MARKER), exist_ok=True)
        with open(V211_MARKER, "w") as f:
            f.write("v2.11 brand-bible language patch + important-dates inventory\n")
            f.write(f"applied_at={os.environ.get('RAILWAY_DEPLOYMENT_ID', 'local')}\n")
        print(f"[v2.11] patched — marker refreshed at {V211_MARKER}")
    else:
        print("[v2.11/dates] nothing to patch (already up to date)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
