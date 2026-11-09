"""The review pack (2026-11-03): a no-login page where a client approves, rejects,
comments and uploads her own photos.

Christelle's ask, from Chantalle (MCM, a separate client): she cannot sign in to
Claude, so she needs a plain web link. Herman's calendar link (clean_calendar.py)
is the pattern, with three differences:

  - it is not tied to one of our brands: a pack is a folder of items, and the
    client's data never goes in git (DATA_DIR/review-packs/<id>/);
  - Approve and Reject only RECORD a decision. Nothing here schedules, sends or
    posts anything, and this module imports nothing that could;
  - the client can upload photos (images only, checked, re-encoded) and tag a
    comment as a copy edit or a design edit.

This module reads, writes and words. app.py owns the routes.

Requirement-Owner: Christelle
"""
from __future__ import annotations

import html
import io
import json
import os
import re
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCOPE = "review_pack"
MAX_AGE = 30 * 24 * 60 * 60

MAX_PACK_IMAGE_BYTES = 15 * 1024 * 1024
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOADS_PER_BATCH = 20
MAX_COMMENT_CHARS = 2000

KINDS = ("single", "choice", "carousel", "note")
STATES = ("approve", "reject", "hold")
CHOICES = ("A", "B", "C")
TAGS = ("general", "copy edit", "design edit")
ROLES = ("client", "us")

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,60}$")
_ITEM_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
_UPLOAD_NAME = re.compile(r"^up-[0-9a-f]{8,}\.(jpg|png)$")
_IMAGE_NAME = re.compile(r"^[a-z0-9-]+-\d+-v\d+\.(jpg|png|webp)$")


class NotFound(ValueError):
    """The pack, item or file is not there. The route answers 404 for this."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _root() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "review-packs"


def _pack_dir(pack_id: str) -> Path | None:
    if not isinstance(pack_id, str) or not _ID.match(pack_id):
        return None
    return _root() / pack_id


def _slug(text: str, fallback: str = "item") -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:40]
    return s or fallback


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _read_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _append_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── the link ────────────────────────────────────────────────────────────────


def mint_token(
    serializer: Any,
    pack_id: str,
    who: str = "Chantalle",
    *,
    uid: str | None = None,
    role: str | None = None,
) -> str:
    """A signed link for ONE pack. It cannot open anything else."""
    if get_pack(pack_id) is None:
        raise NotFound("that pack is not there")
    payload: dict[str, Any] = {
        "scope": SCOPE,
        "pack": pack_id,
        "who": (who or "Chantalle").strip()[:40],
        "v": 1,
    }
    if uid:
        payload["uid"] = str(uid).strip()[:80]
    if role:
        payload["role"] = str(role).strip()[:20]
    return serializer.dumps(payload)


def read_token(serializer: Any, token: str, *, max_age: int = MAX_AGE) -> dict[str, str] | None:
    """{"pack", "who"} for a good link to a pack that still exists; None for anything else."""
    if not token:
        return None
    try:
        payload = serializer.loads(token, max_age=max_age)
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("scope") != SCOPE:
        return None
    pack_id = payload.get("pack")
    if get_pack(pack_id) is None:
        return None
    out: dict[str, str] = {"pack": pack_id, "who": str(payload.get("who") or "Chantalle")}
    if payload.get("uid"):
        out["uid"] = str(payload["uid"])
    if payload.get("role"):
        out["role"] = str(payload["role"])
    return out


# ── packs ───────────────────────────────────────────────────────────────────


def _clean_item(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("each item must be an object")
    name = str(raw.get("title") or "").strip()
    if not name:
        raise ValueError("each item needs a title")
    item_id = _slug(raw.get("id") or name)
    if not _ITEM_ID.match(item_id):
        raise ValueError(f"'{item_id}' is not a usable item id")
    kind = str(raw.get("kind") or "single")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    out = {
        "id": item_id, "title": name[:200], "kind": kind,
        "caption": str(raw.get("caption") or "")[:4000],
        "channels": str(raw.get("channels") or "")[:200],
        "when": str(raw.get("when") or "")[:120],
        "audience": str(raw.get("audience") or "")[:60],
        "note": str(raw.get("note") or "")[:600],
        "version": 1, "images": [],
    }
    if raw.get("plan_item_id"):
        out["plan_item_id"] = str(raw["plan_item_id"])[:80]
    return out


def add_item(pack_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Add one more post to the end of a pack that already exists. Links and answers stay as they are."""
    pack = _pack_or_raise(pack_id)
    item = _clean_item(raw)
    if any(i["id"] == item["id"] for i in pack["items"]):
        raise ValueError(f"this pack already has a post called '{item['id']}'")
    pack["items"].append(item)
    _write_json(_pack_dir(pack_id) / "pack.json", pack)
    return item


def create_pack(title: str, items: list[dict[str, Any]], *, client: str = "",
                theme: dict[str, Any] | None = None, notice: str = "") -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise ValueError("a pack needs a title")
    if not isinstance(items, list) or not items:
        raise ValueError("a pack needs at least one item")
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items:
        item = _clean_item(raw)
        if item["id"] in seen:
            raise ValueError(f"two items share the id '{item['id']}'")
        seen.add(item["id"])
        clean.append(item)
    pack_id = f"{_slug(title, 'pack')[:30].strip('-') or 'pack'}-{secrets.token_hex(3)}"
    pack = {"id": pack_id, "title": title[:200], "client": (client or "").strip()[:60],
            "created": _now(), "theme": _clean_theme(theme),
            "notice": str(notice or "").strip()[:800], "items": clean}
    _write_json(_pack_dir(pack_id) / "pack.json", pack)
    return pack


