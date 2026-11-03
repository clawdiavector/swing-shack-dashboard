"""Resolve writable DATA_DIR without touching committed repo data/."""
from __future__ import annotations

import os
from pathlib import Path

_SEED_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


def points_at_repo_seed_data(path: Path) -> bool:
    try:
        resolved = path.resolve()
        seed = _SEED_DATA_ROOT.resolve()
        return resolved == seed or seed in resolved.parents
    except OSError:
        return False


def runtime_data_dir() -> Path:
    configured = Path(os.environ.get("DATA_DIR", "/data/campaign-os"))
    if points_at_repo_seed_data(configured):
        scratch = os.environ.get("COS_CHECK_SCRATCH") or os.environ.get("COS_RUNTIME_DATA")
        base = Path(scratch) if scratch else Path("/tmp/cos-runtime-data")
        base.mkdir(parents=True, exist_ok=True)
        return base
    return configured


def ensure_writable_data_dir_env() -> None:
    """Point DATA_DIR at scratch storage when it targets committed repo data/."""
    raw = os.environ.get("DATA_DIR")
    if not raw or not points_at_repo_seed_data(Path(raw)):
        return
    scratch = os.environ.get("COS_CHECK_SCRATCH") or os.environ.get("COS_RUNTIME_DATA")
    base = Path(scratch) if scratch else Path("/tmp/cos-runtime-data")
    base.mkdir(parents=True, exist_ok=True)
    os.environ["DATA_DIR"] = str(base)


ensure_writable_data_dir_env()
