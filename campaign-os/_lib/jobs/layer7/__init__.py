"""Layer 7 jobs — Learn (outcomes, recipes, human edit signals)."""

from __future__ import annotations

from typing import Callable

from ..spec import JobSpec
from . import human_edit_signal, post_outcomes, proposal_outcome, winner_promotion

LAYER7_JOB_NAMES: tuple[str, ...] = (
    "post_outcomes",
    "winner_promotion",
    "proposal_outcome",
    "human_edit_signal",
)

LAYER7_DAILY = 86400

_ALL_ACTIVE_BRANDS = ("swing-shack", "stick", "bag-drop")


def layer7_specs() -> list[JobSpec]:
    """Return all Layer 7 JobSpecs."""
    return [
        JobSpec(
            name="post_outcomes",
            fn=post_outcomes.run,
            every_seconds=LAYER7_DAILY,
            timeout_seconds=120,
            best_effort=True,
            criticality="MEDIUM",
            credentials=(),
            reads=(
                "ig-business-analytics.json",
                "post-conversion-score.json",
                "publish-sandbox/receipts.jsonl",
                "ga4-metrics.json",
            ),
            writes=("post-outcomes.json",),
            upstream=("meta_refresh", "post_conversion_score", "publish_dispatch"),
            brand_mode="per_brand",
            requires_integrations=("meta",),
        ),
        JobSpec(
            name="human_edit_signal",
            fn=human_edit_signal.run,
            every_seconds=LAYER7_DAILY,
            timeout_seconds=60,
            best_effort=True,
            criticality="LOW",
            credentials=(),
            reads=("human-edits.jsonl",),
            writes=("human-edit-summary.json",),
            upstream=(),
            brand_mode="per_brand",
            brands=_ALL_ACTIVE_BRANDS,
        ),
        JobSpec(
            name="winner_promotion",
            fn=winner_promotion.run,
            every_seconds=LAYER7_DAILY,
            timeout_seconds=60,
            best_effort=False,
            criticality="MEDIUM",
            credentials=(),
            reads=("post-outcomes.json", "human-edits.jsonl"),
            writes=("winning-recipes.json",),
            upstream=("post_outcomes", "human_edit_signal"),
            brand_mode="per_brand",
            brands=_ALL_ACTIVE_BRANDS,
        ),
        JobSpec(
            name="proposal_outcome",
            fn=proposal_outcome.run,
            every_seconds=LAYER7_DAILY,
            timeout_seconds=60,
            best_effort=True,
            criticality="LOW",
            credentials=(),
            reads=("proposals/pending.jsonl",),
            writes=("proposal-outcomes.json",),
            upstream=(),
            brand_mode="per_brand",
            brands=_ALL_ACTIVE_BRANDS,
        ),
    ]


def bootstrap_layer7(register: Callable[[JobSpec], None] | None = None) -> None:
    """Register all Layer 7 JobSpecs."""
    if register is None:
        from ..registry import register as register  # noqa: PLC0415

    for spec in layer7_specs():
        register(spec)