def create_empty_pack(title: str, *, client: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A pack with no items yet. Used when the catalog will fill slots on sync."""
    title = (title or "").strip()
    if not title:
        raise ValueError("a pack needs a title")
    pack_id = f"pack-{secrets.token_hex(4)}"
    pack: dict[str, Any] = {
        "id": pack_id,
        "title": title[:200],
        "client": (client or "").strip()[:60],
        "created": _now(),
        "theme": {},
        "notice": "",
        "items": [],
    }
    if extra:
        pack.update(extra)
    _write_json(_pack_dir(pack_id) / "pack.json", pack)
    return pack


def patch_pack(pack_id: str, **fields: Any) -> dict[str, Any]:
    pack = _pack_or_raise(pack_id)
    pack.update(fields)
    _write_json(_pack_dir(pack_id) / "pack.json", pack)
    return pack


def update_item_fields(pack_id: str, item_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Change title, caption, channels, when or note. Never touches images or decisions."""
    pack = _pack_or_raise(pack_id)
    item = _item(pack, item_id)
    limits = {"title": 200, "caption": 4000, "channels": 200, "when": 120, "note": 600, "audience": 60}
    for key, val in fields.items():
        if key == "caption_auto":
            item["caption_auto"] = bool(val)
            continue
        if key == "picture_meta" and isinstance(val, list):
            item["picture_meta"] = val
            continue
        if key not in limits:
            continue
        item[key] = str(val or "")[: limits[key]]
        if key == "caption" and "caption_auto" not in fields:
            item["caption_auto"] = False
    _write_json(_pack_dir(pack_id) / "pack.json", pack)
    return item


def _clean_theme(theme: dict[str, Any] | None) -> dict[str, Any]:
    theme = theme or {}
    colour = re.compile(r"^#[0-9a-fA-F]{6}$")
    out: dict[str, Any] = {"name": str(theme.get("name") or "")[:60]}
    for key in ("ink", "bg", "accent"):
        if colour.match(str(theme.get(key) or "")):
            out[key] = theme[key]
    stops = [c for c in (theme.get("gradient") or []) if colour.match(str(c))][:3]
    if len(stops) >= 2:
        out["gradient"] = stops
    return out


def get_pack(pack_id: str) -> dict[str, Any] | None:
    d = _pack_dir(pack_id)
    if d is None:
        return None
    pack = _read_json(d / "pack.json", None)
    return pack if isinstance(pack, dict) else None


def list_packs() -> list[dict[str, Any]]:
    out = []
    if _root().is_dir():
        for d in sorted(_root().iterdir()):
            pack = get_pack(d.name)
            if pack:
                posts = len(pack.get("items") or [])
                pictures = sum(1 for i in pack.get("items") or [] if i.get("images"))
                out.append({
                    "id": pack["id"], "title": pack["title"], "client": pack.get("client", ""),
                    "items": posts, "created": pack.get("created", ""),
                    "kind": pack.get("kind") or "single",
                    "plan_id": pack.get("plan_id") or "",
                    "brand": pack.get("brand_id") or "",
                    "counts": {"posts": posts, "pictures": pictures, "pictures_yet": max(0, posts - pictures)},
                })
    return out


def _item(pack: dict[str, Any], item_id: str) -> dict[str, Any]:
    for it in pack["items"]:
        if it["id"] == item_id:
            return it
    raise NotFound("that item is not in this pack")


def item_exists(pack_id: str, item_id: str) -> bool:
    pack = get_pack(pack_id)
    if pack is None:
        return False
    return item_id == "" or any(it["id"] == item_id for it in pack["items"])


def _pack_or_raise(pack_id: str) -> dict[str, Any]:
    pack = get_pack(pack_id)
    if pack is None:
        raise NotFound("that pack is not there")
    return pack


# ── taking a post off a live pack (our side only) ───────────────────────────
# Hidden, never deleted: the post, its pictures and any answers stay on disk under
# pack["removed_items"], so "Put back" returns it where it was.


def remove_item(pack_id: str, item_id: str) -> dict[str, Any]:
    pack = _pack_or_raise(pack_id)
    item = _item(pack, item_id)
    pos = pack["items"].index(item)
    after = pack["items"][pos - 1]["id"] if pos else None
    pack["items"].remove(item)
    pack.setdefault("removed_items", []).append(
        {**item, "removed_at": _now(), "removed_after": after, "removed_index": pos})
    _write_json(_pack_dir(pack_id) / "pack.json", pack)
    return {"id": item_id, "title": item.get("title", "")}


def restore_item(pack_id: str, item_id: str) -> dict[str, Any]:
    pack = _pack_or_raise(pack_id)
    gone = pack.get("removed_items") or []
    idx = next((n for n in range(len(gone) - 1, -1, -1) if gone[n].get("id") == item_id), None)
    if idx is None or any(i["id"] == item_id for i in pack["items"]):
        raise NotFound("that post is not in the removed list")
    row = gone.pop(idx)
    after, index = row.pop("removed_after", None), row.pop("removed_index", None)
    row.pop("removed_at", None)
    ids = [i["id"] for i in pack["items"]]
    if after in ids:
        pos = ids.index(after) + 1
    elif after is None and index == 0:
        pos = 0
    else:
        pos = min(index, len(ids)) if isinstance(index, int) else len(ids)
    pack["items"].insert(pos, row)
    _write_json(_pack_dir(pack_id) / "pack.json", pack)
    return {"id": item_id, "title": row.get("title", "")}


def removed_items(pack_id: str) -> list[dict[str, Any]]:
    """Posts taken off the pack that can be put back: latest removal first, one row per post."""
    pack = _pack_or_raise(pack_id)
    shown = {i["id"] for i in pack["items"]}
    out, seen = [], set()
    for row in reversed(pack.get("removed_items") or []):
        rid = row.get("id")
        if not rid or rid in seen or rid in shown:
            continue
        seen.add(rid)
        out.append({"id": rid, "title": row.get("title", rid), "removed_at": row.get("removed_at", "")})
    return out


# ── images ──────────────────────────────────────────────────────────────────


def _check_image(data: bytes, limit: int) -> tuple[Any, str]:
    """(decoded image, format) or ValueError. Looks inside the bytes, never at the name."""
    if not data:
        raise ValueError("that file is empty")
    if len(data) > limit:
        raise ValueError(f"that image is too big (the limit is {limit // (1024 * 1024)} MB)")
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "").upper()
        img.load()
    except Exception:
        raise ValueError("that is not a picture we can open (use a JPG, PNG or WebP)")
    if fmt not in ("JPEG", "PNG", "WEBP"):
        raise ValueError("that is not a picture we can open (use a JPG, PNG or WebP)")
    return img, fmt


def check_upload(data: bytes) -> None:
    """Raise ValueError unless this is an image we would keep. Used to check a whole batch first."""
    _check_image(data, MAX_UPLOAD_BYTES)


def add_item_image(pack_id: str, item_id: str, data: bytes, *, replace: bool = False) -> dict[str, Any]:
    """Add a picture to an item. replace=True swaps them all for this one, bumps the
    item's version and clears its decision: she is asked again about what changed."""
    pack = _pack_or_raise(pack_id)
    item = _item(pack, item_id)
    _check_image(data, MAX_PACK_IMAGE_BYTES)
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[(img.format or "JPEG").upper()]
    if replace:
        item["version"] = int(item.get("version", 1)) + 1
        item["images"] = []
    idx = len(item["images"])
    name = f"{item_id}-{idx}-v{item['version']}{ext}"
    d = _pack_dir(pack_id)
    (d / "images").mkdir(parents=True, exist_ok=True)
    (d / "images" / name).write_bytes(data)
    item["images"].append(name)
    _write_json(d / "pack.json", pack)
    if replace:
        decisions = _read_json(d / "decisions.json", {})
        if decisions.pop(item_id, None) is not None:
            _write_json(d / "decisions.json", decisions)
    return {"index": idx, "version": item["version"]}


def add_catalog_picture(
    pack_id: str,
    item_id: str,
    feed_data: bytes,
    *,
    source_url: str,
    content_hash: str,
    story_data: bytes,
    google_data: bytes,
    remake: bool = False,
    shown_to_client: bool = True,
) -> dict[str, Any]:
    """Add a composed feed picture and its story + Google renders. Bumps version, keeps history."""
    pack = _pack_or_raise(pack_id)
    item = _item(pack, item_id)
    hashes = list(item.get("picture_hashes") or [])
    if content_hash in hashes:
        return {"skipped": True, "version": item.get("version", 1)}
    _img, fmt = _check_image(feed_data, MAX_PACK_IMAGE_BYTES)
    ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[fmt.upper()]
    item["version"] = int(item.get("version", 1)) + 1
    idx = len(item.get("images") or [])
    ver = item["version"]
    feed_name = f"{item_id}-{idx}-v{ver}{ext}"
    story_name = f"{item_id}-{idx}-v{ver}-story.png"
    google_name = f"{item_id}-{idx}-v{ver}-google.jpg"
    d = _pack_dir(pack_id)
    assert d is not None
    (d / "images").mkdir(parents=True, exist_ok=True)
    (d / "images" / feed_name).write_bytes(feed_data)
    (d / "images" / story_name).write_bytes(story_data)
    (d / "images" / google_name).write_bytes(google_data)
    item.setdefault("images", []).append(feed_name)
    hashes.append(content_hash)
    item["picture_hashes"] = hashes
    meta = list(item.get("picture_meta") or [])
    meta.append({
        "version": ver,
        "hash": content_hash,
        "source_url": str(source_url or "")[:500],
        "idx": idx,
        "remake": bool(remake),
        "shown_to_client": bool(shown_to_client),
    })
    item["picture_meta"] = meta
    _write_json(d / "pack.json", pack)
    decisions = _read_json(d / "decisions.json", {})
    cur = decisions.get(item_id) if isinstance(decisions.get(item_id), dict) else None
    if cur and not (remake and not shown_to_client):
        if cur.get("state") not in ("hold", "reject"):
            decisions.pop(item_id, None)
            _write_json(d / "decisions.json", decisions)
    return {"index": idx, "version": ver, "skipped": False}


