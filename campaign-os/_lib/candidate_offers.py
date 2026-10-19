"""candidate_offers.py — stock-driven candidate offers for a retail brief.

Reads the weekly stock snapshots (stock_pulse) and lists the lines worth building an
offer around. It never invents a price, discount or promo: those stay blank for the
operator. With one snapshot it can only say what is deep on the shelf; "still" and
"stuck" need a second weekly list, and there is no last-sold date anywhere.

The block carries three lists so the operator can choose anything:
  items      the suggestions (the Retail North Star's product first, then deep shelves)
  catalogue  every line sold as-is, each with why it is or is not suggested
  services   the brand's services (fitting, coaching, membership...)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

MAX_ITEMS = 10
SUPPORTS = "retail"


def _snapshots(brand_id: str) -> List[dict]:
    try:
        from _lib import stock_pulse
        return stock_pulse.load_snapshots(brand_id)
    except Exception:
        return []


def _brand_dirs(brand_id: str) -> List[Path]:
    here = Path(__file__).resolve().parent
    dirs = []
    dd = os.environ.get("DATA_DIR")
    if dd:
        dirs.append(Path(dd) / "brand-directory" / brand_id)
    dirs.append(here.parent.parent / "data" / "brand-directory" / brand_id)
    return dirs


def _read(brand_id: str, filename: str) -> dict:
    for d in _brand_dirs(brand_id):
        try:
            return json.loads((d / filename).read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def focus_product(brand_id: str) -> str:
    """The product the Retail North Star is about ('Psycho Bunny' for Stick), or ''."""
    cfg = _read(brand_id, "calendar_config.json")
    for p in cfg.get("pillars") or []:
        pid = str(p.get("pillar_id") or p.get("name") or "").lower()
        if not pid.endswith("retail"):
            continue
        metric = str(p.get("north_star_metric") or "")
        m = re.match(r"([a-z_]+?)_(monthly|weekly|revenue|sales|per)", metric)
        if m:
            return m.group(1).replace("_", " ").title()
    return ""


def services_for(brand_id: str) -> List[Dict[str, str]]:
    """Fitting, coaching, membership... from the pillars and the brand's verified services."""
    out: Dict[str, Dict[str, str]] = {}
    cfg = _read(brand_id, "calendar_config.json")
    for p in cfg.get("pillars") or []:
        name = str(p.get("name") or "").strip()
        if name and name.lower() != "retail":
            out.setdefault(name.lower(), {"name": name, "detail": "Pillar"})
    know = _read(brand_id, "knowledge.json")
    for f in know.get("services") or []:
        subj = str(f.get("subject") or "").strip()
        if subj:
            key = subj.lower()
            if key not in out:
                out[key] = {"name": subj.title() if subj.islower() else subj,
                            "detail": str(f.get("value") or "")[:140]}
    return list(out.values())


def _matches(name: str, focus: str) -> bool:
    return bool(focus) and all(t in name.lower() for t in focus.lower().split())


def _why_not(r: Dict[str, Any]) -> str:
    if r["status"] == "out":
        return "Out of stock"
    if r["status"] == "low":
        return f"{r['qty']} left, at or under the alert level"
    if r["status"] == "error":
        return f"Quantity is {r['qty']}, check the count"
    return f"Not a deep shelf ({r['qty']} on shelf; deep needs 6+ and 3x the alert level)"


def build(brand_id: str, max_items: int = MAX_ITEMS) -> Dict[str, Any]:
    """The candidate_offers block for a brief (system_draft, operator_editable)."""
    focus = focus_product(brand_id)
    base = {"type": "system_draft", "operator_editable": True,
            "supports_north_star": SUPPORTS, "focus_product": focus,
            "items": [], "catalogue": [], "services": services_for(brand_id)}
    snaps = _snapshots(brand_id)
    if not snaps:
        return dict(base, status="no_stock_data",
                    note="No stock list imported for this brand yet, so there are no "
                         "stock suggestions. Choose a service or write the offer by hand.")
    from _lib import stock_pulse as sp
    results = [r for r in sp.analyse(snaps) if not r["not_for_feed"] and not r.get("folded_into_range")]

    def label(r):
        return r["range_name"] if r.get("range_name") and r["category"] in ("grip", "towel", "ferrule") else r["name"]

    def suggested(r):
        if r["status"] in ("low", "out", "error"):
            return False
        return r["status"] in ("stuck", "still", "new", "back") or r["deep_shelf"] or _matches(r["name"], focus)

    pick = [r for r in results if suggested(r)]
    pick.sort(key=lambda r: (_matches(r["name"], focus), r["feed_boost"], r["days_still"] * r["qty"], r["qty"]),
              reverse=True)
    top = {id(r) for r in pick[:max_items]}

    def entry(r, is_sug):
        why = (f"North Star product ({focus}), {r['qty']} on shelf" if _matches(r["name"], focus) and is_sug
               else (r["reason"] or f"{r['qty']} on the shelf") if is_sug else _why_not(r))
        return {"name": label(r), "category": r["category"], "qty": r["qty"],
                "days_unchanged": r["days_still"], "status": r["status"], "reason": why,
                "idea": r.get("idea") or "", "suggested": is_sug,
                "north_star_product": _matches(r["name"], focus),
                "supports_north_star": SUPPORTS, "price": "", "discount": ""}

    items = [entry(r, True) for r in pick[:max_items]]
    catalogue = sorted((entry(r, id(r) in top) for r in results), key=lambda e: e["name"].lower())
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
                catalogue=catalogue, snapshots=len(snaps), latest_list=latest, note=note)


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
