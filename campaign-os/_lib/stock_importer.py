"""
stock_importer.py — Smart importer that adapts to Christelle's actual stock format.

Per user directive PHASE L-6:
  - Recognise the canonical stock format:
      Location | Product Name | Variant Choices | SKU | Movement Type | Quantity | Alert Level
  - Distinguish STORE brand (Campaign OS brand context) from PRODUCT brand
    (e.g. Stick selling Psycho Bunny)
  - Parse Variant Choices intelligently:
      "Black;O/S"        → colour: Black,   size: O/S
      "Evening Blue;8"   → colour: Evening Blue, size: 8
      "7/8;White"        → size: 7/8,       colour: White
      "Black 2;XXL"      → colour: Black 2,  size: XXL
      "38"               → size: 38 (no colour)
  - Always preserve variant_raw (the original value)
  - Don't require fields that aren't in the source
  - Show example transformed rows before commit
  - Build product_family index so the planner can plan at family level,
    not SKU level (e.g. all Maverick 10K Step Pants = one family)
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Known size tokens (case-insensitive)
SIZE_TOKENS = {
    "xs", "s", "m", "l", "xl", "xxl", "xxxl",
    "o/s", "os", "onesize",
}
# Numeric apparel sizes (single number or range like 7/8 or 30-32)
APPAREL_SIZE_RE = re.compile(r"^(\d{1,2}(?:[/\-]\d{1,2})?)$")


# ── Format recognition ──────────────────────────────────────────────────
CANONICAL_FORMAT_MARKERS = [
    ("Product Name",    "Product Name"),     # → product_name / name
    ("Variant Choices", "Variant Choices"),  # → variant source
    ("SKU",             "SKU"),              # → sku
    ("Quantity",        "Quantity"),         # → stock_quantity
    ("Alert Level",     "Alert Level"),      # → source_alert_level (do not invent meaning)
    ("Location",        "Location"),         # → location
    ("Movement Type",   "Movement Type"),    # → movement_type / source metadata
]


def _normalize_header(s: str) -> str:
    return s.strip().lower().replace(" ", "").replace("_", "")


def _recognise_format(header_row: List[str]) -> Dict[str, Any]:
    """Check whether the input matches the canonical stock format.

    Returns:
      {matched: bool, matched_columns: {logical_field: csv_header}, missing: [logical, ...]}
    """
    normalised = {_normalize_header(h): h for h in header_row}
    matched: Dict[str, str] = {}
    missing: List[str] = []
    for logical, marker in CANONICAL_FORMAT_MARKERS:
        norm_marker = _normalize_header(marker)
        if norm_marker in normalised:
            matched[logical] = normalised[norm_marker]
        else:
            missing.append(logical)
    return {
        "matched": len(matched) >= 4,  # need at least Product Name + SKU + Quantity + Variant
        "matched_columns": matched,
        "missing": missing,
    }


def _parse_variant_choices(raw: str) -> Dict[str, Optional[str]]:
    """Parse "Variant Choices" into {colour, size, variant_raw}.

    Examples:
      "Black;O/S"        → colour: Black,    size: O/S
      "Evening Blue;8"   → colour: Evening Blue, size: 8
      "7/8;White"        → size: 7/8,        colour: White
      "Black 2;XXL"      → colour: Black 2,   size: XXL
      "38"               → size: 38
      ""                 → {}
    """
    out: Dict[str, Optional[str]] = {"variant_raw": (raw or "").strip()}
    if not raw:
        return out
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    if len(parts) == 0:
        return out
    if len(parts) == 1:
        p = parts[0]
        norm = p.lower()
        # Size-only?
        if norm in SIZE_TOKENS or APPAREL_SIZE_RE.match(p):
            out["size"] = p
            out["colour"] = None
        else:
            # Colour-only
            out["colour"] = p
            out["size"] = None
        return out
    # 2+ parts — heuristic: first is colour, second is size (most common).
    # BUT check if any part looks like a size token.
    colour_part = None
    size_part = None
    for p in parts:
        norm = p.lower()
        if norm in SIZE_TOKENS or APPAREL_SIZE_RE.match(p):
            if size_part is None:
                size_part = p
        else:
            if colour_part is None:
                colour_part = p
    # If neither explicit, default to first=colour, second=size
    if colour_part is None and size_part is None:
        colour_part = parts[0]
        if len(parts) > 1:
            size_part = parts[1]
    if colour_part is not None:
        out["colour"] = colour_part
    if size_part is not None:
        out["size"] = size_part
    # Also note parse confidence
    out["parse_confidence"] = "high" if (colour_part or size_part) else "low"
    return out


def _extract_product_family(name: str) -> str:
    """Strip trailing colour/size descriptors to find the family root.

    'Maverick 10K Step Pant - Black'        → 'Maverick 10K Step Pant'
    'Maverick 10K Step Pant - Baritone Blue' → 'Maverick 10K Step Pant'
    'Mens Classic Crew Neck Tee'             → 'Mens Classic Crew Neck Tee'
    """
    if not name:
        return ""
    # Strip " - <something>" suffix (the colour/variant tail)
    # Only strip if the part after dash is short (<25 chars) and looks like colour/size
    m = re.match(r"^(.*?)\s+[-—]\s+(.{1,25})$", name)
    if m:
        suffix = m.group(2).strip()
        suffix_low = suffix.lower()
        if (
            suffix_low in SIZE_TOKENS
            or APPAREL_SIZE_RE.match(suffix)
            or any(c in suffix for c in [";", "Blue", "Black", "White", "Red", "Green", "Taupe", "Grey", "Gray", "Antique"])
        ):
            return m.group(1).strip()
    return name.strip()


# ── Importer ────────────────────────────────────────────────────────────
def preview_smart_import(
    csv_content: str,
    *,
    store_brand: str = "stick",
    default_product_brand: Optional[str] = None,
) -> dict:
    """Preview a stock CSV import with smart format recognition.

    Returns:
      {
        format_recognised: bool,
        format_name: str,    # "Canonical stock format" or "Generic CSV"
        matched_columns: {logical: csv_header},
        missing_required: [logical],
        sample_rows: [{raw, mapped}],  # first 3 transformed
        warnings: [str],
        expected_creates: int,
        expected_updates: int,
        product_families: {family_name: [sku1, sku2, ...]},
        total_rows: int,
        rows_with_data: int,
        header_row: [str],
      }
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    header = reader.fieldnames or []
    rows = list(reader)

    fmt = _recognise_format(header)
    matched = fmt["matched_columns"]

    # Fall back to generic header-to-field heuristic if format not recognised
    if not fmt["matched"]:
        # Use the existing synonym matcher from marketing_lanes
        try:
            from _lib.marketing_lanes import _detect_column_mapping
            generic = _detect_column_mapping(header)
            for k, v in generic.items():
                if k not in matched:
                    matched[k] = v
            fmt["matched_columns"] = matched
        except Exception:
            pass

    sample_rows = []
    families: Dict[str, List[str]] = defaultdict(list)
    warnings: List[str] = []
    rows_with_data = 0

    for idx, row in enumerate(rows):
        # Skip blank rows
        product_name = (row.get(matched.get("Product Name", ""), "") or "").strip()
        if not product_name:
            continue
        rows_with_data += 1
        sku = (row.get(matched.get("SKU", ""), "") or "").strip()
        variant_raw = (row.get(matched.get("Variant Choices", ""), "") or "").strip()
        quantity = (row.get(matched.get("Quantity", ""), "") or "").strip()
        alert_level = (row.get(matched.get("Alert Level", ""), "") or "").strip()
        location = (row.get(matched.get("Location", ""), "") or "").strip()
        movement_type = (row.get(matched.get("Movement Type", ""), "") or "").strip()
        source_brand = (row.get(matched.get("Brand", ""), "") or "").strip() or None

        variant_parsed = _parse_variant_choices(variant_raw)
        family = _extract_product_family(product_name)
        if sku:
            families[family].append(sku)
        try:
            qty_int = int(float(quantity)) if quantity else 0
        except Exception:
            qty_int = 0
            warnings.append(f"Row {idx + 1}: quantity '{quantity}' not numeric — stored as 0")

        if idx < 3:
            sample_rows.append({
                "raw": {
                    "Product Name": product_name,
                    "Variant Choices": variant_raw,
                    "SKU": sku,
                    "Quantity": quantity,
                    "Alert Level": alert_level,
                    "Location": location,
                    "Movement Type": movement_type,
                },
                "mapped": {
                    "name": product_name,
                    "product_family": family,
                    "product_brand": source_brand or default_product_brand or "unknown",
                    "sku": sku or None,
                    "variant_raw": variant_raw,
                    "colour": variant_parsed.get("colour"),
                    "size": variant_parsed.get("size"),
                    "stock_quantity": qty_int,
                    "in_stock": qty_int > 0,
                    "source_alert_level": alert_level or None,
                    "location": location or None,
                    "movement_type": movement_type or None,
                },
            })

    if fmt["matched"]:
        format_name = "Canonical stock format (Product Name / Variant Choices / SKU / Quantity / Alert Level)"
    else:
        format_name = "Generic CSV — columns mapped by header synonyms"
    if not matched.get("SKU"):
        warnings.append("No SKU column detected — products will be matched by name (less reliable).")
    if not matched.get("Product Name"):
        warnings.append("No Product Name column detected — import cannot proceed without it.")
    # Check optional fields presence
    optional_present = []
    optional_absent = []
    for optional in ["Price", "Sale Price", "Product URL", "Image URL", "Description", "Supplier", "Campaign", "Tags", "Notes"]:
        if any(_normalize_header(optional) in _normalize_header(h or "") for h in header):
            optional_present.append(optional)
        else:
            optional_absent.append(optional)

    if optional_absent:
        warnings.append(f"Optional data NOT in source: {', '.join(optional_absent)}. These can be enriched later.")

    return {
        "format_recognised": fmt["matched"],
        "format_name": format_name,
        "matched_columns": matched,
        "missing_required": fmt["missing"],
        "sample_rows": sample_rows,
        "warnings": warnings,
        "expected_creates": rows_with_data,  # all rows are new unless SKU exists
        "expected_updates": 0,
        "product_families": dict(families),
        "total_rows": len(rows),
        "rows_with_data": rows_with_data,
        "header_row": header,
        "optional_present": optional_present,
        "optional_absent": optional_absent,
    }


