"""
fetch_windsor.py - pull live Meta Ads + Google Ads data from Windsor.ai and
write data/meta-ads.json + data/google-ads.json.

REPLACES the synthesised data these files used to hold. Synthesised files
were marked in their own _meta.note as "Replace with live API for true
paid-campaign data." This is that replacement.

The CMO brain uses these files to:
  - stop warning "Paid reach is invisible" when live data is present
  - show real spend, impressions, clicks, reach, ROAS in the weekly report
  - power the paid-vs-organic attribution analysis

The fetcher is read-only. It never sends write actions to Windsor.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from collections import defaultdict

REPO_ROOT = os.environ.get(
    "SWING_SHACK_REPO_ROOT",
    "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard",
)
# When run from the dashboard endpoint on Railway, DATA_DIR is /data/
_data_dir_env = os.environ.get("WINDSOR_DATA_DIR", "").strip()
DATA_DIR = _data_dir_env or os.path.join(REPO_ROOT, "data")
META_ADS_OUT = os.path.join(DATA_DIR, "meta-ads.json")
GOOGLE_ADS_OUT = os.path.join(DATA_DIR, "google-ads.json")

# Make the local _lib importable when running as a script
sys.path.insert(0, os.path.join(REPO_ROOT, "campaign-os"))

from _lib import windsor_client as _w  # noqa: E402


# ----- row normalisation ------------------------------------------------------

def _safe_num(v, default=0):
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_str(v, default=""):
    if v is None:
        return default
    return str(v).strip()


def _detect_currency(rows: list[dict]) -> str:
    """Pick the most common currency in the rows. Windsor returns currency per-row."""
    counts = defaultdict(int)
    for r in rows:
        c = _safe_str(r.get("currency"))
        if c:
            counts[c.upper()] += 1
    if not counts:
        return "USD"  # Windsor default
    return max(counts.items(), key=lambda x: x[1])[0]


def _iso_date(v) -> str:
    """Normalise Windsor's date variants to YYYY-MM-DD. Accepts YYYYMMDD or YYYY-MM-DD."""
    s = _safe_str(v)
    if not s:
        return ""
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s[:10]


def _normalise_meta_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "id": _safe_str(r.get("campaign_id") or r.get("ad_id") or r.get("adset_id")),
            "name": _safe_str(r.get("campaign") or r.get("adset") or r.get("ad")),
            "date": _iso_date(r.get("date")),
            "start_date": _iso_date(r.get("date")),
            "end_date": _iso_date(r.get("date")),
            "spend": _safe_num(r.get("spend")),
            "currency": _safe_str(r.get("currency"), default="USD").upper(),
            "clicks": _safe_num(r.get("clicks") or r.get("clicks_all")),
            "impressions": _safe_num(r.get("impressions")),
            "reach": _safe_num(r.get("reach")),
            "frequency": _safe_num(r.get("frequency")),
            "source": "windsor-facebook",
            "note": "Live data via Windsor.ai facebook connector",
        })
    return out


def _normalise_google_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "id": _safe_str(r.get("campaign_id") or r.get("adgroup_id")),
            "name": _safe_str(r.get("campaign") or r.get("adgroup")),
            "date": _iso_date(r.get("date")),
            "start_date": _iso_date(r.get("date")),
            "end_date": _iso_date(r.get("date")),
            "spend": _safe_num(r.get("spend")),
            "currency": _safe_str(r.get("currency"), default="USD").upper(),
            "clicks": _safe_num(r.get("clicks")),
            "impressions": _safe_num(r.get("impressions")),
            "conversions": _safe_num(r.get("conversions")),
            "cost_per_conversion": _safe_num(r.get("cost_per_conversion")),
            "source": "windsor-google-ads",
            "note": "Live data via Windsor.ai google_ads connector",
        })
    return out


# ----- aggregation helpers ----------------------------------------------------

