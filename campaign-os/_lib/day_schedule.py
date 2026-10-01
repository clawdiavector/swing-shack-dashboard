"""Day desk batch scheduling — candidate records only, no image generation."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable

from _lib.marketing_calendar import (
    ONESHOT_ALLOWED_POST_TYPES,
    VALID_BRAND_IDS,
    add_candidate,
    canonical_records,
    load_brand_config,
    oneshot_eligible,
)
from _lib.meme_lord import apply_meme, load_meme_knowledge, recommend_memes
from _lib.unified_inbox import _WEEK_MOMENT_STATUSES, _moment_go_live_date

MEME_VOICE_BY_BRAND = {"swing-shack": "swing-shack", "stick": "stick", "bag-drop": "bag-drop"}

MEME_PILLAR_BY_BRAND_PILLAR = {
    "ss-fitting": "club-fitting",
    "ss-coaching": "education",
    "ss-membership": "community",
    "stick-fitting": "club-fitting",
    "stick-coaching": "education",
    "stick-retail": "community",
}

MEME_FLAVOUR_BY_BRAND = {"swing-shack": "sarcastic", "stick": "sarcastic", "bag-drop": "sarcastic"}

CONTINUOUS_POST_TYPE_ROTATION: dict[str, list[str]] = {
    "ss-membership": ["price_package", "service_promo", "did_you_know"],
    "stick-retail": ["shop_corner", "service_square", "brand_statement"],
}

ONESHOT_ROTATION: dict[str, list[tuple[str, str]]] = {
    "swing-shack": [("fitting_headline", "ss-fitting")],
    "stick": [
        ("service_hero", "stick-fitting"),
        ("coaching_promo", "stick-coaching"),
        ("humour_card", "stick-retail"),
    ],
}


def _meme_pillar_for(pillar_id: str) -> str:
    if pillar_id in MEME_PILLAR_BY_BRAND_PILLAR:
        return MEME_PILLAR_BY_BRAND_PILLAR[pillar_id]
    suffix = pillar_id.split("-", 1)[-1] if "-" in pillar_id else pillar_id
    if "fitting" in suffix:
        return "club-fitting"
    if "coaching" in suffix:
        return "education"
    return "community"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_moment(
    *,
    day_iso: str,
    batch_id: str,
    pillar_id: str,
    pillar_name: str,
    post_type: str,
    render_mode: str,
    title: str,
) -> dict[str, Any]:
    return {
        "type": "moment",
        "status": "candidate",
        "title": title,
        "angle": "",
        "event_date": day_iso,
        "event_start": day_iso,
        "event_end": day_iso,
        "primary_channel": "instagram",
        "pillars": [pillar_id],
        "pillar_id": pillar_id,
        "post_type": post_type,
        "render_mode": render_mode,
        "created_by": "operator",
        "source_type": "operator",
        "origin": {
            "kind": "operator",
            "actor": "day_desk_schedule",
            "ref": f"schedule-day:{day_iso}:{batch_id}",
        },
        "schedule_batch_id": batch_id,
        "verification_status": "unverified",
    }


def day_is_empty(*, brand_id: str, day_iso: str) -> bool:
    """True when no week-board moment exists on day_iso."""
    for record in canonical_records(brand_id):
        status = str(record.get("status") or "").lower()
        if status not in _WEEK_MOMENT_STATUSES:
            continue
        if _moment_go_live_date(record) == day_iso:
            return False
    return True


def _daily_title(pillar_name: str) -> str:
    return f"{pillar_name} — service frame"


def _rotation_title(pillar_name: str, post_type: str) -> str:
    label = post_type.replace("_", " ").title()
    return f"{pillar_name} — {label}"


def _build_humour_card(
    *,
    brand_id: str,
    day_iso: str,
    batch_id: str,
    pillar_id: str,
    flavour: str | None,
) -> dict[str, Any]:
    voice = MEME_VOICE_BY_BRAND.get(brand_id, brand_id)
    meme_pillar = _meme_pillar_for(pillar_id)
    picks = recommend_memes(
        voice=voice,
        pillar=meme_pillar,
        platform="instagram",
        limit=5,
        only_still_works=True,
    )
    if not picks:
        raise ValueError("No memes available for humour_card scheduling")
    top = picks[0]
    applied = apply_meme(
        meme_id=str(top["id"]),
        voice=voice,
        pillar=meme_pillar,
        platform="instagram",
        pick_seed_index=0,
    )
    use_flavour = flavour or MEME_FLAVOUR_BY_BRAND.get(brand_id, "sarcastic")
    captions = applied.get("captions") or []
    caption = next(
        (c["text"] for c in captions if c.get("flavour") == use_flavour),
        captions[0]["text"] if captions else "",
    )
    meme_name = top.get("name") or top.get("id") or "Meme"
    row = _base_moment(
        day_iso=day_iso,
        batch_id=batch_id,
        pillar_id=pillar_id,
        pillar_name="Humour",
        post_type="humour_card",
        render_mode="oneshot",
        title=f"Humour card — {meme_name}",
    )
    row["angle"] = caption
    row["process"] = "humour"
    row["origin"] = {
        "kind": "meme_lord",
        "actor": "day_desk_schedule",
        "ref": f"schedule-day:{day_iso}:{batch_id}",
    }
    row["meme"] = {
        "id": top.get("id"),
        "name": meme_name,
        "flavour": use_flavour,
        "caption": caption,
        "fit_seed_used": applied.get("applied", {}).get("fit_seed_used"),
        "format_hint": top.get("format_hint"),
        "brand_fit": top.get("brand_fit"),
        "voice": voice,
        "pillar": meme_pillar,
        "platform": "instagram",
        "source": "data/meme_knowledge.json",
        "knowledge_version": load_meme_knowledge().get("version"),
        "picked_at": _now_iso(),
    }
    return row


def plan_day_batch(
    *,
    brand_id: str,
    day_iso: str,
    batch_id: str | None = None,
    meme_picker: Callable[..., list[dict[str, Any]]] | None = None,
    flavour: str | None = None,
    oneshot_override: str | None = None,
) -> list[dict[str, Any]]:
    """Pure planner — no writes."""
    if brand_id not in VALID_BRAND_IDS:
        raise ValueError(f"brand_id '{brand_id}' invalid")
    try:
        day = date.fromisoformat(day_iso[:10])
    except ValueError as exc:
        raise ValueError(f"date '{day_iso}' invalid") from exc

    batch_id = batch_id or uuid.uuid4().hex
    cfg = load_brand_config(brand_id)
    pillars = cfg.get("pillars") or []
    rows: list[dict[str, Any]] = []

    for pillar in pillars:
        if not pillar.get("always_active", True):
            continue
        pillar_id = str(pillar.get("pillar_id") or "")
        pillar_name = str(pillar.get("name") or pillar_id)
        cadence = str(pillar.get("cadence") or "").lower()
        if cadence == "daily":
            rows.append(
                _base_moment(
                    day_iso=day_iso,
                    batch_id=batch_id,
                    pillar_id=pillar_id,
                    pillar_name=pillar_name,
                    post_type="",
                    render_mode="template",
                    title=_daily_title(pillar_name),
                ),
            )
        else:
            rotation = CONTINUOUS_POST_TYPE_ROTATION.get(pillar_id)
            if not rotation:
                continue
            post_type = rotation[day.toordinal() % len(rotation)]
            rows.append(
                _base_moment(
                    day_iso=day_iso,
                    batch_id=batch_id,
                    pillar_id=pillar_id,
                    pillar_name=pillar_name,
                    post_type=post_type,
                    render_mode="template",
                    title=_rotation_title(pillar_name, post_type),
                ),
            )

    oneshot_slots = ONESHOT_ROTATION.get(brand_id, [])
    if oneshot_slots:
        if oneshot_override:
            match = next((s for s in oneshot_slots if s[0] == oneshot_override), None)
            if not match:
                raise ValueError(f"oneshot_override '{oneshot_override}' not in brand rotation")
            post_type, pillar_id = match
        else:
            idx = day.toordinal() % len(oneshot_slots)
            post_type, pillar_id = oneshot_slots[idx]
        if not oneshot_eligible(post_type):
            raise ValueError(f"planned one-shot post_type '{post_type}' not allowlisted")
        if post_type == "humour_card":
            rows.append(
                _build_humour_card(
                    brand_id=brand_id,
                    day_iso=day_iso,
                    batch_id=batch_id,
                    pillar_id=pillar_id,
                    flavour=flavour,
                ),
            )
        else:
            title_map = {
                "fitting_headline": "Fitting headline — one-shot",
                "service_hero": "Service hero — one-shot",
                "coaching_promo": "Coaching promo — one-shot",
            }
            rows.append(
                _base_moment(
                    day_iso=day_iso,
                    batch_id=batch_id,
                    pillar_id=pillar_id,
                    pillar_name="One-shot",
                    post_type=post_type,
                    render_mode="oneshot",
                    title=title_map.get(post_type, f"{post_type} — one-shot"),
                ),
            )

    oneshot_count = sum(1 for r in rows if r.get("render_mode") == "oneshot")
    if oneshot_count > 1:
        raise ValueError(f"batch would create {oneshot_count} one-shot cards (max 1)")
    for r in rows:
        pt = r.get("post_type")
        if r.get("render_mode") == "oneshot" and not oneshot_eligible(pt):
            raise ValueError(f"one-shot row has disallowed post_type '{pt}'")
        if pt and pt not in ONESHOT_ALLOWED_POST_TYPES and r.get("render_mode") == "oneshot":
            raise ValueError(f"one-shot row has disallowed post_type '{pt}'")

    if meme_picker is not None:
        del meme_picker  # reserved for tests / future injection

    return rows


def schedule_day(
    *,
    brand_id: str,
    day_iso: str,
    force: bool = False,
    actor: str = "operator",
    flavour: str | None = None,
) -> dict[str, Any]:
    """Write a day batch to the operator calendar store."""
    del actor
    if brand_id not in VALID_BRAND_IDS:
        return {"ok": False, "error": f"brand_id '{brand_id}' invalid"}
    day_iso = str(day_iso)[:10]
    try:
        date.fromisoformat(day_iso)
    except ValueError:
        return {"ok": False, "error": f"date '{day_iso}' invalid"}

    if not force and not day_is_empty(brand_id=brand_id, day_iso=day_iso):
        existing_ids: list[str] = []
        count = 0
        for record in canonical_records(brand_id):
            status = str(record.get("status") or "").lower()
            if status not in _WEEK_MOMENT_STATUSES:
                continue
            if _moment_go_live_date(record) == day_iso:
                count += 1
                cid = record.get("calendar_id")
                if cid:
                    existing_ids.append(str(cid))
        return {
            "ok": False,
            "code": "day_not_empty",
            "brand_id": brand_id,
            "date": day_iso,
            "existing": count,
            "existing_calendar_ids": existing_ids,
        }

    batch_id = uuid.uuid4().hex
    try:
        planned = plan_day_batch(
            brand_id=brand_id,
            day_iso=day_iso,
            batch_id=batch_id,
            flavour=flavour,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    created: list[dict[str, Any]] = []
    for row in planned:
        persisted = add_candidate(brand_id, row, initial_status="candidate")
        created.append(persisted)

    template_n = sum(1 for r in created if r.get("render_mode") != "oneshot")
    oneshot_n = sum(1 for r in created if r.get("render_mode") == "oneshot")
    return {
        "ok": True,
        "brand_id": brand_id,
        "date": day_iso,
        "batch_id": batch_id,
        "created": created,
        "counts": {"template": template_n, "oneshot": oneshot_n},
    }
