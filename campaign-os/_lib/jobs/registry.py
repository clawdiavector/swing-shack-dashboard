"""Job registry. meta_refresh is registered here; gbp/freshness via register() from app.py."""

from __future__ import annotations

from .spec import JobSpec

JOBS: dict[str, JobSpec] = {}


def register(spec: JobSpec) -> None:
    """Register or replace a JobSpec by name."""
    JOBS[spec.name] = spec


def _bootstrap_meta() -> None:
    """Register meta_refresh without importing app.py (avoids circular import)."""
    if "meta_refresh" in JOBS:
        return
    from _lib.meta_live_fetch import fetch_all as _meta_refresh

    register(
        JobSpec(
            name="meta_refresh",
            fn=_meta_refresh,
            every_seconds=43200,  # 12h — 06:30/18:30 SAST cadence
            criticality="HIGH",
            credentials=("META_SYSTEM_USER_TOKEN",),
            writes=(
                "ig-analytics.json",
                "ig-business-analytics.json",
                "facebook-analytics.json",
                "facebook-business-analytics.json",
            ),
        )
    )


_bootstrap_meta()
