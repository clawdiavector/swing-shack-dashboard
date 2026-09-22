"""Layer 2 jobs — health + planning (slot planner, queue writer, review SLA)."""

from __future__ import annotations

from typing import Callable

from ..spec import JobSpec
from . import agent_queue_writer, data_archive, holiday_inject, review_sla, slot_planner

LAYER2_JOB_NAMES: tuple[str, ...] = (
    "slot_planner",
    "agent_queue_writer",
    "review_sla",
    "holiday_inject",
    "data_archive",
)

LAYER2_DAILY = 86400

_ALL_ACTIVE_BRANDS = ("swing-shack", "stick", "bag-drop")


def layer2_specs() -> list[JobSpec]:
    """Return all Layer 2 JobSpecs."""
    return [
        JobSpec(
            name="slot_planner",
            fn=slot_planner.run,
            every_seconds=LAYER2_DAILY,
            timeout_seconds=60,
            best_effort=True,
            criticality="MEDIUM",
            credentials=(),
            writes=("slot-planner.json",),
            brand_mode="fanout_internal",
        ),
        JobSpec(
            name="agent_queue_writer",
            fn=agent_queue_writer.run,
            every_seconds=LAYER2_DAILY,
            timeout_seconds=60,
            best_effort=True,
            criticality="MEDIUM",
            credentials=(),
            writes=("agent-queue.json",),
            reads=("slot-planner.json", "freshness.json", "recommendation-scores.json"),
            upstream=("slot_planner", "freshness_scan", "insights_reco"),
            brand_mode="fanout_internal",
            shared_reads=("freshness.json",),
        ),
        JobSpec(
            name="review_sla",
            fn=review_sla.run,
            every_seconds=LAYER2_DAILY,
            timeout_seconds=60,
            best_effort=True,
            criticality="LOW",
            credentials=(),
            writes=("review-sla.json",),
            brand_mode="fanout_internal",
        ),
        JobSpec(
            name="holiday_inject",
            fn=holiday_inject.run,
            every_seconds=LAYER2_DAILY,
            timeout_seconds=60,
            best_effort=False,
            criticality="LOW",
            credentials=(),
            writes=(
                "intelligence/marketing-calendar/stick.jsonl",
                "intelligence/marketing-calendar/swing-shack.jsonl",
                "intelligence/marketing-calendar/bag-drop.jsonl",
            ),
            brand_mode="per_brand",
            brands=_ALL_ACTIVE_BRANDS,
        ),
        JobSpec(
            name="data_archive",
            fn=data_archive.run,
            every_seconds=LAYER2_DAILY,
            timeout_seconds=120,
            best_effort=True,
            criticality="MEDIUM",
            credentials=(),
            writes=("archive/manifest.json",),
            brand_mode="fanout_internal",
        ),
    ]


def bootstrap_layer2(register: Callable[[JobSpec], None] | None = None) -> None:
    """Register all Layer 2 JobSpecs."""
    if register is None:
        from ..registry import register as register  # noqa: PLC0415

    for spec in layer2_specs():
        register(spec)
