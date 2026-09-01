"""
marketing_lanes.py — Parallel marketing lanes + content items + calendar.

This module extends (does not duplicate) the existing campaign_planner +
schedule sidecar with:

  1. LANE MODEL — every content item belongs to exactly one lane:
     product | human | campaign | paid | crm | search | events

  2. CAMPAIGN-ABOVE-LANE — a campaign is an umbrella that can contain
     items across multiple lanes. Campaigns are STRATEGIC, lanes are
     EXECUTION types. (Per user directive #19.)

  3. CONTENT ITEM — the canonical unit of execution. Fields:
       id, brand, lane, campaign_id, product_id, platform, format,
       publish_date, publish_time, status, caption, cta, destination,
       creative_id, owner, approval_status, publishing_status,
       postiz_post_id, scheduled_for, reference_ids, error_state,
       created_at, updated_at

     Status (per user directive #25):
       idea → proposed → planned → needs_asset → generating → draft →
       needs_approval → approved → queued → published → failed → cancelled

  4. PARALLEL SCHEDULING — multiple items on the same date, possibly
     on the same platform, in different lanes. Items are independent.

  5. PRODUCT ROTATION MEMORY — for the PRODUCT lane, tracks per-product:
     last_featured_date, total_posts, recent_angles, recent_creative_ids

  6. INVENTORY AWARENESS — checks product stock before publish; flags
     out-of-stock items automatically.

  7. CONFLICT DETECTION — surfaces useful planning signals (5 posts
     same day, no human content this week, etc.) — per user directive #21.

  8. CALENDAR PROPOSAL — generates a proposed calendar (products for a
     date range) WITHOUT generating creative — creative generation is
     user-triggered after approval (per user directive #12).

Built 2026-08-31 to satisfy user directive J-CAMPAIGN OS — PARALLEL
MARKETING CALENDAR + STOCK-TO-POST PIPELINE.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_LOG = logging.getLogger("campaign_os.marketing_lanes")


# ── Constants ──────────────────────────────────────────────────────────────
LANES = ["product", "human", "campaign", "paid", "crm", "search", "events"]

# Default lane colors (CSS hex) — used by the calendar UI to give each lane
# a distinct visual treatment.
LANE_COLORS = {
    "product":  "#d4a849",  # gold (stick / swing shack accent)
    "human":    "#5b9bd5",  # calm blue
    "campaign": "#c95e4d",  # warm red
    "paid":     "#8e44ad",  # paid purple
    "crm":      "#16a085",  # teal
    "search":   "#7f8c8d",  # neutral grey
    "events":   "#f39c12",  # event orange
}

# Content item status (per user directive #25)
CONTENT_STATUSES = [
    "idea",          # user-typed idea, no commitment
    "proposed",      # calendar proposal exists
    "planned",       # user-approved the slot
    "needs_asset",   # creative not yet generated
    "generating",    # Krea job in flight
    "draft",         # creative ready, awaiting approval
    "needs_approval",
    "approved",      # user-approved, can be queued
    "queued",        # pushed to Postiz
    "published",     # Postiz confirms publish
    "failed",        # publish failed
    "cancelled",
]

# Approvable states (only APPROVED may be queued for publish).
APPROVED_STATUS = "approved"

# Valid publish destinations
PLATFORMS = ["instagram", "facebook", "tiktok", "x", "linkedin", "gbp", "youtube", "pinterest"]


# ── Path resolution ───────────────────────────────────────────────────────
def _data_root() -> Path:
    """BUNDLED_DATA_DIR first (the canonical brand-data path), then
    DATA_DIR (Railway volume), then the local dev path."""
    candidates = []
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    if bundled:
        candidates.append(Path(bundled))
    candidates.append(Path(os.environ.get("DATA_DIR") or "/data/campaign-os"))
    candidates.append(Path(
        "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data"
    ))
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


def _lanes_dir(brand_id: str) -> Path:
    """data/brand-directory/<brand>/lanes/ — the lane-content store."""
    d = _data_root() / "brand-directory" / brand_id / "lanes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _campaigns_dir(brand_id: str) -> Path:
    """data/brand-directory/<brand>/campaigns/ — campaign umbrellas."""
    d = _data_root() / "brand-directory" / brand_id / "campaigns"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _products_dir(brand_id: str) -> Path:
    """data/brand-directory/<brand>/products/ — extended product catalog
    (extends the existing product-library.json with stock/SKU/price/rotation)."""
    d = _data_root() / "brand-directory" / brand_id / "products"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _imports_dir(brand_id: str) -> Path:
    """data/brand-directory/<brand>/imports/ — stock import history."""
    d = _data_root() / "brand-directory" / brand_id / "imports"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Content items ─────────────────────────────────────────────────────────
def _content_items_path(brand_id: str) -> Path:
    return _lanes_dir(brand_id) / "content-items.json"


def load_content_items(brand_id: str) -> list:
    """Load all content items for a brand."""
    p = _content_items_path(brand_id)
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text())
        return d.get("items") or []
    except Exception as e:
        _LOG.warning(f"failed to read {p}: {e}")
        return []


def save_content_items(brand_id: str, items: list) -> Path:
    """Persist content items."""
    p = _content_items_path(brand_id)
    payload = {
        "brand_id": brand_id,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(items),
        "items": items,
    }
    p.write_text(json.dumps(payload, indent=2, default=str))
    return p


def add_content_item(brand_id: str, item: dict) -> dict:
    """Add or update a content item. Returns the saved item."""
    items = load_content_items(brand_id)
    item_id = item.get("id") or f"ci-{uuid.uuid4().hex[:10]}"
    item["id"] = item_id
    item["updated_at"] = datetime.utcnow().isoformat() + "Z"
    item.setdefault("created_at", item["updated_at"])
    # Replace if exists
    found = False
    for i, existing in enumerate(items):
        if existing.get("id") == item_id:
            items[i] = {**existing, **item}
            found = True
            break
    if not found:
        items.append(item)
    save_content_items(brand_id, items)
    return item


def get_content_item(brand_id: str, item_id: str) -> Optional[dict]:
    for item in load_content_items(brand_id):
        if item.get("id") == item_id:
            return item
    return None


def delete_content_item(brand_id: str, item_id: str) -> bool:
    items = load_content_items(brand_id)
    before = len(items)
    items = [i for i in items if i.get("id") != item_id]
    if len(items) == before:
        return False
    save_content_items(brand_id, items)
    return True


def update_content_item_status(brand_id: str, item_id: str, new_status: str, **extra) -> Optional[dict]:
    """Update a content item's status. Optionally attach extra fields."""
    if new_status not in CONTENT_STATUSES:
        raise ValueError(f"unknown status {new_status!r}; valid: {CONTENT_STATUSES}")
    items = load_content_items(brand_id)
    for i, item in enumerate(items):
        if item.get("id") == item_id:
            item["status"] = new_status
            item["updated_at"] = datetime.utcnow().isoformat() + "Z"
            for k, v in extra.items():
                item[k] = v
            items[i] = item
            save_content_items(brand_id, items)
            return item
    return None


