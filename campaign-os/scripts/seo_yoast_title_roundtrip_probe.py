#!/usr/bin/env python3
"""Dry-run proof that Yoast title writes round-trip; optional live read-only check.

Default (no flags): in-memory Fake WordPress — safe for CI and local runs.

  python3 campaign-os/scripts/seo_yoast_title_roundtrip_probe.py

Live read-only (OPTIONS schema + current title; no write):

  python3 campaign-os/scripts/seo_yoast_title_roundtrip_probe.py --live-check --brand swing-shack

Do not use this script to write on production. Supervised live proof steps:
docs/seo/yoast-title-live-proof.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from _lib import seo_meta_publish as smp  # noqa: E402
from test_seo_fixer import FakeWP, GOOD_TITLE  # noqa: E402

MEMBERSHIP_ID = 2255
BEFORE = "Membership - Swing Shack"


def dry_run() -> dict:
    wp = FakeWP(behaviour="accept")
    result = smp.write_field(wp, MEMBERSHIP_ID, "title", GOOD_TITLE, BEFORE)
    return {
        "mode": "dry-run",
        "ok": bool(result.get("ok") and result.get("verified")),
        "write": result,
        "stored_meta": wp.pages[MEMBERSHIP_ID]["title"],
    }


def live_check(brand: str) -> dict:
    wp = smp.default_wp(brand)
    writable = smp.page_field_writable(wp, "title")
    page = smp.fetch_page(wp, smp.PAGE_SLUGS["Membership"])
    before = smp.current_value(page, "title") if page else None
    return {
        "mode": "live-check",
        "ok": writable is True,
        "brand": brand,
        "page_field_writable_title": writable,
        "membership_title_before": before,
        "note": "read-only; no write performed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-check", action="store_true", help="OPTIONS + read current title (no write)")
    parser.add_argument("--brand", default="swing-shack", help="Brand for --live-check (default swing-shack)")
    args = parser.parse_args()
    if args.live_check:
        out = live_check(args.brand.strip())
    else:
        out = dry_run()
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
