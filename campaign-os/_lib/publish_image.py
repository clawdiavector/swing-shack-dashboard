"""Publish-ready image paths — composed assets, social JPEG export."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any, Optional

from PIL import Image


def publish_jpeg_suffix() -> str:
    return "-publish.jpg"


def publish_jpeg_name_for_png(png_name: str) -> str:
    base = str(png_name or "").strip()
    if base.lower().endswith(".png"):
        return base[:-4] + publish_jpeg_suffix()
    return base + publish_jpeg_suffix()


def write_publish_jpeg_from_png_bytes(png_bytes: bytes, dest: Path) -> Path:
    """Write a high-quality JPEG tuned for IG/FB (4:4:4, minimal chroma blur on type)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    im.save(
        dest,
        format="JPEG",
        quality=int(os.environ.get("CAMPAIGN_OS_PUBLISH_JPEG_QUALITY", "95")),
        subsampling=0,
        optimize=True,
    )
    return dest


def write_publish_jpeg_from_png_path(png_path: Path) -> Path:
    dest = png_path.with_name(publish_jpeg_name_for_png(png_path.name))
    data = png_path.read_bytes()
    return write_publish_jpeg_from_png_bytes(data, dest)


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR") or "/data")


def _bundled_data_dir() -> Path:
    return Path(os.environ.get("BUNDLED_DATA_DIR") or "data")


def _brand_image_bases(brand_id: str) -> list[Path]:
    bases: list[Path] = []
    runtime = _data_dir() / "brand-directory" / brand_id / "images"
    bundled = _bundled_data_dir() / "brand-directory" / brand_id / "images"
    if runtime.exists():
        bases.append(runtime.resolve())
    if bundled.exists():
        bases.append(bundled.resolve())
    draft_images = _data_dir() / "draft-assets" / "images" / brand_id / "images"
    draft_brand = _data_dir() / "draft-assets" / "images" / brand_id
    if draft_images.exists():
        bases.append(draft_images.resolve())
    if draft_brand.exists():
        bases.append(draft_brand.resolve())
    return bases


def resolve_brand_image_file(brand_id: str, filename: str) -> Optional[Path]:
    """Resolve /brand-images/<brand>/<file> to a local path (mirrors app.py serve order)."""
    name = str(filename or "").strip().lstrip("/")
    if not name or ".." in name.split("/"):
        return None
    for base in _brand_image_bases(brand_id):
        target = (base / name).resolve()
        try:
            target.relative_to(base)
        except ValueError:
            continue
        if target.is_file():
            return target
    return None


def _path_from_brand_image_url(image_url: str) -> Optional[Path]:
    raw = str(image_url or "").strip()
    if not raw.startswith("/brand-images/"):
        return None
    parts = raw.strip("/").split("/")
    if len(parts) < 3:
        return None
    brand_id = parts[1]
    filename = "/".join(parts[2:])
    return resolve_brand_image_file(brand_id, filename)


def _looks_like_krea_raw(path: str) -> bool:
    low = path.lower().replace("\\", "/")
    return "/images/krea-" in low or "/krea-" in low.split("/")[-1]


def resolve_queue_upload_path(row: dict[str, Any]) -> Optional[Path]:
    """Best local file for Postiz upload: composed publish JPEG > composed PNG > raw path.

    Never prefer Krea raws when a composed /brand-images URL is present.
    """
    image_url = str(row.get("image_url") or "").strip()
    image_path = str(row.get("image_path") or "").strip()

    composed_fs = _path_from_brand_image_url(image_url) if image_url else None
    if composed_fs is not None:
        publish = composed_fs.with_name(publish_jpeg_name_for_png(composed_fs.name))
        if publish.is_file():
            return publish
        if composed_fs.is_file():
            return write_publish_jpeg_from_png_path(composed_fs)
        return None

    if image_path and not _looks_like_krea_raw(image_path):
        p = Path(image_path)
        if p.is_file():
            if p.suffix.lower() == ".png":
                pub = p.with_name(publish_jpeg_name_for_png(p.name))
                if pub.is_file():
                    return pub
                return write_publish_jpeg_from_png_path(p)
            return p

    if image_path and _looks_like_krea_raw(image_path):
        return None

    if image_path:
        p = Path(image_path)
        if p.is_file():
            return p
    return None
