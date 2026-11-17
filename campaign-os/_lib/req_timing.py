"""Per-request section timings, sent as a Server-Timing header (17 Nov 2026).

Wrap a request in timings(); any code under it can add a section with timed(name).
Outside timings() a timed block costs a clock read and records nothing."""
from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar

_TIMINGS: "ContextVar[dict[str, float] | None]" = ContextVar("clean_cal_timings", default=None)


@contextmanager
def timings():
    """Collect section times for one month build; yields the dict (name -> ms)."""
    token = _TIMINGS.set({})
    try:
        yield _TIMINGS.get()
    finally:
        _TIMINGS.reset(token)


@contextmanager
def timed(name: str):
    """Add this block's time to the current month build's timings, if one is collecting."""
    store = _TIMINGS.get()
    start = time.perf_counter()
    try:
        yield
    finally:
        if store is not None:
            store[name] = store.get(name, 0.0) + (time.perf_counter() - start) * 1000


def server_timing(store: dict[str, float]) -> str:
    """The Server-Timing header value: shows per section in the browser's Network tab."""
    return ", ".join(f"{k};dur={v:.0f}" for k, v in store.items())
