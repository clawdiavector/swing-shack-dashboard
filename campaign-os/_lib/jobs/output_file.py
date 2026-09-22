"""Read job output files from $DATA_DIR for /ops/jobs JSON inspection."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .registry import JOBS

MAX_BYTES = 2_000_000


def _data_dir() -> str:
    return os.environ.get("DATA_DIR") or "/data"


def _normalize_rel(rel: str) -> str:
    text = (rel or "").strip().replace("\\", "/").lstrip("/")
    parts = [p for p in text.split("/") if p and p != "."]
    if ".." in parts:
        raise ValueError("path traversal not allowed")
    return "/".join(parts)


def _brand_scope(spec) -> tuple[str, ...]:
    """Brands this per_brand job writes under — credential-independent."""
    if spec.brand_mode != "per_brand":
        return ()
    from .brand_lanes import partition_brands

    runnable, skipped = partition_brands(spec)
    return tuple(sorted(set(runnable) | set(skipped) | set(spec.brands)))


def _allowed_writes(spec) -> list[str]:
    """Flat writes plus their brand-resolved twins. Order: flat first, then brands."""
    out: list[str] = []
    for rel in spec.writes or ():
        is_dir = rel.endswith("/")
        norm = _normalize_rel(rel)
        out.append(norm + "/" if is_dir else norm)
        if spec.brand_mode == "per_brand" and rel not in spec.shared_writes:
            for brand in _brand_scope(spec):
                child = f"brands/{brand}/{norm}"
                out.append(child + "/" if is_dir else child)
    return out


def is_path_allowed(job: str, rel: str) -> bool:
    """True if rel is listed in the job's writes (exact file or under a write dir)."""
    spec = JOBS.get(job)
    if spec is None:
        return False
    norm = _normalize_rel(rel)
    for allowed in _allowed_writes(spec):
        is_dir = allowed.endswith("/")
        allowed_norm = _normalize_rel(allowed)
        if is_dir:
            if norm == allowed_norm or norm.startswith(allowed_norm + "/"):
                return True
        elif norm == allowed_norm:
            return True
    return False


def list_output_files(job: str) -> list[dict[str, Any]]:
    """Metadata for each declared write path (file or directory listing)."""
    spec = JOBS.get(job)
    if spec is None:
        return []
    out: list[dict[str, Any]] = []
    base = _data_dir()
    for rel_allowed in _allowed_writes(spec):
        is_dir = rel_allowed.endswith("/")
        rel_norm = _normalize_rel(rel_allowed)
        path = os.path.join(base, rel_norm)
        if is_dir:
            entries: list[str] = []
            if os.path.isdir(path):
                try:
                    prefix = rel_allowed
                    entries = sorted(
                        f"{prefix}{name}"
                        for name in os.listdir(path)
                        if name.endswith(".json")
                    )[:200]
                except OSError:
                    entries = []
            out.append({"path": rel_allowed, "kind": "directory", "entries": entries})
        else:
            exists = os.path.isfile(path)
            size = os.path.getsize(path) if exists else None
            out.append(
                {
                    "path": rel_allowed,
                    "kind": "file",
                    "exists": exists,
                    "bytes": size,
                    "viewable": exists and rel_allowed.endswith(".json"),
                }
            )
    return out


def read_output_file(*, job: str, rel: str) -> dict[str, Any]:
    """Load JSON (or directory listing) for an allowed job output path."""
    if not is_path_allowed(job, rel):
        return {"ok": False, "error": "path not allowed for job", "job": job, "path": rel}

    norm = _normalize_rel(rel)
    path = os.path.join(_data_dir(), norm)

    if norm.endswith("/") or os.path.isdir(path):
        if not os.path.isdir(path):
            return {"ok": False, "error": "directory missing", "job": job, "path": norm}
        try:
            names = sorted(n for n in os.listdir(path) if n.endswith(".json"))[:200]
        except OSError as exc:
            return {"ok": False, "error": str(exc)[:120], "job": job, "path": norm}
        return {
            "ok": True,
            "job": job,
            "path": norm,
            "kind": "directory",
            "entries": [f"{norm.rstrip('/')}/{n}" for n in names],
        }

    if not os.path.isfile(path):
        return {"ok": False, "error": "file missing", "job": job, "path": norm}

    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return {"ok": False, "error": str(exc)[:120], "job": job, "path": norm}

    if not norm.endswith(".json"):
        return {
            "ok": False,
            "error": "only .json files can be viewed",
            "job": job,
            "path": norm,
            "bytes": size,
        }

    truncated = size > MAX_BYTES
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_BYTES if truncated else size + 1)
    except OSError as exc:
        return {"ok": False, "error": str(exc)[:120], "job": job, "path": norm}

    try:
        text = raw.decode("utf-8")
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "error": f"invalid JSON: {exc}",
            "job": job,
            "path": norm,
            "bytes": size,
        }

    return {
        "ok": True,
        "job": job,
        "path": norm,
        "kind": "json",
        "bytes": size,
        "truncated": truncated,
        "data": data,
    }
