"""Append-only post cost ledger ($DATA_DIR/cost-ledger/<day>.jsonl)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

SCHEMA_LINE = "campaign-os/cost-line/v1"
SCHEMA_SUMMARY = "campaign-os/post-cost-summary/v1"


def _data_dir() -> str:
    return os.environ.get("DATA_DIR") or "/data"


def _utc_day(day: Optional[str] = None) -> str:
    return day or datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ledger_path(day: Optional[str] = None) -> Path:
    d = _utc_day(day)
    return Path(_data_dir()) / "cost-ledger" / f"{d}.jsonl"


def _iter_days(from_day: str, to_day: str) -> list[str]:
    start = datetime.strptime(from_day, "%Y-%m-%d").date()
    end = datetime.strptime(to_day, "%Y-%m-%d").date()
    if end < start:
        start, end = end, start
    out: list[str] = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _parse_line(raw: str) -> dict[str, Any] | None:
    line = (raw or "").strip()
    if not line:
        return None
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    return row if isinstance(row, dict) else None


def _read_lines_for_days(days: list[str]) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    degraded = False
    for day in days:
        path = _ledger_path(day)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            degraded = True
            continue
        for raw in text.splitlines():
            row = _parse_line(raw)
            if row is None and raw.strip():
                degraded = True
                continue
            if row:
                rows.append(row)
    return rows, degraded


def _existing_keys(day: Optional[str] = None) -> set[str]:
    path = _ledger_path(day)
    keys: set[str] = set()
    if not path.is_file():
        return keys
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            row = _parse_line(raw)
            if not row:
                continue
            for k in ("post_cost_key", "id"):
                v = row.get(k)
                if isinstance(v, str) and v.strip():
                    keys.add(v.strip())
    except OSError:
        pass
    return keys


def append_line(
    *,
    usd: float,
    brand_id: str,
    kind: str,
    route: str,
    inbox_item_id: str,
    action: str,
    cost_source: str,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    event_key: Optional[str] = None,
    draft_asset_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    queue_row_id: Optional[str] = None,
    retry_of: Optional[str] = None,
    post_cost_key: Optional[str] = None,
    day: Optional[str] = None,
) -> Optional[str]:
    """Append one cost line. Returns post_cost_key or None if skipped (duplicate key)."""
    try:
        amount = round(max(0.0, float(usd or 0.0)), 6)
    except (TypeError, ValueError):
        amount = 0.0
    bid = (brand_id or "").strip()
    if not bid:
        return None
    iid = (inbox_item_id or "").strip()
    if not iid:
        return None

    d = _utc_day(day)
    key = (post_cost_key or "").strip() or f"pcl-{uuid.uuid4().hex[:12]}"
    if key in _existing_keys(d):
        return None

    row: dict[str, Any] = {
        "schema": SCHEMA_LINE,
        "post_cost_key": key,
        "id": key,
        "ts": _utc_now_iso(),
        "brand_id": bid,
        "event_key": (event_key or "").strip() or None,
        "inbox_item_id": iid,
        "draft_asset_id": (draft_asset_id or "").strip() or None,
        "campaign_id": (campaign_id or "").strip() or None,
        "kind": (kind or "image")[:40],
        "action": (action or "unknown")[:80],
        "route": (route or "")[:120],
        "provider": (provider or "")[:80] or None,
        "model": (model or "")[:80] or None,
        "usd": amount,
        "cost_source": (cost_source or "estimate")[:40],
        "queue_row_id": (queue_row_id or "").strip() or None,
        "retry_of": (retry_of or "").strip() or None,
    }
    path = _ledger_path(d)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError:
        return None
    return key


def _sum_by_kind(rows: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        k = str(row.get("kind") or "image")
        out[k] = round(out.get(k, 0.0) + float(row.get("usd") or 0.0), 6)
    return out


def _build_summary(
    rows: list[dict[str, Any]],
    *,
    inbox_item_id: Optional[str] = None,
    event_key: Optional[str] = None,
    degraded: bool = False,
) -> dict[str, Any]:
    if not rows:
        base: dict[str, Any] = {
            "schema": SCHEMA_SUMMARY,
            "brand_id": None,
            "event_key": event_key,
            "inbox_item_id": inbox_item_id,
            "total_usd": 0.0,
            "by_kind": {"text": 0.0, "image": 0.0, "edit": 0.0},
            "by_draft_asset": [],
            "first_ts": None,
            "last_ts": None,
            "call_count": 0,
        }
        if degraded:
            base["degraded"] = True
        return base

    brand_id = str(rows[0].get("brand_id") or "")
    if inbox_item_id is None:
        inbox_item_id = str(rows[0].get("inbox_item_id") or "")
    if event_key is None:
        event_key = rows[0].get("event_key")

    total = round(sum(float(r.get("usd") or 0.0) for r in rows), 6)
    by_kind = _sum_by_kind(rows)
    for k in ("text", "image", "edit"):
        by_kind.setdefault(k, 0.0)

    asset_map: dict[str, dict[str, Any]] = {}
    retries_by_asset: dict[str, int] = {}
    for row in rows:
        aid = str(row.get("draft_asset_id") or "_none")
        bucket = asset_map.setdefault(
            aid,
            {
                "draft_asset_id": None if aid == "_none" else aid,
                "action": row.get("action"),
                "usd": 0.0,
                "calls": 0,
                "retries": 0,
            },
        )
        bucket["usd"] = round(float(bucket["usd"]) + float(row.get("usd") or 0.0), 6)
        bucket["calls"] = int(bucket["calls"]) + 1
        if row.get("retry_of"):
            retries_by_asset[aid] = retries_by_asset.get(aid, 0) + 1
    for aid, n in retries_by_asset.items():
        if aid in asset_map:
            asset_map[aid]["retries"] = n

    ts_vals = [str(r.get("ts") or "") for r in rows if r.get("ts")]
    ts_vals.sort()
    summary: dict[str, Any] = {
        "schema": SCHEMA_SUMMARY,
        "brand_id": brand_id,
        "event_key": event_key,
        "inbox_item_id": inbox_item_id,
        "total_usd": total,
        "by_kind": by_kind,
        "by_draft_asset": list(asset_map.values()),
        "first_ts": ts_vals[0] if ts_vals else None,
        "last_ts": ts_vals[-1] if ts_vals else None,
        "call_count": len(rows),
    }
    if degraded:
        summary["degraded"] = True
    return summary


def today_rollup(*, brand: Optional[str] = None) -> dict[str, Any]:
    day = _utc_day()
    rows, degraded = _read_lines_for_days([day])
    if brand:
        rows = [r for r in rows if str(r.get("brand_id") or "") == brand]
    by_kind = _sum_by_kind(rows)
    for k in ("text", "image", "edit"):
        by_kind.setdefault(k, 0.0)
    by_brand: dict[str, float] = {}
    posts: set[str] = set()
    for row in rows:
        bid = str(row.get("brand_id") or "_unattributed")
        by_brand[bid] = round(by_brand.get(bid, 0.0) + float(row.get("usd") or 0.0), 6)
        iid = str(row.get("inbox_item_id") or "")
        if iid:
            posts.add(iid)
    total = round(sum(float(r.get("usd") or 0.0) for r in rows), 6)
    out: dict[str, Any] = {
        "day": day,
        "spent_usd": total,
        "by_kind": by_kind,
        "by_brand": by_brand,
        "call_count": len(rows),
        "posts_today": len(posts),
    }
    if degraded:
        out["degraded"] = True
    return out


def summary_for_inbox_item(inbox_item_id: str, *, lookback_days: int = 14) -> dict[str, Any]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(1, lookback_days) - 1)
    days = _iter_days(start.isoformat(), end.isoformat())
    rows, degraded = _read_lines_for_days(days)
    iid = (inbox_item_id or "").strip()
    matched = [r for r in rows if str(r.get("inbox_item_id") or "") == iid]
    return _build_summary(matched, inbox_item_id=iid, degraded=degraded)


def summary_for_event_key(event_key: str, *, lookback_days: int = 14) -> dict[str, Any]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(1, lookback_days) - 1)
    days = _iter_days(start.isoformat(), end.isoformat())
    rows, degraded = _read_lines_for_days(days)
    ek = (event_key or "").strip()
    matched = [r for r in rows if str(r.get("event_key") or "") == ek]
    latest_iid = None
    if matched:
        sorted_rows = sorted(matched, key=lambda r: str(r.get("ts") or ""))
        latest_iid = str(sorted_rows[-1].get("inbox_item_id") or "")
    return _build_summary(
        matched,
        inbox_item_id=latest_iid,
        event_key=ek or None,
        degraded=degraded,
    )


def range_rollup(*, brand: Optional[str], from_day: str, to_day: str) -> dict[str, Any]:
    days = _iter_days(from_day, to_day)
    rows, degraded = _read_lines_for_days(days)
    if brand:
        rows = [r for r in rows if str(r.get("brand_id") or "") == brand]
    by_day: dict[str, float] = {}
    posts: set[str] = set()
    for row in rows:
        ts = str(row.get("ts") or "")
        day = ts[:10] if len(ts) >= 10 else _utc_day()
        by_day[day] = round(by_day.get(day, 0.0) + float(row.get("usd") or 0.0), 6)
        iid = str(row.get("inbox_item_id") or "")
        if iid:
            posts.add(iid)
    total = round(sum(float(r.get("usd") or 0.0) for r in rows), 6)
    out: dict[str, Any] = {
        "from": from_day,
        "to": to_day,
        "brand_id": brand,
        "total_usd": total,
        "by_day": by_day,
        "by_kind": _sum_by_kind(rows),
        "posts": len(posts),
    }
    if degraded:
        out["degraded"] = True
    return out
