"""JobSpec dataclass — no Flask / app.py imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .brand_lanes import BRAND_MODE_UNSET


@dataclass(frozen=True)
class JobSpec:
    name: str
    fn: Callable[..., dict]  # per_brand jobs may accept brand= kwarg
    every_seconds: int  # expected cadence; drives LATE
    timeout_seconds: int = 60
    best_effort: bool = False  # scrapers: break → LATE, never FAILED
    enabled: bool = True  # False → cron/manual skip; verdict DISABLED

    # t13: self-heal prerequisite fields (declared now, unused until P1.5)
    criticality: str = "MEDIUM"  # HIGH | MEDIUM | LOW
    retries: int = 0  # declared; inert until t35 (runner has no retry loop yet)
    heal_policy: str = "no_heal"
    credentials: tuple[str, ...] = field(default_factory=tuple)  # env var NAMES
    writes: tuple[str, ...] = field(default_factory=tuple)  # $DATA_DIR-relative paths

    # t29/t30: declarative inputs + upstream graph (scheduler ignores until t37)
    reads: tuple[str, ...] = field(default_factory=tuple)  # $DATA_DIR-relative inputs
    upstream: tuple[str, ...] = field(default_factory=tuple)  # job names that should run first

    # P1a: brand lanes — must be set explicitly on every registered job (no default).
    brand_mode: str = BRAND_MODE_UNSET
    brands: tuple[str, ...] = ()
    requires_integrations: tuple[str, ...] = ()
    shared_writes: tuple[str, ...] = field(default_factory=tuple)
    shared_reads: tuple[str, ...] = field(default_factory=tuple)
