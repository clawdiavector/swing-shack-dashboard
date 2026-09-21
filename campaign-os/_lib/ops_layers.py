"""Ops layer rollup for GET /api/ops/layers — pure functions, no Flask."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from _lib.ops_watch import derive_watch_verdict

VERDICT_RANK = {"OK": 0, "LATE": 1, "STUCK": 2, "FAILED": 3, "NEVER": 4}
VALID_VERDICTS = frozenset(VERDICT_RANK)
ROLLUP_EXCLUDED = frozenset({"DISABLED", "SKIPPED"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def worst_verdict(verdicts: list[str]) -> str:
    """Worst verdict across a list using OK < LATE < STUCK < FAILED < NEVER."""
    if not verdicts:
        return "NEVER"
    return max(verdicts, key=lambda v: VERDICT_RANK.get(str(v).upper(), -1))


def count_verdicts(jobs: list[dict]) -> dict[str, int]:
    """Count jobs by verdict for L1 digest chips."""
    counts = {
        "ok": 0,
        "late": 0,
        "stuck": 0,
        "failed": 0,
        "never": 0,
        "disabled": 0,
        "skipped": 0,
    }
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
        elif v == "DISABLED":
            counts["disabled"] += 1
        elif v == "SKIPPED":
            counts["skipped"] += 1
        else:
            counts["never"] += 1
    return counts


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _parse_iso(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_learn_stats() -> dict[str, Any]:
    """Roll up L7 Learn tab metrics from flat $DATA_DIR JSON outputs."""
    root = _data_dir()
    recipes_doc = _read_json_file(root / "winning-recipes.json")
    outcomes_doc = _read_json_file(root / "post-outcomes.json")
    edits_doc = _read_json_file(root / "human-edit-summary.json")
    proposals_doc = _read_json_file(root / "proposal-outcomes.json")

    recipes = int(recipes_doc.get("winners") or len(recipes_doc.get("recipes") or []))
    samples = int(recipes_doc.get("samples") or outcomes_doc.get("posts_total") or 0)
    ready = bool(recipes_doc.get("ready"))
    last_recipe_at = str(recipes_doc.get("generated_at") or "")
    score_basis = str(recipes_doc.get("score_basis") or outcomes_doc.get("score_basis") or "engagement_only")
    confidence = str(recipes_doc.get("confidence") or "weak_prior")

    gate = proposals_doc.get("gate") if isinstance(proposals_doc.get("gate"), dict) else {}
    gate_verdict = str(gate.get("verdict") or "insufficient_data")

    verdict = "NEVER"
    if gate_verdict == "fail":
        verdict = "FAILED"
    elif ready and recipes > 0:
        verdict = "OK"
    elif samples > 0 or int(edits_doc.get("rows") or 0) > 0:
        verdict = "LATE"

    return {
        "recipes": recipes,
        "winners": recipes,
        "samples": samples,
        "ready": ready,
        "last_recipe_at": last_recipe_at or None,
        "score_basis": score_basis,
        "confidence": confidence,
        "edit_rows": int(edits_doc.get("rows") or 0),
        "edit_rate": edits_doc.get("edit_rate"),
        "proposal_gate": gate_verdict,
        "verdict": verdict,
        "href": "/ops?layer=learn",
    }


def build_learn_summary() -> dict[str, Any]:
    """Full Learn summary payload for GET /api/ops/learn/summary."""
    stats = load_learn_stats()
    root = _data_dir()
    recipes_doc = _read_json_file(root / "winning-recipes.json")
    outcomes_doc = _read_json_file(root / "post-outcomes.json")
    edits_doc = _read_json_file(root / "human-edit-summary.json")
    proposals_doc = _read_json_file(root / "proposal-outcomes.json")

    top_movers = []
    for row in (outcomes_doc.get("outcomes") or [])[:5]:
        if isinstance(row, dict):
            top_movers.append({
                "post_id": row.get("post_id"),
                "hook_id": row.get("hook_id"),
                "score": row.get("score"),
                "rank": row.get("rank"),
                "join_basis": row.get("join_basis"),
            })

    return {
        "schema": "campaign-os/ops-learn-summary/v1",
        "generated_at": _utc_now_iso(),
        "headline": stats,
        "winning_recipes": recipes_doc,
        "post_outcomes": {
            "posts_total": outcomes_doc.get("posts_total"),
            "score_basis": outcomes_doc.get("score_basis"),
            "top_movers": top_movers,
        },
        "human_edits": edits_doc,
        "proposal_gate": proposals_doc.get("gate"),
    }


def load_create_stats() -> dict[str, Any]:
    """Roll up L5 Create tab metrics from $DATA_DIR draft sidecars."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    drafts_today = 0
    last_draft_at: str | None = None
    qc_failed = 0

    draft_dir = _data_dir() / "draft-assets"
    if draft_dir.is_dir():
        for path in draft_dir.glob("*.json"):
            try:
                sidecar = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(sidecar, dict):
                continue
            created = str(sidecar.get("created_at") or "")
            if created.startswith(today):
                drafts_today += 1
            if created and (last_draft_at is None or created > last_draft_at):
                last_draft_at = created

    qc_path = _data_dir() / "asset-qc.json"
    if qc_path.is_file():
        try:
            qc_doc = json.loads(qc_path.read_text(encoding="utf-8"))
            if isinstance(qc_doc, dict):
                qc_failed = int(qc_doc.get("failed") or 0)
        except (OSError, json.JSONDecodeError):
            pass

    spent_usd = 0.0
    cap_usd = 5.0
    at_cap = False
    near_cap = False
    try:
        from _lib import llm_spend  # noqa: PLC0415

        spend = llm_spend.status()
        spent_usd = float(spend.get("spent_usd") or 0)
        cap_usd = float(spend.get("cap_usd") or 5)
        at_cap = bool(spend.get("at_cap"))
        near_cap = bool(spend.get("near_cap"))
    except Exception:
        pass

    verdict = "NEVER"
    if at_cap or qc_failed > 0:
        verdict = "LATE"
    elif drafts_today > 0:
        verdict = "OK"

    return {
        "drafts_today": drafts_today,
        "last_draft_at": last_draft_at,
        "qc_failed": qc_failed,
        "spent_usd": spent_usd,
        "cap_usd": cap_usd,
        "at_cap": at_cap,
        "near_cap": near_cap,
        "verdict": verdict,
        "inbox_href": "/?page=review",
    }


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
    agents: Optional[list[dict]] = None,
    inbox: Optional[dict] = None,
    watch: Optional[dict] = None,
) -> dict[str, Any]:
    """Build campaign-os/ops-layers/v1 payload."""
    jobs = (jobs_status or {}).get("jobs") or []
    all_verdicts = [str(j.get("verdict") or "NEVER").upper() for j in jobs]
    job_verdicts = [v for v in all_verdicts if v not in ROLLUP_EXCLUDED]
    counts = count_verdicts(jobs)
    if job_verdicts:
        l1_verdict = worst_verdict(job_verdicts)
    elif all_verdicts:
        l1_verdict = "DISABLED" if "DISABLED" in all_verdicts else "SKIPPED"
    else:
        l1_verdict = "NEVER"

    rotten = int((freshness or {}).get("rotten") or 0)
    stale = int((freshness or {}).get("stale") or 0)
    depth = queue_depth(queue)
    l2_verdict = _health_verdict(l1_verdict, rotten=rotten, stale=stale)

    watch_verdict, watch_age_s = derive_watch_verdict(watch)

    l4_counts = inbox or {}
    l4_pending = int(l4_counts.get("pending") or 0)
    l4_stale = int(l4_counts.get("stale") or 0)
    l4_approved_today = int(l4_counts.get("approved_today") or 0)
    l4_verdict = str(l4_counts.get("verdict") or "NEVER")

    create_stats = load_create_stats()
    l5_verdict = str(create_stats.get("verdict") or "NEVER")
    learn_stats = load_learn_stats()
    l7_verdict = str(learn_stats.get("verdict") or "NEVER")

    stub_layers = [
        ("L6", "Publish", "publish", "L6 sandbox — publish_dispatch writes receipts; PUBLISH_MODE=live is Kyle gate."),
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
            "disabled": counts["disabled"],
            "skipped": counts["skipped"],
            "href": "/ops?layer=jobs",
        },
        "L2": {
            "label": "Health",
            "verdict": l2_verdict,
            "watch_verdict": watch_verdict,
            "watch_age_s": watch_age_s,
            "watch_all_ok": bool((watch or {}).get("all_ok")) if watch else None,
            "digest_source": "derived",
            "ok": counts["ok"],
            "late": counts["late"],
            "stuck": counts["stuck"],
            "failed": counts["failed"],
            "never": counts["never"],
            "disabled": counts["disabled"],
            "skipped": counts["skipped"],
            "rotten": rotten,
            "stale": stale,
            "queue_depth": depth,
            "href": "/ops?layer=health",
        },
    }

    l6_verdict = "NEVER"
    l6_extra: dict[str, Any] = {}
    try:
        from _lib.publish_mode import get_publish_mode
        from _lib.publish_sandbox import summary as sandbox_summary

        if get_publish_mode() == "sandbox":
            sb = sandbox_summary()
            ready = int(sb.get("queue_approved_ready") or 0)
            receipts = int(sb.get("receipt_count") or 0)
            l6_verdict = "OK" if receipts > 0 else ("LATE" if ready > 0 else "NEVER")
            l6_extra = {
                "mode": "sandbox",
                "queue_approved_ready": ready,
                "receipt_count": receipts,
                "last_receipt_at": sb.get("last_receipt_at"),
            }
    except Exception:
        pass

    if agents is None:
        layers["L3"] = {
            "label": "Agents",
            "verdict": "NEVER",
            "href": "/ops?layer=agents",
            "note": "L3 not built — Mac cos-* fleet and heartbeat API.",
        }
    else:
        roster = agents or []
        reporting = sum(1 for a in roster if a.get("last_heartbeat_at"))
        never = sum(1 for a in roster if str(a.get("last_status") or "NEVER").upper() == "NEVER")
        reporting_statuses = [
            str(a.get("last_status") or "NEVER").upper()
            for a in roster
            if a.get("last_heartbeat_at")
        ]
        l3_verdict = worst_verdict(reporting_statuses) if reporting_statuses else "NEVER"
        layers["L3"] = {
            "label": "Agents",
            "verdict": l3_verdict,
            "href": "/ops?layer=agents",
            "agents": len(roster),
            "reporting": reporting,
            "never": never,
        }

    layers["L4"] = {
        "label": "Approve",
        "verdict": l4_verdict,
        "href": "/ops?layer=approve",
        "pending": l4_pending,
        "stale": l4_stale,
        "approved_today": l4_approved_today,
        "inbox_href": "/?page=review",
    }

    layers["L5"] = {
        "label": "Create",
        "verdict": l5_verdict,
        "href": "/ops?layer=create",
        "drafts_today": create_stats.get("drafts_today", 0),
        "last_draft_at": create_stats.get("last_draft_at"),
        "qc_failed": create_stats.get("qc_failed", 0),
        "spent_usd": create_stats.get("spent_usd", 0),
        "cap_usd": create_stats.get("cap_usd", 5),
        "at_cap": create_stats.get("at_cap", False),
        "near_cap": create_stats.get("near_cap", False),
        "inbox_href": create_stats.get("inbox_href", "/?page=review"),
    }

    layers["L7"] = {
        "label": "Learn",
        "verdict": l7_verdict,
        "href": "/ops?layer=learn",
        "recipes": learn_stats.get("recipes", 0),
        "winners": learn_stats.get("winners", 0),
        "samples": learn_stats.get("samples", 0),
        "ready": learn_stats.get("ready", False),
        "last_recipe_at": learn_stats.get("last_recipe_at"),
        "score_basis": learn_stats.get("score_basis"),
        "confidence": learn_stats.get("confidence"),
        "edit_rows": learn_stats.get("edit_rows", 0),
        "proposal_gate": learn_stats.get("proposal_gate"),
    }

    for key, label, slug, note in stub_layers:
        entry: dict[str, Any] = {
            "label": label,
            "verdict": "NEVER",
            "href": f"/ops?layer={slug}",
            "note": note,
        }
        if key == "L6":
            entry["verdict"] = l6_verdict
            entry.update(l6_extra)
        layers[key] = entry

    return {
        "schema": "campaign-os/ops-layers/v1",
        "generated_at": _utc_now_iso(),
        "layers": layers,
    }
