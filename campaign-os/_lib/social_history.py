"""
social_history.py — Published social posts as a creative reference source.

This module treats published social posts as a CREATIVE INTELLIGENCE asset,
not just an analytics data source. It pairs each post with:

  - brand
  - platform (instagram | facebook | tiktok | x | ...)
  - post ID + permalink + URL
  - publish date + media type
  - thumbnail (downloaded from full_picture or media_url)
  - caption_full + caption_preview + hashtags + linked_url
  - performance metrics (reach, engagement, impressions, clicks)
  - classification (curated / published / strong / old_system /
                    high_performing / low_performing / rejected)
  - aspect ratio / orientation
  - campaign / product / service / property tags (set by user)

Storage layout:
  data/brand-directory/<brand>/social/<platform>/posts.json
  data/brand-directory/<brand>/social/<platform>/media/<post_id>.<ext>
  data/brand-directory/<brand>/social/asset-classifications.json
  data/brand-directory/<brand>/social/derived/visual-patterns.json

The system supports:
  - ingest_social_history(brand, platform) — pull new posts, persist
  - search_creative(brand, query, sources=[curated|published|generated])
  - classify_asset(brand, source, asset_id, classification)
  - extract_visual_patterns(brand) — surface recurring colour / composition / copy

Built 2026-08-31 to satisfy user directive 'IMPORTANT ADDITION —
SOCIAL HISTORY MUST FEED CREATIVE INTELLIGENCE'.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_LOG = logging.getLogger("campaign_os.social_history")


# ── Path resolution ─────────────────────────────────────────────────────
def _data_root(brand_id: str) -> Path:
    """Resolve the canonical social-history root for a brand.

    Priority:
      1. BUNDLED_DATA_DIR env var (set by app.py from REPO_ROOT/data) — bundled repo
      2. DATA_DIR env var (Railway volume) — runtime-persisted
      3. Hard-coded local dev path

    The function returns the FIRST existing path that has the brand directory.
    Falls back to writing to DATA_DIR so new files land on the persistent volume.
    """
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    runtime = os.environ.get("DATA_DIR") or "/data/campaign-os"
    candidates = []
    if bundled:
        candidates.append(Path(bundled))
    candidates.extend([
        Path("/data/campaign-os"),
        Path(runtime),
        Path(
            "/Users/fivefriday/.openclaw-instance2/workspace/"
            "swing-shack-dashboard/data"
        ),
    ])
    for c in candidates:
        brand_dir = c / "brand-directory" / brand_id
        if brand_dir.parent.exists():
            return brand_dir
    # Fallback — write to runtime DATA_DIR
    return Path(runtime) / "brand-directory" / brand_id


def _social_dir(brand_id: str) -> Path:
    """Return <data>/brand-directory/<brand>/social/. Auto-created."""
    d = _data_root(brand_id) / "social"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _platform_dir(brand_id: str, platform: str) -> Path:
    d = _social_dir(brand_id) / platform
    d.mkdir(parents=True, exist_ok=True)
    return d


def _media_dir(brand_id: str, platform: str) -> Path:
    d = _platform_dir(brand_id, platform) / "media"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Source post loaders (wrap existing fetcher outputs) ───────────────
def load_ig_history(brand_id: str = "swing-shack") -> list:
    """Load IG business analytics + return as social-history records."""
    candidates = [
        _data_root(brand_id) / "ig-business-analytics.json",
        _data_root(brand_id).parent / "ig-business-analytics.json",
        Path("/data/campaign-os/ig-business-analytics.json"),
        Path(
            "/Users/fivefriday/.openclaw-instance2/workspace/"
            "swing-shack-dashboard/data/ig-business-analytics.json"
        ),
    ]
    for c in candidates:
        if c.exists():
            try:
                d = json.loads(c.read_text())
                return _normalise_ig_posts(d.get("media") or [], brand_id)
            except Exception as e:
                _LOG.warning(f"failed to read {c}: {e}")
                continue
    return []


def load_fb_history(brand_id: str = "swing-shack") -> list:
    """Load FB page analytics + return as social-history records."""
    candidates = [
        _data_root(brand_id) / "fb-page-analytics.json",
        _data_root(brand_id).parent / "fb-page-analytics.json",
        Path("/data/campaign-os/fb-page-analytics.json"),
        Path(
            "/Users/fivefriday/.openclaw-instance2/workspace/"
            "swing-shack-dashboard/data/fb-page-analytics.json"
        ),
    ]
    for c in candidates:
        if c.exists():
            try:
                d = json.loads(c.read_text())
                return _normalise_fb_posts(d.get("media") or [], brand_id)
            except Exception as e:
                _LOG.warning(f"failed to read {c}: {e}")
                continue
    return []


def _normalise_ig_posts(posts: list, brand_id: str) -> list:
    """Project IG fetcher output to social-history schema."""
    out = []
    for p in posts:
        # Build aspect ratio + orientation hints from media_product_type
        media_type = p.get("media_type", "")
        product_type = p.get("media_product_type", "")
        orientation = "portrait" if media_type in ("VIDEO",) else "square"
        # Build the normalised record
        out.append({
            "source": "ig",
            "source_id": p.get("id"),
            "permalink": p.get("permalink"),
            "platform": "instagram",
            "brand_id": brand_id,
            "publish_date": p.get("timestamp"),
            "media_type": media_type,
            "media_product_type": product_type,
            "orientation": orientation,
            "media_url": p.get("media_url"),
            "thumbnail_url": p.get("thumbnail_url"),
            "caption_preview": p.get("caption_preview"),
            "caption_full": p.get("caption_full", p.get("caption_preview", "")),
            "hashtags": p.get("hashtags", []),
            "linked_url": p.get("linked_url"),
            "hook_id": p.get("hook_id"),
            "performance": p.get("metrics", {}),
            "engagement_rate_pct": p.get("engagement_rate_pct"),
            "insights_errors": p.get("insights_errors", []),
        })
    return out


def _normalise_fb_posts(posts: list, brand_id: str) -> list:
    """Project FB fetcher output to social-history schema."""
    out = []
    for p in posts:
        st = p.get("status_type", "")
        # Heuristic orientation from status_type
        orientation = (
            "vertical" if "reel" in st.lower() or "video" in st.lower()
            else "horizontal"
        )
        out.append({
            "source": "fb",
            "source_id": p.get("id"),
            "permalink": p.get("permalink"),
            "platform": "facebook",
            "brand_id": brand_id,
            "publish_date": p.get("timestamp"),
            "status_type": st,
            "orientation": orientation,
            "media_url": p.get("full_picture"),
            "thumbnail_url": p.get("full_picture"),
            "caption_preview": p.get("message_preview"),
            "caption_full": p.get("message_full", p.get("message_preview", "")),
            "hashtags": p.get("hashtags", []),
            "linked_url": p.get("linked_url"),
            "performance": {
                "reactions_total": p.get("reactions_total"),
                "clicks": p.get("clicks"),
                "shares": p.get("shares"),
                **{
                    k.replace("post_", ""): v
                    for k, v in (p.get("metrics") or {}).items()
                },
            },
        })
    return out


# ── Persistence ─────────────────────────────────────────────────────────
def persist_social_history(
    brand_id: str,
    posts: list,
    platform: str = "instagram",
) -> Path:
    """Write normalised posts to disk under the brand's social dir.

    Returns the path to the resulting posts.json file.
    """
    out_path = _platform_dir(brand_id, platform) / "posts.json"
    payload = {
        "brand_id": brand_id,
        "platform": platform,
        "count": len(posts),
        "ingested_at": datetime.utcnow().isoformat() + "Z",
        "posts": posts,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    return out_path


def load_social_history(brand_id: str, platform: Optional[str] = None) -> list:
    """Load persisted social-history records for a brand."""
    out: list = []
    platforms = [platform] if platform else ["instagram", "facebook", "tiktok", "x"]
    for plat in platforms:
        p = _platform_dir(brand_id, plat) / "posts.json"
        if p.exists():
            try:
                d = json.loads(p.read_text())
                out.extend(d.get("posts") or [])
            except Exception as e:
                _LOG.warning(f"failed to read {p}: {e}")
    return out


# ── Asset classification ───────────────────────────────────────────────
# Per user directive:
#   CURATED / PUBLISHED / STRONG / OLD_SYSTEM / CAMPAIGN_SPECIFIC /
#   HIGH_PERFORMING / LOW_PERFORMING / REJECTED

CLASSIFICATIONS = {
    "curated": "Manually uploaded / approved strong example",
    "published": "Real social content that went live",
    "strong": "Content we actively want future generation to learn from",
    "old_system": "Historically published but no longer representative",
    "campaign_specific": "Useful only when recreating that particular campaign/property",
    "high_performing": "Evidence suggests it performed strongly",
    "low_performing": "Published but performance was weak",
    "rejected": "Explicitly excluded from positive visual learning",
}


def classify_asset(
    brand_id: str,
    source: str,
    asset_id: str,
    classification: str,
    notes: str = "",
    platform: str = "instagram",
) -> dict:
    """Persist a classification for a social / curated / generated asset.

    `source` is one of: 'curated', 'ig', 'fb', 'generated', 'local'
    `asset_id` is the post id / image filename / krea job_id
    `classification` is one of CLASSIFICATIONS keys
    """
    if classification not in CLASSIFICATIONS:
        raise ValueError(
            f"unknown classification {classification!r}; "
            f"valid: {list(CLASSIFICATIONS.keys())}"
        )
    classifications_path = _social_dir(brand_id) / "asset-classifications.json"
    existing = {}
    if classifications_path.exists():
        try:
            existing = json.loads(classifications_path.read_text())
        except Exception:
            existing = {}
    key = f"{source}::{asset_id}"
    existing[key] = {
        "source": source,
        "asset_id": asset_id,
        "classification": classification,
        "platform": platform,
        "notes": notes,
        "classified_at": datetime.utcnow().isoformat() + "Z",
    }
    classifications_path.write_text(json.dumps(existing, indent=2, default=str))
    return existing[key]


def load_classifications(brand_id: str) -> dict:
    """Load all classifications for a brand. Returns dict keyed by source::asset_id."""
    classifications_path = _social_dir(brand_id) / "asset-classifications.json"
    if not classifications_path.exists():
        return {}
    try:
        return json.loads(classifications_path.read_text())
    except Exception:
        return {}


def is_learnable(brand_id: str, source: str, asset_id: str) -> bool:
    """True if the asset is allowed to feed creative_director.compose_prompt.

    A post is 'learnable' when:
      - It has NO classification entry, OR
      - Its classification is in: curated, strong, published, high_performing, campaign_specific
    It is NOT learnable when classified as: old_system, low_performing, rejected
    """
    classifications = load_classifications(brand_id)
    cls = classifications.get(f"{source}::{asset_id}")
    if not cls:
        return True  # No classification = default to learnable
    return cls.get("classification") not in (
        "old_system", "low_performing", "rejected"
    )


# ── Thumbnail download ──────────────────────────────────────────────────
def download_thumbnail(
    brand_id: str,
    platform: str,
    asset_id: str,
    url: str,
    ext: str = "jpg",
    timeout_s: int = 30,
) -> Optional[Path]:
    """Download a thumbnail for a post. Skips silently on error."""
    if not url:
        return None
    media_dir = _media_dir(brand_id, platform)
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(asset_id))
    out_path = media_dir / f"{safe_id}.{ext}"
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CampaignOS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read()
        out_path.write_bytes(data)
        return out_path
    except (urllib.error.URLError, TimeoutError) as e:
        _LOG.warning(f"thumbnail download failed for {asset_id}: {e}")
        return None


def download_thumbnails_parallel(brand_id: str, posts: list) -> dict:
    """Download all post thumbnails in parallel.

    Returns: {asset_id: relative_path or None}
    """
    downloads = []
    for p in posts:
        plat = p.get("platform", "instagram")
        asset_id = p.get("source_id", p.get("permalink"))
        url = p.get("thumbnail_url") or p.get("media_url")
        if not url:
            continue
        ext = "jpg"
        if url.lower().endswith(".png"):
            ext = "png"
        downloads.append((brand_id, plat, asset_id, url, ext))
    results = {}
    if downloads:
        with ThreadPoolExecutor(max_workers=4) as ex:
            future_to_id = {
                ex.submit(download_thumbnail, b, pl, aid, u, e): aid
                for b, pl, aid, u, e in downloads
            }
            for fut in as_completed(future_to_id):
                aid = future_to_id[fut]
                try:
                    path = fut.result()
                    if path:
                        results[aid] = str(path.relative_to(_data_root(brand_id).parent))
                except Exception as e:
                    _LOG.warning(f"download task failed for {aid}: {e}")
                    results[aid] = None
    return results


# ── Creative search (curated + published + generated) ─────────────────
def search_creative(
    brand_id: str,
    query: str,
    *,
    sources: Optional[list] = None,
    classifications: Optional[list] = None,
    platform: Optional[str] = None,
    product: Optional[str] = None,
    limit: int = 25,
) -> dict:
    """Search across curated + published + generated creative assets.

    Args:
      brand_id: which brand to search
      query: free-text query (matches filename, caption, hashtag, etc.)
      sources: list of ['curated', 'published', 'generated'] — default all
      classifications: filter by classification (e.g. ['strong', 'high_performing'])
      platform: filter published posts by platform
      product: filter by product/hashtag hint
      limit: max results to surface

    Returns:
      {
        "query": "...",
        "total": int,
        "results": [
          {rank, source, asset_id, score, classification, match_reason, ...}
        ]
      }

    Weighting order (per user directive #7):
      1. Explicitly selected reference (source=curated, classification=strong)
      2. Manually approved/curated reference
      3. Current strategic brand system
      4. Recent published content consistent with current strategy
      5. Historically high-performing relevant work
      6. General historical social archive
    """
    sources = sources or ["curated", "published", "generated"]
    out = []
    q_low = (query or "").lower().strip()
    _sample_fnames = []  # DEBUG

    # 1) CURATED — search brand-directory/<brand>/images/
    # Fall back to scanning *.visual-dna.json sidecars when no source images
    # are on disk (live-verified 2026-08-31: bundle ships sidecars only).
    if "curated" in sources:
        curated_root = _data_root(brand_id) / "images"
        if curated_root.exists():
            classifications_db = load_classifications(brand_id)
            seen_filenames = set()
            # First pass: real image files (when present)
            for img in sorted(curated_root.iterdir()):
                if not img.is_file():
                    continue
                if img.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
                    continue
                if img.name.endswith(".visual-dna.json"):
                    continue
                seen_filenames.add(img.name)
                fname = img.name
                if q_low and q_low not in fname.lower():
                    continue
                cls_entry = classifications_db.get(f"curated::{fname}")
                cls = cls_entry.get("classification") if cls_entry else "curated"
                if classifications and cls not in classifications:
                    continue
                score = _score_curated(q_low, fname, cls)
                out.append({
                    "source": "curated",
                    "asset_id": fname,
                    "score": score,
                    "classification": cls,
                    "match_reason": "curated upload" if not q_low else f"filename contains {q_low!r}",
                    "thumbnail_path": f"brand-directory/{brand_id}/images/{fname}",
                    "media_type": "image",
                })
            # Second pass: visual-dna.json sidecars (when real images absent).
            # Each sidecar's filename hint (e.g. JORDAN_BAG) feeds the query.
            _sidecar_count = 0
            _sidecar_matched = 0
            _sidecar_seen_filter = 0
            _sidecar_q_filter = 0
            for dna_path in sorted(curated_root.glob("*.visual-dna.json")):
                _sidecar_count += 1
                if _sidecar_count <= 5:
                    _sample_fnames.append(dna_path.name)
                # The sidecar filename is "<image>.<ext>.visual-dna.json"
                # Strip ".visual-dna.json" (18 chars) then split on the
                # last remaining dot to recover base + ext.
                stripped = dna_path.name
                if not stripped.endswith(".visual-dna.json"):
                    continue
                stripped = stripped[: -len(".visual-dna.json")]  # remove '.visual-dna.json'
                # Find the LAST remaining dot — that's the boundary between
                # base filename and original extension (e.g. ".jpg").
                last_dot = stripped.rfind(".")
                if last_dot == -1:
                    _sidecar_q_filter += 1
                    continue
                orig_name = stripped
                if orig_name in seen_filenames:
                    _sidecar_seen_filter += 1
                    continue  # already added in first pass
                fname = orig_name
                if q_low and q_low not in fname.lower():
                    _sidecar_q_filter += 1
                    continue
                # Read the sidecar for palette / orientation / hints
                try:
                    dna = json.loads(dna_path.read_text())
                except Exception:
                    dna = {}
                palette = dna.get("layer9_palette", {}).get("dominant_colors", [])
                dominant_hex = palette[0].get("hex", "") if palette else ""
                orientation = dna.get("layer1_metadata", {}).get("orientation")
                cls_entry = classifications_db.get(f"curated::{orig_name}")
                cls = cls_entry.get("classification") if cls_entry else "curated"
                if classifications and cls not in classifications:
                    continue
                score = _score_curated(q_low, orig_name, cls) - 0.05  # tiny penalty for sidecar-only
                _sidecar_matched += 1
                out.append({
                    "source": "curated",
                    "asset_id": orig_name,
                    "score": score,
                    "classification": cls,
                    "match_reason": "sidecar-only (image not on disk); palette + composition from .visual-dna.json" if not q_low else f"sidecar filename contains {q_low!r}",
                    "thumbnail_path": f"brand-directory/{brand_id}/images/{orig_name}",
                    "media_type": "image",
                    "dominant_hex": dominant_hex,
                    "orientation": orientation,
                    "sidecar_path": str(dna_path.relative_to(_data_root(brand_id).parent)),
                })

    # 2) PUBLISHED — search persisted social-history records
    if "published" in sources:
        posts = load_social_history(brand_id, platform=platform)
        classifications_db = load_classifications(brand_id)
        for p in posts:
            source_id = p.get("source_id", "")
            # Source-specific classification key
            cls_key = f"{p.get('source', 'ig')}::{source_id}"
            cls_entry = classifications_db.get(cls_key)
            cls = cls_entry.get("classification") if cls_entry else "published"
            if classifications and cls not in classifications:
                continue
            score, reason = _score_published(q_low, p, cls, product)
            if score <= 0 and q_low:
                continue
            out.append({
                "source": "published",
                "asset_id": source_id,
                "score": score,
                "classification": cls,
                "platform": p.get("platform"),
                "permalink": p.get("permalink"),
                "publish_date": p.get("publish_date"),
                "media_type": p.get("media_type") or p.get("status_type") or "image",
                "caption_preview": p.get("caption_preview"),
                "performance": p.get("performance"),
                "hashtags": p.get("hashtags"),
                "match_reason": reason,
                "thumbnail_path": (
                    f"brand-directory/{brand_id}/social/{p.get('platform')}/media/{source_id}.jpg"
                ),
            })

    # 3) GENERATED — search krea + overlay sidecars
    if "generated" in sources:
        generated_root = _data_root(brand_id) / "images" / "krea"
        if generated_root.exists():
            for jp in sorted(generated_root.glob("*.json")):
                try:
                    meta = json.loads(jp.read_text())
                except Exception:
                    continue
                fname = jp.stem
                if q_low and q_low not in fname.lower() and q_low not in json.dumps(meta).lower()[:500]:
                    continue
                out.append({
                    "source": "generated",
                    "asset_id": fname,
                    "score": 0.5,
                    "classification": "generated",
                    "match_reason": "krea job record",
                    "thumbnail_path": str(jp.with_suffix(".png").relative_to(_data_root(brand_id).parent)),
                    "url": meta.get("url"),
                    "saved_at": meta.get("saved_at"),
                })

    # Sort by score desc
    out.sort(key=lambda x: -x.get("score", 0))
    out = out[:limit]

    # Build debug stats
    debug_info = {
        "data_root_resolved": str(_data_root(brand_id)),
        "data_root_exists": _data_root(brand_id).exists(),
        "_sample_fnames": _sample_fnames,
        "curated_root": str(_data_root(brand_id) / "images"),
        "curated_root_exists": (_data_root(brand_id) / "images").exists(),
        "curated_total_files": (
            len([f for f in (_data_root(brand_id) / "images").iterdir()
                 if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".heic")])
            if (_data_root(brand_id) / "images").exists() else 0
        ),
        "curated_total_sidecars": (
            len(list((_data_root(brand_id) / "images").glob("*.visual-dna.json")))
            if (_data_root(brand_id) / "images").exists() else 0
        ),
        "_sidecar_count": _sidecar_count,
        "_sidecar_matched": _sidecar_matched,
        "_sidecar_seen_filter": _sidecar_seen_filter,
        "_sidecar_q_filter": _sidecar_q_filter,
        "published_count": len(load_social_history(brand_id)),
        "generated_count": (
            len(list((_data_root(brand_id) / "images" / "krea").glob("*.json")))
            if (_data_root(brand_id) / "images" / "krea").exists() else 0
        ),
    }
    return {
        "query": query,
        "brand_id": brand_id,
        "sources_searched": sources,
        "total": len(out),
        "results": out,
        "debug": debug_info,
    }


def _score_curated(query: str, filename: str, classification: str) -> float:
    """Score a curated image based on query match + classification weight."""
    score = 0.0
    if not query:
        score = 0.5
    elif query in filename.lower():
        score = 0.8
    # Classification weight (per user directive #7)
    if classification == "strong":
        score += 0.5
    elif classification == "curated":
        score += 0.3
    elif classification == "high_performing":
        score += 0.2
    elif classification == "old_system":
        score -= 0.4
    elif classification == "rejected":
        score = 0  # Never recommend rejected
    elif classification == "campaign_specific":
        score += 0.1
    return score


def _score_published(query: str, post: dict, classification: str, product_hint: Optional[str]) -> tuple:
    """Score a published post based on query match + classification + performance."""
    score = 0.0
    reason_parts = []
    if not query:
        score = 0.4
    else:
        # caption / hashtag / product match
        caption = (post.get("caption_full") or post.get("caption_preview") or "").lower()
        hashtags = [h.lower() for h in (post.get("hashtags") or [])]
        if query in caption:
            score += 0.5
            reason_parts.append(f"caption contains {query!r}")
        if any(query in h for h in hashtags):
            score += 0.3
            reason_parts.append(f"hashtag matches {query!r}")
        if product_hint and product_hint in caption:
            score += 0.3
            reason_parts.append(f"product {product_hint!r} in caption")
    # Recency weight — newer posts score higher
    pd = post.get("publish_date", "")
    if pd:
        try:
            post_date = datetime.fromisoformat(pd.replace("Z", "+00:00")[:19])
            days_ago = (datetime.utcnow() - post_date.replace(tzinfo=None)).days
            if days_ago < 30:
                score += 0.2
                reason_parts.append("recent (< 30 days)")
            elif days_ago < 90:
                score += 0.1
                reason_parts.append("recent (< 90 days)")
        except Exception:
            pass
    # Performance weight — engagement above brand baseline boosts score
    perf = post.get("performance") or {}
    eng_rate = post.get("engagement_rate_pct") or 0
    if eng_rate and eng_rate > 2.0:
        score += 0.2
        reason_parts.append(f"high engagement rate {eng_rate:.1f}%")
    # Classification weight
    if classification == "strong":
        score += 0.5
    elif classification == "high_performing":
        score += 0.3
    elif classification == "campaign_specific":
        score += 0.2
    elif classification == "old_system":
        score -= 0.4
    elif classification == "low_performing":
        score -= 0.3
    elif classification == "rejected":
        return 0, "rejected"
    return score, "; ".join(reason_parts) or "no match"


# ── Visual pattern extraction (per user directive #5) ─────────────────
def extract_visual_patterns(brand_id: str) -> dict:
    """Aggregate the published + curated corpus to surface recurring patterns.

    Returns:
      {
        brand_id, sample_size, dominant_colours, recurring_hashtags,
        recurring_caption_patterns, performance_baseline,
        common_orientation, common_media_type
      }
    """
    curated_root = _data_root(brand_id) / "images"
    palette: list = []
    recurring_hashtags: dict = {}
    caption_first_lines: list = []
    performances: list = []
    orientations: dict = {}
    media_types: dict = {}

    # Curated — extract dominant colours from sidecar DNA
    if curated_root.exists():
        for dna_path in curated_root.glob("*.visual-dna.json"):
            try:
                dna = json.loads(dna_path.read_text())
                for c in (dna.get("layer9_palette", {}).get("dominant_colors") or []):
                    if "hex" in c:
                        palette.append(c["hex"])
                orientation = dna.get("layer1_metadata", {}).get("orientation")
                if orientation:
                    orientations[orientation] = orientations.get(orientation, 0) + 1
            except Exception:
                continue

    # Published — collect hashtags + captions + performance
    for post in load_social_history(brand_id):
        for h in (post.get("hashtags") or []):
            recurring_hashtags[h] = recurring_hashtags.get(h, 0) + 1
        caption = post.get("caption_full") or post.get("caption_preview") or ""
        first_line = caption.split("\n", 1)[0].strip()
        if first_line:
            caption_first_lines.append(first_line)
        eng_rate = post.get("engagement_rate_pct")
        if eng_rate:
            performances.append(eng_rate)
        ori = post.get("orientation")
        if ori:
            orientations[ori] = orientations.get(ori, 0) + 1
        mt = post.get("media_type") or post.get("status_type")
        if mt:
            media_types[mt] = media_types.get(mt, 0) + 1

    # Top hashtags
    top_hashtags = sorted(recurring_hashtags.items(), key=lambda x: -x[1])[:15]

    # Top recurring first-line patterns (very lightweight — first 5 words)
    from collections import Counter
    patterns = Counter()
    for line in caption_first_lines:
        words = line.split()[:5]
        if words:
            pattern = " ".join(words)
            patterns[pattern] += 1
    top_patterns = patterns.most_common(10)

    # Engagement baseline
    if performances:
        eng_baseline = {
            "median": sorted(performances)[len(performances) // 2],
            "mean": round(sum(performances) / len(performances), 2),
            "max": max(performances),
            "min": min(performances),
            "n": len(performances),
        }
    else:
        eng_baseline = None

    return {
        "brand_id": brand_id,
        "sample_size": len(caption_first_lines) + (1 if curated_root.exists() else 0),
        "top_dominant_colours": palette[:20],
        "top_hashtags": [{"tag": h, "count": c} for h, c in top_hashtags],
        "top_caption_openers": [
            {"pattern": p, "count": c} for p, c in top_patterns
        ],
        "engagement_baseline": eng_baseline,
        "common_orientations": sorted(
            orientations.items(), key=lambda x: -x[1]
        ),
        "common_media_types": sorted(
            media_types.items(), key=lambda x: -x[1]
        ),
        "extracted_at": datetime.utcnow().isoformat() + "Z",
    }