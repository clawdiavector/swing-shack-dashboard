"""Unified review inbox (L4) — calendar candidates, proposals, drafts, publish requests."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Optional

from _lib.jobs.layer1._io import read_json

SCHEMA = "campaign-os/unified-inbox/v1"
HUMAN_EDIT_SCHEMA = "campaign-os/human-edit-signal/v1"
SLA_STALE_HOURS = 24
ITEM_TYPES = frozenset({"calendar_candidate", "proposal", "draft_asset", "publish_request"})
_DRAFT_HEX_TITLE = re.compile(r"^Draft [0-9a-f]{6}$", re.IGNORECASE)
QC_KEY_PREFIX = "qc-"


def asset_id_from_queue_row(row: dict[str, Any]) -> str | None:
    """Parse qc-<asset_id>-<platform> idempotency keys (asset_id may contain hyphens)."""
    key = str(row.get("idempotency_key") or "")
    platform = str(row.get("platform") or "")
    if not key.startswith(QC_KEY_PREFIX) or not platform:
        return None
    suffix = f"-{platform}"
    if not key.endswith(suffix):
        return None
    asset_id = key[len(QC_KEY_PREFIX):-len(suffix)]
    return asset_id or None


def _campaign_asset_for_id(
    campaign_data: dict[str, Any],
    asset_id: str,
) -> tuple[str | None, dict[str, Any]]:
    campaigns = campaign_data.get("campaigns") if isinstance(campaign_data, dict) else None
    if isinstance(campaigns, dict):
        for cid, campaign in campaigns.items():
            if not isinstance(campaign, dict):
                continue
            assets = campaign.get("assets")
            if isinstance(assets, dict):
                maybe = assets.get(asset_id)
                if isinstance(maybe, dict):
                    return str(cid), maybe
    sidecar = _data_dir() / "draft-assets" / f"{asset_id}.json"
    if sidecar.is_file():
        try:
            doc = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                cid = str(doc.get("campaign_id") or "")
                if cid and isinstance(campaigns, dict):
                    campaign = campaigns.get(cid)
                    if isinstance(campaign, dict):
                        assets = campaign.get("assets")
                        if isinstance(assets, dict):
                            maybe = assets.get(asset_id)
                            if isinstance(maybe, dict):
                                return cid, maybe
        except (OSError, json.JSONDecodeError):
            pass
    return None, {}


def _is_caption_only_l5_draft(asset_id: str, asset: dict[str, Any]) -> bool:
    """True for pending L5 caption sidecars without persisted image bytes."""
    image_path, image_url = _asset_image_meta(asset)
    if image_path or image_url:
        return False
    sidecar_path = _data_dir() / "draft-assets" / f"{asset_id}.json"
    if not sidecar_path.is_file():
        return False
    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(sidecar, dict):
        return False
    return str(sidecar.get("action") or "") in ("draft_caption", "fill_slot")


def _resolve_image_path(asset: dict[str, Any]) -> Path | None:
    if not asset:
        return None
    raw = asset.get("image_path") or asset.get("filePath")
    if not raw:
        url = (
            asset.get("creative_url")
            or asset.get("image_url")
            or asset.get("visualUrl")
            or asset.get("imageUrl")
            or asset.get("mediaUrl")
        )
        raw = url
    path_s = str(raw or "").strip()
    if not path_s or path_s.startswith(("http://", "https://", "data:")):
        return None
    candidate = Path(path_s)
    if candidate.is_file():
        return candidate
    alt = _data_dir() / path_s.lstrip("/")
    if alt.is_file():
        return alt
    bundled = Path(__file__).resolve().parents[2] / path_s.lstrip("/")
    if bundled.is_file():
        return bundled
    return None


def _asset_image_file_size(asset: dict[str, Any]) -> int | None:
    path = _resolve_image_path(asset)
    if not path:
        return None
    try:
        return int(path.stat().st_size)
    except OSError:
        return None


def _asset_has_reviewable_image(asset: dict[str, Any]) -> bool:
    """True when this server can read non-empty image bytes from disk."""
    size = _asset_image_file_size(asset)
    return size is not None and size > 0


def _asset_image_local(asset: dict[str, Any]) -> Path | None:
    """Resolved local path when bytes exist on this server; None for remote-only refs."""
    if not _asset_has_reviewable_image(asset):
        return None
    return _resolve_image_path(asset)


def _asset_image_meta(asset: dict[str, Any]) -> tuple[Any, Any]:
    """Resolve image_path / image_url from campaign assets (camelCase or snake_case).

    Does not require the file to exist locally — remote URLs are valid visuals.
    """
    if not asset:
        return None, None
    image_url = (
        asset.get("creative_url")
        or asset.get("image_url")
        or asset.get("visualUrl")
        or asset.get("imageUrl")
        or asset.get("mediaUrl")
    )
    image_path = asset.get("image_path") or asset.get("filePath")
    if not image_url and image_path:
        image_url = image_path
    if not image_path and not image_url:
        return None, None
    return image_path, image_url


def _draft_item_title(row: dict[str, Any], asset: dict[str, Any], aid: str) -> str:
    title = str(row.get("name") or aid)
    if not _DRAFT_HEX_TITLE.match(title):
        return title
    from _lib.jobs.layer5.draft_assets import caption_first_line_name  # noqa: PLC0415

    caption = str(asset.get("caption") or row.get("caption") or "")
    fallback = caption_first_line_name(caption)
    return fallback or title


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _human_edits_path() -> Path:
    return _data_dir() / "human-edits.jsonl"


def _proposals_path() -> Path:
    return _data_dir() / "proposals" / "pending.jsonl"


def _parse_iso(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _age_hours(value: str | None, *, now: datetime) -> float | None:
    parsed = _parse_iso(value)
    if parsed is None:
        return None
    return (now - parsed).total_seconds() / 3600.0


def _sla_state(ts: str | None, *, now: datetime) -> str:
    age = _age_hours(ts, now=now)
    if age is None:
        return "ok"
    return "stale" if age >= SLA_STALE_HOURS else "ok"


def _item_id(item_type: str, key: str) -> str:
    return f"{item_type}:{key}"


def _parse_item_id(item_id: str) -> tuple[str, str]:
    if ":" not in item_id:
        raise ValueError("invalid inbox item id")
    item_type, key = item_id.split(":", 1)
    if item_type not in ITEM_TYPES:
        raise ValueError(f"unknown inbox item type '{item_type}'")
    return item_type, key


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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_campaign_data(data: dict[str, Any]) -> None:
    path = _data_dir() / "campaign-data.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _load_campaign_data() -> dict[str, Any]:
    path = _data_dir() / "campaign-data.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    bundled = Path(__file__).resolve().parents[1] / "campaign-data.json"
    if bundled.is_file():
        try:
            return json.loads(bundled.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    repo = Path(__file__).resolve().parents[2] / "data" / "campaign-data.json"
    if repo.is_file():
        try:
            return json.loads(repo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"campaigns": {}}


def record_human_edit(
    *,
    inbox_item_id: str,
    item_type: str,
    brand_id: str,
    editor: str,
    fields: dict[str, Any],
    note: str = "",
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a human_edit_signal row for L7."""
    row = {
        "schema": HUMAN_EDIT_SCHEMA,
        "ts": _utc_now_iso(),
        "editor": editor,
        "inbox_item_id": inbox_item_id,
        "item_type": item_type,
        "brand_id": brand_id,
        "fields": fields,
        "note": note,
    }
    if previous:
        row["previous"] = previous
    _append_jsonl(_human_edits_path(), row)
    return row