def commit_smart_import(
    csv_content: str,
    *,
    store_brand: str,
    default_product_brand: Optional[str] = None,
    actor: str = "operator",
    mark_as_demo: bool = False,
) -> dict:
    """Commit the smart import.

    Per user directive PHASE L-7: distinct STORE brand (Campaign OS context)
    from PRODUCT brand (the actual maker). For the example, store_brand=stick
    and default_product_brand="Psycho Bunny".

    Per user directive PHASE L-7 also: mark_as_demo=True labels the rows
    so they can be cleared without touching real data.
    """
    from _lib.marketing_lanes import (
        _load_extended_products, _save_extended_products,
        _extended_products_path,
    )

    reader = csv.DictReader(io.StringIO(csv_content))
    header = reader.fieldnames or []
    rows = list(reader)
    fmt = _recognise_format(header)
    matched = fmt["matched_columns"]

    # Fallback mapping
    if not fmt["matched"]:
        try:
            from _lib.marketing_lanes import _detect_column_mapping
            generic = _detect_column_mapping(header)
            for k, v in generic.items():
                if k not in matched:
                    matched[k] = v
        except Exception:
            pass

    if not matched.get("Product Name"):
        return {"ok": False, "error": "no Product Name column — cannot proceed"}

    products = _load_extended_products(store_brand)
    by_sku = {p.get("sku"): p for p in products if p.get("sku")}

    created = []
    updated = []
    skipped = []
    errors = []
    families: Dict[str, List[str]] = defaultdict(list)

    for idx, row in enumerate(rows):
        try:
            product_name = (row.get(matched.get("Product Name", ""), "") or "").strip()
            if not product_name:
                continue
            sku = (row.get(matched.get("SKU", ""), "") or "").strip()
            variant_raw = (row.get(matched.get("Variant Choices", ""), "") or "").strip()
            quantity = (row.get(matched.get("Quantity", ""), "") or "").strip()
            alert_level = (row.get(matched.get("Alert Level", ""), "") or "").strip()
            location = (row.get(matched.get("Location", ""), "") or "").strip()
            movement_type = (row.get(matched.get("Movement Type", ""), "") or "").strip()
            source_brand = (row.get(matched.get("Brand", ""), "") or "").strip()

            variant_parsed = _parse_variant_choices(variant_raw)
            family = _extract_product_family(product_name)
            try:
                qty_int = int(float(quantity)) if quantity else 0
            except Exception:
                qty_int = 0

            product_brand = source_brand or default_product_brand or "unknown"

            if sku and sku in by_sku:
                prev = by_sku[sku]
                item_id = prev["id"]
                action = "updated"
            else:
                base = sku or product_name.lower().replace(" ", "-")[:40]
                item_id = f"product-{store_brand}-{base}-{uuid.uuid4().hex[:6]}"
                action = "created"

            product_record = {
                "id": item_id,
                "kind": "product",
                "brand_id": store_brand,
                "store_brand": store_brand,           # ← store vs product brand distinction
                "product_brand": product_brand,       # ← the actual maker
                "sku": sku or None,
                "name": product_name,
                "product_family": family,             # ← family-level planner input
                "category": "uncategorised",           # not in this source
                "variant_raw": variant_raw,
                "colour": variant_parsed.get("colour"),
                "size": variant_parsed.get("size"),
                "source_alert_level": alert_level or None,  # preserved untouched
                "location": location or None,
                "movement_type": movement_type or None,
                "stock_quantity": qty_int,
                "in_stock": qty_int > 0,
                "is_demo_data": mark_as_demo,          # ← can be cleared without touching real data
                "source_format": "canonical_stock_v1" if fmt["matched"] else "generic_csv",
                "updated": datetime.utcnow().isoformat() + "Z",
                "updated_by": actor,
            }
            if action == "updated":
                for i, p in enumerate(products):
                    if p.get("id") == item_id:
                        # Preserve rotation + creation metadata
                        product_record["rotation"] = p.get("rotation")
                        product_record["created"] = p.get("created")
                        products[i] = {**p, **product_record}
                        break
                updated.append({"sku": sku, "name": product_name, "id": item_id})
            else:
                product_record["created"] = product_record["updated"]
                products.append(product_record)
                created.append({"sku": sku, "name": product_name, "id": item_id})

            families[family].append(sku or item_id)
        except Exception as e:
            errors.append({"row": idx + 1, "error": str(e)})

    _save_extended_products(store_brand, products)

    return {
        "ok": True,
        "created": len(created),
        "updated": len(updated),
        "skipped": len(skipped),
        "errors": len(errors),
        "created_items": created,
        "updated_items": updated,
        "product_families": dict(families),
        "store_brand": store_brand,
        "default_product_brand": default_product_brand,
        "is_demo": mark_as_demo,
    }


