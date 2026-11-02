"""One line added to a brand's product captions while its online store is not live yet.

Delete the brand's entry when the store opens, and replace it with the store link."""

from __future__ import annotations

NOTICES: dict[str, str] = {
    "stick": "Shopify store coming soon.",
}

# A closing signature stays last, so the notice goes above it.
SIGN_OFFS: dict[str, str] = {
    "stick": "Better begins here.",
}


def add_store_notice(caption: str | None, brand: str) -> str | None:
    notice = NOTICES.get(brand)
    if not caption or not notice:
        return caption
    lines = caption.rstrip().split("\n")
    if notice in lines:
        return caption
    if lines[-1].strip() == SIGN_OFFS.get(brand):
        lines.insert(len(lines) - 1, notice)
    else:
        lines.append(notice)
    return "\n".join(lines)
