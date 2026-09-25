#!/usr/bin/env python3
"""Idempotent Campaign Model v1 backfill (C0). Default: --dry-run prints planned changes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_OS = REPO_ROOT / "campaign-os"
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.campaigns import (  # noqa: E402
    default_origin_from_record,
    ensure_always_on,
    migrate_brand_planning_active_campaigns,
)
from _lib.marketing_calendar import (  # noqa: E402
    VALID_BRAND_IDS,
    canonical_records,
    load_brand_config,
    write_brand_config,
)
from _lib.marketing_lanes import get_campaign, save_campaign  # noqa: E402

STICK_EVENT_GAPS = [
    {
        "id": "halloween-2026",
        "name": "Halloween",
        "start": "2026-10-31",
        "tier": "B-PIN",
        "notes": "events-file gap — humour lane",
    },
    {
        "id": "festive-gifting-2026",
        "name": "Festive Gifting",
        "start": "2026-11-16",
        "tier": "A-PIN",
        "notes": "events-file gap",
    },
    {
        "id": "singles-day-2026",
        "name": "Singles' Day",
        "start": "2026-11-11",
        "tier": "B-PIN",
        "notes": "events-file gap",
    },
    {
        "id": "cyber-monday-2026",
        "name": "Cyber Monday",
        "start": "2026-11-30",
        "tier": "A-PIN",
        "notes": "events-file gap",
    },
    {
        "id": "new-years-eve-2026",
        "name": "New Year's Eve",
        "start": "2026-12-31",
        "tier": "C-PIN",
        "notes": "events-file gap",
    },
]


def _log(changes: list[dict[str, Any]], row: dict[str, Any]) -> None:
    changes.append(row)


def _backfill_record_origins(brand_id: str, *, dry_run: bool) -> list[dict[str, Any]]:
    from _lib.marketing_calendar import _calendar_path, _watchlist_path  # noqa: PLC0415

    changes: list[dict[str, Any]] = []
    paths = [_calendar_path(brand_id), _watchlist_path(brand_id)]
    for path in paths:
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        new_lines: list[str] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                new_lines.append(line)
                continue
            updated = dict(rec)
            touched = False
            if brand_id == "stick" and not updated.get("type"):
                updated["type"] = "moment"
                _log(changes, {"action": "set_type_moment", "calendar_id": updated.get("calendar_id")})
                touched = True
            if not updated.get("origin"):
                updated["origin"] = default_origin_from_record(updated)
                updated["origin"]["kind"] = "legacy"
                _log(
                    changes,
                    {
                        "action": "backfill_origin_legacy",
                        "calendar_id": updated.get("calendar_id"),
                    },
                )
                touched = True
            pillars = updated.get("pillars") or []
            if not updated.get("pillar_id") and isinstance(pillars, list) and len(pillars) == 1:
                p0 = pillars[0]
                pid = p0 if isinstance(p0, str) else (p0.get("pillar_id") if isinstance(p0, dict) else None)
                if pid:
                    updated["pillar_id"] = pid
                    touched = True
            if touched and not dry_run:
                new_lines.append(json.dumps(updated, ensure_ascii=False))
            else:
                new_lines.append(line if not touched else json.dumps(updated, ensure_ascii=False))
        if not dry_run and changes:
            path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
    return changes


def _move_psycho_bunny_objective(*, dry_run: bool) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    cfg = load_brand_config("stick")
    pillars = cfg.get("pillars") or []
    retail = next((p for p in pillars if isinstance(p, dict) and p.get("pillar_id") == "stick-retail"), None)
    if not retail:
        return changes
    objective = str(retail.get("objective") or "")
    north = retail.get("north_star_target")
    if "Psycho Bunny" in objective or (isinstance(north, dict) and north.get("monthly_target_zar") == 350000):
        _log(changes, {"action": "move_pb_objective_to_campaign", "pillar_id": "stick-retail"})
        if not dry_run:
            camp = get_campaign("stick", "psycho-bunny-launch") or {}
            camp.setdefault("name", "Psycho Bunny Launch")
            camp["pillar_id"] = "stick-retail"
            camp["phase"] = camp.get("phase") or "launching"
            camp["objective"] = objective
            if isinstance(north, dict):
                camp["north_star_target"] = north
            camp["product_brand"] = camp.get("product_brand") or "psycho-bunny"
            save_campaign("stick", "psycho-bunny-launch", camp)
            retail["objective"] = "Retail revenue"
            if isinstance(north, dict):
                retail["north_star_target"] = {
                    **north,
                    "monthly_target_zar": None,
                    "monthly_target_note": "Moved to psycho-bunny-launch campaign",
                }
            write_brand_config("stick", cfg)
    return changes


def _load_plan_file_moments(*, dry_run: bool) -> list[dict[str, Any]]:
    from _lib.marketing_calendar import add_candidate  # noqa: PLC0415

    changes: list[dict[str, Any]] = []
    existing_titles = {
        str(r.get("title") or "").lower()
        for r in canonical_records("stick")
    }
    for ev in STICK_EVENT_GAPS:
        title = ev["name"]
        if title.lower() in existing_titles:
            _log(changes, {"action": "skip_moment_exists", "title": title})
            continue
        _log(changes, {"action": "add_plan_file_moment", "title": title, "date": ev["start"]})
        if dry_run:
            continue
        add_candidate(
            "stick",
            {
                "type": "moment",
                "title": title,
                "event_date": ev["start"],
                "event_start": ev["start"],
                "status": "approved",
                "verification_status": "verified_primary",
                "date_confidence": "confirmed_date",
                "source_origin": "internal_strategy",
                "created_by": "migrate_campaign_model_v1",
                "pillars": ["stick-retail"],
                "origin": {
                    "kind": "plan_file",
                    "actor": "migrate_campaign_model_v1",
                    "ref": ev["id"],
                },
                "notes": ev.get("notes"),
            },
            initial_status="approved",
        )
    return changes


def run_migration(*, dry_run: bool = True) -> dict[str, Any]:
    report: dict[str, Any] = {"dry_run": dry_run, "brands": {}}
    for brand_id in VALID_BRAND_IDS:
        brand_changes: list[dict[str, Any]] = []
        brand_changes.extend(_backfill_record_origins(brand_id, dry_run=dry_run))
        brand_changes.extend(ensure_always_on(brand_id, dry_run=dry_run))
        brand_changes.extend(migrate_brand_planning_active_campaigns(brand_id, dry_run=dry_run))
        report["brands"][brand_id] = brand_changes
    report["brands"]["stick"] = (report["brands"].get("stick") or []) + _move_psycho_bunny_objective(
        dry_run=dry_run
    )
    report["brands"]["stick"] = (report["brands"].get("stick") or []) + _load_plan_file_moments(dry_run=dry_run)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Campaign Model v1 migration (C0)")
    parser.add_argument("--apply", action="store_true", help="Write changes to DATA_DIR (default is dry-run)")
    args = parser.parse_args()
    dry_run = not args.apply
    if args.apply and not os.environ.get("DATA_DIR"):
        print("DATA_DIR must be set for --apply", file=sys.stderr)
        return 2
    report = run_migration(dry_run=dry_run)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
