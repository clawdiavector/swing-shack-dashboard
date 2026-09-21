"""Campaign OS watchdog heartbeat — L2 watch_verdict on /api/ops/layers."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA = "campaign-os/watch-heartbeat/v1"
SUBDIR = "ops"
FILENAME = "campaign-os-watch-heartbeat.json"
DEFAULT_EVERY_S = 900  # campaign-os-watch Hermes cron: every 15m


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    text = str(ts).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _age_seconds(ts: str | None) -> float | None:
    parsed = _parse_iso(ts)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def heartbeat_path(data_dir: Path) -> Path:
    """Path to persisted watchdog heartbeat under DATA_DIR."""
    return data_dir / SUBDIR / FILENAME


def normalise_heartbeat(body: dict[str, Any]) -> dict[str, Any]:
    """Validate POST body from campaign-os-watch; raises ValueError on bad input."""
    if not isinstance(body, dict):
        raise ValueError("body must be an object")
    all_ok = bool(body.get("all_ok"))
    jobs_total = int(body.get("jobs_total") or 0)
    jobs_ok = int(body.get("jobs_ok") or 0)
    if jobs_ok > jobs_total:
        jobs_ok = jobs_total
    received_at = _utc_now_iso()
    return {
        "schema": SCHEMA,
        "source": "campaign-os-watch",
        "all_ok": all_ok,
        "jobs_total": max(0, jobs_total),
        "jobs_ok": max(0, jobs_ok),
        "received_at": received_at,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def write_heartbeat(data_dir: Path, hb: dict[str, Any]) -> dict[str, Any]:
    """Persist watchdog heartbeat to $DATA_DIR/ops/campaign-os-watch-heartbeat.json."""
    path = heartbeat_path(data_dir)
    _atomic_write_json(path, hb)
    return hb


def read_heartbeat(data_dir: Path) -> Optional[dict[str, Any]]:
    """Read last watchdog heartbeat; None if missing or unreadable."""
    path = heartbeat_path(data_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def derive_watch_verdict(
    hb: Optional[dict[str, Any]],
    *,
    every_s: int = DEFAULT_EVERY_S,
) -> tuple[str, float | None]:
    """Map heartbeat to watch_verdict + watch_age_s for L2 ribbon."""
    if not hb:
        return "NEVER", None
    age = _age_seconds(hb.get("received_at"))
    if age is None:
        return "NEVER", None
    late_after = max(every_s * 1.5, every_s + 60)
    if age > late_after:
        return "LATE", age
    if not hb.get("all_ok"):
        return "FAILED", age
    return "OK", age
