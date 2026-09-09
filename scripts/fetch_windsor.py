"""
fetch_windsor.py - thin wrapper that calls _lib/windsor_fetcher.build_meta_ads
+ build_google_ads and writes the results to data/meta-ads.json +
data/google-ads.json.

The real work lives in campaign-os/_lib/windsor_fetcher.py so the same code
runs from this CLI script AND from POST /api/admin/windsor-refresh on Railway.

Local invocation:
    WINDSOR_API_KEY=<key> python3 scripts/fetch_windsor.py

Or set the key once via /secrets-sync (service=windsor-api) on Railway and
trigger via:
    curl -X POST https://swing-shack-dashboard-production.up.railway.app/api/admin/windsor-refresh
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone


# Resolve repo root. Falls back to the canonical hardcoded path so the script
# works whether invoked from the repo or from a cron / launchd elsewhere.
REPO_ROOT = os.environ.get(
    "SWING_SHACK_REPO_ROOT",
    "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard",
)
_data_dir_env = os.environ.get("WINDSOR_DATA_DIR", "").strip()
DATA_DIR = _data_dir_env or os.path.join(REPO_ROOT, "data")
META_ADS_OUT = os.path.join(DATA_DIR, "meta-ads.json")
GOOGLE_ADS_OUT = os.path.join(DATA_DIR, "google-ads.json")

# Make the local _lib importable when running as a script
sys.path.insert(0, os.path.join(REPO_ROOT, "campaign-os"))

from _lib import windsor_client as _w  # noqa: E402
from _lib.windsor_fetcher import build_meta_ads, build_google_ads, _atomic_write  # noqa: E402


def main() -> int:
    print("=== fetch_windsor.py ===")
    api_key = _w.read_api_key()
    if not api_key:
        print("WINDSOR_API_KEY not configured.")
        print("Set it via /secrets-sync (service=windsor-api) or as WINDSOR_API_KEY env var.")
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