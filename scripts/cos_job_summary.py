#!/usr/bin/env python3
"""Parse Campaign OS job-run API responses (single-run or ?all=1 fan-out)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def normalize_runs(data: dict[str, Any]) -> list[dict[str, Any]]:
    runs = data.get("runs")
    if isinstance(runs, list) and runs:
        return [r for r in runs if isinstance(r, dict)]
    return [data]


def summarize_runs(data: dict[str, Any]) -> dict[str, Any]:
    runs = normalize_runs(data)
    ok = all(bool(r.get("ok")) or r.get("status") == "SKIPPED" for r in runs)
    statuses = [str(r.get("status") or "?") for r in runs]
    return {
        "ok": ok,
        "top_ok": data.get("ok"),
        "run_count": len(runs),
        "statuses": statuses,
        "runs": runs,
    }


def print_summary(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = summarize_runs(data)
    runs = summary["runs"]
    if len(runs) == 1:
        run = runs[0]
        print(
            f"ok={run.get('ok')} status={run.get('status', '?')} "
            f"run_id={run.get('run_id', '?')} brand={run.get('brand', '-')}"
        )
        if run.get("rows") is not None:
            print(f"rows={run.get('rows')}")
        if run.get("duration_s") is not None:
            print(f"duration_s={run.get('duration_s')}")
    else:
        print(
            f"ok={summary['top_ok']} runs={summary['run_count']} "
            f"statuses={','.join(summary['statuses'])}"
        )
        for run in runs:
            print(
                f"  brand={run.get('brand', '-')} ok={run.get('ok')} "
                f"status={run.get('status', '?')} run_id={run.get('run_id', '?')}"
            )
    return 0


def assert_ok(path: Path, *, hard_gate: bool) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = normalize_runs(data)
    failures: list[str] = []
    for run in runs:
        status = str(run.get("status") or "").upper()
        if status == "SKIPPED":
            continue
        if run.get("ok") is True or status == "OK":
            continue
        brand = run.get("brand") or "-"
        failures.append(f"brand={brand} status={status} error={run.get('error', '?')}")
    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        return 1 if hard_gate else 0
    if hard_gate and not runs:
        print("no runs in response", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    print_p = sub.add_parser("print", help="Print human-readable job summary")
    print_p.add_argument("path", type=Path)

    assert_p = sub.add_parser("assert-ok", help="Exit non-zero when a non-SKIPPED run failed")
    assert_p.add_argument("path", type=Path)
    assert_p.add_argument(
        "--hard-gate",
        action="store_true",
        help="Treat any non-SKIPPED failure as exit 1 (cron hard gates)",
    )

    args = parser.parse_args(argv)
    if args.cmd == "print":
        return print_summary(args.path)
    if args.cmd == "assert-ok":
        return assert_ok(args.path, hard_gate=args.hard_gate)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
