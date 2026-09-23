"""Per-job manual Run-now cooldown (t44) — independent of CAMPAIGN_OS_PRODUCTION.

In-memory + lock. Resets on process restart (acceptable; stated in RFT).
Window: min(every_seconds, 300) seconds per (job name, brand lane).
"""

from __future__ import annotations

import threading
import time
from typing import Optional

_LOCK = threading.Lock()
_LAST: dict[tuple[str, str], float] = {}  # (job_name, brand or "") -> monotonic ts
_DEFAULT_CAP_S = 300.0


def _key(job_name: str, brand: str | None = None) -> tuple[str, str]:
    name = (job_name or "").strip()
    lane = (brand or "").strip()
    return name, lane


def window_s(every_seconds: Optional[float] = None) -> float:
    try:
        every = float(every_seconds) if every_seconds is not None else _DEFAULT_CAP_S
    except (TypeError, ValueError):
        every = _DEFAULT_CAP_S
    if every <= 0:
        every = _DEFAULT_CAP_S
    return min(every, _DEFAULT_CAP_S)


def check(
    job_name: str,
    every_seconds: Optional[float] = None,
    *,
    brand: str | None = None,
) -> tuple[bool, float]:
    """Return (allowed, retry_after_s)."""
    key = _key(job_name, brand)
    if not key[0]:
        return True, 0.0
    win = window_s(every_seconds)
    now = time.monotonic()
    with _LOCK:
        last = _LAST.get(key)
        if last is None:
            return True, 0.0
        elapsed = now - last
        if elapsed >= win:
            return True, 0.0
        return False, round(win - elapsed, 3)


def mark(job_name: str, *, brand: str | None = None) -> None:
    key = _key(job_name, brand)
    if not key[0]:
        return
    with _LOCK:
        _LAST[key] = time.monotonic()


def reset_for_tests() -> None:
    with _LOCK:
        _LAST.clear()
