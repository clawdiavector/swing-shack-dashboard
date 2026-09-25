"""Weekly social history ingest — Meta IG/FB posts into brand-directory/social/."""

from __future__ import annotations

from typing import Any

JOB_NAME = "social_ingest"

_META_PLATFORMS = frozenset({"instagram", "facebook"})


def run(*, brand: str | None = None) -> dict[str, Any]:
    """Ingest social history for publish channels that include IG or Facebook."""
    if not brand:
        return {"ok": False, "error": "brand required for social_ingest"}

    from _lib.publish_sandbox import intended_publish_channels  # noqa: PLC0415
    from _lib.social_history import (  # noqa: PLC0415
        _meta_credentials_missing_reason,
        ingest_social_history,
    )

    channels = {c.lower() for c in intended_publish_channels(brand)}
    platforms = sorted(channels & _META_PLATFORMS)
    if not platforms:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no instagram or facebook in intended_publish_channels",
            "brand": brand,
        }

    meta_reason = _meta_credentials_missing_reason(brand)
    if meta_reason:
        return {"ok": True, "skipped": True, "reason": meta_reason, "brand": brand}

    summary = ingest_social_history(
        brand,
        platforms=tuple(platforms),
        download_thumbnails=True,
    )
    plat_summary = summary.get("platforms") or {}
    total = sum(int((plat_summary.get(p) or {}).get("count") or 0) for p in platforms)
    all_skipped = all(
        (plat_summary.get(p) or {}).get("status") == "skipped" for p in platforms
    )
    if all_skipped:
        reasons = [
            str((plat_summary.get(p) or {}).get("reason") or "")
            for p in platforms
        ]
        reason = next((r for r in reasons if r), "all platforms skipped")
        return {"ok": True, "skipped": True, "reason": reason, "brand": brand, "platforms": plat_summary}

    return {
        "ok": True,
        "brand": brand,
        "platforms": plat_summary,
        "posts": total,
    }
