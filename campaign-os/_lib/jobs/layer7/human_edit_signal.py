"""Aggregate L4 human-edits.jsonl → human-edit-summary.json."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..layer1._io import atomic_write, utc_now_iso

OUTPUT = "human-edit-summary.json"
SCHEMA = "campaign-os/human-edit-summary/v1"


def _data_dir() -> Path:
    return Path(__import__("os").environ.get("DATA_DIR", "/data"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows


def _normalise_action(row: dict[str, Any]) -> str:
    action = str(row.get("action") or "").lower()
    if action in ("approve", "reject", "edit"):
        return action
    if row.get("fields"):
        return "edit"
    return "edit"


def run() -> dict:
    """Summarise human edit signals from L4 jsonl."""
    rows = _read_jsonl(_data_dir() / "human-edits.jsonl")

    by_action: dict[str, int] = defaultdict(int)
    by_item_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_brand: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    field_counts: dict[str, int] = defaultdict(int)
    last_edit_at: str | None = None
    delta_available = False
    kept_verbatim = 0
    char_deltas: list[int] = []

    for row in rows:
        action = _normalise_action(row)
        by_action[action] += 1
        item_type = str(row.get("item_type") or "unknown")
        brand = str(row.get("brand_id") or "unknown")
        by_item_type[item_type][action] += 1
        by_brand[brand][action] += 1

        ts = str(row.get("ts") or "")
        if ts and (last_edit_at is None or ts > last_edit_at):
            last_edit_at = ts

        fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
        previous = row.get("previous") if isinstance(row.get("previous"), dict) else {}
        for field_name in fields:
            field_counts[str(field_name)] += 1
        if previous:
            delta_available = True
            for field_name, new_val in fields.items():
                old_val = previous.get(field_name)
                if old_val is not None and new_val is not None:
                    old_s = str(old_val)
                    new_s = str(new_val)
                    char_deltas.append(len(new_s) - len(old_s))
                    if old_s == new_s:
                        kept_verbatim += 1

    edits = int(by_action.get("edit", 0))
    approves = int(by_action.get("approve", 0))
    rejects = int(by_action.get("reject", 0))
    actionable = edits + approves + rejects
    edit_rate = round(edits / actionable, 3) if actionable else 0.0

    top_edited_fields = sorted(
        [{"field": k, "count": v} for k, v in field_counts.items()],
        key=lambda item: item["count"],
        reverse=True,
    )

    delta_block: dict[str, Any] = {
        "available": delta_available,
        "_note": "previous values not captured before 2026-09-17; see plan §3.4",
    }
    if delta_available and char_deltas:
        delta_block = {
            "available": True,
            "mean_char_delta": round(sum(char_deltas) / len(char_deltas), 1),
            "median_char_delta": sorted(char_deltas)[len(char_deltas) // 2],
            "kept_verbatim": kept_verbatim,
        }

    payload = {
        "schema": SCHEMA,
        "generated_at": utc_now_iso(),
        "generated_by": "layer7/human_edit_signal.py",
        "rows": len(rows),
        "by_action": dict(by_action),
        "by_item_type": {k: dict(v) for k, v in by_item_type.items()},
        "by_brand": {k: dict(v) for k, v in by_brand.items()},
        "edit_rate": edit_rate,
        "top_edited_fields": top_edited_fields,
        "last_edit_at": last_edit_at,
        "delta": delta_block,
    }
    atomic_write(OUTPUT, payload)
    return {"ok": True, "rows": len(rows)}
