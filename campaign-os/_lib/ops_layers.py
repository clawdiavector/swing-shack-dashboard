"""Ops layer rollup for GET /api/ops/layers — pure functions, no Flask."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

VERDICT_RANK = {"OK": 0, "LATE": 1, "STUCK": 2, "FAILED": 3, "NEVER": 4}
VALID_VERDICTS = frozenset(VERDICT_RANK)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def worst_verdict(verdicts: list[str]) -> str:
    """Worst verdict across a list using OK < LATE < STUCK < FAILED < NEVER."""
    if not verdicts:
        return "NEVER"
    return max(verdicts, key=lambda v: VERDICT_RANK.get(str(v).upper(), 4))


def count_verdicts(jobs: list[dict]) -> dict[str, int]:
    """Count jobs by verdict for L1 digest chips."""
    counts = {"ok": 0, "late": 0, "stuck": 0, "failed": 0, "never": 0}
    for job in jobs:
        v = str(job.get("verdict") or "NEVER").upper()
        if v == "OK":
            counts["ok"] += 1
        elif v == "LATE":
            counts["late"] += 1
        elif v == "STUCK":
            counts["stuck"] += 1
        elif v == "FAILED":
            counts["failed"] += 1
        else:
            counts["never"] += 1
    return counts


def queue_depth(queue: Optional[dict | list]) -> int:
    """Count pending rows in agent-queue.json; missing file → 0."""
    if queue is None:
        return 0
    if isinstance(queue, list):
        rows = queue
    elif isinstance(queue, dict):
        rows = queue.get("rows")
        if rows is None and "id" in queue:
            rows = [queue]
        rows = rows or []
    else:
        return 0
    if not isinstance(rows, list):
        return 0
    return sum(
        1
        for row in rows
        if isinstance(row, dict) and str(row.get("status") or "").lower() == "pending"
    )


def _health_verdict(job_worst: str, *, rotten: int, stale: int) -> str:
    """L2 verdict from job rollup plus freshness signals."""
    verdict = job_worst
    if rotten > 0:
        verdict = worst_verdict([verdict, "FAILED" if rotten >= 5 else "LATE"])
    elif stale > 0:
        verdict = worst_verdict([verdict, "LATE"])
    return verdict


def build_layers(
    jobs_status: dict,
    *,
    freshness: Optional[dict] = None,
    queue: Optional[dict | list] = None,
) -> dict[str, Any]:
    """Build campaign-os/ops-layers/v1 payload."""
    jobs = (jobs_status or {}).get("jobs") or []
    job_verdicts = [str(j.get("verdict") or "NEVER").upper() for j in jobs]
    counts = count_verdicts(jobs)
    l1_verdict = worst_verdict(job_verdicts)

    rotten = int((freshness or {}).get("rotten") or 0)
    stale = int((freshness or {}).get("stale") or 0)
    depth = queue_depth(queue)
    l2_verdict = _health_verdict(l1_verdict, rotten=rotten, stale=stale)

    stub_layers = [
        ("L3", "Agents", "agents", "L3 not built — Mac cos-* fleet and heartbeat API."),
        ("L4", "Approve", "approve", "L4 not built — unified inbox for Christelle."),
        ("L5", "Create", "create", "L5 not built — caption/image/GBP drafts after approve."),
        ("L6", "Publish", "publish", "L6 not built — Postiz dispatch after human_approved."),
        ("L7", "Learn", "learn", "L7 not built — outcomes feed recipes for L3/L5."),
    ]

    layers: dict[str, dict] = {
        "L1": {
            "label": "Jobs",
            "verdict": l1_verdict,
            "ok": counts["ok"],
            "late": counts["late"],
            "stuck": counts["stuck"],
            "failed": counts["failed"],
            "never": counts["never"],
            "href": "/ops?layer=jobs",
        },
        "L2": {
            "label": "Health",
            "verdict": l2_verdict,
            "watch_verdict": "NEVER",
            "watch_age_s": None,
            "digest_source": "derived",
            "ok": counts["ok"],
            "late": counts["late"],
            "stuck": counts["stuck"],
            "failed": counts["failed"],
            "never": counts["never"],
            "rotten": rotten,
            "stale": stale,
            "queue_depth": depth,
            "href": "/ops?layer=health",
        },
    }

    for key, label, slug, note in stub_layers:
        layers[key] = {
            "label": label,
            "verdict": "NEVER",
            "href": f"/ops?layer={slug}",
            "note": note,
        }

    return {
        "schema": "campaign-os/ops-layers/v1",
        "generated_at": _utc_now_iso(),
        "layers": layers,
    }
