"""Campaign OS job registry — thin wrappers around existing ETL, no new fetchers."""

from .registry import JOBS, register
from .runner import build_digest, build_status, run_job, verdict_for
from .spec import JobSpec

__all__ = [
    "JOBS",
    "JobSpec",
    "register",
    "run_job",
    "verdict_for",
    "build_status",
    "build_digest",
]
