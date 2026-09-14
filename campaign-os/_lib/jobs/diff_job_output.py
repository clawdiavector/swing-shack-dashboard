"""Normalise and diff job JSON outputs for Class A / Class B side-by-side (t30/t32).

Scoped under _lib/jobs so the implement job stays inside campaign-os/_lib/jobs/**.
Usage:
  python3 -m _lib.jobs.diff_job_output --job insights_hooks --js a.json --py b.json --out-dir /tmp/diff
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VOLATILE_KEYS = frozenset(
    {
        "updated",
        "generated",
        "fetched_at",
        "timestamp",
        "run_id",
        "duration_s",
    }
)


def strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: strip_volatile(v)
            for k, v in obj.items()
            if k not in VOLATILE_KEYS
        }
    if isinstance(obj, list):
        return [strip_volatile(x) for x in obj]
    return obj


def deep_diff(a: Any, b: Any, path: str = "") -> list[str]:
    diffs: list[str] = []
    if type(a) is not type(b):
        diffs.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
        return diffs
    if isinstance(a, dict):
        ak, bk = set(a), set(b)
        for k in sorted(ak - bk):
            diffs.append(f"{path}.{k}: missing in b")
        for k in sorted(bk - ak):
            diffs.append(f"{path}.{k}: missing in a")
        for k in sorted(ak & bk):
            diffs.extend(deep_diff(a[k], b[k], f"{path}.{k}"))
        return diffs
    if isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"{path}: len {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(deep_diff(x, y, f"{path}[{i}]"))
        return diffs
    if a != b:
        diffs.append(f"{path}: {a!r} != {b!r}")
    return diffs


def diff_files(js_path: Path, py_path: Path, out_dir: Path | None = None) -> dict:
    js_raw = json.loads(js_path.read_text(encoding="utf-8"))
    py_raw = json.loads(py_path.read_text(encoding="utf-8"))
    js_n = strip_volatile(js_raw)
    py_n = strip_volatile(py_raw)
    diffs = deep_diff(js_n, py_n, "$")
    result = {
        "schema": {
            "js_keys": sorted(js_raw.keys()) if isinstance(js_raw, dict) else None,
            "py_keys": sorted(py_raw.keys()) if isinstance(py_raw, dict) else None,
            "keys_equal": (
                isinstance(js_raw, dict)
                and isinstance(py_raw, dict)
                and set(js_raw) == set(py_raw)
            ),
        },
        "normalized_equal": len(diffs) == 0,
        "diff_count": len(diffs),
        "diffs": diffs[:200],
        "thresholds": {
            "volatile_keys_stripped": sorted(VOLATILE_KEYS),
            "acceptance": "byte-identical after normalisation (Class A)",
        },
    }
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "normalized-js.json").write_text(
            json.dumps(js_n, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (out_dir / "normalized-py.json").write_text(
            json.dumps(py_n, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (out_dir / "diff.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--js", required=True, type=Path)
    p.add_argument("--py", required=True, type=Path)
    p.add_argument("--out-dir", type=Path, default=None)
    args = p.parse_args(argv)
    out = args.out_dir or Path(f"/tmp/cos-p1b-diff-{args.job}")
    result = diff_files(args.js, args.py, out)
    print(json.dumps({"job": args.job, "out_dir": str(out), **{k: result[k] for k in ("normalized_equal", "diff_count", "schema")}}, indent=2))
    return 0 if result["normalized_equal"] else 1


if __name__ == "__main__":
    sys.exit(main())
