"""
P1.2 Slice D — Adaptive VIDEO observation.

Same Pass A integrity as Slice B/C:
- visual observation only
- no caption / hashtags / filename / campaign / topic / product /
  performance / historical labels reach the vision model
- unknown stays unknown (three-state discipline)

Adaptive flow:
1. Fetch IG media_url (VIDEO) + duration via Meta Graph API
2. Download video bytes to disk
3. Probe with ffprobe for duration (fallback to Meta length)
4. Compute a deterministic initial sample of timestamps
5. Extract candidate frames at those timestamps via ffmpeg
6. Compute cheap deterministic similarity (mean pixel diff) between
   consecutive candidate frames → group near-identical frames
7. Send only UNIQUE visual frames to the vision model
8. Adaptive expansion: if major visual change detected and we are
   under cap, insert midpoints between divergent consecutive frames
9. Each unique frame uses the locked Slice B observer (gpt-4o-mini,
   1024px JPEG q80, detail=low) with independent cache key
10. Derive video-level features from frame observations
    (three-state, evidence_frames preserved, opening separate)
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _lib.p12_creative_genome import (
    P12A_ANALYSIS_VERSION,
    P12A_VISION_MODEL,
    _validate_observation,
    _call_vision,
    _bytes_to_data_url,
    _make_analysis_derivative,
    _save_frame,
    _cache_lookup,
    _cache_write,
    _append_observation,
    _load_observation_by_id,
    _download_image_raw,
    P12A_OBSERVATIONS,
    P12A_FRAMES_DIR,
)

_LOG = logging.getLogger(__name__)

# ─── Adaptive sampling config ────────────────────────────────────────────────
VIDEO_FRAME_CAP = 6                  # hard cap on unique frames per video
VIDEO_NEAR_IDENTICAL_THRESHOLD = 0.04  # mean pixel diff below this = near-identical
VIDEO_MIN_GAP_SECONDS = 0.5          # adaptive extras must be at least this far apart


def _ffprobe_duration(video_path: Path) -> Optional[float]:
    """Return video duration in seconds, or None if probe fails."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode != 0:
            return None
        return float(out.stdout.strip())
    except Exception as e:
        _LOG.warning("ffprobe failed for %s: %s", video_path, e)
        return None


def _extract_frame(video_path: Path, timestamp_sec: float, out_path: Path,
                    width: int = 1024) -> Optional[bytes]:
    """Extract one frame at a timestamp via ffmpeg. Returns image bytes or None."""
    try:
        cmd = [
            "ffmpeg", "-y", "-ss", f"{timestamp_sec:.3f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-vf", f"scale='min({width},iw)':-1",
            "-q:v", "3",
            str(out_path),
        ]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if out.returncode != 0 or not out_path.exists():
            return None
        return out_path.read_bytes()
    except Exception as e:
        _LOG.warning("frame extract failed for %s @ %.2fs: %s", video_path, timestamp_sec, e)
        return None


def _bytes_to_pil(bytes_: bytes):
    """Decode bytes → PIL.Image. Returns None on failure."""
    try:
        from PIL import Image
        return Image.open(io.BytesIO(bytes_)).convert("RGB")
    except Exception:
        return None


def _image_mean_pixel_diff(a, b) -> float:
    """Mean absolute pixel difference between two PIL images, normalised to
    [0, 1]. Downsamples to 64x64 for speed. Returns 1.0 on failure."""
    try:
        if a is None or b is None:
            return 1.0
        if a.size != b.size:
            b = b.resize(a.size)
        a_s = a.resize((64, 64))
        b_s = b.resize((64, 64))
        a_pixels = list(a_s.getdata())
        b_pixels = list(b_s.getdata())
        n = len(a_pixels)
        if n == 0:
            return 1.0
        total = 0
        for ap, bp in zip(a_pixels, b_pixels):
            # ap, bp are (r,g,b) tuples
            total += abs(ap[0] - bp[0]) + abs(ap[1] - bp[1]) + abs(ap[2] - bp[2])
        return (total / (n * 3 * 255.0))
    except Exception:
        return 1.0


def _adaptive_initial_timestamps(duration: Optional[float]) -> List[float]:
    """Return the initial sample timestamps for a video of the given duration.
    Adaptive to duration so very short videos don't waste time on distant samples."""
    if duration is None or duration <= 0:
        return [0.0]
    if duration <= 1.0:
        return [0.0]
    if duration <= 2.0:
        return [0.0, max(0.0, duration - 0.2)]
    if duration <= 4.0:
        return [0.0, duration * 0.5, max(0.0, duration - 0.2)]
    return [
        0.0,
        min(1.0, duration * 0.25),
        duration * 0.5,
        max(0.5, duration - 0.5),
    ]


