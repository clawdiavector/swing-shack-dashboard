"""Optional idempotent backfill for asset.channels and queue post_id fields."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run(*, apply: bool = False, brand: str | None = None) -> dict[str, Any]:
    from _lib import publish_sandbox
    from _lib.unified_inbox import _campaign_asset_for_id, _load_campaign_data, _write_campaign_data, asset_id_from_queue_row

    data_dir = publish_sandbox._data_dir()
    queue_path = publish_sandbox._queue_path()
    rows = publish_sandbox._read_jsonl(queue_path)
    campaign_data = _load_campaign_data()
    by_asset: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        bid = str(row.get("brand_id") or "")
        if brand and bid != brand:
            continue
        aid = asset_id_from_queue_row(row) or str(row.get("post_id") or "")
        if not aid:
            continue
        by_asset.setdefault(aid, []).append(row)

    stats: dict[str, dict[str, int]] = {}
    writes = 0
    backup: str | None = None
    for aid, group in by_asset.items():
        bid = str(group[0].get("brand_id") or "")
        stats.setdefault(bid, {"posts": 0, "deliveries": 0, "half_approved": 0})
        stats[bid]["posts"] += 1
        stats[bid]["deliveries"] += len(group)
        approved = sum(1 for r in group if r.get("human_approved"))
        if 0 < approved < len(group):
            stats[bid]["half_approved"] += 1
        picked = publish_sandbox.picked_channels(None, brand_id=bid, queue_rows=group)
        _cid, asset = _campaign_asset_for_id(campaign_data, aid)
        if asset is not None and asset.get("channels") != picked:
            writes += 1
            if apply:
                asset["channels"] = list(picked)
        for row in group:
            if not row.get("post_id"):
                writes += 1
                if apply:
                    row["post_id"] = aid
    if apply and writes:
        _write_campaign_data(campaign_data)
        backup = queue_path.with_suffix(
            f".jsonl.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        shutil.copy2(queue_path, backup)
        publish_sandbox._rewrite_jsonl(queue_path, rows)
    return {
        "ok": True,
        "dry_run": not apply,
        "writes": writes,
        "stats_by_brand": stats,
        "backup": str(backup) if apply and writes else None,
    }