def list_demo_data(brand_id: str) -> dict:
    """Find demo products and content items that can be safely cleared."""
    from _lib.marketing_lanes import (
        load_content_items, _load_extended_products,
        list_campaigns,
    )
    products = _load_extended_products(brand_id)
    demo_products = [p for p in products if p.get("is_demo_data")]
    content_items = load_content_items(brand_id)
    # Heuristic: demo content items are those referencing demo products,
    # or those created by actor 'demo' or 'christelle' (test runs)
    demo_product_ids = {p["id"] for p in demo_products}
    demo_items = [
        it for it in content_items
        if (it.get("is_demo_data")
            or it.get("product_id") in demo_product_ids
            or it.get("created_by") == "demo")
    ]
    campaigns = list_campaigns(brand_id)
    # Don't auto-list campaigns as demo — they're strategic
    return {
        "demo_products": demo_products,
        "demo_product_count": len(demo_products),
        "demo_content_items": demo_items,
        "demo_content_count": len(demo_items),
        "all_content_items": len(content_items),
        "all_products": len(products),
    }


def clear_demo_data(brand_id: str, *, confirm: bool = False) -> dict:
    """Remove demo products + demo content items. Refuses without confirm=True."""
    if not confirm:
        return {"ok": False, "error": "pass confirm=true to clear"}

    from _lib.marketing_lanes import (
        load_content_items, save_content_items,
        _load_extended_products, _save_extended_products,
    )
    products = _load_extended_products(brand_id)
    demo_product_ids = {p["id"] for p in products if p.get("is_demo_data")}
    kept_products = [p for p in products if not p.get("is_demo_data")]
    _save_extended_products(brand_id, kept_products)

    items = load_content_items(brand_id)
    kept_items = [
        it for it in items
        if not (it.get("is_demo_data")
                or it.get("product_id") in demo_product_ids
                or it.get("created_by") == "demo")
    ]
    save_content_items(brand_id, kept_items)

    return {
        "ok": True,
        "removed_products": len(products) - len(kept_products),
        "removed_content_items": len(items) - len(kept_items),
        "remaining_products": len(kept_products),
        "remaining_content_items": len(kept_items),
    }
