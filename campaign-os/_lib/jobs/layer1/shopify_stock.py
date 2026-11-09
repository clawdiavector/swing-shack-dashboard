"""Daily: save today's stock list for a brand that sells through Shopify (The Bag Drop).

Reads the store's public product list and saves a dated stock_pulse snapshot (a
same-day run replaces the earlier one), so story ideas, the daily target and feed
suggestions work from Bag Drop's real stock the way they do from the weekly CSVs.
"""
from __future__ import annotations

from typing import Any

from ._io import io_for_job, utc_now_iso

JOB_NAME = "shopify_stock"
OUTPUT = "shopify-stock.json"


def run(*, brand: str | None = None) -> dict[str, Any]:
    from ... import shopify_stock, stock_pulse  # noqa: PLC0415

    domain = shopify_stock.store_for(brand)
    if not domain:
        return {"ok": False, "error": f"{brand} has no Shopify store, so there is no stock list to read"}
    try:
        products = shopify_stock.fetch_products(domain)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"could not read {domain}: {e}"[:300]}
    rows = shopify_stock.to_rows(products)
    if not rows:
        return {"ok": False, "error": f"{domain} listed no products, so nothing was saved"}
    day = stock_pulse.save_snapshot(brand, rows)
    summary = {
        "brand": brand, "store": domain, "date": day, "fetched_at": utc_now_iso(),
        "products": len(products), "rows": len(rows), "for_sale": sum(r["qty"] for r in rows),
        "snapshots": len(stock_pulse.load_snapshots(brand)),
    }
    try:
        io = io_for_job(JOB_NAME, brand)
        io.write(OUTPUT, summary)
    except Exception:  # noqa: BLE001 — the snapshot is what matters; the summary is a receipt
        pass
    return {"ok": True, **summary}