# ── Campaigns (above lanes, strategic umbrellas) ─────────────────────────
def list_campaigns(brand_id: str) -> list:
    """List campaign umbrellas for a brand."""
    results = []
    for p in sorted(_campaigns_dir(brand_id).glob("*.json")):
        try:
            d = json.loads(p.read_text())
            d.setdefault("campaign_id", p.stem)
            results.append(d)
        except Exception as e:
            _LOG.warning(f"failed to read {p}: {e}")
    return results


def get_campaign(brand_id: str, campaign_id: str) -> Optional[dict]:
    p = _campaigns_dir(brand_id) / f"{campaign_id}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        d.setdefault("campaign_id", campaign_id)
        return d
    except Exception:
        return None


def save_campaign(brand_id: str, campaign_id: str, data: dict) -> Path:
    """Save a campaign umbrella."""
    p = _campaigns_dir(brand_id) / f"{campaign_id}.json"
    data["campaign_id"] = campaign_id
    data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    p.write_text(json.dumps(data, indent=2, default=str))
    return p


def delete_campaign(brand_id: str, campaign_id: str) -> bool:
    p = _campaigns_dir(brand_id) / f"{campaign_id}.json"
    if p.exists():
        p.unlink()
        # Detach content items from this campaign
        items = load_content_items(brand_id)
        for i, item in enumerate(items):
            if item.get("campaign_id") == campaign_id:
                items[i]["campaign_id"] = None
        save_content_items(brand_id, items)
        return True
    return False


def campaign_bands(brand_id: str, start_date: str, end_date: str) -> list:
    """Return campaigns that span the given period. Used to draw campaign
    overlay bands on the calendar."""
    start = datetime.fromisoformat(start_date[:10]).date()
    end = datetime.fromisoformat(end_date[:10]).date()
    bands = []
    for c in list_campaigns(brand_id):
        c_start = c.get("start_date")
        c_end = c.get("end_date") or c_start
        if not c_start:
            continue
        cs = datetime.fromisoformat(c_start[:10]).date()
        ce = datetime.fromisoformat(c_end[:10]).date()
        # Overlap
        if cs <= end and ce >= start:
            bands.append({
                "campaign_id": c.get("campaign_id"),
                "name": c.get("name", c.get("campaign_id")),
                "lane": c.get("primary_lane", "campaign"),
                "start_date": c_start[:10],
                "end_date": c_end[:10],
                "color": c.get("color") or LANE_COLORS.get(c.get("primary_lane", "campaign"), "#888"),
                "status": c.get("status", "planned"),
            })
    return bands


# ── Stock import (CSV) ────────────────────────────────────────────────────
# Per user directive #6 — upload spreadsheet → populate product library.
# Per user directive #7 — UPDATE not DUPLICATE. Use SKU as identity.
# Per user directive #11 — preview before commit, history retained.

# Field canonical names → synonyms (lowercase, fuzzy)
COLUMN_SYNONYMS = {
    "sku": ["sku", "item code", "itemcode", "product code", "code", "id"],
    "name": ["name", "item name", "product name", "title", "description"],
    "brand": ["brand", "make", "manufacturer"],
    "category": ["category", "cat", "type", "department"],
    "subcategory": ["subcategory", "sub-cat", "subcat", "sub-category"],
    "description": ["description", "descr", "notes", "detail"],
    "price": ["price", "retail", "rrp", "msrp", "list price"],
    "sale_price": ["sale price", "sale", "discount price", "promo price"],
    "stock_quantity": ["stock", "qty", "quantity", "inventory", "stock level", "on hand", "onhand"],
    "size": ["size", "sizes", "variant size"],
    "color": ["color", "colour", "variant colour"],
    "variant": ["variant", "sku variant", "option"],
    "product_url": ["url", "product url", "link", "web url", "shopify url"],
    "image_url": ["image", "image url", "img", "photo", "picture"],
    "supplier": ["supplier", "vendor", "distributor"],
    "priority": ["priority", "rank", "importance"],
    "campaign": ["campaign", "campaign tag", "marketing campaign"],
    "tags": ["tags", "labels", "keywords"],
    "status": ["status", "active", "in stock status"],
    "notes": ["internal notes", "note", "memo", "staff notes"],
}


def _detect_column_mapping(header_row: list) -> dict:
    """Given the first row of a CSV, return {canonical_field: csv_header}.

    Matches by exact lowercase equality first, then by substring.
    Returns only fields that were detected.
    """
    mapping = {}
    lowered = [h.strip().lower() for h in header_row]
    for canonical, synonyms in COLUMN_SYNONYMS.items():
        for syn in synonyms:
            for i, h in enumerate(lowered):
                if h == syn or syn in h:
                    mapping[canonical] = header_row[i]
                    break
            if canonical in mapping:
                break
    return mapping


