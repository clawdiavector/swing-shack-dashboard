"""Per-brand daily image submit cap (CAMPAIGN_OS_MAX_IMAGES_PER_DAY)."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

_LOCK = threading.Lock()
SCHEMA = "campaign-os/image-submit-count/v1"
DEFAULT_MAX_PER_DAY = 2


def _data_dir() -> str:
    return os.environ.get("DATA_DIR") or "/data/campaign-os"


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def max_images_per_day() -> int:
    raw = (os.environ.get("CAMPAIGN_OS_MAX_IMAGES_PER_DAY") or "").strip()
    if not raw:
        return DEFAULT_MAX_PER_DAY
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MAX_PER_DAY


def _day_path(day: str | None = None) -> str:
    d = day or _utc_day()
    return os.path.join(_data_dir(), "image-submit-count", f"{d}.json")


def _load(day: str | None = None) -> dict[str, Any]:
    path = _day_path(day)
    d = day or _utc_day()
    if not os.path.isfile(path):
        return {"schema": SCHEMA, "date": d, "brands": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("image-submit-count must be object")
        data.setdefault("schema", SCHEMA)
        data.setdefault("date", d)
        brands = data.get("brands")
        if not isinstance(brands, dict):
            data["brands"] = {}
        return data
    except (OSError, ValueError, TypeError):
        return {"schema": SCHEMA, "date": d, "brands": {}, "broken": True}


def _save(data: dict[str, Any]) -> None:
    path = _day_path(data.get("date"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def count_for_brand(brand_id: str, *, day: str | None = None) -> int:
    with _LOCK:
        data = _load(day)
        brands = data.get("brands") if isinstance(data.get("brands"), dict) else {}
        try:
            return max(0, int(brands.get(brand_id) or 0))
        except (TypeError, ValueError):
            return 0


def totals_today() -> dict[str, int]:
    with _LOCK:
        data = _load()
        brands = data.get("brands") if isinstance(data.get("brands"), dict) else {}
        out: dict[str, int] = {}
        for key, val in brands.items():
            try:
                out[str(key)] = max(0, int(val or 0))
            except (TypeError, ValueError):
                continue
        return out


def check_brand_image_submit(brand_id: str) -> tuple[bool, str]:
    cap = max_images_per_day()
    if cap <= 0:
        return False, "daily image submit cap is zero"
    used = count_for_brand(brand_id)
    if used >= cap:
        return False, f"daily image cap reached for {brand_id} ({used}/{cap})"
    return True, "ok"


def record_brand_image_submit(brand_id: str) -> dict[str, int]:
    """Increment submit count after a provider submit is initiated."""
    with _LOCK:
        data = _load()
        brands = data.setdefault("brands", {})
        if not isinstance(brands, dict):
            brands = {}
            data["brands"] = brands
        used = max(0, int(brands.get(brand_id) or 0)) + 1
        brands[brand_id] = used
        try:
            _save(data)
        except OSError:
            pass
        return {"brand_id": brand_id, "count": used, "cap": max_images_per_day()}
