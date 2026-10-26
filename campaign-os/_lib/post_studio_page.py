"""Post studio — compose preview and field metadata for the Heroes UI.

Preview is synchronous and does not write calendar records or draft assets.
Lodge stays on post_lodge.lodge_post(approve=False).
"""
from __future__ import annotations

import base64
from typing import Any

from _lib.brand_validate import validate_brand_id


class StudioPageError(ValueError):
    """A request the studio page refuses."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _render_post():
    from _lib.jobs.layer5.render_batch import _scripts_module  # noqa: PLC0415

    return _scripts_module("render_post")


def text_field_specs(brand_id: str, archetype_id: str) -> list[dict[str, Any]]:
    """Editable text zones for one archetype (zone source keys, not zone names)."""
    brand = validate_brand_id(brand_id)
    archetype_id = (archetype_id or "").strip()
    if not archetype_id:
        raise StudioPageError("archetype is required")
    render_post = _render_post()
    try:
        arc = render_post._get(brand, archetype_id)
    except SystemExit as exc:
        raise StudioPageError(str(exc)) from None

    applies = arc.get("applies_to") or {}
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for zone in (arc.get("zones") or {}).values():
        if not isinstance(zone, dict) or zone.get("kind") != "text":
            continue
        key = str(zone.get("source") or "").strip()
        if not key or key == "static" or key in seen:
            continue
        seen.add(key)
        hint_parts: list[str] = []
        if zone.get("max_chars_per_line"):
            lines = zone.get("max_lines") or 1
            hint_parts.append(
                f"up to {lines} line(s) × {zone['max_chars_per_line']} chars"
            )
        if zone.get("text_suffix"):
            hint_parts.append(f"template appends {zone['text_suffix']!r}")
        specs.append(
            {
                "key": key,
                "label": key.replace("_", " "),
                "hint": "; ".join(hint_parts) if hint_parts else "",
                "required": True,
            }
        )
    specs.sort(key=lambda row: row["key"])
    return specs


def preview_compose(
    *,
    brand_id: str,
    archetype_id: str,
    fields: dict[str, Any] | None,
    photo: str | None,
    channels: list[str] | None = None,
) -> dict[str, Any]:
    """Render archetype channels to PNG bytes; return data URLs (no disk writes)."""
    from _lib.archetype_compose import compose_post_for_channels  # noqa: PLC0415

    brand = validate_brand_id(brand_id)
    archetype_id = (archetype_id or "").strip()
    if not archetype_id:
        raise StudioPageError("archetype is required")

    render_post = _render_post()
    try:
        arc = render_post._get(brand, archetype_id)
    except SystemExit as exc:
        raise StudioPageError(str(exc)) from None

    applies = arc.get("applies_to") or {}
    use_channels = channels or applies.get("channels") or ["instagram"]
    if not isinstance(use_channels, list) or not use_channels:
        raise StudioPageError("channels must be a non-empty list")

    photo_bytes = render_post._pick_photo(brand, arc, (photo or "").strip() or None, None)
    if applies.get("needs_photo") and photo_bytes is None:
        raise StudioPageError(
            f"{archetype_id} needs a photo — pick one from the library or the template pack"
        )

    field_map = dict(fields or {})
    composed = compose_post_for_channels(
        brand_id=brand,
        archetype=arc,
        channels=[str(c) for c in use_channels],
        fields=field_map,
        photo_bytes=photo_bytes,
    )
    if not composed:
        raise StudioPageError(
            f"{archetype_id} produced nothing for channels {use_channels}"
        )

    images: dict[str, str] = {}
    for channel, png in composed.items():
        images[channel] = "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    return {
        "ok": True,
        "brand_id": brand,
        "archetype_id": archetype_id,
        "channels": list(composed.keys()),
        "images": images,
        "needs_photo": bool(applies.get("needs_photo")),
        "field_specs": text_field_specs(brand, archetype_id),
    }
