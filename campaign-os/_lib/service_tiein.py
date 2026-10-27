"""Link a product post to a service the shop offers, so it is not just "in stock".

Only pairings the brands really offer go here. Ball fitting is run at both Swing Shack
and Stick. Add a category only once the service is confirmed for that brand."""

from __future__ import annotations

# category (from stock_pulse.categorise) -> brand -> caption line
TIE_INS: dict[str, dict[str, str]] = {
    "ball": {
        "swing-shack": "Not sure which one suits your game? Book a ball fitting at Swing Shack.",
        "stick": "Not sure which one suits your game? Book a ball fitting at Stick.",
    },
}


def service_tiein_line(product_name: str | None, brand: str) -> str | None:
    from _lib.stock_pulse import categorise
    if not product_name:
        return None
    return TIE_INS.get(categorise(product_name), {}).get(brand)


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
