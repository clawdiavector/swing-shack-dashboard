"""Campaign OS job registry — thin wrappers around existing ETL, no new fetchers."""

from .diagnostics import read_bundle, write_bundle
from .errors import classify, fingerprint
from .registry import JOBS, register
from .outcome import build_outcome
from .runner import build_digest, build_history, build_status, run_job, verdict_for
from .spec import JobSpec
from .suggested_checks import checks_for

__all__ = [
    "JOBS",
    "JobSpec",
    "register",
    "run_job",
    "verdict_for",
    "build_status",
    "build_history",
    "build_outcome",
    "build_digest",
    "classify",
    "fingerprint",
    "checks_for",
    "write_bundle",
    "read_bundle",
]