def clear_decision(pack_id: str, item_id: str) -> None:
    d = _pack_dir(pack_id)
    decisions = _read_json(d / "decisions.json", {})
    if decisions.pop(item_id, None) is not None:
        _write_json(d / "decisions.json", decisions)


def _feed_image_name(item: dict[str, Any], index: int) -> str | None:
    try:
        name = item["images"][int(index)]
    except (IndexError, ValueError, TypeError, KeyError):
        return None
    return name if _IMAGE_NAME.match(name) else None


def image_path(pack_id: str, item_id: str, index: int, *, size: str = "feed") -> Path | None:
    pack = get_pack(pack_id)
    if pack is None:
        return None
    try:
        item = _item(pack, item_id)
        feed_name = _feed_image_name(item, index)
    except NotFound:
        return None
    if not feed_name:
        return None
    size = (size or "feed").strip().lower()
    if size == "feed":
        name = feed_name
    else:
        base = re.sub(r"\.(jpe?g|png|webp)$", "", feed_name, flags=re.I)
        name = f"{base}-story.png" if size == "story" else (
            f"{base}-google.jpg" if size == "google" else ""
        )
        if not name:
            return None
    p = _pack_dir(pack_id) / "images" / name
    return p if p.is_file() else None


# ── decisions and comments ──────────────────────────────────────────────────


def record_decision(pack_id: str, item_id: str, state: str, who: str, *, choice: str | None = None) -> dict[str, Any]:
    """Record Approve / Reject / Hold. This is a note and nothing more."""
    pack = _pack_or_raise(pack_id)
    item = _item(pack, item_id)
    if state not in STATES:
        raise ValueError("choose Approve, Reject or Hold")
    if choice not in (None, "") and choice not in CHOICES:
        raise ValueError("choose A, B or C")
    d = _pack_dir(pack_id)
    decisions = _read_json(d / "decisions.json", {})
    row = {"state": state, "by": (who or "someone").strip()[:40], "at": _now(), "version": item.get("version", 1)}
    if choice:
        row["choice"] = choice
    elif isinstance(decisions.get(item_id), dict) and decisions[item_id].get("choice"):
        row["choice"] = decisions[item_id]["choice"]
    decisions[item_id] = row
    _write_json(d / "decisions.json", decisions)
    return row


def record_choice(pack_id: str, item_id: str, choice: str, who: str) -> dict[str, Any]:
    """Record which of A, B or C she picked. This does NOT approve the post: it stays
    waiting ('pending') until she presses Approve, Reject or Hold."""
    pack = _pack_or_raise(pack_id)
    item = _item(pack, item_id)
    if item.get("kind") != "choice":
        raise ValueError("this post has no designs to pick from")
    if choice not in CHOICES:
        raise ValueError("choose A, B or C")
    d = _pack_dir(pack_id)
    decisions = _read_json(d / "decisions.json", {})
    cur = decisions.get(item_id) if isinstance(decisions.get(item_id), dict) else {}
    row = {"state": cur.get("state", "pending"), "by": (who or "someone").strip()[:40], "at": _now(),
           "version": item.get("version", 1), "choice": choice}
    decisions[item_id] = row
    _write_json(d / "decisions.json", decisions)
    return row


def add_comment(pack_id: str, item_id: str, who: str, text: str, *, role: str = "client",
                tag: str = "general") -> dict[str, Any]:
    pack = _pack_or_raise(pack_id)
    if item_id:
        _item(pack, item_id)
    text = (text or "").strip()
    if not text:
        raise ValueError("write something first")
    if tag not in TAGS:
        raise ValueError(f"tag must be one of {', '.join(TAGS)}")
    if role not in ROLES:
        raise ValueError("role must be client or us")
    row = {"item": item_id or "", "who": (who or "someone").strip()[:40], "role": role,
           "tag": tag, "text": text[:MAX_COMMENT_CHARS], "at": _now()}
    _append_row(_pack_dir(pack_id) / "comments.jsonl", row)
    return row


# ── uploads ─────────────────────────────────────────────────────────────────


def _clean_name(name: str) -> str:
    base = re.split(r"[\\/]", str(name or ""))[-1]
    base = re.sub(r"[^A-Za-z0-9 ._-]", "", base).strip()
    return base[:60] or "photo"


def save_upload(pack_id: str, item_id: str, data: bytes, *, original_name: str, source: str,
                rights: bool, who: str, purpose: str = "", text: str = "") -> dict[str, Any]:
    """Keep one photo she uploaded. Checked by looking inside it, re-encoded (which
    drops hidden location data) and saved under a random name."""
    pack = _pack_or_raise(pack_id)
    if item_id:
        _item(pack, item_id)
    img, fmt = _check_image(data, MAX_UPLOAD_BYTES)
    from PIL import Image

    buf = io.BytesIO()
    if fmt == "PNG":
        ext = ".png"
        img.save(buf, format="PNG")
    else:
        ext = ".jpg"
        img.convert("RGB").save(buf, format="JPEG", quality=92)
    name = f"up-{secrets.token_hex(6)}{ext}"
    d = _pack_dir(pack_id)
    (d / "uploads").mkdir(parents=True, exist_ok=True)
    (d / "uploads" / name).write_bytes(buf.getvalue())
    row = {"file": name, "item": item_id or "", "original_name": _clean_name(original_name),
           "source": str(source or "").strip()[:200], "rights": bool(rights),
           "purpose": str(purpose or "").strip()[:40], "text": str(text or "").strip()[:400],
           "who": (who or "someone").strip()[:40], "at": _now(), "bytes": buf.tell()}
    _append_row(d / "uploads.jsonl", row)
    return row


def upload_path(pack_id: str, name: str) -> Path | None:
    d = _pack_dir(pack_id)
    if d is None or not isinstance(name, str) or not _UPLOAD_NAME.match(name):
        return None
    p = d / "uploads" / name
    return p if p.is_file() else None


# ── reading it back ─────────────────────────────────────────────────────────


def view(pack_id: str) -> dict[str, Any]:
    pack = _pack_or_raise(pack_id)
    d = _pack_dir(pack_id)
    comments: dict[str, list[dict[str, Any]]] = {}
    for row in _read_rows(d / "comments.jsonl"):
        comments.setdefault(str(row.get("item") or ""), []).append(row)
    return {"pack": pack, "decisions": _read_json(d / "decisions.json", {}), "comments": comments,
            "uploads": _read_rows(d / "uploads.jsonl")}


def mark_done(pack_id: str, who: str) -> dict[str, Any]:
    """She says she has finished. A note for us and nothing more: it schedules and sends nothing.
    Pressing it again just updates the time, so it is news again."""
    _pack_or_raise(pack_id)
    d = _pack_dir(pack_id)
    key = " ".join(str(who or "someone").lower().split())
    rows = _read_json(d / "done.json", {})
    row = {"by": (who or "someone").strip()[:40], "at": _now()}
    rows[key] = row
    _write_json(d / "done.json", rows)
    return row


def _done_rows(pack_id: str) -> dict[str, dict[str, Any]]:
    d = _pack_dir(pack_id)
    rows = _read_json(d / "done.json", {}) if d is not None else {}
    return {k: r for k, r in rows.items() if isinstance(r, dict)}


PALETTE = ["#f2994a", "#56ccf2", "#bb6bd9", "#6fcf97", "#eb5757", "#f2c94c", "#4f9cf0", "#e07bb0", "#27ae9a", "#a5a5f5"]


def colour_of(pack_id: str, who: str) -> str:
    """One colour per person per pack, kept so they keep it. 'Yolanda ' and 'yolanda' are one person."""
    d = _pack_dir(pack_id)
    key = " ".join(str(who or "someone").lower().split())
    if d is None or not d.is_dir():
        return PALETTE[0]
    people = _read_json(d / "people.json", {})
    if key not in people:
        people[key] = len(people)
        _write_json(d / "people.json", people)
    return PALETTE[people[key] % len(PALETTE)]


