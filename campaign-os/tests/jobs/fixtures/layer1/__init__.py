"""Golden top-level (and array element) key sets for Layer 1 job outputs.

Derived from repo seed data/*.json plus port-declared element keys where
seed arrays are empty (golf-news / reddit-trends since 2026-08-13).
"""

from __future__ import annotations

import json
from pathlib import Path

_FIXTURE = Path(__file__).resolve().parent / "golden_keys.json"


def load_golden() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def top_level_keys(filename: str) -> set[str]:
    return set(load_golden()[filename]["top_level"])


def elem_keys(filename: str) -> set[str] | None:
    raw = load_golden()[filename].get("elem_keys")
    return set(raw) if raw else None
