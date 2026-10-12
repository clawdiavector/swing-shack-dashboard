"""Today's story suggestion: one thing to feature and the brand page to repost from.

Pure and deterministic, no model. Days alternate between a retail brand and a
service; the service day names a stocked brand that fits it, so the repost relates
to what we sell. Brands without a page we can open (RipIt, for now) are skipped.
The lists live in data/brand-directory/<brand>/story-brands.json.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "data" / "brand-directory"


def _load(brand: str) -> dict | None:
    try:
        return json.loads((_ROOT / brand / "story-brands.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _page(b: dict) -> dict:
    return {"id": b["id"], "name": b["name"], "instagram": b.get("instagram"),
            "facebook": b.get("facebook"), "look_for": b.get("look_for", "")}


def suggest(brand: str, day: date) -> dict | None:
    data = _load(brand)
    if not data:
        return None
    retail = [b for b in data["retail"] if b.get("instagram") or b.get("facebook")]
    services = data.get("services") or []
    n = day.toordinal()
    if not retail:
        return None
    if services and n % 2:
        svc = services[(n // 2) % len(services)]
        paired = next((b for b in retail if b["id"] == svc.get("pairs_with")), None)
        return {"brand": brand, "date": day.isoformat(), "kind": "service",
                "feature": svc["name"], "repost_from": _page(paired or retail[(n // 2) % len(retail)])}
    pick = retail[(n // 2) % len(retail)]
    return {"brand": brand, "date": day.isoformat(), "kind": "retail",
            "feature": pick["name"], "repost_from": _page(pick)}
