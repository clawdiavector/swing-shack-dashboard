#!/usr/bin/env python3
"""Read-only report of visual gaps across calendar moments."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def main() -> int:
    parser = argparse.ArgumentParser(description="List computed visual gaps (read-only).")
    parser.add_argument("--brand", action="append", dest="brands", help="Limit to brand id (repeatable)")
    parser.add_argument("--days", type=int, default=14, help="Horizon days from today (SAST)")
    args = parser.parse_args()

    from _lib.marketing_calendar import VALID_BRAND_IDS, canonical_records  # noqa: PLC0415
    from _lib.visual_gate import decide  # noqa: PLC0415
    from _lib.jobs.layer5.retry_failed_images import _horizon_dates, _record_go_live  # noqa: PLC0415

    brands = args.brands or list(VALID_BRAND_IDS)
    horizon = _horizon_dates(days=max(1, args.days))
    rows: list[tuple[str, str, str, str, str, str]] = []

    for brand_id in brands:
        if brand_id not in VALID_BRAND_IDS:
            continue
        for record in canonical_records(brand_id):
            if not isinstance(record, dict):
                continue
            go = _record_go_live(record)
            if not go or go not in horizon:
                continue
            cal_id = str(record.get("calendar_id") or record.get("event_key") or "")
            if not cal_id:
                continue
            item_id = f"calendar_candidate:{brand_id}:{cal_id}"
            decision = decide(brand_id, item_id, record=record)
            if not decision.is_gap():
                continue
            asset_id = ""
            from _lib.jobs.layer5.draft_assets import _find_caption_draft_for_item  # noqa: PLC0415

            aid, _ = _find_caption_draft_for_item(item_id)
            asset_id = aid or ""
            rows.append(
                (
                    brand_id,
                    go,
                    decision.post_type,
                    decision.reason,
                    asset_id,
                    cal_id,
                )
            )

    print("brand\tdate\tpost_type\treason\tasset_id\tcalendar_id")
    for row in sorted(rows):
        print("\t".join(row))
    print(f"# total gaps: {len(rows)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
