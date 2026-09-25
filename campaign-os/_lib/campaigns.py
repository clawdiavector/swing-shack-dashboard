"""Campaign umbrellas and Campaign Model v1 provenance helpers."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from _lib.marketing_lanes import (
    delete_campaign,
    get_campaign,
    list_campaigns,
    save_campaign,
)

VALID_ORIGIN_KINDS = frozenset(
    {
        "scout",
        "cadence",
        "moment",
        "product_rotation",
        "holiday",
        "meme_lord",
        "operator",
        "plan_file",
        "legacy",
    }
)
VALID_PROCESSES = frozenset({"standard", "strict", "humour"})

CREATE_PAYLOAD_SCHEMA = "campaign-os/inbox-create-payload/v1"
UNASSIGNED_BUCKET = "unassigned"

_PROCESS_RANK = {"standard": 0, "humour": 1, "strict": 2}


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _create_payload_dir() -> Path:
    d = _data_dir() / "inbox-create-payload"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _payload_path_for_item(item_id: str) -> Path:
    digest = hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:24]
    return _create_payload_dir() / f"{digest}.json"


def validate_origin(origin: Any) -> dict[str, Any]:
    if not isinstance(origin, dict):
        raise ValueError("origin must be an object")
    kind = str(origin.get("kind") or "").strip()
    if kind not in VALID_ORIGIN_KINDS:
        raise ValueError(f"origin.kind '{kind}' invalid; valid: {sorted(VALID_ORIGIN_KINDS)}")
    actor = str(origin.get("actor") or "unknown").strip() or "unknown"
    ref = str(origin.get("ref") or "").strip()
    at = origin.get("at")
    if at is not None:
        at = str(at)
    out: dict[str, Any] = {"kind": kind, "actor": actor, "ref": ref}
    if at:
        out["at"] = at
    return out


def validate_process(process: Any) -> str:
    proc = str(process or "standard").strip().lower()
    if proc not in VALID_PROCESSES:
        raise ValueError(f"process '{proc}' invalid; valid: {sorted(VALID_PROCESSES)}")
    return proc


def default_origin_from_record(record: dict[str, Any]) -> dict[str, Any]:
    created_by = str(record.get("created_by") or "unknown").strip() or "unknown"
    src_origin = str(record.get("source_origin") or "").strip()
    cal_ref = str(record.get("calendar_id") or record.get("event_key") or "").strip()
    kind = "legacy"
    if created_by == "holiday_inject" or src_origin == "deterministic_calendar":
        kind = "holiday"
    elif src_origin == "internal_strategy":
        kind = "plan_file"
    elif src_origin == "external" or created_by.startswith("hermes-scout") or created_by.startswith("cos-"):
        kind = "scout"
    elif created_by in ("operator", "proposal_promote", "manual"):
        kind = "operator"
    origin: dict[str, Any] = {
        "kind": kind,
        "actor": created_by,
        "ref": cal_ref or created_by,
    }
    created_at = record.get("created_at")
    if created_at:
        origin["at"] = str(created_at)
    return origin


def enrich_record_provenance(record: dict[str, Any], brand_id: str | None = None) -> dict[str, Any]:
    """Default pillar_id, origin, process; never invent campaign_id."""
    out = dict(record)
    out.setdefault("reference_images", [])
    if not isinstance(out["reference_images"], list):
        raise ValueError("reference_images must be a list")

    pillars = out.get("pillars") or []
    if not out.get("pillar_id") and isinstance(pillars, list) and len(pillars) == 1:
        only = pillars[0]
        if isinstance(only, str) and only.strip():
            out["pillar_id"] = only.strip()
        elif isinstance(only, dict):
            pid = only.get("pillar_id") or only.get("id")
            if pid:
                out["pillar_id"] = str(pid)

    if out.get("origin"):
        out["origin"] = validate_origin(out["origin"])
    else:
        out["origin"] = default_origin_from_record(out)

    if out.get("process"):
        out["process"] = validate_process(out["process"])
    elif brand_id and out.get("pillar_id"):
        from _lib.marketing_calendar import load_brand_config  # noqa: PLC0415

        cfg = load_brand_config(brand_id)
        pillar = _pillar_by_id(cfg, str(out["pillar_id"]))
        camp = get_campaign(brand_id, str(out["campaign_id"])) if out.get("campaign_id") else None
        out["process"] = resolve_process(pillar, camp)
    else:
        out["process"] = "standard"

    return out


def validate_record_campaign_fields(record: dict[str, Any]) -> None:
    if record.get("origin") is not None:
        validate_origin(record["origin"])
    if record.get("process") is not None:
        validate_process(record["process"])
    refs = record.get("reference_images")
    if refs is not None and not isinstance(refs, list):
        raise ValueError("reference_images must be a list")


def provenance_fields_from_record(record: dict[str, Any]) -> dict[str, Any]:
    origin = record.get("origin") if isinstance(record.get("origin"), dict) else {}
    return {
        "pillar_id": record.get("pillar_id"),
        "campaign_id": record.get("campaign_id"),
        "lane": record.get("lane"),
        "origin": origin,
        "process": record.get("process") or "standard",
        "product_id": record.get("product_id"),
        "product_brand": record.get("product_brand"),
        "reference_images": list(record.get("reference_images") or []),
        "moment_ref": record.get("moment_ref"),
    }


def meta_slim_from_record(record: dict[str, Any]) -> dict[str, Any]:
    fields = provenance_fields_from_record(record)
    refs = fields.get("reference_images") or []
    go_live = record.get("event_start") or record.get("event_date") or record.get("event_window_start")
    return {
        "pillar_id": fields.get("pillar_id"),
        "campaign_id": fields.get("campaign_id"),
        "lane": fields.get("lane"),
        "origin": fields.get("origin"),
        "process": fields.get("process"),
        "event_start": go_live,
        "product_id": fields.get("product_id"),
        "reference_images_count": len(refs) if isinstance(refs, list) else 0,
    }


def _pillar_by_id(cfg: dict[str, Any], pillar_id: str) -> dict[str, Any] | None:
    for pillar in cfg.get("pillars") or []:
        if not isinstance(pillar, dict):
            continue
        pid = str(pillar.get("pillar_id") or pillar.get("id") or "")
        if pid == pillar_id:
            return pillar
    return None


def resolve_process(pillar: dict[str, Any] | None, campaign: dict[str, Any] | None) -> str:
    p_proc = validate_process((pillar or {}).get("process") or "standard")
    if not campaign:
        return p_proc
    c_proc = str(campaign.get("process") or "").strip().lower()
    if c_proc not in VALID_PROCESSES:
        return p_proc
    return c_proc if _PROCESS_RANK[c_proc] >= _PROCESS_RANK[p_proc] else p_proc


def ensure_always_on(brand_id: str, *, dry_run: bool = False) -> list[dict[str, Any]]:
    from _lib.marketing_calendar import load_brand_config, write_brand_config  # noqa: PLC0415

    cfg = load_brand_config(brand_id)
    changes: list[dict[str, Any]] = []
    pillars = cfg.get("pillars") or []
    touched = False
    for pillar in pillars:
        if not isinstance(pillar, dict):
            continue
        pid = str(pillar.get("pillar_id") or pillar.get("id") or "").strip()
        if not pid:
            continue
        camp_id = str(pillar.get("default_campaign_id") or f"{pid}-always-on").strip()
        existing = get_campaign(brand_id, camp_id)
        if not existing:
            payload = {
                "name": f"{pillar.get('name') or pid} always-on",
                "pillar_id": pid,
                "phase": "always_on",
                "lanes": list(pillar.get("lanes") or []),
                "process": pillar.get("process") or "standard",
                "sources": {},
            }
            changes.append({"action": "create_campaign", "campaign_id": camp_id, "pillar_id": pid})
            if not dry_run:
                save_campaign(brand_id, camp_id, payload)
        if pillar.get("default_campaign_id") != camp_id:
            changes.append({"action": "set_default_campaign_id", "pillar_id": pid, "campaign_id": camp_id})
            if not dry_run:
                pillar["default_campaign_id"] = camp_id
                touched = True
    if touched and not dry_run:
        write_brand_config(brand_id, cfg)
    return changes


def active_campaigns(brand_id: str, on_date: date | str | None = None) -> list[dict[str, Any]]:
    day = on_date
    if day is None:
        day = date.today()
    elif isinstance(day, str):
        day = date.fromisoformat(day[:10])
    out: list[dict[str, Any]] = []
    for camp in list_campaigns(brand_id):
        phase = str(camp.get("phase") or "").lower()
        if phase in ("paused", "archived"):
            continue
        if phase == "always_on":
            out.append(camp)
            continue
        start = camp.get("start_date") or camp.get("window", {}).get("start")
        end = camp.get("end_date") or camp.get("window", {}).get("end") or start
        if not start:
            if phase in ("live", "launching"):
                out.append(camp)
            continue
        try:
            cs = date.fromisoformat(str(start)[:10])
            ce = date.fromisoformat(str(end)[:10]) if end else cs
        except ValueError:
            continue
        if cs <= day <= ce:
            out.append(camp)
    return out


def migrate_brand_planning_active_campaigns(brand_id: str, *, dry_run: bool = True) -> list[dict[str, Any]]:
    from _lib.marketing_lanes import _data_root  # noqa: PLC0415

    planning_path = _data_root().parent / "brand-planning" / f"{brand_id}.json"
    bundled = Path(__file__).resolve().parents[2] / "data" / "brand-planning" / f"{brand_id}.json"
    for candidate in (planning_path, bundled):
        if candidate.is_file():
            planning_path = candidate
            break
    if not planning_path.is_file():
        return []
    try:
        planning = json.loads(planning_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    active = planning.get("active_campaigns") or []
    if not isinstance(active, list):
        return []
    changes: list[dict[str, Any]] = []
    pillar_map = {
        "psycho-bunny-launch": "stick-retail",
        "spring-at-stick": "stick-fitting",
    }
    for row in active:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id") or row.get("campaign_id") or "").strip()
        if not cid:
            continue
        if get_campaign(brand_id, cid) and dry_run:
            changes.append({"action": "skip_existing", "campaign_id": cid})
            continue
        if get_campaign(brand_id, cid) and not dry_run:
            continue
        payload = {
            "name": row.get("name") or cid,
            "phase": row.get("phase") or "live",
            "lanes": list(row.get("lanes") or []),
            "pillar_id": row.get("pillar_id") or pillar_map.get(cid),
            "sources": {"brand_planning": True},
        }
        changes.append({"action": "migrate_active_campaign", "campaign_id": cid, "payload": payload})
        if not dry_run:
            save_campaign(brand_id, cid, payload)
    return changes


def inbox_bucket_campaign_id(
    *,
    brand_id: str,
    record: dict[str, Any] | None = None,
    sidecar: dict[str, Any] | None = None,
) -> str:
    for src in (sidecar, record):
        if not isinstance(src, dict):
            continue
        cid = src.get("campaign_id")
        if isinstance(cid, str) and cid.strip():
            return cid.strip()
    return UNASSIGNED_BUCKET


def provenance_for_inbox_item(brand_id: str, item_id: str) -> dict[str, Any]:
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    if item_id.count(":") < 2:
        return {}
    _item_type, bid, cal_id = item_id.split(":", 2)
    if bid != brand_id:
        brand_id = bid
    for record in canonical_records(brand_id):
        rid = str(record.get("calendar_id") or record.get("event_key") or "")
        if rid == cal_id:
            enriched = enrich_record_provenance(dict(record), brand_id)
            fields = provenance_fields_from_record(enriched)
            fields["ref"] = f"inbox/{item_id}"
            return fields
    return {"ref": f"inbox/{item_id}"}


def write_create_payload(*, item_id: str, fields: dict[str, Any]) -> Path:
    path = _payload_path_for_item(item_id)
    payload = {
        "schema": CREATE_PAYLOAD_SCHEMA,
        "item_id": item_id,
        "updated_at": _utc_now_iso(),
        **fields,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def read_create_payload(item_id: str) -> dict[str, Any]:
    path = _payload_path_for_item(item_id)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def merge_provenance_into_sidecar(sidecar: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    out = dict(sidecar)
    for key in (
        "pillar_id",
        "campaign_id",
        "lane",
        "origin",
        "process",
        "product_id",
        "product_brand",
        "reference_images",
        "moment_ref",
    ):
        if key in fields and fields[key] is not None:
            out[key] = fields[key]
    return out


def stamp_provenance_on_asset(asset: dict[str, Any], fields: dict[str, Any]) -> None:
    for key in ("pillar_id", "campaign_id", "lane", "origin", "process"):
        if key in fields and fields[key] is not None:
            asset[key] = fields[key]