def _current_field_values(
    item_type: str,
    key: str,
    field_names: list[str] | Any,
) -> dict[str, Any]:
    """Capture current field values before an edit overwrites them."""
    names = list(field_names)
    previous: dict[str, Any] = {}
    if item_type == "draft_asset" and names:
        try:
            campaign_id, asset_id = key.split(":", 1)
        except ValueError:
            return previous
        data = _load_campaign_data()
        asset = ((data.get("campaigns") or {}).get(campaign_id) or {}).get("assets", {}).get(asset_id)
        if not isinstance(asset, dict):
            return previous
        for name in names:
            if name == "caption" and "caption" in asset:
                previous["caption"] = asset.get("caption")
            elif name == "title" and "name" in asset:
                previous["title"] = asset.get("name")
            elif name in asset:
                previous[name] = asset.get(name)
    if item_type == "calendar_candidate" and names:
        try:
            brand_id, cal_id = key.split(":", 1)
        except ValueError:
            return previous
        from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

        for record in canonical_records(brand_id):
            rid = str(record.get("calendar_id") or record.get("event_key") or "")
            if rid != cal_id:
                continue
            for name in names:
                if name == "event_date":
                    previous["event_date"] = _moment_go_live_date(record)
                elif name in record:
                    previous[name] = record.get(name)
            break
    return previous


def _actions_for_candidate(flags: list[str]) -> list[str]:
    actions = ["book", "edit", "reject"]
    if "no_date" not in flags:
        actions.insert(0, "lodge")
    return actions


def _calendar_record_angle(record: dict[str, Any]) -> str | None:
    angle = record.get("angle")
    if angle is not None and str(angle).strip():
        return str(angle).strip()
    suggested = record.get("suggested_angles")
    if isinstance(suggested, list):
        for item in suggested:
            if item is not None and str(item).strip():
                return str(item).strip()
    return None


def _calendar_items(*, brand: str | None, status: str, now: datetime) -> list[dict[str, Any]]:
    from _lib.marketing_calendar import VALID_BRAND_IDS, canonical_records  # noqa: PLC0415

    brands = [brand] if brand else list(VALID_BRAND_IDS)
    out: list[dict[str, Any]] = []
    for brand_id in brands:
        if brand_id not in VALID_BRAND_IDS:
            continue
        for record in canonical_records(brand_id):
            if record.get("status") != "candidate":
                continue
            ts = record.get("created_at") or record.get("last_verified")
            item_status = "pending"
            if status != "all" and item_status != status:
                continue
            cal_id = str(record.get("calendar_id") or record.get("event_key") or "")
            cand_state = "candidate"
            flags = _compute_flags(record, state=cand_state, now=now)
            go_live = _moment_go_live_date(record)
            from _lib.campaigns import meta_slim_from_record  # noqa: PLC0415

            meta_slim = meta_slim_from_record(record)
            out.append({
                "id": _item_id("calendar_candidate", f"{brand_id}:{cal_id}"),
                "type": "calendar_candidate",
                "brand_id": brand_id,
                "title": str(record.get("title") or record.get("event_key") or cal_id or "Calendar candidate"),
                "summary": str(record.get("angle") or record.get("pillar") or "")[:200],
                "evidence": [
                    {"source": "marketing-calendar", "ref": cal_id},
                ],
                "created_at": ts,
                "updated_at": ts,
                "status": item_status,
                "sla_state": "ok",
                "actions": _actions_for_candidate(flags),
                "meta_slim": meta_slim,
                "meta": {
                    "calendar_id": cal_id,
                    "pillar": record.get("pillar"),
                    "angle": _calendar_record_angle(record),
                    "relevance_reason": record.get("relevance_reason"),
                    "event_start": record.get("event_start") or record.get("event_window_start"),
                    "event_date": go_live,
                    "primary_channel": record.get("primary_channel"),
                    "state": cand_state,
                    "flags": flags,
                    "source_type": record.get("source_type"),
                    "created_by": record.get("created_by"),
                    "meta_slim": meta_slim,
                },
            })
    return out


def _proposal_items(*, brand: str | None, status: str, now: datetime) -> list[dict[str, Any]]:
    rows = _read_jsonl(_proposals_path())
    out: list[dict[str, Any]] = []
    for row in rows:
        row_status = str(row.get("status") or "pending").lower()
        if row_status not in ("pending", ""):
            continue
        brand_id = str(row.get("brand_id") or row.get("brand") or "")
        if brand and brand_id and brand_id != brand:
            continue
        if status != "all" and row_status != status:
            continue
        pid = str(row.get("id") or row.get("proposal_id") or "")
        if not pid:
            continue
        ts = row.get("created_at") or row.get("updated_at")
        evidence = row.get("evidence") or []
        if not isinstance(evidence, list):
            evidence = []
        out.append({
            "id": _item_id("proposal", f"{brand_id}:{pid}"),
            "type": "proposal",
            "brand_id": brand_id,
            "title": str(row.get("title") or row.get("headline") or pid),
            "summary": str(row.get("summary") or row.get("rationale") or "")[:240],
            "evidence": evidence,
            "created_at": ts,
            "updated_at": row.get("updated_at") or ts,
            "status": "pending",
            "sla_state": _sla_state(str(ts) if ts else None, now=now),
            "actions": ["approve", "edit", "reject"],
            "meta": {"proposal_id": pid},
        })
    return out


_DRAFT_INBOX_TOTALS: dict[str, int] = {"approved_total": 0, "rejected_total": 0}


def _sibling_draft_has_composed_gbp(source_item_id: str, *, exclude_asset_id: str) -> bool:
    """True when another draft for the same moment already carries composed.gbp."""
    if not source_item_id:
        return False
    draft_dir = _data_dir() / "draft-assets"
    if not draft_dir.is_dir():
        return False
    for path in draft_dir.glob("*.json"):
        if path.name.endswith(".brief.json") or path.name.endswith(".qc.json"):
            continue
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(sidecar, dict):
            continue
        if str(sidecar.get("source_inbox_item_id") or "") != source_item_id:
            continue
        if str(sidecar.get("asset_id") or path.stem) == exclude_asset_id:
            continue
        composed = sidecar.get("composed")
        if isinstance(composed, dict) and composed.get("gbp"):
            return True
    return False


