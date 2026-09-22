"""Human-readable last-run outcomes for /ops/jobs (no raw JSON dumps)."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import ledger
from .registry import JOBS
from .diagnostics import _file_meta


def _data_dir() -> str:
    return os.environ.get("DATA_DIR") or "/data"


def summarize_result(result: Any) -> dict[str, Any]:
    """Safe subset of a job result dict for ledger storage."""
    if not isinstance(result, dict):
        return {}
    out: dict[str, Any] = {}
    if "ok" in result:
        out["ok"] = bool(result.get("ok"))
    for key in (
        "skipped",
        "reason",
        "rows",
        "ig_posts",
        "fb_posts",
        "fan_count",
        "partial",
        "total_files",
        "fresh_count",
        "stale_count",
        "rotten_count",
    ):
        if result.get(key) is not None:
            out[key] = result[key]
    err = result.get("error")
    if err:
        out["error"] = str(err)[:300]
    return out


def _json_highlights(rel: str, data: Any) -> list[str]:
    """Extract readable bullets from a known output file shape."""
    lines: list[str] = []
    if isinstance(data, list):
        lines.append(f"{len(data)} items in file")
        if data and isinstance(data[0], dict):
            sample = data[0]
            if "title" in sample:
                lines.append(f"Latest: {str(sample.get('title', ''))[:80]}")
        return lines
    if not isinstance(data, dict):
        return lines

    if "articles" in data and isinstance(data["articles"], list):
        lines.append(f"{len(data['articles'])} articles")
    elif "trends" in data and isinstance(data["trends"], list):
        lines.append(f"{len(data['trends'])} trends")
    elif "posts" in data and isinstance(data["posts"], list):
        lines.append(f"{len(data['posts'])} posts")
    elif "by_staleness" in data:
        bs = data["by_staleness"]
        if isinstance(bs, dict):
            lines.append(
                "fresh {fresh} · stale {stale} · rotten {rotten}".format(
                    fresh=bs.get("fresh", "?"),
                    stale=bs.get("stale", "?"),
                    rotten=bs.get("rotten", "?"),
                )
            )
        if data.get("total_files") is not None:
            lines.append(f"{data['total_files']} files scanned")
    elif "hooks" in data and isinstance(data["hooks"], list):
        lines.append(f"{len(data['hooks'])} hooks")
    elif "recommendations" in data and isinstance(data["recommendations"], list):
        lines.append(f"{len(data['recommendations'])} recommendations")
    else:
        keys = [k for k in data.keys() if not k.startswith("_")][:6]
        if keys:
            lines.append("Sections: " + ", ".join(keys))
    return lines


def inspect_output_file(rel: str) -> dict[str, Any]:
    """One output file with human highlights."""
    meta = _file_meta(rel)
    highlights: list[str] = []
    if meta.get("exists") and rel.endswith(".json"):
        path = os.path.join(_data_dir(), rel)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            highlights = _json_highlights(rel, data)
        except (OSError, json.JSONDecodeError):
            highlights = ["Could not parse JSON"]
    elif meta.get("exists") and rel.endswith("/"):
        try:
            count = len(os.listdir(os.path.join(_data_dir(), rel.rstrip("/"))))
            highlights = [f"{count} files in folder"]
        except OSError:
            pass
    return {
        "path": rel,
        "exists": meta.get("exists", False),
        "bytes": meta.get("bytes"),
        "age_h": meta.get("age_h"),
        "highlights": highlights,
    }


def _metrics_lines(summary: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if summary.get("ok") is True:
        lines.append("Run reported success.")
    elif summary.get("ok") is False:
        lines.append("Run reported failure.")
    if summary.get("rows") is not None:
        lines.append(f"Rows / records written: {summary['rows']}")
    if summary.get("ig_posts") is not None:
        lines.append(f"Instagram posts fetched: {summary['ig_posts']}")
    if summary.get("fb_posts") is not None:
        lines.append(f"Facebook posts fetched: {summary['fb_posts']}")
    if summary.get("fan_count") is not None:
        lines.append(f"Page fan count: {summary['fan_count']}")
    if summary.get("total_files") is not None:
        lines.append(f"Files scanned: {summary['total_files']}")
    for key in ("fresh_count", "stale_count", "rotten_count"):
        if summary.get(key) is not None:
            lines.append(f"{key.replace('_', ' ')}: {summary[key]}")
    if summary.get("partial"):
        lines.append("Partial success (some sources missing).")
    if summary.get("error"):
        lines.append(f"Error: {summary['error']}")
    return lines


def build_outcome(*, job: str, run_id: Optional[str] = None) -> dict[str, Any]:
    """Human-readable outcome for one finished run (or latest for job)."""
    spec = JOBS.get(job)
    if spec is None:
        return {"ok": False, "error": "unknown job"}

    rows = ledger.read_rows(job)
    finished = [r for r in rows if r.get("phase") == "finished" and r.get("run_id")]
    finished.sort(key=lambda r: r.get("finished") or r.get("started") or "", reverse=True)

    row: Optional[dict] = None
    if run_id:
        for r in finished:
            if r.get("run_id") == run_id:
                row = r
                break
        if row is None:
            return {"ok": False, "error": "run not found", "job": job, "run_id": run_id}
    elif finished:
        row = finished[0]
    else:
        return {"ok": False, "error": "no runs yet", "job": job}

    assert row is not None
    summary = row.get("result_summary") if isinstance(row.get("result_summary"), dict) else {}
    lines = _metrics_lines(summary)
    if not lines and row.get("status"):
        lines.append(f"Status: {row.get('status')}")
    if row.get("duration_s") is not None:
        lines.append(f"Duration: {row['duration_s']}s")

    files = [inspect_output_file(rel) for rel in (spec.writes or ())]
    for fmeta in files:
        if fmeta.get("highlights"):
            lines.append(f"{fmeta['path']}: " + "; ".join(fmeta["highlights"]))
        elif fmeta.get("exists"):
            age = fmeta.get("age_h")
            age_s = f"{age:.1f}h old" if age is not None else "updated"
            lines.append(f"{fmeta['path']}: {fmeta.get('bytes', '?')} bytes · {age_s}")

    headline = "OK" if row.get("status") == "OK" else str(row.get("status") or "?")
    if summary.get("rows") is not None and row.get("status") == "OK":
        headline = f"OK — {summary['rows']} records"

    return {
        "ok": True,
        "job": job,
        "run_id": row.get("run_id"),
        "status": row.get("status"),
        "started": row.get("started"),
        "finished": row.get("finished"),
        "triggered_by": row.get("triggered_by"),
        "headline": headline,
        "lines": lines,
        "files": files,
        "metrics": summary,
    }
