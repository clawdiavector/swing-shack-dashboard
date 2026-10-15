"""
stock_pulse.py — weekly stock lists decide what earns feed time.

Each weekly stocklist is kept as a dated snapshot beside the product catalog.
Comparing snapshots shows what is selling (quantity falls), what is "still"
(quantity unchanged for weeks) and what is thin (at or under its alert level).
Still and heavy stock earns a feed boost; thin and out-of-stock does not.

A weekly level file only shows quantity, so "still" means "no net movement".
A sale cancelled out by a restock looks still too. It is a prompt to look, not proof.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date as _date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Days with no change in quantity before a product counts as still / stuck.
STILL_DAYS = 14
STUCK_DAYS = 28
# Shelf is heavy when quantity is at least this many times its alert level.
HEAVY_ALERT_MULTIPLE = 3
# With no alert level to compare against, this many units is a heavy shelf.
HEAVY_NO_ALERT_UNITS = 15
# ...and never fewer than this many units.
HEAVY_MIN_UNITS = 6
# A line stays "new" (worth announcing) for this long after it first appears.
NEW_DAYS = 21

# Added to the planner's priority score (marketing_lanes.propose_product_calendar).
FEED_BOOST = {
    "stuck": 60, "still": 40, "new": 45, "back": 25, "heavy": 25,
    "selling": 0, "steady": 0, "low": -20, "out": 0, "error": 0,
}

# The list is for things sold as they are. Drinks, snacks and food are never
# promoted, and shafts are fitting components, mentioned in fitting content and
# never pushed one by one. Add a pattern when a new line turns up.
EXCLUDED = [
    ("drink or food", re.compile(
        r"\bfull swing\b|\b(still|sparkling) water\b|\b(water|drink|soda|cola|juice|coffee|beer|"
        r"snack|biltong|chips|biscuit|chocolate|sandwich|toastie|food)\b", re.I)),
    ("fitting component", re.compile(r"\bdriver shafts?\b|\b(tensei|speeder|kbs|dynamic gold)\b", re.I)),
]


def excluded_reason(name: str) -> str:
    for reason, pattern in EXCLUDED:
        if pattern.search(name):
            return reason
    return ""

CATEGORY_RULES = [
    ("rangefinder", r"rangefinder"),
    ("putter", r"putter|sausage|runner"),
    ("wedge", r"wedge|vokey"),
    ("driver-wood", r"driver|3 wood|\bwood\b"),
    ("shaft", r"shaft|tensei|speeder"),
    ("bag", r"golf bag"),
    ("towel", r"towel"),
    ("glove", r"glove|cabretta|perma soft|stasof|weathersoft|raingrip|sofjoy|sciflex|hyper flex|all weather"),
    ("ferrule", r"ferrule"),
    ("grip", r"grip|pride|lamkin|tour velvet"),
    ("ball", r"titleist (tru feel|tour soft|pro v1|velocity|avx)|srixon (z|q|soft)|chrome|quantum|vice (pro|drive|tour)"),
]

PUSH_IDEAS = {
    "ball": "Ball-fitting tie-in, or a sleeve/dozen offer",
    "glove": "Glove sizing and the right glove for the weather",
    "grip": "Re-grip service tie-in",
    "putter": "Putter fitting on the launch monitor",
    "wedge": "Wedge fitting / gapping session",
    "driver-wood": "Driver fitting on the launch monitor",
    "shaft": "Shaft fitting on the launch monitor",
    "bag": "Close-up of the bag with what fits inside",
    "rangefinder": "On-course use, side by side with the others",
    "towel": "Gift or add-on idea",
    "ferrule": "Custom-build detail: the finishing touch on a club",
}

# Grips, ferrules and towels are promoted as a range per brand ("GripDrip is
# available at ..."), never one colourway at a time.
RANGE_CATEGORIES = {"grip": "grips", "ferrule": "ferrules", "towel": "towels"}
RANGE_BRANDS = [
    ("GripDrip", r"^grip ?drip|^tropical vibes"),
    ("RipIt", r"^rip ?it"),
    ("Golf Pride", r"^golf pride"),
    ("AJM GripCo", r"^ajm"),
    ("Lamkin", r"^lamkin"),
    ("BB&F Co", r"^bb&f"),
]


def range_name_for(name: str, category: str) -> str:
    """'GripDrip grips' for a member of a range, else ''."""
    word = RANGE_CATEGORIES.get(category)
    if not word:
        return ""
    for brand, pattern in RANGE_BRANDS:
        if re.search(pattern, name, re.I):
            return f"{brand} {word}"
    first = re.split(r"[\s\-]+", name.strip())[0]
    return f"{first} {word}"


def strip_excel_sep(text: str) -> str:
    """Excel writes a `sep=,` first line; DictReader would take it as the header."""
    text = text.lstrip("﻿")
    first, _, rest = text.partition("\n")
    if re.match(r"^\s*sep=.?\s*$", first):
        return rest
    return text


def _int(v: Any) -> Optional[int]:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


SIZE_VARIANT = re.compile(
    r"^(xxs|xs|s|m|l|xl|xxl|xxxl|m/l|o/s|os|pw|sw|aw|gw|lw|standard|midsize|small|medium|large|"
    r"extra large|medium large|\d{1,2}t?|\d{1,2}/\d{1,2}|[sml]/\d|xl/\d)$", re.I)


def product_key(name: str, variant: str) -> str:
    """A size or colour-and-size variant belongs to its product. Any other variant is a
    different model ("Callaway Chrome Tour" / "Chrome Tour Triple Diamond"), kept apart."""
    v = (variant or "").strip()
    if categorise(name) == "ball":
        # Colours of one ball model are one entry; each model stays its own.
        name = re.sub(rf"\s+-\s+({BALL_COLOURS})$", "", name.strip(), flags=re.I)
    if not v or ";" in v or SIZE_VARIANT.match(v):
        return name
    return f"{name} ({v})"


def parse_stock_csv(text: str) -> List[Dict[str, Any]]:
    """Canonical stock export -> [{sku, name, variant, qty, alert}]."""
    reader = csv.DictReader(io.StringIO(strip_excel_sep(text)))
    out = []
    for row in reader:
        name = (row.get("Product Name") or "").strip()
        if not name:
            continue
        out.append({
            "sku": (row.get("SKU") or "").strip(),
            "name": product_key(name, row.get("Variant Choices") or ""),
            "variant": (row.get("Variant Choices") or "").strip(),
            "qty": _int(row.get("Quantity")) or 0,
            "alert": _int(row.get("Alert Level")),
        })
    return out


_BALL_MODELS: Optional[List[Dict[str, Any]]] = None
BALL_COLOURS = r"white|yellow|blue|green|pink|red|orange|purple|black|grey|lime|neon|drip"


def ball_profile(name: str) -> Optional[Dict[str, Any]]:
    """The ball model a stock line belongs to, with what the maker says it is known for."""
    global _BALL_MODELS
    if _BALL_MODELS is None:
        f = Path(__file__).resolve().parents[2] / "data" / "brand-directory" / "_system" / "ball-models.json"
        try:
            _BALL_MODELS = json.loads(f.read_text(encoding="utf-8"))["models"]
        except Exception:
            _BALL_MODELS = []
    for m in _BALL_MODELS:
        if re.search(m["match"], name, re.I):
            return m
    return None


def categorise(name: str) -> str:
    for cat, pattern in CATEGORY_RULES:
        if re.search(pattern, name, re.I):
            return cat
    return "other"


# ── Snapshots ───────────────────────────────────────────────────────────
def _history_dir(brand_id: str, create: bool = False) -> Path:
    from _lib.marketing_lanes import _products_dir
    d = _products_dir(brand_id) / "stock-history"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def save_snapshot(brand_id: str, rows: List[Dict[str, Any]], on: Optional[str] = None) -> str:
    """Write one dated snapshot (a same-day upload replaces the earlier one)."""
    on = (on or _date.today().isoformat())[:10]
    payload = {"brand_id": brand_id, "date": on, "rows": rows}
    (_history_dir(brand_id, create=True) / f"{on}.json").write_text(json.dumps(payload), encoding="utf-8")
    return on


def load_snapshots(brand_id: str) -> List[Dict[str, Any]]:
    snaps = []
    for p in sorted(_history_dir(brand_id).glob("*.json")):
        try:
            snaps.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return snaps


def _by_product(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Variants (sizes) roll up to their product."""
    prods: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        p = prods.setdefault(r["name"], {"qty": 0, "alert": None, "variants": [], "skus": []})
        p["qty"] += r["qty"]
        if r.get("alert") is not None:
            p["alert"] = (p["alert"] or 0) + r["alert"]
        p["variants"].append(r)
        if r.get("sku"):
            p["skus"].append(r["sku"])
    return prods


