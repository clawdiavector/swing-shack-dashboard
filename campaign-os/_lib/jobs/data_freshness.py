"""How old the data a job writes is, so "OK" can be checked against it (audit, 3 Nov 2026).

ga4_report and meta_refresh said OK while Reach showed GA4 46 days old and Instagram 14.
A job's data age is the newest timestamp inside the files it writes (FRESHNESS_TS_KEYS),
or the file's own date when it has none.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .freshness_heuristic import parse_ts, walk_timestamps

# Stale when older than this many runs, and never under the floor (a missed day is not news).
RUNS_ALLOWED = 3
FLOOR_DAYS = 2.0


def _newest_ms(path: Path) -> Optional[float]:
    try:
        parsed: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        parsed = None
    hits: list[Any] = []
    if isinstance(parsed, (dict, list)):
        walk_timestamps(parsed, hits)
    stamps = [ms for ms in (parse_ts(h) for h in hits) if ms is not None]
    if stamps:
        return max(stamps)
    try:
        return os.path.getmtime(path) * 1000.0
    except OSError:
        return None


def newest_data(writes: tuple[str, ...], data_dir: str | os.PathLike[str], *, now: Optional[datetime] = None) -> Optional[dict]:
    """{file, newest_at, age_days} for the freshest file the job writes, or None if none exist."""
    now = now or datetime.now(timezone.utc)
    best: Optional[tuple[float, str]] = None
    for rel in writes:
        path = Path(data_dir) / rel
        if not path.is_file():
            continue
        ms = _newest_ms(path)
        if ms is not None and (best is None or ms > best[0]):
            best = (ms, rel)
    if best is None:
        return None
    ms, rel = best
    newest = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    age_days = max(0.0, round((now - newest).total_seconds() / 86400.0, 1))
    return {"file": rel, "newest_at": newest.strftime("%Y-%m-%dT%H:%M:%SZ"), "age_days": age_days}


def is_data_stale(verdict: str, every_seconds: Optional[int], data: Optional[dict]) -> bool:
    """OK job whose newest data is older than RUNS_ALLOWED runs (at least FLOOR_DAYS)."""
    if verdict != "OK" or not data:
        return False
    run_days = (every_seconds or 86400) / 86400.0
    return float(data.get("age_days") or 0) > max(RUNS_ALLOWED * run_days, FLOOR_DAYS)
