"""candidate_offers.py — stock-driven candidate offers for a retail brief.

Reads the weekly stock snapshots (stock_pulse) and lists the lines worth building an
offer around. It never invents a price, discount or promo: those stay blank for the
operator. With one snapshot it can only say what is deep on the shelf; "still" and
"stuck" need a second weekly list, and there is no last-sold date anywhere.
"""
from __future__ import annotations

from typing import Any, Dict, List

MAX_ITEMS = 8
SUPPORTS = "retail"


def _snapshots(brand_id: str) -> List[dict]:
    try:
        from _lib import stock_pulse
        return stock_pulse.load_snapshots(brand_id)
    except Exception:
        return []


def build(brand_id: str, max_items: int = MAX_ITEMS) -> Dict[str, Any]:
    """The candidate_offers block for a brief (system_draft, operator_editable)."""
    base = {"type": "system_draft", "operator_editable": True,
            "supports_north_star": SUPPORTS, "items": []}
    snaps = _snapshots(brand_id)
    if not snaps:
        return dict(base, status="no_stock_data",
                    note="No stock list imported for this brand yet, so there are no "
                         "candidate offers. Import a weekly stock list, or write the "
                         "offer by hand.")
    from _lib import stock_pulse as sp
    results = sp.analyse(snaps)
    pick = [r for r in results
            if not r["not_for_feed"] and not r.get("folded_into_range")
            and r["status"] not in ("low", "out", "error")
            and (r["status"] in ("stuck", "still", "new", "back") or r["deep_shelf"])]
    pick.sort(key=lambda r: (r["feed_boost"], r["days_still"] * r["qty"], r["qty"]), reverse=True)
    items = [{
        "name": r["range_name"] if r.get("range_name") and r["category"] in ("grip", "towel", "ferrule") else r["name"],
        "category": r["category"],
        "qty": r["qty"],
        "days_unchanged": r["days_still"],
        "status": r["status"],
        "reason": r["reason"] or (f"{r['qty']} on the shelf" if r["deep_shelf"] else ""),
        "idea": r.get("idea") or "",
        "supports_north_star": SUPPORTS,
        "price": "",
        "discount": "",
    } for r in pick[:max_items]]
    latest = snaps[-1].get("date", "")
    if len(snaps) < 2:
        note = (f"Single baseline list ({latest}), quantity only, no last-sold data. "
                "'Still' and 'stuck' need a second weekly list. Price and discount are "
                "yours to fill in.")
    else:
        note = (f"From {len(snaps)} weekly lists, latest {latest}. Quantity only, no "
                "last-sold data: 'still' means no net movement. Price and discount are "
                "yours to fill in.")
    return dict(base, status="ok" if items else "nothing_to_push", items=items,
                snapshots=len(snaps), latest_list=latest, note=note)


def proposition_text(block: Dict[str, Any]) -> str:
    """A retail proposition drafted from the candidates, or '' when there are none."""
    items = (block or {}).get("items") or []
    if not items:
        return ""
    lead = ", ".join(i["name"] for i in items[:3])
    more = f" Also on the shelf: {', '.join(i['name'] for i in items[3:6])}." if len(items) > 3 else ""
    return (f"Build the offer around what we hold in depth: {lead}.{more} "
            "Show real product, tie each line to the Retail North Star, and let the "
            "operator set the price, discount and the one idea. Nothing here is a "
            "promised price.")