def _dedupe_consecutive_frames(pil_frames: List[Any],
                                 timestamps: List[float],
                                 threshold: float = VIDEO_NEAR_IDENTICAL_THRESHOLD
                                 ) -> Tuple[List[int], List[List[int]]]:
    """Group consecutive near-identical frames. Returns:
      unique_indices: indices of the first frame of each unique group
      groups: list of index-lists (each represents one unique visual state)
    A new group starts when mean_pixel_diff vs the previous retained frame
    exceeds `threshold`.
    """
    if not pil_frames:
        return [], []
    unique_indices = [0]
    groups = [[0]]
    for i in range(1, len(pil_frames)):
        prev = pil_frames[unique_indices[-1]]
        diff = _image_mean_pixel_diff(prev, pil_frames[i])
        if diff > threshold:
            unique_indices.append(i)
            groups.append([i])
        else:
            groups[-1].append(i)
    return unique_indices, groups


def _resolve_video_metadata(asset: Dict[str, Any]) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Fetch VIDEO metadata via Meta Graph API. Returns (media_url, duration, error)."""
    ig_media_id = asset.get("ig_media_id") or asset.get("source_media_id")
    if not ig_media_id and str(asset.get("asset_id", "")).startswith("ig-"):
        ig_media_id = str(asset.get("asset_id"))[3:]
    if not ig_media_id or not str(ig_media_id).isdigit():
        return None, None, "no ig_media_id"
    try:
        from _lib.meta_api import (
            _read_meta_access_token, _graph_get,
            MetaAuthError, MetaUpstreamError, MetaNetworkError,
        )
    except Exception as e:
        return None, None, f"meta_api import failed: {e}"
    token = _read_meta_access_token()
    if not token:
        return None, None, "no Meta access token"
    try:
        out = _graph_get(
            f"/{ig_media_id}",
            {"fields": "media_type,media_url,thumbnail_url,permalink,length"},
        )
    except (MetaAuthError, MetaUpstreamError, MetaNetworkError) as e:
        return None, None, f"meta error: {type(e).__name__}: {e}"
    media_url = out.get("media_url")
    if not media_url:
        return None, None, "meta returned no media_url"
    duration = out.get("length")
    if duration is not None:
        try:
            duration = float(duration)
        except Exception:
            duration = None
    return media_url, duration, None


def _video_content_hash(video_bytes: bytes) -> str:
    return hashlib.sha256(video_bytes).hexdigest()[:16]


def _analyse_one_frame(asset_id: str, brand_id: str,
                        timestamp_sec: float,
                        frame_bytes: bytes,
                        frame_cache_key: str,
                        max_dim: int = 1024, quality: int = 80,
                        model: Optional[str] = None) -> Dict[str, Any]:
    """Analyse one video frame via the locked Slice B observer.
    Independent cache key per (asset_id, timestamp_ms)."""
    _ensure_dirs()
    frame_content_hash = hashlib.sha256(frame_bytes).hexdigest()[:16]
    _save_frame(frame_cache_key, frame_content_hash, frame_bytes)
    derivative, deriv_stats = _make_analysis_derivative(
        frame_bytes, frame_cache_key, frame_content_hash,
        max_dim=max_dim, quality=quality,
    )
    cached = _cache_lookup(frame_cache_key, frame_content_hash, P12A_ANALYSIS_VERSION)
    if cached:
        obs_id = cached.get("observation_id")
        existing = _load_observation_by_id(obs_id) if obs_id else None
        return {
            "ok": True,
            "cached": True,
            "timestamp": round(timestamp_sec, 3),
            "content_hash": frame_content_hash,
            "analysis_version": P12A_ANALYSIS_VERSION,
            "observation_id": obs_id,
            "observations": (existing or {}).get("observations") or {},
            "normalisation_warnings": (existing or {}).get("normalisation_warnings") or [],
            "model_usage": None,
            "duration_ms": None,
            "derivative_stats": deriv_stats,
        }
    if derivative:
        send_bytes = derivative
        send_dimensions = deriv_stats.get("derivative_dimensions")
    else:
        send_bytes = frame_bytes
        send_dimensions = None
    data_url = _bytes_to_data_url(send_bytes, "image/jpeg")
    t0 = time.time()
    api_result = _call_vision(data_url, frame_cache_key, brand_id, model=model)
    if "error" in api_result:
        return {
            "ok": False,
            "timestamp": round(timestamp_sec, 3),
            "content_hash": frame_content_hash,
            "error": api_result["error"],
        }
    obs, nw = _validate_observation(api_result.get("observation") or {})
    duration_ms = int((time.time() - t0) * 1000)
    obs_id = f"video_frame_t{int(timestamp_sec*1000):06d}_{frame_cache_key}_{int(time.time()*1000)}"
    record = {
        "observation_id": obs_id,
        "asset_id": frame_cache_key,
        "brand_id": brand_id,
        "media_type": "VIDEO_FRAME",
        "analysis_version": P12A_ANALYSIS_VERSION,
        "vision_model": model or P12A_VISION_MODEL,
        "content_hash": frame_content_hash,
        "timestamp": round(timestamp_sec, 3),
        "image_sent_to_model": {
            "source": "derivative",
            "bytes": len(send_bytes),
            "dimensions": send_dimensions,
        },
        "analysis_kind": "visual_observation",
        "pass": "A",
        "slide_kind": "video_frame",
        "context_inputs_forbidden": [
            "caption", "hashtags", "filename", "campaign", "service",
            "topic", "product_name", "performance", "win_score",
            "historical_classification",
        ],
        "context_inputs_actually_sent": ["image_url (data URL) only"],
        "normalisation_warnings": nw,
        "observations": obs,
        "model_usage": api_result.get("usage") or {},
        "analysed_at": time.time(),
        "duration_ms": duration_ms,
    }
    _append_observation(record)
    _cache_write(frame_cache_key, frame_content_hash, P12A_ANALYSIS_VERSION, obs_id)
    return {
        "ok": True,
        "cached": False,
        "timestamp": round(timestamp_sec, 3),
        "content_hash": frame_content_hash,
        "analysis_version": P12A_ANALYSIS_VERSION,
        "observation_id": obs_id,
        "observations": obs,
        "normalisation_warnings": nw,
        "model_usage": api_result.get("usage") or {},
        "duration_ms": duration_ms,
        "derivative_stats": deriv_stats,
    }


def _derive_video_features(asset_id: str, brand_id: str,
                              frame_results: List[Dict[str, Any]],
                              frames_sampled: int,
                              duration: Optional[float],
                              duplicate_groups: List[List[int]],
                              coverage_notes: List[str]) -> Dict[str, Any]:
    """Derive video-level features from frame observations. Three-state discipline."""
    analysed = [f for f in frame_results if f.get("ok") and f.get("observations")]
    failed = [f for f in frame_results if not f.get("ok")]

    def _bool_at(frame, field):
        return frame.get("observations", {}).get(field, {}).get("value")

    def _cat_at(frame, field):
        return frame.get("observations", {}).get(field, {}).get("value")

    bool_fields = [
        "human_present", "face_visible", "golfer_present", "golf_club_present",
        "golf_ball_present", "screen_visible", "text_overlay", "logo_visible",
        "indoor", "outdoor", "product_closeup", "simulator_environment",
        "golfer_swinging", "golfer_putting", "golf_bag_present",
    ]
    by_field = {}
    for f in bool_fields:
        pos = [i for i, fr in enumerate(analysed) if _bool_at(fr, f) is True]
        neg = [i for i, fr in enumerate(analysed) if _bool_at(fr, f) is False]
        unk = [i for i, fr in enumerate(analysed) if _bool_at(fr, f) is None]
        if pos:
            derived = True
            evidence = pos
        elif neg:
            derived = False
            evidence = neg
        else:
            derived = None
            evidence = []
        by_field[f] = {
            "derived": derived,
            "evidence_frames": evidence,
            "positive_count": len(pos),
            "negative_count": len(neg),
            "unknown_count": len(unk),
            "observed_count": len(pos) + len(neg),
            "observed_ratio": round((len(pos) + len(neg)) / len(analysed), 3) if analysed else None,
            "positive_ratio": round(len(pos) / len(analysed), 3) if analysed else None,
        }

    opening = analysed[0] if analysed else None
    closing = analysed[-1] if analysed else None

    def _opening(field):
        if not opening: return None
        return _bool_at(opening, field) if field in by_field else _cat_at(opening, field)
    def _closing(field):
        if not closing: return None
        return _bool_at(closing, field) if field in by_field else _cat_at(closing, field)

    # Subject/shot progressions (in temporal order)
    dom_seq = [f.get("observations", {}).get("dominant_subject", {}).get("value")
               for f in analysed]
    shot_seq = [f.get("observations", {}).get("shot_type", {}).get("value")
                for f in analysed]
    text_seq = [_bool_at(f, "text_overlay") for f in analysed]

    # Transitions between adjacent frames
    transitions = []
    for i in range(1, len(analysed)):
        a_dom = dom_seq[i-1]
        b_dom = dom_seq[i]
        if a_dom is None or b_dom is None:
            continue
        if a_dom == "human" and b_dom == "product":
            transitions.append("human_to_product")
        elif a_dom == "product" and b_dom == "human":
            transitions.append("product_to_human")
        elif a_dom in ("text", "graphic") and b_dom not in ("text", "graphic"):
            transitions.append("graphic_to_footage")
        elif b_dom in ("text", "graphic") and a_dom not in ("text", "graphic"):
            transitions.append("footage_to_graphic")

    # Early-frame (≤3 seconds) subset
    early = [f for f in analysed if (f.get("timestamp") or 0) <= 3.0]
    early_pos_human = sum(1 for f in early if _bool_at(f, "human_present") is True)
    early_neg_human = sum(1 for f in early if _bool_at(f, "human_present") is False)
    early_pos_text = sum(1 for f in early if _bool_at(f, "text_overlay") is True)
    early_neg_text = sum(1 for f in early if _bool_at(f, "text_overlay") is False)
    early_human_present = (True if early_pos_human else
                           False if early_neg_human else None)
    early_text_present = (True if early_pos_text else
                          False if early_neg_text else None)
    early_doms = sorted({v for v, f in
                          zip(dom_seq, analysed)
                          if (f.get("timestamp") or 0) <= 3.0
                          and v is not None and v != "unknown"})
    early_subject_change = len(early_doms) > 1

    # Sampled visual-change measure (deterministic from content_hash transitions)
    visual_change_count = 0
    prev_hash = None
    for f in analysed:
        h = f.get("content_hash")
        if h and h != prev_hash:
            visual_change_count += 1
            prev_hash = h
    visual_change_count = max(0, visual_change_count - 1)

    unique_visual_frames = sum(1 for g in duplicate_groups if len(g) > 0)

    return {
        "asset_id": asset_id,
        "brand_id": brand_id,
        "duration_seconds": duration,
        "frames_sampled": frames_sampled,
        "frames_analysed": len(analysed),
        "frames_failed": len(failed),
        "unique_visual_frames": unique_visual_frames,
        "duplicate_frame_groups": duplicate_groups,
        "coverage_notes": coverage_notes,
        # Per-attribute three-state fields with evidence_frames
        "human_anywhere": by_field["human_present"]["derived"],
        "human_evidence_frames": by_field["human_present"]["evidence_frames"],
        "human_positive_count": by_field["human_present"]["positive_count"],
        "human_negative_count": by_field["human_present"]["negative_count"],
        "human_unknown_count": by_field["human_present"]["unknown_count"],
        "human_observed_count": by_field["human_present"]["observed_count"],
        "human_observed_ratio": by_field["human_present"]["observed_ratio"],
        "golfer_anywhere": by_field["golfer_present"]["derived"],
        "golfer_evidence_frames": by_field["golfer_present"]["evidence_frames"],
        "product_anywhere": by_field["product_closeup"]["derived"],
        "product_evidence_frames": by_field["product_closeup"]["evidence_frames"],
        "product_observed_count": by_field["product_closeup"]["observed_count"],
        "product_observed_ratio": by_field["product_closeup"]["observed_ratio"],
        "club_anywhere": by_field["golf_club_present"]["derived"],
        "club_evidence_frames": by_field["golf_club_present"]["evidence_frames"],
        "ball_anywhere": by_field["golf_ball_present"]["derived"],
        "ball_evidence_frames": by_field["golf_ball_present"]["evidence_frames"],
        "screen_anywhere": by_field["screen_visible"]["derived"],
        "screen_evidence_frames": by_field["screen_visible"]["evidence_frames"],
        "text_overlay_anywhere": by_field["text_overlay"]["derived"],
        "text_evidence_frames": by_field["text_overlay"]["evidence_frames"],
        "text_observed_count": by_field["text_overlay"]["observed_count"],
        "text_observed_ratio": by_field["text_overlay"]["observed_ratio"],
        "logo_anywhere": by_field["logo_visible"]["derived"],
        "logo_evidence_frames": by_field["logo_visible"]["evidence_frames"],
        "simulator_anywhere": by_field["simulator_environment"]["derived"],
        "simulator_evidence_frames": by_field["simulator_environment"]["evidence_frames"],
        # Opening snapshot (separate from rest)
        "opening": {
            "timestamp": opening.get("timestamp") if opening else None,
            "human_present": _opening("human_present"),
            "face_visible": _opening("face_visible"),
            "golfer_present": _opening("golfer_present"),
            "club_present": _opening("golf_club_present"),
            "ball_present": _opening("golf_ball_present"),
            "screen_visible": _opening("screen_visible"),
            "text_overlay": _opening("text_overlay"),
            "logo_visible": _opening("logo_visible"),
            "shot_type": _opening("shot_type"),
            "dominant_subject": _opening("dominant_subject"),
        },
        # Closing snapshot
        "closing": {
            "timestamp": closing.get("timestamp") if closing else None,
            "human_present": _closing("human_present"),
            "text_overlay": _closing("text_overlay"),
            "logo_visible": _closing("logo_visible"),
            "shot_type": _closing("shot_type"),
            "dominant_subject": _closing("dominant_subject"),
        },
        # Early-3s intelligence (sparse-frame honest)
        "early_human_present": early_human_present,
        "early_text_present": early_text_present,
        "early_subject_change": early_subject_change,
        # Transitions + structure
        "transitions": transitions,
        "dominant_subject_changes": len(set(dom_seq) - {None, "unknown"}),
        "shot_type_changes": len(set(shot_seq) - {None, "unknown"}),
        "text_overlay_changes": sum(1 for i in range(1, len(text_seq))
                                       if text_seq[i] is not None and text_seq[i-1] is not None
                                       and text_seq[i] != text_seq[i-1]),
        "visual_change_count": visual_change_count,
        "dominant_subject_progression": dom_seq,
        "shot_type_progression": shot_seq,
        "timestamps": [f.get("timestamp") for f in analysed],
        "analysis_version": P12A_ANALYSIS_VERSION,
    }


def _ensure_dirs():
    P12A_FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    P12A_OBSERVATIONS.parent.mkdir(parents=True, exist_ok=True)


def _find_asset(asset_id: str):
    for a in _load_canonical_assets():
        if a.get("asset_id") == asset_id:
            return a
    return None


def _load_canonical_assets():
    try:
        from app import _P06A_CLEAN_CANONICAL
        path = _P06A_CLEAN_CANONICAL
    except Exception:
        path = Path("/data/campaign-os/intelligence/history/p06a/canonical-history.cleaned.jsonl")
        if not path.exists():
            return []
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("kind") == "asset":
            out.append(r)
    return out


def observe_video(asset_id: str, brand_id: str,
                   max_dim: int = 1024, quality: int = 80,
                   model: Optional[str] = None,
                   use_adaptive: bool = True,
                   fixed_n_frames: int = 4) -> Dict[str, Any]:
    """Slice D: adaptive VIDEO observation.

    use_adaptive=False forces a fixed N-frame sample (no dedupe, no adaptive
    inserts) so the comparison run can be benchmarked against adaptive.
    """
    _ensure_dirs()
    asset = _find_asset(asset_id)
    if not asset:
        return {"ok": False, "error": f"asset_id '{asset_id}' not in canonical"}
    asset_brand = asset.get("brand_id") or brand_id
    if asset_brand and asset_brand != brand_id:
        return {"ok": False, "error": f"brand mismatch: asset={asset_brand} request={brand_id}"}
    media_type = asset.get("media_type") or ""
    if media_type != "VIDEO":
        return {"ok": False, "error": f"observe_video requires VIDEO (got {media_type})"}

    media_url, duration_meta, fetch_err = _resolve_video_metadata(asset)
    if fetch_err:
        return {"ok": False, "error": f"metadata fetch failed: {fetch_err}",
                "failure_type": "source_unavailable"}
    if not media_url:
        return {"ok": False, "error": "no media_url"}

    raw_bytes, err = _download_image_raw(media_url, max_bytes=80_000_000)
    if not raw_bytes:
        return {"ok": False, "error": f"download_failed: {err}",
                "failure_type": "download_failed"}
    video_content_hash = _video_content_hash(raw_bytes)

    tmp_dir = Path(tempfile.gettempdir()) / "creative_genome_videos"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{asset_id}__{video_content_hash}.mp4"
    try:
        tmp_path.write_bytes(raw_bytes)
    except Exception as e:
        return {"ok": False, "error": f"tmp_write_failed: {e}",
                "failure_type": "download_failed"}

    ffprobe_duration = _ffprobe_duration(tmp_path)
    duration = ffprobe_duration if ffprobe_duration is not None else duration_meta
    coverage_notes = []
    if ffprobe_duration is None and duration_meta is not None:
        coverage_notes.append(f"duration_from_meta_only ({duration_meta:.1f}s)")
    elif ffprobe_duration is None and duration_meta is None:
        coverage_notes.append("duration_unknown")
        if duration is None:
            duration = 5.0

    if use_adaptive:
        timestamps = _adaptive_initial_timestamps(duration)
    else:
        n = max(1, fixed_n_frames)
        if duration <= 0:
            timestamps = [0.0]
        else:
            timestamps = [duration * i / max(1, n - 1) for i in range(n)]
            timestamps[-1] = max(0.0, min(duration - 0.1, timestamps[-1]))

    candidate_frames: List[bytes] = []
    candidate_times: List[float] = []
    candidate_pils: List[Any] = []
    extraction_failures = []
    for ts in timestamps:
        out_jpeg = tmp_dir / f"{asset_id}__t{int(ts*1000):06d}.jpg"
        fb = _extract_frame(tmp_path, ts, out_jpeg, width=max_dim)
        if fb:
            pil = _bytes_to_pil(fb)
            if pil:
                candidate_frames.append(fb)
                candidate_times.append(ts)
                candidate_pils.append(pil)
            else:
                extraction_failures.append({"timestamp": ts, "reason": "decode_failed"})
        else:
            extraction_failures.append({"timestamp": ts, "reason": "frame_extract_failed"})
    if not candidate_frames:
        try: tmp_path.unlink()
        except Exception: pass
        return {"ok": False, "error": "no frames extracted",
                "failure_type": "frame_extract_failed",
                "candidates_requested": len(timestamps),
                "extraction_failures": extraction_failures}

    if use_adaptive:
        unique_indices, groups = _dedupe_consecutive_frames(
            candidate_pils, candidate_times,
            threshold=VIDEO_NEAR_IDENTICAL_THRESHOLD,
        )
    else:
        unique_indices = list(range(len(candidate_frames)))
        groups = [[i] for i in range(len(candidate_frames))]

        # Adaptive expansion: insert midpoints between divergent consecutive unique frames
        new_ts_to_insert: list = []
        if use_adaptive and len(unique_indices) < VIDEO_FRAME_CAP and duration:
            for k in range(len(unique_indices) - 1):
                a_idx = unique_indices[k]
                b_idx = unique_indices[k+1]
                diff = _image_mean_pixel_diff(candidate_pils[a_idx], candidate_pils[b_idx])
                if diff > VIDEO_NEAR_IDENTICAL_THRESHOLD * 4:
                    ts_a = candidate_times[a_idx]
                    ts_b = candidate_times[b_idx]
                    midpoint = (ts_a + ts_b) / 2.0
                    if (midpoint - ts_a >= VIDEO_MIN_GAP_SECONDS
                            and ts_b - midpoint >= VIDEO_MIN_GAP_SECONDS):
                        new_ts_to_insert.append((b_idx, midpoint))
        for offset, (orig_b_idx, new_ts) in enumerate(new_ts_to_insert):
            if len(unique_indices) >= VIDEO_FRAME_CAP:
                break
            out_jpeg = tmp_dir / f"{asset_id}__t{int(new_ts*1000):06d}_mid.jpg"
            fb = _extract_frame(tmp_path, new_ts, out_jpeg, width=max_dim)
            if fb:
                pil = _bytes_to_pil(fb)
                if pil:
                    candidate_frames.append(fb)
                    candidate_times.append(new_ts)
                    candidate_pils.append(pil)
                    insert_at = unique_indices.index(orig_b_idx) + offset
                    unique_indices.insert(insert_at, len(candidate_frames) - 1)
                    groups.insert(insert_at, [len(candidate_frames) - 1])
        # Re-sort by timestamp
        order = sorted(range(len(unique_indices)),
                       key=lambda j: candidate_times[unique_indices[j]])
        unique_indices = [unique_indices[j] for j in order]
        groups = [groups[j] for j in order]

    frame_results = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    total_ms = 0
    cache_hits = 0
    vision_calls = 0
    for ui in unique_indices:
        frame_cache_key = f"{asset_id}__frame_t{int(candidate_times[ui]*1000):06d}"
        r = _analyse_one_frame(
            asset_id, asset_brand, candidate_times[ui],
            candidate_frames[ui], frame_cache_key,
            max_dim=max_dim, quality=quality, model=model,
        )
        frame_results.append(r)
        if r.get("cached"):
            cache_hits += 1
        else:
            vision_calls += 1
        u = r.get("model_usage") or {}
        total_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
        total_usage["completion_tokens"] += u.get("completion_tokens", 0)
        total_usage["total_tokens"] += u.get("total_tokens", 0)
        total_ms += r.get("duration_ms", 0) or 0

    derived = _derive_video_features(
        asset_id, asset_brand, frame_results,
        frames_sampled=len(candidate_frames),
        duration=duration,
        duplicate_groups=groups,
        coverage_notes=coverage_notes + extraction_failures,
    )

    video_record = {
        "asset_id": asset_id,
        "brand_id": asset_brand,
        "media_type": "VIDEO",
        "kind": "video_observation",
        "analysis_version": P12A_ANALYSIS_VERSION,
        "vision_model": model or P12A_VISION_MODEL,
        "duration_seconds": duration,
        "video_content_hash": video_content_hash,
        "frames_sampled": derived["frames_sampled"],
        "frames_analysed": derived["frames_analysed"],
        "frames_failed": derived["frames_failed"],
        "unique_visual_frames": derived["unique_visual_frames"],
        "duplicate_frame_groups": derived["duplicate_frame_groups"],
        "coverage_notes": derived["coverage_notes"],
        "frames": [
            {
                "timestamp": (candidate_times[ui] if ui < len(candidate_times) else None),
                "content_hash": r.get("content_hash"),
                "ok": r.get("ok"),
                "error": r.get("error"),
                "observation_id": r.get("observation_id"),
                "model_usage": r.get("model_usage"),
                "duration_ms": r.get("duration_ms"),
                "analysis_version": r.get("analysis_version"),
                "derivative_stats": r.get("derivative_stats"),
            }
            for ui, r in zip(unique_indices, frame_results)
        ],
        "derived": derived,
        "total_usage": total_usage,
        "total_duration_ms": total_ms,
        "vision_calls": vision_calls,
        "cache_hits": cache_hits,
        "use_adaptive": use_adaptive,
        "fixed_n_frames": (fixed_n_frames if not use_adaptive else None),
        "context_inputs_forbidden": [
            "caption", "hashtags", "filename", "campaign", "service",
            "topic", "product_name", "performance", "win_score",
            "historical_classification",
        ],
        "context_inputs_actually_sent": ["image_url (data URL) only — per frame"],
        "analysed_at": time.time(),
    }
    _append_observation(video_record)

    try: tmp_path.unlink()
    except Exception: pass

    return {
        "ok": True,
        "asset_id": asset_id,
        "brand_id": asset_brand,
        "media_type": media_type,
        "duration_seconds": duration,
        "frames_sampled": derived["frames_sampled"],
        "frames_analysed": derived["frames_analysed"],
        "frames_failed": derived["frames_failed"],
        "unique_visual_frames": derived["unique_visual_frames"],
        "duplicate_frame_groups": derived["duplicate_frame_groups"],
        "vision_calls": vision_calls,
        "cache_hits": cache_hits,
        "total_usage": total_usage,
        "total_duration_ms": total_ms,
        "use_adaptive": use_adaptive,
        "fixed_n_frames": (fixed_n_frames if not use_adaptive else None),
        "derived": derived,
        "frames": [
            {
                "timestamp": (candidate_times[ui] if ui < len(candidate_times) else None),
                "ok": r.get("ok"),
                "error": r.get("error"),
                "observation_id": r.get("observation_id"),
                "duration_ms": r.get("duration_ms"),
            }
            for ui, r in zip(unique_indices, frame_results)
        ],
    }


def video_contact_sheet_html(asset_id: str) -> str:
    """Build an HTML contact sheet for one VIDEO asset."""
    rec = None
    if P12A_OBSERVATIONS.exists():
        for line in P12A_OBSERVATIONS.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if (r.get("kind") == "video_observation"
                    and r.get("asset_id") == asset_id):
                rec = r
                break
    if not rec:
        return f"<html><body><h1>No video observation for {asset_id}</h1></body></html>"
    derived = rec.get("derived") or {}
    frames = rec.get("frames") or []
    import base64
    frame_html = []
    for i, fr in enumerate(frames):
        ts_ms = int((fr.get("timestamp") or 0) * 1000)
        frame_key = f"{asset_id}__frame_t{ts_ms:06d}"
        ch = fr.get("content_hash") or ""
        deriv_candidates = list(P12A_FRAMES_DIR.glob(f"{frame_key}__{ch[:16]}*derivative.jpg"))
        if not deriv_candidates:
            deriv_candidates = list(P12A_FRAMES_DIR.glob(f"{frame_key}__*derivative.jpg"))
        deriv_path = deriv_candidates[0] if deriv_candidates else None
        deriv_b64 = None
        if deriv_path and deriv_path.exists():
            try:
                deriv_b64 = base64.b64encode(deriv_path.read_bytes()).decode("ascii")
            except Exception:
                deriv_b64 = None
        obs = {}
        if fr.get("observation_id"):
            full = _load_observation_by_id(fr["observation_id"])
            if full:
                obs = full.get("observations") or {}
        def _cell(k):
            o = obs.get(k) or {}
            v = o.get("value")
            c = o.get("confidence") or "—"
            if v is None: vs = "null"
            elif isinstance(v, bool): vs = "T" if v else "F"
            else: vs = str(v)
            return f"{vs}/{c[0].upper()}"
        img = (f'<img src="data:image/jpeg;base64,{deriv_b64}" alt="frame {i}"/>'
               if deriv_b64 else "<em>no derivative</em>")
        frame_html.append(f"""
        <div class="frame">
          <h3>frame #{i} t={fr.get('timestamp')}s {'(cached)' if fr.get('duration_ms') is None else ''}</h3>
          <div class="img">{img}</div>
          <table>
            <tr><th>human_present</th><td>{_cell('human_present')}</td></tr>
            <tr><th>golfer_present</th><td>{_cell('golfer_present')}</td></tr>
            <tr><th>golf_club_present</th><td>{_cell('golf_club_present')}</td></tr>
            <tr><th>golf_ball_present</th><td>{_cell('golf_ball_present')}</td></tr>
            <tr><th>screen_visible</th><td>{_cell('screen_visible')}</td></tr>
            <tr><th>text_overlay</th><td>{_cell('text_overlay')}</td></tr>
            <tr><th>logo_visible</th><td>{_cell('logo_visible')}</td></tr>
            <tr><th>shot_type</th><td>{_cell('shot_type')}</td></tr>
            <tr><th>dominant_subject</th><td>{_cell('dominant_subject')}</td></tr>
          </table>
          <div class="status">ok={fr.get('ok')} error={fr.get('error') or 'none'} ms={fr.get('duration_ms')}</div>
        </div>""")
    op = derived.get("opening") or {}
    cl = derived.get("closing") or {}
    body = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Video {asset_id}</title>
<style>
body {{ font-family: ui-monospace, monospace; background: #111; color: #ddd; padding: 16px; }}
.frames {{ display: flex; gap: 12px; flex-wrap: wrap; }}
.frame {{ background: #1a1a1a; border: 1px solid #333; padding: 10px; border-radius: 6px; width: 280px; }}
.frame h3 {{ margin: 0 0 6px; font-size: 12px; color: #999; }}
.frame img {{ width: 100%; height: auto; display: block; border-radius: 4px; }}
table {{ width: 100%; font-size: 10px; margin-top: 6px; }}
th {{ text-align: left; color: #888; font-weight: normal; }}
td {{ text-align: right; }}
.status {{ color: #888; font-size: 10px; margin-top: 4px; }}
.meta {{ background: #181818; padding: 12px; border: 1px solid #333; margin-bottom: 16px; border-radius: 6px; }}
.meta h2 {{ margin: 0 0 8px; font-size: 13px; color: #aaa; }}
.meta pre {{ font-size: 11px; }}
</style></head><body>
<h1>Video contact sheet — {asset_id}</h1>
<div class="meta">
  <h2>Coverage</h2>
  <pre>duration_seconds = {derived.get('duration_seconds')}
frames_sampled = {derived.get('frames_sampled')}
frames_analysed = {derived.get('frames_analysed')}
frames_failed = {derived.get('frames_failed')}
unique_visual_frames = {derived.get('unique_visual_frames')}
duplicate_frame_groups = {derived.get('duplicate_frame_groups')}</pre>
  <h2>Asset-level features (three-state)</h2>
  <pre>human_anywhere        = {derived.get('human_anywhere')}  pos={derived.get('human_positive_count')} neg={derived.get('human_negative_count')} unk={derived.get('human_unknown_count')} observed_ratio={derived.get('human_observed_ratio')} frames={derived.get('human_evidence_frames')}
golfer_anywhere       = {derived.get('golfer_anywhere')}  frames={derived.get('golfer_evidence_frames')}
product_anywhere      = {derived.get('product_anywhere')}  observed={derived.get('product_observed_count')} ratio={derived.get('product_observed_ratio')} frames={derived.get('product_evidence_frames')}
club_anywhere         = {derived.get('club_anywhere')}  frames={derived.get('club_evidence_frames')}
ball_anywhere         = {derived.get('ball_anywhere')}  frames={derived.get('ball_evidence_frames')}
screen_anywhere       = {derived.get('screen_anywhere')}  frames={derived.get('screen_evidence_frames')}
text_overlay_anywhere = {derived.get('text_overlay_anywhere')}  observed={derived.get('text_observed_count')} ratio={derived.get('text_observed_ratio')} frames={derived.get('text_evidence_frames')}
logo_anywhere         = {derived.get('logo_anywhere')}  frames={derived.get('logo_evidence_frames')}
simulator_anywhere    = {derived.get('simulator_anywhere')}  frames={derived.get('simulator_evidence_frames')}</pre>
  <h2>Opening (first frame)</h2>
  <pre>{json.dumps(op, indent=2)}

early_human_present = {derived.get('early_human_present')}
early_text_present = {derived.get('early_text_present')}
early_subject_change = {derived.get('early_subject_change')}</pre>
  <h2>Closing (last frame)</h2>
  <pre>{json.dumps(cl, indent=2)}</pre>
  <h2>Transitions</h2>
  <pre>{derived.get('transitions')}
visual_change_count = {derived.get('visual_change_count')}
dominant_subject_changes = {derived.get('dominant_subject_changes')}
shot_type_changes = {derived.get('shot_type_changes')}
text_overlay_changes = {derived.get('text_overlay_changes')}</pre>
  <h2>Dominant subject progression</h2>
  <pre>{derived.get('dominant_subject_progression')}</pre>
  <h2>Timestamps</h2>
  <pre>{derived.get('timestamps')}</pre>
</div>
<div class="frames">{''.join(frame_html)}</div>
</body></html>"""
    return body