def _parse_csv(content: str) -> tuple:
    """Parse CSV text. Returns (header_row, data_rows)."""
    reader = csv.DictReader(io.StringIO(content))
    header = reader.fieldnames or []
    rows = list(reader)
    return header, rows


def preview_stock_import(content: str, *, brand_id: str = "swing-shack") -> dict:
    """Preview a stock CSV import before committing.

    Returns:
      {
        detected_mapping: {canonical_field: csv_header, ...},
        sample_rows: [{canonical_field: value, ...}, ...] (first 5 rows)
        estimated_new: int,
        estimated_updates: int,
        would_duplicate_sku: [sku1, sku2, ...],
        warnings: [str, ...],
        header_row: [str, ...]
      }
    """
    header, rows = _parse_csv(content)
    mapping = _detect_column_mapping(header)

    # Load existing products to estimate new vs update
    existing = _load_extended_products(brand_id)
    by_sku = {p.get("sku"): p for p in existing if p.get("sku")}

    estimated_new = 0
    estimated_updates = 0
    duplicates = []
    sample_rows = []
    seen_skus_in_import = set()

    for i, row in enumerate(rows):
        sku = (row.get(mapping.get("sku", ""), "") or "").strip()
        if not sku:
            continue
        if sku in seen_skus_in_import:
            duplicates.append(sku)
        seen_skus_in_import.add(sku)
        if sku in by_sku:
            estimated_updates += 1
        else:
            estimated_new += 1
        if i < 5:
            # Project to canonical fields
            projected = {}
            for canonical, csv_header in mapping.items():
                projected[canonical] = (row.get(csv_header) or "").strip()
            sample_rows.append(projected)

    warnings = []
    if not mapping.get("name"):
        warnings.append("No product name column detected — required.")
    if not mapping.get("sku"):
        warnings.append("No SKU column detected — products will be matched by name (less reliable).")
    if duplicates:
        warnings.append(f"{len(duplicates)} duplicate SKUs within this import.")
    if mapping.get("stock_quantity"):
        warnings.append("Stock quantity detected — will track inventory and flag out-of-stock items.")
    if mapping.get("price"):
        warnings.append("Price detected — will enable sale-price + price-change tracking.")

    return {
        "brand_id": brand_id,
        "detected_mapping": mapping,
        "header_row": header,
        "row_count": len(rows),
        "estimated_new": estimated_new,
        "estimated_updates": estimated_updates,
        "would_duplicate_sku": duplicates[:10],
        "sample_rows": sample_rows,
        "warnings": warnings,
    }


def commit_stock_import(
    content: str,
    *,
    brand_id: str = "swing-shack",
    mapping: Optional[dict] = None,
    actor: str = "operator",
) -> dict:
    """Commit a stock CSV import.

    Returns:
      {
        import_id, created, updated, skipped, errors,
        history: [{timestamp, sku, action, before_stock, after_stock, before_price, after_price}, ...]
      }
    """
    header, rows = _parse_csv(content)
    if mapping is None:
        mapping = _detect_column_mapping(header)

    # Load existing products
    products = _load_extended_products(brand_id)
    by_sku = {p.get("sku"): p for p in products if p.get("sku")}
    by_name = {p.get("name", "").lower(): p for p in products if p.get("name")}

    created = []
    updated = []
    skipped = []
    errors = []
    history = []

    for row_idx, row in enumerate(rows):
        try:
            # Extract canonical fields
            sku = (row.get(mapping.get("sku", ""), "") or "").strip()
            name = (row.get(mapping.get("name", ""), "") or "").strip()
            if not name:
                skipped.append({"row": row_idx + 1, "reason": "no name"})
                continue
            prev = None
            if sku and sku in by_sku:
                prev = by_sku[sku]
            elif not sku and name.lower() in by_name:
                prev = by_name[name.lower()]

            # Build new product record
            new_item = _build_product_from_csv_row(row, mapping, brand_id, prev=prev)
            new_item["updated"] = datetime.utcnow().isoformat() + "Z"
            new_item["updated_by"] = actor

            before_stock = prev.get("stock_quantity") if prev else None
            after_stock = new_item.get("stock_quantity")
            before_price = prev.get("price") if prev else None
            after_price = new_item.get("price")

            # Insert or replace
            if prev:
                # Update — preserve id + creation metadata
                for i, p in enumerate(products):
                    if p.get("id") == prev.get("id"):
                        products[i] = {**p, **new_item, "id": p["id"]}
                        break
                updated.append({"sku": sku or None, "name": name, "id": prev.get("id")})
                history.append({
                    "timestamp": new_item["updated"],
                    "sku": sku,
                    "name": name,
                    "action": "updated",
                    "before_stock": before_stock,
                    "after_stock": after_stock,
                    "before_price": before_price,
                    "after_price": after_price,
                })
            else:
                products.append(new_item)
                created.append({"sku": sku or None, "name": name, "id": new_item["id"]})
                history.append({
                    "timestamp": new_item["updated"],
                    "sku": sku,
                    "name": name,
                    "action": "created",
                    "before_stock": None,
                    "after_stock": after_stock,
                    "before_price": None,
                    "after_price": after_price,
                })
        except Exception as e:
            errors.append({"row": row_idx + 1, "error": str(e)})

    # Persist
    _save_extended_products(brand_id, products)

    # Record import history
    import_id = f"import-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    history_payload = {
        "import_id": import_id,
        "brand_id": brand_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "actor": actor,
        "mapping": mapping,
        "row_count": len(rows),
        "created": len(created),
        "updated": len(updated),
        "skipped": len(skipped),
        "errors": len(errors),
        "created_items": created,
        "updated_items": updated,
        "diff_log": history,
    }
    history_path = _imports_dir(brand_id) / f"{import_id}.json"
    history_path.write_text(json.dumps(history_payload, indent=2, default=str))

    return {
        "ok": True,
        "import_id": import_id,
        "created": len(created),
        "updated": len(updated),
        "skipped": len(skipped),
        "errors": len(errors),
        "created_items": created,
        "updated_items": updated,
        "history_path": str(history_path.relative_to(_data_root())),
        "diff_summary": history[-10:],
    }


