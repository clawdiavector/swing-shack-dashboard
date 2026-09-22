"""Shared data freshness timestamp walk + staleness classify (Campaign OS)."""

from __future__ import annotations

import datetime
import os
from typing import Any, Iterator

STALE_DAYS = 14
FRESHNESS_SKIP_FILES = frozenset(
    {"freshness.json", "freshness-detail.json", "meta-auth-health.json"}
)
FRESHNESS_TS_KEYS = frozenset(
    {
        "generated",
        "lastUpdated",
        "last_run",
        "last_run_at",
        "last_check",
        "ts",
        "date",
        "saved_at",
        "published_at",
        "posted_at",
        "polled",
        "fetched_at",
        "updated_at",
        "created_at",
        "scanned_at",
        "synced_at",
        "checked_at",
        "detected_at",
        "analyzed_at",
        "snapshot_at",
    }
)
ARCHIVE_META_KEY = "_campaign_os_archive"


def is_archived_ignored(parsed: Any) -> bool:
    """True when JSON object is flagged to skip freshness / queue refresh."""
    if not isinstance(parsed, dict):
        return False
    block = parsed.get(ARCHIVE_META_KEY)
    return isinstance(block, dict) and block.get("ignored") is True


def walk_timestamps(node: Any, hits: list[Any], depth: int = 0) -> None:
    if depth > 8 or len(hits) > 80:
        return
    if isinstance(node, list):
        for v in node:
            walk_timestamps(v, hits, depth + 1)
        return
    if not isinstance(node, dict):
        return
    for k, v in node.items():
        if k in FRESHNESS_TS_KEYS and (isinstance(v, str) or isinstance(v, (int, float))):
            hits.append(v)
        if isinstance(v, (dict, list)):
            walk_timestamps(v, hits, depth + 1)


def parse_ts(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = float(value)
        if n > 1e11:
            return n
        if n > 1e9:
            return n * 1000.0
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000.0
        except (ValueError, TypeError):
            return None
    return None


def classify(
    parsed: Any,
    mtime_ts: float,
    *,
    stale_days: int = STALE_DAYS,
) -> tuple[str, str | None, Any, float | None]:
    """Return (staleness, newest_ts_iso, newest_raw, age_days). None fields for static/unknown."""
    if not isinstance(parsed, (dict, list)):
        return ("unknown", None, None, None)
    hits: list[Any] = []
    walk_timestamps(parsed, hits)
    if not hits:
        return ("static", None, None, None)
    newest_ms: float | None = None
    newest_raw: Any = None
    for h in hits:
        ms = parse_ts(h)
        if ms is None:
            continue
        if newest_ms is None or ms > newest_ms:
            newest_ms = ms
            newest_raw = h
    if newest_ms is None:
        return ("unknown", None, None, None)
    age_days = round((mtime_ts - newest_ms) / 86400000.0, 1)
    if age_days < 0:
        age_days = 0.0
    iso = (
        datetime.datetime.fromtimestamp(newest_ms / 1000.0, tz=datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    if age_days > stale_days * 3:
        staleness = "rotten"
    elif age_days > stale_days:
        staleness = "stale"
    else:
        staleness = "fresh"
    return (staleness, iso, newest_raw, age_days)


def _rel_under_archive(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/")
    return norm == "archive" or norm.startswith("archive/")


def walk_data_json_files(root: str | os.PathLike[str]) -> Iterator[tuple[str, str]]:
    """Yield (abs_path, rel_path) for every *.json under root (skips archive/ + skip list)."""
    root_s = os.fspath(root)
    if not root_s or not os.path.isdir(root_s):
        return
    for dirpath, dirs, files in os.walk(root_s):
        rel_dir = os.path.relpath(dirpath, root_s)
        if rel_dir == "archive" or rel_dir.startswith(f"archive{os.sep}"):
            dirs.clear()
            continue
        if rel_dir == ".":
            dirs[:] = [d for d in dirs if d != "archive"]
        for name in files:
            if not name.endswith(".json"):
                continue
            if name in FRESHNESS_SKIP_FILES:
                continue
            ap = os.path.join(dirpath, name)
            rp = os.path.relpath(ap, root_s)
            if _rel_under_archive(rp.replace("\\", "/")):
                continue
            yield ap, rp
