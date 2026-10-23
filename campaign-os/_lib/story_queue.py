"""Story reposts — a short list of links to share to Instagram / Facebook Stories.

Someone finds a good post, sends the link to Foreman on Telegram, Foreman adds it
here, and the Today page shows it. A person can still open the link and use the
app's own "Share to story" button. Post sends a card we render through Postiz.
The source post is never downloaded.

One JSON file in DATA_DIR. Items stay open until marked done, so a link added late
in the day is still there tomorrow.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

BRANDS = ("swing-shack", "stick", "bag-drop")
_HOSTS = ("instagram.com", "instagr.am", "facebook.com", "fb.com", "fb.watch", "fb.me")
_TZ = ZoneInfo("Africa/Johannesburg")
_LOCK = threading.Lock()


class StoryError(ValueError):
    pass


def _path() -> str:
    return os.path.join(os.environ.get("DATA_DIR") or "/data/campaign-os", "story-queue.json")


def _now() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


def _load() -> list[dict]:
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save(items: list[dict]) -> None:
    path = _path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp, path)


def clean_url(raw: str) -> str:
    """Return the link without tracking parameters, or raise StoryError."""
    raw = (raw or "").strip()
    if not raw:
        raise StoryError("a link is required")
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not any(
        host == h or host.endswith("." + h) for h in _HOSTS
    ):
        raise StoryError("only Instagram and Facebook links can be added")
    host = host[4:] if host.startswith("www.") else host
    return urlunsplit(("https", host, parts.path.rstrip("/") or "/", "", ""))


def add(brand: str, url: str, note: str = "", added_by: str = "") -> tuple[dict, bool]:
    """Add a link. Returns (item, created); a link already open is returned, not duplicated."""
    if brand not in BRANDS:
        raise StoryError(f"brand must be one of {', '.join(BRANDS)}")
    link = clean_url(url)
    with _LOCK:
        items = _load()
        for it in items:
            if it["brand"] == brand and it["url"] == link and it["status"] == "open":
                return it, False
        item = {
            "id": uuid.uuid4().hex[:10],
            "brand": brand,
            "url": link,
            "note": (note or "").strip()[:280],
            "added_by": (added_by or "").strip()[:60],
            "added_at": _now(),
            "status": "open",
            "done_at": None,
        }
        items.append(item)
        _save(items)
    return item, True


def list_items(brand: str | None = None) -> dict:
    """Open items, plus what was finished today so the list doesn't look empty at 5pm."""
    today = datetime.now(_TZ).date().isoformat()
    items = [i for i in _load() if not brand or i["brand"] == brand]
    return {
        "open": [i for i in items if i["status"] == "open"],
        "done_today": [
            i for i in items if i["status"] == "done" and (i.get("done_at") or "").startswith(today)
        ],
    }


def get(item_id: str) -> dict:
    for it in _load():
        if it["id"] == item_id:
            return it
    raise KeyError(item_id)


def record_post(item_id: str, postiz_post_id: str) -> dict:
    """Mark a story done after Postiz accepts it."""
    posted = (postiz_post_id or "").strip()
    if not posted:
        raise StoryError("postiz post id is required")
    with _LOCK:
        items = _load()
        for it in items:
            if it["id"] == item_id:
                it["status"] = "done"
                it["done_at"] = _now()
                it["postiz_post_id"] = posted
                it["posted_via"] = "postiz"
                _save(items)
                return it
    raise KeyError(item_id)


def set_status(item_id: str, status: str) -> dict:
    if status not in ("open", "done"):
        raise StoryError("status must be open or done")
    with _LOCK:
        items = _load()
        for it in items:
            if it["id"] == item_id:
                it["status"] = status
                it["done_at"] = _now() if status == "done" else None
                _save(items)
                return it
    raise KeyError(item_id)
