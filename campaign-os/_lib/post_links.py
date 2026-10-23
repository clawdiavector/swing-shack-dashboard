"""Post -> asset -> template links, written when Campaign OS publishes a post.

meta-post-index.json holds two lookups the What worked page uses:

  by_asset_id  { <asset_id>: link }   every post we published from an asset
  by_media_id  { <ig media id>: link } the same post, once Instagram's id is known

Before this module the publish path wrote neither. The links were only ever
filled by scripts/back_map_postiz_to_ig.py, which rebuilds the whole index and
was never run against production. The publish step now records the link as it
goes out, so "make another like this" does not depend on a later back-map.

Postiz returns its own post id when a post is created, not the Instagram media
id. The media id is recorded here only when the create response carries it;
otherwise by_asset_id keeps platform_media_id as None until it is known.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

INDEX_NAME = "meta-post-index.json"
MEDIA_ID_KEYS = ("platformMediaId", "platform_media_id")


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _load_index(path: Path) -> dict[str, Any]:
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"by_asset_id": {}, "by_media_id": {}, "external_publications": {}, "_meta": {}}


def record_publish_link(
    *,
    brand_id: str,
    asset_id: str,
    template_id: Optional[str],
    postiz_post_id: str,
    channel: str,
    platform_media_id: Optional[str] = None,
    published_at: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Write one publish link into meta-post-index.json and return it.

    Upserts by asset_id (a re-publish replaces the earlier link for that asset)
    and by platform_media_id when one is known. Other keys in the index are
    left alone.
    """
    if not asset_id or not postiz_post_id:
        raise ValueError("asset_id and postiz_post_id are required")
    media_id = str(platform_media_id).strip() if platform_media_id else None
    if media_id is not None and not media_id.isdigit():
        media_id = None

    path = (data_dir or _data_dir()) / INDEX_NAME
    index = _load_index(path)
    link = {
        "brand_id": brand_id,
        "asset_id": asset_id,
        "template_id": template_id or None,
        "postiz_post_id": postiz_post_id,
        "platform_media_id": media_id,
        "channel": channel,
        "published_at": published_at,
        "link_source": "publish-path",
    }
    index.setdefault("by_asset_id", {})[asset_id] = link
    if media_id is not None:
        index.setdefault("by_media_id", {})[media_id] = link
    index["count"] = len(index.get("by_media_id") or {})

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return link


def _template_id_for_asset(asset_id: str) -> Optional[str]:
    sidecar = _data_dir() / "draft-assets" / f"{asset_id}.json"
    if not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return str(data.get("template_id") or data.get("archetype_id") or "").strip() or None


def _media_id_from_response(post: dict[str, Any]) -> Optional[str]:
    for key in MEDIA_ID_KEYS:
        value = post.get(key)
        if value and str(value).isdigit():
            return str(value)
    return None


def record_from_queue_row(
    row: dict[str, Any],
    *,
    brand_id: str,
    postiz_post_id: str,
    post_response: dict[str, Any],
    published_at: Optional[str],
) -> Optional[dict[str, Any]]:
    """Record the link for a queue row that was just sent to Postiz.

    Returns None when the row is not tied to an asset (an inbox item with no
    asset id), since there is nothing to link.
    """
    asset_id = str(row.get("post_id") or "").strip()
    if not asset_id:
        from _lib.unified_inbox import asset_id_from_queue_row  # noqa: PLC0415

        asset_id = str(asset_id_from_queue_row(row) or "").strip()
    if not asset_id:
        return None
    return record_publish_link(
        brand_id=brand_id,
        asset_id=asset_id,
        template_id=_template_id_for_asset(asset_id),
        postiz_post_id=postiz_post_id,
        channel=str(row.get("platform") or "instagram"),
        platform_media_id=_media_id_from_response(post_response),
        published_at=published_at,
    )
