"""Shared DATA_DIR I/O for Layer 1 insight jobs."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_flat_fallback_counts: dict[tuple[str | None, str | None, str], int] = {}


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data"))


def repo_root() -> Path:
    """Repository root (parent of campaign-os/)."""
    return Path(__file__).resolve().parents[4]


def _fallback_brand() -> str:
    from ..brand_lanes import load_brands_registry

    reg = load_brands_registry()
    return str(reg.get("default_brand_id") or "swing-shack")


def resolve_brand_domain(brand: str | None) -> tuple[str | None, str | None]:
    """Return (hostname, error). Non-default brands require BRAND_DOMAIN_<BRAND>."""
    from ..brand_lanes import _brand_safe

    bid = brand or _fallback_brand()
    safe = _brand_safe(bid)
    explicit = os.environ.get(f"BRAND_DOMAIN_{safe}", "").strip()
    if explicit:
        host = explicit.removeprefix("https://").removeprefix("http://").rstrip("/")
        return host, None
    default_bid = _fallback_brand()
    if bid != default_bid:
        return None, f"BRAND_DOMAIN_{safe} not set"
    legacy = os.environ.get("SWING_SHACK_DOMAIN", "swingshack.co.za").strip()
    if not legacy:
        return None, "SWING_SHACK_DOMAIN not set"
    host = legacy.removeprefix("https://").removeprefix("http://").rstrip("/")
    return host, None


def flat_fallback_counts() -> dict[str, int]:
    """Return flat-fallback hit counts keyed by job:brand:file."""
    return {f"{job or '?'}:{brand or '?'}:{name}": n for (job, brand, name), n in _flat_fallback_counts.items()}


def reset_flat_fallback_counts() -> None:
    _flat_fallback_counts.clear()


def _count_flat_fallback(job_name: str | None, brand: str | None, name: str) -> None:
    key = (job_name, brand, name)
    _flat_fallback_counts[key] = _flat_fallback_counts.get(key, 0) + 1


def _load_json_path(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def read_json(
    name: str,
    *,
    brand: str | None = None,
    spec=None,
    allow_flat_fallback: bool = True,
) -> dict | list | None:
    resolved = name
    if spec is not None and brand is not None:
        from ..brand_lanes import resolve_path

        resolved = resolve_path(spec, name, brand)

    path = data_dir() / resolved
    loaded = _load_json_path(path)
    if loaded is not None:
        return loaded

    if (
        allow_flat_fallback
        and os.environ.get("COS_FLAT_FALLBACK", "1") != "0"
        and spec is not None
        and brand is not None
        and resolved != name
        and brand == _fallback_brand()
    ):
        flat = data_dir() / name
        loaded = _load_json_path(flat)
        if loaded is not None:
            _count_flat_fallback(getattr(spec, "name", None), brand, name)
            return loaded

    return None


@dataclass(frozen=True)
class BrandIO:
    spec: Any
    brand: str | None

    def read(self, name: str, *, allow_flat_fallback: bool = True) -> dict | list | None:
        return read_json(
            name,
            brand=self.brand,
            spec=self.spec,
            allow_flat_fallback=allow_flat_fallback,
        )

    def write(self, name: str, obj: Any) -> bool:
        return atomic_write(name, obj, brand=self.brand, spec=self.spec)


def io_for_job(job_name: str, brand: str | None) -> BrandIO:
    from ..registry import JOBS

    return BrandIO(JOBS.get(job_name), brand)


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


def atomic_write(name: str, obj: Any, *, brand: str | None = None, spec=None) -> bool:
    """Write JSON atomically; skip when COS_JOB_CANCEL=1."""
    if os.environ.get("COS_JOB_CANCEL") == "1":
        return False

    if spec is not None and brand is not None:
        from ..brand_lanes import resolve_path

        name = resolve_path(spec, name, brand)
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
