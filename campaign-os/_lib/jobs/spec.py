"""JobSpec dataclass — no Flask / app.py imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class JobSpec:
    name: str
    fn: Callable[[], dict]  # no args; expected failures return ok:False, not raise
    every_seconds: int  # expected cadence; drives LATE
    timeout_seconds: int = 60
    best_effort: bool = False  # scrapers: break → LATE, never FAILED

    # t13: self-heal prerequisite fields (declared now, unused until P1.5)
    criticality: str = "MEDIUM"  # HIGH | MEDIUM | LOW
    retries: int = 0  # tier-0 retry count; 0 = no retry in P0
    heal_policy: str = "no_heal"
    credentials: tuple[str, ...] = field(default_factory=tuple)  # env var NAMES
    writes: tuple[str, ...] = field(default_factory=tuple)  # $DATA_DIR-relative paths
