"""Sandbox publish adapter — receipts + queue under $DATA_DIR/publish-sandbox/. No outbound HTTP."""

from __future__ import annotations

import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from _lib.brand_validate import validate_brand_id

SANDBOX_CONFIG_SCHEMA = "campaign-os/publish-sandbox/v1"
RECEIPT_SCHEMA = "campaign-os/publish-receipt/v1"
QUEUE_SCHEMA = "campaign-os/publish-queue-item/v1"

INTENDED_CHANNELS_FALLBACK: dict[str, list[str]] = {
    "swing-shack": ["instagram", "facebook", "gbp"],
    "stick": ["instagram", "facebook"],
    "bag-drop": [],
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def sandbox_dir() -> Path:
    override = os.environ.get("PUBLISH_SANDBOX_DIR")
    if override:
        return Path(override)
    return _data_dir() / "publish-sandbox"


def _config_path() -> Path:
    return sandbox_dir() / "config.json"


def _queue_path() -> Path:
    return sandbox_dir() / "queue.jsonl"


def _receipts_path() -> Path:
    return sandbox_dir() / "receipts.jsonl"


def _mirror_path() -> Path:
    return sandbox_dir() / "postiz-mirror.json"


def _load_brands_registry() -> dict[str, Any]:
    path = _data_dir() / "brands.json"
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                return doc
        except (OSError, json.JSONDecodeError):
            pass
    bundled = Path(__file__).resolve().parents[2] / "data" / "brands.json"
    if bundled.is_file():
        try:
            doc = json.loads(bundled.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                return doc
        except (OSError, json.JSONDecodeError):
            pass
    return {"brands": {}}


def intended_publish_channels(brand_id: str) -> list[str]:
    """Return brands.json publish_channels, else the auth-status matrix fallback."""
    brand_id = validate_brand_id(brand_id)
    reg = _load_brands_registry()
    brands = reg.get("brands") if isinstance(reg, dict) else None
    if isinstance(brands, dict):
        entry = brands.get(brand_id)
        if isinstance(entry, dict):
            channels = entry.get("publish_channels")
            if isinstance(channels, list):
                return [str(ch) for ch in channels if ch]
    return list(INTENDED_CHANNELS_FALLBACK.get(brand_id, []))


def _normalize_platform(platform: str) -> str:
    from _lib.jobs.layer5.image_draft_context import _normalize_platform as _norm  # noqa: PLC0415

    return _norm(platform)


def platform_allowed(brand_id: str, platform: str) -> bool:
    """True when platform is on the brand publish_channels allowlist."""
    brand_id = validate_brand_id(brand_id)
    want = _normalize_platform(platform)
    allowed = {_normalize_platform(ch) for ch in intended_publish_channels(brand_id)}
    return want in allowed


def _would_publish_at_from_event_date(
    event_date: str,
    *,
    release_time_sast: str = "09:00",
) -> Optional[str]:
    raw = (event_date or "").strip()
    if not raw:
        return None
    day = raw[:10]
    if len(day) != 10 or day[4] != "-" or day[7] != "-":
        return None
    time_part = (release_time_sast or "09:00").strip() or "09:00"
    if len(time_part) == 5:
        time_part = f"{time_part}:00"
    return f"{day}T{time_part}Z"


def enqueue_for_primary_channel(
    *,
    brand_id: str,
    caption_preview: str,
    inbox_item_id: str,
    asset_id: str,
    asset_platform: str = "",
    lodged_title: str = "",
) -> list[dict[str, Any]]:
    """One sandbox row for the calendar moment's primary_channel (allowlist-checked)."""
    from _lib.jobs.layer5.image_draft_context import (  # noqa: PLC0415
        calendar_event_date_for_item,
        lodged_title_for_item,
        primary_channel_for_item,
    )

    brand_id = validate_brand_id(brand_id)
    inbox_ref = str(inbox_item_id or "")
    platform = primary_channel_for_item(
        brand_id,
        inbox_ref,
        fallback=asset_platform or "instagram",
    )
    if not platform_allowed(brand_id, platform):
        return []
    title = lodged_title_for_item(
        brand_id,
        inbox_ref,
        sidecar_title=lodged_title,
    )
    event_date = calendar_event_date_for_item(brand_id, inbox_ref)
    item = enqueue_item(
        brand_id=brand_id,
        platform=platform,
        caption_preview=caption_preview,
        inbox_item_id=inbox_item_id,
        human_approved=False,
        would_publish_at=_would_publish_at_from_event_date(event_date),
        idempotency_key=f"qc-{asset_id}-{platform}",
        lodged_title=title or None,
        event_date=event_date or None,
        provenance=_provenance_from_draft_asset(asset_id),
    )
    return [item]


def enqueue_for_intended_channels(
    *,
    brand_id: str,
    caption_preview: str,
    inbox_item_id: str,
    asset_id: str,
    asset_platform: str = "",
    lodged_title: str = "",
) -> list[dict[str, Any]]:
    """Backward-compatible alias — one row on primary_channel only."""
    return enqueue_for_primary_channel(
        brand_id=brand_id,
        caption_preview=caption_preview,
        inbox_item_id=inbox_item_id,
        asset_id=asset_id,
        asset_platform=asset_platform,
        lodged_title=lodged_title,
    )


def ensure_sandbox_layout() -> Path:
    root = sandbox_dir()
    root.mkdir(parents=True, exist_ok=True)
    cfg = _config_path()
    if not cfg.is_file():
        cfg.write_text(
            json.dumps(
                {
                    "schema": SANDBOX_CONFIG_SCHEMA,
                    "mode": "sandbox",
                    "created_at": _utc_now_iso(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return root


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


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    ensure_sandbox_layout()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _rewrite_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_sandbox_layout()
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    path.write_text(text, encoding="utf-8")


def _receipt_index() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rec in _read_jsonl(_receipts_path()):
        key = rec.get("idempotency_key")
        if key:
            out[str(key)] = rec
    return out


def _queue_index_by_idempotency() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(_queue_path()):
        key = row.get("idempotency_key")
        if key:
            out[str(key)] = row
    return out


def _provenance_from_draft_asset(asset_id: str) -> dict[str, Any]:
    path = _data_dir() / "draft-assets" / f"{asset_id}.json"
    if not path.is_file():
        return {}
    try:
        sidecar = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(sidecar, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("pillar_id", "campaign_id", "lane", "origin", "process"):
        if sidecar.get(key) is not None:
            out[key] = sidecar[key]
    return out


def enqueue_item(
    *,
    brand_id: str,
    platform: str = "instagram",
    channel: str = "postiz",
    caption_preview: str = "",
    inbox_item_id: Optional[str] = None,
    human_approved: bool = False,
    would_publish_at: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    lodged_title: Optional[str] = None,
    event_date: Optional[str] = None,
    provenance: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Append a pending queue row (no network)."""
    ensure_sandbox_layout()
    brand_id = validate_brand_id(brand_id)
    key = idempotency_key or f"sb-{brand_id}-{platform}-{secrets.token_hex(8)}"
    existing = _receipt_index().get(key) or _queue_index_by_idempotency().get(key)
    if existing:
        return existing
    item = {
        "schema": QUEUE_SCHEMA,
        "queue_id": str(uuid.uuid4()),
        "inbox_item_id": inbox_item_id,
        "brand_id": brand_id,
        "channel": channel,
        "platform": platform,
        "caption_preview": (caption_preview or "")[:500],
        "lodged_title": (lodged_title or "")[:240] or None,
        "event_date": (event_date or "")[:32] or None,
        "idempotency_key": key,
        "human_approved": bool(human_approved),
        "human_approved_at": _utc_now_iso() if human_approved else None,
        "status": "pending",
        "would_publish_at": would_publish_at,
        "created_at": _utc_now_iso(),
    }
    prov = provenance or {}
    if inbox_item_id and not prov:
        from _lib.campaigns import read_create_payload  # noqa: PLC0415

        prov = read_create_payload(str(inbox_item_id))
    for key in ("pillar_id", "campaign_id", "lane", "origin", "process"):
        if prov.get(key) is not None:
            item[key] = prov[key]
    _append_jsonl(_queue_path(), item)
    return item


def approve_item(idempotency_key: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Mark a pending queue item human-approved."""
    rows = _read_jsonl(_queue_path())
    found: Optional[dict[str, Any]] = None
    for row in rows:
        if row.get("idempotency_key") == idempotency_key and row.get("status") == "pending":
            row["human_approved"] = True
            row["human_approved_at"] = _utc_now_iso()
            found = row
            break
    if not found:
        return None, "queue item not found or not pending"
    _rewrite_jsonl(_queue_path(), rows)
    return found, None


def dispatch_item(item: dict[str, Any]) -> tuple[dict[str, Any], Optional[str]]:
    """Write sandbox receipt for one approved item. Idempotent on idempotency_key."""
    if not item.get("human_approved"):
        return {}, "human_approved required"

    key = str(item.get("idempotency_key") or "")
    if not key:
        return {}, "idempotency_key required"

    try:
        brand_id = validate_brand_id(item.get("brand_id"))
    except ValueError as exc:
        return {}, str(exc)

    existing = _receipt_index().get(key)
    if existing:
        return existing, None

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "mode": "sandbox",
        "inbox_item_id": item.get("inbox_item_id"),
        "brand_id": brand_id,
        "channel": item.get("channel", "postiz"),
        "platform": item.get("platform", "instagram"),
        "idempotency_key": key,
        "human_approved_at": item.get("human_approved_at"),
        "dispatched_at": _utc_now_iso(),
        "sandbox_post_id": f"sb-post-{uuid.uuid4()}",
        "caption_preview": (item.get("caption_preview") or "")[:120],
        "would_publish_at": item.get("would_publish_at"),
    }
    for key in ("pillar_id", "campaign_id", "lane", "origin", "process"):
        if item.get(key) is not None:
            receipt[key] = item[key]
    _append_jsonl(_receipts_path(), receipt)
    _update_mirror(receipt)
    return receipt, None


def _stamp_queue_row_dispatched(row: dict[str, Any], receipt: dict[str, Any]) -> None:
    row["status"] = "dispatched"
    row["dispatched_at"] = receipt.get("dispatched_at")
    row["sandbox_post_id"] = receipt.get("sandbox_post_id")


def dispatch_one(idempotency_key: str) -> tuple[dict[str, Any], Optional[str]]:
    """Dispatch exactly one pending + human_approved row. Idempotent on the key."""
    ensure_sandbox_layout()
    key = str(idempotency_key or "").strip()
    if not key:
        return {}, "idempotency_key required"
    rows = _read_jsonl(_queue_path())
    target: dict[str, Any] | None = None
    for row in rows:
        if row.get("idempotency_key") == key and row.get("status") == "pending":
            target = row
            break
    if not target:
        existing = _receipt_index().get(key)
        if existing:
            return existing, None
        return {}, "queue item not found or not pending"
    if not target.get("human_approved"):
        return {}, "human_approved required"
    receipts_index = _receipt_index()
    if key in receipts_index:
        receipt = receipts_index[key]
    else:
        receipt, err = dispatch_item(target)
        if err:
            return {}, err
    for row in rows:
        if row.get("idempotency_key") == key and row.get("status") == "pending":
            _stamp_queue_row_dispatched(row, receipt)
            break
    _rewrite_jsonl(_queue_path(), rows)
    return receipt, None


def release_moment(
    *,
    brand_id: str,
    calendar_id: str,
    editor: str = "operator",
    dispatch: bool,
) -> dict[str, Any]:
    """Set human_approved on this moment's pending rows. Scheduled → Released."""
    from _lib.unified_inbox import post_state_for  # noqa: PLC0415

    brand_id = validate_brand_id(brand_id)
    cal_id = str(calendar_id or "").strip()
    if not cal_id:
        return {"ok": False, "error": "calendar_id required", "code": "bad_request"}

    state_doc = post_state_for(brand_id, cal_id)
    if not state_doc:
        return {"ok": False, "error": "calendar record not found", "code": "not_found"}

    state = str(state_doc.get("state") or "")
    sandbox = state_doc.get("sandbox") or []
    go_live = state_doc.get("go_live_date")
    would_publish_at = _would_publish_at_from_event_date(str(go_live or ""))

    if state in ("released", "posted"):
        return {
            "ok": False,
            "error": "already released",
            "code": "already_released",
            "state": state,
            "would_publish_at": would_publish_at,
        }
    if state != "scheduled":
        return {
            "ok": False,
            "error": f"not scheduled (state={state})",
            "code": "not_scheduled",
            "state": state,
        }
    if not sandbox:
        return {
            "ok": False,
            "error": "no publish channel queue row",
            "code": "no_channel",
            "state": state,
        }

    released: list[str] = []
    for row in sandbox:
        if str(row.get("status") or "") != "pending":
            continue
        key = str(row.get("idempotency_key") or "")
        if not key:
            continue
        if row.get("human_approved"):
            released.append(key)
            continue
        updated, err = approve_item(key)
        if err:
            return {"ok": False, "error": err, "code": "approve_failed", "state": state}
        if updated:
            released.append(key)

    if not released:
        return {
            "ok": False,
            "error": "no pending queue rows to release",
            "code": "no_channel",
            "state": state,
        }

    inbox_ref = str(state_doc.get("inbox_item_id") or "")
    _append_jsonl(
        _data_dir() / "human-edits.jsonl",
        {
            "schema": "campaign-os/human-edit-signal/v1",
            "ts": _utc_now_iso(),
            "action": "release",
            "editor": editor,
            "inbox_item_id": inbox_ref,
            "item_type": "draft_asset",
            "brand_id": brand_id,
            "calendar_id": cal_id,
        },
    )

    dispatched: list[str] = []
    if dispatch:
        for key in released:
            _, err = dispatch_one(key)
            if not err:
                dispatched.append(key)

    after = post_state_for(brand_id, cal_id) or state_doc
    return {
        "ok": True,
        "released": released,
        "dispatched": dispatched,
        "state": str(after.get("state") or state),
        "would_publish_at": would_publish_at,
    }


def dispatch_pending() -> dict[str, Any]:
    """Process all pending + human_approved queue rows. Job entrypoint helper."""
    ensure_sandbox_layout()
    rows = _read_jsonl(_queue_path())
    receipts_index = _receipt_index()
    dispatched = 0
    refused = 0
    skipped = 0
    errors: list[str] = []

    updated_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "pending":
            updated_rows.append(row)
            continue
        if not row.get("human_approved"):
            skipped += 1
            updated_rows.append(row)
            continue
        key = str(row.get("idempotency_key") or "")
        if key in receipts_index:
            _stamp_queue_row_dispatched(row, receipts_index[key])
            dispatched += 1
            updated_rows.append(row)
            continue
        receipt, err = dispatch_item(row)
        if err:
            refused += 1
            errors.append(f"{key}: {err}")
            updated_rows.append(row)
            continue
        _stamp_queue_row_dispatched(row, receipt)
        dispatched += 1
        updated_rows.append(row)

    _rewrite_jsonl(_queue_path(), updated_rows)
    return {
        "ok": True,
        "mode": "sandbox",
        "dispatched": dispatched,
        "refused": refused,
        "skipped_unapproved": skipped,
        "errors": errors[:20],
        "writes": ["publish-sandbox/queue.jsonl", "publish-sandbox/receipts.jsonl"],
    }


def _update_mirror(receipt: dict[str, Any]) -> None:
    mirror = {"schema": "campaign-os/postiz-mirror-sandbox/v1", "posts": []}
    mp = _mirror_path()
    if mp.is_file():
        try:
            mirror = json.loads(mp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    posts = mirror.get("posts")
    if not isinstance(posts, list):
        posts = []
    posts.append(
        {
            "id": receipt.get("sandbox_post_id"),
            "brand_id": receipt.get("brand_id"),
            "platform": receipt.get("platform"),
            "caption": receipt.get("caption_preview"),
            "status": "sandbox_scheduled",
            "dispatched_at": receipt.get("dispatched_at"),
        }
    )
    mirror["posts"] = posts[-100:]
    mirror["updated_at"] = _utc_now_iso()
    mp.write_text(json.dumps(mirror, indent=2), encoding="utf-8")


def queued_asset_ids(*, brand: str | None = None) -> set[str]:
    """Asset ids with a pending sandbox row (qc-* keys only)."""
    from _lib.unified_inbox import asset_id_from_queue_row  # noqa: PLC0415

    out: set[str] = set()
    for row in _read_jsonl(_queue_path()):
        if str(row.get("status") or "") != "pending":
            continue
        if brand:
            row_brand = str(row.get("brand_id") or "")
            if row_brand and row_brand != brand:
                continue
        asset_id = asset_id_from_queue_row(row)
        if asset_id:
            out.add(asset_id)
    return out


def list_queue(*, brand: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Pending sandbox rows (+ recent receipts) enriched with draft image_url."""
    from _lib.unified_inbox import (  # noqa: PLC0415
        _asset_image_meta,
        _load_campaign_data,
        asset_id_from_queue_row,
        _campaign_asset_for_id,
    )

    ensure_sandbox_layout()
    campaign_data = _load_campaign_data()
    pending_rows: list[dict[str, Any]] = []
    for row in _read_jsonl(_queue_path()):
        if str(row.get("status") or "") != "pending":
            continue
        brand_id = str(row.get("brand_id") or "")
        if brand and brand_id and brand_id != brand:
            continue
        asset_id = asset_id_from_queue_row(row)
        campaign_id: str | None = None
        image_path: Any = None
        image_url: Any = None
        if asset_id:
            campaign_id, asset = _campaign_asset_for_id(campaign_data, asset_id)
            image_path, image_url = _asset_image_meta(asset)
        pending_rows.append(
            {
                "queue_id": row.get("queue_id"),
                "idempotency_key": row.get("idempotency_key"),
                "brand_id": brand_id,
                "platform": row.get("platform"),
                "channel": row.get("channel"),
                "caption": row.get("caption_preview") or "",
                "caption_preview": row.get("caption_preview") or "",
                "lodged_title": row.get("lodged_title"),
                "event_date": row.get("event_date"),
                "status": row.get("status"),
                "human_approved": bool(row.get("human_approved")),
                "created_at": row.get("created_at"),
                "would_publish_at": row.get("would_publish_at"),
                "asset_id": asset_id,
                "campaign_id": campaign_id,
                "image_path": image_path,
                "image_url": image_url,
                "inbox_item_id": row.get("inbox_item_id"),
            }
        )
    pending_rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    total_pending = len(pending_rows)
    pending_rows = pending_rows[: max(1, min(limit, 200))]

    receipts = _read_jsonl(_receipts_path())
    recent_receipts = receipts[-20:] if receipts else []
    recent_receipts.reverse()

    return {
        "ok": True,
        "mode": "sandbox",
        "brand": brand,
        "items": pending_rows,
        "recent_receipts": recent_receipts,
        "total_pending": total_pending,
    }


RECEIPTS_SCAN_CAP = 5000


def queue_rows_for_brand(brand_id: str) -> list[dict[str, Any]]:
    """All sandbox queue rows for a brand (every status)."""
    ensure_sandbox_layout()
    brand_id = validate_brand_id(brand_id)
    out: list[dict[str, Any]] = []
    for row in _read_jsonl(_queue_path()):
        if str(row.get("brand_id") or "") != brand_id:
            continue
        out.append(row)
    return out


def receipts_for_brand(brand_id: str) -> list[dict[str, Any]]:
    """Receipt rows for a brand (tail-capped scan)."""
    ensure_sandbox_layout()
    brand_id = validate_brand_id(brand_id)
    path = _receipts_path()
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > RECEIPTS_SCAN_CAP:
        lines = lines[-RECEIPTS_SCAN_CAP:]
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        if str(rec.get("brand_id") or "") != brand_id:
            continue
        out.append(rec)
    return out


def summary() -> dict[str, Any]:
    ensure_sandbox_layout()
    queue = _read_jsonl(_queue_path())
    receipts = _read_jsonl(_receipts_path())
    pending = sum(1 for q in queue if q.get("status") == "pending")
    pending_approved = sum(
        1 for q in queue if q.get("status") == "pending" and q.get("human_approved")
    )
    last_receipt = receipts[-1] if receipts else None
    return {
        "ok": True,
        "mode": "sandbox",
        "queue_depth": pending,
        "queue_approved_ready": pending_approved,
        "receipt_count": len(receipts),
        "last_receipt_at": last_receipt.get("dispatched_at") if last_receipt else None,
        "last_sandbox_post_id": last_receipt.get("sandbox_post_id") if last_receipt else None,
        "dir": str(sandbox_dir()),
    }
