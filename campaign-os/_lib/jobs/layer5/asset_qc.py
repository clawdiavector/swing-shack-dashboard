"""L5 asset_qc job — deterministic QC on draft-assets sidecars."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..errors import describe_exception
from ..layer1._io import atomic_write
from _lib.brand_validate import validate_brand_id

VALID_IMAGE_SIZES = frozenset({"1024x1024", "1024x1792", "1792x1024"})
REQUIRED_FIELDS = frozenset(
    {"schema", "asset_id", "campaign_id", "brand_id", "source_inbox_item_id", "created_at"}
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _l6_enqueue_enabled() -> bool:
    raw = (os.environ.get("CAMPAIGN_OS_L6_ENQUEUE") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _load_sidecars() -> list[tuple[Path, dict[str, Any]]]:
    root = _data_dir() / "draft-assets"
    if not root.is_dir():
        return []
    out: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            out.append((path, data))
    return out


def _reject_asset(campaign_id: str, asset_id: str, reason: str) -> None:
    from _lib.unified_inbox import _load_campaign_data, _write_campaign_data  # noqa: PLC0415

    data = _load_campaign_data()
    campaign = (data.get("campaigns") or {}).get(campaign_id)
    if not campaign:
        return
    asset = (campaign.get("assets") or {}).get(asset_id)
    if not asset:
        return
    now = _utc_now_iso()
    asset["approvalStatus"] = "rejected"
    asset["rejectionReason"] = reason
    asset["updatedAt"] = now
    campaign["updatedAt"] = now
    _write_campaign_data(data)


def _check_sidecar(sidecar: dict[str, Any], caption: str) -> list[str]:
    from _lib.p11_context_engine import _extract_banned_terms  # noqa: PLC0415

    issues: list[str] = []
    missing = REQUIRED_FIELDS - set(sidecar.keys())
    if missing:
        issues.append(f"missing fields: {', '.join(sorted(missing))}")

    brand_id = str(sidecar.get("brand_id") or "")
    if not brand_id:
        issues.append("invalid brand_id")
    else:
        try:
            validate_brand_id(brand_id)
        except ValueError:
            issues.append("invalid brand_id")
    text = caption or ""
    if text.startswith("[LLM unavailable"):
        issues.append("placeholder caption from unavailable LLM")

    banned = _extract_banned_terms(brand_id) if brand_id else []
    lower = text.lower()
    for term in banned:
        if term and term.lower() in lower:
            issues.append(f"banned term: {term}")

    action = str(sidecar.get("action") or "")
    if action == "draft_image":
        size = str(sidecar.get("image_size") or "")
        if size and size not in VALID_IMAGE_SIZES:
            issues.append(f"invalid image aspect: {size}")

    cost = sidecar.get("cost_estimate_usd")
    if cost is None and action in ("draft_caption", "draft_image"):
        issues.append("cost_estimate_usd not recorded")

    return issues


def _maybe_enqueue_publish_request(
    *,
    sidecar: dict[str, Any],
    asset: dict[str, Any],
    caption: str,
    asset_id: str,
) -> None:
    if not _l6_enqueue_enabled():
        return
    brand_id = str(sidecar.get("brand_id") or "")
    if not brand_id:
        return
    from _lib import publish_sandbox  # noqa: PLC0415

    publish_sandbox.enqueue_for_intended_channels(
        brand_id=brand_id,
        caption_preview=caption,
        inbox_item_id=str(sidecar.get("source_inbox_item_id") or ""),
        asset_id=asset_id,
    )


def run() -> dict[str, Any]:
    """Run deterministic QC; reject failing assets in campaign-data.json."""
    try:
        from _lib import llm_spend  # noqa: PLC0415
        from _lib.unified_inbox import _load_campaign_data  # noqa: PLC0415

        spend = llm_spend.status()
        sidecars = _load_sidecars()
        campaign_data = _load_campaign_data()
        checked = 0
        passed = 0
        failed = 0
        results: list[dict[str, Any]] = []

        for path, sidecar in sidecars:
            asset_id = str(sidecar.get("asset_id") or path.stem)
            campaign_id = str(sidecar.get("campaign_id") or "")
            caption = ""
            campaign = (campaign_data.get("campaigns") or {}).get(campaign_id) or {}
            asset = (campaign.get("assets") or {}).get(asset_id) or {}
            caption = str(asset.get("caption") or "")

            issues = _check_sidecar(sidecar, caption)
            checked += 1
            verdict = "pass" if not issues else "fail"
            if verdict == "pass":
                passed += 1
                _maybe_enqueue_publish_request(
                    sidecar=sidecar,
                    asset=asset,
                    caption=caption,
                    asset_id=asset_id,
                )
            else:
                failed += 1
                _reject_asset(campaign_id, asset_id, "; ".join(issues))

            sidecar["qc"] = {
                "verdict": verdict,
                "issues": issues,
                "checked_at": _utc_now_iso(),
                "spend_reconciled": not spend.get("broken"),
            }
            atomic_write(f"draft-assets/{asset_id}.json", sidecar)
            results.append({"asset_id": asset_id, "verdict": verdict, "issues": issues})

        summary = {
            "schema": "campaign-os/asset-qc/v1",
            "generated_at": _utc_now_iso(),
            "checked": checked,
            "passed": passed,
            "failed": failed,
            "spend": {
                "spent_usd": spend.get("spent_usd"),
                "cap_usd": spend.get("cap_usd"),
                "calls": spend.get("calls"),
            },
            "results": results,
        }
        atomic_write("asset-qc.json", summary)
        return {"ok": True, "rows": checked, "passed": passed, "failed": failed}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": describe_exception(exc)}