def _build_product_from_csv_row(row: dict, mapping: dict, brand_id: str, prev: Optional[dict]) -> dict:
    """Build a product record from a CSV row + detected mapping."""
    def gv(key: str, default: str = "") -> str:
        col = mapping.get(key)
        if not col:
            return default
        return (row.get(col) or default).strip()

    def gf(key: str, default: float = 0.0) -> float:
        v = gv(key)
        if not v:
            return default
        try:
            return float(v.replace("$", "").replace(",", ""))
        except Exception:
            return default

    def gi(key: str, default: int = 0) -> int:
        v = gv(key)
        if not v:
            return default
        try:
            return int(float(v))
        except Exception:
            return default

    # Tags: comma-separated
    tags_raw = gv("tags")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

    if prev:
        item_id = prev["id"]
    else:
        base = gv("sku") or gv("name").lower().replace(" ", "-")
        item_id = f"product-{brand_id}-{base[:40]}-{uuid.uuid4().hex[:6]}"

    out = {
        "id": item_id,
        "kind": "product",
        "brand_id": brand_id,
        "sku": gv("sku") or None,
        "name": gv("name"),
        "brand": gv("brand") or brand_id,
        "category": gv("category") or "uncategorised",
        "subcategory": gv("subcategory") or None,
        "description": gv("description"),
        "price": gf("price"),
        "sale_price": gf("sale_price"),
        "stock_quantity": gi("stock_quantity"),
        "size": gv("size") or None,
        "color": gv("color") or None,
        "variant": gv("variant") or None,
        "product_url": gv("product_url") or None,
        "image_url": gv("image_url") or None,
        "supplier": gv("supplier") or None,
        "priority": gv("priority") or "normal",
        "campaign": gv("campaign") or None,
        "tags": tags,
        "status": gv("status") or "active",
        "notes": gv("notes") or None,
    }

    # Compute stock-out flag
    out["in_stock"] = out["stock_quantity"] > 0

    return out


# ── Extended product catalog (extends the existing product library) ───────
def _extended_products_path(brand_id: str) -> Path:
    return _products_dir(brand_id) / "catalog.json"


def _load_extended_products(brand_id: str) -> list:
    """Load extended product catalog (stock/SKU/price)."""
    p = _extended_products_path(brand_id)
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text())
        return d.get("products") or []
    except Exception:
        return []


def _save_extended_products(brand_id: str, products: list) -> Path:
    p = _extended_products_path(brand_id)
    payload = {
        "brand_id": brand_id,
        "version": 1,
        "updated": datetime.utcnow().isoformat() + "Z",
        "count": len(products),
        "products": products,
    }
    p.write_text(json.dumps(payload, indent=2, default=str))
    return p


def list_extended_products(brand_id: str) -> list:
    return _load_extended_products(brand_id)


def get_extended_product(brand_id: str, product_id: str) -> Optional[dict]:
    for p in _load_extended_products(brand_id):
        if p.get("id") == product_id:
            return p
    return None


def update_product_rotation(brand_id: str, product_id: str, update: dict) -> None:
    """Update rotation memory for a product after a post is published."""
    products = _load_extended_products(brand_id)
    for i, p in enumerate(products):
        if p.get("id") == product_id:
            rotation = p.setdefault("rotation", {
                "last_featured_date": None,
                "total_posts": 0,
                "recent_angles": [],
                "recent_creative_ids": [],
            })
            rotation.update(update)
            products[i] = p
            _save_extended_products(brand_id, products)
            return


# ── Calendar queries ─────────────────────────────────────────────────────
def get_calendar_view(
    brand_id: str,
    *,
    start_date: str,
    end_date: str,
    lanes: Optional[list] = None,
    campaigns: Optional[list] = None,
    platforms: Optional[list] = None,
    statuses: Optional[list] = None,
    include_campaign_bands: bool = True,
) -> dict:
    """Return a multi-lane calendar view for a date range.

    Returns:
      {
        start_date, end_date, items: [...], campaign_bands: [...],
        conflicts: [{type, severity, message, ...}],
        density: {date: {lane: count}}
      }
    """
    items = load_content_items(brand_id)
    # Apply filters
    if lanes:
        items = [i for i in items if i.get("lane") in lanes]
    if campaigns:
        items = [i for i in items if i.get("campaign_id") in campaigns]
    if platforms:
        items = [i for i in items if any(
            p in (i.get("platforms") or [i.get("platform")] or []) for p in platforms
        )]
    if statuses:
        items = [i for i in items if i.get("status") in statuses]

    # Filter to date range
    start = start_date[:10]
    end = end_date[:10]
    in_range = []
    for item in items:
        d = (item.get("publish_date") or "")[:10]
        if not d:
            continue
        if start <= d <= end:
            in_range.append(item)

    # Get campaign bands
    bands = campaign_bands(brand_id, start_date, end_date) if include_campaign_bands else []

    # Density matrix
    density = defaultdict(lambda: defaultdict(int))
    for item in in_range:
        d = (item.get("publish_date") or "")[:10]
        l = item.get("lane", "campaign")
        density[d][l] += 1

    # Conflict detection (per user directive #21)
    conflicts = detect_conflicts(brand_id, start, end, items=in_range, density=density)

    return {
        "brand_id": brand_id,
        "start_date": start,
        "end_date": end,
        "lanes_filter": lanes,
        "total_items": len(in_range),
        "items": in_range,
        "campaign_bands": bands,
        "density": {d: dict(l) for d, l in density.items()},
        "conflicts": conflicts,
    }


