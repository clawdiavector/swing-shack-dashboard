"""Per-type layout ledger for the Taxonomy of Design page.

For every shared post type and every brand: does the brand have a layout that
renders it, does it need a real photo first, is the layout not vetted yet, or
is there nothing built? The answer comes from the same visual gate the calendar
uses (``visual_gate.decide``), so the page and the calendar cannot disagree.

Operating plan phase 1 asked for this table by 16 Oct 2026 ("has layout / one-shot
allowed / not yet"). One-shot marks come from Christelle's agreed November
marks (wiki decisions/november-post-type-marks-2026-10-21).
"""

from __future__ import annotations

from typing import Any

BRANDS = ("swing-shack", "stick", "bag-drop")

# shared type id -> brand -> the brand's post_type values the layout rules know.
# None = the type does not apply to that brand (Bag Drop is an online store).
# [] = applies, but the brand has no post_type for it, so nothing is built.
PROBES: dict[str, dict[str, list[str] | None]] = {
    "product": {"swing-shack": ["product_post"], "stick": ["product_post"], "bag-drop": ["product_post"]},
    "offer": {"swing-shack": ["sale_offer", "discount_code"], "stick": [], "bag-drop": ["weekly_deal"]},
    "price": {"swing-shack": ["price_package", "price_list"], "stick": [], "bag-drop": []},
    "service": {
        "swing-shack": ["service_promo", "fitting_headline", "lesson"],
        "stick": ["service_start", "service_end", "coaching_promo", "service_hero"],
        "bag-drop": None,
    },
    # "Where to find us" (location) is part of venue since 16 Nov 2026 (Christelle: 9 types, not 11).
    "venue": {"swing-shack": ["venue_promo"], "stick": ["shop_corner", "product_lifestyle", "location"], "bag-drop": None},
    "person": {"swing-shack": [], "stick": ["staff_profile"], "bag-drop": []},
    "tip": {"swing-shack": ["tip"], "stick": [], "bag-drop": ["tip"]},
    "statement": {"swing-shack": [], "stick": ["brand_statement"], "bag-drop": []},
    "condition": {"swing-shack": None, "stick": None, "bag-drop": ["condition"]},
}

# "One-shot OK until vetted" in the agreed November marks (Stick only).
ONE_SHOT_OK = {("stick", "coaching_promo"), ("stick", "service_hero")}

LABELS = {
    "has_layout": "Has a layout",
    "partial": "Some of it has a layout",
    "needs_photo": "Layout ready, needs a real photo",
    "not_vetted": "Layout not vetted yet",
    "not_yet": "Not built yet",
    "not_applicable": "Does not apply",
    "unknown": "Could not check",
}

# Best status first. A type reads "has a layout" only when all its post types do.
_RANK = ["has_layout", "needs_photo", "not_vetted", "not_yet", "unknown"]


def _status_for(reason: str, gate_status: str) -> str:
    if gate_status == "trusted":
        return "has_layout"
    if reason == "no_real_photo":
        return "needs_photo"
    if reason == "layout_not_vetted":
        return "not_vetted"
    return "not_yet"


def _probe(brand: str, post_type: str) -> dict[str, Any]:
    row: dict[str, Any] = {"post_type": post_type, "one_shot_ok": (brand, post_type) in ONE_SHOT_OK}
    try:
        from _lib import visual_gate  # noqa: PLC0415

        rec = {
            "id": "ledger-probe",
            "brand_id": brand,
            "post_type": post_type,
            "title": f"ledger probe {post_type}",
            "scheduled_date": "2099-01-01",
            "pillar": "",
        }
        d = visual_gate.decide(brand, f"calendar_candidate:{brand}:ledger-probe", record=rec)
        row.update(
            status=_status_for(d.reason, d.status),
            archetype_id=d.archetype_id,
            reason=d.reason,
        )
    except Exception as exc:  # the page must still load if one probe breaks
        row.update(status="unknown", archetype_id=None, reason=f"{type(exc).__name__}")
    return row


def build_layout_ledger() -> dict[str, dict[str, dict[str, Any]]]:
    """{type_id: {brand: {status, label, one_shot_ok, rows: [...]}}}"""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for type_id, per_brand in PROBES.items():
        out[type_id] = {}
        for brand in BRANDS:
            probes = per_brand.get(brand)
            if probes is None:
                out[type_id][brand] = {"status": "not_applicable", "label": LABELS["not_applicable"], "one_shot_ok": False, "rows": []}
                continue
            rows = [_probe(brand, pt) for pt in probes]
            if not rows:
                status = "not_yet"
            else:
                worst = max((r["status"] for r in rows), key=_RANK.index)
                status = "has_layout" if worst == "has_layout" else worst
                if status != "has_layout" and any(r["status"] == "has_layout" for r in rows):
                    status = "partial"
            # one-shot only matters for post types that have no trusted layout yet
            one_shot = status != "has_layout" and any(r["one_shot_ok"] and r["status"] != "has_layout" for r in rows)
            out[type_id][brand] = {"status": status, "label": LABELS[status], "one_shot_ok": one_shot, "rows": rows}
    return out
