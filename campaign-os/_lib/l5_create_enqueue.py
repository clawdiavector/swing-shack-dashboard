"""Shared L5 create enqueue helpers (draft_photo / compose_post split)."""

from __future__ import annotations

import hashlib
from typing import Any

PHOTO_EQUIV = frozenset({"draft_photo", "draft_image"})


def already_queued(existing: set[tuple[str, str]], action: str) -> bool:
    names = PHOTO_EQUIV if action in PHOTO_EQUIV else {action}
    return any((n, s) in existing for n in names for s in ("pending", "waiting"))


def create_actions_for_moment(brand_id: str, item_id: str) -> list[str]:
    from _lib.archetypes import select_archetype
    from _lib.publish_sandbox import intended_publish_channels

    actions = ["draft_caption"]
    archetype = select_archetype(brand_id, item_id)
    if archetype.get("applies_to", {}).get("needs_photo", True):
        actions.append("draft_photo")
    actions.append("compose_post")
    if "gbp" in intended_publish_channels(brand_id):
        actions.append("draft_gbp")
    return actions


def enqueue_create_actions(
    *,
    item_id: str,
    brand_id: str,
    reason: str,
    rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    from _lib import ops_agents

    enqueued: list[str] = []
    item_hash = hashlib.sha1(item_id.encode()).hexdigest()[:12]
    existing: set[tuple[str, str]] = set()
    if rows is not None:
        for row in rows:
            pref = str(row.get("payload_ref") or "")
            if pref != f"inbox/{item_id}":
                continue
            existing.add((str(row.get("action") or ""), str(row.get("status") or "").lower()))

    for action in create_actions_for_moment(brand_id, item_id):
        if already_queued(existing, action):
            continue
        if action == "draft_photo":
            from _lib.image_submit_quota import check_brand_image_submit

            ok, _reason = check_brand_image_submit(brand_id)
            if not ok:
                continue
        agent = "cos-image" if action in ("draft_photo", "compose_post") else "cos-caption"
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


def _data_dir():
    import os
    from pathlib import Path

    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))