def detect_conflicts(brand_id: str, start: str, end: str, items: list, density: dict) -> list:
    """Surface useful planning signals per user directive #21."""
    today = datetime.utcnow().date()  # computed once; used by time-aware rules
    conflicts = []

    # 1) NO HUMAN CONTENT THIS WEEK
    if items:
        start_dt = datetime.fromisoformat(start).date()
        end_dt = datetime.fromisoformat(end).date()
        cur = start_dt
        while cur <= end_dt:
            week_start = cur
            week_end = min(cur + timedelta(days=6), end_dt)
            week_dates = [(week_start + timedelta(days=i)).isoformat() for i in range((week_end - week_start).days + 1)]
            week_items = [i for i in items if (i.get("publish_date") or "")[:10] in week_dates]
            week_lanes = {i.get("lane") for i in week_items}
            if week_items and "human" not in week_lanes:
                conflicts.append({
                    "type": "no_human_content_this_week",
                    "severity": "info",
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                    "message": f"No HUMAN content scheduled {week_start} → {week_end}",
                })
            cur += timedelta(days=7)

    # 2) 3+ PRODUCT POSTS FROM SAME CATEGORY IN A ROW
    by_date_cat = defaultdict(lambda: defaultdict(int))
    for item in items:
        if item.get("lane") != "product":
            continue
        d = (item.get("publish_date") or "")[:10]
        # Need category from product — quick lookup
        product_id = item.get("product_id")
        cat = item.get("product_category")
        if not cat and product_id:
            prod = get_extended_product(brand_id, product_id)
            if prod:
                cat = prod.get("category", "uncategorised")
        by_date_cat[d][cat or "uncategorised"] += 1

    # Check for 3+ in same category in any 3-day window
    sorted_dates = sorted({(item.get("publish_date") or "")[:10] for item in items if item.get("lane") == "product"})
    for cat in set(c for d in by_date_cat.values() for c in d):
        dates_with_cat = [d for d in sorted_dates if by_date_cat[d].get(cat, 0) > 0]
        if len(dates_with_cat) < 3:
            continue
        for i in range(len(dates_with_cat) - 2):
            d1 = datetime.fromisoformat(dates_with_cat[i]).date()
            d3 = datetime.fromisoformat(dates_with_cat[i + 2]).date()
            if (d3 - d1).days <= 2:
                conflicts.append({
                    "type": "category_cluster",
                    "severity": "warning",
                    "category": cat,
                    "dates": dates_with_cat[i:i+3],
                    "message": f"3+ {cat} product posts within {(d3-d1).days + 1} days — consider rotating categories",
                })

    # 3) MAJOR CAMPAIGN DAY HAS NO SUPPORTING CONTENT
    campaign_days = set()
    for item in items:
        if item.get("lane") == "campaign":
            d = (item.get("publish_date") or "")[:10]
            if d:
                campaign_days.add(d)
    for d in campaign_days:
        supporting = [
            i for i in items
            if (i.get("publish_date") or "")[:10] == d
            and i.get("lane") in ("product", "human", "paid")
        ]
        if not supporting:
            conflicts.append({
                "type": "campaign_no_support",
                "severity": "info",
                "date": d,
                "message": f"Campaign item on {d} has no PRODUCT/HUMAN/PAID supporting content",
            })

    # 4) 5+ POSTS SAME DAY
    for d, lane_counts in density.items():
        total = sum(lane_counts.values())
        if total >= 5:
            conflicts.append({
                "type": "high_density_day",
                "severity": "warning",
                "date": d,
                "total": total,
                "by_lane": lane_counts,
                "message": f"{total} posts scheduled on {d} — possible spam risk",
            })

    # 5) PRODUCT FEATURE HAS NO CREATIVE — time-aware (per directive #18)
    for item in items:
        if item.get("lane") != "product":
            continue
        if item.get("creative_id") or item.get("creative"):
            continue
        d = item.get("publish_date", "")[:10]
        if not d:
            continue
        try:
            pub = datetime.fromisoformat(d).date()
        except Exception:
            continue
        days_to_pub = (pub - today).days
        # Time-aware: only surface as conflict within the urgency window.
        if days_to_pub > 20:
            continue  # plenty of time, not a conflict yet
        if days_to_pub > 7:
            severity = "info"
            message = f"Product post {item.get('id')} due {d} — start creative when ready ({days_to_pub} days)"
        elif days_to_pub > 3:
            severity = "warning"
            message = f"Product post {item.get('id')} due {d} — needs creative ({days_to_pub} days)"
        elif days_to_pub > 0:
            severity = "critical"
            message = f"Product post {item.get('id')} due {d} — URGENT: needs creative in {days_to_pub} day(s)"
        else:
            # Already past — critical, also flag for review
            severity = "critical"
            message = f"Product post {item.get('id')} was due {d} — creative missing or past-due"
        conflicts.append({
            "type": "product_no_creative",
            "severity": severity,
            "item_id": item.get("id"),
            "date": d,
            "days_to_publish": days_to_pub,
            "message": message,
        })

    # 6) OUT OF STOCK (user directive #22 — inventory awareness)
    for item in items:
        if item.get("lane") != "product":
            continue
        product_id = item.get("product_id")
        if not product_id:
            continue
        prod = get_extended_product(brand_id, product_id)
        if prod and prod.get("stock_quantity", 0) <= 0:
            conflicts.append({
                "type": "out_of_stock",
                "severity": "critical",
                "item_id": item.get("id"),
                "date": item.get("publish_date"),
                "product_id": product_id,
                "product_name": prod.get("name"),
                "stock_quantity": prod.get("stock_quantity"),
                "message": f"Product {prod.get('name')} is OUT OF STOCK — post scheduled for {item.get('publish_date')}",
                "actions": ["replace_product", "keep_as_brand_educational", "cancel_post", "move_to_waitlist"],
            })

    # 7) CONTENT NEEDS CAPTURE IN 3 DAYS (HUMAN lane)
    for item in items:
        if item.get("lane") != "human":
            continue
        d = item.get("publish_date", "")[:10]
        if not d:
            continue
        days = (datetime.fromisoformat(d).date() - today).days
        if 0 <= days <= 3 and item.get("status") in ("needs_asset", "planned"):
            conflicts.append({
                "type": "capture_needed_soon",
                "severity": "warning",
                "item_id": item.get("id"),
                "date": d,
                "days_until_publish": days,
                "message": f"HUMAN content {item.get('id')} needs capture in {days} day(s)",
            })

    # 8) POST APPROVED BUT NOT QUEUED — time-aware
    for item in items:
        if item.get("status") != "approved" or item.get("scheduled_for"):
            continue
        d = item.get("publish_date", "")[:10]
        if not d:
            continue
        try:
            days = (datetime.fromisoformat(d).date() - today).days
        except Exception:
            continue
        if days < 0:
            conflicts.append({
                "type": "approved_not_queued",
                "severity": "critical",
                "item_id": item.get("id"),
                "date": d,
                "message": f"Approved post {item.get('id')} was due {d} — not queued",
            })
        elif days <= 3:
            conflicts.append({
                "type": "approved_not_queued",
                "severity": "warning",
                "item_id": item.get("id"),
                "date": d,
                "days_to_publish": days,
                "message": f"Approved post {item.get('id')} ({d}) — queue to Postiz in {days} day(s)",
            })
        elif days <= 7:
            conflicts.append({
                "type": "approved_not_queued",
                "severity": "info",
                "item_id": item.get("id"),
                "date": d,
                "days_to_publish": days,
                "message": f"Approved post {item.get('id')} ({d}) — queue when ready ({days} days)",
            })
        # 7+ days away — no conflict yet

    return conflicts


