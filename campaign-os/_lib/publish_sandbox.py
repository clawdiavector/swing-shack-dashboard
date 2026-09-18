"""Sandbox publish adapter — receipts + queue under $DATA_DIR/publish-sandbox/. No outbound HTTP."""

from __future__ import annotations

import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from _lib.brand_validate import validate_brand_id

SANDBOX_CONFIG_SCHEMA = "campaign-os/publish-sandbox/v1"
RECEIPT_SCHEMA = "campaign-os/publish-receipt/v1"
QUEUE_SCHEMA = "campaign-os/publish-queue-item/v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def sandbox_dir() -> Path:
    override = os.environ.get("PUBLISH_SANDBOX_DIR")
    if override:
        return Path(override)
    return _data_dir() / "publish-sandbox"


def _config_path() -> Path:
    return sandbox_dir() / "config.json"


def _queue_path() -> Path:
    return sandbox_dir() / "queue.jsonl"


def _receipts_path() -> Path:
    return sandbox_dir() / "receipts.jsonl"


def _mirror_path() -> Path:
    return sandbox_dir() / "postiz-mirror.json"


def ensure_sandbox_layout() -> Path:
    root = sandbox_dir()
    root.mkdir(parents=True, exist_ok=True)
    cfg = _config_path()
    if not cfg.is_file():
        cfg.write_text(
            json.dumps(
                {
                    "schema": SANDBOX_CONFIG_SCHEMA,
                    "mode": "sandbox",
                    "created_at": _utc_now_iso(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return root


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    ensure_sandbox_layout()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _rewrite_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_sandbox_layout()
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    path.write_text(text, encoding="utf-8")


def _receipt_index() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rec in _read_jsonl(_receipts_path()):
        key = rec.get("idempotency_key")
        if key:
            out[str(key)] = rec
    return out


def enqueue_item(
    *,
    brand_id: str,
    platform: str = "instagram",
    channel: str = "postiz",
    caption_preview: str = "",
    inbox_item_id: Optional[str] = None,
    human_approved: bool = False,
    would_publish_at: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict[str, Any]:
    """Append a pending queue row (no network)."""
    ensure_sandbox_layout()
    brand_id = validate_brand_id(brand_id)
    key = idempotency_key or f"sb-{brand_id}-{platform}-{secrets.token_hex(8)}"
    item = {
        "schema": QUEUE_SCHEMA,
        "queue_id": str(uuid.uuid4()),
        "inbox_item_id": inbox_item_id,
        "brand_id": brand_id,
        "channel": channel,
        "platform": platform,
        "caption_preview": (caption_preview or "")[:500],
        "idempotency_key": key,
        "human_approved": bool(human_approved),
        "human_approved_at": _utc_now_iso() if human_approved else None,
        "status": "pending",
        "would_publish_at": would_publish_at,
        "created_at": _utc_now_iso(),
    }
    _append_jsonl(_queue_path(), item)
    return item


def approve_item(idempotency_key: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Mark a pending queue item human-approved."""
    rows = _read_jsonl(_queue_path())
    found: Optional[dict[str, Any]] = None
    for row in rows:
        if row.get("idempotency_key") == idempotency_key and row.get("status") == "pending":
            row["human_approved"] = True
            row["human_approved_at"] = _utc_now_iso()
            found = row
            break
    if not found:
        return None, "queue item not found or not pending"
    _rewrite_jsonl(_queue_path(), rows)
    return found, None


def dispatch_item(item: dict[str, Any]) -> tuple[dict[str, Any], Optional[str]]:
    """Write sandbox receipt for one approved item. Idempotent on idempotency_key."""
    if not item.get("human_approved"):
        return {}, "human_approved required"

    key = str(item.get("idempotency_key") or "")
    if not key:
        return {}, "idempotency_key required"

    try:
        brand_id = validate_brand_id(item.get("brand_id"))
    except ValueError as exc:
        return {}, str(exc)

    existing = _receipt_index().get(key)
    if existing:
        return existing, None

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "mode": "sandbox",
        "inbox_item_id": item.get("inbox_item_id"),
        "brand_id": brand_id,
        "channel": item.get("channel", "postiz"),
        "platform": item.get("platform", "instagram"),
        "idempotency_key": key,
        "human_approved_at": item.get("human_approved_at"),
        "dispatched_at": _utc_now_iso(),
        "sandbox_post_id": f"sb-post-{uuid.uuid4()}",
        "caption_preview": (item.get("caption_preview") or "")[:120],
        "would_publish_at": item.get("would_publish_at"),
    }
    _append_jsonl(_receipts_path(), receipt)
    _update_mirror(receipt)
    return receipt, None


def dispatch_pending() -> dict[str, Any]:
    """Process all pending + human_approved queue rows. Job entrypoint helper."""
    ensure_sandbox_layout()
    rows = _read_jsonl(_queue_path())
    receipts_index = _receipt_index()
    dispatched = 0
    refused = 0
    skipped = 0
    errors: list[str] = []

    updated_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "pending":
            updated_rows.append(row)
            continue
        if not row.get("human_approved"):
            skipped += 1
            updated_rows.append(row)
            continue
        key = str(row.get("idempotency_key") or "")
        if key in receipts_index:
            row["status"] = "dispatched"
            row["dispatched_at"] = receipts_index[key].get("dispatched_at")
            dispatched += 1
            updated_rows.append(row)
            continue
        receipt, err = dispatch_item(row)
        if err:
            refused += 1
            errors.append(f"{key}: {err}")
            updated_rows.append(row)
            continue
        row["status"] = "dispatched"
        row["dispatched_at"] = receipt.get("dispatched_at")
        row["sandbox_post_id"] = receipt.get("sandbox_post_id")
        dispatched += 1
        updated_rows.append(row)

    _rewrite_jsonl(_queue_path(), updated_rows)
    return {
        "ok": True,
        "mode": "sandbox",
        "dispatched": dispatched,
        "refused": refused,
        "skipped_unapproved": skipped,
        "errors": errors[:20],
        "writes": ["publish-sandbox/queue.jsonl", "publish-sandbox/receipts.jsonl"],
    }


def _update_mirror(receipt: dict[str, Any]) -> None:
    mirror = {"schema": "campaign-os/postiz-mirror-sandbox/v1", "posts": []}
    mp = _mirror_path()
    if mp.is_file():
        try:
            mirror = json.loads(mp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    posts = mirror.get("posts")
    if not isinstance(posts, list):
        posts = []
    posts.append(
        {
            "id": receipt.get("sandbox_post_id"),
            "brand_id": receipt.get("brand_id"),
            "platform": receipt.get("platform"),
            "caption": receipt.get("caption_preview"),
            "status": "sandbox_scheduled",
            "dispatched_at": receipt.get("dispatched_at"),
        }
    )
    mirror["posts"] = posts[-100:]
    mirror["updated_at"] = _utc_now_iso()
    mp.write_text(json.dumps(mirror, indent=2), encoding="utf-8")


def summary() -> dict[str, Any]:
    ensure_sandbox_layout()
    queue = _read_jsonl(_queue_path())
    receipts = _read_jsonl(_receipts_path())
    pending = sum(1 for q in queue if q.get("status") == "pending")
    pending_approved = sum(
        1 for q in queue if q.get("status") == "pending" and q.get("human_approved")
    )
    last_receipt = receipts[-1] if receipts else None
    return {
        "ok": True,
        "mode": "sandbox",
        "queue_depth": pending,
        "queue_approved_ready": pending_approved,
        "receipt_count": len(receipts),
        "last_receipt_at": last_receipt.get("dispatched_at") if last_receipt else None,
        "last_sandbox_post_id": last_receipt.get("sandbox_post_id") if last_receipt else None,
        "dir": str(sandbox_dir()),
    }
