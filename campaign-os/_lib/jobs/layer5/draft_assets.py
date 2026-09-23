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

from .image_draft_context import calendar_title_for_item, image_url_for

_DRAFT_HEX_NAME = re.compile(r"^Draft [0-9a-f]{6}$", re.IGNORECASE)
_CAPTION_NAME_MAX = 72

CREATE_ACTIONS = frozenset({"draft_caption", "draft_image", "draft_gbp"})
SLOT_ACTIONS = frozenset({"fill_slot"})
PROCESS_ACTIONS = CREATE_ACTIONS | SLOT_ACTIONS
CAPTION_EST_USD = 0.002
IMAGE_EST_USD = 0.04
GBP_EST_USD = 0.0
VALID_IMAGE_SIZES = frozenset({"1024x1024", "1024x1792", "1792x1024"})


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
    asset_id = _write_draft(
        brand_id=brand_id,
        caption=caption,
        platform="instagram",
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

    try:
        result = generate_image_with_persistence(**gen_kwargs)
    except ImageGenAuthError:
        return None, "missing OPENAI_API_KEY"
    except Exception as exc:  # noqa: BLE001
        return None, _record_error(
            exc,
            context={"brand": brand_id, "item": item_id, "step": "generate_image_with_persistence"},
        )

    llm_spend.write_approval_receipt(
        route="job:draft_assets",
        estimate_usd=est,
        brand_id=brand_id,
    )
    llm_spend.record(
        est,
        route="job:draft_assets/image",
        model=getattr(result, "model", None),
        kind="image",
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
    image_url = image_url_for(brand_id, image_path_str)
    def _result_str(attr: str) -> str | None:
        val = getattr(result, attr, None)
        return val if isinstance(val, str) else None

    asset_id = _write_draft(
        brand_id=brand_id,
        caption=caption,
        platform="instagram",
        source_item_id=item_id,
        image_path=image_path_str,
        image_url=image_url,
        sidecar={
            "action": "draft_image",
            "route": "job:draft_assets/image",
            "model": _result_str("model"),
            "provider": _result_str("provider"),
            "image_path": image_path_str,
            "image_url": image_url,
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
    drafted = 0
    skipped = 0
    errors: list[str] = []
    stop_cap = False
    stop_auth = False
    rows: list[dict[str, Any]] = []

    try:
        _backfill_draft_names(brand)
        rows = _read_queue()
        pending = [
            r
            for r in rows
            if str(r.get("status") or "").lower() == "pending"
            and str(r.get("action") or "") in PROCESS_ACTIONS
            and (brand is None or str(r.get("brand") or "") == brand)
        ]

        for row in pending:
            try:
                if stop_cap or stop_auth:
                    skipped += 1
                    continue

                brand_raw = row.get("brand")
                action = str(row.get("action") or "")

                try:
                    brand_id = validate_brand_id(brand_raw)
                except ValueError:
                    skipped += 1
                    continue

                item_id: Optional[str] = None
                if action in SLOT_ACTIONS:
                    slot = _parse_slot_ref(str(row.get("payload_ref") or ""))
                    if not slot:
                        skipped += 1
                        continue
                    slot_brand, slot_date, slot_pillar = slot
                    if slot_brand != brand_id:
                        skipped += 1
                        continue
                    item_id = _resolve_slot_calendar_item(brand_id, slot_date, slot_pillar)
                    if not item_id:
                        skipped += 1
                        continue
                else:
                    item_id = _parse_inbox_ref(str(row.get("payload_ref") or ""))
                    if not item_id:
                        skipped += 1
                        continue

                if not _is_inbox_item_approved(item_id):
                    skipped += 1
                    continue

                asset_id: Optional[str] = None
                err: Optional[str] = None

                if action in SLOT_ACTIONS or action == "draft_caption":
                    asset_id, err = _process_caption_row(row, item_id=item_id, brand_id=brand_id)
                elif action == "draft_image":
                    asset_id, err = _process_image_row(row, item_id=item_id, brand_id=brand_id)
                elif action == "draft_gbp":
                    asset_id, err = _process_gbp_row(row, item_id=item_id, brand_id=brand_id)
                else:
                    skipped += 1
                    continue

                if err:
                    if "daily LLM spend cap reached" in err:
                        stop_cap = True
                        errors.append(err)
                        skipped += 1
                        continue
                    if "missing OPENAI_API_KEY" in err:
                        stop_auth = True
                        errors.append(err)
                        skipped += 1
                        continue
                    skipped += 1
                    errors.append(err)
                    continue

                if asset_id:
                    row["status"] = "done"
                    drafted += 1
                else:
                    skipped += 1
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
    except Exception as exc:  # noqa: BLE001
        label = _record_error(exc, context={"step": "run"})
        return {"ok": False, "error": label, "drafted": drafted, "skipped": skipped}
    finally:
        if rows:
            _write_queue(rows)

    if stop_auth:
        return {
            "ok": False,
            "error": "missing OPENAI_API_KEY",
            "drafted": drafted,
            "skipped": skipped,
        }
    if stop_cap:
        return {
            "ok": False,
            "error": "daily LLM spend cap reached",
            "drafted": drafted,
            "skipped": skipped,
        }
    if errors and drafted == 0:
        return {
            "ok": False,
            "error": errors[0],
            "drafted": drafted,
            "skipped": skipped,
        }

    return {"ok": True, "drafted": drafted, "skipped": skipped, "rows": drafted}