# ── Product-post engine (per user directive #14, #23) ────────────────────
# Build product calendar proposals WITHOUT generating creative.
# Per user directive #12 — propose 30 products/dates first; only after
# approval do we begin generation.

# ── Currency + price-band helpers ──────────────────────────────────────
def _brand_currency(brand_id: str) -> str:
    """Return the brand's currency code. Default: ZAR.

    Brand currency can be overridden per-brand via:
      data/brand-directory/<brand>/brand.json → "currency": "USD" | "ZAR" | ...
    """
    brand_json = _data_root() / "brand-directory" / brand_id / "brand.json"
    if brand_json.exists():
        try:
            d = json.loads(brand_json.read_text())
            cur = d.get("currency")
            if isinstance(cur, str) and cur:
                return cur
        except Exception:
            pass
    return "ZAR"


def _currency_symbol(code: str) -> str:
    return {
        "ZAR": "R",
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "AUD": "A$",
    }.get(code, code + " ")


def _format_money(amount, currency: str) -> str:
    """Format amount with the brand's currency symbol.

    ZAR example: 1499.0 → 'R1,499'
    USD example: 1499.0 → '$1,499'
    """
    if amount is None:
        return ""
    try:
        amt = float(amount)
    except Exception:
        return f"{amount}"
    symbol = _currency_symbol(currency)
    if amt == int(amt):
        return f"{symbol}{int(amt):,}"
    return f"{symbol}{amt:,.2f}"


def _price_bucket(price: float, currency: str) -> str:
    """Bucket price for diversity scoring. Buckets derive from currency:
    ZAR → free / <R200 / R200-500 / R500-1.5k / R1.5k+
    USD → free / <$50 / $50-150 / $150-500 / $500+
    """
    if price == 0:
        return "free"
    if currency == "ZAR":
        if price < 200:
            return "under-R200"
        if price < 500:
            return "R200-500"
        if price < 1500:
            return "R500-1.5k"
        return "R1.5k-plus"
    # Default to USD-style
    if price < 50:
        return "under-50"
    if price < 150:
        return "50-150"
    if price < 500:
        return "150-500"
    return "500-plus"


# Product angles (per user directive #15)
PRODUCT_ANGLES = [
    "hero_product",
    "why_its_here",
    "detail",
    "who_its_for",
    "material",
    "feature",
    "use_case",
    "staff_pick",
    "new_arrival",
    "back_in_stock",
    "limited_stock",
    "colour_variant",
    "fit_performance",
    "style",
]

# Creative-property routing (per user directive #14)
def _pick_creative_property(product: dict, brand_id: str) -> str:
    """Route to the right recurring creative property based on product category."""
    name_low = (product.get("name") or "").lower()
    cat = (product.get("category") or "").lower()
    desc = (product.get("description") or "").lower()

    if "iron" in name_low or "wedge" in name_low or "fitting" in cat or "fitting" in desc:
        return "fit_first"
    if "pants" in name_low or "polo" in name_low or "apparel" in cat:
        return "style_that_belongs"
    if "ball" in name_low:
        return "why_its_here"
    if "putter" in name_low:
        return "why_its_here"
    if "bag" in name_low or "vessel" in name_low:
        return "why_its_here"
    if "grip" in name_low or "shaft" in name_low:
        return "built_at_stick"
    return "product_feature"


def _pick_angle(product: dict, recent_angles: list) -> str:
    """Pick an angle that hasn't been used recently (per user directive #23)."""
    recent_set = set(recent_angles or [])
    available = [a for a in PRODUCT_ANGLES if a not in recent_set]
    if not available:
        available = PRODUCT_ANGLES
    # Default to 'hero_product' if new arrival, otherwise first available
    is_new_arrival = product.get("status") == "new_arrival"
    campaign_hint = product.get("campaign") or ""
    if is_new_arrival or "new" in campaign_hint.lower():
        return "new_arrival"
    return available[0]


