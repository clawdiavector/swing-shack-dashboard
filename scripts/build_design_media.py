#!/usr/bin/env python3
"""Build the picture layer for the Taxonomy of Design page.

Reads the phase 0 posts index (agent-control handoffs) and, for every post whose
image files exist on this machine, writes small WebP copies into
data/design/media/ plus data/design/taxonomy-media.json (what the page loads).

Nothing is invented: a post gets a style only when its index label names one of
the seeded styles (LABEL_TO_STYLES below), and a template only when the index
says so. Everything else stays "not recorded".

    python3 scripts/build_design_media.py \
        --index ~/finder-workspace/repos/work/agent-control/handoffs/taxonomy-of-design-20261109/posts-index.json \
        --root  ~/finder-workspace/repos/work/agent-control
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "data" / "design"
MEDIA_DIR = OUT_DIR / "media"

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXT = {".mp4", ".mov"}
THUMB_W, MID_W = 320, 640

# Index label -> seeded style ids. The phase 0 index guessed these labels from
# file names, so only labels that name exactly one look (or the two a combined
# label names) are mapped. "Poster collage (Snap/Night family)" is left out: it
# also caught Stick polo shots and people photos.
LABEL_TO_STYLES: dict[str, list[str]] = {
    "Lights-out (campaign default)": ["lights-out"],
    "Night / Lights-out": ["night", "lights-out"],
    "Snap": ["snap"],
    "Bold objects": ["bold-objects"],
    "Jordan spotlight": ["jordan-spotlight"],
    "Stick neon / sim-screen": ["neon-icon", "sim-screen"],
    "Ideogram": ["ideogram-balloons"],
    "Maker stack": ["maker-stack"],
}


def _is_reference(paths: list[str]) -> bool:
    """A raw photo or Krea source that goes INTO a post, not a finished post."""
    for p in paths:
        low = p.lower()
        name = low.rsplit("/", 1)[-1]
        if "/ref/" in low or "/people/" in low or "source" in name or name.startswith("ref_") or "reference" in name:
            return True
    return False


def _role(path: str, declared: str | None) -> str:
    name = path.lower().rsplit("/", 1)[-1]
    if "story" in name:
        return "story"
    if "gbp" in name:
        return "gbp"
    if "feed" in name:
        return "feed"
    return declared or "image"


_ROLE_RANK = {"feed": 0, "image": 1, "calendar": 1, "asset": 1, "shelf": 1, "golden": 1, "gbp": 2, "story": 3}


def _save(im: Image.Image, dest: Path, width: int, quality: int) -> None:
    if dest.exists():
        return
    copy = im.copy()
    copy.thumbnail((width, width * 2))
    copy.save(dest, "WEBP", quality=quality, method=4)


def _make_from_image(src: Path, want_mid: bool) -> tuple[str, str | None] | None:
    try:
        raw = src.read_bytes()
    except OSError:
        return None
    key = hashlib.sha1(raw).hexdigest()[:12]
    thumb, mid = MEDIA_DIR / f"{key}-t.webp", MEDIA_DIR / f"{key}-m.webp"
    if not thumb.exists() or (want_mid and not mid.exists()):
        try:
            im = Image.open(src)
            im = im.convert("RGB")
        except Exception:
            return None
        _save(im, thumb, THUMB_W, 62)
        if want_mid:
            _save(im, mid, MID_W, 68)
    return thumb.name, (mid.name if want_mid else None)


def _make_from_video(src: Path) -> tuple[str, str | None] | None:
    try:
        key = hashlib.sha1(f"{src}:{src.stat().st_size}".encode()).hexdigest()[:12]
    except OSError:
        return None
    thumb, mid = MEDIA_DIR / f"{key}-t.webp", MEDIA_DIR / f"{key}-m.webp"
    if thumb.exists() and mid.exists():
        return thumb.name, mid.name
    with tempfile.TemporaryDirectory() as tmp:
        frame = Path(tmp) / "f.png"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.6", "-i", str(src), "-frames:v", "1", str(frame)],
            capture_output=True,
        )
        if proc.returncode != 0 or not frame.is_file():
            return None
        try:
            im = Image.open(frame).convert("RGB")
        except Exception:
            return None
        _save(im, thumb, THUMB_W, 62)
        _save(im, mid, MID_W, 68)
    return thumb.name, mid.name


def build(index_path: Path, root: Path) -> dict:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    posts_in = json.loads(index_path.read_text(encoding="utf-8"))["posts"]
    posts_out: list[dict] = []
    stats = {"posts": 0, "with_picture": 0, "video_only": 0, "template_renders_skipped": 0, "files_unreadable": 0}

    for p in posts_in:
        kinds = {loc.get("kind") for loc in p.get("locations", [])}
        if kinds == {"product_repo"}:
            stats["template_renders_skipped"] += 1  # golden renders belong to Templates, not Posts
            continue
        stats["posts"] += 1
        pics: list[dict] = []
        seen: set[str] = set()
        for f in p.get("files", []):
            raw = str(f.get("path") or "")
            if raw.startswith("origin/"):
                continue
            src = Path(raw)
            if not src.is_absolute():
                src = root / raw
            ext = src.suffix.lower()
            if not src.is_file():
                continue
            role = _role(raw, f.get("role"))
            if ext in IMAGE_EXT:
                made = _make_from_image(src, want_mid=True)
                video = False
            elif ext in VIDEO_EXT:
                made = _make_from_video(src)
                video = True
            else:
                continue
            if not made:
                stats["files_unreadable"] += 1
                continue
            if made[0] in seen:
                continue
            seen.add(made[0])
            try:
                where = str(src.relative_to(root))
            except ValueError:
                where = raw
            pics.append({"role": "reel" if video else role, "thumb": made[0], "mid": made[1], "video": video, "where": where})
        pics.sort(key=lambda x: (x["video"], _ROLE_RANK.get(x["role"], 1)))
        label = (p.get("style") or "").strip()
        if "snapback" in (p.get("title") or "").lower():
            label = ""  # "snap" matched the product name, not the style
        row = {
            "id": p["id"],
            "brand": p.get("brand", ""),
            "campaign": p.get("campaign", ""),
            "date": p.get("date", ""),
            "title": p.get("title", ""),
            "status": p.get("status", ""),
            "style": label or "no style",
            "style_ids": LABEL_TO_STYLES.get(label, []),
            "template_id": None,
            "reference_photo": bool(pics) and _is_reference([x["where"] for x in pics]),
            "caption": (p.get("caption") or "")[:280],
            "sources": sorted({loc.get("kind", "") for loc in p.get("locations", [])} - {""}),
            "pictures": pics,
        }
        if pics:
            stats["with_picture"] += 1
            if all(x["video"] for x in pics):
                stats["video_only"] += 1
        posts_out.append(row)

    # Examples the seed names by file (e.g. img/ss-17-membership-snap__feed.jpg).
    # A post in the index is a slot that can hold several looks, so the pin keeps
    # the exact picture. Bare post ids are skipped: the index and the seed
    # disagree about which look post-00010 is (Night vs Snap), so it is not pinned.
    seed = json.loads((OUT_DIR / "taxonomy-seed.json").read_text(encoding="utf-8"))
    pins: dict[str, list[dict]] = {}
    for st in seed.get("styles", []):
        for ex in st.get("examples", []):
            if "/" not in ex:
                continue
            name = ex.split("/")[-1]
            for row in posts_out:
                for pic in row["pictures"]:
                    if pic["where"].endswith("/" + name):
                        pins.setdefault(st["id"], []).append({"post": row["id"], "thumb": pic["thumb"], "mid": pic["mid"]})
                        if st["id"] not in row["style_ids"]:
                            row["style_ids"].append(st["id"])

    return {
        "schema_version": "taxonomy-media-v1",
        "style_pins": pins,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "generated_from": str(index_path),
        "label_to_styles": LABEL_TO_STYLES,
        "stats": stats,
        "posts": posts_out,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True, type=Path)
    ap.add_argument("--root", required=True, type=Path, help="agent-control repo root (index paths are relative to it)")
    args = ap.parse_args()
    doc = build(args.index.expanduser(), args.root.expanduser())
    (OUT_DIR / "taxonomy-media.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in MEDIA_DIR.glob("*.webp"))
    print(json.dumps(doc["stats"]), f"media={len(list(MEDIA_DIR.glob('*.webp')))} files, {size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
