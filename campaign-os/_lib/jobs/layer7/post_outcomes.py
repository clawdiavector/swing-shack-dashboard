"""Join IG posts, GA4-derived scores, and publish receipts → post-outcomes.json."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..layer1._io import as_dict, as_list, io_for_job, utc_now_iso

JOB_NAME = "post_outcomes"
from _lib import feedback_loop as fb

OUTPUT = "post-outcomes.json"
SCHEMA = "campaign-os/post-outcomes/v1"
DEFAULT_BRAND = "stick"
WINDOW_DAYS = 30

HOOK_THEMES = {
    "club_fitting": ["fitting", "fitted", "club", "driver", "iron", "sub 70", "avoda", "miura", "takomo"],
    "wrong_ball": ["wrong ball", "ball fitting"],
    "golf_lessons": ["lesson", "coach", "cat", "dave", "coaching", "putting", "short game"],
    "golf_humor": ["spirit", "lovely", "same old setup", "off-the-rack", "golf is", "golf's"],
    "trackman_stats": ["trackman", "data", "stat", "yard", "metric"],
    "booking_cta": ["book your", "book today", "book a", "dm us"],
}


def _data_dir() -> Path:
    return Path(__import__("os").environ.get("DATA_DIR", "/data"))


def _read_jsonl(name: str) -> list[dict[str, Any]]:
    path = _data_dir() / name
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


def _caption_to_hook_id(caption: str) -> str:
    first_line = (caption or "").split("\n")[0]
    return re.sub(r"[^a-z0-9]+", "-", first_line.lower()).strip("-")[:50]


def _classify_themes(caption: str) -> list[str]:
    cap = (caption or "").lower()
    return [theme for theme, kws in HOOK_THEMES.items() if any(kw in cap for kw in kws)]


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text.replace("+0000", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _in_window(ts: str | None, *, cutoff: datetime) -> bool:
    parsed = _parse_ts(ts)
    if parsed is None:
        return True
    return parsed >= cutoff


def _conversion_index(conversion_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in as_list(conversion_doc.get("posts_ranked")):
        if not isinstance(row, dict):
            continue
        hook_id = str(row.get("hook_id") or "")
        post_id = str(row.get("post_id") or "")
        if hook_id:
            out[f"hook:{hook_id}"] = row
        if post_id:
            out[f"post:{post_id}"] = row
    return out


def _join_receipt(
    receipt: dict[str, Any],
    ig_by_hook: dict[str, dict[str, Any]],
    ig_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    inbox_id = str(receipt.get("inbox_item_id") or "")
    caption = str(receipt.get("caption_preview") or "")
    slug = _caption_to_hook_id(caption)
    if slug and slug in ig_by_hook:
        return ig_by_hook[slug], "hook_id"
    if inbox_id.startswith("draft_asset:"):
        parts = inbox_id.split(":")
        if len(parts) >= 3:
            asset_key = parts[-1]
            for post in ig_by_id.values():
                if str(post.get("asset_id") or "") == asset_key:
                    return post, "inbox_item_id"
    if slug:
        for post in ig_by_id.values():
            post_ts = _parse_ts(str(post.get("timestamp") or ""))
            if post_ts and slug == str(post.get("hook_id") or ""):
                return post, "timestamp"
    return None, "receipt_only"


def _build_outcome_row(
    post: dict[str, Any],
    *,
    brand_id: str,
    conversion_row: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
    join_basis: str,
) -> dict[str, Any]:
    metrics = post.get("metrics") if isinstance(post.get("metrics"), dict) else {}
    caption = str(post.get("caption_preview") or post.get("caption") or "")
    reach = int(metrics.get("reach") or post.get("reach") or 0)
    signal = {
        "reach": reach,
        "likes": int(metrics.get("likes") or 0),
        "comments": int(metrics.get("comments") or 0),
        "saves": int(metrics.get("saved") or metrics.get("saves") or 0),
        "link_clicks": int(metrics.get("link_clicks") or 0),
        "ga_sessions": int((conversion_row or {}).get("direct_attributed_sessions") or 0),
        "bookings": int((conversion_row or {}).get("bookings") or 0),
    }
    score = fb.compute_score(signal)
    has_conversion = signal["ga_sessions"] > 0 or signal["bookings"] > 0 or signal["link_clicks"] > 0
    themes = _classify_themes(caption)
    media_type = str(post.get("media_type") or "IMAGE")
    evidence = [{"source": "ig-business-analytics.json", "ref": str(post.get("id") or "")}]
    if receipt:
        evidence.append({"source": "publish-sandbox/receipts.jsonl", "ref": str(receipt.get("sandbox_post_id") or receipt.get("idempotency_key") or "")})

    return {
        "recipe_id": str(post.get("id") or post.get("hook_id") or ""),
        "post_id": str(post.get("id") or ""),
        "brand_id": brand_id,
        "hook_id": str(post.get("hook_id") or _caption_to_hook_id(caption)),
        "caption_preview": caption[:100],
        "permalink": str(post.get("permalink") or ""),
        "timestamp": str(post.get("timestamp") or ""),
        "format_type": "reel" if media_type == "VIDEO" else "image",
        "themes": themes,
        "reach": reach,
        "score": score,
        "score_basis": "conversion_backed" if has_conversion else "engagement_only",
        "direct_attributed_sessions": signal["ga_sessions"],
        "join_basis": join_basis,
        "inbox_item_id": str((receipt or {}).get("inbox_item_id") or ""),
        "evidence": evidence,
    }


def run(*, brand: str | None = None) -> dict:
    """Build post-outcomes.json from IG analytics + optional conversion + receipts."""
    io = io_for_job(JOB_NAME, brand)
    ig_doc = as_dict(io.read("ig-business-analytics.json"))
    media = as_list(ig_doc.get("media"))
    if not media:
        return {"ok": False, "error": "ig-business-analytics.json missing or empty — run meta_refresh first"}

    conversion_doc = as_dict(io.read("post-conversion-score.json"))
    conversion_index = _conversion_index(conversion_doc)
    receipts = _read_jsonl("publish-sandbox/receipts.jsonl")

    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    ig_by_hook: dict[str, dict[str, Any]] = {}
    ig_by_id: dict[str, dict[str, Any]] = {}
    for post in media:
        if not isinstance(post, dict):
            continue
        if not _in_window(str(post.get("timestamp") or ""), cutoff=cutoff):
            continue
        post_id = str(post.get("id") or "")
        hook_id = str(post.get("hook_id") or _caption_to_hook_id(str(post.get("caption_preview") or "")))
        post = {**post, "hook_id": hook_id}
        if post_id:
            ig_by_id[post_id] = post
        if hook_id:
            ig_by_hook.setdefault(hook_id, post)

    joined_receipts: set[str] = set()
    outcomes: list[dict[str, Any]] = []

    for receipt in receipts:
        if str(receipt.get("schema") or "") != "campaign-os/publish-receipt/v1":
            continue
        post, join_basis = _join_receipt(receipt, ig_by_hook, ig_by_id)
        if not post:
            continue
        post_id = str(post.get("id") or "")
        conv = conversion_index.get(f"post:{post_id}") or conversion_index.get(f"hook:{post.get('hook_id')}")
        outcomes.append(_build_outcome_row(
            post,
            brand_id=str(receipt.get("brand_id") or DEFAULT_BRAND),
            conversion_row=conv,
            receipt=receipt,
            join_basis=join_basis,
        ))
        joined_receipts.add(post_id)

    for post in ig_by_id.values():
        post_id = str(post.get("id") or "")
        if post_id in joined_receipts:
            continue
        conv = conversion_index.get(f"post:{post_id}") or conversion_index.get(f"hook:{post.get('hook_id')}")
        outcomes.append(_build_outcome_row(
            post,
            brand_id=DEFAULT_BRAND,
            conversion_row=conv,
            receipt=None,
            join_basis="ig_only",
        ))

    ranked = fb.rank_outcomes(outcomes, window_days=WINDOW_DAYS)
    any_conversion = any(str(o.get("score_basis")) == "conversion_backed" for o in ranked)

    payload = {
        "schema": SCHEMA,
        "generated_at": utc_now_iso(),
        "generated_by": "layer7/post_outcomes.py",
        "window_days": WINDOW_DAYS,
        "score_basis": "conversion_backed" if any_conversion else "engagement_only",
        "posts_total": len(ranked),
        "receipts_joined": len(joined_receipts),
        "outcomes": ranked,
    }
    io.write(OUTPUT, payload)
    return {"ok": True, "rows": len(ranked)}
