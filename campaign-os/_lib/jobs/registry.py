"""Job registry. meta_refresh + Layer 1 bootstrap here; gbp/freshness via app.py."""

from __future__ import annotations

from .spec import JobSpec

JOBS: dict[str, JobSpec] = {}


def register(spec: JobSpec) -> None:
    """Register or replace a JobSpec by name."""
    from .brand_lanes import validate_job_spec

    validate_job_spec(spec, JOBS)
    JOBS[spec.name] = spec
    validate_job_spec(spec, JOBS)


def _bootstrap_meta() -> None:
    """Register meta_refresh without importing app.py (avoids circular import)."""
    if "meta_refresh" in JOBS:
        return
    # V2.4.1 §1: extend meta_refresh to also pull paid-media.
    # Uses fetch_all_with_paid_media (same function extended
    # to also call /act_{id}/insights at level=campaign).
    from _lib.meta_live_fetch import fetch_all_with_paid_media as _meta_refresh

    register(
        JobSpec(
            name="meta_refresh",
            fn=_meta_refresh,
            every_seconds=43200,  # 12h — 06:30/18:30 SAST cadence
            criticality="HIGH",
            credentials=(
                "META_SYSTEM_USER_TOKEN",
                "META_SYSTEM_USER_TOKEN_STICK",
                "META_SYSTEM_USER_TOKEN_STICK_PAARL",
            ),
            writes=(
                "ig-analytics.json",
                "ig-business-analytics.json",
                "facebook-analytics.json",
                "facebook-business-analytics.json",
                "paid-media/stick.json",
                "paid-media/swing-shack.json",
            ),
            brand_mode="per_brand",
            requires_integrations=("meta",),
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