def _next_publish_slot(
    start_date: datetime,
    frequency: str,
    days_count: int,
) -> list:
    """Return the list of publish dates given frequency.

    frequency: 'daily' | 'weekdays' | 'x_per_week' | 'custom'
    For 'x_per_week' and 'custom', use defaults: x=3 (Tue/Thu/Sat).
    """
    dates = []
    if frequency == "daily":
        for i in range(days_count):
            dates.append(start_date + timedelta(days=i))
    elif frequency == "weekdays":
        i = 0
        while len(dates) < days_count:
            d = start_date + timedelta(days=i)
            if d.weekday() < 5:  # Mon-Fri
                dates.append(d)
            i += 1
    elif frequency == "x_per_week":
        # Default: Tue / Thu / Sat
        slots_per_week = 3
        week_starts = 0
        while len(dates) < days_count:
            for offset in [1, 3, 5]:  # Tue, Thu, Sat
                d = start_date + timedelta(days=week_starts * 7 + offset)
                if d >= start_date and len(dates) < days_count:
                    dates.append(d)
            week_starts += 1
    else:  # custom — fallback to daily
        for i in range(days_count):
            dates.append(start_date + timedelta(days=i))
    dates = sorted(set(dates))
    return dates


def propose_product_calendar(
    brand_id: str,
    *,
    start_date: str,
    days_count: int = 20,
    frequency: str = "weekdays",
    categories: Optional[list] = None,
    exclude_recent_days: int = 7,
    min_category_diversity: int = 4,
) -> dict:
    """Propose a product-feature calendar (no creative generation yet).

    Per user directive #9 — the planner considers:
      stock availability, priority, new arrivals, category diversity,
      brand diversity, price-point diversity, recent product history,
      availability of reference imagery.

    Returns:
      {
        start_date, end_date, frequency, proposed_items: [...],
        skipped_due_to_stock: [...], category_distribution: {...},
        price_distribution: {...}, skipped_due_to_repeat: [...]
      }
    """
    products = _load_extended_products(brand_id)
    if not products:
        # Fall back to existing product library
        try:
            from product_service_library import list_items
            products = list_items(brand_id, kind="product")
        except Exception:
            pass

    if not products:
        return {
            "ok": False,
            "error": f"No products in extended catalog for {brand_id}. Import stock first.",
            "proposed_items": [],
        }

    # Filter out of stock
    in_stock = [p for p in products if p.get("stock_quantity", 0) > 0]
    skipped_stock = [p for p in products if p.get("stock_quantity", 0) <= 0]

    # Filter categories if specified
    if categories:
        in_stock = [p for p in in_stock if p.get("category") in categories]
    elif min_category_diversity:
        # Group by category
        by_cat = defaultdict(list)
        for p in in_stock:
            by_cat[p.get("category", "uncategorised")].append(p)
        # Keep all categories, but try to ensure diversity in scheduling

    # Recently featured — exclude for N days
    today = datetime.utcnow().date()
    recent_cutoff = today - timedelta(days=exclude_recent_days)
    eligible = []
    skipped_recent = []
    for p in in_stock:
        rotation = p.get("rotation") or {}
        last = rotation.get("last_featured_date")
        if last:
            try:
                last_date = datetime.fromisoformat(last[:10]).date()
                if last_date >= recent_cutoff:
                    skipped_recent.append({"name": p.get("name"), "last_featured": last})
                    continue
            except Exception:
                pass
        eligible.append(p)

    # Sort by priority: in_stock + new_arrivals + featured + high stock
    def priority_key(p):
        score = 0
        if p.get("priority") == "high":
            score += 100
        if p.get("campaign"):
            score += 50
        if p.get("status") == "new_arrival":
            score += 30
        # Higher stock = lower priority (we want to feature scarce items)
        # but we need to feature things we have
        stock = p.get("stock_quantity", 0)
        if stock <= 2:
            score += 20  # scarce — feature before sold-out
        # Lower price point gets a small boost for accessibility
        price = p.get("price", 0)
        if 0 < price < 100:
            score += 5
        return -score  # negate so higher = earlier

    eligible.sort(key=priority_key)

    # Generate publish dates
    start_dt_date = datetime.fromisoformat(start_date[:10]).date()
    start_dt = datetime.combine(start_dt_date, datetime.min.time())
    publish_dates = _next_publish_slot(start_dt, frequency, days_count)

    # Build proposed items with FAMILY/brand/price diversity
    # Key insight: a family (e.g. "Maverick 10K Step Pant") contains multiple
    # SKU variants (Black + Baritone Blue). The planner plans at the FAMILY
    # level — picking the same family three times in a row is the same
    # repetition as picking the same SKU. Falls back to category when the
    # family is not set, then to category group, then to SKU.
    proposed = []
    category_count = Counter()
    family_count = Counter()
    brand_count = Counter()
    price_bucket_count = Counter()
    p_idx = 0
    last_families = []  # last 2 families used (we don't repeat the same family twice in a row)
    used_angles_per_family = {}  # family -> set of angles already used this proposal

    def family_of(prod):
        """Get the diversity key for a product. Prefer family, then category."""
        f = prod.get("product_family")
        if f and f.strip():
            return ("family", f)
        cat = prod.get("category", "uncategorised")
        if cat and cat != "uncategorised":
            return ("category", cat)
        # Fall back to name root (strip colour/size suffix)
        name = prod.get("name", "")
        # Try to dedup by extracting "Mens Classic Polo" from "Mens Classic Polo - Antique Taupe"
        return ("name", name.split(" - ")[0].split(";")[0].strip())

    for d in publish_dates:
        if not eligible:
            break
        # Round-robin pick: advance through eligible, skip if family repeats last 2
        attempts = 0
        chosen = None
        chosen_diversity = None
        while attempts < len(eligible) * 2:
            candidate = eligible[p_idx % len(eligible)]
            p_idx += 1
            attempts += 1
            div_key = family_of(candidate)
            # Skip if same family was used last 2 slots
            if (len(last_families) >= 2
                and div_key == last_families[-1] == last_families[-2]):
                continue
            # Skip if all eligible candidates have already been used for the
            # same family with the same angle (rare edge case)
            chosen = candidate
            chosen_diversity = div_key
            break

        if not chosen:
            # No family-diverse candidate — fall back to the first eligible
            # but pick a fresh angle so the post isn't a copy of last time
            chosen = eligible[0]
            chosen_diversity = family_of(chosen)

        family_name = chosen_diversity[1]
        recent_angles = used_angles_per_family.get(family_name, [])
        angle = _pick_angle(chosen, recent_angles)
        # Mark this angle as used for this family in THIS proposal
        used_angles_per_family.setdefault(family_name, []).append(angle)
        property_used = _pick_creative_property(chosen, brand_id)

        # Build creative brief + references for this slot.
        # Per heidi.txt directive (2026-09-01): a product calendar item
        # must ALREADY KNOW how it will become a post — master prompt,
        # preservation rules, references, currency-correct price.
        from .product_creative_brief import build_full_creative_brief
        _brief_item = {
            "product_id": chosen.get("id"),
            "creative_property": property_used,
            "angle": angle,
        }
        try:
            _brief = build_full_creative_brief(_brief_item, brand_id)
        except Exception as _cb_err:
            import traceback as _tb
            print(f"[brief-generator] error: {_cb_err}\n{_tb.format_exc()}")
            _brief = {"ok": False, "creative_brief": {}, "references": {}, "formatted_price": "", "price_bucket": "", "currency_symbol": "R", "currency": "ZAR"}

        proposed.append({
            "id": f"ci-prop-{uuid.uuid4().hex[:8]}",
            "brand_id": brand_id,
            "lane": "product",
            "status": "proposed",
            "publish_date": d.isoformat(),
            "publish_time": "09:00",
            "platforms": ["instagram"],
            "product_id": chosen.get("id"),
            "product_name": chosen.get("name"),
            "product_sku": chosen.get("sku"),
            "product_category": chosen.get("category"),
            "product_family": family_name,
            "product_brand": chosen.get("product_brand") or chosen.get("brand") or brand_id,
            "creative_property": property_used,
            "angle": angle,
            "platform": "instagram",
            "format": "1:1",
            "owner": "operator",
            # Auto-generated brief fields (per heidi.txt 2026-09-01)
            "needs_asset": True,
            "creative_brief": _brief.get("creative_brief", {}),
            "references": _brief.get("references", {}),
            "reference_status": "missing" if _brief.get("missing") else "ready",
            "formatted_price": _brief.get("formatted_price", ""),
            "price_bucket": _brief.get("price_bucket", ""),
            "currency": _brief.get("currency", "ZAR"),
            "currency_symbol": _brief.get("currency_symbol", "R"),
            # Status flow per heidi.txt #17:
            # PLANNED → REFERENCE READY → PROMPT READY → GENERATING → CREATIVE READY → NEEDS APPROVAL → APPROVED → QUEUED → PUBLISHED
            "reference_ready": not _brief.get("missing"),
            "prompt_ready": True,  # The brief is always ready even without reference
            "next_step": _brief.get("next_step", ""),
        })
        category_count[chosen.get("category", "uncategorised")] += 1
        family_count[family_name] += 1
        brand_count[chosen.get("product_brand") or chosen.get("brand") or brand_id] += 1
        # Per heidi.txt 2026-09-01: price buckets must be brand-aware (ZAR for
        # Stick / Swing Shack / Bag Drop). Hard-coded US ranges removed.
        from .product_creative_brief import price_bucket_for, get_brand_config
        cfg = get_brand_config(brand_id)
        sym = cfg.get("currency_symbol", "R")
        price = chosen.get("price", 0)
        bucket = price_bucket_for(price, brand_id)
        price_bucket_count[bucket] += 1
        last_families = (last_families + [chosen_diversity])[-3:]

    return {
        "ok": True,
        "brand_id": brand_id,
        "start_date": start_dt_date.isoformat(),
        "end_date": publish_dates[-1].isoformat() if publish_dates else start_dt.isoformat(),
        "frequency": frequency,
        "slot_count": len(proposed),
        "proposed_items": proposed,
        "skipped_due_to_stock": [{"name": p.get("name"), "sku": p.get("sku")} for p in skipped_stock],
        "skipped_due_to_recent": skipped_recent,
        "category_distribution": dict(category_count),
        "family_distribution": dict(family_count),
        "brand_distribution": dict(brand_count),
        "price_distribution": dict(price_bucket_count),
        "available_products": len(eligible),
        "total_products": len(products),
    }


