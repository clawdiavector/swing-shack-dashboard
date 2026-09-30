"""Shared L5 create enqueue helpers (draft_photo / compose_post split)."""

from __future__ import annotations

import hashlib
from typing import Any

PHOTO_EQUIV = frozenset({"draft_photo", "draft_image"})


def already_queued(existing: set[tuple[str, str]], action: str) -> bool:
    names = PHOTO_EQUIV if action in PHOTO_EQUIV else {action}
    return any((n, s) in existing for n in names for s in ("pending", "waiting"))


def create_actions_for_moment(
    brand_id: str,
    item_id: str,
    *,
    phase: str = "all",
) -> list[str]:
    """``lodge``: caption (+ gbp) only; ``image``: gen/photo + compose; ``all``: full pipeline."""
    from _lib.archetypes import select_archetype
    from _lib.publish_sandbox import intended_publish_channels
    from _lib.template_recipe import load_recipe_for_moment

    if phase == "lodge":
        actions = ["draft_caption"]
        if "gbp" in intended_publish_channels(brand_id):
            actions.append("draft_gbp")
        return actions

    image_actions: list[str] = []
    recipe = load_recipe_for_moment(brand_id, item_id)
    gen_slots = recipe.get("gen_slots") if isinstance(recipe, dict) else None
    if isinstance(gen_slots, list) and gen_slots:
        image_actions.append("draft_gen_slots")
    else:
        archetype = select_archetype(brand_id, item_id)
        needs_photo = archetype.get("applies_to", {}).get("needs_photo", True)
        bg = archetype.get("background") if isinstance(archetype.get("background"), dict) else {}
        template_library = (
            bg.get("kind") == "photo_full_bleed" and bool(str(bg.get("library") or "").strip())
        )
        if needs_photo and not template_library:
            image_actions.append("draft_photo")
    image_actions.append("compose_post")

    if phase == "image":
        return image_actions

    actions = ["draft_caption", *image_actions]
    if "gbp" in intended_publish_channels(brand_id):
        actions.append("draft_gbp")
    return actions


def enqueue_create_actions(
    *,
    item_id: str,
    brand_id: str,
    reason: str,
    rows: list[dict[str, Any]] | None = None,
    phase: str = "all",
) -> list[str]:
    from _lib import ops_agents
    from _lib.campaigns import provenance_for_inbox_item, write_create_payload  # noqa: PLC0415

    payload_fields = provenance_for_inbox_item(brand_id, item_id)
    if payload_fields:
        write_create_payload(item_id=item_id, fields=payload_fields)

    enqueued: list[str] = []
    item_hash = hashlib.sha1(item_id.encode()).hexdigest()[:12]
    existing: set[tuple[str, str]] = set()
    if rows is not None:
        for row in rows:
            pref = str(row.get("payload_ref") or "")
            if pref != f"inbox/{item_id}":
                continue
            existing.add((str(row.get("action") or ""), str(row.get("status") or "").lower()))

    for action in create_actions_for_moment(brand_id, item_id, phase=phase):
        if already_queued(existing, action):
            continue
        if action == "draft_photo":
            from _lib.image_submit_quota import check_brand_image_submit

            ok, _reason = check_brand_image_submit(brand_id)
            if not ok:
                continue
        agent = "cos-image" if action in ("draft_photo", "compose_post", "draft_gen_slots") else "cos-caption"
        row = ops_agents.normalise_enqueue(
            {
                "agent": agent,
                "brand": brand_id,
                "reason": reason,
                "action": action,
                "payload_ref": f"inbox/{item_id}",
                "dedupe_key": f"{action}-{item_hash}",
            }
        )
        ops_agents.append_enqueue_row(_data_dir(), row)
        if rows is not None:
            rows.append(row)
            existing.add((action, "pending"))
        enqueued.append(action)
    return enqueued


def enqueue_compose_post_for_moment(
    *,
    item_id: str,
    brand_id: str,
    reason: str,
    rows: list[dict[str, Any]] | None = None,
) -> bool:
    """Append compose_post when photo/gen finished and compose not already queued."""
    from _lib import ops_agents

    item_hash = hashlib.sha1(item_id.encode()).hexdigest()[:12]
    existing: set[tuple[str, str]] = set()
    if rows is not None:
        for row in rows:
            pref = str(row.get("payload_ref") or "")
            if pref != f"inbox/{item_id}":
                continue
            existing.add((str(row.get("action") or ""), str(row.get("status") or "").lower()))
    if already_queued(existing, "compose_post"):
        return False
    row = ops_agents.normalise_enqueue(
        {
            "agent": "cos-image",
            "brand": brand_id,
            "reason": reason,
            "action": "compose_post",
            "payload_ref": f"inbox/{item_id}",
            "dedupe_key": f"compose_post-{item_hash}",
        }
    )
    ops_agents.append_enqueue_row(_data_dir(), row)
    if rows is not None:
        rows.append(row)
    return True


def _data_dir():
    import os
    from pathlib import Path

    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))