def _days(a: str, b: str) -> int:
    return (datetime.fromisoformat(b[:10]) - datetime.fromisoformat(a[:10])).days


def _ball_idea(name: str) -> str:
    prof = ball_profile(name)
    if prof and prof["known_for"]:
        return (f"Show it as the {prof['model']}: {prof['known_for']} Tie in with a ball fitting "
                "(the shop offers them) to find the right one.")
    return "Ball model: no maker wording on file yet, add a sourced 'known for' line before writing about it."


def _item_results(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Status, feed boost and reason per product from the snapshot history."""
    if not snapshots:
        return []
    snaps = [(s["date"], _by_product(s["rows"])) for s in snapshots]
    latest_date, latest = snaps[-1]
    results = []
    for name, now in latest.items():
        qty, alert = now["qty"], now["alert"]
        history = [(d, prods[name]["qty"]) for d, prods in snaps if name in prods]
        prev_qty = history[-2][1] if len(history) > 1 else None
        first_seen = history[0][0]
        # Only lines that appear after the first list are known to be new.
        just_in = snaps[0][0] != first_seen and _days(first_seen, latest_date) <= NEW_DAYS
        # How long the quantity has sat at today's level.
        still_since = latest_date
        for d, q in reversed(history):
            if q != qty:
                break
            still_since = d
        days_still = _days(still_since, latest_date) if len(history) > 1 else 0
        # An alert level of 1 is how a one-off piece is held, not a reorder trigger.
        thin_variants = [v["variant"] or v["sku"] for v in now["variants"]
                         if v.get("alert") and v["alert"] >= 2 and v["qty"] <= v["alert"]]

        if qty < 0:
            status, reason = "error", f"Quantity is {qty}, check the count"
        elif qty == 0:
            status, reason = "out", "Out of stock"
        elif just_in:
            status, reason = "new", f"New on the shelf, first listed {first_seen}"
        elif prev_qty == 0 and qty > 0:
            status, reason = "back", f"Back in stock ({qty})"
        elif alert and alert >= 2 and qty <= alert:
            status, reason = "low", f"{qty} left, at or under the alert level of {alert}"
        elif days_still >= STUCK_DAYS:
            status, reason = "stuck", f"Unchanged at {qty} for {days_still} days"
        elif days_still >= STILL_DAYS:
            status, reason = "still", f"Unchanged at {qty} for {days_still} days"
        elif prev_qty is not None and qty < prev_qty:
            status, reason = "selling", f"Down {prev_qty - qty} since the last list"
        elif (alert and qty >= max(alert * HEAVY_ALERT_MULTIPLE, HEAVY_MIN_UNITS)) or (not alert and qty >= HEAVY_NO_ALERT_UNITS):
            status = "heavy"
            reason = (f"{qty} on the shelf against an alert level of {alert}" if alert
                      else f"{qty} on the shelf")
        else:
            status, reason = "steady", ""

        # Heavy applies on top of selling/steady: a deep shelf that is moving still has a lot to move.
        deep = bool((alert and qty >= max(alert * HEAVY_ALERT_MULTIPLE, HEAVY_MIN_UNITS)) or (not alert and qty >= HEAVY_NO_ALERT_UNITS))
        cat = categorise(name)
        results.append({
            "name": name, "category": cat, "qty": qty, "alert": alert,
            "prev_qty": prev_qty, "days_still": days_still, "status": status,
            "deep_shelf": deep, "reason": reason, "skus": now["skus"],
            "thin_variants": thin_variants,
            "feed_boost": 0 if excluded_reason(name) else FEED_BOOST[status],
            "not_for_feed": bool(excluded_reason(name)),
            "excluded_reason": excluded_reason(name),
            "idea": (_ball_idea(name) if cat == "ball" else PUSH_IDEAS.get(cat, ""))
                    if status in ("stuck", "still", "heavy", "new", "back") else "",
            "ball_model": (ball_profile(name) or {}).get("model", "") if cat == "ball" else "",
            "known_for": (ball_profile(name) or {}).get("known_for", "") if cat == "ball" else "",
            "range_name": range_name_for(name, cat),
            "first_seen": first_seen,
            "snapshots_seen": len(history),
        })
    return results


def _range_rows(snapshots: List[Dict[str, Any]], items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per brand range with 2+ lines: summed units, newest line, combined stillness."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        if it["range_name"] and not it["not_for_feed"]:
            groups.setdefault(it["range_name"], []).append(it)
    rows = []
    for rname, members in groups.items():
        if len(members) < 2:
            continue
        names = {m["name"] for m in members}
        series = [(s["date"], sum(r["qty"] for r in s["rows"] if r["name"] in names)) for s in snapshots]
        units, latest_date = series[-1][1], series[-1][0]
        since = latest_date
        for d, q in reversed(series):
            if q != units:
                break
            since = d
        days_still = _days(since, latest_date) if len(series) > 1 else 0
        new = [m for m in members if m["status"] == "new"]
        back = [m for m in members if m["status"] == "back"]
        if units <= 0:
            status, reason = "out", "Whole range out of stock"
        elif new:
            status = "new"
            reason = f"{len(new)} new line(s) in the range: " + ", ".join(m["name"] for m in new[:4])
        elif back:
            status, reason = "back", f"{len(back)} line(s) back in stock"
        elif days_still >= STUCK_DAYS:
            status, reason = "stuck", f"Range unchanged at {units} units for {days_still} days"
        elif days_still >= STILL_DAYS:
            status, reason = "still", f"Range unchanged at {units} units for {days_still} days"
        else:
            status, reason = "steady", ""
        rows.append({
            "name": rname, "is_range": True, "category": members[0]["category"], "qty": units,
            "alert": None, "prev_qty": series[-2][1] if len(series) > 1 else None,
            "days_still": days_still, "status": status, "deep_shelf": False, "reason": reason,
            "skus": [k for m in members for k in m["skus"]], "thin_variants": [],
            "feed_boost": FEED_BOOST[status], "not_for_feed": False, "excluded_reason": "",
            "idea": "Range post: where to buy it, the colours in stock" if status != "steady" else "",
            "range_name": rname, "members": [m["name"] for m in members],
            "first_seen": min(m["first_seen"] for m in members), "snapshots_seen": len(series),
        })
    return rows


def analyse(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What the planner and the report work from: single lines sold as-is, plus one
    row per brand range. Range members are returned too, marked folded_into_range."""
    items = _item_results(snapshots)
    ranges = _range_rows(snapshots, items)
    folded = {r["range_name"] for r in ranges}
    single = [it for it in items if it["range_name"] not in folded]
    members = [dict(it, folded_into_range=True) for it in items if it["range_name"] in folded]
    return single + ranges + members


def push_list(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Products worth pushing, biggest stuck pile first."""
    pushes = [r for r in results if r["status"] in ("stuck", "still") and not r["not_for_feed"] and not r.get("folded_into_range")]
    pushes.sort(key=lambda r: (r["days_still"] * r["qty"]), reverse=True)
    return pushes


def heavy_shelf(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deep stock against alert level. Needs one snapshot, so it works from week one."""
    heavy = [r for r in results if r["deep_shelf"] and r["status"] not in ("low", "out", "error")
             and not r["not_for_feed"] and not r.get("folded_into_range")]
    heavy.sort(key=lambda r: r["qty"] / (r["alert"] or 1), reverse=True)
    return heavy


def data_problems(results: List[Dict[str, Any]], rows: List[Dict[str, Any]]) -> List[str]:
    """Things in the file that look wrong and would mislead the planner."""
    out = []
    for r in results:
        if r["status"] == "error":
            out.append(f"{r['name']}: quantity {r['qty']}")
    no_alert = sum(1 for r in results if not r["alert"] and not r["not_for_feed"])
    if no_alert:
        out.append(f"{no_alert} products have no alert level, so 'heavy' falls back to {HEAVY_NO_ALERT_UNITS}+ units")
    sku_seen: Dict[str, str] = {}
    for r in rows:
        if r["sku"] and r["sku"] in sku_seen and sku_seen[r["sku"]] != r["name"]:
            out.append(f"SKU {r['sku']} is on both '{sku_seen[r['sku']]}' and '{r['name']}'")
        sku_seen.setdefault(r["sku"], r["name"])
    blank = [r["name"] for r in rows if not r["sku"]]
    if blank:
        out.append(f"{len(blank)} line(s) have no SKU, so they cannot be matched week to week or stamped: "
                   + ", ".join(blank[:4]))
    odd = [r["sku"] for r in rows if r["sku"] and not re.fullmatch(r"[A-Za-z0-9\-_]+", r["sku"])]
    if odd:
        out.append(f"{len(odd)} SKUs contain odd characters ({', '.join(odd[:4])}...)")
    return out


# ── Wiring into the catalog ─────────────────────────────────────────────
def record_and_stamp(brand_id: str, csv_text: str, products: List[Dict[str, Any]],
                     on: Optional[str] = None) -> Dict[str, Any]:
    """Save this week's snapshot, then stamp status and boost onto catalog records."""
    rows = parse_stock_csv(csv_text)
    save_snapshot(brand_id, rows, on)
    results = analyse(load_snapshots(brand_id))
    by_sku = {}
    for r in results:
        if r.get("folded_into_range"):
            continue  # the range row already carries these SKUs
        for s in r["skus"]:
            by_sku[s] = r
    stamped = 0
    for p in products:
        r = by_sku.get(p.get("sku"))
        if r:
            p["stock_status"] = r["status"]
            p["days_still"] = r["days_still"]
            p["feed_boost"] = r["feed_boost"]
            p["push_reason"] = r["reason"]
            p["not_for_feed"] = r["not_for_feed"]
            p["range_name"] = r["name"] if r.get("is_range") else ""
            stamped += 1
    try:
        from _lib.photo_map import stamp_catalog
        photos = stamp_catalog(brand_id, products)
    except Exception:
        photos = 0
    return {"snapshots": len(load_snapshots(brand_id)), "stamped": stamped, "with_approved_photo": photos,
            "push": [r["name"] for r in push_list(results)]}


# ── Real photo lookup ───────────────────────────────────────────────────
# The make comes first in a stock name. Golf is model-specific, so a photo of the
# right maker and the wrong model is not a match.
MAKERS = {
    "titleist", "srixon", "callaway", "taylormade", "footjoy", "ping", "odyssey", "takomo",
    "mileseey", "gripdrip", "golfpride", "fullswing", "lab", "lagolf", "mitsubishi", "fujikura",
    "herschel", "jordan", "vice", "lamkin", "ajm", "vessel", "scottycameron",
}
GENERIC_TOKENS = {
    "golf", "putter", "putters", "driver", "wood", "wedge", "bag", "glove", "grip", "swing",
    "magnet", "towel", "rangefinder", "shafts", "shaft", "the", "and", "set", "ss", "pro",
    "white", "yellow", "blue", "green", "red", "black", "grey", "navy", "small", "medium",
    "large", "extra", "standard", "midsize", "2025", "2026", "grips", "ferrules", "towels",
}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _norm(s: str) -> str:
    s = s.lower().replace("l.a.b", "lab").replace("foot joy", "footjoy").replace("la golf", "lagolf")
    s = s.replace("golf pride", "golfpride").replace("full swing", "fullswing")
    return s.replace("scotty cameron", "scottycameron")


def _tokens(s: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", _norm(s)) if t not in GENERIC_TOKENS]


def match_photos(product_name: str, images_dir: Path) -> Dict[str, Any]:
    """Find real photos for one product by filename.

    exact: the filename carries the maker and every model word. Still worth a look.
    candidate: the maker and at least one model word match, but not all. For a person
    to check by eye, never used automatically.
    none: nothing usable.
    """
    need = _tokens(product_name)
    maker = next((t for t in need if t in MAKERS), None)
    model = [t for t in need if t != maker]
    exact, partial = [], []
    if not maker or not images_dir.exists():
        return {"match": "none", "exact": [], "candidates": []}
    for f in images_dir.rglob("*"):
        if f.suffix.lower() not in IMAGE_EXT:
            continue
        words = set(re.findall(r"[a-z0-9]+", _norm(f.stem)))
        compact = re.sub(r"[^a-z0-9]", "", _norm(f.stem))
        if maker not in words and maker not in compact:
            # Photos are often named for the model alone (genesonic1.jpg). Never exact
            # without the make, but worth a person's look.
            if any(len(t) >= 4 and t in compact for t in model):
                partial.append((0, str(f)))
            continue

        def has(t: str) -> bool:
            return t in words or (len(t) >= 3 and t in compact)

        hit = [t for t in model if has(t)]
        # "Z-Star XV" may be filed as zstar_xv: the joined model words count too.
        joined = len("".join(model)) >= 4 and "".join(model) in compact
        if model and (len(hit) == len(model) or joined):
            exact.append(str(f))
        elif not model:
            partial.append((0, str(f)))  # a brand range: any real photo of the brand, for a person to check
        elif hit:
            partial.append((len(hit), str(f)))
    partial.sort(reverse=True)
    return {
        "match": "exact" if exact else ("candidate" if partial else "none"),
        "exact": exact,
        "candidates": [p for _, p in partial[:3]],
    }
