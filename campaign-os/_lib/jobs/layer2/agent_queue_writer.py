"""Write agent-queue.json rows from slot planner, freshness, and reco inputs."""

from __future__ import annotations

from typing import Any

from ..errors import describe_exception
from _lib.brand_data_paths import read_brand_data_json
from _lib.marketing_calendar import VALID_BRAND_IDS

from ..layer1._io import as_dict, as_list, atomic_write, read_json, slug_id, utc_now_iso

OUTPUT = "agent-queue.json"
SCHEMA = "campaign-os/agent-queue/v1"
ROW_KEYS = frozenset({"id", "layer", "agent", "brand", "action", "payload_ref", "status"})


def _row_id(*, brand: str, action: str, payload_ref: str) -> str:
    return slug_id(f"{brand}-{action}-{payload_ref}", limit=80)


def _rows_from_slots(slots_doc: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for slot in as_list(slots_doc.get("empty_slots")):
        if not isinstance(slot, dict):
            continue
        brand = str(slot.get("brand") or "")
        date = str(slot.get("date") or "")
        pillar_id = str(slot.get("pillar_id") or "")
        if not brand or not date:
            continue
        payload_ref = f"slot-planner.json#{brand}/{date}/{pillar_id}"
        rows.append(
            {
                "id": _row_id(brand=brand, action="fill_slot", payload_ref=payload_ref),
                "layer": "L3",
                "agent": "cos-scout",
                "brand": brand,
                "action": "fill_slot",
                "payload_ref": payload_ref,
                "status": "pending",
            }
        )
    return rows


def _rows_from_freshness(freshness_doc: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for bucket in ("rotten_files", "stale_files"):
        for entry in as_list(freshness_doc.get(bucket)):
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or entry.get("file") or "")
            if not path:
                continue
            payload_ref = f"freshness.json#{path}"
            rows.append(
                {
                    "id": _row_id(brand="all", action="refresh_data", payload_ref=payload_ref),
                    "layer": "L1",
                    "agent": "cos-foreman",
                    "brand": "all",
                    "action": "refresh_data",
                    "payload_ref": payload_ref,
                    "status": "pending",
                }
            )
    return rows


def _rows_from_reco(reco_doc: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for bucket in ("do_first", "ranked_items"):
        for entry in as_list(reco_doc.get(bucket)):
            if not isinstance(entry, dict):
                continue
            item = entry.get("item") if isinstance(entry.get("item"), dict) else entry
            if not isinstance(item, dict):
                continue
            hook = str(item.get("hook_id") or item.get("hook") or item.get("type") or "")
            if not hook or hook in seen:
                continue
            seen.add(hook)
            brand = str(item.get("owner") or item.get("brand") or "swing-shack").split()[0].lower()
            if brand not in {"swing-shack", "stick", "bag-drop"}:
                brand = "swing-shack"
            payload_ref = f"recommendation-scores.json#{hook}"
            rows.append(
                {
                    "id": _row_id(brand=brand, action="interpret_reco", payload_ref=payload_ref),
                    "layer": "L3",
                    "agent": "cos-interpreter",
                    "brand": brand,
                    "action": "interpret_reco",
                    "payload_ref": payload_ref,
                    "status": "pending",
                }
            )
    return rows


def _validate_row(row: dict[str, Any]) -> dict[str, str]:
    clean = {k: str(row.get(k, "")) for k in ROW_KEYS}
    missing = ROW_KEYS - set(clean)
    if missing:
        raise ValueError(f"queue row missing keys: {sorted(missing)}")
    return clean


def _merge_rows(
    generated: list[dict[str, str]],
    existing: list[dict[str, Any]],
) -> list[dict[str, str]]:
    preserved = [
        _validate_row(row)
        for row in existing
        if isinstance(row, dict)
        and (
            row.get("status") != "pending"
            or str(row.get("id", "")).startswith("manual-")
        )
    ]
    preserved_ids = {row["id"] for row in preserved}
    merged = list(preserved)
    for row in generated:
        if row["id"] in preserved_ids:
            continue
        merged.append(row)
    merged.sort(key=lambda row: row["id"])
    return merged


def run() -> dict[str, Any]:
    """Merge deterministic queue rows; preserve non-pending rows from prior runs."""
    try:
        slots_doc = as_dict(read_json("slot-planner.json"))
        freshness_doc = as_dict(read_json("freshness.json"))

        existing_doc = as_dict(read_json(OUTPUT))
        existing_rows = as_list(existing_doc.get("rows"))

        generated: list[dict[str, str]] = []
        generated.extend(_rows_from_slots(slots_doc))
        generated.extend(_rows_from_freshness(freshness_doc))
        for brand_id in VALID_BRAND_IDS:
            reco_doc = as_dict(read_brand_data_json("recommendation-scores.json", brand_id))
            generated.extend(_rows_from_reco(reco_doc))

        rows = _merge_rows(generated, existing_rows)
        for row in rows:
            _validate_row(row)

        payload = {
            "schema": SCHEMA,
            "generated_at": utc_now_iso(),
            "rows": rows,
        }
        atomic_write(OUTPUT, payload)
        pending_count = sum(1 for row in rows if row.get("status") == "pending")
        return {"ok": True, "rows": pending_count}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": describe_exception(exc)}
