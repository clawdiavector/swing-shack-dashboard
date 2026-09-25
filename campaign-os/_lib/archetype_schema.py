"""Validate brand visual-spec/archetypes.json against schema v2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).resolve().parent / "archetype_schema_data.json"


def load_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_archetypes_doc(doc: dict[str, Any], schema: dict[str, Any] | None = None) -> None:
    """Raise jsonschema.ValidationError on failure."""
    import jsonschema

    jsonschema.validate(instance=doc, schema=schema or load_schema())


def iter_archetype_files(repo_root: Path | None = None) -> list[Path]:
    root = repo_root or Path(__file__).resolve().parent.parent.parent
    base = root / "data" / "brand-directory"
    return sorted(base.glob("*/visual-spec/archetypes.json"))
