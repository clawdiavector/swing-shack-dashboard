"""Compatibility shim — use _lib.archetypes."""

from typing import Any

from _lib.archetypes import (  # noqa: F401
    archetype_by_id,
    canvas_for_channel,
    font_size_for_role,
    load_archetypes_doc,
    palette_tokens,
    resolve_colour,
    select_archetype,
)

SCHEMA_URL = "https://campaign-os/brand-directory/visual-archetypes/v2"


def validate_archetypes_doc(doc: dict[str, Any]) -> list[str]:
    from _lib.archetype_schema import validate_archetypes_doc as _validate

    try:
        _validate(doc)
        return []
    except Exception as exc:  # noqa: BLE001
        return [str(exc)]