def public_view(
    pack_id: str,
    token: str,
    who: str = "",
    staff: bool = False,
    *,
    campaign_can_approve: bool = False,
    share_role: str | None = None,
    session_user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """What the page needs, with links that carry her token. staff=True only for a signed-in
    teammate: it adds the data for Remove and Put back. The client's view never carries it."""
    v = view(pack_id)
    base = f"/review-pack/{token}"
    is_catalog = v["pack"].get("kind") == "catalog"
    items = []
    for it in v["pack"]["items"]:
        urls = [f"{base}/image/{it['id']}/{i}" for i in range(len(it.get("images") or []))]
        latest = len(urls) - 1
        if is_catalog:
            from _lib import catalog as _cat

            latest = _cat.client_picture_index(it, staff=staff)
            if latest < 0:
                latest = len(urls) - 1
            if not staff and latest < len(urls) - 1:
                urls = urls[: latest + 1]
        size_urls = {}
        if latest >= 0 and urls:
            root = f"{base}/image/{it['id']}/{latest}"
            size_urls = {"feed": root, "story": f"{root}?size=story", "google": f"{root}?size=google"}
        keys = ("id", "title", "kind", "caption", "channels", "when", "due", "audience", "note", "version")
        row = {**{k: it[k] for k in keys if k in it}, "images": urls, "size_urls": size_urls}
        if staff and is_catalog:
            meta = it.get("picture_meta") or []
            row["hidden_remake"] = bool(
                meta and meta[-1].get("remake") and meta[-1].get("shown_to_client") is False
            )
        items.append(row)
    uploads = [{**u, "url": f"{base}/file/{u['file']}", "colour": colour_of(pack_id, u.get("who", ""))} for u in v["uploads"]]
    comments = {k: [{**c, "colour": colour_of(pack_id, c.get("who", ""))} for c in rows] for k, rows in v["comments"].items()}
    decisions = {k: ({**r, "colour": colour_of(pack_id, r.get("by", ""))} if isinstance(r, dict) else r)
                 for k, r in v["decisions"].items()}
    me = " ".join(str(who or "").lower().split())
    done = [{**r, "colour": colour_of(pack_id, r.get("by", "")), "mine": bool(me) and k == me}
            for k, r in sorted(_done_rows(pack_id).items(), key=lambda kv: kv[1].get("at", ""))]
    catalog_line = ""
    labels = None
    campaign_summary = None
    month_strip = None
    can_drag = False
    can_remake = False
    if v["pack"].get("kind") == "catalog":
        from _lib import catalog as _cat
        from _lib import users as _users

        catalog_line = _cat.catalog_header(v["pack"])
        labels = _cat.labels_for(v["pack"])
        campaign_summary = _cat.mark_summary(pack_id)
        month_strip = _cat.month_strip_view(pack_id)
        can_drag = _cat.staff_can_drag(staff=staff, session_user=session_user, share_role=share_role)
        can_remake = bool(staff and session_user and _users.can(session_user, "catalog_make"))
    out = {"pack": {"title": v["pack"]["title"], "client": v["pack"].get("client", ""),
                     "theme": v["pack"].get("theme", {}), "notice": v["pack"].get("notice", ""), "items": items},
            "decisions": decisions, "comments": comments, "uploads": uploads, "done": done, "staff": False,
            "catalog_line": catalog_line, "catalog_upload": v["pack"].get("kind") == "catalog",
            "campaign_can_approve": bool(campaign_can_approve and v["pack"].get("kind") == "catalog"),
            "campaign_summary": campaign_summary}
    if labels:
        out["labels"] = labels
    if month_strip is not None:
        out["month_strip"] = month_strip
        out["can_drag"] = can_drag
        out["can_remake"] = can_remake
    if v["pack"].get("campaign_approval"):
        out["campaign_approved"] = v["pack"]["campaign_approval"]
    if staff:
        out["staff"] = True
        out["pack_id"] = pack_id
        out["removed"] = removed_items(pack_id)
    return out


def news(pack_id: str, since: str = "") -> dict[str, Any]:
    """What the client did after `since` (an ISO time from an earlier call's `now`), as counts and
    plain text for the Mac watcher to send. Our own replies are not news. Sends nothing itself."""
    v = view(pack_id)
    since = (since or "").strip()
    titles = {i["id"]: i.get("title") or i["id"] for i in v["pack"]["items"]}

    def fresh(row: dict[str, Any], key: str = "at") -> bool:
        return str(row.get(key) or "") > since

    decided = [(titles.get(k, k), r) for k, r in v["decisions"].items() if isinstance(r, dict) and fresh(r)]
    comments = [c for rows in v["comments"].values() for c in rows if c.get("role") == "client" and fresh(c)]
    uploads = [u for u in v["uploads"] if fresh(u)]
    counts = {
        "approved": sum(1 for _, r in decided if r.get("state") == "approve"),
        "rejected": sum(1 for _, r in decided if r.get("state") == "reject"),
        "held": sum(1 for _, r in decided if r.get("state") == "hold"),
        "picked": sum(1 for _, r in decided if r.get("state") == "pending" and r.get("choice")),
        "comments": len(comments),
        "uploads": len(uploads),
    }
    done_now = [r for r in sorted(_done_rows(pack_id).values(), key=lambda r: r.get("at", "")) if fresh(r)]
    camp = v["pack"].get("campaign_approval") if isinstance(v["pack"].get("campaign_approval"), dict) else {}
    camp_fresh = bool(camp and fresh(camp))
    empty = not any(counts.values()) and not done_now and not camp_fresh
    lines: list[str] = []
    campaign_approved = camp if camp_fresh else None
    if not empty:
        client = v["pack"].get("client") or "The client"
        lines.append(f"{client} on \"{v['pack']['title']}\":")
        words = {"approve": "approved", "reject": "rejected", "hold": "put on hold", "pending": "picked a design for"}
        for title, r in sorted(decided, key=lambda t: t[1].get("at", "")):
            lines.append(f"- {r.get('by', 'someone')} {words.get(r.get('state'), r.get('state'))} {title}"
                         + (f" (design {r['choice']})" if r.get("choice") else ""))
        for c in comments:
            tag = f", {c['tag']}" if c.get("tag") and c["tag"] != "general" else ""
            lines.append(f"- {c.get('who', 'someone')} commented on {titles.get(c.get('item'), 'the pack')}{tag}: {c.get('text', '')[:140]}")
        for u in uploads:
            lines.append(f"- {u.get('who', 'someone')} uploaded a photo to {titles.get(u.get('item'), 'the pack')}")
        for r in done_now:
            lines.append(f"- {r.get('by', 'someone')} says they are done")
        if campaign_approved:
            lines.append(
                f"- {campaign_approved.get('by', 'someone')} approved the campaign "
                f"({campaign_approved.get('at', '')[:16].replace('T', ' ')})"
            )
    return {"pack_id": pack_id, "since": since, "now": _now(), "empty": empty, "counts": counts,
            "done": [r.get("by", "someone") for r in done_now], "text": "\n".join(lines),
            "campaign_approved": {"by": campaign_approved.get("by"), "at": campaign_approved.get("at")}
            if campaign_approved else None}


def has_activity(pack_id: str) -> bool:
    """True once the CLIENT has answered: a decision, a comment of hers or an upload.
    Our own replies do not count."""
    d = _pack_dir(pack_id)
    if d is None or not d.is_dir():
        return False
    if _read_json(d / "decisions.json", {}) or _read_json(d / "done.json", {}):
        return True
    if any(r.get("role") == "client" for r in _read_rows(d / "comments.jsonl")):
        return True
    return bool(_read_rows(d / "uploads.jsonl"))


def delete_pack(pack_id: str, *, force: bool = False) -> bool:
    """Delete a pack for good. False if it is not there. A pack the client has already
    answered is refused (ValueError) unless force: deleting is final."""
    d = _pack_dir(pack_id)
    if d is None or not d.is_dir():
        return False
    if not force and has_activity(pack_id):
        raise ValueError("She has already answered this pack (a decision, a comment or an upload). "
                         "Deleting is final. Add force to delete it anyway.")
    shutil.rmtree(d)
    return True


# ── the page ────────────────────────────────────────────────────────────────

_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>__TITLE__</title>
<style>
:root{--ink:__INK__;--bg:__BG__;--accent:__ACCENT__;--grad:__GRAD__;--card:#fff;--muted:#5c6078;--line:#dad6d0;--ok:#0e7a4f;--okbg:#ddf3e8;--no:#a3262f;--nobg:#fde3e3;--hold:#5c6078;--holdbg:#e8e6ef;--us:#efe7ff;--them:#e8f3fc}
@media (prefers-color-scheme:dark){:root{--ink:#f6f4f1;--bg:#0e1020;--card:#171a30;--muted:#a5a9c2;--line:#2b2f4d;--ok:#7be0b0;--okbg:#12362a;--no:#ff9aa2;--nobg:#3a1519;--hold:#a5a9c2;--holdbg:#262944;--us:#2a2150;--them:#10304a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:24px max(16px,env(safe-area-inset-right)) 120px max(16px,env(safe-area-inset-left))}
.wrap{max-width:1000px;margin:0 auto;display:flex;flex-direction:column;gap:22px}
h1{font-size:clamp(28px,5vw,42px);line-height:1.1;margin:0;font-weight:900}h1 span{background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
.lead{color:var(--muted);margin:8px 0 0;max-width:62ch}h2{font-size:22px;margin:0;font-weight:800}.sub{color:var(--muted);font-size:15px;margin:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;display:flex;flex-direction:column;gap:14px;min-width:0}
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.badge{font-weight:800;font-size:14px;border-radius:999px;padding:6px 14px;background:var(--holdbg);color:var(--hold);white-space:nowrap}
.badge.approve{background:var(--okbg);color:var(--ok)}.badge.reject{background:var(--nobg);color:var(--no)}
.meta{font-size:15px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}.grid.one{grid-template-columns:minmax(0,420px)}.grid.choice{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.grid.choice .zoom{top:6px;right:6px;width:34px;height:34px;font-size:16px}
.cell{position:relative;min-width:0}.cell img{width:100%;display:block;border-radius:10px;background:var(--line);aspect-ratio:4/5;object-fit:cover;cursor:zoom-in}
.pic.none{aspect-ratio:4/5;border-radius:10px;border:1px dashed var(--line);display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:13px;text-align:center;padding:8px;min-height:120px}
.size-tabs{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 8px}
.size-tabs button.pill{font-size:14px;padding:6px 14px;min-height:40px}
.earlier{margin:4px 0 0;font-size:13px;color:var(--muted)}
.catline{font-size:15px;color:var(--muted);margin:6px 0 0}
.month-strip{display:flex;flex-direction:column;gap:10px;margin:4px 0 18px}
.month-row{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.month-lbl{font-weight:800;font-size:14px;min-width:5rem}
.month-days{display:flex;flex-wrap:wrap;gap:6px}
.day-dot{font:inherit;display:inline-flex;gap:3px;align-items:center;border:1px solid var(--line);border-radius:8px;padding:5px 9px;background:var(--card);cursor:pointer;min-height:40px}
.day-dot.drag-over{outline:2px dashed var(--accent)}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.slot-chip{cursor:grab;font-weight:700}
.move-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:4px}
.move-row input[type=date]{font:inherit;border:2px solid var(--line);border-radius:10px;padding:8px}
.zoom{position:absolute;top:10px;right:10px;width:40px;height:40px;border-radius:50%;border:0;background:rgba(18,21,40,.78);color:#fff;font-size:19px;cursor:pointer}
.opt{border:3px solid transparent;border-radius:14px;padding:5px;background:transparent;color:inherit;font:inherit;cursor:pointer;display:flex;flex-direction:column;gap:8px;text-align:left}
.opt[aria-pressed=true]{border-color:var(--accent)}.opt b{font-size:18px}
.cap{white-space:pre-wrap;border-left:4px solid var(--line);padding-left:12px;font-size:16px;overflow-wrap:anywhere}
.row{display:flex;flex-wrap:wrap;gap:10px}
button.pill{font:inherit;font-weight:800;border:2px solid var(--line);background:transparent;color:var(--ink);border-radius:999px;padding:10px 22px;min-height:46px;cursor:pointer}
button.pill[aria-pressed=true]{border-color:transparent;color:#fff;background:var(--grad)}
button.pill.reject[aria-pressed=true]{background:var(--no)}button.pill.hold[aria-pressed=true]{background:var(--hold)}
.thread{border-top:1px solid var(--line);padding-top:12px;display:flex;flex-direction:column;gap:8px}.thread h3{margin:0;font-size:15px;color:var(--muted)}
.cm{border-radius:12px;padding:8px 12px;max-width:min(100%,62ch);overflow-wrap:anywhere}.cm.client{background:var(--them)}.cm.us{background:var(--us)}
.cm small{display:block;font-weight:700;color:var(--muted)}.cm p{margin:2px 0 0;white-space:pre-wrap}
.compose{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end}
textarea,input[type=text],select{font:inherit;border:2px solid var(--line);border-radius:12px;padding:9px 11px;background:var(--bg);color:var(--ink)}
textarea{flex:1 1 240px;min-height:52px;resize:vertical}
.send{font:inherit;font-weight:800;border:0;border-radius:999px;padding:11px 22px;min-height:46px;cursor:pointer;color:#fff;background:var(--grad)}.send[disabled]{opacity:.5}
.up{border:2px dashed var(--line);border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:8px}
.up label.chk{display:flex;gap:8px;align-items:flex-start;font-size:14px}
.ups{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px}.ups img{width:100%;border-radius:8px;aspect-ratio:1;object-fit:cover;cursor:zoom-in}
.nextb{font:inherit;font-weight:800;border:2px solid var(--bg);background:transparent;color:var(--bg);border-radius:999px;padding:6px 16px;min-height:40px;cursor:pointer}#progress{font-weight:800}
#finish:focus,.card:focus{outline:none}
[hidden]{display:none!important}
.team{border:2px dashed var(--no);border-radius:12px;padding:10px 14px;display:flex;flex-direction:column;gap:8px;font-size:15px}
button.rm{font:inherit;font-size:14px;font-weight:800;border:2px solid var(--no);background:transparent;color:var(--no);border-radius:999px;padding:6px 14px;min-height:38px;cursor:pointer}
.bar{flex-wrap:wrap;position:fixed;left:0;right:0;bottom:0;background:var(--ink);color:var(--bg);padding:12px 16px;display:flex;justify-content:space-between;align-items:center;gap:12px;z-index:5}
.lb{position:fixed;inset:0;background:rgba(8,10,22,.95);z-index:50;display:flex;align-items:center;justify-content:center;padding:16px}.lb[hidden]{display:none}
.lb img{max-width:min(96vw,1100px);max-height:86vh;border-radius:8px}
.lbb{position:absolute;border:0;border-radius:999px;background:rgba(255,255,255,.18);color:#fff;font:inherit;font-weight:800;cursor:pointer;padding:10px 18px}
#lbx{top:16px;right:16px}#lbp{left:10px;top:50%}#lbn{right:10px;top:50%}#lbc{position:absolute;bottom:14px;left:0;right:0;text-align:center;color:#fff;font-size:15px}
button:focus-visible,textarea:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
</style></head><body>
<div class="wrap">
<header><h1 id="ttl"></h1><p class="catline" id="catline" hidden></p><p class="catline" id="campaignline" hidden></p><button type="button" class="send" data-campaign-yes hidden>Approve the campaign</button><p class="lead" id="intro"></p></header>
<aside class="card" id="notice" hidden style="border-left:6px solid var(--accent)"></aside>
<div id="items" class="wrap"></div>
<section class="card" id="week"></section>
<section class="card" id="finish" tabindex="-1"></section>
</div>
<div class="bar"><span id="progress"></span><button id="nextb" class="nextb" type="button">Next post</button><span id="status" aria-live="polite"></span></div>
<div id="lb" class="lb" hidden role="dialog" aria-modal="true" aria-label="Full screen picture"><button id="lbx" class="lbb" type="button">Close</button><button id="lbp" class="lbb" type="button" aria-label="Previous">&lsaquo;</button><img id="lbi" alt=""><button id="lbn" class="lbb" type="button" aria-label="Next">&rsaquo;</button><div id="lbc"></div></div>
<script type="application/json" id="boot">__DATA__</script>
<script>
const TOKEN="__TOKEN__",BASE="/review-pack/"+TOKEN;let D=JSON.parse(document.getElementById("boot").textContent);
const $=id=>document.getElementById(id);const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=x;return e};
const LBL=__LBL__;let LB={l:[],i:0,t:""};const SIZE_PICK=new Map();let UNMARKED_OK=false;
function pickSize(item,key,img,urls){SIZE_PICK.set(item,key);document.querySelectorAll('[data-size-tab="'+item+'"]').forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.k===key)));if(img&&urls[key])img.src=urls[key]}
function openLB(l,i,t){LB={l,i,t};showLB();$("lb").hidden=false;$("lbx").focus()}
function showLB(){$("lbi").src=LB.l[LB.i];$("lbc").textContent=LB.t+(LB.l.length>1?"  ·  "+(LB.i+1)+" of "+LB.l.length:"");$("lbp").hidden=$("lbn").hidden=LB.l.length<2}
function step(d){LB.i=(LB.i+d+LB.l.length)%LB.l.length;showLB()}
$("lbx").onclick=()=>{$("lb").hidden=true};$("lbp").onclick=()=>step(-1);$("lbn").onclick=()=>step(1);$("lb").onclick=e=>{if(e.target===$("lb"))$("lb").hidden=true};
document.addEventListener("keydown",e=>{if($("lb").hidden)return;if(e.key==="Escape")$("lb").hidden=true;if(e.key==="ArrowLeft")step(-1);if(e.key==="ArrowRight")step(1)});
function say(t){$("status").textContent=t;if(t)setTimeout(()=>{if($("status").textContent===t)$("status").textContent=""},4000)}
async function post(path,body){const r=await fetch(BASE+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||"Something went wrong");return j}
let DRAG_ITEM="";
function paintMonthStrip(){const old=document.getElementById("monthstrip");if(old)old.remove();if(!D.month_strip||!D.month_strip.months||!D.month_strip.months.length)return;
 const strip=el("div","month-strip");strip.id="monthstrip";strip.setAttribute("role","navigation");strip.setAttribute("aria-label","Campaign calendar");
 D.month_strip.months.forEach(m=>{const row=el("div","month-row");row.append(el("span","month-lbl",m.label));const days=el("div","month-days");
  m.days.forEach(day=>{const b=el("button","day-dot",String(Number(day.iso.slice(8,10))));
   b.type="button";b.dataset.day=day.iso;(day.dots||[]).forEach(d=>{const dot=el("span","dot");dot.style.background=d.colour;b.append(dot)});
   b.onclick=()=>{const t=document.querySelector('section[data-id="'+day.first_slot+'"]');if(t)t.scrollIntoView({behavior:"smooth",block:"start"})};
   if(D.can_drag){b.ondragover=e=>{e.preventDefault();b.classList.add("drag-over")};b.ondragleave=()=>b.classList.remove("drag-over");
    b.ondrop=async e=>{e.preventDefault();b.classList.remove("drag-over");const id=e.dataTransfer.getData("text/plain")||DRAG_ITEM;if(!id)return;try{await post("/move-slot",{item:id,date:day.iso});say("Moved to "+day.iso);location.reload()}catch(err){say(err.message)}}}
   days.append(b)});row.append(days);strip.append(row)});$("items").before(strip)}
async function remakeNotes(){if(!D.can_remake||!D.pack_id)return;const r=await fetch("/api/review-packs/"+encodeURIComponent(D.pack_id)+"/remake",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:"{}"});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||j.message||"Could not start remakes");say(j.message||"Remakes queued");location.reload()}
async function showRemake(item){if(!D.pack_id)return;const r=await fetch("/api/review-packs/"+encodeURIComponent(D.pack_id)+"/items/"+encodeURIComponent(item)+"/show-remake",{method:"POST",credentials:"same-origin"});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||"Could not show remake");say("Shown to Herman");location.reload()}
function threadHTML(box,item){box.textContent="";const list=D.comments[item]||[];if(!list.length)box.append(el("p","sub","No comments yet."));
 list.forEach(c=>{const d=el("div","cm "+c.role);if(c.colour)d.style.borderLeft="5px solid "+c.colour;const nm=el("small","",c.who+(c.tag&&c.tag!=="general"?"  ·  "+c.tag:"")+"  ·  "+(c.at||"").slice(0,16).replace("T"," "));if(c.colour)nm.style.color=c.colour;d.append(nm,el("p","",c.text));box.append(d)})}
function composer(item,box){const w=el("div","compose");const ta=document.createElement("textarea");ta.placeholder="Write a comment";ta.setAttribute("aria-label","Comment");
 const sel=document.createElement("select");sel.setAttribute("aria-label","What kind of comment");[["general","General"],["copy edit","Copy edit (the words)"],["design edit","Design edit (the picture)"]].forEach(([v,t])=>{const o=el("option","",t);o.value=v;sel.append(o)});
 const b=el("button","send","Send");b.type="button";b.disabled=true;ta.oninput=()=>{b.disabled=!ta.value.trim()};
 b.onclick=async()=>{b.disabled=true;try{const j=await post("/comment",{item,text:ta.value,tag:sel.value});(D.comments[item]=D.comments[item]||[]).push(j.comment);ta.value="";threadHTML(box,item);say("Comment sent")}catch(e){say(e.message);b.disabled=false}};
 w.append(ta,sel,b);return w}
function uploadBox(item,onDone){const u=el("div","up");u.append(el("b","","Add your own photo"));
 const f=document.createElement("input");f.type="file";f.accept="image/jpeg,image/png,image/webp";f.multiple=true;f.setAttribute("aria-label","Choose photos");
 const s=document.createElement("input");s.type="text";s.placeholder="Where is it from, and who owns it?";s.setAttribute("aria-label","Source and owner");
 const lab=el("label","chk");const cb=document.createElement("input");cb.type="checkbox";lab.append(cb,el("span","","I own this photo, or I have permission to use it."));
 let pur,txt;if(D.catalog_upload){pur=document.createElement("select");pur.setAttribute("aria-label","What is this photo for");[["reference","The look I want"],["element","Use this in the post"],["post","This is the post"]].forEach(([v,t])=>{const o=el("option","",t);o.value=v;pur.append(o)});txt=document.createElement("textarea");txt.rows=2;txt.placeholder="Say what this is for in a line of text";txt.setAttribute("aria-label","What this photo is for")}
 const b=el("button","send","Upload");b.type="button";const out=el("p","sub","Up to 20 photos at a time.");
 b.onclick=async()=>{const files=[...f.files];if(!files.length){out.textContent="Choose a photo first.";return}
  if(files.length>20){out.textContent="Only 20 photos at a time. Please choose fewer.";return}
  if(D.catalog_upload&&(!pur.value||!txt.value.trim())){out.textContent="Choose what the photo is for and write a line about it.";return}
  const fd=new FormData();files.forEach(x=>fd.append("files",x));fd.append("item",item);fd.append("source",s.value);fd.append("rights",cb.checked?"1":"");
  if(D.catalog_upload){fd.append("purpose",pur.value);fd.append("text",txt.value.trim())}
  b.disabled=true;out.textContent="Uploading "+files.length+"...";
  try{const r=await fetch(BASE+"/upload",{method:"POST",body:fd});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||"Upload failed");out.textContent=j.uploads.length+" saved.";f.value="";if(txt)txt.value="";await refresh()}catch(e){out.textContent=e.message}finally{b.disabled=false}};
 u.append(f,s,lab);if(pur)u.append(pur,txt);u.append(b,out);return u}
function uploadsGrid(item){const g=el("div","ups");const mine=D.uploads.filter(x=>x.item===item);mine.forEach((x,i)=>{const im=new Image();im.src=x.url;im.alt=x.original_name;im.title=x.source||x.original_name;im.onclick=()=>openLB(mine.map(y=>y.url),i,"Your photo");g.append(im);if(x.text||x.purpose){const cap=el("p","sub",(x.purpose?x.purpose.replace("_"," ")+": ":"")+(x.text||""));g.append(cap)}});return mine.length?g:null}
let SURE=false;
function paintFinish(done,total,first){SURE=false;$("progress").textContent=done+" of "+total+" answered";
 const nb=$("nextb");nb.textContent=first?"Next post":"Finish";nb.onclick=()=>{const t=first?document.querySelector('section[data-id="'+first+'"]'):$("finish");if(t){t.scrollIntoView({behavior:"smooth",block:"start"});t.focus({preventScroll:true})}};
 const f=$("finish");f.textContent="";const mine=(D.done||[]).find(x=>x.mine);const others=(D.done||[]).filter(x=>!x.mine);
 f.append(el("h2","","All finished?"));
 if(mine)f.append(el("p","sub","Thank you. We have your answers and will take it from here. You can still change anything, and tap again if you add more later."));
 else f.append(el("p","sub",done<total?(total-done)+" of "+total+" posts still have no answer. Answer them, or tell us you are done and we will take it as it is.":"Every post has an answer. Tell us when you are happy for us to take it from here."));
 others.forEach(x=>{const p=el("p","meta",x.by+" is done");if(x.colour)p.style.color=x.colour;f.append(p)});
 const b=el("button","send",mine?"Done. Tell us again":"I'm done");b.type="button";
 b.onclick=async()=>{if(!mine&&done<total&&!SURE){SURE=true;b.textContent="Send anyway ("+(total-done)+" unanswered)";return}
  b.disabled=true;try{const j=await post("/done",{});D.done=(D.done||[]).filter(x=>!x.mine);D.done.push({by:j.done.by,at:j.done.at,mine:true,colour:"#7c38f8"});paint();say("Thank you, we have it")}catch(e){say(e.message);b.disabled=false}};
 if(D.campaign_can_approve){const cy=el("button","send","Approve the campaign");cy.type="button";cy.setAttribute("data-campaign-yes","");cy.onclick=campaignYes;f.prepend(cy)}
 f.append(b)}
function paint(){let done=0,total=0,first=null;D.pack.items.forEach(it=>{const ans=!!D.decisions[it.id]&&D.decisions[it.id].state!=="pending";if(it.kind!=="note"){total++;if(ans)done++;else if(!first)first=it.id}const d=D.decisions[it.id];const b=document.querySelector('[data-badge="'+it.id+'"]');
  if(b){const pend=d&&d.state==="pending";b.className="badge"+(d&&!pend?" "+d.state:"");b.textContent=d?(pend?"Option "+d.choice+" picked. Now Approve, Reject or Hold":LBL[d.state]+(d.choice?" · option "+d.choice:"")):"Waiting for you"}
  document.querySelectorAll('[data-st="'+it.id+'"]').forEach(x=>x.setAttribute("aria-pressed",String(!!d&&d.state===x.dataset.v)));
  document.querySelectorAll('[data-ch="'+it.id+'"]').forEach(x=>x.setAttribute("aria-pressed",String(!!d&&d.choice===x.dataset.v)));
  const t=document.querySelector('[data-th="'+it.id+'"]');if(t)threadHTML(t,it.id);
  const g=document.querySelector('[data-ug="'+it.id+'"]');if(g){g.textContent="";const u=uploadsGrid(it.id);if(u)g.append(u)}});
 paintFinish(done,total,first)}
async function team(id,what){const r=await fetch("/api/review-packs/"+encodeURIComponent(D.pack_id)+"/items/"+encodeURIComponent(id)+"/"+what,{method:"POST",credentials:"same-origin"});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||"That did not work");return j}
function teamRemove(it){const b=el("button","rm","Remove from pack");b.type="button";b.title="Only your team sees this button";
 b.onclick=async()=>{if(!confirm('Take "'+it.title+'" off this page? The client stops seeing it. You can put it back from the list at the bottom.'))return;b.disabled=true;try{await team(it.id,"remove");location.reload()}catch(e){say(e.message);b.disabled=false}};return b}
function teamSection(){const s=el("section","card team");s.append(el("b","","Team view: only signed-in teammates see Remove and Put back. The client never does."));
 const gone=D.removed||[];s.append(el("h2","","Removed posts"));if(!gone.length)s.append(el("p","sub","Nothing removed."));
 gone.forEach(g=>{const r=el("div","row");r.style.alignItems="center";r.append(el("span","",g.title));const b=el("button","rm","Put back");b.type="button";
  b.onclick=async()=>{b.disabled=true;try{await team(g.id,"restore");location.reload()}catch(e){say(e.message);b.disabled=false}};r.append(b);s.append(r)});return s}
async function act(item,state,choice){try{let body={item,state:state||undefined,choice:choice||undefined};
 if(D.catalog_upload&&state&&(state==="hold"||state==="reject")){const note=window.prompt("What should change?","");
  if(note===null)return;if(!note.trim()){say("Say what should change first.");return}
  const tag=state==="reject"?"general":"design edit";body={...body,note:note.trim(),tag}}
 const j=await post("/act",body);D.decisions[item]=j.decision;paint();say(state?LBL[state]+" saved":"Option "+choice+" picked")}catch(e){say(e.message)}}
async function campaignYes(){if(!D.campaign_can_approve)return;const s=D.campaign_summary||{};const un=s.unmarked||0;
 if(un&&!UNMARKED_OK){UNMARKED_OK=true;say(un+" posts are not marked. Approve the campaign anyway? Unmarked posts are treated as Maybe.");return}
 try{const j=await post("/campaign-approve",{confirm_unmarked:un>0});D.campaign_approved=j.campaign_approval;UNMARKED_OK=false;paintCampaign();say("Campaign approved")}catch(e){say(e.message)}}
function paintCampaign(){document.querySelectorAll("[data-campaign-yes]").forEach(b=>{b.hidden=!D.campaign_can_approve||!!D.campaign_approved});const line=document.getElementById("campaignline");if(line&&D.campaign_summary)line.textContent=D.campaign_summary.line||"";if(D.campaign_approved&&line)line.textContent="Campaign approved by "+D.campaign_approved.by+"."}
function build(){const P=D.pack;const parts=(P.theme&&P.theme.name)?P.theme.name+": ":"";$("ttl").textContent="";$("ttl").append(document.createTextNode(parts),el("span","",P.title));
 if(D.can_remake){const rb=el("button","send","Remake from notes");rb.type="button";rb.style.marginTop="10px";rb.onclick=async()=>{try{await remakeNotes()}catch(e){say(e.message)}};$("ttl").after(rb)}
 paintMonthStrip();
 $("intro").textContent="Look at each post, then choose Approve, Reject or Hold. Leave a comment on anything, and upload your own photo where you have one. Your answers save as you go. When you have been through them all, press I'm done at the bottom.";
 if(D.catalog_line){const cl=$("catline");cl.hidden=false;cl.textContent=D.catalog_line}
 if(D.campaign_summary||D.campaign_approved){const cl=$("campaignline");cl.hidden=false;if(D.campaign_summary)cl.textContent=D.campaign_summary.line}
 document.querySelectorAll("[data-campaign-yes]").forEach(b=>{b.onclick=campaignYes});
 paintCampaign();
 if(P.notice){const n=$("notice");n.hidden=false;n.append(el("b","","Please note: "),document.createTextNode(P.notice))}
 const box=$("items");P.items.forEach(it=>{const c=el("section","card");c.dataset.id=it.id;c.tabIndex=-1;const h=el("div","head");const hh=el("div");hh.append(el("h2","",it.title));
  if(D.can_drag&&it.when){const chip=el("span","slot-chip",it.when);chip.draggable=true;chip.title="Drag to a day on the calendar strip";chip.ondragstart=e=>{DRAG_ITEM=it.id;e.dataTransfer.setData("text/plain",it.id)};hh.append(chip)}else{const m=[it.audience,it.when,it.channels].filter(Boolean).join("  ·  ");if(m)hh.append(el("p","meta",m))}
  if(it.channels&&D.can_drag)hh.append(el("p","meta",it.channels));else if(!D.can_drag){const m2=[it.audience,it.channels].filter(Boolean).join("  ·  ");if(m2)hh.append(el("p","meta",m2))}
  const bd=el("span","badge");bd.dataset.badge=it.id;h.append(hh,bd);if(D.staff)h.append(teamRemove(it));c.append(h);
  if(D.can_drag&&it.due){const mv=el("div","move-row");const inp=document.createElement("input");inp.type="date";inp.value=it.due;inp.setAttribute("aria-label","Move to day");const mb=el("button","pill","Move to…");mb.type="button";mb.onclick=async()=>{if(!inp.value)return;try{await post("/move-slot",{item:it.id,date:inp.value});say("Day updated");location.reload()}catch(e){say(e.message)}};mv.append(inp,mb);c.append(mv)}
  if(it.hidden_remake){const sb=el("button","pill","Show to Herman");sb.type="button";sb.onclick=()=>showRemake(it.id).catch(e=>say(e.message));c.append(sb)}
  if(it.images.length){const one=it.images.length===1;const g=el("div","grid"+(one?" one":"")+(it.kind==="choice"&&it.images.length>1?" choice":""));const latest=it.images.length-1;it.images.forEach((src,i)=>{const cell=el("div","cell");const im=new Image();const urls=it.size_urls||{};const isLatest=i===latest&&it.kind!=="choice";
    im.src=(isLatest&&urls.feed)?urls.feed:src;im.alt=it.title;
    if(it.kind==="choice"&&it.images.length>1){const L="ABC"[i];const o=el("button","opt");o.type="button";o.setAttribute("aria-label","Pick design option "+L);o.dataset.ch=it.id;o.dataset.v=L;o.setAttribute("aria-pressed","false");o.append(im,el("b","","Option "+L));o.onclick=()=>act(it.id,null,L);im.onclick=null;cell.append(o)}else{
      if(isLatest&&urls.feed){const tabs=el("div","size-tabs");tabs.setAttribute("role","tablist");tabs.setAttribute("aria-label","Picture size");[["feed","Feed"],["story","Story"],["google","Google"]].forEach(([k,l])=>{const b=el("button","pill",l);b.type="button";b.dataset.sizeTab=it.id;b.dataset.k=k;b.setAttribute("role","tab");b.setAttribute("aria-pressed",String(k==="feed"));b.onclick=()=>pickSize(it.id,k,im,urls);tabs.append(b)});cell.append(tabs)}
      if(!isLatest)cell.append(el("p","earlier","Earlier version"));
      im.onclick=()=>{const pick=SIZE_PICK.get(it.id)||"feed";const lb=(isLatest&&urls[pick])?[urls.feed,urls.story,urls.google].filter(Boolean):it.images;const at=isLatest?["feed","story","google"].indexOf(pick):i;openLB(lb,Math.max(0,at),it.title)};cell.append(im)}
    if(it.kind==="choice"&&it.images.length>1){const z=el("button","zoom","⤢");z.type="button";z.setAttribute("aria-label","View full screen");z.onclick=()=>openLB(it.images,i,it.title);cell.append(z)}g.append(cell)});c.append(g)}else{c.append(el("div","pic none","Picture to come"))}
  if(it.caption)c.append(el("div","cap",it.caption));if(it.note)c.append(el("p","meta",it.note));
  const r=el("div","row");["approve","reject","hold"].forEach(s=>{const b=el("button","pill "+s,LBL[s]);b.type="button";b.dataset.st=it.id;b.dataset.v=s;b.setAttribute("aria-pressed","false");b.onclick=()=>{const cur=D.decisions[it.id];act(it.id,s,cur&&cur.choice)};r.append(b)});c.append(r);
  const t=el("div","thread");t.append(el("h3","","Comments"));const tb=el("div");tb.dataset.th=it.id;t.append(tb,composer(it.id,tb));c.append(t);
  const ug=el("div");ug.dataset.ug=it.id;c.append(uploadBox(it.id),ug);box.append(c)});
 if(D.staff)$("finish").after(teamSection());
 const w=$("week");w.append(el("h2","","Your own photos for the week"),el("p","sub","Not tied to one post? Add them here."),uploadBox(""));const wg=el("div");wg.dataset.ug="";w.append(wg);
 const wt=el("div","thread");wt.append(el("h3","","General comments"));const wb=el("div");wb.dataset.th="";wt.append(wb,composer("",wb));w.append(wt);paint();const g0=document.querySelector('[data-ug=""]');if(g0){const u=uploadsGrid("");if(u)g0.append(u)};threadHTML(document.querySelector('[data-th=""]'),"")}
async function refresh(){try{const r=await fetch(BASE+"/data",{cache:"no-store"});if(!r.ok)return;const j=await r.json();D.decisions=j.decisions;D.comments=j.comments;if(j.pack&&j.pack.items.length!==D.pack.items.length){if(![...document.querySelectorAll("textarea")].some(t=>t.value.trim())){location.reload();return}say("A new post was added. Reload the page to see it.");return}D.uploads=j.uploads;D.done=j.done||[];paint();const g0=document.querySelector('[data-ug=""]');if(g0){g0.textContent="";const u=uploadsGrid("");if(u)g0.append(u)};threadHTML(document.querySelector('[data-th=""]'),"")}catch(e){}}
build();setInterval(()=>{if(!document.hidden)refresh()},20000);
</script></body></html>"""


def render_page(data: dict[str, Any], *, token: str) -> str:
    theme = data["pack"].get("theme") or {}
    grad = theme.get("gradient") or ["#D751F7", "#7C38F8", "#23A4F1"]
    css_grad = "linear-gradient(90deg," + ",".join(grad) + ")"
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    labels = data.get("labels") or {"approve": "Approve", "reject": "Reject", "hold": "Hold"}
    lbl = json.dumps(labels, ensure_ascii=False).replace("<", "\\u003c")
    safe_token = re.sub(r"[^A-Za-z0-9_.-]", "", token)
    return (_PAGE.replace("__TITLE__", html.escape(data["pack"]["title"]))
            .replace("__INK__", theme.get("ink", "#121528")).replace("__BG__", theme.get("bg", "#f6f4f1"))
            .replace("__ACCENT__", theme.get("accent", "#7c38f8")).replace("__GRAD__", css_grad)
            .replace("__LBL__", lbl)
            .replace("__DATA__", payload).replace("__TOKEN__", safe_token))


def render_bad_link_page() -> str:
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<meta name=robots content=noindex><title>Link not working</title>"
            "<body style='font:18px/1.5 system-ui,sans-serif;max-width:34rem;margin:15vh auto;padding:0 20px'>"
            "<h1 style='font-size:28px'>This link is not working</h1>"
            "<p>It may have expired, or it was copied a little short. Ask for a new link and we will send one.</p></body>")
