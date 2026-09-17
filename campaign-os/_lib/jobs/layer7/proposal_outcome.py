"""Proposal approval rate for interpreter quality gate → proposal-outcomes.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..layer1._io import atomic_write, utc_now_iso

OUTPUT = "proposal-outcomes.json"
SCHEMA = "campaign-os/proposal-outcomes/v1"
GATE_THRESHOLD_PCT = 60.0
GATE_MIN_SAMPLES = 10


def _data_dir() -> Path:
    return Path(__import__("os").environ.get("DATA_DIR", "/data"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows


def _gate_verdict(*, approved: int, rejected: int, min_samples: int, threshold_pct: float) -> dict[str, Any]:
    samples = approved + rejected
    if samples < min_samples:
        return {
            "threshold_pct": threshold_pct,
            "measured_pct": None,
            "verdict": "insufficient_data",
            "min_samples": min_samples,
            "samples": samples,
        }
    measured = round((approved / samples) * 100.0, 1) if samples else None
    verdict = "pass" if measured is not None and measured >= threshold_pct else "fail"
    return {
        "threshold_pct": threshold_pct,
        "measured_pct": measured,
        "verdict": verdict,
        "min_samples": min_samples,
        "samples": samples,
    }


def run() -> dict:
    """Aggregate proposal statuses into proposal-outcomes.json."""
    rows = _read_jsonl(_data_dir() / "proposals" / "pending.jsonl")
    approved = rejected = pending = 0
    for row in rows:
        status = str(row.get("status") or "pending").lower()
        if status == "approved":
            approved += 1
        elif status == "rejected":
            rejected += 1
        else:
            pending += 1

    gate = _gate_verdict(
        approved=approved,
        rejected=rejected,
        min_samples=GATE_MIN_SAMPLES,
        threshold_pct=GATE_THRESHOLD_PCT,
    )

    payload = {
        "schema": SCHEMA,
        "generated_at": utc_now_iso(),
        "generated_by": "layer7/proposal_outcome.py",
        "totals": {
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
            "rows": len(rows),
        },
        "gate": gate,
    }
    atomic_write(OUTPUT, payload)
    return {"ok": True, "rows": len(rows), "gate_verdict": gate.get("verdict")}
