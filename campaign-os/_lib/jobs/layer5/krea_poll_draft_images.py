"""L5 krea_poll_draft_images — poll waiting draft_image rows; write PNG when Krea completes."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

from ..layer1._io import read_json
from _lib.brand_validate import validate_brand_id
from _lib.krea_job_parse import parse_get_job_payload

from .draft_assets import (
    _find_caption_draft_for_item,
    _parse_inbox_ref,
    _read_queue,
    _write_draft,
    _write_queue,
)
from .image_draft_context import build_image_draft_context, image_url_for, primary_channel_for_item

_POLL_FAILED_KEY = "krea_poll_failed"
_DEFAULT_BATCH = 10


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _batch_size() -> int:
    raw = (os.environ.get("KREA_POLL_BATCH_SIZE") or "").strip()
    if not raw:
        return _DEFAULT_BATCH
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return _DEFAULT_BATCH


def _spend_cap_blocks() -> bool:
    from _lib import llm_spend  # noqa: PLC0415
    from .draft_assets import IMAGE_EST_USD  # noqa: PLC0415

    allowed, _reason = llm_spend.check("image", IMAGE_EST_USD)
    return not allowed


def _provider_job_id_from_row(row: dict[str, Any]) -> str | None:
    raw = row.get("provider_job_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    sidecar_path = row.get("router_sidecar_path")
    if isinstance(sidecar_path, str) and sidecar_path.strip():
        path = Path(sidecar_path)
        if path.is_file():
            try:
                meta = json.loads(path.read_text(encoding="utf-8"))
                pj = meta.get("provider_job_id")
                if isinstance(pj, str) and pj.strip():
                    return pj.strip()
            except (OSError, json.JSONDecodeError):
                pass
    return None


def _load_router_sidecar(row: dict[str, Any]) -> dict[str, Any]:
    sidecar_path = row.get("router_sidecar_path")
    if not isinstance(sidecar_path, str) or not sidecar_path.strip():
        return {}
    path = Path(sidecar_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_png_from_url(*, url: str, sidecar_path: Path, brand_id: str) -> tuple[Path | None, bytes]:
    with urllib.request.urlopen(url, timeout=60) as resp:
        raw = resp.read()
        mime = resp.headers.get("Content-Type", "image/png")
    if not raw:
        return None, b""
    save_dir = sidecar_path.parent
    save_dir.mkdir(parents=True, exist_ok=True)
    meta = {}
    if sidecar_path.is_file():
        try:
            meta = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if not isinstance(meta, dict):
                meta = {}
        except (OSError, json.JSONDecodeError):
            meta = {}
    fname = meta.get("saved_filename")
    if not isinstance(fname, str) or not fname.strip():
        safe_brand = re.sub(r"[^a-zA-Z0-9_\-]", "", brand_id)[:64] or "default"
        ext = "png" if "png" in mime else "jpg" if "jpeg" in mime or "jpg" in mime else "png"
        fname = f"gen-{safe_brand}-{int(time.time())}.{ext}"
    out = save_dir / fname
    out.write_bytes(raw)
    meta["saved_filename"] = fname
    meta["bytes_size"] = len(raw)
    meta["krea_result_url"] = url
    meta["saved_at"] = int(time.time())
    sidecar_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out, raw


def _finalize_draft_from_poll(
    row: dict[str, Any],
    *,
    brand_id: str,
    item_id: str,
    image_path: Path,
    router_meta: dict[str, Any],
    cost_est: float,
) -> str | None:
    from _lib import llm_spend  # noqa: PLC0415

    ctx = build_image_draft_context(brand_id, item_id)
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

    image_path_str = str(image_path)
    image_url = image_url_for(brand_id, image_path_str)
    primary_platform = primary_channel_for_item(brand_id, item_id, fallback="instagram")
    provider_job_id = _provider_job_id_from_row(row)
    size = str(row.get("image_size") or router_meta.get("size") or "1024x1024")

    llm_spend.record(
        cost_est,
        route="job:krea_poll_draft_images/image",
        model=str(router_meta.get("model") or "krea"),
        kind="image",
    )

    return _write_draft(
        brand_id=brand_id,
        caption=caption,
        platform=primary_platform,
        source_item_id=item_id,
        image_path=image_path_str,
        image_url=image_url,
        sidecar={
            "action": "draft_image",
            "route": "job:krea_poll_draft_images/image",
            "model": router_meta.get("model"),
            "provider": router_meta.get("provider") or "krea",
            "image_path": image_path_str,
            "image_url": image_url,
            "provider_job_id": provider_job_id,
            "image_size": size,
            "cost_estimate_usd": cost_est,
            "queue_row_id": row.get("id"),
            "prompt": ctx.job,
            "prompt_used": router_meta.get("prompt_used"),
            "sections": cd.get("sections") or [],
            "negative_prompt": cd.get("negative_prompt") or "",
            "model_routing": model_routing,
            "reference_dnas": ctx.lineage.get("reference_meta") or [],
            "product_service_items": ctx.lineage.get("product_meta") or [],
            "brand_bible": ctx.lineage.get("brand_bible") or {},
            "calendar": calendar,
            "router_sidecar_path": row.get("router_sidecar_path"),
            "caption_asset_id": caption_asset_id,
            "context_degraded": ctx.lineage.get("degraded") or [],
        },
    )


def _process_waiting_row(row: dict[str, Any]) -> str:
    """Returns outcome token: completed | still_waiting | failed | skipped."""
    from _lib import krea_mcp  # noqa: PLC0415
    from _lib import llm_spend  # noqa: PLC0415

    job_id = _provider_job_id_from_row(row)
    if not job_id:
        row["status"] = "pending"
        row["note"] = "waiting row missing provider_job_id"
        return "failed"

    brand_raw = row.get("brand")
    try:
        brand_id = validate_brand_id(brand_raw)
    except ValueError:
        row["status"] = "pending"
        row["note"] = "invalid brand on waiting row"
        return "failed"

    item_id = _parse_inbox_ref(str(row.get("payload_ref") or ""))
    if not item_id:
        row["status"] = "pending"
        row["note"] = "waiting row missing inbox ref"
        return "failed"

    sidecar_path_raw = row.get("router_sidecar_path")
    if not isinstance(sidecar_path_raw, str) or not sidecar_path_raw.strip():
        row["status"] = "pending"
        row[_POLL_FAILED_KEY] = True
        row["note"] = "missing router sidecar path"
        return "failed"
    sidecar_path = Path(sidecar_path_raw)
    if sidecar_path.is_file():
        try:
            existing = json.loads(sidecar_path.read_text(encoding="utf-8"))
            fname = existing.get("saved_filename") if isinstance(existing, dict) else None
            if isinstance(fname, str) and fname.strip():
                png = sidecar_path.parent / fname
                if png.is_file() and png.stat().st_size > 0:
                    router_meta = existing if isinstance(existing, dict) else {}
                    est = float(row.get("image_cost_estimate_usd") or router_meta.get("cost_estimate_usd") or 0.04)
                    allowed, _reason = llm_spend.check("image", est)
                    if not allowed:
                        return "skipped"
                    _finalize_draft_from_poll(
                        row,
                        brand_id=brand_id,
                        item_id=item_id,
                        image_path=png,
                        router_meta=router_meta,
                        cost_est=est,
                    )
                    row["status"] = "done"
                    row.pop("note", None)
                    return "completed"
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    poll_resp = krea_mcp.get_job(job_id)
    parsed = parse_get_job_payload(poll_resp)
    status = parsed.get("status") or "unknown"

    if status in ("running", "queued", "pending", "processing", "in_progress"):
        return "still_waiting"

    if status in ("failed", "error", "cancelled", "canceled"):
        row["status"] = "pending"
        row[_POLL_FAILED_KEY] = True
        row["note"] = parsed.get("error") or f"krea job {status}"
        return "failed"

    if status != "completed":
        return "still_waiting"

    urls = parsed.get("result_urls") or []
    if not urls:
        row["status"] = "pending"
        row[_POLL_FAILED_KEY] = True
        row["note"] = "krea completed without result URLs"
        return "failed"

    router_meta = _load_router_sidecar(row)
    est = float(row.get("image_cost_estimate_usd") or router_meta.get("cost_estimate_usd") or 0.04)
    allowed, _reason = llm_spend.check("image", est)
    if not allowed:
        return "skipped"

    png_path, raw = _write_png_from_url(url=urls[0], sidecar_path=sidecar_path, brand_id=brand_id)
    if not png_path or len(raw) == 0:
        row["status"] = "pending"
        row[_POLL_FAILED_KEY] = True
        row["note"] = "krea download returned empty bytes"
        return "failed"

    _finalize_draft_from_poll(
        row,
        brand_id=brand_id,
        item_id=item_id,
        image_path=png_path,
        router_meta=router_meta,
        cost_est=est,
    )
    row["status"] = "done"
    row.pop("note", None)
    row.pop(_POLL_FAILED_KEY, None)
    return "completed"


def run(brand: str | None = None) -> dict[str, Any]:
    """Poll Krea for waiting draft_image rows; never submits new jobs."""
    if brand is not None:
        try:
            brand = validate_brand_id(brand)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    if _spend_cap_blocks():
        return {
            "ok": True,
            "skipped_cap": True,
            "reason": "daily LLM spend cap reached",
            "polled": 0,
        }

    if not read_json("agent-queue.json") and not _read_queue():
        return {"ok": True, "polled": 0, "completed": 0}

    rows = _read_queue()
    waiting = [
        r
        for r in rows
        if str(r.get("action") or "") == "draft_image"
        and str(r.get("status") or "").lower() == "waiting"
        and (brand is None or str(r.get("brand") or "") == brand)
    ]
    waiting = waiting[: _batch_size()]

    completed = 0
    still_waiting = 0
    failed = 0
    skipped = 0

    for row in waiting:
        if _spend_cap_blocks():
            skipped += len(waiting) - (completed + still_waiting + failed + skipped)
            break
        try:
            outcome = _process_waiting_row(row)
        except Exception as exc:  # noqa: BLE001
            row["status"] = "pending"
            row[_POLL_FAILED_KEY] = True
            row["note"] = str(exc)[:200]
            failed += 1
            continue
        if outcome == "completed":
            completed += 1
        elif outcome == "still_waiting":
            still_waiting += 1
        elif outcome == "failed":
            failed += 1
        else:
            skipped += 1

    if rows:
        _write_queue(rows)

    return {
        "ok": True,
        "polled": len(waiting),
        "completed": completed,
        "still_waiting": still_waiting,
        "failed": failed,
        "skipped": skipped,
    }
