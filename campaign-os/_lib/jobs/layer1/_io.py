"""Shared DATA_DIR I/O for Layer 1 insight jobs."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data"))


def repo_root() -> Path:
    """Repository root (parent of campaign-os/)."""
    return Path(__file__).resolve().parents[4]


def read_json(name: str) -> dict | list | None:
    path = data_dir() / name
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def js_number(value: Any) -> Any:
    """Match Node JSON.stringify numeric encoding (whole floats → int)."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, dict):
        return {k: js_number(v) for k, v in value.items()}
    if isinstance(value, list):
        return [js_number(v) for v in value]
    return value


def fmt_num(value: Any) -> str:
    """Format numbers like JS template literals (`10` not `10.0`)."""
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return str(value)
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
        return str(f)
    except (TypeError, ValueError):
        return str(value)


def js_substring(text: str | None, length: int) -> str:
    """Match JS String.prototype.substring — length is UTF-16 code units."""
    if not text or length <= 0:
        return ""
    units = 0
    out: list[str] = []
    for ch in text:
        units += 2 if ord(ch) > 0xFFFF else 1
        if units > length:
            break
        out.append(ch)
    return "".join(out)


def atomic_write(name: str, obj: Any) -> bool:
    """Write JSON atomically; skip when COS_JOB_CANCEL=1."""
    if os.environ.get("COS_JOB_CANCEL") == "1":
        return False

    path = data_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            # Node JSON.stringify emits `0` not `0.0` — keep Class A diffs clean.
            json.dump(js_number(obj), fh, indent=2)
            fh.write("\n")
        os.replace(tmp_path, path)
        return True
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def as_dict(value: dict | list | None) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: dict | list | None) -> list:
    return value if isinstance(value, list) else []


def parse_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        if isinstance(value, str):
            cleaned = value.replace("%", "").strip()
            return float(cleaned) if cleaned else default
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def slug_id(text: str, limit: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:limit]


def empty_hook_bank() -> dict:
    return {
        "updated": utc_now_iso(),
        "total_hooks": 0,
        "cross_signal_sources": {
            "ig_weight": "60%",
            "youtube_weight": "20%",
            "reddit_weight": "20%",
            "youtube_videos_analyzed": 0,
            "reddit_trends_available": 0,
        },
        "output_buckets": {
            "proven_and_trending": [],
            "proven_only": [],
            "trending_to_test": [],
            "retire": [],
        },
        "watched_and_worked": [],
        "hook_formulas": [],
        "ab_winners": [],
        "youtube_signals_summary": None,
    }


def empty_youtube_hook_signals() -> dict:
    return {
        "fetched_at": utc_now_iso(),
        "source_file": "youtube-trends.json",
        "videos_analyzed": 0,
        "top_videos": [],
        "signals": {
            "recurring_phrases": [],
            "topic_clusters": {},
            "format_patterns": [],
            "urgency_score": 0,
            "urgency_language": [],
            "has_before_after": False,
            "before_after_examples": [],
            "has_mistake_fix": False,
            "mistake_fix_examples": [],
            "top_channels": [],
            "hook_templates": [],
        },
        "summary": {
            "dominant_topics": [],
            "dominant_formats": [],
            "top_template": None,
        },
    }
