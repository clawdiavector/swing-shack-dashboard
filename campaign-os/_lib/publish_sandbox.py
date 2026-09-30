"""Sandbox publish adapter — receipts + queue under $DATA_DIR/publish-sandbox/. No outbound HTTP."""

from __future__ import annotations

import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
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

# Match L5 compose_post_for_channels — social feed channels only (GBP is separate).
COMPOSE_PUBLISH_CHANNEL_EXCLUDE = frozenset({"gbp"})


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


def compose_publish_channels(brand_id: str) -> list[str]:
    """IG + FB (etc.) for one creative — same set L5 uses when composing PNGs."""
    brand_id = validate_brand_id(brand_id)
    out: list[str] = []
    seen: set[str] = set()
    for ch in intended_publish_channels(brand_id):
        norm = _normalize_platform(str(ch))
        if norm in COMPOSE_PUBLISH_CHANNEL_EXCLUDE:
            continue
        if not platform_allowed(brand_id, norm):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _load_draft_sidecar(asset_id: str) -> dict[str, Any]:
    path = _data_dir() / "draft-assets" / f"{asset_id}.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _composed_url_for_platform(
    *,
    platform: str,
    asset: dict[str, Any] | None,
    sidecar: dict[str, Any] | None,
) -> str | None:
    plat = _normalize_platform(platform)
    composed: dict[str, Any] = {}
    for src in (sidecar, asset):
        if not isinstance(src, dict):
            continue
        block = src.get("composed")
        if isinstance(block, dict):
            composed.update(block)
    for key in (plat, platform):
        raw = composed.get(key)
        if raw:
            return str(raw).strip() or None
    if isinstance(asset, dict):
        from _lib.unified_inbox import _asset_image_meta  # noqa: PLC0415

        _path, url = _asset_image_meta(asset)
        if url:
            return str(url).strip() or None
    return None


_SAST = ZoneInfo("Africa/Johannesburg")


def _would_publish_at_from_event_date(
    event_date: str,
    *,
    release_time_sast: str = "09:00",
) -> Optional[str]:
    """Turn a calendar day plus a SAST wall time into a real UTC instant.

    13:00 SAST is 11:00Z. Stamping the SAST clock with Z made the dashboard
    show two hours later.
    """
    raw = (event_date or "").strip()
    if not raw:
        return None
    day = raw[:10]
    if len(day) != 10 or day[4] != "-" or day[7] != "-":
        return None
    time_part = (release_time_sast or "09:00").strip() or "09:00"
    if len(time_part) == 5:
        time_part = f"{time_part}:00"
    local = datetime.fromisoformat(f"{day}T{time_part}").replace(tzinfo=_SAST)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    asset: dict[str, Any] | None = None,
    sidecar: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """One sandbox row per compose channel (typically instagram + facebook)."""
    from _lib.jobs.layer5.image_draft_context import (  # noqa: PLC0415
        calendar_event_date_for_item,
        lodged_title_for_item,
    )
    from _lib.unified_inbox import _campaign_asset_for_id, _load_campaign_data  # noqa: PLC0415

    brand_id = validate_brand_id(brand_id)
    inbox_ref = str(inbox_item_id or "")
    side = sidecar if sidecar is not None else _load_draft_sidecar(asset_id)
    camp_asset = asset
    if camp_asset is None and asset_id:
        _cid, camp_asset = _campaign_asset_for_id(_load_campaign_data(), asset_id)

    title = lodged_title_for_item(
        brand_id,
        inbox_ref,
        sidecar_title=str(side.get("title") or ""),
        asset_name=str((camp_asset or {}).get("name") or ""),
    )
    if not title and lodged_title:
        title = lodged_title
    event_date = calendar_event_date_for_item(brand_id, inbox_ref)
    would_publish_at = _would_publish_at_from_event_date(event_date)
    provenance = _provenance_from_draft_asset(asset_id)

    items: list[dict[str, Any]] = []
    for platform in compose_publish_channels(brand_id):
        image_url = _composed_url_for_platform(
            platform=platform,
            asset=camp_asset,
            sidecar=side,
        )
        item = enqueue_item(
            brand_id=brand_id,
            platform=platform,
            caption_preview=caption_preview,
            inbox_item_id=inbox_item_id,
            human_approved=False,
            would_publish_at=would_publish_at,
            idempotency_key=f"qc-{asset_id}-{platform}",
            lodged_title=title or None,
            event_date=event_date or None,
            provenance=provenance,
            image_url=image_url,
        )
        items.append(item)
    if camp_asset and str(camp_asset.get("caption") or "").strip():
        sync_queue_rows_for_asset(
            brand_id=brand_id,
            asset_id=asset_id,
            asset=camp_asset,
            sidecar=side,
        )
    return items


