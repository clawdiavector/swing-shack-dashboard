"""Link a product post to a service the shop offers, so it is not just "in stock".

Only pairings the brands really offer go here. Ball fitting, club fitting, putter fitting,
wedge gapping and re-gripping are confirmed for both Swing Shack and Stick (Christelle,
2026-10-27). Add a category only once the service is confirmed for that brand."""

from __future__ import annotations

SHOPS: dict[str, str] = {"swing-shack": "Swing Shack", "stick": "Stick"}

CLUB_FITTING = "Fit before you buy. Book a club fitting at {shop}."

# category (from stock_pulse.categorise) -> caption line; {shop} is filled per brand.
TIE_INS: dict[str, str] = {
    "ball": "Not sure which one suits your game? Book a ball fitting at {shop}.",
    "putter": "Putter feel is personal. Book a putter fitting at {shop}.",
    "wedge": "Know your gaps. Book a wedge gapping session at {shop}.",
    "grip": "Tired grips? Ask about a re-grip at {shop}.",
    "driver-wood": CLUB_FITTING,
    "shaft": CLUB_FITTING,
}


def service_tiein_line(product_name: str | None, brand: str) -> str | None:
    from _lib.stock_pulse import categorise
    shop = SHOPS.get(brand)
    if not product_name or not shop:
        return None
    template = TIE_INS.get(categorise(product_name))
    return template.format(shop=shop) if template else None


def add_service_tiein(caption: str | None, product_name: str | None, brand: str) -> str | None:
    line = service_tiein_line(product_name, brand)
    if not caption or not line:
        return caption
    lines = caption.rstrip().split("\n")
    if line in lines:
        return caption
    # After the "Available at ..." line when there is one, otherwise at the end.
    at = next((i for i, l in enumerate(lines) if l.startswith("Available at")), len(lines) - 1)
    lines.insert(at + 1, line)
    return "\n".join(lines)
