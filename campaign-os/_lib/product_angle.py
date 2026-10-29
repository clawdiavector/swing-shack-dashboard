"""One angle per product post, rotated so posts in a row don't read as repeats.

  product   the product on its own
  service   the product tied to the service that goes with it (service_tiein)
  shopify   the product plus the brand's online-store line (store_notice); only brands that have one

The next angle is the least recently used one the product allows, never the same as the last post
when there is a choice. Recent angles are kept per brand in the runtime data dir."""

from __future__ import annotations

import json

from _lib.data_paths import runtime_data_dir
from _lib.service_tiein import add_service_tiein, service_tiein_line
from _lib.store_notice import NOTICES, add_store_notice

ANGLES = ("product", "service", "shopify")
_KEEP = 24


def available(brand: str, product_name: str | None) -> list[str]:
    out = ["product"]
    if service_tiein_line(product_name, brand):
        out.append("service")
    if NOTICES.get(brand):
        out.append("shopify")
    return out


def next_angle(brand: str, product_name: str | None, recent: list[str]) -> str:
    opts = available(brand, product_name)
    if recent and len(opts) > 1:
        opts = [a for a in opts if a != recent[-1]] or opts

    def last_used(a: str) -> int:
        return max((i for i, r in enumerate(recent) if r == a), default=-1)

    return min(opts, key=lambda a: (last_used(a), ANGLES.index(a)))


def apply_angle(caption: str | None, angle: str, product_name: str | None, brand: str) -> str | None:
    if angle == "service":
        return add_service_tiein(caption, product_name, brand)
    if angle == "shopify":
        return add_store_notice(caption, brand)
    return caption


def _history_path(brand: str):
    return runtime_data_dir() / "product-angles" / f"{brand}.json"


def recent_angles(brand: str) -> list[str]:
    try:
        data = json.loads(_history_path(brand).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [a for a in data if a in ANGLES] if isinstance(data, list) else []


def remember(brand: str, angle: str) -> None:
    path = _history_path(brand)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps((recent_angles(brand) + [angle])[-_KEEP:]), encoding="utf-8")


def caption_with_rotation(caption: str | None, product_name: str | None, brand: str) -> tuple[str | None, str]:
    """Pick the next angle for this brand, add its line to the caption, and remember it."""
    angle = next_angle(brand, product_name, recent_angles(brand))
    remember(brand, angle)
    return apply_angle(caption, angle, product_name, brand), angle
