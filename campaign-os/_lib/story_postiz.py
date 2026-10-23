"""Publish a story-list row to Instagram through Postiz.

The card is drawn here from the brand, the note, and the link text. The
Instagram or Facebook post is not downloaded. Live calls run only when
PUBLISH_MODE=live, the same switch as the feed publisher.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from _lib import story_queue
from _lib.postiz_client import create_post, list_integrations, postiz_status, upload_media
from _lib.publish_live import _integration_for_platform, _normalize_integrations

log = logging.getLogger("story_postiz")

_LABELS = {
    "swing-shack": "Swing Shack",
    "stick": "Stick",
    "bag-drop": "Bag Drop",
}


def live_mode() -> bool:
    return (os.environ.get("PUBLISH_MODE") or "sandbox").strip().lower() == "live"


def render_story_png(brand: str, note: str, url: str, dest: Path) -> None:
    """Write a 1080×1920 card. Text only — never the source post's media."""
    image = Image.new("RGB", (1080, 1920), (18, 18, 20))
    draw = ImageDraw.Draw(image)
    title = ImageFont.load_default(size=64)
    body = ImageFont.load_default(size=36)
    label = _LABELS.get(brand, brand)
    draw.text((80, 640), label, fill=(255, 255, 255), font=title)
    y = 760
    for line in _wrap(draw, (note or "Story").strip()[:180], body, 920)[:6]:
        draw.text((80, y), line, fill=(230, 230, 230), font=body)
        y += 52
    y += 36
    for line in _wrap(draw, (url or "").strip(), body, 920)[:3]:
        draw.text((80, y), line, fill=(150, 150, 155), font=body)
        y += 48
    image.save(dest, "PNG")


def _wrap(draw, text: str, font, width: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if draw.textlength(trial, font=font) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _postiz_id(result) -> str:
    if isinstance(result, list) and result:
        result = result[0]
    if not isinstance(result, dict):
        return ""
    found = result.get("id") or result.get("postId") or (result.get("post") or {}).get("id")
    return str(found or "")


def publish_item(item: dict) -> dict:
    """Publish one open story row. Returns a JSON-ready dict with optional status."""
    if item.get("status") != "open":
        return {"ok": False, "error": "story is already closed", "status": 409}
    if not live_mode():
        return {
            "ok": True,
            "dry_run": True,
            "error": "Postiz sandbox is on. Nothing was published.",
        }

    brand = str(item.get("brand") or "")
    if not postiz_status(brand_id=brand).get("configured"):
        return {"ok": False, "error": f"Postiz is not configured for {brand}", "status": 409}

    raw, err = list_integrations(brand_id=brand)
    if err:
        log.warning("story postiz list_integrations failed code=%s", err[0])
        return {"ok": False, "error": "Could not read Postiz accounts", "status": 502}
    integration_id = _integration_for_platform(_normalize_integrations(raw), "instagram")
    if not integration_id:
        return {"ok": False, "error": "No Instagram account connected in Postiz for this brand", "status": 409}

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        render_story_png(brand, str(item.get("note") or ""), str(item.get("url") or ""), Path(path))
        data, up_err = upload_media(path, brand_id=brand)
        if up_err or not isinstance(data, dict):
            log.warning("story postiz upload failed")
            return {"ok": False, "error": "Postiz media upload failed", "status": 502}
        media_id = data.get("id") or data.get("mediaId")
        media_path = data.get("path")
        if not media_id or not media_path:
            return {"ok": False, "error": "Postiz media upload returned no id", "status": 502}
        content = (str(item.get("note") or "").strip() or "Story")[:280]
        result, post_err = create_post(
            integration_id=integration_id,
            content=content,
            media=[{"id": str(media_id), "path": str(media_path)}],
            brand_id=brand,
            platform_settings={"post_type": "story"},
        )
        if post_err:
            log.warning("story postiz create_post failed code=%s", post_err[0])
            return {"ok": False, "error": "Postiz rejected the story", "status": 502}
        post_id = _postiz_id(result)
        if not post_id:
            return {"ok": False, "error": "Postiz did not return a post id", "status": 502}
        saved = story_queue.record_post(str(item["id"]), post_id)
        return {"ok": True, "dry_run": False, "postiz_post_id": post_id, "item": saved}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
