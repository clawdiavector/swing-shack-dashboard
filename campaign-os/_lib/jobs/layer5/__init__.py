"""Layer 5 jobs — Create (draft_assets, asset_qc)."""

from __future__ import annotations

from typing import Callable

from ..spec import JobSpec
from . import asset_qc, draft_assets

LAYER5_JOB_NAMES: tuple[str, ...] = (
    "draft_assets",
    "asset_qc",
)

LAYER5_DAILY = 86400


def layer5_specs() -> list[JobSpec]:
    """Return all Layer 5 JobSpecs."""
    return [
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
            upstream=("agent_queue_writer",),
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
            upstream=("draft_assets",),
        ),
    ]


def bootstrap_layer5(register: Callable[[JobSpec], None] | None = None) -> None:
    """Register all Layer 5 JobSpecs."""
    if register is None:
        from ..registry import register as register  # noqa: PLC0415

    for spec in layer5_specs():
        register(spec)
