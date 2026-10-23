"""Shared / not-for-us marks for Stories suggestions.

The idea cards and scout rows are not queue items, so nothing remembered that a
person had dealt with one. A mark is a key plus a state; the key carries the date
for an idea card (it comes back tomorrow) and the post link for a scout row (a
post you have shared or skipped never comes back).

One JSON file in DATA_DIR. Idea marks older than a week are dropped on write.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

STATES = ("shared", "skipped")
_TZ = ZoneInfo("Africa/Johannesburg")
_LOCK = threading.Lock()


class MarkError(ValueError):
    pass


def _path() -> str:
    return os.path.join(os.environ.get("DATA_DIR") or "/data/campaign-os", "story-marks.json")


def _load() -> dict:
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    path = _path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _norm_url(u: str) -> str:
    return u.replace("://www.", "://").rstrip("/")


def idea_key(brand: str, day: str, kind: str, feature: str) -> str:
    return f"idea|{brand}|{day}|{kind}|{feature}"


def post_key(url: str) -> str:
    return f"post|{_norm_url(url)}"


def read() -> dict[str, str]:
    """key -> state for every mark worth keeping."""
    return {k: v["state"] for k, v in _load().items() if isinstance(v, dict) and v.get("state") in STATES}


def set_mark(key: str, state: str) -> None:
    """state is shared, skipped, or clear (removes the mark, for Undo)."""
    if not key or not key.startswith(("idea|", "post|")):
        raise MarkError("key must start with idea| or post|")
    if state not in STATES + ("clear",):
        raise MarkError("state must be shared, skipped or clear")
    cutoff = (datetime.now(_TZ).date() - timedelta(days=7)).isoformat()
    with _LOCK:
        data = _load()
        data = {k: v for k, v in data.items() if not (k.startswith("idea|") and k.split("|")[2] < cutoff)}
        if state == "clear":
            data.pop(key, None)
        else:
            data[key] = {"state": state, "at": datetime.now(_TZ).isoformat(timespec="seconds")}
        _save(data)
