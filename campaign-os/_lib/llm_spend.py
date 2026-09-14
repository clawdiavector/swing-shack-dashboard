"""Per-day LLM spend counter + hard cap for generate routes (t50).

Plan shape (handoff §8.2): check BEFORE egress, record AFTER.
Env: CAMPAIGN_OS_DAILY_LLM_CAP_USD (default 5.00); alias COS_LLM_DAILY_CAP_USD.
Persistence: $DATA_DIR/llm-spend/<YYYY-MM-DD>.json (never repo data/).
Corrupt / unreadable counter → fail closed.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Optional

_LOCK = threading.Lock()

DEFAULT_CAP_USD = 5.0
DEFAULT_WARN_FRAC = 0.5
SCHEMA = "campaign-os/llm-spend/v1"

# Modelled USD when upstream reports 0 (OpenAI path) — t50-I.
MODELLED_IMAGE_USD = {
    "1024x1024": 0.04,
    "1024x1792": 0.08,
    "1792x1024": 0.08,
}
MODELLED_IMAGE_DEFAULT = 0.05


def _data_dir() -> str:
    return os.environ.get("DATA_DIR") or "/data"


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _day_path(day: Optional[str] = None) -> str:
    d = day or _utc_day()
    return os.path.join(_data_dir(), "llm-spend", f"{d}.json")


def _cap_usd() -> float:
    raw = (
        (os.environ.get("CAMPAIGN_OS_DAILY_LLM_CAP_USD") or "").strip()
        or (os.environ.get("COS_LLM_DAILY_CAP_USD") or "").strip()
    )
    if not raw:
        return DEFAULT_CAP_USD
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_CAP_USD


def modelled_image_cost(size: str = "1024x1024", n: int = 1) -> float:
    try:
        count = max(1, int(n or 1))
    except (TypeError, ValueError):
        count = 1
    unit = MODELLED_IMAGE_USD.get((size or "").strip(), MODELLED_IMAGE_DEFAULT)
    return round(unit * count, 6)


def _load_day(day: Optional[str] = None) -> dict[str, Any]:
    path = _day_path(day)
    if not os.path.isfile(path):
        # Migrate legacy single-file counter if present
        legacy = os.path.join(_data_dir(), "llm-spend.json")
        d = day or _utc_day()
        if os.path.isfile(legacy):
            try:
                with open(legacy, "r", encoding="utf-8") as f:
                    old = json.load(f)
                entry = (old.get("days") or {}).get(d) if isinstance(old, dict) else None
                if isinstance(entry, dict):
                    return {
                        "schema": SCHEMA,
                        "date": d,
                        "usd": float(entry.get("usd") or 0),
                        "calls": len(entry.get("events") or []),
                        "events": list(entry.get("events") or []),
                    }
            except (OSError, ValueError, TypeError):
                pass
        return {"schema": SCHEMA, "date": d, "usd": 0.0, "calls": 0, "events": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("llm-spend day file must be object")
        data.setdefault("schema", SCHEMA)
        data.setdefault("date", day or _utc_day())
        data.setdefault("usd", 0.0)
        data.setdefault("calls", 0)
        data.setdefault("events", [])
        if not isinstance(data["events"], list):
            raise ValueError("events must be list")
        return data
    except (OSError, ValueError, TypeError) as e:
        return {
            "schema": SCHEMA,
            "date": day or _utc_day(),
            "usd": 0.0,
            "calls": 0,
            "events": [],
            "broken": True,
            "error": str(e)[:120],
        }


def _save_day(data: dict[str, Any]) -> None:
    path = _day_path(data.get("date"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def today_spend() -> dict[str, Any]:
    with _LOCK:
        data = _load_day()
        if data.get("broken"):
            return {
                "date": _utc_day(),
                "usd": _cap_usd(),
                "calls": 0,
                "broken": True,
                "error": data.get("error"),
            }
        return {
            "date": data.get("date") or _utc_day(),
            "usd": float(data.get("usd") or 0),
            "calls": int(data.get("calls") or 0),
            "broken": False,
        }


def today_spent_usd() -> float:
    snap = today_spend()
    if snap.get("broken"):
        return _cap_usd() + 1.0
    try:
        return float(snap.get("usd") or 0)
    except (TypeError, ValueError):
        return _cap_usd() + 1.0


def status() -> dict[str, Any]:
    cap = _cap_usd()
    snap = today_spend()
    broken = bool(snap.get("broken"))
    spent = float(snap.get("usd") or 0) if not broken else cap
    remaining = 0.0 if broken else max(0.0, round(cap - spent, 4))
    warn_at = round(cap * DEFAULT_WARN_FRAC, 4)
    return {
        "ok": not broken,
        "broken": broken,
        "day": snap.get("date") or _utc_day(),
        "spent_usd": round(spent, 4),
        "cap_usd": cap,
        "remaining_usd": remaining,
        "warn_usd": warn_at,
        "calls": snap.get("calls") or 0,
        "at_cap": True if broken else (spent >= cap if cap > 0 else False),
        "near_cap": True if broken else (spent >= warn_at if cap > 0 else False),
    }


def check(kind: str, est_usd: float = 0.0) -> tuple[bool, str]:
    """Pre-flight. Returns (allowed, reason)."""
    with _LOCK:
        data = _load_day()
        if data.get("broken"):
            return False, "budget state unreadable"
    cap = _cap_usd()
    if cap <= 0:
        return False, "daily cap is zero"
    try:
        est = max(0.0, float(est_usd or 0.0))
    except (TypeError, ValueError):
        est = 0.0
    spent = today_spent_usd()
    if spent + est > cap:
        return False, f"daily cap would be exceeded ({spent:.4f}+{est:.4f}>{cap:.4f})"
    return True, "ok"


def can_afford(estimate_usd: float = 0.0) -> bool:
    ok, _ = check("generate", estimate_usd)
    return ok


def record(usd: float, *, route: str, model: Optional[str] = None, kind: str = "image") -> dict[str, Any]:
    """Post-flight accounting. Returns updated status()."""
    try:
        amount = max(0.0, float(usd or 0.0))
    except (TypeError, ValueError):
        amount = 0.0
    if amount <= 0:
        # Still count the call with modelled floor so OpenAI 0.0 is not free (t50-I).
        amount = MODELLED_IMAGE_DEFAULT
    day = _utc_day()
    with _LOCK:
        data = _load_day(day)
        if data.get("broken"):
            return status()
        try:
            data["usd"] = round(float(data.get("usd") or 0.0) + amount, 6)
        except (TypeError, ValueError):
            data["usd"] = amount
        events = data.get("events") if isinstance(data.get("events"), list) else []
        events.append(
            {
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "usd": round(amount, 6),
                "route": (route or "")[:120],
                "model": (model or "")[:80] or None,
                "kind": (kind or "image")[:40],
            }
        )
        data["events"] = events[-200:]
        data["calls"] = int(data.get("calls") or 0) + 1
        data["date"] = day
        try:
            _save_day(data)
        except OSError:
            pass
    return status()


def write_approval_receipt(*, route: str, estimate_usd: float, brand_id: Optional[str] = None) -> Optional[str]:
    """Dedicated gate receipt (plan §8.3 — governance brand_id gap → local receipt)."""
    try:
        root = os.path.join(_data_dir(), "receipts")
        os.makedirs(root, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(root, f"llm-generate-{ts}.json")
        payload = {
            "schema": "campaign-os/llm-generate-receipt/v1",
            "ts": ts,
            "route": (route or "")[:160],
            "brand_id": brand_id,
            "estimate_usd": float(estimate_usd or 0),
            "human_approved": True,
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
        return path
    except OSError:
        return None