def _draft_items(*, brand: str | None, status: str, now: datetime) -> list[dict[str, Any]]:
    from _lib import intelligence  # noqa: PLC0415

    if brand:
        intelligence.set_request_brand(brand)
    inbox = intelligence.review_inbox()
    _DRAFT_INBOX_TOTALS["approved_total"] = int(inbox.get("approved_total") or len(inbox.get("approved") or []))
    _DRAFT_INBOX_TOTALS["rejected_total"] = int(inbox.get("rejected_total") or len(inbox.get("rejected") or []))
    campaign_data = _load_campaign_data()
    campaigns = campaign_data.get("campaigns") if isinstance(campaign_data, dict) else {}
    if not isinstance(campaigns, dict):
        campaigns = {}
    out: list[dict[str, Any]] = []
    buckets = {
        "pending": inbox.get("pending") or [],
        "approved": inbox.get("approved") or [],
        "rejected": inbox.get("rejected") or [],
    }
    for bucket_name, rows in buckets.items():
        if status != "all" and bucket_name != status:
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            cid = str(row.get("campaignId") or "")
            aid = str(row.get("assetId") or "")
            brand_id = str(row.get("brand") or brand or "")
            ts = row.get("updatedAt")
            item_status = bucket_name if bucket_name != "pending" else "pending"
            asset: dict[str, Any] = {}
            campaign = campaigns.get(cid)
            if isinstance(campaign, dict):
                assets = campaign.get("assets")
                if isinstance(assets, dict):
                    maybe_asset = assets.get(aid)
                    if isinstance(maybe_asset, dict):
                        asset = maybe_asset
            full_caption = str(asset.get("caption") or row.get("caption") or "")
            image_path, image_url = _asset_image_meta(asset)
            platform = str(row.get("platform") or asset.get("platform") or "")
            if bucket_name == "pending" and platform != "gbp" and _is_caption_only_l5_draft(aid, asset):
                continue
            sidecar_path = _data_dir() / "draft-assets" / f"{aid}.json"
            sidecar: dict[str, Any] = {}
            if sidecar_path.is_file():
                try:
                    loaded = json.loads(sidecar_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        sidecar = loaded
                except (OSError, json.JSONDecodeError):
                    pass
            source_item = str(sidecar.get("source_inbox_item_id") or "")
            if platform == "gbp" and _sibling_draft_has_composed_gbp(source_item, exclude_asset_id=aid):
                continue
            from _lib.jobs.layer5.image_draft_context import (  # noqa: PLC0415
                calendar_event_date_for_item,
                lodged_title_for_item,
                primary_channel_for_item,
            )

            primary_channel = primary_channel_for_item(
                brand_id,
                source_item,
                fallback=platform or "instagram",
            )
            lodged_title = lodged_title_for_item(
                brand_id,
                source_item,
                sidecar_title=str(sidecar.get("title") or ""),
                asset_name=str(asset.get("name") or row.get("name") or ""),
            )
            event_date = calendar_event_date_for_item(brand_id, source_item)
            display_title = lodged_title or _draft_item_title(row, asset, aid)
            out.append({
                "id": _item_id("draft_asset", f"{cid}:{aid}"),
                "type": "draft_asset",
                "brand_id": brand_id,
                "title": display_title,
                "summary": full_caption[:240],
                "evidence": [{"source": "review_inbox", "ref": f"{cid}/{aid}"}],
                "created_at": ts,
                "updated_at": ts,
                "status": item_status,
                "sla_state": _sla_state(str(ts) if ts else None, now=now),
                "actions": ["approve", "edit", "reject"] if item_status == "pending" else ["edit"],
                "meta": {
                    "campaign_id": cid,
                    "asset_id": aid,
                    "platform": primary_channel or row.get("platform"),
                    "primary_channel": primary_channel,
                    "event_date": event_date or None,
                    "approval_status": row.get("approvalStatus"),
                    "caption": full_caption,
                    "image_path": image_path,
                    "image_url": image_url,
                },
            })
            meta = out[-1]["meta"]
            if sidecar.get("photo_candidates"):
                meta["photo_candidates"] = sidecar["photo_candidates"]
            if sidecar.get("qc"):
                meta["qc"] = sidecar["qc"]
            if sidecar.get("composed"):
                meta["composed"] = sidecar["composed"]
            if sidecar.get("archetype"):
                meta["archetype"] = sidecar["archetype"]
            if sidecar.get("sections") or sidecar.get("negative_prompt"):
                meta["brief"] = {
                    "sections": sidecar.get("sections") or [],
                    "negative_prompt": sidecar.get("negative_prompt") or "",
                    "platform_spec": sidecar.get("platform_spec") or {},
                    "brief_ref": f"draft-assets/{aid}.brief.json",
                }
            ref_meta = sidecar.get("reference_dnas")
            if isinstance(ref_meta, list) and ref_meta:
                first = ref_meta[0] if isinstance(ref_meta[0], dict) else {}
                meta["reference_used"] = {
                    "ref_id": first.get("ref_id"),
                    "url": first.get("url"),
                    "source": first.get("source"),
                    "platform": first.get("platform"),
                    "selected_because": first.get("selected_because"),
                }
            composed = meta.get("composed")
            if isinstance(composed, dict) and meta.get("primary_channel") in composed:
                meta["image_url"] = composed[meta["primary_channel"]]
    return out


def _publish_request_items(*, brand: str | None, status: str, now: datetime) -> list[dict[str, Any]]:
    from _lib import publish_sandbox  # noqa: PLC0415

    queue_path = publish_sandbox._queue_path()  # noqa: SLF001
    rows = _read_jsonl(queue_path)
    campaign_data = _load_campaign_data()
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("status") or "") != "pending":
            continue
        brand_id = str(row.get("brand_id") or "")
        if brand and brand_id and brand_id != brand:
            continue
        key = str(row.get("idempotency_key") or row.get("queue_id") or "")
        if not key:
            continue
        ts = row.get("created_at")
        blocked = not row.get("human_approved")
        item_status = "pending"
        if status != "all" and item_status != status:
            continue
        lodged_title = str(row.get("lodged_title") or "").strip()
        inbox_ref = str(row.get("inbox_item_id") or "")
        if not lodged_title and inbox_ref:
            from _lib.jobs.layer5.image_draft_context import lodged_title_for_item  # noqa: PLC0415

            lodged_title = lodged_title_for_item(brand_id, inbox_ref)
        platform = str(row.get("platform") or "post")
        title = lodged_title or str(row.get("caption_preview") or "")[:120] or key
        event_date = str(row.get("event_date") or "").strip()
        goes_out = row.get("would_publish_at") or (
            f"{event_date}T09:00:00Z" if event_date and "T" not in event_date else event_date
        )
        out.append({
            "id": _item_id("publish_request", key),
            "type": "publish_request",
            "brand_id": brand_id,
            "title": title,
            "summary": str(row.get("caption_preview") or "")[:240],
            "evidence": [{"source": "publish-sandbox", "ref": key}],
            "created_at": ts,
            "updated_at": row.get("human_approved_at") or ts,
            "status": item_status,
            "sla_state": _sla_state(str(ts) if ts else None, now=now),
            "blocked_missing_oauth": blocked,
            "actions": ["approve", "edit", "reject"],
            "meta": {
                **_publish_request_meta(row, key, campaign_data),
                "platform": platform,
                "primary_channel": platform,
                "event_date": event_date or None,
                "goes_out_at": goes_out or None,
            },
        })
    return out


def _publish_request_meta(
    row: dict[str, Any],
    key: str,
    campaign_data: dict[str, Any],
) -> dict[str, Any]:
    asset_id = asset_id_from_queue_row(row)
    campaign_id: str | None = None
    image_path: Any = None
    image_url: Any = None
    if asset_id:
        campaign_id, asset = _campaign_asset_for_id(campaign_data, asset_id)
        image_path, image_url = _asset_image_meta(asset)
    return {
        "idempotency_key": key,
        "human_approved": bool(row.get("human_approved")),
        "channel": row.get("channel"),
        "asset_id": asset_id,
        "campaign_id": campaign_id,
        "inbox_item_id": row.get("inbox_item_id"),
        "image_path": image_path,
        "image_url": image_url,
    }


def list_items(
    *,
    brand: str | None = None,
    status: str = "pending",
    item_type: str | None = None,
) -> dict[str, Any]:
    """Build unified inbox list payload."""
    now = datetime.now(timezone.utc)
    _DRAFT_INBOX_TOTALS["approved_total"] = 0
    _DRAFT_INBOX_TOTALS["rejected_total"] = 0
    status = (status or "pending").lower()
    if status not in ("pending", "approved", "rejected", "all"):
        status = "pending"

    collectors = {
        "calendar_candidate": _calendar_items,
        "proposal": _proposal_items,
        "draft_asset": _draft_items,
        "publish_request": _publish_request_items,
    }
    items: list[dict[str, Any]] = []
    if item_type and item_type in collectors:
        items.extend(collectors[item_type](brand=brand, status=status, now=now))
    else:
        for fn in collectors.values():
            items.extend(fn(brand=brand, status=status, now=now))

    def _created_desc_key(item: dict[str, Any]) -> datetime:
        parsed = _parse_iso(item.get("created_at"))
        if parsed is not None:
            return parsed
        return datetime.min.replace(tzinfo=timezone.utc)

    items.sort(key=_created_desc_key, reverse=True)

    def _pending_stale(item: dict[str, Any]) -> bool:
        if item.get("status") != "pending":
            return False
        if item.get("type") == "calendar_candidate":
            flags = (item.get("meta") or {}).get("flags") or []
            return "stale" in flags
        return item.get("sla_state") == "stale"

    stale = sum(1 for i in items if _pending_stale(i))
    approved_on_shelf = 0
    if status in ("approved", "all"):
        draft_approved = _DRAFT_INBOX_TOTALS.get("approved_total", 0)
        non_draft_approved = sum(
            1 for i in items if i.get("status") == "approved" and i.get("type") != "draft_asset"
        )
        if item_type == "draft_asset":
            approved_on_shelf = draft_approved
        elif item_type is None:
            approved_on_shelf = non_draft_approved + draft_approved
        else:
            approved_on_shelf = sum(1 for i in items if i.get("status") == "approved")
    return {
        "schema": SCHEMA,
        "generated_at": _utc_now_iso(),
        "brand": brand,
        "status_filter": status,
        "type_filter": item_type,
        "summary": {
            "total": len(items),
            "pending": sum(1 for i in items if i.get("status") == "pending"),
            "stale": stale,
        },
        "counts": {
            "pending": sum(1 for i in items if i.get("status") == "pending"),
            "stale": stale,
            "approved_today": _approved_today_from_edits(),
            "approved": approved_on_shelf,
        },
        "items": items,
    }


