"""Append-only job-runs.jsonl under $DATA_DIR."""

from __future__ import annotations

import json
import os
import threading
from typing import Optional

_lock = threading.Lock()


def _ledger_path() -> str:
    base = os.environ.get("DATA_DIR") or "/data"
    return os.path.join(base, "job-runs.jsonl")


def append_row(row: dict) -> None:
    """Append one JSON object as a line. Creates DATA_DIR if needed."""
    path = _ledger_path()
    line = json.dumps(row, separators=(",", ":"), default=str) + "\n"
    with _lock:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)


def read_rows(job: Optional[str] = None) -> list[dict]:
    """Read ledger rows; optionally filter by job name. Missing file → []."""
    path = _ledger_path()
    if not os.path.isfile(path):
        return []
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if job is not None and row.get("job") != job:
                    continue
                out.append(row)
    except OSError:
        return []
    return out


def last_rows_per_job(job_names: list[str]) -> dict[str, list[dict]]:
    """Return all rows grouped by job for the given names (order preserved)."""
    wanted = set(job_names)
    grouped: dict[str, list[dict]] = {n: [] for n in job_names}
    for row in read_rows():
        name = row.get("job")
        if name in wanted:
            grouped[name].append(row)
    return grouped
