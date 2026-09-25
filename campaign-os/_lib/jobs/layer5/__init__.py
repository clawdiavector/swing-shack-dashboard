"""Layer 5 jobs — Create (draft_assets, asset_qc)."""

from __future__ import annotations

from typing import Callable

from ..spec import JobSpec
from . import asset_qc, draft_assets, krea_poll_draft_images, retry_failed_images

LAYER5_JOB_NAMES: tuple[str, ...] = (
    "retry_failed_images",
    "draft_assets",
    "krea_poll_draft_images",
    "asset_qc",
)

LAYER5_DAILY = 86400

_ALL_ACTIVE_BRANDS = ("swing-shack", "stick", "bag-drop")


def layer5_specs() -> list[JobSpec]:
    """Return all Layer 5 JobSpecs."""
    return [
        JobSpec(
            name="retry_failed_images",
            fn=retry_failed_images.run,
            every_seconds=LAYER5_DAILY,
            timeout_seconds=90,
            best_effort=True,
            criticality="MEDIUM",
            retries=0,
            credentials=(),
            reads=("agent-queue.json",),
            writes=("agent-queue.json",),
            upstream=("agent_queue_writer",),
            brand_mode="per_brand",
            brands=_ALL_ACTIVE_BRANDS,
        ),
        JobSpec(
            name="draft_assets",
            fn=draft_assets.run,
            every_seconds=LAYER5_DAILY,
            timeout_seconds=120,
            best_effort=True,
            criticality="MEDIUM",
            retries=0,
            credentials=("OPENAI_API_KEY",),
            reads=("agent-queue.json",),
            writes=("draft-assets/", "campaign-data.json"),
            upstream=("retry_failed_images",),
            brand_mode="per_brand",
            brands=_ALL_ACTIVE_BRANDS,
        ),
        JobSpec(
            name="krea_poll_draft_images",
            fn=krea_poll_draft_images.run,
            every_seconds=LAYER5_DAILY,
            timeout_seconds=180,
            best_effort=True,
            criticality="MEDIUM",
            retries=0,
            credentials=("KREA_API_KEY",),
            reads=("agent-queue.json",),
            writes=("draft-assets/", "campaign-data.json"),
            upstream=("draft_assets",),
            brand_mode="per_brand",
            brands=_ALL_ACTIVE_BRANDS,
        ),
        JobSpec(
            name="asset_qc",
            fn=asset_qc.run,
            every_seconds=LAYER5_DAILY,
            timeout_seconds=60,
            best_effort=False,
            criticality="LOW",
            retries=0,
            credentials=(),
            reads=("draft-assets/",),
            writes=("asset-qc.json",),
            upstream=("krea_poll_draft_images",),
            brand_mode="per_brand",
            brands=_ALL_ACTIVE_BRANDS,
        ),
    ]


def bootstrap_layer5(register: Callable[[JobSpec], None] | None = None) -> None:
    """Register all Layer 5 JobSpecs."""
    if register is None:
        from ..registry import register as register  # noqa: PLC0415

    for spec in layer5_specs():
        register(spec)
