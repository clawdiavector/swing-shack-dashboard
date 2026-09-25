"""auto_release job — release scheduled posts on go-live day (SAST). Off by default."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

_SAST = ZoneInfo("Africa/Johannesburg")


def _auto_release_enabled() -> bool:
    raw = (os.environ.get("CAMPAIGN_OS_AUTO_RELEASE") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _default_release_hour() -> int:
    raw = (os.environ.get("CAMPAIGN_OS_AUTO_RELEASE_HOUR") or "0").strip()
    try:
        return max(0, min(23, int(raw)))
    except ValueError:
        return 0


def _brand_release_hour(brand_id: str) -> int:
    from _lib.marketing_calendar import load_brand_config  # noqa: PLC0415

    try:
        cfg = load_brand_config(brand_id)
    except ValueError:
        return _default_release_hour()
    prefs = cfg.get("calendar_preferences") if isinstance(cfg, dict) else None
    if not isinstance(prefs, dict):
        return _default_release_hour()
    rt = prefs.get("release_time_sast")
    if isinstance(rt, str) and ":" in rt:
        try:
            return max(0, min(23, int(rt.split(":")[0])))
        except ValueError:
            pass
    return _default_release_hour()


def _auto_release_reason() -> str:
    if _auto_release_enabled():
        return "CAMPAIGN_OS_AUTO_RELEASE=1"
    raw = (os.environ.get("CAMPAIGN_OS_AUTO_RELEASE") or "").strip()
    if not raw:
        return "CAMPAIGN_OS_AUTO_RELEASE unset"
    return f"CAMPAIGN_OS_AUTO_RELEASE={raw!r} (not enabled)"


def run(*, brand: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Release scheduled posts whose go-live is today (SAST). Gated by CAMPAIGN_OS_AUTO_RELEASE."""
    from _lib.marketing_calendar import VALID_BRAND_IDS, canonical_records  # noqa: PLC0415
    from _lib import unified_inbox  # noqa: PLC0415
    from _lib.publish_sandbox import release_moment  # noqa: PLC0415

    now_local = (now or datetime.now(timezone.utc)).astimezone(_SAST)
    today = now_local.date()
    brands = [brand] if brand else list(VALID_BRAND_IDS)

    candidates: list[str] = []
    for brand_id in brands:
        if brand_id not in VALID_BRAND_IDS:
            continue
        hour_gate = _brand_release_hour(brand_id)
        if now_local.hour < hour_gate:
            continue
        index = unified_inbox.build_post_index(brand_id=brand_id)
        for record in canonical_records(brand_id):
            joined = unified_inbox.post_state(record, index=index, now=now)
            if str(joined.get("state") or "") != "scheduled":
                continue
            go_live = joined.get("go_live_date")
            if not go_live:
                continue
            try:
                go_date = date.fromisoformat(str(go_live)[:10])
            except ValueError:
                continue
            if go_date != today:
                continue
            cal_id = str(joined.get("calendar_id") or "")
            if cal_id:
                candidates.append(f"{brand_id}:{cal_id}")

    enabled = _auto_release_enabled()
    if not enabled:
        return {
            "ok": True,
            "rows": len(candidates),
            "released": 0,
            "gated": True,
            "reason": _auto_release_reason(),
            "candidates": candidates,
        }

    released_count = 0
    errors: list[str] = []
    for token in candidates:
        brand_id, cal_id = token.split(":", 1)
        result = release_moment(
            brand_id=brand_id,
            calendar_id=cal_id,
            editor="auto_release",
            dispatch=False,
        )
        if result.get("ok"):
            released_count += 1
        else:
            code = str(result.get("code") or result.get("error") or "failed")
            errors.append(f"{cal_id}: {code}")

    return {
        "ok": True,
        "rows": len(candidates),
        "released": released_count,
        "gated": False,
        "candidates": candidates,
        "errors": errors[:20],
    }