def backfill_dual_channel_queue(*, brand: str | None = None) -> dict[str, Any]:
    """Ensure pending queue rows exist for every compose channel on QC-passed drafts."""
    from _lib.unified_inbox import _campaign_asset_for_id, _load_campaign_data  # noqa: PLC0415

    campaign_data = _load_campaign_data()
    sidecars = sorted((_data_dir() / "draft-assets").glob("*.json"))
    enqueued = 0
    skipped = 0
    brands_touched: set[str] = set()

    for path in sidecars:
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped += 1
            continue
        if not isinstance(sidecar, dict):
            skipped += 1
            continue
        brand_id = str(sidecar.get("brand_id") or "")
        if not brand_id:
            skipped += 1
            continue
        if brand and brand_id != brand:
            continue
        asset_id = str(sidecar.get("asset_id") or path.stem)
        qc = sidecar.get("qc") if isinstance(sidecar.get("qc"), dict) else {}
        if str(qc.get("verdict") or "").lower() in ("fail", "failed", "reject"):
            skipped += 1
            continue
        _cid, asset = _campaign_asset_for_id(campaign_data, asset_id)
        caption = str((asset or {}).get("caption") or "")
        if not caption.strip():
            skipped += 1
            continue
        inbox_item_id = str(sidecar.get("source_inbox_item_id") or "")
        rows = enqueue_for_intended_channels(
            brand_id=brand_id,
            caption_preview=caption,
            inbox_item_id=inbox_item_id,
            asset_id=asset_id,
            asset=asset,
            sidecar=sidecar,
        )
        sync_queue_rows_for_asset(
            brand_id=brand_id,
            asset_id=asset_id,
            caption=caption,
            asset=asset,
            sidecar=sidecar,
        )
        if rows:
            brands_touched.add(brand_id)
            enqueued += len(rows)

    return {
        "ok": True,
        "enqueued_rows": enqueued,
        "skipped_sidecars": skipped,
        "brands": sorted(brands_touched),
    }


