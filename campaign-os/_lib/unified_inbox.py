"""Unified review inbox (L4) — calendar candidates, proposals, drafts, publish requests."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA = "campaign-os/unified-inbox/v1"
HUMAN_EDIT_SCHEMA = "campaign-os/human-edit-signal/v1"
SLA_STALE_HOURS = 24
ITEM_TYPES = frozenset({"calendar_candidate", "proposal", "draft_asset", "publish_request"})


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
    return previous


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
            ts = record.get("last_verified") or record.get("created_at")
            item_status = "pending"
            if status != "all" and item_status != status:
                continue
            cal_id = str(record.get("calendar_id") or record.get("event_key") or "")
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
                "sla_state": _sla_state(ts, now=now),
                "actions": ["approve", "edit", "reject"],
                "meta": {
                    "calendar_id": cal_id,
                    "pillar": record.get("pillar"),
                    "event_start": record.get("event_start") or record.get("event_window_start"),
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


def _draft_items(*, brand: str | None, status: str, now: datetime) -> list[dict[str, Any]]:
    from _lib import intelligence  # noqa: PLC0415

    if brand:
        intelligence.set_request_brand(brand)
    inbox = intelligence.review_inbox()
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
            out.append({
                "id": _item_id("draft_asset", f"{cid}:{aid}"),
                "type": "draft_asset",
                "brand_id": brand_id,
                "title": str(row.get("name") or aid),
                "summary": str(row.get("caption") or "")[:240],
                "evidence": [{"source": "review_inbox", "ref": f"{cid}/{aid}"}],
                "created_at": ts,
                "updated_at": ts,
                "status": item_status,
                "sla_state": _sla_state(str(ts) if ts else None, now=now),
                "actions": ["approve", "edit", "reject"] if item_status == "pending" else ["edit"],
                "meta": {
                    "campaign_id": cid,
                    "asset_id": aid,
                    "platform": row.get("platform"),
                    "approval_status": row.get("approvalStatus"),
                },
            })
    return out


def _publish_request_items(*, brand: str | None, status: str, now: datetime) -> list[dict[str, Any]]:
    from _lib import publish_sandbox  # noqa: PLC0415

    queue_path = publish_sandbox._queue_path()  # noqa: SLF001
    rows = _read_jsonl(queue_path)
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
        out.append({
            "id": _item_id("publish_request", key),
            "type": "publish_request",
            "brand_id": brand_id,
            "title": f"Publish {row.get('platform') or 'post'} — {brand_id}",
            "summary": str(row.get("caption_preview") or "")[:240],
            "evidence": [{"source": "publish-sandbox", "ref": key}],
            "created_at": ts,
            "updated_at": row.get("human_approved_at") or ts,
            "status": item_status,
            "sla_state": _sla_state(str(ts) if ts else None, now=now),
            "blocked_missing_oauth": blocked,
            "actions": ["approve", "edit", "reject"],
            "meta": {
                "idempotency_key": key,
                "human_approved": bool(row.get("human_approved")),
                "channel": row.get("channel"),
            },
        })
    return out


def list_items(
    *,
    brand: str | None = None,
    status: str = "pending",
    item_type: str | None = None,
) -> dict[str, Any]:
    """Build unified inbox list payload."""
    now = datetime.now(timezone.utc)
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

    items.sort(key=lambda x: (0 if x.get("sla_state") == "stale" else 1, x.get("updated_at") or ""))

    stale = sum(1 for i in items if i.get("sla_state") == "stale" and i.get("status") == "pending")
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
        "items": items,
    }


def inbox_counts(*, review_sla: dict[str, Any] | None = None) -> dict[str, Any]:
    """Counts for /ops Approve tab and L4 rollup."""
    payload = list_items(status="pending")
    pending = int(payload["summary"]["pending"])
    stale = int(payload["summary"]["stale"])

    approved_today = 0
    edits_path = _human_edits_path()
    today_iso_prefix = datetime.now(timezone.utc).date().isoformat()
    for row in _read_jsonl(edits_path):
        if str(row.get("action") or "") != "approve":
            continue
        ts = str(row.get("ts") or "")
        if ts.startswith(today_iso_prefix):
            approved_today += 1

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


def _l5_enqueue_enabled() -> bool:
    raw = (os.environ.get("CAMPAIGN_OS_L5_ENQUEUE") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _maybe_enqueue_l5_create(item_id: str, brand_id: str, item_type: str) -> None:
    """Enqueue a draft_caption row after L4 approve (flag-gated; never fails approve)."""
    if not _l5_enqueue_enabled():
        return
    if item_type not in ("proposal", "calendar_candidate"):
        return
    try:
        from _lib import ops_agents  # noqa: PLC0415

        reason = item_type.replace("_", "-")[:32]
        row = ops_agents.normalise_enqueue(
            {
                "agent": "cos-caption",
                "brand": brand_id,
                "reason": reason,
                "action": "draft_caption",
                "payload_ref": f"inbox/{item_id}",
            }
        )
        ops_agents.append_enqueue_row(_data_dir(), row)
    except Exception:
        pass


def find_item(item_id: str) -> Optional[dict[str, Any]]:
    item_type, _key = _parse_item_id(item_id)
    payload = list_items(status="all", item_type=item_type)
    for item in payload.get("items") or []:
        if item.get("id") == item_id:
            return item
    return None


def approve_item(item_id: str, *, editor: str = "operator", reason: str = "") -> dict[str, Any]:
    item = find_item(item_id)
    if not item:
        return {"ok": False, "error": "inbox item not found"}
    item_type, key = _parse_item_id(item_id)

    if item_type == "calendar_candidate":
        brand_id, cal_id = key.split(":", 1)
        from _lib.marketing_calendar import transition_status  # noqa: PLC0415

        updated = transition_status(brand_id, cal_id, "approved", reason=reason or "L4 approve")
        if not updated:
            return {"ok": False, "error": "calendar record not found"}
        record_human_edit(
            inbox_item_id=item_id,
            item_type=item_type,
            brand_id=brand_id,
            editor=editor,
            fields={"new_status": "approved", "calendar_id": cal_id},
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
        _maybe_enqueue_l5_create(item_id, brand_id, item_type)
        return {"ok": True, "item_id": item_id, "record": updated}

    if item_type == "proposal":
        brand_id, pid = key.split(":", 1)
        rows = _read_jsonl(_proposals_path())
        found = False
        for row in rows:
            if str(row.get("id") or row.get("proposal_id")) == pid:
                row["status"] = "approved"
                row["approved_at"] = _utc_now_iso()
                row["approved_by"] = editor
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
            "action": "approve",
            "editor": editor,
            "inbox_item_id": item_id,
            "item_type": item_type,
            "brand_id": brand_id,
        })
        _maybe_enqueue_l5_create(item_id, brand_id, item_type)
        return {"ok": True, "item_id": item_id}

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
        campaign_id, asset_id = key.split(":", 1)
        data = _load_campaign_data()
        campaign = (data.get("campaigns") or {}).get(campaign_id)
        if not campaign:
            return {"ok": False, "error": "campaign not found"}
        asset = (campaign.get("assets") or {}).get(asset_id)
        if not asset:
            return {"ok": False, "error": "asset not found"}
        now = _utc_now_iso()
        asset["approvalStatus"] = "rejected"
        asset["rejectionReason"] = reason or "Rejected from unified inbox"
        asset["updatedAt"] = now
        asset["reviewTs"] = now
        campaign["updatedAt"] = now
        _write_campaign_data(data)
        brand_id = str(item.get("brand_id") or "")
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

    if item_type == "draft_asset" and ("caption" in fields or "title" in fields):
        campaign_id, asset_id = key.split(":", 1)
        data = _load_campaign_data()
        campaign = (data.get("campaigns") or {}).get(campaign_id)
        if campaign:
            asset = (campaign.get("assets") or {}).get(asset_id)
            if asset:
                if "caption" in fields:
                    asset["caption"] = fields["caption"]
                if "title" in fields:
                    asset["name"] = fields["title"]
                asset["updatedAt"] = _utc_now_iso()
                campaign["updatedAt"] = asset["updatedAt"]
                _write_campaign_data(data)

    return {"ok": True, "item_id": item_id, "human_edit": True}
