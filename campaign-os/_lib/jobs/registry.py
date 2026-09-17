"""Job registry. meta_refresh + Layer 1 bootstrap here; gbp/freshness via app.py."""

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


def _bootstrap_layer1() -> None:
    """Register eight Layer 1 ports (t30). Idempotent via register().replace."""
    from .layer1 import bootstrap_layer1

    bootstrap_layer1(register)


def _bootstrap_layer2() -> None:
    """Register the three L2 health/planning jobs. Idempotent via register()."""
    from .layer2 import bootstrap_layer2

    bootstrap_layer2(register)


def _bootstrap_layer5() -> None:
    """Register L5 Create jobs (draft_assets, asset_qc). Idempotent via register()."""
    from .layer5 import bootstrap_layer5

    bootstrap_layer5(register)


def _bootstrap_layer7() -> None:
    """Register L7 Learn jobs. Idempotent via register()."""
    from .layer7 import bootstrap_layer7

    bootstrap_layer7(register)


_bootstrap_meta()
_bootstrap_layer1()
_bootstrap_layer2()
_bootstrap_layer5()
_bootstrap_layer7()