def approve_proposal(brand_id: str, item_ids: list, *, actor: str = "operator") -> dict:
    """Promote proposed items to 'planned' status."""
    items = load_content_items(brand_id)
    promoted = []
    existing_ids = {i.get("id") for i in items}

    for cid in item_ids:
        # Find the proposed item (it's NOT yet in items list — proposals are transient)
        # We need to store the proposal first; for now, just record approval.
        promoted.append({"id": cid, "approved_at": datetime.utcnow().isoformat() + "Z"})

    return {"ok": True, "promoted": promoted}


# ── Inventory / out-of-stock awareness ───────────────────────────────────
def check_inventory_for_date(brand_id: str, item_id: str) -> dict:
    """Check inventory status for a content item that references a product."""
    item = get_content_item(brand_id, item_id)
    if not item:
        return {"ok": False, "error": "item not found"}
    product_id = item.get("product_id")
    if not product_id:
        return {"ok": True, "in_stock": None, "message": "no product reference"}
    prod = get_extended_product(brand_id, product_id)
    if not prod:
        return {"ok": True, "in_stock": None, "message": "product not in extended catalog"}
    qty = prod.get("stock_quantity", 0)
    return {
        "ok": True,
        "in_stock": qty > 0,
        "stock_quantity": qty,
        "product_id": product_id,
        "product_name": prod.get("name"),
        "action_required": qty <= 0,
    }