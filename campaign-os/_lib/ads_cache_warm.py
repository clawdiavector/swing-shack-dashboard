"""Keep the Meta ad cache the weekly report reads warm, so a person never opens it cold.

The weekly report's Advertising section reads ``/api/meta/ads/cache/<brand>?period_days=7|31``. That route
re-ingests from Meta when its copy is older than 12 hours, and does it inside the page request: slow enough that the
report's own 60 second timeout gives up and the section reads "Advertising is not yet connected" (seen on 2026-10-22,
first load of the day, for both brands). The ads job runs every morning, so it refreshes the same two files first.

The route itself is unchanged; this only keeps its files fresh. It mirrors the route's own steps: ingest, and when the
ingest is good copy the canonical ``paid-media/<brand>.json`` to the period-scoped file.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import ads_brain

PERIODS = (7, 31)
# Older than this is refreshed. Under the route's 12 hours so a morning refresh is still fresh at 19:00.
MIN_AGE_HOURS = 6


def warm(brand_id: str, *, ingest, data_dir, deadline: float | None = None, min_age_hours: float = MIN_AGE_HOURS) -> dict:
    """Refresh each period's cache file that is missing or older than ``min_age_hours``.

    ``ingest(brand_id, period_days=..., ytd=...)`` is the app's own ingest. ``deadline`` is a ``time.monotonic()``
    value after which nothing more is started, so the warm-up can never cost the job its time. Returns
    {"7": ..., "31": ...} with a plain word for each. Never raises.
    """
    out: dict = {}
    base = Path(data_dir) / "paid-media"
    for period in PERIODS:
        key = str(period)
        if deadline is not None and time.monotonic() > deadline:
            out[key] = "skipped: out of time"
            continue
        path = base / f"{brand_id}__{period}d.json"
        try:
            if not ads_brain.is_stale(path, min_age_hours):
                out[key] = "already fresh"
                continue
            res = ingest(brand_id, period_days=period, ytd=(period >= 31)) or {}
            canonical = base / f"{brand_id}.json"
            if bool((res.get("current_period") or {}).get("ok")) and canonical.exists():
                shutil.copy2(canonical, path)
                out[key] = "refreshed"
            else:
                out[key] = "failed"
        except Exception as exc:  # one window failing must not stop the other
            out[key] = f"failed: {type(exc).__name__}"
    return out