def sync_queue_rows_for_asset(
    *,
    brand_id: str,
    asset_id: str,
    caption: str = "",
    asset: dict[str, Any] | None = None,
    sidecar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Align pending publish-queue rows with the approved draft (caption + composed URLs)."""
    from _lib.unified_inbox import _campaign_asset_for_id, _load_campaign_data  # noqa: PLC0415

    brand_id = validate_brand_id(brand_id)
    asset_id = str(asset_id or "").strip()
    if not asset_id:
        return {"ok": False, "error": "asset_id required", "updated": 0}

    side = sidecar if sidecar is not None else _load_draft_sidecar(asset_id)
    camp_asset = asset
    if camp_asset is None:
        _cid, camp_asset = _campaign_asset_for_id(_load_campaign_data(), asset_id)
    cap = (caption or str((camp_asset or {}).get("caption") or "")).strip()[:500]

    rows = _read_jsonl(_queue_path())
    updated = 0
    prefix = f"qc-{asset_id}-"
    for row in rows:
        if str(row.get("status") or "") != "pending":
            continue
        if validate_brand_id(str(row.get("brand_id") or "")) != brand_id:
            continue
        key = str(row.get("idempotency_key") or "")
        if not key.startswith(prefix):
            continue
        platform = str(row.get("platform") or "instagram")
        if cap:
            row["caption_preview"] = cap
        url = _composed_url_for_platform(platform=platform, asset=camp_asset, sidecar=side)
        if url:
            row["image_url"] = url
        updated += 1
    if updated:
        _rewrite_jsonl(_queue_path(), rows)
    return {"ok": True, "updated": updated, "asset_id": asset_id, "brand_id": brand_id}


def refresh_queue_row_from_draft(row: dict[str, Any]) -> dict[str, Any]:
    """Refresh one pending row from campaign-data + sidecar before dispatch."""
    from _lib.unified_inbox import asset_id_from_queue_row, _campaign_asset_for_id, _load_campaign_data  # noqa: PLC0415

    asset_id = asset_id_from_queue_row(row)
    if not asset_id:
        return row
    brand_id = str(row.get("brand_id") or "")
    try:
        brand_id = validate_brand_id(brand_id)
    except ValueError:
        return row
    side = _load_draft_sidecar(asset_id)
    _cid, asset = _campaign_asset_for_id(_load_campaign_data(), asset_id)
    cap = str((asset or {}).get("caption") or "").strip()
    if cap:
        row["caption_preview"] = cap[:500]
    platform = str(row.get("platform") or "instagram")
    url = _composed_url_for_platform(platform=platform, asset=asset, sidecar=side)
    if url:
        row["image_url"] = url
    return row


def preflight_queue_row(row: dict[str, Any]) -> tuple[bool, str]:
    """Gate live dispatch — caption + composed image must be present."""
    from _lib.unified_inbox import asset_id_from_queue_row, _campaign_asset_for_id, _load_campaign_data  # noqa: PLC0415

    if not str(row.get("caption_preview") or "").strip():
        return False, "empty caption_preview"
    if not str(row.get("image_url") or "").strip():
        return False, "missing image_url"
    asset_id = asset_id_from_queue_row(row)
    if not asset_id:
        return False, "unparseable idempotency_key"
    _cid, asset = _campaign_asset_for_id(_load_campaign_data(), asset_id)
    draft_cap = str((asset or {}).get("caption") or "").strip()
    queue_cap = str(row.get("caption_preview") or "").strip()
    if draft_cap and draft_cap[:500] != queue_cap:
        return False, "caption drift vs approved draft — run sync_queue_rows_for_asset"
    side = _load_draft_sidecar(asset_id)
    platform = str(row.get("platform") or "instagram")
    if not _composed_url_for_platform(platform=platform, asset=asset, sidecar=side):
        return False, f"no composed image for platform={platform}"
    return True, ""


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
    image_url: Optional[str] = None,
    image_path: Optional[str] = None,
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
    if image_url:
        item["image_url"] = str(image_url).strip()
    if image_path:
        item["image_path"] = str(image_path).strip()
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


def reschedule_item(
    idempotency_key: str,
    *,
    would_publish_at: str,
    event_date: str | None = None,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Update schedule on a pending sandbox row (does not approve)."""
    key = str(idempotency_key or "").strip()
    if not key:
        return None, "idempotency_key required"
    when = str(would_publish_at or "").strip()
    if not when:
        return None, "would_publish_at required"
    rows = _read_jsonl(_queue_path())
    found: Optional[dict[str, Any]] = None
    for row in rows:
        if row.get("idempotency_key") == key and row.get("status") == "pending":
            row["would_publish_at"] = when
            if event_date:
                row["event_date"] = str(event_date)[:32]
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


def row_is_due(would_publish_at: str | None, *, now: datetime | None = None) -> bool:
    """True when a queue row should be sent on this tick.

    Missing schedule means due. A future would_publish_at waits for a later tick.
    """
    raw = str(would_publish_at or "").strip()
    if not raw:
        return True
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        when = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return when <= current


def dispatch_pending() -> dict[str, Any]:
    """Process pending + human-approved rows whose schedule is due."""
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
        if not row_is_due(str(row.get("would_publish_at") or "")):
            skipped += 1
            updated_rows.append(row)
            continue
        row = refresh_queue_row_from_draft(row)
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
            row_url = str(row.get("image_url") or "").strip()
            row_path = str(row.get("image_path") or "").strip()
            if row_url:
                image_url = row_url
                image_path = row_path or None
            else:
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