_WEEK_MOMENT_STATUSES = frozenset({"approved", "candidate", "active", "completed"})
_WEEK_TZ = ZoneInfo("Africa/Johannesburg")
_STAGE_ORDER = (
    "booked",
    "caption",
    "image",
    "in_review",
    "approved",
    "queued",
    "released",
    "posted",
)
_STALE_CANDIDATE_DAYS = 7
UNDATED_CAP = 50
POST_STATES = frozenset(
    {
        "candidate",
        "booked",
        "drafting",
        "needs_fix",
        "draft_ready",
        "scheduled",
        "released",
        "posted",
    }
)


def _calendar_id_from_inbox_ref(inbox_item_id: str) -> str | None:
    """Parse calendar_id from calendar_candidate:<brand>:<calendar_id>."""
    if not inbox_item_id.startswith("calendar_candidate:"):
        return None
    parts = inbox_item_id.split(":", 2)
    if len(parts) < 3:
        return None
    cal_id = parts[2].strip()
    return cal_id or None


def _moment_go_live_date(record: dict[str, Any]) -> str | None:
    for key in ("event_date", "event_start", "event_window_start"):
        raw = record.get(key)
        if raw and isinstance(raw, str):
            return raw[:10]
    return None


def _index_draft_sidecars(*, brand_id: str) -> tuple[dict[str, dict[str, Any]], int]:
    """Map calendar_id → draft join row; return (index, orphan_count)."""
    sidecar_dir = _data_dir() / "draft-assets"
    campaign_data = _load_campaign_data()
    by_cal: dict[str, dict[str, Any]] = {}
    orphans = 0
    if not sidecar_dir.is_dir():
        return by_cal, orphans
    for path in sidecar_dir.glob("*.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        if str(doc.get("brand_id") or "") not in ("", brand_id):
            if doc.get("brand_id") and str(doc.get("brand_id")) != brand_id:
                continue
        asset_id = str(doc.get("asset_id") or path.stem)
        campaign_id = str(doc.get("campaign_id") or "")
        source = str(doc.get("source_inbox_item_id") or "")
        cal_id = _calendar_id_from_inbox_ref(source)
        if not cal_id:
            orphans += 1
            continue
        cid, asset = _campaign_asset_for_id(campaign_data, asset_id)
        if not cid:
            cid = campaign_id
        approval = str(asset.get("approvalStatus") or asset.get("approval_status") or "draft").lower()
        bucket = "approved" if approval == "approved" else "pending"
        caption = str(asset.get("caption") or "")
        image_path, image_url = _asset_image_meta(asset)
        inbox_item_id = _item_id("draft_asset", f"{cid}:{asset_id}")
        row = {
            "calendar_id": cal_id,
            "asset_id": asset_id,
            "campaign_id": cid,
            "inbox_item_id": inbox_item_id,
            "caption": caption,
            "image_path": image_path,
            "image_url": image_url,
            "draft_bucket": bucket,
            "updated_at": asset.get("updatedAt") or doc.get("created_at"),
        }
        prev = by_cal.get(cal_id)
        if prev is None or str(row.get("updated_at") or "") >= str(prev.get("updated_at") or ""):
            by_cal[cal_id] = row
    return by_cal, orphans


def _index_publish_by_cal(
    *, brand_id: str
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    from _lib import publish_sandbox  # noqa: PLC0415

    queue_by: dict[str, list[dict[str, Any]]] = {}
    for row in publish_sandbox.queue_rows_for_brand(brand_id):
        inbox_ref = str(row.get("inbox_item_id") or "")
        cal_id = _calendar_id_from_inbox_ref(inbox_ref)
        if not cal_id:
            continue
        queue_by.setdefault(cal_id, []).append(
            {
                "platform": row.get("platform"),
                "idempotency_key": row.get("idempotency_key") or row.get("queue_id"),
                "inbox_item_id": inbox_ref,
                "status": row.get("status"),
                "human_approved": bool(row.get("human_approved")),
            }
        )
    receipts_by: dict[str, list[dict[str, Any]]] = {}
    for rec in publish_sandbox.receipts_for_brand(brand_id):
        inbox_ref = str(rec.get("inbox_item_id") or "")
        cal_id = _calendar_id_from_inbox_ref(inbox_ref)
        if not cal_id:
            continue
        receipts_by.setdefault(cal_id, []).append(
            {
                "platform": rec.get("platform"),
                "sandbox_post_id": rec.get("sandbox_post_id"),
                "dispatched_at": rec.get("dispatched_at"),
                "inbox_item_id": inbox_ref,
            }
        )
    return queue_by, receipts_by


def _stale_candidate_days() -> int:
    raw = os.environ.get("CAMPAIGN_OS_STALE_CANDIDATE_DAYS", str(_STALE_CANDIDATE_DAYS))
    try:
        return max(1, int(raw))
    except ValueError:
        return _STALE_CANDIDATE_DAYS


def _is_holiday_record(record: dict[str, Any]) -> bool:
    if str(record.get("created_by") or "") == "holiday_inject":
        return True
    return str(record.get("source_type") or "") in ("deterministic", "holiday")


def _inbox_ref_for_cal(*, brand_id: str, cal_id: str) -> str:
    return f"calendar_candidate:{brand_id}:{cal_id}"


def _rollup_stages(
    *,
    has_moment: bool,
    draft: dict[str, Any] | None,
    sandbox_rows: list[dict[str, Any]],
    receipts: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, bool], str]:
    receipts = receipts or []
    stages: dict[str, bool] = {
        "booked": has_moment,
        "caption": False,
        "image": False,
        "in_review": False,
        "approved": False,
        "queued": bool(sandbox_rows),
        "released": any(bool(r.get("human_approved")) for r in sandbox_rows),
        "posted": bool(receipts),
    }
    if draft:
        if draft.get("caption", "").strip():
            stages["caption"] = True
        if draft.get("image_path") or draft.get("image_url"):
            stages["image"] = True
        has_reviewable_image = bool(draft.get("image_path") or draft.get("image_url"))
        if draft.get("draft_bucket") == "pending" and has_reviewable_image:
            stages["in_review"] = True
        if draft.get("draft_bucket") == "approved":
            stages["approved"] = True
            stages["in_review"] = False
    stage = "booked"
    for name in _STAGE_ORDER:
        if stages.get(name):
            stage = name
    return stages, stage


@dataclass(frozen=True)
class PostIndex:
    brand_id: str
    drafts: dict[str, dict[str, Any]]
    queue: dict[str, list[dict[str, Any]]]
    receipts: dict[str, list[dict[str, Any]]]
    work_orders: dict[str, list[dict[str, Any]]]
    image_jobs: dict[str, dict[str, Any]]
    sidecar_orphans: int


def build_post_index(*, brand_id: str) -> PostIndex:
    from _lib import ops_agents  # noqa: PLC0415
    from _lib.jobs.layer5 import image_jobs_state  # noqa: PLC0415

    drafts, orphans = _index_draft_sidecars(brand_id=brand_id)
    queue_by, receipts_by = _index_publish_by_cal(brand_id=brand_id)
    work_by_cal: dict[str, list[dict[str, Any]]] = {}
    for row in ops_agents.rows_for_brand(_data_dir(), brand_id):
        if str(row.get("layer") or "") != "L5":
            continue
        pref = str(row.get("payload_ref") or "")
        if not pref.startswith("inbox/"):
            continue
        inbox_id = pref[len("inbox/") :]
        cal_id = _calendar_id_from_inbox_ref(inbox_id)
        if not cal_id:
            continue
        work_by_cal.setdefault(cal_id, []).append(dict(row))

    jobs_raw = image_jobs_state.load_doc().get("jobs")
    image_jobs: dict[str, dict[str, Any]] = {}
    if isinstance(jobs_raw, dict):
        for key, entry in jobs_raw.items():
            if isinstance(entry, dict):
                image_jobs[str(key)] = entry

    return PostIndex(
        brand_id=brand_id,
        drafts=drafts,
        queue=queue_by,
        receipts=receipts_by,
        work_orders=work_by_cal,
        image_jobs=image_jobs,
        sidecar_orphans=orphans,
    )


def _draft_has_image(draft: dict[str, Any] | None) -> bool:
    if not draft:
        return False
    return bool(draft.get("image_path") or draft.get("image_url"))


def _retry_count_for_inbox(index: PostIndex, inbox_item_id: str) -> int:
    entry = index.image_jobs.get(inbox_item_id)
    if not isinstance(entry, dict):
        return 0
    try:
        return int(entry.get("retry_count") or 0)
    except (TypeError, ValueError):
        return 0


def _image_job_failed(index: PostIndex, inbox_item_id: str) -> bool:
    entry = index.image_jobs.get(inbox_item_id)
    if not isinstance(entry, dict):
        return False
    return str(entry.get("last_status") or "") == "failed"


def _work_orders_active(work_rows: list[dict[str, Any]]) -> bool:
    for row in work_rows:
        status = str(row.get("status") or "")
        if status in {"pending", "waiting"}:
            return True
    return False


def _work_orders_done_no_image(
    work_rows: list[dict[str, Any]], *, has_image: bool
) -> bool:
    if has_image:
        return False
    return any(str(row.get("status") or "") == "done" for row in work_rows)


def _derive_post_state(
    record: dict[str, Any],
    *,
    index: PostIndex,
    draft: dict[str, Any] | None,
    queue_rows: list[dict[str, Any]],
    receipts: list[dict[str, Any]],
    work_rows: list[dict[str, Any]],
    inbox_item_id: str,
) -> tuple[str, str | None]:
    from _lib.jobs.layer5.retry_failed_images import MAX_IMAGE_RETRIES  # noqa: PLC0415

    cal_status = str(record.get("status") or "")
    has_image = _draft_has_image(draft)
    caption_ok = bool((draft or {}).get("caption", "").strip())
    retry_count = _retry_count_for_inbox(index, inbox_item_id)

    if receipts:
        return "posted", None
    if any(bool(r.get("human_approved")) for r in queue_rows):
        return "released", None
    if draft and draft.get("draft_bucket") == "approved":
        return "scheduled", None
    if draft and caption_ok and has_image:
        return "draft_ready", None
    if _image_job_failed(index, inbox_item_id):
        return "needs_fix", "image job failed"
    if _work_orders_done_no_image(work_rows, has_image=has_image) and retry_count >= MAX_IMAGE_RETRIES:
        return "needs_fix", "no image"
    if draft and caption_ok and not has_image:
        return "needs_fix", "no image"
    if _work_orders_active(work_rows):
        return "drafting", None
    if _work_orders_done_no_image(work_rows, has_image=has_image) and retry_count < MAX_IMAGE_RETRIES:
        return "drafting", None
    if cal_status in {"approved", "active", "completed"}:
        return "booked", None
    return "candidate", None


def _compute_flags(
    record: dict[str, Any],
    *,
    state: str,
    now: datetime,
) -> list[str]:
    flags: list[str] = []
    if not _moment_go_live_date(record):
        flags.append("no_date")
    if not str(record.get("primary_channel") or "").strip():
        flags.append("no_channel")
    if _is_holiday_record(record):
        flags.append("holiday")
    if str(record.get("source_type") or "") == "operator":
        flags.append("operator")
    if state == "candidate" and "holiday" not in flags:
        ts = record.get("created_at") or record.get("last_verified")
        age = _age_hours(str(ts) if ts else None, now=now)
        if age is not None and age >= 24.0 * _stale_candidate_days():
            flags.append("stale")
    return flags


def _next_action_for_state(state: str, *, needs_fix_reason: str | None) -> str:
    if state == "needs_fix" and needs_fix_reason:
        return needs_fix_reason
    mapping = {
        "candidate": "Lodge or book",
        "booked": "Waiting on caption",
        "drafting": "Draft in progress",
        "needs_fix": "Needs fix",
        "draft_ready": "Ready to review",
        "scheduled": "On the shelf",
        "released": "Waiting to go out",
        "posted": "Posted",
    }
    return mapping.get(state, "—")


def post_state(
    record: dict[str, Any],
    *,
    index: PostIndex,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Single calendar moment joined to drafts, sandbox, and work orders."""
    now = now or datetime.now(timezone.utc)
    cal_id = str(record.get("calendar_id") or record.get("event_key") or "")
    draft = index.drafts.get(cal_id)
    queue_rows = index.queue.get(cal_id, [])
    receipts = index.receipts.get(cal_id, [])
    work_rows = index.work_orders.get(cal_id, [])
    inbox_item_id = (
        str(draft.get("inbox_item_id") or "")
        if draft
        else _inbox_ref_for_cal(brand_id=index.brand_id, cal_id=cal_id)
    )
    state, needs_fix_reason = _derive_post_state(
        record,
        index=index,
        draft=draft,
        queue_rows=queue_rows,
        receipts=receipts,
        work_rows=work_rows,
        inbox_item_id=inbox_item_id,
    )
    flags = _compute_flags(record, state=state, now=now)
    stages, stage = _rollup_stages(
        has_moment=True,
        draft=draft,
        sandbox_rows=queue_rows,
        receipts=receipts,
    )
    go_live = _moment_go_live_date(record)
    image_url = None
    if draft:
        image_url = draft.get("image_url") or draft.get("image_path")
    retry_count = _retry_count_for_inbox(index, inbox_item_id)
    sandbox_slim = [
        {
            "platform": r.get("platform"),
            "idempotency_key": r.get("idempotency_key"),
            "status": r.get("status"),
            "human_approved": r.get("human_approved"),
        }
        for r in queue_rows
    ]
    from _lib.campaigns import provenance_fields_from_record  # noqa: PLC0415

    prov = provenance_fields_from_record(record)
    out: dict[str, Any] = {
        "calendar_id": cal_id,
        "state": state,
        "flags": flags,
        "stages": stages,
        "stage": stage,
        "go_live_date": go_live,
        "inbox_item_id": (
            draft.get("inbox_item_id")
            if draft
            else _inbox_ref_for_cal(brand_id=index.brand_id, cal_id=cal_id)
        ),
        "asset_id": draft.get("asset_id") if draft else None,
        "image_url": image_url,
        "retry_count": retry_count,
        "sandbox": sandbox_slim,
        "receipts": receipts,
        "next_action": _next_action_for_state(state, needs_fix_reason=needs_fix_reason),
        "pillar_id": prov.get("pillar_id"),
        "campaign_id": prov.get("campaign_id"),
        "lane": prov.get("lane"),
        "origin": prov.get("origin"),
        "process": prov.get("process"),
    }
    if needs_fix_reason:
        out["needs_fix_reason"] = needs_fix_reason
    return out


def post_state_for(brand_id: str, calendar_id: str) -> dict[str, Any] | None:
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    index = build_post_index(brand_id=brand_id)
    for record in canonical_records(brand_id):
        cal_id = str(record.get("calendar_id") or record.get("event_key") or "")
        if cal_id == calendar_id:
            return post_state(record, index=index)
    return None


def _post_row_from_record(
    record: dict[str, Any],
    *,
    index: PostIndex,
    now: datetime,
) -> dict[str, Any]:
    joined = post_state(record, index=index, now=now)
    title = str(record.get("title") or record.get("event_key") or joined["calendar_id"])
    return {
        **joined,
        "title": title,
        "primary_channel": record.get("primary_channel"),
        "source_type": record.get("source_type"),
        "calendar_status": record.get("status"),
    }


def week_board(
    *,
    brand_id: str,
    start: date | None = None,
    days: int = 7,
    past_days: int = 0,
    include_candidates: bool = True,
    include_undated: bool = True,
) -> dict[str, Any]:
    """Operator posting calendar: moments in horizon joined via post_state."""
    from _lib.marketing_calendar import VALID_BRAND_IDS, canonical_records  # noqa: PLC0415

    if brand_id not in VALID_BRAND_IDS:
        raise ValueError(f"brand_id '{brand_id}' is not an operating brand")
    days = max(1, min(int(days), 31))
    past_days = max(0, min(int(past_days), 7))
    tz = _WEEK_TZ
    today = datetime.now(tz).date()
    anchor = start or today
    window_start = anchor - timedelta(days=past_days)
    window_end = anchor + timedelta(days=days - 1)
    now = datetime.now(timezone.utc)

    index = build_post_index(brand_id=brand_id)
    moments_by_cal: dict[str, dict[str, Any]] = {}
    undated_records: list[dict[str, Any]] = []

    for record in canonical_records(brand_id):
        status = str(record.get("status") or "")
        if status not in _WEEK_MOMENT_STATUSES:
            continue
        cal_id = str(record.get("calendar_id") or record.get("event_key") or "")
        if not cal_id:
            continue
        go_live = _moment_go_live_date(record)
        if not go_live:
            if include_undated:
                undated_records.append(record)
            continue
        if not include_candidates and status == "candidate" and not _is_holiday_record(record):
            continue
        try:
            go_date = date.fromisoformat(go_live)
        except ValueError:
            continue
        if go_date < window_start or go_date > window_end:
            continue
        moments_by_cal[cal_id] = {**record, "_go_live": go_live}

    orphan_drafts = index.sidecar_orphans
    for cal_id in index.drafts:
        if cal_id not in moments_by_cal:
            orphan_drafts += 1

    undated_records.sort(
        key=lambda r: str(r.get("created_at") or r.get("last_verified") or ""),
        reverse=True,
    )
    undated_total = len(undated_records)
    undated_slice = undated_records[:UNDATED_CAP] if include_undated else []
    undated_posts = [
        _post_row_from_record(rec, index=index, now=now) for rec in undated_slice
    ]

    days_list: list[dict[str, Any]] = []
    state_counts: dict[str, int] = {s: 0 for s in POST_STATES}
    moment_count = 0
    draft_count = 0
    queued_count = 0
    day_cursor = window_start
    while day_cursor <= window_end:
        day_iso = day_cursor.isoformat()
        posts: list[dict[str, Any]] = []
        for cal_id, record in moments_by_cal.items():
            if record.get("_go_live") != day_iso:
                continue
            moment_count += 1
            row = _post_row_from_record(record, index=index, now=now)
            if row.get("asset_id"):
                draft_count += 1
            if row.get("sandbox"):
                queued_count += 1
            st = str(row.get("state") or "")
            if st in state_counts:
                state_counts[st] += 1
            posts.append(row)
        posts.sort(key=lambda p: p.get("title") or "")
        holidays = [
            {"title": p.get("title")}
            for p in posts
            if "holiday" in (p.get("flags") or [])
        ]
        days_list.append(
            {
                "date": day_iso,
                "weekday": day_cursor.strftime("%a"),
                "is_today": day_cursor == today,
                "is_past": day_cursor < today,
                "posts": posts,
                "holidays": holidays,
            }
        )
        day_cursor += timedelta(days=1)

    for row in undated_posts:
        st = str(row.get("state") or "")
        if st in state_counts:
            state_counts[st] += 1

    return {
        "ok": True,
        "brand": brand_id,
        "timezone": str(tz),
        "start": anchor.isoformat(),
        "days": days,
        "past_days": past_days,
        "days_list": days_list,
        "undated": undated_posts,
        "undated_total": undated_total,
        "orphan_drafts": orphan_drafts,
        "counts": {
            "moments": moment_count,
            "drafts": draft_count,
            "queued": queued_count,
            "released": state_counts.get("released", 0),
            "posted": state_counts.get("posted", 0),
            "candidates": state_counts.get("candidate", 0),
            "needs_fix": state_counts.get("needs_fix", 0),
            "stale": sum(1 for d in days_list for p in d["posts"] if "stale" in (p.get("flags") or [])),
        },
    }


def shelf_board(*, brand_id: str, include_released: bool = True) -> dict[str, Any]:
    """Committed posts grouped by go-live date: scheduled and released awaiting dispatch."""
    from _lib.marketing_calendar import VALID_BRAND_IDS, canonical_records  # noqa: PLC0415

    if brand_id not in VALID_BRAND_IDS:
        raise ValueError(f"brand_id '{brand_id}' is not an operating brand")
    tz = _WEEK_TZ
    today = datetime.now(tz).date()
    now = datetime.now(timezone.utc)
    index = build_post_index(brand_id=brand_id)

    by_date: dict[str, list[dict[str, Any]]] = {}
    undated: list[dict[str, Any]] = []
    counts = {
        "scheduled": 0,
        "released": 0,
        "undated": 0,
        "releasable_today": 0,
        "released_today": _released_today_from_edits(),
    }

    for record in canonical_records(brand_id):
        status = str(record.get("status") or "")
        if status not in _WEEK_MOMENT_STATUSES:
            continue
        row = _post_row_from_record(record, index=index, now=now)
        st = str(row.get("state") or "")
        if st == "posted":
            continue
        if st == "scheduled":
            counts["scheduled"] += 1
        elif st == "released":
            if not include_released:
                continue
            counts["released"] += 1
        else:
            continue

        go_live = row.get("go_live_date")
        if not go_live:
            undated.append(row)
            counts["undated"] += 1
            continue
        if st == "scheduled" and go_live == today.isoformat():
            counts["releasable_today"] += 1
        by_date.setdefault(str(go_live), []).append(row)

    date_groups: list[dict[str, Any]] = []
    for day_iso in sorted(by_date.keys()):
        posts = by_date[day_iso]
        posts.sort(key=lambda p: p.get("title") or "")
        date_groups.append({"date": day_iso, "posts": posts})

    undated.sort(key=lambda p: p.get("title") or "")
    undated = undated[:UNDATED_CAP]

    return {
        "ok": True,
        "brand": brand_id,
        "timezone": str(tz),
        "today": today.isoformat(),
        "date_groups": date_groups,
        "undated": undated,
        "counts": counts,
    }


def _released_today_from_edits() -> int:
    today_iso_prefix = datetime.now(timezone.utc).date().isoformat()
    released_today = 0
    for row in _read_jsonl(_human_edits_path()):
        if str(row.get("action") or "") != "release":
            continue
        ts = str(row.get("ts") or "")
        if ts.startswith(today_iso_prefix):
            released_today += 1
    return released_today


def _approved_today_from_edits() -> int:
    today_iso_prefix = datetime.now(timezone.utc).date().isoformat()
    approved_today = 0
    for row in _read_jsonl(_human_edits_path()):
        if str(row.get("action") or "") != "approve":
            continue
        ts = str(row.get("ts") or "")
        if ts.startswith(today_iso_prefix):
            approved_today += 1
    return approved_today


def inbox_counts(*, review_sla: dict[str, Any] | None = None) -> dict[str, Any]:
    """Counts for /ops Approve tab and L4 rollup."""
    payload = list_items(status="pending")
    pending = int(payload["summary"]["pending"])
    stale = int(payload["summary"]["stale"])

    approved_today = _approved_today_from_edits()

    if review_sla and isinstance(review_sla, dict):
        summary = review_sla.get("summary") or {}
        stale = max(stale, int(summary.get("total_breached") or 0))

    verdict = "NEVER"
    if pending > 0:
        verdict = "LATE" if stale > 0 else "OK"
    elif approved_today > 0:
        verdict = "OK"

    return {
        "pending": pending,
        "stale": stale,
        "approved_today": approved_today,
        "verdict": verdict,
    }


def _l5_enqueue_suppressed() -> bool:
    """Explicit falsey CAMPAIGN_OS_L5_ENQUEUE suppresses enqueue; unset allows it."""
    raw = os.environ.get("CAMPAIGN_OS_L5_ENQUEUE")
    if raw is None or not str(raw).strip():
        return False
    return str(raw).strip().lower() not in ("1", "true", "yes", "on")


def _photo_equiv_queued(existing: set[tuple[str, str]]) -> bool:
    from _lib.jobs.layer5.draft_assets import _PHOTO_EQUIV  # noqa: PLC0415

    for name in _PHOTO_EQUIV:
        if (name, "pending") in existing or (name, "waiting") in existing:
            return True
    return False


def _maybe_enqueue_l5_create(item_id: str, brand_id: str, item_type: str) -> list[str]:
    """Enqueue draft_caption + draft_photo + compose_post (+ draft_gbp when intended) after lodge."""
    enqueued: list[str] = []
    if _l5_enqueue_suppressed():
        return enqueued
    if item_type not in ("proposal", "calendar_candidate"):
        return enqueued
    try:
        from _lib.l5_create_enqueue import enqueue_create_actions  # noqa: PLC0415

        reason = item_type.replace("_", "-")[:32]
        enqueued = enqueue_create_actions(item_id=item_id, brand_id=brand_id, reason=reason)
    except Exception:
        pass
    return enqueued


def _calendar_record_for_key(brand_id: str, cal_id: str) -> dict[str, Any] | None:
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    for record in canonical_records(brand_id):
        rid = str(record.get("calendar_id") or record.get("event_key") or "")
        if rid == cal_id:
            return record
    return None


def _promote_proposal_to_moment(
    row: dict[str, Any],
    *,
    brand_id: str,
    event_date: str,
    primary_channel: str | None = None,
) -> str:
    from _lib.marketing_calendar import add_candidate  # noqa: PLC0415

    day = str(event_date)[:10]
    payload: dict[str, Any] = {
        "type": "moment",
        "title": str(row.get("title") or row.get("headline") or "Proposal"),
        "angle": row.get("summary") or row.get("rationale") or "",
        "source_type": "interpreter",
        "created_by": "proposal_promote",
        "event_date": day,
        "event_start": day,
        "event_end": day,
        "verification_status": "unverified",
    }
    if primary_channel:
        payload["primary_channel"] = primary_channel
    created = add_candidate(brand_id, payload, initial_status="candidate")
    return str(created.get("calendar_id") or "")


def find_item(item_id: str) -> Optional[dict[str, Any]]:
    item_type, _key = _parse_item_id(item_id)
    payload = list_items(status="all", item_type=item_type)
    for item in payload.get("items") or []:
        if item.get("id") == item_id:
            return item
    return None


def approve_item(
    item_id: str,
    *,
    editor: str = "operator",
    reason: str = "",
    mode: str = "lodge",
    event_date: str | None = None,
    primary_channel: str | None = None,
) -> dict[str, Any]:
    item = find_item(item_id)
    if not item:
        return {"ok": False, "error": "inbox item not found"}
    item_type, key = _parse_item_id(item_id)
    mode_norm = (mode or "lodge").strip().lower()
    if mode_norm not in ("lodge", "book"):
        mode_norm = "lodge"

    if item_type == "calendar_candidate":
        brand_id, cal_id = key.split(":", 1)
        from _lib.marketing_calendar import set_fields, transition_status  # noqa: PLC0415

        record = _calendar_record_for_key(brand_id, cal_id)
        if not record:
            return {"ok": False, "error": "calendar record not found"}
        if mode_norm == "lodge" and not _moment_go_live_date(record):
            return {"ok": False, "error": "no_date", "code": "no_date"}
        if not str(record.get("primary_channel") or "").strip():
            ch = (primary_channel or "instagram").strip().lower()
            set_fields(brand_id, cal_id, {"primary_channel": ch}, reason="default channel on lodge")
            item_id = _item_id("calendar_candidate", f"{brand_id}:{cal_id}")

        updated = transition_status(
            brand_id,
            cal_id,
            "approved",
            reason=reason or ("Lodge" if mode_norm == "lodge" else "Book only"),
        )
        if not updated:
            return {"ok": False, "error": "calendar record not found"}
        record_human_edit(
            inbox_item_id=item_id,
            item_type=item_type,
            brand_id=brand_id,
            editor=editor,
            fields={"new_status": "approved", "calendar_id": cal_id, "mode": mode_norm},
            note=reason,
        )
        _append_jsonl(_human_edits_path(), {
            "schema": HUMAN_EDIT_SCHEMA,
            "ts": _utc_now_iso(),
            "action": "approve",
            "editor": editor,
            "inbox_item_id": item_id,
            "item_type": item_type,
            "brand_id": brand_id,
        })
        enqueued: list[str] = []
        result: dict[str, Any] = {
            "ok": True,
            "item_id": item_id,
            "record": updated,
            "mode": mode_norm,
            "enqueued": enqueued,
        }
        if mode_norm == "lodge":
            enqueued.extend(_maybe_enqueue_l5_create(item_id, brand_id, item_type))
            result["enqueued"] = enqueued
            if _l5_enqueue_suppressed():
                result["enqueue_suppressed"] = "CAMPAIGN_OS_L5_ENQUEUE=0"
        return result

    if item_type == "proposal":
        brand_id, pid = key.split(":", 1)
        rows = _read_jsonl(_proposals_path())
        prop_row: dict[str, Any] | None = None
        for row in rows:
            if str(row.get("id") or row.get("proposal_id")) == pid:
                prop_row = row
                break
        if prop_row is None:
            return {"ok": False, "error": "proposal not found"}
        lodge_date = event_date
        if mode_norm == "lodge" and not lodge_date:
            return {"ok": False, "error": "no_date", "code": "no_date"}
        cal_id = ""
        if lodge_date:
            cal_id = _promote_proposal_to_moment(
                prop_row,
                brand_id=brand_id,
                event_date=lodge_date,
                primary_channel=primary_channel,
            )
        elif mode_norm == "book":
            from _lib.marketing_calendar import add_candidate  # noqa: PLC0415

            created = add_candidate(
                brand_id,
                {
                    "type": "moment",
                    "title": str(prop_row.get("title") or prop_row.get("headline") or "Proposal"),
                    "angle": prop_row.get("summary") or prop_row.get("rationale") or "",
                    "source_type": "interpreter",
                    "created_by": "proposal_promote",
                    "verification_status": "unverified",
                },
                initial_status="candidate",
            )
            cal_id = str(created.get("calendar_id") or "")
        if cal_id:
            item_id = _item_id("calendar_candidate", f"{brand_id}:{cal_id}")
        for row in rows:
            if str(row.get("id") or row.get("proposal_id")) == pid:
                row["status"] = "approved"
                row["approved_at"] = _utc_now_iso()
                row["approved_by"] = editor
                if cal_id:
                    row["promoted_calendar_id"] = cal_id
                    row["promoted_at"] = _utc_now_iso()
        _proposals_path().parent.mkdir(parents=True, exist_ok=True)
        _proposals_path().write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )
        if cal_id:
            from _lib.marketing_calendar import transition_status  # noqa: PLC0415

            transition_status(brand_id, cal_id, "approved", reason=reason or "proposal lodge")
        _append_jsonl(_human_edits_path(), {
            "schema": HUMAN_EDIT_SCHEMA,
            "ts": _utc_now_iso(),
            "action": "approve",
            "editor": editor,
            "inbox_item_id": item_id,
            "item_type": item_type,
            "brand_id": brand_id,
        })
        enqueued = []
        result = {"ok": True, "item_id": item_id, "mode": mode_norm, "enqueued": enqueued}
        if cal_id and mode_norm == "lodge":
            enqueued.extend(_maybe_enqueue_l5_create(item_id, brand_id, "calendar_candidate"))
            result["enqueued"] = enqueued
            if _l5_enqueue_suppressed():
                result["enqueue_suppressed"] = "CAMPAIGN_OS_L5_ENQUEUE=0"
        return result

    if item_type == "draft_asset":
        campaign_id, asset_id = key.split(":", 1)
        data = _load_campaign_data()
        campaign = (data.get("campaigns") or {}).get(campaign_id)
        if not campaign:
            return {"ok": False, "error": "campaign not found"}
        asset = (campaign.get("assets") or {}).get(asset_id)
        if not asset:
            return {"ok": False, "error": "asset not found"}
        now = _utc_now_iso()
        asset["approvalStatus"] = "approved"
        asset["updatedAt"] = now
        asset["reviewTs"] = now
        campaign["updatedAt"] = now
        _write_campaign_data(data)
        brand_id = str(item.get("brand_id") or "")
        _append_jsonl(_human_edits_path(), {
            "schema": HUMAN_EDIT_SCHEMA,
            "ts": now,
            "action": "approve",
            "editor": editor,
            "inbox_item_id": item_id,
            "item_type": item_type,
            "brand_id": brand_id,
        })
        return {"ok": True, "item_id": item_id, "asset_id": asset_id}

    if item_type == "publish_request":
        from _lib import publish_sandbox  # noqa: PLC0415

        updated, err = publish_sandbox.approve_item(key)
        if err:
            return {"ok": False, "error": err}
        _append_jsonl(_human_edits_path(), {
            "schema": HUMAN_EDIT_SCHEMA,
            "ts": _utc_now_iso(),
            "action": "approve",
            "editor": editor,
            "inbox_item_id": item_id,
            "item_type": item_type,
            "brand_id": str(item.get("brand_id") or ""),
        })
        return {"ok": True, "item_id": item_id, "queue_item": updated}

    return {"ok": False, "error": "unsupported item type"}


def reject_item(item_id: str, *, editor: str = "operator", reason: str = "") -> dict[str, Any]:
    item = find_item(item_id)
    if not item:
        return {"ok": False, "error": "inbox item not found"}
    item_type, key = _parse_item_id(item_id)

    if item_type == "calendar_candidate":
        brand_id, cal_id = key.split(":", 1)
        from _lib.marketing_calendar import transition_status  # noqa: PLC0415

        updated = transition_status(brand_id, cal_id, "ignored", reason=reason or "L4 reject")
        if not updated:
            return {"ok": False, "error": "calendar record not found"}
        record_human_edit(
            inbox_item_id=item_id,
            item_type=item_type,
            brand_id=brand_id,
            editor=editor,
            fields={"new_status": "ignored", "calendar_id": cal_id},
            note=reason,
        )
        _append_jsonl(_human_edits_path(), {
            "schema": HUMAN_EDIT_SCHEMA,
            "ts": _utc_now_iso(),
            "action": "reject",
            "editor": editor,
            "inbox_item_id": item_id,
            "item_type": item_type,
            "brand_id": brand_id,
        })
        return {"ok": True, "item_id": item_id, "record": updated}

    if item_type == "proposal":
        brand_id, pid = key.split(":", 1)
        rows = _read_jsonl(_proposals_path())
        found = False
        for row in rows:
            if str(row.get("id") or row.get("proposal_id")) == pid:
                row["status"] = "rejected"
                row["rejected_at"] = _utc_now_iso()
                row["rejected_by"] = editor
                if reason:
                    row["rejection_reason"] = reason
                found = True
        if not found:
            return {"ok": False, "error": "proposal not found"}
        _proposals_path().parent.mkdir(parents=True, exist_ok=True)
        _proposals_path().write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )
        _append_jsonl(_human_edits_path(), {
            "schema": HUMAN_EDIT_SCHEMA,
            "ts": _utc_now_iso(),
            "action": "reject",
            "editor": editor,
            "inbox_item_id": item_id,
            "item_type": item_type,
            "brand_id": brand_id,
        })
        return {"ok": True, "item_id": item_id}

    if item_type == "draft_asset":
        if not (reason or "").strip():
            return {"ok": False, "error": "reason is required for draft_asset reject", "code": "reason_required"}
        campaign_id, asset_id = key.split(":", 1)
        data = _load_campaign_data()
        campaign = (data.get("campaigns") or {}).get(campaign_id)
        if not campaign:
            return {"ok": False, "error": "campaign not found"}
        asset = (campaign.get("assets") or {}).get(asset_id)
        if not asset:
            return {"ok": False, "error": "asset not found"}
        sidecar_path = _data_dir() / "draft-assets" / f"{asset_id}.json"
        sidecar: dict[str, Any] = {}
        if sidecar_path.is_file():
            try:
                loaded = json.loads(sidecar_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    sidecar = loaded
            except (OSError, json.JSONDecodeError):
                pass
        now = _utc_now_iso()
        asset["approvalStatus"] = "rejected"
        asset["rejectionReason"] = reason.strip()
        asset["updatedAt"] = now
        asset["reviewTs"] = now
        campaign["updatedAt"] = now
        _write_campaign_data(data)
        brand_id = str(item.get("brand_id") or "")
        from _lib.draft_review_actions import record_draft_reject_feedback  # noqa: PLC0415

        record_draft_reject_feedback(
            brand_id=brand_id,
            asset_id=asset_id,
            reason=reason.strip(),
            sidecar=sidecar,
        )
        _append_jsonl(_human_edits_path(), {
            "schema": HUMAN_EDIT_SCHEMA,
            "ts": now,
            "action": "reject",
            "editor": editor,
            "inbox_item_id": item_id,
            "item_type": item_type,
            "brand_id": brand_id,
        })
        return {"ok": True, "item_id": item_id, "asset_id": asset_id}

    if item_type == "publish_request":
        from _lib import publish_sandbox  # noqa: PLC0415

        queue_path = publish_sandbox._queue_path()  # noqa: SLF001
        rows = _read_jsonl(queue_path)
        found = False
        for row in rows:
            if str(row.get("idempotency_key") or "") == key:
                row["status"] = "rejected"
                row["rejected_at"] = _utc_now_iso()
                if reason:
                    row["rejection_reason"] = reason
                found = True
        if not found:
            return {"ok": False, "error": "publish request not found"}
        publish_sandbox._rewrite_jsonl(queue_path, rows)  # noqa: SLF001
        _append_jsonl(_human_edits_path(), {
            "schema": HUMAN_EDIT_SCHEMA,
            "ts": _utc_now_iso(),
            "action": "reject",
            "editor": editor,
            "inbox_item_id": item_id,
            "item_type": item_type,
            "brand_id": str(item.get("brand_id") or ""),
        })
        return {"ok": True, "item_id": item_id}

    return {"ok": False, "error": "unsupported item type"}


def edit_item(
    item_id: str,
    *,
    editor: str = "operator",
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = find_item(item_id)
    if not item:
        return {"ok": False, "error": "inbox item not found"}
    item_type, key = _parse_item_id(item_id)
    fields = dict(fields or {})
    brand_id = str(item.get("brand_id") or fields.get("brand_id") or "")
    previous = _current_field_values(item_type, key, list(fields.keys()))

    record_human_edit(
        inbox_item_id=item_id,
        item_type=item_type,
        brand_id=brand_id,
        editor=editor,
        fields=fields,
        previous=previous or None,
    )

    changed: list[str] = []

    if item_type == "calendar_candidate":
        brand_id, cal_id = key.split(":", 1)
        from _lib.marketing_calendar import set_fields  # noqa: PLC0415
        from zoneinfo import ZoneInfo

        editable = {
            k: fields[k]
            for k in ("event_date", "primary_channel", "title", "angle")
            if k in fields
        }
        if "event_date" in editable:
            day = str(editable["event_date"])[:10]
            try:
                picked = date.fromisoformat(day)
            except ValueError as exc:
                raise ValueError("event_date must be YYYY-MM-DD") from exc
            today_sast = datetime.now(ZoneInfo("Africa/Johannesburg")).date()
            if picked < today_sast:
                raise ValueError("event_date cannot be in the past")
            editable["event_date"] = day
        if editable:
            before = _calendar_record_for_key(brand_id, cal_id) or {}
            updated = set_fields(brand_id, cal_id, editable, reason="inbox edit")
            if not updated:
                return {"ok": False, "error": "calendar record not found"}
            after = _calendar_record_for_key(brand_id, cal_id) or {}
            for fname in editable:
                if before.get(fname) != after.get(fname) or (
                    fname == "event_date" and _moment_go_live_date(before) != _moment_go_live_date(after)
                ):
                    changed.append(fname)

    if item_type == "draft_asset" and ("caption" in fields or "title" in fields):
        campaign_id, asset_id = key.split(":", 1)
        data = _load_campaign_data()
        campaign = (data.get("campaigns") or {}).get(campaign_id)
        if campaign:
            asset = (campaign.get("assets") or {}).get(asset_id)
            if asset:
                if "caption" in fields:
                    asset["caption"] = fields["caption"]
                    changed.append("caption")
                if "title" in fields:
                    asset["name"] = fields["title"]
                    changed.append("title")
                asset["updatedAt"] = _utc_now_iso()
                campaign["updatedAt"] = asset["updatedAt"]
                _write_campaign_data(data)

    refreshed = find_item(item_id)
    out: dict[str, Any] = {
        "ok": True,
        "item_id": item_id,
        "human_edit": True,
        "changed": changed,
    }
    if refreshed:
        out["item"] = refreshed
    return out
