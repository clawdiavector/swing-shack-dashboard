"""L5 draft_assets job — assemble drafts from approved inbox queue rows."""

from __future__ import annotations

import json
import os
import re
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..errors import describe_exception
from ..layer1._io import atomic_write, read_json
from _lib.brand_validate import validate_brand_id

from .image_draft_context import calendar_title_for_item, image_url_for, primary_channel_for_item

_DRAFT_HEX_NAME = re.compile(r"^Draft [0-9a-f]{6}$", re.IGNORECASE)
_CAPTION_NAME_MAX = 72

CREATE_ACTIONS = frozenset({"draft_caption", "draft_image", "draft_gbp"})
SLOT_ACTIONS = frozenset({"fill_slot"})
PROCESS_ACTIONS = CREATE_ACTIONS | SLOT_ACTIONS
CAPTION_EST_USD = 0.002
IMAGE_EST_USD = 0.04
GBP_EST_USD = 0.0
VALID_IMAGE_SIZES = frozenset({"1024x1024", "1024x1792", "1792x1024"})
# image_gen_router.py:810-811 openai, :1013-1014 openrouter — already record spend.
_ROUTER_SELF_RECORDING_PROVIDERS = frozenset({"openai", "openrouter"})
_CAPTION_ONLY_REJECT_REASON = "caption-only incomplete post; operator clear 2026-09-23"
_CAPTION_SIDEcar_ACTIONS = frozenset({"draft_caption", "fill_slot"})
_CAPTION_QUEUE_ACTIONS = frozenset({"draft_caption", "fill_slot"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _exc_label(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return describe_exception(exc)
    frame = frames[-1]
    return f"{describe_exception(exc)} at {Path(frame.filename).name}:{frame.lineno} in {frame.name}"


def _record_error(exc: BaseException, *, context: dict[str, Any]) -> str:
    label = _exc_label(exc)
    try:
        atomic_write(
            "draft-assets/_diagnostics/last-error.json",
            {
                "schema": "campaign-os/draft-assets-diagnostic/v1",
                "ts": _utc_now_iso(),
                "error": label,
                "traceback": traceback.format_exc()[-8000:],
                "context": context,
            },
        )
    except Exception:  # noqa: BLE001
        pass
    return label


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _read_queue() -> list[dict[str, Any]]:
    doc = read_json("agent-queue.json")
    rows = doc.get("rows") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _write_queue(rows: list[dict[str, Any]]) -> None:
    atomic_write(
        "agent-queue.json",
        {
            "schema": "campaign-os/agent-queue/v1",
            "generated_at": _utc_now_iso(),
            "rows": rows,
        },
    )


def _parse_inbox_ref(payload_ref: str) -> Optional[str]:
    prefix = "inbox/"
    if not payload_ref.startswith(prefix):
        return None
    item_id = payload_ref[len(prefix) :].strip()
    return item_id or None


def _approved_calendar_records(brand_id: str) -> list[dict[str, Any]]:
    """canonical_records with dict guard — bad JSONL lines must not abort the job."""
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    try:
        records = canonical_records(brand_id)
    except Exception as exc:  # noqa: BLE001
        _record_error(exc, context={"brand": brand_id, "read": "canonical_records"})
        return []
    return [r for r in records if isinstance(r, dict)]


def _parse_slot_ref(payload_ref: str) -> Optional[tuple[str, str, str]]:
    prefix = "slot-planner.json#"
    if not payload_ref.startswith(prefix):
        return None
    parts = payload_ref[len(prefix) :].split("/")
    if len(parts) < 2:
        return None
    brand = parts[0].strip()
    slot_date = parts[1].strip()
    pillar_id = parts[2].strip() if len(parts) > 2 else ""
    if not brand or not slot_date:
        return None
    return brand, slot_date, pillar_id


def _record_dates(record: dict[str, Any]) -> set[str]:
    dates: set[str] = set()
    for key in (
        "event_date",
        "event_start",
        "event_window_start",
        "campaign_start",
        "campaign_end",
        "event_window_end",
    ):
        raw = record.get(key)
        if not raw or not isinstance(raw, str):
            continue
        dates.add(raw[:10])
    return dates


def _resolve_slot_calendar_item(
    brand_id: str,
    slot_date: str,
    pillar_id: str,
) -> Optional[str]:
    """Map a slot-planner ref to an approved calendar_candidate item id."""
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    for record in canonical_records(brand_id):
        if str(record.get("status") or "") != "approved":
            continue
        rec_pillar = str(record.get("pillar_id") or record.get("pillar") or "")
        if pillar_id and rec_pillar and rec_pillar != pillar_id:
            continue
        if slot_date not in _record_dates(record):
            continue
        cal_id = str(record.get("calendar_id") or record.get("event_key") or "")
        if not cal_id:
            continue
        return f"calendar_candidate:{brand_id}:{cal_id}"
    return None


def _is_inbox_item_approved(item_id: str) -> bool:
    """True when the originating L4 item has been approved (not pending)."""
    if ":" not in item_id:
        return False
    item_type, key = item_id.split(":", 1)
    if item_type == "proposal":
        brand_id, pid = key.split(":", 1)
        path = _data_dir() / "proposals" / "pending.jsonl"
        if not path.is_file():
            return False
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id") or row.get("proposal_id") or "")
            row_brand = str(row.get("brand_id") or row.get("brand") or "")
            if row_id == pid and row_brand == brand_id:
                return str(row.get("status") or "").lower() == "approved"
        return False

    if item_type == "calendar_candidate":
        brand_id, cal_id = key.split(":", 1)
        for record in _approved_calendar_records(brand_id):
            rec_cal = str(record.get("calendar_id") or "")
            rec_evt = str(record.get("event_key") or "")
            if cal_id not in (rec_cal, rec_evt):
                continue
            return str(record.get("status") or "") == "approved"
        return False

    return False


def _load_brands_registry() -> dict[str, Any]:
    path = _data_dir() / "brands.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            pass
    bundled = Path(__file__).resolve().parents[2] / "data" / "brands.json"
    if bundled.is_file():
        try:
            return json.loads(bundled.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            pass
    return {"brands": {}}


def _write_brands_registry(data: dict[str, Any]) -> None:
    path = _data_dir() / "brands.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _resolve_campaign_id(brand_id: str) -> str:
    """Return an owned campaign id for brand; register cos-drafts-* if needed."""
    from _lib.unified_inbox import _load_campaign_data, _write_campaign_data  # noqa: PLC0415

    reg = _load_brands_registry()
    brands = reg.setdefault("brands", {})
    brand_entry = brands.setdefault(brand_id, {"id": brand_id, "campaign_ids": []})
    cids = brand_entry.get("campaign_ids")
    if not isinstance(cids, list):
        cids = []
        brand_entry["campaign_ids"] = cids
    if cids:
        return str(cids[0])

    campaign_id = f"cos-drafts-{brand_id}"
    if campaign_id not in cids:
        cids.append(campaign_id)
    _write_brands_registry(reg)

    data = _load_campaign_data()
    campaigns = data.setdefault("campaigns", {})
    if campaign_id not in campaigns:
        campaigns[campaign_id] = {
            "identity": {"name": f"L5 drafts ({brand_id})", "brand": brand_id},
            "assets": {},
            "updatedAt": _utc_now_iso(),
        }
        _write_campaign_data(data)
    return campaign_id


def _caption_unavailable(result: dict[str, Any]) -> bool:
    obs = result.get("observability") if isinstance(result.get("observability"), dict) else {}
    if obs.get("provider") == "none":
        return True
    survivors = result.get("survivors") or []
    if survivors and isinstance(survivors[0], dict):
        body = str(survivors[0].get("body") or "")
        if body.startswith("[LLM unavailable"):
            return True
    return False


def _pick_caption(result: dict[str, Any]) -> str:
    survivors = result.get("survivors") or []
    if survivors and isinstance(survivors[0], dict):
        return str(survivors[0].get("body") or "").strip()
    return ""


def caption_first_line_name(caption: str, *, max_len: int = _CAPTION_NAME_MAX) -> str:
    """First line of caption trimmed for human draft titles."""
    line = (caption or "").split("\n", 1)[0].strip()
    line = re.sub(r"^[^\w#@]+", "", line, flags=re.UNICODE)
    if not line:
        return ""
    if len(line) <= max_len:
        return line
    cut = line[:max_len]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    trimmed = cut.rstrip()
    return f"{trimmed}…" if trimmed else line[:max_len]


def _draft_name(
    *,
    brand_id: str,
    item_id: str,
    caption: str,
    calendar_title: str = "",
) -> str:
    title = (calendar_title or "").strip()
    if not title:
        title = calendar_title_for_item(brand_id, item_id)
    if title:
        return title if len(title) <= _CAPTION_NAME_MAX else title[: _CAPTION_NAME_MAX - 1] + "…"
    return caption_first_line_name(caption)


def _backfill_draft_names(brand: str | None = None) -> int:
    """Rename assets still using Draft <hex> from sidecar/calendar/caption. Idempotent."""
    from _lib.unified_inbox import _load_campaign_data, _write_campaign_data  # noqa: PLC0415

    draft_dir = _data_dir() / "draft-assets"
    if not draft_dir.is_dir():
        return 0

    sidecars_by_asset: dict[str, dict[str, Any]] = {}
    for path in draft_dir.glob("*.json"):
        if path.parent.name != "draft-assets" or path.name.startswith("_"):
            continue
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(sidecar, dict):
            continue
        asset_id = str(sidecar.get("asset_id") or "")
        if asset_id:
            sidecars_by_asset[asset_id] = sidecar

    data = _load_campaign_data()
    campaigns = data.get("campaigns") if isinstance(data.get("campaigns"), dict) else {}
    updated = 0
    for campaign in campaigns.values():
        if not isinstance(campaign, dict):
            continue
        identity = campaign.get("identity") if isinstance(campaign.get("identity"), dict) else {}
        asset_brand = str(identity.get("brand") or "")
        if brand and asset_brand != brand:
            continue
        assets = campaign.get("assets") if isinstance(campaign.get("assets"), dict) else {}
        for asset_id, asset in assets.items():
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            if not _DRAFT_HEX_NAME.match(name):
                continue
            sidecar = sidecars_by_asset.get(str(asset_id), {})
            calendar = sidecar.get("calendar") if isinstance(sidecar.get("calendar"), dict) else {}
            cal_title = str(sidecar.get("title") or calendar.get("title") or "")
            item_id = str(sidecar.get("source_inbox_item_id") or "")
            caption = str(asset.get("caption") or "")
            new_name = _draft_name(
                brand_id=asset_brand,
                item_id=item_id,
                caption=caption,
                calendar_title=cal_title,
            )
            if new_name and new_name != name:
                asset["name"] = new_name
                updated += 1

    if updated:
        _write_campaign_data(data)
    return updated


def _write_draft(
    *,
    brand_id: str,
    caption: str,
    platform: str,
    source_item_id: str,
    sidecar: dict[str, Any],
    image_path: str | None = None,
    image_url: str | None = None,
) -> str:
    from _lib.unified_inbox import _load_campaign_data, _write_campaign_data  # noqa: PLC0415

    campaign_id = _resolve_campaign_id(brand_id)
    asset_id = f"draft-{uuid.uuid4().hex[:12]}"
    now = _utc_now_iso()

    data = _load_campaign_data()
    campaign = data.setdefault("campaigns", {}).setdefault(campaign_id, {})
    campaign.setdefault("identity", {"name": f"L5 drafts ({brand_id})", "brand": brand_id})
    assets = campaign.setdefault("assets", {})
    asset_row: dict[str, Any] = {
        "name": sidecar.get("title") or f"Draft {asset_id[-6:]}",
        "caption": caption,
        "approvalStatus": "draft",
        "platform": platform,
        "updatedAt": now,
        "draft_ref": f"draft-assets/{asset_id}.json",
    }
    if image_path:
        asset_row["image_path"] = image_path
    if image_url:
        asset_row["image_url"] = image_url
    assets[asset_id] = asset_row
    campaign["updatedAt"] = now
    _write_campaign_data(data)

    sidecar_path = _data_dir() / "draft-assets" / f"{asset_id}.json"
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_payload = {
        "schema": "campaign-os/draft-asset/v1",
        "asset_id": asset_id,
        "campaign_id": campaign_id,
        "brand_id": brand_id,
        "source_inbox_item_id": source_item_id,
        "created_at": now,
        **sidecar,
    }
    atomic_write(f"draft-assets/{asset_id}.json", sidecar_payload)
    return asset_id


def _process_caption_row(
    row: dict[str, Any],
    *,
    item_id: str,
    brand_id: str,
) -> tuple[Optional[str], Optional[str]]:
    from _lib import llm_spend  # noqa: PLC0415
    from _lib.p11_context_engine import run_caption_pipeline  # noqa: PLC0415

    allowed, reason = llm_spend.check("text", CAPTION_EST_USD)
    if not allowed:
        return None, "daily LLM spend cap reached" if "cap" in reason.lower() else reason

    result = run_caption_pipeline(
        {
            "brand_id": brand_id,
            "user_brief": f"Draft from approved inbox item {item_id}",
            "channel": "instagram",
            "n_survivors": 1,
            "n_candidates": 3,
        }
    )
    if not isinstance(result, dict) or not result.get("ok"):
        err = str(result.get("error") or "caption pipeline failed")
        if "key" in err.lower() or "auth" in err.lower():
            return None, "missing OPENAI_API_KEY"
        return None, err
    if _caption_unavailable(result):
        return None, "missing OPENAI_API_KEY"

    caption = _pick_caption(result)
    if not caption:
        return None, "caption pipeline returned no survivors"

    llm_spend.write_approval_receipt(
        route="job:draft_assets",
        estimate_usd=CAPTION_EST_USD,
        brand_id=brand_id,
    )
    llm_spend.record(
        CAPTION_EST_USD,
        route="job:draft_assets/caption",
        model=str((result.get("observability") or {}).get("model") or "gpt-4o-mini"),
        kind="text",
    )

    obs = result.get("observability") or {}
    cal_title = calendar_title_for_item(brand_id, item_id)
    draft_title = _draft_name(
        brand_id=brand_id,
        item_id=item_id,
        caption=caption,
        calendar_title=cal_title,
    )
    primary_platform = primary_channel_for_item(brand_id, item_id, fallback="instagram")
    asset_id = _write_draft(
        brand_id=brand_id,
        caption=caption,
        platform=primary_platform,
        source_item_id=item_id,
        sidecar={
            "action": "draft_caption",
            "route": "job:draft_assets/caption",
            "model": obs.get("model"),
            "provider": obs.get("provider"),
            "cost_estimate_usd": CAPTION_EST_USD,
            "queue_row_id": row.get("id"),
            "title": draft_title or cal_title or None,
        },
    )
    return asset_id, None


def _find_caption_draft_for_item(source_item_id: str) -> tuple[Optional[str], Optional[str]]:
    """Return (caption_asset_id, caption_text) when a caption draft exists."""
    draft_dir = _data_dir() / "draft-assets"
    if not draft_dir.is_dir():
        return None, None

    from _lib.unified_inbox import _load_campaign_data  # noqa: PLC0415

    for path in sorted(draft_dir.glob("*.json")):
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(sidecar, dict):
            continue
        if sidecar.get("source_inbox_item_id") != source_item_id:
            continue
        if sidecar.get("action") != "draft_caption":
            continue
        asset_id = str(sidecar.get("asset_id") or "")
        if not asset_id:
            continue
        data = _load_campaign_data()
        for campaign in (data.get("campaigns") or {}).values():
            asset = (campaign.get("assets") or {}).get(asset_id)
            if isinstance(asset, dict):
                caption = str(asset.get("caption") or "").strip()
                if caption:
                    return asset_id, caption
    return None, None


def _asset_has_persisted_image(asset: dict[str, Any]) -> bool:
    from _lib.unified_inbox import _asset_image_meta  # noqa: PLC0415

    image_path, image_url = _asset_image_meta(asset)
    path_s = str(image_path or "").strip()
    url_s = str(image_url or "").strip()
    if path_s:
        candidate = Path(path_s)
        if not candidate.is_file():
            alt = _data_dir() / path_s.lstrip("/")
            if alt.is_file():
                candidate = alt
        return candidate.is_file() and candidate.stat().st_size > 0
    return bool(url_s)


def _moment_has_image(brand_id: str, item_id: str) -> bool:
    draft_dir = _data_dir() / "draft-assets"
    if not draft_dir.is_dir():
        return False
    from _lib.unified_inbox import _load_campaign_data  # noqa: PLC0415

    data = _load_campaign_data()
    campaigns = data.get("campaigns") if isinstance(data.get("campaigns"), dict) else {}
    for path in sorted(draft_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(sidecar, dict):
            continue
        if sidecar.get("source_inbox_item_id") != item_id:
            continue
        asset_id = str(sidecar.get("asset_id") or "")
        if not asset_id:
            continue
        for campaign in campaigns.values():
            if not isinstance(campaign, dict):
                continue
            assets = campaign.get("assets")
            if not isinstance(assets, dict):
                continue
            asset = assets.get(asset_id)
            if isinstance(asset, dict) and _asset_has_persisted_image(asset):
                return True
    return False


def _sidecars_by_asset_id() -> dict[str, dict[str, Any]]:
    draft_dir = _data_dir() / "draft-assets"
    out: dict[str, dict[str, Any]] = {}
    if not draft_dir.is_dir():
        return out
    for path in draft_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(sidecar, dict):
            continue
        asset_id = str(sidecar.get("asset_id") or "")
        if asset_id:
            out[asset_id] = sidecar
    return out


def _campaign_ids_for_brand(brand: str | None) -> set[str] | None:
    if brand is None:
        return None
    reg = _load_brands_registry()
    brands = reg.get("brands") if isinstance(reg.get("brands"), dict) else {}
    entry = brands.get(brand) if isinstance(brands, dict) else None
    if not isinstance(entry, dict):
        return set()
    cids = entry.get("campaign_ids")
    if not isinstance(cids, list):
        return set()
    return {str(c) for c in cids if c}


def _reject_caption_only_drafts(brand: str | None = None) -> int:
    from _lib.unified_inbox import _asset_image_meta, _load_campaign_data, _write_campaign_data  # noqa: PLC0415

    sidecars = _sidecars_by_asset_id()
    data = _load_campaign_data()
    campaigns = data.get("campaigns") if isinstance(data.get("campaigns"), dict) else {}
    if not isinstance(campaigns, dict):
        return 0
    allowed = _campaign_ids_for_brand(brand)
    now = _utc_now_iso()
    rejected = 0
    for cid, campaign in campaigns.items():
        if not isinstance(campaign, dict):
            continue
        if allowed is not None and cid not in allowed:
            continue
        assets = campaign.get("assets")
        if not isinstance(assets, dict):
            continue
        for aid, asset in assets.items():
            if not isinstance(asset, dict):
                continue
            aps = str(asset.get("approvalStatus") or "draft").lower()
            if aps not in ("draft", "pending", ""):
                continue
            if str(asset.get("platform") or "") == "gbp":
                continue
            sidecar = sidecars.get(str(aid))
            if not sidecar:
                continue
            if str(sidecar.get("action") or "") not in _CAPTION_SIDEcar_ACTIONS:
                continue
            image_path, image_url = _asset_image_meta(asset)
            if image_path or image_url:
                continue
            asset["approvalStatus"] = "rejected"
            asset["rejectionReason"] = _CAPTION_ONLY_REJECT_REASON
            asset["updatedAt"] = now
            asset["reviewTs"] = now
            campaign["updatedAt"] = now
            rejected += 1
    if rejected:
        _write_campaign_data(data)
    return rejected


def _moment_rejected_caption_only(item_id: str) -> bool:
    from _lib.unified_inbox import _load_campaign_data  # noqa: PLC0415

    sidecars = _sidecars_by_asset_id()
    data = _load_campaign_data()
    campaigns = data.get("campaigns") if isinstance(data.get("campaigns"), dict) else {}
    for campaign in (campaigns or {}).values():
        if not isinstance(campaign, dict):
            continue
        assets = campaign.get("assets")
        if not isinstance(assets, dict):
            continue
        for aid, asset in assets.items():
            if not isinstance(asset, dict):
                continue
            sidecar = sidecars.get(str(aid))
            if not sidecar or sidecar.get("source_inbox_item_id") != item_id:
                continue
            if str(sidecar.get("action") or "") not in _CAPTION_SIDEcar_ACTIONS:
                continue
            if str(asset.get("approvalStatus") or "").lower() != "rejected":
                continue
            if asset.get("rejectionReason") == _CAPTION_ONLY_REJECT_REASON:
                return True
    return False


def _retire_orphan_queue_rows(rows: list[dict[str, Any]], brand: str | None) -> int:
    retired = 0
    moment_has_image_row: dict[str, bool] = {}
    for row in rows:
        if str(row.get("status") or "").lower() != "pending":
            continue
        if str(row.get("action") or "") == "draft_image":
            resolved = _resolve_row_moment(row)
            if resolved:
                moment_has_image_row[resolved[1]] = True

    for row in rows:
        if str(row.get("status") or "").lower() != "pending":
            continue
        action = str(row.get("action") or "")
        if action not in _CAPTION_QUEUE_ACTIONS:
            continue
        if brand is not None and str(row.get("brand") or "") != brand:
            continue
        resolved = _resolve_row_moment(row)
        if not resolved:
            continue
        item_id = resolved[1]
        if moment_has_image_row.get(item_id):
            continue
        if not _moment_rejected_caption_only(item_id):
            continue
        row["status"] = "skipped"
        row["note"] = "ticket-20260923-cos-complete-post-create caption-only retired"
        retired += 1
    return retired


def _resolve_row_moment(row: dict[str, Any]) -> Optional[tuple[str, str]]:
    brand_raw = row.get("brand")
    action = str(row.get("action") or "")
    try:
        brand_id = validate_brand_id(brand_raw)
    except ValueError:
        return None
    item_id: Optional[str] = None
    if action in SLOT_ACTIONS:
        slot = _parse_slot_ref(str(row.get("payload_ref") or ""))
        if not slot:
            return None
        slot_brand, slot_date, slot_pillar = slot
        if slot_brand != brand_id:
            return None
        item_id = _resolve_slot_calendar_item(brand_id, slot_date, slot_pillar)
    else:
        item_id = _parse_inbox_ref(str(row.get("payload_ref") or ""))
    if not item_id or not _is_inbox_item_approved(item_id):
        return None
    return brand_id, item_id


def _count_pending_rows(moment_items: list[tuple[tuple[str, str], list[tuple[dict[str, Any], str]]]], start: int) -> int:
    total = 0
    for _, rows_for_moment in moment_items[start:]:
        for row, _action in rows_for_moment:
            if str(row.get("status") or "").lower() == "pending":
                total += 1
    return total


def _apply_stop_error(
    err: str,
    *,
    errors: list[str],
    stop_cap: bool,
    stop_auth: bool,
) -> tuple[bool, bool]:
    if "daily LLM spend cap reached" in err:
        errors.append(err)
        return True, stop_auth
    if "missing OPENAI_API_KEY" in err:
        errors.append(err)
        return stop_cap, True
    errors.append(err)
    return stop_cap, stop_auth


def _process_image_row(
    row: dict[str, Any],
    *,
    item_id: str,
    brand_id: str,
) -> tuple[Optional[str], Optional[str]]:
    from _lib import llm_spend  # noqa: PLC0415
    from _lib.image_gen_router import ImageGenAuthError, generate_image_with_persistence  # noqa: PLC0415
    from _lib.jobs.layer5.image_draft_context import build_image_draft_context  # noqa: PLC0415

    ctx = build_image_draft_context(brand_id, item_id)
    size = ctx.aspect
    est = llm_spend.modelled_image_cost(size)
    allowed, reason = llm_spend.check("image", est)
    if not allowed:
        return None, "daily LLM spend cap reached" if "cap" in reason.lower() else reason

    from _lib.image_submit_quota import check_brand_image_submit, record_brand_image_submit  # noqa: PLC0415

    img_ok, img_reason = check_brand_image_submit(brand_id)
    if not img_ok:
        return None, img_reason

    output_base = str(_data_dir() / "draft-assets" / "images")
    gen_kwargs: dict[str, Any] = {
        "brand_id": brand_id,
        "prompt": ctx.job,
        "size": size,
        "output_base": output_base,
    }
    if ctx.refs:
        gen_kwargs["reference_dnas"] = ctx.refs
    if ctx.products:
        gen_kwargs["product_service_items"] = ctx.products

    llm_spend.write_approval_receipt(
        route="job:draft_assets",
        estimate_usd=est,
        brand_id=brand_id,
    )
    record_brand_image_submit(brand_id)

    try:
        result = generate_image_with_persistence(**gen_kwargs)
    except ImageGenAuthError:
        return None, "missing OPENAI_API_KEY"
    except Exception as exc:  # noqa: BLE001
        return None, _record_error(
            exc,
            context={"brand": brand_id, "item": item_id, "step": "generate_image_with_persistence"},
        )

    image_path = getattr(result, "saved_path", None) or getattr(result, "path", None)
    calendar = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
    title = str(calendar.get("title") or "")
    angle = str(calendar.get("angle") or "")
    caption_asset_id, caption_text = _find_caption_draft_for_item(item_id)
    if caption_text:
        caption = caption_text
    elif title and angle:
        caption = f"{title} — {angle}"
    elif title:
        caption = title
    else:
        caption = f"Image draft for {item_id}"

    cd = ctx.lineage.get("creative_director") if isinstance(ctx.lineage.get("creative_director"), dict) else {}
    model_routing = dict(cd.get("model_routing") or {})
    if cd.get("requirements"):
        model_routing["requirements"] = cd["requirements"]

    image_path_str = str(image_path) if image_path else None
    raw_bytes = getattr(result, "bytes", b"")
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raw_bytes = b""
    has_bytes = len(raw_bytes) > 0
    if image_path_str:
        try:
            has_bytes = Path(image_path_str).is_file() and Path(image_path_str).stat().st_size > 0
        except OSError:
            has_bytes = False
    image_url = image_url_for(brand_id, image_path_str) if has_bytes else None
    def _result_str(attr: str) -> str | None:
        val = getattr(result, attr, None)
        return val if isinstance(val, str) else None

    primary_platform = primary_channel_for_item(brand_id, item_id, fallback="instagram")
    pj_raw = getattr(result, "provider_job_id", None)
    provider_job_id = pj_raw.strip() if isinstance(pj_raw, str) and pj_raw.strip() else None
    sidecar_path = _result_str("saved_sidecar_path")
    if provider_job_id and not has_bytes:
        from . import image_jobs_state  # noqa: PLC0415

        row_fallback = row.get("image_retry_count")
        try:
            rc = max(0, int(row_fallback or 0))
        except (TypeError, ValueError):
            rc = 0
        image_jobs_state.upsert_submit(
            item_id,
            job_id=provider_job_id,
            brand=brand_id,
            size=size,
            est_usd=est,
            retry_count=rc,
        )
        row["status"] = "waiting"
        return None, None

    if not has_bytes:
        return None, None

    provider_name = str(getattr(result, "provider", "") or "")
    if provider_name not in _ROUTER_SELF_RECORDING_PROVIDERS:
        llm_spend.record(
            est,
            route="job:draft_assets/image",
            model=getattr(result, "model", None),
            kind="image",
            brand_id=brand_id,
        )

    asset_id = _write_draft(
        brand_id=brand_id,
        caption=caption,
        platform=primary_platform,
        source_item_id=item_id,
        image_path=image_path_str if has_bytes else None,
        image_url=image_url,
        sidecar={
            "action": "draft_image",
            "route": "job:draft_assets/image",
            "model": _result_str("model"),
            "provider": _result_str("provider"),
            "image_path": image_path_str if has_bytes else None,
            "image_url": image_url,
            "provider_job_id": provider_job_id,
            "image_size": size,
            "cost_estimate_usd": est,
            "queue_row_id": row.get("id"),
            "title": _draft_name(
                brand_id=brand_id,
                item_id=item_id,
                caption=caption,
                calendar_title=title,
            )
            or None,
            "prompt": ctx.job,
            "prompt_used": _result_str("prompt_used"),
            "sections": cd.get("sections") or [],
            "negative_prompt": cd.get("negative_prompt") or "",
            "model_routing": model_routing,
            "reference_dnas": ctx.lineage.get("reference_meta") or [],
            "product_service_items": ctx.lineage.get("product_meta") or [],
            "brand_bible": ctx.lineage.get("brand_bible") or {},
            "calendar": calendar,
            "router_sidecar_path": _result_str("saved_sidecar_path"),
            "caption_asset_id": caption_asset_id,
            "context_degraded": ctx.lineage.get("degraded") or [],
        },
    )
    return asset_id, None


def _process_gbp_row(
    row: dict[str, Any],
    *,
    item_id: str,
    brand_id: str,
) -> tuple[Optional[str], Optional[str]]:
    from _lib import gbp_daily_poster  # noqa: PLC0415

    plan = gbp_daily_poster.build_daily_plan(
        brand_id,
        days=1,
        posts_per_day=1,
        publish=False,
    )
    if not isinstance(plan, dict) or not plan.get("ok"):
        return None, str(plan.get("error") or "gbp plan failed")

    posts = plan.get("posts") or []
    body = ""
    if posts and isinstance(posts[0], dict):
        body = str(posts[0].get("body") or posts[0].get("caption") or "").strip()
    if not body:
        body = f"GBP draft for {brand_id} (dry-run plan {plan.get('plan_id') or ''})".strip()

    gbp_title = _draft_name(brand_id=brand_id, item_id=item_id, caption=body)
    asset_id = _write_draft(
        brand_id=brand_id,
        caption=body,
        platform="gbp",
        source_item_id=item_id,
        sidecar={
            "action": "draft_gbp",
            "route": "job:draft_assets/gbp",
            "gbp_plan_id": plan.get("plan_id"),
            "gbp_publish_skipped": (plan.get("publish") or {}).get("skipped"),
            "cost_estimate_usd": GBP_EST_USD,
            "queue_row_id": row.get("id"),
            "title": gbp_title or None,
        },
    )
    return asset_id, None


def run(brand: str | None = None) -> dict[str, Any]:
    """Process pending L5 queue rows into draft_asset inbox rows."""
    from _lib import llm_spend  # noqa: PLC0415

    allowed, reason = llm_spend.check("image", IMAGE_EST_USD)
    if not allowed and "cap" in reason.lower():
        return {
            "ok": True,
            "skipped_cap": True,
            "reason": "daily LLM spend cap reached",
            "drafted": 0,
            "skipped": 0,
        }

    drafted = 0
    skipped = 0
    rejected = 0
    errors: list[str] = []
    stop_cap = False
    stop_auth = False
    rows: list[dict[str, Any]] = []

    try:
        _backfill_draft_names(brand)
        rejected = _reject_caption_only_drafts(brand)
        rows = _read_queue()
        _retire_orphan_queue_rows(rows, brand)

        pending = [
            r
            for r in rows
            if str(r.get("status") or "").lower() == "pending"
            and str(r.get("action") or "") in PROCESS_ACTIONS
            and (brand is None or str(r.get("brand") or "") == brand)
        ]

        moments: dict[tuple[str, str], list[tuple[dict[str, Any], str]]] = {}
        for row in pending:
            resolved = _resolve_row_moment(row)
            if not resolved:
                skipped += 1
                continue
            key = resolved
            moments.setdefault(key, []).append((row, str(row.get("action") or "")))

        moment_items = list(moments.items())
        halted = False

        for idx, ((brand_id, item_id), rows_for_moment) in enumerate(moment_items):
            if halted or stop_cap or stop_auth:
                skipped += _count_pending_rows(moment_items, idx)
                break

            if _moment_has_image(brand_id, item_id):
                for row, action in rows_for_moment:
                    if action != "draft_gbp":
                        row["status"] = "done"
                continue

            for row, action in rows_for_moment:
                if action != "draft_gbp":
                    continue
                if stop_cap or stop_auth:
                    break
                try:
                    asset_id, err = _process_gbp_row(row, item_id=item_id, brand_id=brand_id)
                except Exception as exc:  # noqa: BLE001
                    skipped += 1
                    errors.append(
                        _record_error(
                            exc,
                            context={
                                "row_id": row.get("id"),
                                "action": row.get("action"),
                                "brand": row.get("brand"),
                                "payload_ref": row.get("payload_ref"),
                            },
                        )
                    )
                    continue
                if err:
                    stop_cap, stop_auth = _apply_stop_error(err, errors=errors, stop_cap=stop_cap, stop_auth=stop_auth)
                    skipped += 1
                    if stop_cap or stop_auth:
                        halted = True
                        skipped += _count_pending_rows(moment_items, idx)
                        break
                    continue
                if asset_id:
                    row["status"] = "done"
                    drafted += 1
                else:
                    skipped += 1

            if halted or stop_cap or stop_auth:
                break

            caption_rows = [(r, a) for r, a in rows_for_moment if a in _CAPTION_QUEUE_ACTIONS]
            image_rows = [(r, a) for r, a in rows_for_moment if a == "draft_image"]

            cap_asset_id, _cap_text = _find_caption_draft_for_item(item_id)
            if cap_asset_id is None and caption_rows:
                cap_row = caption_rows[0][0]
                try:
                    asset_id, err = _process_caption_row(cap_row, item_id=item_id, brand_id=brand_id)
                except Exception as exc:  # noqa: BLE001
                    skipped += 1
                    errors.append(
                        _record_error(
                            exc,
                            context={
                                "row_id": cap_row.get("id"),
                                "action": cap_row.get("action"),
                                "brand": cap_row.get("brand"),
                                "payload_ref": cap_row.get("payload_ref"),
                            },
                        )
                    )
                    asset_id, err = None, _exc_label(exc)
                if err:
                    stop_cap, stop_auth = _apply_stop_error(err, errors=errors, stop_cap=stop_cap, stop_auth=stop_auth)
                    skipped += 1
                    if stop_cap or stop_auth:
                        halted = True
                        skipped += _count_pending_rows(moment_items, idx)
                        break
                elif asset_id:
                    for row, action in rows_for_moment:
                        if action in _CAPTION_QUEUE_ACTIONS:
                            row["status"] = "done"
                    drafted += 1
                else:
                    skipped += 1

            if stop_cap or stop_auth:
                halted = True
                skipped += _count_pending_rows(moment_items, idx)
                break

            has_image_queue_row = bool(image_rows)
            if not _moment_has_image(brand_id, item_id) and has_image_queue_row:
                img_row = image_rows[0][0]
                if img_row is not None:
                    try:
                        asset_id, err = _process_image_row(img_row, item_id=item_id, brand_id=brand_id)
                    except Exception as exc:  # noqa: BLE001
                        skipped += 1
                        errors.append(
                            _record_error(
                                exc,
                                context={
                                    "row_id": img_row.get("id"),
                                    "action": img_row.get("action"),
                                    "brand": img_row.get("brand"),
                                    "payload_ref": img_row.get("payload_ref"),
                                },
                            )
                        )
                        asset_id, err = None, _exc_label(exc)
                    if err:
                        if "missing OPENAI_API_KEY" in err and drafted > 0:
                            errors.append(err)
                            skipped += 1
                        else:
                            stop_cap, stop_auth = _apply_stop_error(
                                err, errors=errors, stop_cap=stop_cap, stop_auth=stop_auth
                            )
                            skipped += 1
                            if stop_cap or stop_auth:
                                halted = True
                                skipped += _count_pending_rows(moment_items, idx)
                                break
                    elif asset_id:
                        image_rows[0][0]["status"] = "done"
                        drafted += 1
                    else:
                        skipped += 1

            if stop_cap or stop_auth:
                break

            if not _moment_has_image(brand_id, item_id):
                skipped += _count_pending_rows(moment_items, idx)
                halted = True
                break

            break

    except Exception as exc:  # noqa: BLE001
        label = _record_error(exc, context={"step": "run"})
        return {
            "ok": False,
            "error": label,
            "drafted": drafted,
            "skipped": skipped,
            "rejected": rejected,
        }
    finally:
        rejected += _reject_caption_only_drafts(brand)
        if rows:
            _write_queue(rows)

    if stop_auth:
        return {
            "ok": False,
            "error": "missing OPENAI_API_KEY",
            "drafted": drafted,
            "skipped": skipped,
            "rejected": rejected,
        }
    if stop_cap:
        return {
            "ok": False,
            "error": "daily LLM spend cap reached",
            "drafted": drafted,
            "skipped": skipped,
            "rejected": rejected,
        }
    if errors and drafted == 0:
        return {
            "ok": False,
            "error": errors[0],
            "drafted": drafted,
            "skipped": skipped,
            "rejected": rejected,
        }

    out: dict[str, Any] = {"ok": True, "drafted": drafted, "skipped": skipped, "rows": drafted}
    if rejected:
        out["rejected"] = rejected
    return out
