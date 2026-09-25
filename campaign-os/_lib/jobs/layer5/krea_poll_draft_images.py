"""L5 krea_poll_draft_images — poll waiting draft_image rows; write PNG when Krea completes."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..errors import describe_exception
from ..layer1._io import read_json
from _lib.brand_validate import validate_brand_id
from _lib.krea_job_parse import parse_get_job_payload

from . import image_jobs_state
from .draft_assets import (
    _moment_has_image,
    _parse_inbox_ref,
    _read_queue,
    _write_draft,
    _write_queue,
)
from .image_draft_context import build_image_draft_context, image_url_for, primary_channel_for_item

_DEFAULT_MAX_ROWS = 12
_DEFAULT_BUDGET_S = 150
_DEFAULT_STALE_HOURS = 24


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _max_rows() -> int:
    raw = (os.environ.get("KREA_POLL_MAX_ROWS") or os.environ.get("KREA_POLL_BATCH_SIZE") or "").strip()
    if not raw:
        return _DEFAULT_MAX_ROWS
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return _DEFAULT_MAX_ROWS


def _poll_budget_s() -> float:
    raw = (os.environ.get("KREA_POLL_BUDGET_S") or "").strip()
    if not raw:
        return float(_DEFAULT_BUDGET_S)
    try:
        return max(30.0, float(raw))
    except ValueError:
        return float(_DEFAULT_BUDGET_S)


def _stale_hours() -> float:
    raw = (os.environ.get("KREA_POLL_STALE_HOURS") or "").strip()
    if not raw:
        return float(_DEFAULT_STALE_HOURS)
    try:
        return max(1.0, float(raw))
    except ValueError:
        return float(_DEFAULT_STALE_HOURS)


def _safe_token(value: str, *, limit: int = 120) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "", value)[:limit] or "x"


def _krea_artifact_paths(brand_id: str, job_id: str) -> tuple[Path, Path]:
    safe_brand = _safe_token(brand_id, limit=64)
    safe_job = _safe_token(job_id, limit=120)
    base = _data_dir() / "draft-assets" / "images" / safe_brand / "images"
    png = base / f"krea-{safe_brand}-{safe_job}.png"
    meta = base / f"krea-{safe_brand}-{safe_job}.png.meta.json"
    return png, meta


def _write_krea_png_and_sidecar(
    *,
    brand_id: str,
    job_id: str,
    raw: bytes,
    url: str,
    est_usd: float,
    size: str,
) -> Path:
    png_path, meta_path = _krea_artifact_paths(brand_id, job_id)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(raw)
    sidecar = {
        "provider": "krea",
        "provider_job_id": job_id,
        "brand_id": brand_id,
        "bytes_size": len(raw),
        "saved_filename": png_path.name,
        "krea_result_url": url,
        "size": size,
        "cost_estimate_usd": est_usd,
        "saved_at": int(time.time()),
    }
    meta_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    return png_path


def _finalize_draft_from_poll(
    *,
    brand_id: str,
    item_id: str,
    image_path: Path,
    job_entry: dict[str, Any],
    queue_row_id: str | None,
) -> str | None:
    ctx = build_image_draft_context(brand_id, item_id)
    calendar = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
    title = str(calendar.get("title") or "")
    angle = str(calendar.get("angle") or "")
    from .draft_assets import _find_caption_draft_for_item  # noqa: PLC0415

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
    size = str(job_entry.get("size") or "1024x1024")
    est = float(job_entry.get("est_usd") or 0.04)
    job_id = str(job_entry.get("job_id") or "")

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
            "model": "krea",
            "provider": "krea",
            "image_path": image_path_str,
            "image_url": image_url,
            "provider_job_id": job_id,
            "image_size": size,
            "cost_estimate_usd": est,
            "queue_row_id": queue_row_id,
            "prompt": ctx.job,
            "sections": cd.get("sections") or [],
            "negative_prompt": cd.get("negative_prompt") or "",
            "model_routing": model_routing,
            "reference_dnas": ctx.lineage.get("reference_meta") or [],
            "product_service_items": ctx.lineage.get("product_meta") or [],
            "brand_bible": ctx.lineage.get("brand_bible") or {},
            "calendar": calendar,
            "caption_asset_id": caption_asset_id,
            "context_degraded": ctx.lineage.get("degraded") or [],
        },
    )


def _record_poll_spend(item_id: str, job_entry: dict[str, Any], *, brand_id: str) -> None:
    from _lib import llm_spend  # noqa: PLC0415

    if image_jobs_state.is_settled(item_id):
        return
    est = float(job_entry.get("est_usd") or 0.04)
    llm_spend.record(
        est,
        route="job:krea_poll_draft_images/image",
        model="krea",
        kind="image",
        brand_id=brand_id,
    )
    image_jobs_state.mark_settled(item_id)


def _complete_row(
    row: dict[str, Any],
    *,
    brand_id: str,
    item_id: str,
    job_entry: dict[str, Any],
    png_path: Path,
) -> None:
    if _moment_has_image(brand_id, item_id):
        row["status"] = "done"
        row.pop("note", None)
        image_jobs_state.drop_entry(item_id)
        return
    _record_poll_spend(item_id, job_entry, brand_id=brand_id)
    _finalize_draft_from_poll(
        brand_id=brand_id,
        item_id=item_id,
        image_path=png_path,
        job_entry=job_entry,
        queue_row_id=str(row.get("id") or "") or None,
    )
    row["status"] = "done"
    row.pop("note", None)
    image_jobs_state.drop_entry(item_id)


def _is_stale(entry: dict[str, Any]) -> bool:
    submitted = image_jobs_state.parse_submitted_at(entry)
    if submitted is None:
        return False
    age = datetime.now(timezone.utc) - submitted
    return age > timedelta(hours=_stale_hours())


def _process_waiting_row(row: dict[str, Any], *, deadline: float) -> str:
    """Returns: completed | still_running | failed | stale | skipped | deadline."""
    if time.monotonic() >= deadline:
        return "deadline"

    from _lib import krea_mcp  # noqa: PLC0415

    item_id = _parse_inbox_ref(str(row.get("payload_ref") or ""))
    if not item_id:
        row["status"] = "pending"
        row["note"] = "waiting row missing inbox ref"
        return "failed"

    job_entry = image_jobs_state.get_entry(item_id)
    if not job_entry:
        row["status"] = "pending"
        row["note"] = "waiting row missing image job state"
        return "failed"

    brand_raw = row.get("brand") or job_entry.get("brand")
    try:
        brand_id = validate_brand_id(brand_raw)
    except ValueError:
        row["status"] = "pending"
        row["note"] = "invalid brand on waiting row"
        return "failed"

    job_id = str(job_entry.get("job_id") or "").strip()
    if not job_id:
        row["status"] = "pending"
        row["note"] = "missing job_id in state"
        return "failed"

    if _is_stale(job_entry):
        row["status"] = "pending"
        row["note"] = "krea job stale — exceeded poll window"
        image_jobs_state.update_poll(item_id, last_status="stale")
        image_jobs_state.drop_entry(item_id)
        return "stale"

    png_path, _meta = _krea_artifact_paths(brand_id, job_id)
    if png_path.is_file() and png_path.stat().st_size > 0:
        _complete_row(row, brand_id=brand_id, item_id=item_id, job_entry=job_entry, png_path=png_path)
        return "completed"

    if _moment_has_image(brand_id, item_id):
        row["status"] = "done"
        image_jobs_state.drop_entry(item_id)
        return "completed"

    poll_resp = krea_mcp.get_job(job_id)
    parsed = parse_get_job_payload(poll_resp)
    status = str(parsed.get("status") or "unknown").lower()
    image_jobs_state.update_poll(item_id, last_status=status)

    if status in ("failed", "error", "cancelled", "canceled"):
        row["status"] = "pending"
        row["note"] = parsed.get("error") or f"krea job {status}"
        image_jobs_state.update_poll(item_id, last_status="failed")
        return "failed"

    if status != "completed":
        return "still_running"

    urls = parsed.get("result_urls") or []
    if not urls:
        row["status"] = "pending"
        row["note"] = "krea completed without result URLs"
        image_jobs_state.update_poll(item_id, last_status="failed")
        return "failed"

    with urllib.request.urlopen(urls[0], timeout=30) as resp:
        raw = resp.read()
    if not raw:
        row["status"] = "pending"
        row["note"] = "krea download returned empty bytes"
        return "failed"

    size = str(job_entry.get("size") or "1024x1024")
    est = float(job_entry.get("est_usd") or 0.04)
    out_path = _write_krea_png_and_sidecar(
        brand_id=brand_id,
        job_id=job_id,
        raw=raw,
        url=urls[0],
        est_usd=est,
        size=size,
    )
    _complete_row(row, brand_id=brand_id, item_id=item_id, job_entry=job_entry, png_path=out_path)
    return "completed"


def run(brand: str | None = None) -> dict[str, Any]:
    """Poll Krea for waiting draft_image rows; never submits new jobs."""
    if brand is not None:
        try:
            brand = validate_brand_id(brand)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

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
    waiting = waiting[: _max_rows()]

    deadline = time.monotonic() + _poll_budget_s()
    completed = 0
    still_running = 0
    failed = 0
    stale = 0
    skipped = 0
    deadline_hit = False

    try:
        for row in waiting:
            try:
                outcome = _process_waiting_row(row, deadline=deadline)
            except Exception as exc:  # noqa: BLE001
                row["status"] = "pending"
                row["note"] = str(exc)[:200]
                failed += 1
                continue
            if outcome == "deadline":
                deadline_hit = True
                break
            if outcome == "completed":
                completed += 1
            elif outcome == "still_running":
                still_running += 1
            elif outcome == "stale":
                stale += 1
            elif outcome == "failed":
                failed += 1
            else:
                skipped += 1
    except Exception as exc:  # noqa: BLE001
        if rows:
            _write_queue(rows)
        return {"ok": False, "error": describe_exception(exc)}

    if rows:
        _write_queue(rows)

    return {
        "ok": True,
        "polled": len(waiting),
        "completed": completed,
        "still_running": still_running,
        "failed": failed,
        "stale": stale,
        "skipped": skipped,
        "deadline_hit": deadline_hit,
        "skipped_cap": 0,
    }
