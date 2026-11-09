"""A brand's stock list read from its public Shopify product list.

Swing Shack and Stick upload a weekly stock CSV (stock_pulse.parse_stock_csv). The Bag
Drop sells online through Shopify, so its stock is read from
https://thebagdrop.co.za/products.json instead and saved as the same snapshot rows
({sku, name, variant, qty, alert}), so stock_pulse works unchanged.

The public list carries no counts, only whether a variant can be bought. Most Bag Drop
pieces are one-offs, so a variant for sale counts 1 and a sold one 0. Read that way,
"new" is a fresh listing and "still"/"stuck" is a piece listed for weeks without selling.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

# Brands that sell through a Shopify store, and its domain.
STORES: Dict[str, str] = {"bag-drop": "thebagdrop.co.za"}

PAGE_SIZE = 250
MAX_PAGES = 20
RETRY_WAIT_S = 30
USER_AGENT = "CampaignOS/1.0 (stock list)"


def _get(url: str) -> Tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (fixed https store URL)
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def fetch_products(domain: str, *, get: Callable[[str], Tuple[int, bytes]] = _get,
                   sleep: Callable[[float], Any] = time.sleep) -> List[Dict[str, Any]]:
    """Every product on the store, page by page. Waits once when Shopify says too many requests."""
    out: List[Dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"https://{domain}/products.json?limit={PAGE_SIZE}&page={page}"
        status, body = get(url)
        if status == 429:
            sleep(RETRY_WAIT_S)
            status, body = get(url)
        if status != 200:
            raise RuntimeError(f"{domain} products.json page {page} returned HTTP {status}")
        products = json.loads(body.decode("utf-8") or "{}").get("products") or []
        if not products:
            break
        out.extend(products)
    return out


def to_rows(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Shopify products -> stock_pulse snapshot rows, one per variant."""
    rows: List[Dict[str, Any]] = []
    for p in products:
        name = (p.get("title") or "").strip()
        if not name:
            continue
        for v in p.get("variants") or []:
            variant = (v.get("title") or "").strip()
            if variant.lower() == "default title":
                variant = ""
            rows.append({
                "sku": (v.get("sku") or "").strip() or f"shopify-{v.get('id')}",
                "name": name,
                "variant": variant,
                "qty": 1 if v.get("available") else 0,
                "alert": None,
            })
    return rows


def store_for(brand_id: Optional[str]) -> Optional[str]:
    return STORES.get(brand_id or "")
