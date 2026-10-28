"""9:16 companion renders for an approved feed post (story, TikTok, YouTube Shorts)."""

from __future__ import annotations

import io
from typing import Any

FEED_RENDER_CHANNEL = "instagram"
VERTICAL_RENDER_CHANNELS: tuple[str, ...] = (
    "instagram_story",
    "tiktok",
    "youtube_shorts",
)

_FEED_ASPECT = (4 / 5, 1.91)
_STORY_ASPECT = 9 / 16
_OUT_WIDTH = 1080

_PLATFORM_COMPOSED_ALIASES: dict[str, str] = {
    "youtube": "youtube_shorts",
}


def is_vertical_channel(channel: str) -> bool:
    ch = (channel or "").strip().lower()
    if not ch:
        return False
    if "story" in ch or "reel" in ch or "shorts" in ch:
        return True
    return ch in ("tiktok",)


def render_channel_keys(brand_id: str) -> list[str]:
    _ = brand_id
    return [FEED_RENDER_CHANNEL, *VERTICAL_RENDER_CHANNELS]


def composed_key_for_platform(platform: str) -> str:
    from _lib.jobs.layer5.image_draft_context import _normalize_platform  # noqa: PLC0415

    plat = _normalize_platform(platform)
    return _PLATFORM_COMPOSED_ALIASES.get(plat, plat)


def _blur_fill(im: Any, target: float) -> Any:
    """Whole image centred on a blurred, darkened cover copy of itself (nothing cut off)."""
    from PIL import Image, ImageEnhance, ImageFilter  # noqa: PLC0415

    w, h = im.size
    if w / h > target:
        cw, ch = w, round(w / target)
    else:
        cw, ch = round(h * target), h
    scale = max(cw / w, ch / h)
    bg = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.LANCZOS)
    left = (bg.size[0] - cw) // 2
    top = (bg.size[1] - ch) // 2
    bg = bg.crop((left, top, left + cw, top + ch))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=max(cw, ch) / 40))
    bg = ImageEnhance.Brightness(bg).enhance(0.6)
    bg.paste(im, ((cw - w) // 2, (ch - h) // 2))
    return bg


def fit_for_channel_png(src: Any, channel: str) -> tuple[bytes, str | None]:
    """Size a finished image for one channel. Returns (PNG bytes, note or None).

    Vertical channels (story, TikTok, Shorts) never crop: the whole feed post sits
    on a blurred fill so template text and badges near the edges stay visible.
    """
    from PIL import Image  # noqa: PLC0415

    if hasattr(src, "convert"):
        im = src.convert("RGB")
    else:
        with Image.open(io.BytesIO(src)) as opened:
            im = opened.convert("RGB")
    w, h = im.size
    aspect = w / h
    note = None
    if is_vertical_channel(channel):
        if abs(_STORY_ASPECT - aspect) > 0.005:
            im = _blur_fill(im, _STORY_ASPECT)
    else:
        target = min(max(aspect, _FEED_ASPECT[0]), _FEED_ASPECT[1])
        if abs(target - aspect) > 0.005:
            if aspect > target:
                nw = round(h * target)
                left = (w - nw) // 2
                im = im.crop((left, 0, left + nw, h))
            else:
                nh = round(w / target)
                top = (h - nh) // 2
                im = im.crop((0, top, w, top + nh))
            note = (
                f"{channel}: cropped {w}x{h} to {target:.3f}:1 — check no type was cut off"
            )
    out_h = round(_OUT_WIDTH * im.size[1] / im.size[0])
    im = im.resize((_OUT_WIDTH, out_h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG", compress_level=6)
    return buf.getvalue(), note


def add_vertical_renders(
    brand: str,
    slug: str,
    placed: dict[str, str],
    *,
    feed_png: bytes | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Fill missing vertical channel URLs in ``placed`` from the feed image."""
    if not placed.get(FEED_RENDER_CHANNEL) and not feed_png:
        return placed, []
    notes: list[str] = []
    if feed_png is None:
        feed_png = _load_png_for_url(brand, placed.get(FEED_RENDER_CHANNEL) or "")
    if not feed_png:
        return placed, notes

    render_post = _render_post_module()
    out = dict(placed)
    for channel in VERTICAL_RENDER_CHANNELS:
        if out.get(channel):
            continue
        png, note = fit_for_channel_png(feed_png, channel)
        published = render_post.publish_into_campaign_os(brand, slug, channel, png)
        out[channel] = published["url"]
        if note:
            notes.append(note)
    return out, notes


def vertical_renders_from_composed(composed: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(composed, dict):
        return []
    labels = {
        "instagram_story": "Instagram story",
        "tiktok": "TikTok",
        "youtube_shorts": "YouTube Shorts",
    }
    rows: list[dict[str, str]] = []
    for ch in VERTICAL_RENDER_CHANNELS:
        url = str(composed.get(ch) or "").strip()
        if url:
            rows.append({"channel": ch, "label": labels.get(ch, ch), "url": url})
    return rows


def ensure_vertical_composed_for_asset(
    *,
    brand_id: str,
    asset_id: str,
    slug: str | None = None,
) -> dict[str, Any]:
    """Idempotently add story / TikTok / Shorts renders when only the feed exists."""
    from _lib.unified_inbox import (  # noqa: PLC0415
        _load_campaign_data,
        _write_campaign_data,
        _load_draft_sidecar,
    )

    data = _load_campaign_data()
    asset = None
    for campaign in (data.get("campaigns") or {}).values():
        if not isinstance(campaign, dict):
            continue
        row = (campaign.get("assets") or {}).get(asset_id)
        if isinstance(row, dict):
            asset = row
            break
    if not asset:
        return {"ok": False, "error": "asset not found"}
    composed = dict(asset.get("composed") or {})
    sidecar = _load_draft_sidecar(asset_id)
    if isinstance(sidecar.get("composed"), dict):
        composed.update(sidecar["composed"])

    missing = [ch for ch in VERTICAL_RENDER_CHANNELS if not composed.get(ch)]
    if not missing or not composed.get(FEED_RENDER_CHANNEL):
        return {"ok": True, "updated": False, "composed": composed}

    if slug:
        slug = slug.strip()
    elif asset_id.startswith(f"{brand_id}-"):
        slug = asset_id[len(brand_id) + 1 :]
    else:
        slug = asset_id
    merged, _notes = add_vertical_renders(brand_id, slug, composed)
    if merged == composed:
        return {"ok": True, "updated": False, "composed": composed}

    asset["composed"] = merged
    _write_campaign_data(data)
    sidecar_path = _data_dir() / "draft-assets" / f"{asset_id}.json"
    if sidecar_path.is_file():
        sidecar = _load_draft_sidecar(asset_id)
        sidecar["composed"] = merged
        try:
            import json

            sidecar_path.write_text(
                json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
    return {"ok": True, "updated": True, "composed": merged, "added": missing}


def _data_dir():
    import os
    from pathlib import Path

    explicit = os.environ.get("DATA_DIR") or os.environ.get("CAMPAIGN_OS_DATA_DIR")
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve().parent
    return here.parent / "data"


def _load_png_for_url(brand: str, url: str) -> bytes | None:
    from pathlib import Path

    url = (url or "").strip()
    prefix = f"/brand-images/{brand}/"
    if not url.startswith(prefix):
        return None
    name = url[len(prefix) :]
    path = _data_dir() / "draft-assets" / "images" / brand / name
    if not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def _render_post_module():
    from _lib.jobs.layer5 import render_batch  # noqa: PLC0415

    return render_batch._scripts_module("render_post")
