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


def is_path_allowed(job: str, rel: str) -> bool:
    """True if rel is listed in the job's writes (exact file or under a write dir)."""
    spec = JOBS.get(job)
    if spec is None:
        return False
    norm = _normalize_rel(rel)
    for allowed in spec.writes or ():
        allowed_raw = (allowed or "").strip().replace("\\", "/")
        is_dir = allowed_raw.endswith("/")
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
    for rel in spec.writes or ():
        rel_norm = _normalize_rel(rel)
        path = os.path.join(base, rel_norm)
        if rel_norm.endswith("/"):
            entries: list[str] = []
            if os.path.isdir(path):
                try:
                    entries = sorted(
                        f"{rel_norm}{name}"
                        for name in os.listdir(path)
                        if name.endswith(".json")
                    )[:200]
                except OSError:
                    entries = []
            out.append({"path": rel_norm, "kind": "directory", "entries": entries})
        else:
            exists = os.path.isfile(path)
            size = os.path.getsize(path) if exists else None
            out.append(
                {
                    "path": rel_norm,
                    "kind": "file",
                    "exists": exists,
                    "bytes": size,
                    "viewable": exists and rel_norm.endswith(".json"),
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
