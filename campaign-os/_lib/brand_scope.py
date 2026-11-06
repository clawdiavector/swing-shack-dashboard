"""Which businesses Campaign OS markets, and which of them are a place people visit.

One list instead of ~45 copies of ("swing-shack", "stick") (audit 2026-11-06, wiki
research/bag-drop-activation-audit-and-brand-parity-2026-11-06). Christelle asked for
everything done for Swing Shack and Stick to be done for The Bag Drop too, so a feature
uses OPERATING_BRANDS unless it only makes sense for a venue.

VENUE_BRANDS have a physical place: Google Business Profile, bookings, services,
fittings and local events apply to them. The Bag Drop is an online store
(thebagdrop.co.za) with no shop to visit, so those stay off for it.

Ads are not here: a brand runs ads when it has a Meta ad account
(app._META_ADS_ACCOUNT_FOR_BRAND).
"""
from __future__ import annotations

OPERATING_BRANDS: tuple[str, ...] = ("swing-shack", "stick", "bag-drop")
VENUE_BRANDS: tuple[str, ...] = ("swing-shack", "stick")

# Each brand's own website. Bag Drop is thebagdrop.co.za, never bagdrop.co.za (an
# unrelated luggage company) or swingshack.co.za.
BRAND_DOMAINS: dict[str, str] = {
    "swing-shack": "swingshack.co.za",
    "stick": "stickgolf.co.za",
    "bag-drop": "thebagdrop.co.za",
}


def is_operating(brand_id: str | None) -> bool:
    return brand_id in OPERATING_BRANDS


def is_venue(brand_id: str | None) -> bool:
    return brand_id in VENUE_BRANDS
