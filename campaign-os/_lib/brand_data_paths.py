"""Shared brand-aware DATA_DIR path resolution for app and _lib readers."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

# Per-brand L1 job outputs that app/_lib readers must resolve under brands/<id>/.
PER_BRAND_L1_OUTPUTS = frozenset({
    "anomaly-alerts.json",
    "booking-events.json",
    "competitor-tracker.json",
    "conversion-attribution.json",
    "facebook-analytics.json",
    "facebook-business-analytics.json",
    "funnel-leaks.json",
    "ga4-metrics.json",
    "geo-audit.json",
    "google-ads.json",
    "hook-bank.json",
    "ig-analytics.json",
    "ig-business-analytics.json",
    "lead-quality.json",
    "leads.json",
    "meta-ads.json",
    "missed-opportunities.json",
    "post-conversion-score.json",
    "recommendation-outcomes.json",
    "recommendation-scores.json",
    "retargeting-recommendations.json",
    "search-console.json",
    "seo-audit.json",
    "seo-rankings.json",
    "ubersuggest-backlinks.json",
    "ubersuggest-competitors.json",
    "ubersuggest-domain.json",
    "website-insights.json",
    "youtube-hook-signals.json",
})


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data"))


def _bundled_data_dir() -> Path | None:
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    return Path(bundled) if bundled else None


@lru_cache(maxsize=1)
def _default_brand_id() -> str:
    bundled = _bundled_data_dir()
    brands_file = (bundled / "brands.json") if bundled else None
    if brands_file and brands_file.is_file():
        try:
            reg = json.loads(brands_file.read_text(encoding="utf-8"))
            return str(reg.get("default_brand_id") or "swing-shack")
        except (json.JSONDecodeError, OSError):
            pass
    return "swing-shack"


def resolve_brand_data_path(rel: str, brand: str | None) -> str:
    """Return filesystem path for a data file, brand-first with flat fallback."""
    bid = brand or _default_brand_id()
    rel = rel.lstrip("/").replace("\\", "/")
    if rel not in PER_BRAND_L1_OUTPUTS:
        runtime = _data_dir() / rel
        if runtime.is_file():
            return str(runtime)
        bundled = _bundled_data_dir()
        if bundled:
            bundled_path = bundled / rel
            if bundled_path.is_file():
                return str(bundled_path)
        return str(runtime)

    brand_rel = f"brands/{bid}/{rel}"
    brand_path = _data_dir() / brand_rel
    if brand_path.is_file():
        return str(brand_path)

    if bid == _default_brand_id():
        flat = _data_dir() / rel
        if flat.is_file():
            return str(flat)
        bundled = _bundled_data_dir()
        if bundled:
            bundled_flat = bundled / rel
            if bundled_flat.is_file():
                return str(bundled_flat)

    bundled = _bundled_data_dir()
    if bundled:
        bundled_brand = bundled / brand_rel
        if bundled_brand.is_file():
            return str(bundled_brand)
        if bid == _default_brand_id():
            bundled_flat = bundled / rel
            if bundled_flat.is_file():
                return str(bundled_flat)

    return str(brand_path)


def read_brand_data_json(rel: str, brand: str | None) -> dict | list | None:
    """Read JSON from brand path with default-brand flat fallback."""
    path = Path(resolve_brand_data_path(rel, brand))
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None
