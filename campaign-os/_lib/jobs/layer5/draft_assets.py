"""L5 draft_assets job — assemble drafts from approved inbox queue rows."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..errors import describe_exception
from ..layer1._io import atomic_write, read_json

CREATE_ACTIONS = frozenset({"draft_caption", "draft_image", "draft_gbp"})
CAPTION_EST_USD = 0.002
IMAGE_EST_USD = 0.04
GBP_EST_USD = 0.0
VALID_IMAGE_SIZES = frozenset({"1024x1024", "1024x1792", "1792x1024"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

        for record in canonical_records(brand_id):
            rid = str(record.get("calendar_id") or record.get("event_key") or "")
            if rid == cal_id:
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


def _write_draft(
    *,
    brand_id: str,
    caption: str,
    platform: str,
    source_item_id: str,
    sidecar: dict[str, Any],
) -> str:
    from _lib.unified_inbox import _load_campaign_data, _write_campaign_data  # noqa: PLC0415

    campaign_id = _resolve_campaign_id(brand_id)
    asset_id = f"draft-{uuid.uuid4().hex[:12]}"
    now = _utc_now_iso()

    data = _load_campaign_data()
    campaign = data.setdefault("campaigns", {}).setdefault(campaign_id, {})
    campaign.setdefault("identity", {"name": f"L5 drafts ({brand_id})", "brand": brand_id})
    assets = campaign.setdefault("assets", {})
    assets[asset_id] = {
        "name": sidecar.get("title") or f"Draft {asset_id[-6:]}",
        "caption": caption,
        "approvalStatus": "draft",
        "platform": platform,
        "updatedAt": now,
        "draft_ref": f"draft-assets/{asset_id}.json",
    }
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
        },
    )
    return asset_id, None


def _process_image_row(
    row: dict[str, Any],
    *,
    item_id: str,
    brand_id: str,
) -> tuple[Optional[str], Optional[str]]:
    from _lib import llm_spend  # noqa: PLC0415
    from _lib.image_gen_router import ImageGenAuthError, generate_image_with_persistence  # noqa: PLC0415

    size = "1024x1024"
    est = llm_spend.modelled_image_cost(size)
    allowed, reason = llm_spend.check("image", est)
    if not allowed:
        return None, "daily LLM spend cap reached" if "cap" in reason.lower() else reason

    output_base = str(_data_dir() / "draft-assets" / "images")
    try:
        result = generate_image_with_persistence(
            brand_id=brand_id,
            prompt=f"Social image for approved inbox item {item_id}",
            size=size,
            output_base=output_base,
        )
    except ImageGenAuthError:
        return None, "missing OPENAI_API_KEY"
    except Exception as exc:  # noqa: BLE001
        return None, describe_exception(exc)

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
    caption = f"Image draft for {item_id}"
    asset_id = _write_draft(
        brand_id=brand_id,
        caption=caption,
        platform="instagram",
        source_item_id=item_id,
        sidecar={
            "action": "draft_image",
            "route": "job:draft_assets/image",
            "model": getattr(result, "model", None),
            "provider": getattr(result, "provider", None),
            "image_path": str(image_path) if image_path else None,
            "image_size": size,
            "cost_estimate_usd": est,
            "queue_row_id": row.get("id"),
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
        },
    )
    return asset_id, None


def run() -> dict[str, Any]:
    """Process pending L5 queue rows into draft_asset inbox rows."""
    drafted = 0
    skipped = 0
    errors: list[str] = []
    stop_cap = False
    stop_auth = False

    try:
        rows = _read_queue()
        pending = [
            r
            for r in rows
            if str(r.get("status") or "").lower() == "pending"
            and str(r.get("action") or "") in CREATE_ACTIONS
        ]

        for row in pending:
            if stop_cap or stop_auth:
                skipped += 1
                continue

            item_id = _parse_inbox_ref(str(row.get("payload_ref") or ""))
            brand_id = str(row.get("brand") or "")
            action = str(row.get("action") or "")

            if not item_id or not brand_id:
                skipped += 1
                continue

            if not _is_inbox_item_approved(item_id):
                skipped += 1
                continue

            asset_id: Optional[str] = None
            err: Optional[str] = None

            if action == "draft_caption":
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
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": describe_exception(exc), "drafted": drafted, "skipped": skipped}
