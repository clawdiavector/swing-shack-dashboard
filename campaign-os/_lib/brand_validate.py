"""Brand id validation for agent pipeline and write APIs."""

from __future__ import annotations

from _lib.marketing_calendar import VALID_BRAND_IDS

QUEUE_BRAND_SENTINELS = frozenset({"all"})

# swing-shack is the legacy global Postiz tenant; other lanes must not inherit its key.
POSTIZ_GLOBAL_FALLBACK_BRAND = "swing-shack"


def validate_brand_id(raw: str | None, *, allow_sentinel: bool = False) -> str:
    """Return normalized brand_id or raise ValueError."""
    value = str(raw or "").strip().lower()
    if not value:
        raise ValueError("brand_id required")
    if value in VALID_BRAND_IDS:
        return value
    if allow_sentinel and value in QUEUE_BRAND_SENTINELS:
        return value
    raise ValueError(
        f"invalid brand_id {value!r}; expected one of {list(VALID_BRAND_IDS)}"
    )
