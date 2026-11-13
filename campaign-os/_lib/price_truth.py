"""The real prices for each brand, and a check that every rand price in a caption is one of them.

Christelle's rule: no number without a source, and an unverified price is never used.

Live prices are public and read without a login:
  - each venue's ClubLab booking list (services and coaching packages)
  - each shop's Shopify products.json (price and compare-at price)
Prices that are approved but not live yet (a deal, next year's memberships) go in
data/brand-directory/<brand>/prices-approved.json, each with what it is, its source and
an end date.

Live prices are kept for six hours in a small cache file so a batch of captions makes
one set of requests. When a source can't be reached, check_text() still runs but the
caller is told, so an unknown price becomes "check it" instead of "wrong".
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
BRAND_DIR = REPO / "data" / "brand-directory"

CLUBLAB_BASE = "https://clublab.app/api/v1/bookme/public"
SOURCES: Dict[str, Dict[str, Any]] = {
    "swing-shack": {"clublab": 6},
    "stick": {"clublab": 7, "shopify": "shop.stickgolf.co.za"},
    "bag-drop": {"shopify": "thebagdrop.co.za"},
}
MAX_AGE_S = 6 * 3600
SHOPIFY_PAGE_SIZE = 250
SHOPIFY_MAX_PAGES = 20
USER_AGENT = "CampaignOS/1.0 (price check)"

Getter = Callable[[str], Tuple[int, bytes]]

# "R2,000", "R 820", "R12,999.00", "R1 500". Spaces are allowed as thousands separators only
# when exactly three digits follow, so "R540 for" does not swallow the next word.
_PRICE_RE = re.compile(r"\bR\s?\d{1,3}(?:[ ,.]\d{3})*(?:\.\d{2})?(?!\d)|\bR\s?\d+(?:\.\d{2})?(?!\d)")


def _get(url: str) -> Tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (fixed public https URLs)
        return r.status, r.read()


def _rand_value(token: str) -> Optional[int]:
    digits = token[1:].strip()
    cents = re.search(r"\.(\d{2})$", digits)
    if cents:
        digits = digits[: cents.start()]
    digits = re.sub(r"[ ,.]", "", digits)
    return int(digits) if digits.isdigit() else None


def find_prices(text: str) -> List[Tuple[str, int]]:
    """Every rand price in the text, as (what was written, whole rand)."""
    out: List[Tuple[str, int]] = []
    for m in _PRICE_RE.finditer(text or ""):
        tok = m.group(0).rstrip(" ,.")
        value = _rand_value(tok)
        if value is not None:
            out.append((tok, value))
    return out


def _cache_dir(cache_dir: Optional[Path]) -> Path:
    if cache_dir:
        return Path(cache_dir)
    env = os.environ.get("PRICE_CACHE_DIR")
    if env:
        return Path(env)
    data = os.environ.get("DATA_DIR")
    if data and os.path.isdir(data):
        return Path(data) / "products"
    return Path(tempfile.gettempdir()) / "campaign-os-prices"


def _clublab(fid: int, get: Getter) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for kind in ("services", "packages"):
        status, body = get(f"{CLUBLAB_BASE}/{kind}?facilityId={fid}")
        if status != 200:
            raise RuntimeError(f"HTTP {status}")
        data = (json.loads(body.decode("utf-8")) or {}).get("data") or {}
        for it in data.get("items") or []:
            if (it.get("status") or "Active") != "Active":
                continue
            cents = it.get("priceCents")
            if not cents:
                continue  # free assessments carry no price to check
            items.append({
                "name": it.get("title") or it.get("name") or "",
                "rand": int(round(cents / 100)),
                "source": f"ClubLab {kind} ({data.get('facilityName') or fid})",
            })
    return items


def _shopify(domain: str, get: Getter) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for page in range(1, SHOPIFY_MAX_PAGES + 1):
        status, body = get(f"https://{domain}/products.json?limit={SHOPIFY_PAGE_SIZE}&page={page}")
        if status != 200:
            raise RuntimeError(f"HTTP {status}")
        products = (json.loads(body.decode("utf-8")) or {}).get("products") or []
        if not products:
            break
        for p in products:
            for v in p.get("variants") or []:
                for field in ("price", "compare_at_price"):
                    raw = v.get(field)
                    if not raw:
                        continue
                    try:
                        rand = int(round(float(raw)))
                    except (TypeError, ValueError):
                        continue
                    label = p.get("title") or ""
                    if field == "compare_at_price":
                        label += " (was)"
                    items.append({"name": label, "rand": rand, "source": f"Shopify {domain}"})
    return items


def live_prices(brand: str, *, get: Getter = _get, cache_dir: Optional[Path] = None,
                now: Callable[[], float] = time.time, max_age_s: int = MAX_AGE_S) -> Dict[str, Any]:
    """{"items": [{name, rand, source}], "errors": [...], "fetched_at": epoch} for one brand."""
    sources = SOURCES.get(brand)
    if not sources:
        return {"items": [], "errors": [f"No price source is set up for {brand}"], "fetched_at": now()}
    cache = _cache_dir(cache_dir) / f"live-prices-{brand}.json"
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if now() - float(cached.get("fetched_at") or 0) < max_age_s and not cached.get("errors"):
            return cached
    except (OSError, ValueError):
        pass
    items: List[Dict[str, Any]] = []
    errors: List[str] = []
    if "clublab" in sources:
        try:
            items += _clublab(sources["clublab"], get)
        except Exception as e:  # noqa: BLE001 (any failure means "could not read")
            errors.append(f"ClubLab booking list could not be read: {e}")
    if "shopify" in sources:
        try:
            items += _shopify(sources["shopify"], get)
        except Exception as e:  # noqa: BLE001
            errors.append(f"Shop {sources['shopify']} could not be read: {e}")
    res = {"items": items, "errors": errors, "fetched_at": now()}
    if items and not errors:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return res


def approved_prices(brand: str, *, path: Optional[Path] = None,
                    today: Optional[dt.date] = None) -> List[Dict[str, Any]]:
    """Approved prices still in date. An entry without a source does not count."""
    path = path or BRAND_DIR / brand / "prices-approved.json"
    today = today or dt.date.today()
    try:
        rows = json.loads(Path(path).read_text(encoding="utf-8")).get("prices") or []
    except (OSError, ValueError):
        return []
    out = []
    for r in rows:
        if not r.get("source") or not isinstance(r.get("rand"), int):
            continue
        until = r.get("until")
        if until:
            try:
                if dt.date.fromisoformat(until) < today:
                    continue
            except ValueError:
                continue
        out.append({"name": r.get("what") or "", "rand": r["rand"], "source": f"Approved: {r['source']}"})
    return out


def price_list(brand: str, *, get: Getter = _get, cache_dir: Optional[Path] = None,
               today: Optional[dt.date] = None) -> Dict[str, Any]:
    """Live and approved prices together, plus any source that could not be read."""
    live = live_prices(brand, get=get, cache_dir=cache_dir)
    return {
        "brand": brand,
        "items": live["items"] + approved_prices(brand, today=today),
        "errors": live["errors"],
    }


def check_text(text: str, prices: Dict[str, Any]) -> Dict[str, Any]:
    """Split the prices in a text into known (with what they are) and unknown."""
    by_rand: Dict[int, Dict[str, Any]] = {}
    for it in prices.get("items") or []:
        by_rand.setdefault(it["rand"], it)
    known, unknown = [], []
    for tok, value in find_prices(text):
        hit = by_rand.get(value)
        if hit:
            known.append({"token": tok, "name": hit["name"], "source": hit["source"]})
        elif tok not in unknown:
            unknown.append(tok)
    return {"known": known, "unknown": unknown, "errors": list(prices.get("errors") or [])}
