"""Archetype schema v2 validation tests (P3.3a)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _lib.archetype_schema import iter_archetype_files, validate_archetypes_doc

REPO = Path(__file__).resolve().parents[3]


def test_schema_validates_three_brands():
    for path in iter_archetype_files(REPO):
        if path.parts[-3] not in ("stick", "swing-shack", "bag-drop"):
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        validate_archetypes_doc(doc)


def test_at_most_four_archetypes_per_brand():
    for brand in ("stick", "swing-shack", "bag-drop"):
        path = REPO / "data" / "brand-directory" / brand / "visual-spec" / "archetypes.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert 1 <= len(doc.get("archetypes") or []) <= 4