def _aggregate(rows: list[dict]) -> dict:
    """Sum spend, impressions, clicks, reach across rows. Derive ctr/cpc."""
    spend = sum(r.get("spend", 0) for r in rows)
    imps = sum(r.get("impressions", 0) for r in rows)
    clicks = sum(r.get("clicks", 0) for r in rows)
    reach = sum(r.get("reach", 0) for r in rows)
    conv = sum(r.get("conversions", 0) for r in rows)
    cpc = (spend / clicks) if clicks > 0 else 0.0
    ctr_pct = (clicks / imps * 100) if imps > 0 else 0.0
    cpa = (spend / conv) if conv > 0 else 0.0
    return {
        "spend": round(spend, 2),
        "impressions": int(imps),
        "clicks": int(clicks),
        "reach": int(reach),
        "conversions": int(conv),
        "ctr_pct": round(ctr_pct, 2),
        "cpc": round(cpc, 2),
        "cost_per_conversion": round(cpa, 2),
    }


def _window_subset(rows: list[dict], days_back: int) -> list[dict]:
    """Filter rows to the last ``days_back`` days from today (UTC)."""
    today = datetime.now(timezone.utc).date()
    cutoff = today.toordinal() - days_back
    out = []
    for r in rows:
        d = _safe_str(r.get("date") or r.get("start_date"))
        if not d:
            continue
        try:
            dt = datetime.strptime(d[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if dt.toordinal() > cutoff:
            out.append(r)
    return out


# ----- main builders ----------------------------------------------------------

def build_meta_ads(api_key: str) -> dict:
    date_from, date_to = _w.month_window(days_back=30)
    rows, meta = _w.fetch_connector(
        "facebook",
        api_key=api_key,
        fields=_w.FACEBOOK_FIELDS,
        date_from=date_from,
        date_to=date_to,
    )

    # Distinguish failure modes - caller decides what to do with this
    if not meta.get("ok"):
        return {
            "_meta": {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "windsor-facebook",
                "note": f"Windsor fetch failed: {meta.get('error', 'unknown')}",
                "campaigns_count": 0,
                "live": False,
            },
            "campaigns": [],
            "totals": _aggregate([]),
            "live": False,
            "error": meta.get("error"),
        }

    norm = _normalise_meta_rows(rows)
    currency = _detect_currency(rows) or "USD"
    totals = _aggregate(norm)
    totals["currency"] = currency
    week_subset = _window_subset(norm, days_back=7)
    week = _aggregate(week_subset)
    week["currency"] = currency

    return {
        "_meta": {
            "fetched_at": meta.get("fetched_at"),
            "source": "windsor-facebook",
            "note": "Live Meta Ads data via Windsor.ai connector (campaign-level fields).",
            "campaigns_count": len(norm),
            "fields_returned": _w.FACEBOOK_FIELDS,
            "date_from": date_from,
            "date_to": date_to,
            "currency": currency,
            "live": True,
        },
        "campaigns": norm,
        "totals": totals,
        "week": week,
        "live": True,
    }


def build_google_ads(api_key: str) -> dict:
    date_from, date_to = _w.month_window(days_back=30)
    rows, meta = _w.fetch_connector(
        "google_ads",
        api_key=api_key,
        fields=_w.GOOGLE_ADS_FIELDS,
        date_from=date_from,
        date_to=date_to,
    )

    if not meta.get("ok"):
        return {
            "_meta": {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "windsor-google-ads",
                "note": f"Windsor fetch failed: {meta.get('error', 'unknown')}",
                "campaigns_count": 0,
                "live": False,
            },
            "campaigns": [],
            # Dashboard reads these top-level keys (spend, impressions, ...)
            "spend": 0, "impressions": 0, "clicks": 0, "conversions": 0,
            "local_actions": 0, "calls": 0, "ctr": 0.0, "cpc": 0.0,
            "live": False,
            "error": meta.get("error"),
        }

    norm = _normalise_google_rows(rows)
    currency = _detect_currency(rows) or "USD"
    totals = _aggregate(norm)
    totals["currency"] = currency
    week_subset = _window_subset(norm, days_back=7)
    week = _aggregate(week_subset)
    week["currency"] = currency

    return {
        "_meta": {
            "fetched_at": meta.get("fetched_at"),
            "source": "windsor-google-ads",
            "note": "Live Google Ads data via Windsor.ai connector (campaign-level fields).",
            "campaigns_count": len(norm),
            "fields_returned": _w.GOOGLE_ADS_FIELDS,
            "date_from": date_from,
            "date_to": date_to,
            "currency": currency,
            "live": True,
        },
        "campaigns": norm,
        "totals": totals,
        "week": week,
        # Top-level keys for the weekly report dashboard cards
        # (matches the shape the brain expects per app.py:11444)
        "spend": week["spend"],
        "impressions": week["impressions"],
        "clicks": week["clicks"],
        "conversions": week["conversions"],
        "local_actions": 0,  # Windsor google_ads doesn't expose local_actions; keep shape
        "calls": 0,
        "ctr": week["ctr_pct"],
        "cpc": week["cpc"],
        "live": True,
    }


# ----- atomic write -----------------------------------------------------------

def _atomic_write(path: str, payload: dict) -> None:
    """Write JSON atomically: write to tmp, fsync, rename. mode 0600."""
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


# ----- entry point ------------------------------------------------------------

def main() -> int:
    print("=== fetch_windsor.py ===")
    api_key = _w.read_api_key()
    if not api_key:
        print("WINDSOR_API_KEY not configured.")
        print("Set it via /secrets-sync (service=windsor) or as WINDSOR_API_KEY env var.")
        # Don't write failure files - leave the existing synthesised files in place
        # so the brain keeps showing "Paid reach is invisible" (truthful).
        return 1

    print(f"API key loaded (length={len(api_key)})")

    # Meta Ads
    print("\n[1/2] Fetching Meta Ads via Windsor facebook connector...")
    meta_payload = build_meta_ads(api_key)
    if meta_payload.get("live"):
        m = meta_payload["_meta"]
        t = meta_payload["totals"]
        w = meta_payload["week"]
        print(f"  {m['campaigns_count']} rows | {m['currency']}")
        print(f"  30d totals: spend={t['spend']} impressions={t['impressions']:,} "
              f"clicks={t['clicks']:,} reach={t['reach']:,}")
        print(f"  7d  totals: spend={w['spend']} impressions={w['impressions']:,} "
              f"clicks={w['clicks']:,} reach={w['reach']:,}")
    else:
        print(f"  FAILED: {meta_payload.get('error')}")
    _atomic_write(META_ADS_OUT, meta_payload)
    print(f"  wrote: {META_ADS_OUT}")

    # Google Ads
    print("\n[2/2] Fetching Google Ads via Windsor google_ads connector...")
    ga_payload = build_google_ads(api_key)
    if ga_payload.get("live"):
        m = ga_payload["_meta"]
        t = ga_payload["totals"]
        w = ga_payload["week"]
        print(f"  {m['campaigns_count']} rows | {m['currency']}")
        print(f"  30d totals: spend={t['spend']} impressions={t['impressions']:,} "
              f"clicks={t['clicks']:,} conversions={t['conversions']:,}")
        print(f"  7d  totals: spend={w['spend']} impressions={w['impressions']:,} "
              f"clicks={w['clicks']:,} conversions={w['conversions']:,}")
    else:
        print(f"  FAILED: {ga_payload.get('error')}")
    _atomic_write(GOOGLE_ADS_OUT, ga_payload)
    print(f"  wrote: {GOOGLE_ADS_OUT}")

    # Verdict
    print("\n=== Verdict ===")
    if meta_payload.get("live") or ga_payload.get("live"):
        print("Live paid-media data is now in data/. The brain will stop warning")
        print("'Paid reach is invisible' on the next weekly-report render.")
        return 0
    else:
        print("Both connectors failed. Synthesised files preserved (truthful: brain")
        print("will keep warning 'Paid reach is invisible').")
        return 2


if __name__ == "__main__":
    sys.exit(main())