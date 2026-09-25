#!/usr/bin/env python3
"""Read-only probe: list provider_job_id from draft image sidecars and Krea job status."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_OS = REPO_ROOT / "campaign-os"
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.krea_job_parse import parse_get_job_payload  # noqa: E402


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _collect_job_ids(root: Path) -> list[tuple[str, str, Path]]:
    rows: list[tuple[str, str, Path]] = []
    images_root = root / "draft-assets" / "images"
    if not images_root.is_dir():
        return rows
    for meta_path in images_root.glob("**/*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(meta, dict):
            continue
        job_id = meta.get("provider_job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            continue
        brand = str(meta.get("brand_id") or meta_path.parts[-3] if len(meta_path.parts) >= 3 else "")
        rows.append((job_id.strip(), brand, meta_path))
    return rows


def main() -> int:
    data_dir = _data_dir()
    entries = _collect_job_ids(data_dir)
    if not entries:
        print(f"No provider_job_id sidecars under {data_dir / 'draft-assets' / 'images'}")
        return 0

    try:
        from _lib import krea_mcp  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"Krea MCP unavailable: {exc}")
        return 1

    print(f"{'job_id':<36} {'brand':<16} {'status':<12} sidecar")
    print("-" * 100)
    for job_id, brand, meta_path in sorted(entries, key=lambda t: t[0]):
        status = "error"
        try:
            poll = krea_mcp.get_job(job_id)
            parsed = parse_get_job_payload(poll)
            status = str(parsed.get("status") or "unknown")
        except Exception as exc:  # noqa: BLE001
            status = f"err:{str(exc)[:40]}"
        rel = meta_path.relative_to(data_dir) if meta_path.is_relative_to(data_dir) else meta_path
        print(f"{job_id:<36} {brand:<16} {status:<12} {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
