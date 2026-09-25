"""Brand Visuals tab API — social grid, Drive assets, reference curation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from _lib import reference_dna as ref_dna_mod


def brand_directory_root() -> Path:
    runtime = os.environ.get("DATA_DIR")
    if runtime:
        root = Path(runtime) / "brand-directory"
        root.mkdir(parents=True, exist_ok=True)
        return root
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    if bundled:
        return Path(bundled) / "brand-directory"
    return Path("/data/campaign-os") / "brand-directory"


def _reference_index(brand_id: str, root: Path) -> dict[str, dict[str, Any]]:
    """Map curator asset id and ref_id → reference DNA row."""
    by_curator: dict[str, dict[str, Any]] = {}
    for row in ref_dna_mod.list_reference_dnas(brand_id, root):
        ref_id = str(row.get("ref_id") or "")
        if ref_id:
            by_curator[ref_id] = row
        curator = str(row.get("curator_id") or row.get("source_asset_id") or "")
        if curator:
            by_curator[curator] = row
    return by_curator


def _social_thumb_url(brand_id: str, platform: str, post_id: str) -> str:
    media_dir = brand_directory_root() / brand_id / "social" / platform / "media"
    if media_dir.is_dir():
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            if (media_dir / f"{post_id}{ext}").is_file():
                fn = f"{post_id}{ext}"
                return f"/api/visual-library/{brand_id}/image/{fn}"
    return f"/api/visual-library/{brand_id}/image/{post_id}.jpg"


def list_visuals_payload(
    brand_id: str,
    *,
    platform: str = "",
    root: Path | None = None,
) -> dict[str, Any]:
    root = root or brand_directory_root()
    ref_index = _reference_index(brand_id, root)
    plat_filter = platform.strip().lower()

    social_out: list[dict[str, Any]] = []
    for plat in ("instagram", "facebook"):
        if plat_filter and plat != plat_filter:
            continue
        posts_path = root / brand_id / "social" / plat / "posts.json"
        if not posts_path.is_file():
            continue
        try:
            payload = json.loads(posts_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        posts = payload.get("posts") or []
        if not isinstance(posts, list):
            continue
        sorted_posts = sorted(
            posts,
            key=lambda p: str((p or {}).get("publish_date") or ""),
            reverse=True,
        )[:24]
        for post in sorted_posts:
            if not isinstance(post, dict):
                continue
            post_id = str(post.get("source_id") or post.get("id") or "")
            if not post_id:
                continue
            ref_row = ref_index.get(post_id)
            social_out.append(
                {
                    "id": post_id,
                    "platform": plat,
                    "thumb_url": _social_thumb_url(brand_id, plat, post_id),
                    "caption": post.get("caption_preview") or post.get("caption_full") or "",
                    "posted_at": post.get("publish_date"),
                    "metrics": post.get("performance") or post.get("metrics") or {},
                    "is_reference": bool(ref_row and ref_row.get("is_learnable")),
                }
            )

    drive_out: list[dict[str, Any]] = []
    images_dir = root / brand_id / "images"
    if images_dir.is_dir():
        for img in sorted(images_dir.iterdir()):
            if not img.is_file():
                continue
            if img.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            stem = img.stem
            ref_row = ref_index.get(stem) or ref_index.get(img.name)
            folder = "images"
            drive_out.append(
                {
                    "id": stem,
                    "folder": folder,
                    "thumb_url": f"/api/visual-library/{brand_id}/image/{img.name}",
                    "is_reference": bool(ref_row and ref_row.get("is_learnable")),
                }
            )

    references = [
        _reference_summary(row, brand_id)
        for row in ref_dna_mod.list_reference_dnas(brand_id, root)
        if row.get("is_learnable")
    ]

    return {
        "social": social_out,
        "drive": drive_out,
        "references": references,
    }


def _reference_summary(row: dict[str, Any], brand_id: str) -> dict[str, Any]:
    ref_id = str(row.get("ref_id") or "")
    thumb = row.get("thumbnail")
    thumb_url = f"/api/image/references/{brand_id}/{ref_id}/thumbnail"
    if isinstance(thumb, str) and thumb:
        thumb_url = f"/api/visual-library/{brand_id}/image/{Path(thumb).name}"
    return {
        "id": ref_id,
        "curator_id": row.get("curator_id") or row.get("source_asset_id"),
        "platform": row.get("platform"),
        "pillar": row.get("pillar"),
        "source": row.get("source"),
        "label": row.get("label"),
        "thumb_url": thumb_url,
        "palette": row.get("palette") or [],
        "created": row.get("created"),
    }


def list_references(brand_id: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    root = root or brand_directory_root()
    return [_reference_summary(row, brand_id) for row in ref_dna_mod.list_reference_dnas(brand_id, root)]


def _resolve_social_image(
    brand_id: str,
    asset_id: str,
    platform: str,
    root: Path,
) -> Path:
    plat = (platform or "instagram").lower()
    media_dir = root / brand_id / "social" / plat / "media"
    if media_dir.is_dir():
        for p in media_dir.iterdir():
            if p.is_file() and p.stem == asset_id:
                return p
    posts_path = root / brand_id / "social" / plat / "posts.json"
    if posts_path.is_file():
        try:
            posts = json.loads(posts_path.read_text(encoding="utf-8")).get("posts") or []
        except Exception:
            posts = []
        for post in posts:
            if str((post or {}).get("source_id") or "") != asset_id:
                continue
            media_url = (post or {}).get("media_url") or (post or {}).get("thumbnail_url")
            if media_url:
                ref = ref_dna_mod.ingest_url(
                    str(media_url),
                    brand_id,
                    label=f"social-{asset_id}",
                    root=root,
                )
                src = ref.get("source_path")
                if src and Path(src).is_file():
                    return Path(src)
    raise FileNotFoundError(f"social media not found for id={asset_id!r} platform={plat!r}")


def _resolve_drive_image(brand_id: str, asset_id: str, root: Path) -> Path:
    images_dir = root / brand_id / "images"
    for name in (asset_id, f"{asset_id}.jpg", f"{asset_id}.png", f"{asset_id}.jpeg"):
        candidate = images_dir / name
        if candidate.is_file():
            return candidate
    matches = list(images_dir.glob(f"{asset_id}.*"))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"drive image not found: {asset_id!r}")


def mark_reference(
    brand_id: str,
    body: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    root = root or brand_directory_root()
    source = str(body.get("source") or "").lower()
    asset_id = str(body.get("id") or "").strip()
    if source not in ("social", "drive"):
        raise ValueError("source must be social or drive")
    if not asset_id:
        raise ValueError("id required")

    platform = str(body.get("platform") or "").strip()
    pillar = str(body.get("pillar") or "").strip()
    note = str(body.get("note") or "").strip()

    if source == "social":
        image_path = _resolve_social_image(brand_id, asset_id, platform, root)
        ref = ref_dna_mod.ingest_local_image(
            image_path,
            brand_id,
            label=note or f"social-{asset_id}",
            tags=[f"platform:{platform or 'instagram'}"] if platform else None,
            copy=True,
            root=root,
        )
    else:
        image_path = _resolve_drive_image(brand_id, asset_id, root)
        ref = ref_dna_mod.ingest_local_image(
            image_path,
            brand_id,
            label=note or asset_id,
            copy=True,
            root=root,
        )

    ref["is_learnable"] = True
    ref["source"] = source
    ref["curator_id"] = asset_id
    ref["source_asset_id"] = asset_id
    if platform:
        ref["platform"] = platform.lower()
    if pillar:
        ref["pillar"] = pillar
    if note:
        ref["note"] = note
    ref_dna_mod.save_reference_dna(ref, brand_id, root)
    return _reference_summary(ref, brand_id)


def unmark_reference(
    brand_id: str,
    ref_or_asset_id: str,
    *,
    root: Path | None = None,
) -> bool:
    root = root or brand_directory_root()
    ref_id = ref_or_asset_id
    if not ref_id.startswith("ref-"):
        index = _reference_index(brand_id, root)
        row = index.get(ref_or_asset_id)
        if row:
            ref_id = str(row.get("ref_id") or ref_or_asset_id)
    return ref_dna_mod.delete_reference_dna(ref_id, brand_id, root)


def dna_summary(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref_id": ref.get("ref_id"),
        "palette": ref.get("palette") or [],
        "mood": ref.get("mood") or [],
        "orientation": ref.get("orientation"),
        "luminance": ref.get("luminance"),
        "product_tags": ref.get("product_tags") or [],
        "platform": ref.get("platform"),
        "pillar": ref.get("pillar"),
        "source": ref.get("source"),
        "is_learnable": ref.get("is_learnable"),
        "label": ref.get("label"),
    }
