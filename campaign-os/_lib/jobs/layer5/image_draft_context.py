"""Build rich creative context for L5 draft_image rows — pure, no writes."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

VALID_ASPECTS = frozenset({"1024x1024", "1024x1792", "1792x1024"})
_GENERIC_JOB = "Social image for approved inbox item"


def _brand_root() -> Path:
    """Resolve brand-directory root from DATA_DIR / BUNDLED_DATA_DIR only."""
    candidates: list[Path] = []
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    if bundled:
        candidates.append(Path(bundled))
    candidates.append(Path(os.environ.get("DATA_DIR") or "/data/campaign-os"))
    for base in candidates:
        if base.exists():
            return base / "brand-directory"
    return candidates[-1] / "brand-directory"


def _parse_item_id(item_id: str) -> tuple[str, Optional[str], Optional[str]]:
    if item_id.count(":") < 2:
        return item_id.split(":", 1)[0] if ":" in item_id else item_id, None, None
    item_type, brand_id, key = item_id.split(":", 2)
    return item_type, brand_id, key


def _first_str(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, list) and val:
            first = val[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
    return ""


def _resolve_pillar_name(brand_id: str, pillar_id: str) -> str:
    if not pillar_id:
        return ""
    try:
        from _lib.marketing_calendar import load_brand_config  # noqa: PLC0415

        cfg = load_brand_config(brand_id)
        for pillar in cfg.get("pillars") or []:
            if not isinstance(pillar, dict):
                continue
            pid = str(pillar.get("pillar_id") or pillar.get("id") or "")
            if pid == pillar_id:
                return str(pillar.get("name") or pillar_id)
    except Exception:
        pass
    return pillar_id


def _build_job_line(
    *,
    title: str,
    pillar_name: str,
    angle: str,
    event_start: str,
) -> str:
    subject = title or "calendar item"
    parts = [f'Social image for "{subject}"']
    if pillar_name:
        parts.append(f"— {pillar_name} pillar")
    if angle:
        parts.append(f"Angle: {angle}.")
    if event_start:
        try:
            ev = datetime.fromisoformat(event_start.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if ev.tzinfo is None:
                ev = ev.replace(tzinfo=timezone.utc)
            delta_days = (ev - now).days
            if -30 <= delta_days <= 365:
                parts.append(f"Event {ev.date().isoformat()}.")
        except Exception:
            pass
    job = " ".join(parts).strip()
    return job[:300] if job else _GENERIC_JOB


def _select_aspect(record: dict[str, Any], *, title: str, angle: str) -> str:
    record_type = str(record.get("type") or "").lower()
    text = f"{title} {angle}".lower()
    if record_type == "moment" or any(w in text for w in ("story", "reel", "vertical")):
        return "1024x1792"
    if record_type == "campaign" and any(w in text for w in ("banner", "wide", "landscape")):
        return "1792x1024"
    return "1024x1024"


def _load_reference_records(brand_id: str, root: Path) -> list[dict[str, Any]]:
    refs_dir = root / brand_id / "references"
    if not refs_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in refs_dir.glob("*.reference-dna.json"):
        try:
            import json

            row = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(row, dict):
                out.append(row)
        except Exception:
            continue
    return out


def _load_product_library(brand_id: str, root: Path) -> dict[str, Any]:
    lib_path = root / brand_id / "product-library.json"
    if not lib_path.is_file():
        return {"products": [], "services": []}
    try:
        import json

        data = json.loads(lib_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"products": [], "services": []}


def _select_reference(
    brand_id: str,
    *,
    query: str,
    root: Path,
    degraded: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Optional[dict[str, Any]]]:
    from _lib import social_history  # noqa: PLC0415

    meta: list[dict[str, Any]] = []
    try:
        hits = social_history.search_creative(
            brand_id,
            query,
            sources=["curated", "published"],
            limit=10,
        )
        results = hits.get("results") if isinstance(hits, dict) else []
        if not isinstance(results, list):
            results = []
        learnable = [
            hit
            for hit in results
            if isinstance(hit, dict)
            and social_history.is_learnable(
                brand_id,
                str(hit.get("source") or ""),
                str(hit.get("asset_id") or ""),
            )
        ]
        if not learnable:
            degraded.append({"source": "reference", "reason": "no learnable curated/published match"})
            return [], meta, {"selected": None, "reason": "no learnable curated/published match"}

        top = max(learnable, key=lambda h: float(h.get("score") or 0))
        asset_id = str(top.get("asset_id") or "")
        dna_records = _load_reference_records(brand_id, root)
        matched = next(
            (row for row in dna_records if str(row.get("source_filename") or "") == asset_id),
            None,
        )
        if not matched:
            degraded.append({"source": "reference", "reason": "learnable hit without matching reference DNA"})
            return [], meta, {
                "selected": None,
                "reason": "learnable hit without matching reference DNA",
                "asset_id": asset_id,
            }

        meta.append(
            {
                "ref_id": matched.get("ref_id"),
                "source_filename": matched.get("source_filename") or asset_id,
                "label": matched.get("label") or matched.get("filename") or asset_id,
                "score": top.get("score"),
                "classification": top.get("classification"),
                "match_reason": top.get("match_reason"),
            }
        )
        return [matched], meta, {"selected": matched.get("ref_id"), "asset_id": asset_id}
    except Exception as exc:
        degraded.append({"source": "reference", "reason": str(exc)[:120]})
        return [], meta, {"selected": None, "reason": "reference lookup failed"}


def _item_matches_calendar_product(item: dict[str, Any], token: str) -> bool:
    token_l = token.lower()
    for key in ("id", "name", "category"):
        val = str(item.get(key) or "").lower()
        if val and (val == token_l or token_l in val or val in token_l):
            return True
    return False


def _select_products(
    brand_id: str,
    *,
    record: dict[str, Any],
    title: str,
    angle: str,
    root: Path,
    degraded: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    meta: list[dict[str, Any]] = []
    try:
        lib = _load_product_library(brand_id, root)
        candidates: list[tuple[str, dict[str, Any]]] = []
        for kind in ("products", "services"):
            for item in lib.get(kind) or []:
                if isinstance(item, dict):
                    candidates.append((kind[:-1], item))

        calendar_products = record.get("products") or []
        selected: list[dict[str, Any]] = []
        if isinstance(calendar_products, list) and calendar_products:
            for token in calendar_products:
                token_s = str(token)
                for kind, item in candidates:
                    if _item_matches_calendar_product(item, token_s):
                        selected.append(item)
                        break

        if not selected:
            text = f"{title} {angle}".lower()
            for kind, item in candidates:
                name = str(item.get("name") or "").lower()
                category = str(item.get("category") or "").lower()
                if (name and name in text) or (category and category in text):
                    selected.append(item)

        selected = selected[:2]
        for item in selected:
            kind = "product" if str(item.get("id", "")).startswith("product-") else "service"
            meta.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "category": item.get("category"),
                    "kind": kind,
                }
            )
        return selected[:1], meta
    except Exception as exc:
        degraded.append({"source": "product", "reason": str(exc)[:120]})
        return [], meta


def _resolve_calendar_record(brand_id: str, cal_id: str) -> Optional[dict[str, Any]]:
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    for record in canonical_records(brand_id):
        rid = str(record.get("calendar_id") or record.get("event_key") or "")
        if rid == cal_id:
            return record
    return None


@dataclass
class ImageDraftContext:
    job: str
    refs: list[dict[str, Any]] = field(default_factory=list)
    products: list[dict[str, Any]] = field(default_factory=list)
    aspect: str = "1024x1024"
    lineage: dict[str, Any] = field(default_factory=dict)


def build_image_draft_context(brand_id: str, inbox_item_id: str) -> ImageDraftContext:
    """Assemble calendar-driven creative context for draft_image (never raises)."""
    degraded: list[dict[str, str]] = []
    root = _brand_root()
    item_type, parsed_brand, cal_id = _parse_item_id(inbox_item_id)
    brand = parsed_brand or brand_id

    if item_type != "calendar_candidate" or not cal_id:
        job = f"{_GENERIC_JOB} {inbox_item_id}".strip()
        cd = _compose_cd(brand, job, None, None, degraded)
        return ImageDraftContext(
            job=job,
            aspect="1024x1024",
            lineage={
                "source": "proposal" if item_type == "proposal" else item_type,
                "degraded": degraded,
                "creative_director": cd,
                "calendar": {},
                "reference": {"selected": None},
                "reference_meta": [],
                "product_meta": [],
                "brand_bible": _brand_bible_lineage(brand, [], degraded),
            },
        )

    record = _resolve_calendar_record(brand, cal_id)
    if not record:
        job = f"{_GENERIC_JOB} {inbox_item_id}".strip()
        degraded.append({"source": "calendar", "reason": "no matching calendar record"})
        cd = _compose_cd(brand, job, None, None, degraded)
        return ImageDraftContext(
            job=job,
            aspect="1024x1024",
            lineage={
                "source": "calendar_candidate",
                "degraded": degraded,
                "creative_director": cd,
                "calendar": {"calendar_id": cal_id},
                "reference": {"selected": None},
                "reference_meta": [],
                "product_meta": [],
                "brand_bible": _brand_bible_lineage(brand, [], degraded),
            },
        )

    title = _first_str(record, "title", "event_key", "calendar_id")
    angle = _first_str(record, "angle", "suggested_angles", "relevance_reason")
    pillar_id = _first_str(record, "pillar", "pillars")
    pillar_name = _resolve_pillar_name(brand, pillar_id)
    event_start = _first_str(record, "event_start", "event_window_start", "event_date")
    job = _build_job_line(title=title, pillar_name=pillar_name, angle=angle, event_start=event_start)
    aspect = _select_aspect(record, title=title, angle=angle)
    if aspect not in VALID_ASPECTS:
        aspect = "1024x1024"

    query = " ".join(w for w in re.split(r"[^a-zA-Z0-9]+", f"{angle} {title}") if w).strip()
    refs, ref_meta, ref_info = _select_reference(brand, query=query or title, root=root, degraded=degraded)
    products, product_meta = _select_products(
        brand,
        record=record,
        title=title,
        angle=angle,
        root=root,
        degraded=degraded,
    )
    brand_bible = _brand_bible_lineage(brand, products, degraded)
    cd = _compose_cd(brand, job, refs[0] if refs else None, products[0] if products else None, degraded)

    calendar_lineage = {
        "calendar_id": cal_id,
        "title": title,
        "pillar": pillar_name or pillar_id,
        "angle": angle,
        "event_start": event_start,
        "event_lifecycle": record.get("event_lifecycle"),
        "type": record.get("type"),
    }

    return ImageDraftContext(
        job=job,
        refs=refs,
        products=products,
        aspect=aspect,
        lineage={
            "source": "calendar_candidate",
            "calendar": calendar_lineage,
            "lifecycle": record.get("event_lifecycle"),
            "degraded": degraded,
            "creative_director": cd,
            "reference": ref_info or {"selected": None},
            "reference_meta": ref_meta,
            "product_meta": product_meta,
            "brand_bible": brand_bible,
        },
    )


def _brand_bible_lineage(
    brand_id: str,
    products: list[dict[str, Any]],
    degraded: list[dict[str, str]],
) -> dict[str, Any]:
    try:
        from _lib import brand_bible  # noqa: PLC0415

        category = str((products[0] or {}).get("category") or "") if products else ""
        lane = "product" if products else "campaign"
        info = brand_bible.retrieve_for_job(
            brand_id,
            lane=lane,
            job_type="social",
            product_category=category,
        )
        fields = info.get("fields") if isinstance(info.get("fields"), dict) else {}
        return {
            "available": bool(info.get("available")),
            "last_updated": info.get("last_updated"),
            "fields": sorted(fields.keys()),
        }
    except Exception as exc:
        degraded.append({"source": "brand_bible", "reason": str(exc)[:120]})
        return {"available": False, "last_updated": None, "fields": []}


def _compose_cd(
    brand_id: str,
    job: str,
    reference_dna: Optional[dict[str, Any]],
    product: Optional[dict[str, Any]],
    degraded: list[dict[str, str]],
) -> dict[str, Any]:
    try:
        from _lib.creative_director import compose_prompt  # noqa: PLC0415

        return compose_prompt(
            brand_id=brand_id,
            job=job,
            reference_dna=reference_dna,
            product_service_item=product,
        )
    except Exception as exc:
        degraded.append({"source": "creative_director", "reason": str(exc)[:120]})
        return {"sections": [], "negative_prompt": "", "model_routing": {}}


def calendar_title_for_item(brand_id: str, inbox_item_id: str) -> str:
    """Best-effort calendar title for an inbox item. Never raises, never writes."""
    item_type, item_brand, cal_id = _parse_item_id(inbox_item_id)
    if item_type != "calendar_candidate" or not cal_id:
        return ""
    try:
        record = _resolve_calendar_record(item_brand or brand_id, cal_id)
    except Exception:  # noqa: BLE001
        return ""
    if not isinstance(record, dict):
        return ""
    return _first_str(record, "title", "event_key")


def _normalize_platform(raw: str) -> str:
    p = (raw or "").strip().lower()
    aliases = {
        "fb": "facebook",
        "ig": "instagram",
        "google": "gbp",
        "google_business": "gbp",
        "google-business": "gbp",
    }
    return aliases.get(p, p)


def calendar_record_for_item(brand_id: str, inbox_item_id: str) -> Optional[dict[str, Any]]:
    """Calendar moment dict for a calendar_candidate inbox id, else None."""
    item_type, item_brand, cal_id = _parse_item_id(inbox_item_id)
    if item_type != "calendar_candidate" or not cal_id:
        return None
    try:
        record = _resolve_calendar_record(item_brand or brand_id, cal_id)
    except Exception:  # noqa: BLE001
        return None
    return record if isinstance(record, dict) else None


def primary_channel_for_item(
    brand_id: str,
    inbox_item_id: str,
    *,
    fallback: str = "instagram",
) -> str:
    """Channel this lodge publishes on (calendar primary_channel, else asset fallback)."""
    record = calendar_record_for_item(brand_id, inbox_item_id)
    if record:
        ch = _first_str(record, "primary_channel", "platform", "channel")
        if ch:
            return _normalize_platform(ch)
    return _normalize_platform(fallback)


def calendar_event_date_for_item(brand_id: str, inbox_item_id: str) -> str:
    """Goes-out date (YYYY-MM-DD) from the calendar moment when available."""
    record = calendar_record_for_item(brand_id, inbox_item_id)
    if not record:
        return ""
    return _first_str(record, "event_date", "event_start", "event_window_start")


def lodged_title_for_item(
    brand_id: str,
    inbox_item_id: str,
    *,
    sidecar_title: str = "",
    asset_name: str = "",
) -> str:
    """Human title for cards — sidecar/asset name, else calendar title."""
    for candidate in (sidecar_title, asset_name):
        text = (candidate or "").strip()
        if text and not text.lower().startswith("draft "):
            return text
    cal = calendar_title_for_item(brand_id, inbox_item_id)
    return cal.strip()


def image_url_for(brand_id: str, saved_path: str | None) -> str | None:
    """/brand-images/<brand>/<basename> — mirrors app.py image generate preview_url."""
    if not saved_path:
        return None
    name = Path(saved_path).name
    if not name:
        return None
    return f"/brand-images/{brand_id}/{name}"
