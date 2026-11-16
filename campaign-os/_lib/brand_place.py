"""Is a suggestion set far from the brand? (audit, 3 Nov 2026)

Stick is in Paarl (Western Cape), Swing Shack in Johannesburg (Gauteng); they are separate
companies. The scout offered Stick a Johannesburg tournament as "the most local elite
event". A suggestion that names a South African place in another province, and none in the
brand's own, is far away. International events are watched anywhere; Bag Drop is online.
"""

from __future__ import annotations

import re
from typing import Optional

HOME = {
    "stick": ("Western Cape", "Paarl"),
    "swing-shack": ("Gauteng", "Johannesburg"),
}

PLACES = {
    "Gauteng": ("Johannesburg", "Joburg", "Jozi", "JHB", "Sandton", "Woodmead", "Houghton", "Randburg",
                "Fourways", "Midrand", "Pretoria", "Tshwane", "Centurion", "Soweto", "Gauteng"),
    "Western Cape": ("Cape Town", "Paarl", "Stellenbosch", "Franschhoek", "Somerset West", "Winelands",
                     # Not "George": golfers are called George too. Fancourt is the course there.
                     "Durbanville", "Hermanus", "Fancourt", "Knysna", "Western Cape"),
    "KwaZulu-Natal": ("Durban", "Umhlanga", "Ballito", "Pietermaritzburg", "KwaZulu-Natal", "KZN"),
    "Mpumalanga": ("Leopard Creek", "Malelane", "Mbombela", "Nelspruit", "Mpumalanga"),
    "North West": ("Sun City", "Rustenburg", "North West"),
    "Eastern Cape": ("Gqeberha", "Port Elizabeth", "East London", "Eastern Cape"),
    "Free State": ("Bloemfontein", "Free State"),
    "Limpopo": ("Polokwane", "Limpopo"),
}

_PATTERNS = [
    (province, place, re.compile(rf"(?<![A-Za-z]){re.escape(place)}(?![A-Za-z])", re.IGNORECASE))
    for province, places in PLACES.items()
    for place in places
]


def far_from_brand(brand_id: str, text: str) -> Optional[dict]:
    """{place, home} when the text is set in another province than the brand's, else None."""
    home = HOME.get(brand_id)
    if not home or not text:
        return None
    found = sorted(
        (m.start(), province, place)
        for province, place, pattern in _PATTERNS
        for m in [pattern.search(text)]
        if m
    )
    if not found or any(province == home[0] for _, province, _ in found):
        return None
    _, _, place = found[0]
    return {"place": place, "home": home[1]}
