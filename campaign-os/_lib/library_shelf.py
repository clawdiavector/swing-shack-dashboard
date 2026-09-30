"""Read-only brand library — drafts, sandbox posts, template reference art."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _lib.brand_validate import validate_brand_id
from _lib import template_catalog
from _lib import template_gallery


def caption_present(text: str | None) -> bool:
    return bool(str(text or "").strip())


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clamp_limit(limit: int | None, *, default: int = 200, maximum: int = 500) -> int:
    if limit is None:
        return default
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, maximum))


def _normalize_view(view: str | None) -> str:
    v = str(view or "all").strip().lower()
    if v in ("drafts", "sandbox", "templates", "all"):
        return v
    return "all"


def _apply_limit(rows: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], bool]:
    if len(rows) <= limit:
        return rows, False
    return rows[:limit], True


def _draft_status(asset: dict[str, Any]) -> str:
    raw = str(asset.get("approvalStatus") or asset.get("approval_status") or "draft").lower()
    if raw == "approved":
        return "approved"
    if raw == "rejected":
        return "rejected"
    if raw == "archived":
        return "archived"
    return "pending"


def _build_draft_rows(brand_id: str) -> list[dict[str, Any]]:
    from _lib.unified_inbox import (  # noqa: PLC0415
        _asset_image_meta_with_sidecar,
        _calendar_id_from_inbox_ref,
        _campaign_asset_for_id,
        _composed_channel_url,
        _item_id,
        _load_campaign_data,
        _load_draft_sidecar,
    )

    campaign_data = _load_campaign_data()
    sidecar_dir = Path(__import__("os").environ.get("DATA_DIR", "/data/campaign-os")) / "draft-assets"
    if not sidecar_dir.is_dir():
        return []

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for path in sorted(sidecar_dir.glob("*.json")):
        if path.name.endswith(".brief.json") or path.name.endswith(".qc.json"):
            continue
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(sidecar, dict):
            continue
        asset_id = str(sidecar.get("asset_id") or path.stem)
        if asset_id in seen:
            continue
        campaign_id = str(sidecar.get("campaign_id") or "")
        cid, asset = _campaign_asset_for_id(campaign_data, asset_id)
        if cid:
            campaign_id = cid
        if not isinstance(asset, dict):
            asset = {}

        row_brand = str(sidecar.get("brand_id") or asset.get("brand") or "").strip()
        if row_brand != brand_id:
            continue

        seen.add(asset_id)
        source_item = str(sidecar.get("source_inbox_item_id") or "")
        cal_id = _calendar_id_from_inbox_ref(source_item)
        orphan = not bool(cal_id)
        full_caption = str(asset.get("caption") or sidecar.get("caption") or "")
        image_path, image_url = _asset_image_meta_with_sidecar(asset, sidecar)
        platform = str(asset.get("platform") or asset.get("integration") or sidecar.get("platform") or "instagram")

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
            asset_name=str(asset.get("name") or asset_id),
        )
        title = lodged_title or full_caption.split("\n", 1)[0].strip() or asset_id
        status = _draft_status(asset)
        inbox_item_id = _item_id("draft_asset", f"{campaign_id}:{asset_id}")

        composed = sidecar.get("composed") if isinstance(sidecar.get("composed"), dict) else {}
        composed_channels = sorted(str(k) for k in composed.keys()) if composed else []
        compose_pending = False
        arch_meta = sidecar.get("archetype") if isinstance(sidecar.get("archetype"), dict) else {}
        is_v2_template = str(arch_meta.get("schema") or "").endswith("/v2")
        if is_v2_template and arch_meta.get("id") and not composed:
            compose_pending = True
            image_url = None
            image_path = None
        elif composed:
            channel_url = _composed_channel_url(composed, primary_channel)
            if channel_url:
                image_url = channel_url

        row: dict[str, Any] = {
            "asset_id": asset_id,
            "campaign_id": campaign_id,
            "inbox_item_id": inbox_item_id,
            "title": title,
            "status": status,
            "platform": platform,
            "primary_channel": primary_channel,
            "created_at": sidecar.get("created_at") or asset.get("createdAt"),
            "updated_at": asset.get("updatedAt") or sidecar.get("created_at"),
            "caption": full_caption,
            "caption_present": caption_present(full_caption),
            "caption_chars": len(full_caption),
            "image_url": image_url,
            "image_path": image_path,
            "image_present": bool(image_path or image_url),
            "composed_channels": composed_channels,
            "compose_pending": compose_pending,
            "orphan": orphan,
            "source_inbox_item_id": source_item or None,
            "calendar_id": cal_id,
            "review_href": f"/review/{inbox_item_id}",
        }
        template_catalog.attach_template_fields(
            brand_id,
            row,
            archetype_meta=arch_meta or None,
            source_inbox_item_id=source_item or None,
        )
        if sidecar.get("qc") and isinstance(sidecar["qc"], dict):
            row["qc_verdict"] = sidecar["qc"].get("verdict") or sidecar["qc"].get("status")
        rows.append(row)

    rows.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True)
    return rows


def _read_sandbox_queue(brand_id: str) -> list[dict[str, Any]]:
    from _lib.publish_sandbox import _queue_path, _read_jsonl  # noqa: PLC0415

    out: list[dict[str, Any]] = []
    for row in _read_jsonl(_queue_path()):
        if str(row.get("brand_id") or "") != brand_id:
            continue
        out.append(dict(row))
    return out


def _read_sandbox_receipts(brand_id: str) -> tuple[list[dict[str, Any]], bool]:
    from _lib.publish_sandbox import RECEIPTS_SCAN_CAP, _receipts_path  # noqa: PLC0415

    path = _receipts_path()
    if not path.is_file():
        return [], False
    lines = path.read_text(encoding="utf-8").splitlines()
    tail_capped = len(lines) > RECEIPTS_SCAN_CAP
    if tail_capped:
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
    return out, tail_capped


def _build_sandbox_rows(brand_id: str) -> tuple[list[dict[str, Any]], bool]:
    from _lib.unified_inbox import (  # noqa: PLC0415
        _asset_image_meta,
        _asset_image_meta_with_sidecar,
        _campaign_asset_for_id,
        _load_campaign_data,
        _load_draft_sidecar,
        asset_id_from_queue_row,
    )

    campaign_data = _load_campaign_data()
    queue_rows = _read_sandbox_queue(brand_id)
    receipts, tail_capped = _read_sandbox_receipts(brand_id)
    receipt_by_key: dict[str, dict[str, Any]] = {}
    for rec in receipts:
        key = str(rec.get("idempotency_key") or "")
        if key:
            receipt_by_key[key] = rec

    out: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for row in queue_rows:
        key = str(row.get("idempotency_key") or row.get("queue_id") or "")
        seen_keys.add(key)
        rec = receipt_by_key.get(key) or {}
        asset_id = asset_id_from_queue_row(row)
        campaign_id: str | None = None
        image_path: Any = None
        image_url: Any = None
        if asset_id:
            campaign_id, asset = _campaign_asset_for_id(campaign_data, asset_id)
            row_url = str(row.get("image_url") or "").strip()
            if row_url:
                image_url = row_url
            else:
                    side = _load_draft_sidecar(asset_id)
                    asset_dict = asset if isinstance(asset, dict) else {}
                    image_path, image_url = _asset_image_meta_with_sidecar(asset_dict, side)
                    if not image_url:
                        image_path, image_url = _asset_image_meta(asset_dict)

        cap = str(row.get("caption_preview") or rec.get("caption_preview") or "")
        status = str(row.get("status") or "pending")
        dispatched_at = row.get("dispatched_at") or rec.get("dispatched_at")
        sandbox_post_id = row.get("sandbox_post_id") or rec.get("sandbox_post_id")
        queue_id = str(row.get("queue_id") or key)
        href_key = str(row.get("idempotency_key") or queue_id)
        out.append(
            {
                "queue_id": queue_id,
                "idempotency_key": row.get("idempotency_key"),
                "platform": row.get("platform"),
                "channel": row.get("channel") or "postiz",
                "status": status,
                "human_approved": bool(row.get("human_approved")),
                "human_approved_at": row.get("human_approved_at"),
                "created_at": row.get("created_at"),
                "would_publish_at": row.get("would_publish_at") or rec.get("would_publish_at"),
                "event_date": row.get("event_date"),
                "dispatched_at": dispatched_at,
                "sandbox_post_id": sandbox_post_id,
                "is_sandbox_post": bool(sandbox_post_id),
                "caption_preview": cap,
                "caption_present": caption_present(cap),
                "caption_truncated": len(cap) >= 120,
                "lodged_title": row.get("lodged_title"),
                "asset_id": asset_id,
                "campaign_id": campaign_id or row.get("campaign_id"),
                "inbox_item_id": row.get("inbox_item_id"),
                "image_url": image_url or row.get("image_url"),
                "image_path": image_path or row.get("image_path"),
                "image_present": bool(image_url or image_path or row.get("image_url")),
                "receipt_only": False,
                "sandbox_href": f"/publish/sandbox/{href_key}",
            }
        )

    for rec in receipts:
        key = str(rec.get("idempotency_key") or "")
        if key and key in seen_keys:
            continue
        cap = str(rec.get("caption_preview") or "")
        out.append(
            {
                "queue_id": None,
                "idempotency_key": rec.get("idempotency_key"),
                "platform": rec.get("platform"),
                "channel": rec.get("channel") or "postiz",
                "status": "dispatched",
                "human_approved": bool(rec.get("human_approved")),
                "human_approved_at": rec.get("human_approved_at"),
                "created_at": rec.get("created_at"),
                "would_publish_at": rec.get("would_publish_at"),
                "event_date": rec.get("event_date"),
                "dispatched_at": rec.get("dispatched_at"),
                "sandbox_post_id": rec.get("sandbox_post_id"),
                "is_sandbox_post": True,
                "caption_preview": cap,
                "caption_present": caption_present(cap),
                "caption_truncated": len(cap) >= 120,
                "lodged_title": rec.get("lodged_title"),
                "asset_id": None,
                "campaign_id": rec.get("campaign_id"),
                "inbox_item_id": rec.get("inbox_item_id"),
                "image_url": None,
                "image_path": None,
                "image_present": False,
                "receipt_only": True,
                "sandbox_href": f"/publish/sandbox/{rec.get('idempotency_key') or rec.get('sandbox_post_id') or ''}",
            }
        )

    out.sort(key=lambda r: str(r.get("dispatched_at") or r.get("created_at") or ""), reverse=True)
    return out, tail_capped


def _union_reference_images(
    brand_id: str,
    declared_urls: list[str],
    disk_urls: list[str],
) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    seen: set[str] = set()
    for url in declared_urls:
        u = str(url or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        images.append({"url": u, "provenance": "declared"})
    for url in disk_urls:
        u = str(url or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        images.append({"url": u, "provenance": "disk"})
    return images


def _build_template_rows(brand_id: str) -> list[dict[str, Any]]:
    gallery = template_gallery.build_template_gallery(brand_id)
    templates = gallery.get("templates") or []
    rows: list[dict[str, Any]] = []
    for tpl in templates:
        if not isinstance(tpl, dict):
            continue
        tid = str(tpl.get("template_id") or "")
        meta = template_catalog.template_display_meta(brand_id, tid)
        declared_urls = list(meta.get("template_reference_urls") or [])
        disk_urls = list(tpl.get("preview_urls") or [])
        reference_images = _union_reference_images(brand_id, declared_urls, disk_urls)
        declared_count = sum(1 for r in reference_images if r["provenance"] == "declared")
        disk_count = sum(1 for r in reference_images if r["provenance"] == "disk")
        rows.append(
            {
                "template_id": tid,
                "template_label": tpl.get("label") or meta.get("template_label") or tid,
                "template_name": tpl.get("name") or meta.get("template_name") or tid,
                "section": tpl.get("section") or "Other",
                "canvas": tpl.get("canvas") or "",
                "needs_photo": bool(tpl.get("needs_photo")),
                "template_pack": tpl.get("template_pack") or "",
                "reference_images": reference_images,
                "declared_reference_count": declared_count,
                "disk_reference_count": disk_count,
                "references_undeclared": declared_count == 0 and disk_count > 0,
                "templates_href": f"/results/templates?template={tid}",
            }
        )
    return rows


def _filter_caption(rows: list[dict[str, Any]], mode: str, *, field: str) -> list[dict[str, Any]]:
    if mode == "any":
        return rows
    want = mode == "present"
    return [r for r in rows if bool(r.get("caption_present")) == want]


def _filter_draft_status(rows: list[dict[str, Any]], status: str) -> list[dict[str, Any]]:
    if status == "any":
        return rows
    return [r for r in rows if str(r.get("status") or "") == status]


def _filter_sandbox_status(rows: list[dict[str, Any]], status: str) -> list[dict[str, Any]]:
    if status == "any":
        return rows
    return [r for r in rows if str(r.get("status") or "") == status]


def _draft_counts(rows: list[dict[str, Any]], *, total: int, orphans: int) -> dict[str, Any]:
    by_status: dict[str, int] = {"pending": 0, "approved": 0, "rejected": 0, "archived": 0}
    for r in rows:
        st = str(r.get("status") or "pending")
        if st in by_status:
            by_status[st] += 1
    with_cap = sum(1 for r in rows if r.get("caption_present"))
    with_img = sum(1 for r in rows if r.get("image_present"))
    return {
        "total": total,
        "returned": len(rows),
        "with_caption": with_cap,
        "without_caption": len(rows) - with_cap,
        "with_image": with_img,
        "without_image": len(rows) - with_img,
        "orphans": orphans,
        "by_status": by_status,
    }


def _sandbox_counts(rows: list[dict[str, Any]], *, total: int, receipt_only: int) -> dict[str, Any]:
    by_status: dict[str, int] = {"pending": 0, "dispatched": 0, "failed": 0}
    for r in rows:
        st = str(r.get("status") or "pending")
        if st in by_status:
            by_status[st] += 1
        elif st not in by_status:
            by_status.setdefault(st, 0)
            by_status[st] += 1
    with_cap = sum(1 for r in rows if r.get("caption_present"))
    return {
        "total": total,
        "returned": len(rows),
        "with_caption": with_cap,
        "without_caption": len(rows) - with_cap,
        "by_status": by_status,
        "receipts_without_queue_row": receipt_only,
    }


def _template_counts(rows: list[dict[str, Any]], *, total: int) -> dict[str, Any]:
    ref_images = sum(len(r.get("reference_images") or []) for r in rows)
    declared_only = sum(
        1
        for r in rows
        if (r.get("declared_reference_count") or 0) > 0 and not r.get("references_undeclared")
    )
    disk_only = sum(1 for r in rows if r.get("references_undeclared"))
    without_refs = sum(1 for r in rows if not (r.get("reference_images") or []))
    return {
        "total": total,
        "returned": len(rows),
        "reference_images": ref_images,
        "declared_only": declared_only,
        "disk_only": disk_only,
        "without_references": without_refs,
    }


def build_library_shelf(
    brand_id: str,
    *,
    view: str | None = "all",
    limit: int | None = 200,
    caption_filter: str | None = "any",
    status_filter: str | None = "any",
) -> dict[str, Any]:
    """Aggregate read-only library lanes for one brand."""
    bid = validate_brand_id(brand_id, allow_sentinel=False)
    lane_view = _normalize_view(view)
    cap = _clamp_limit(limit)
    cap_mode = str(caption_filter or "any").lower()
    if cap_mode not in ("any", "present", "absent"):
        cap_mode = "any"
    st_mode = str(status_filter or "any").lower()

    notes: list[str] = []
    truncated = {"drafts": False, "sandbox": False, "templates": False}

    all_drafts = _build_draft_rows(bid) if lane_view in ("all", "drafts") else []
    draft_orphans = sum(1 for r in all_drafts if r.get("orphan"))
    all_drafts = _filter_draft_status(all_drafts, st_mode if lane_view in ("all", "drafts") else "any")
    all_drafts = _filter_caption(all_drafts, cap_mode, field="caption")
    draft_total = len(all_drafts)
    drafts, truncated["drafts"] = _apply_limit(all_drafts, cap)

    all_sandbox: list[dict[str, Any]] = []
    receipt_tail = False
    if lane_view in ("all", "sandbox"):
        all_sandbox, receipt_tail = _build_sandbox_rows(bid)
        if receipt_tail:
            notes.append("receipts scan is tail-capped at 5000 rows")
    all_sandbox = _filter_sandbox_status(
        all_sandbox,
        st_mode if lane_view in ("all", "sandbox") else "any",
    )
    all_sandbox = _filter_caption(all_sandbox, cap_mode, field="caption_preview")
    sandbox_total = len(all_sandbox)
    receipt_only = sum(1 for r in all_sandbox if r.get("receipt_only"))
    sandbox, truncated["sandbox"] = _apply_limit(all_sandbox, cap)

    all_templates = _build_template_rows(bid) if lane_view in ("all", "templates") else []
    template_total = len(all_templates)
    templates, truncated["templates"] = _apply_limit(all_templates, cap)

    payload: dict[str, Any] = {
        "brand_id": bid,
        "generated_at": _utc_now_iso(),
        "counts": {
            "drafts": _draft_counts(drafts, total=draft_total, orphans=draft_orphans),
            "sandbox": _sandbox_counts(sandbox, total=sandbox_total, receipt_only=receipt_only),
            "templates": _template_counts(templates, total=template_total),
        },
        "drafts": drafts,
        "sandbox": sandbox,
        "templates": templates,
        "truncated": truncated,
        "notes": notes,
    }
    return payload
