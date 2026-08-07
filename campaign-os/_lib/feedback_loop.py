"""
feedback_loop.py — Self-improvement for the image generator.

Tracks per-image performance across platforms, correlates performance
with the image's DNA attributes, and surfaces learned signals that the
router injects into every future prompt.

DATA MODEL

data/brand-directory/<brand>/feedback/

  image-performance.json
    {
      "version": 1,
      "brand": "swing-shack",
      "updated": 1234567890.0,
      "records": [
        {
          "image_id": "<ref_id or generated-<hash>>",
          "kind": "reference" | "generated",
          "source": "ig" | "ga4" | "gmb" | "manual" | "import",
          "captured_at": 1234567890.0,
          "platform_post_id": "ig_post_1234",         # optional
          "captured_signal": {
            "impressions": 1200,
            "likes": 47,
            "comments": 3,
            "saves": 12,
            "reach": 980,
            "link_clicks": 24,
            "ga_sessions": 36,
            "ga_conversions": 2,
            "gmb_calls": 1,
            "bookings": 1,
          },
          "score": 0.78,                             # 0..1 composite win score
          "dna_snapshot": {                          # captured at scoring time
            "palette": ["#0b0d0e", "#f5c842"],
            "mood": ["dark", "premium"],
            "luminance": {"bucket": "mid", "value": 0.3},
            "orientation": "square",
            "product_tags": ["GTS Putter"],
            "typography": {"primary_family": "Inter", "weight": "Bold"},
          },
          "notes": "Black-friday promo, dark hero, GTS featured"
        }
      ]
    }

  learned-signals.json
    {
      "version": 1,
      "brand": "swing-shack",
      "updated": 1234567890.0,
      "samples": 47,
      "win_threshold": 0.65,
      "preferences": {
        "luminance_bucket": {"dark": 0.71, "mid": 0.52, "bright": 0.44},
        "mood": {"premium": 0.74, "studio": 0.62, "promotional": 0.55, ...},
        "orientation": {"square": 0.68, "portrait": 0.55, "landscape": 0.49},
        "palette_centroid_hex": ["#0b0d0e", "#f5c842"],
        "palette_warmth_score": 0.72,            # higher = warmer wins
        "product_tags": {"GTS Putter": 0.78, "TrackMan": 0.71, ...},
        "typography_family": {"Inter-Bold": 0.69, ...}
      },
      "anti_preferences": {
        # attributes that correlate NEGATIVELY with wins
        "luminance_bucket": {"bright": 0.42},
        "mood": {"muted": 0.38},
        ...
      },
      "decision_criteria": {
        # weights used to compute the composite score
        "click_weight": 0.50,
        "booking_weight": 0.40,
        "engagement_weight": 0.10
      }
    }

The composite score formula:

  score = (
    normalised_clicks    * click_weight    +  # from link_clicks + ga_sessions
    normalised_bookings  * booking_weight  +  # from bookings + ga_conversions + gmb_calls
    normalised_engagement* engagement_weight   # from likes + saves + comments / reach
  )

Win threshold defaults to 0.65 — i.e. the top 35% of images by composite score.
This is configurable via /api/image/feedback/threshold.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _default_brand_root() -> Path:
    repo_root = Path(__file__).resolve().parent.parent.parent
    return repo_root / "data" / "brand-directory"


def _feedback_dir(brand: str, root: Path | None = None) -> Path:
    if root is None:
        root = _default_brand_root()
    out = root / brand / "feedback"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _perf_path(brand: str, root: Path | None = None) -> Path:
    return _feedback_dir(brand, root) / "image-performance.json"


def _learned_path(brand: str, root: Path | None = None) -> Path:
    return _feedback_dir(brand, root) / "learned-signals.json"


# ---------------------------------------------------------------------------
# Performance record I/O
# ---------------------------------------------------------------------------


def _empty_perf(brand: str) -> dict[str, Any]:
    return {"version": 1, "brand": brand, "updated": time.time(), "records": [], "win_threshold": 0.65}


def load_performance(brand: str, root: Path | None = None) -> dict[str, Any]:
    p = _perf_path(brand, root)
    if not p.exists():
        return _empty_perf(brand)
    try:
        return json.loads(p.read_text())
    except Exception:
        return _empty_perf(brand)


def save_performance(perf: dict[str, Any], brand: str, root: Path | None = None) -> Path:
    p = _perf_path(brand, root)
    perf["updated"] = time.time()
    perf["brand"] = brand
    p.write_text(json.dumps(perf, indent=2, default=str))
    return p


def add_record(
    brand: str,
    *,
    image_id: str,
    kind: str,
    source: str,
    captured_signal: dict[str, Any],
    dna_snapshot: dict[str, Any] | None = None,
    platform_post_id: str | None = None,
    notes: str = "",
    root: Path | None = None,
) -> dict[str, Any]:
    """Append a single performance record. Auto-computes the score.

    Returns the record dict (with computed score).
    """
    if kind not in ("reference", "generated"):
        raise ValueError(f"kind must be reference|generated, got {kind}")
    if source not in ("ig", "ga4", "gmb", "manual", "import"):
        raise ValueError(f"source must be ig|ga4|gmb|manual|import, got {source}")

    perf = load_performance(brand, root)
    score = compute_score(captured_signal)
    record = {
        "image_id": image_id,
        "kind": kind,
        "source": source,
        "captured_at": time.time(),
        "platform_post_id": platform_post_id,
        "captured_signal": captured_signal,
        "score": score,
        "dna_snapshot": dna_snapshot or {},
        "notes": notes,
    }
    perf.setdefault("records", []).append(record)
    save_performance(perf, brand, root)
    return record


def list_records(
    brand: str,
    *,
    min_score: float | None = None,
    kind: str | None = None,
    limit: int | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    perf = load_performance(brand, root)
    out = perf.get("records", [])
    if kind:
        out = [r for r in out if r.get("kind") == kind]
    if min_score is not None:
        out = [r for r in out if r.get("score", 0) >= min_score]
    out = sorted(out, key=lambda r: r.get("captured_at", 0), reverse=True)
    if limit:
        out = out[:limit]
    return out


def summary(brand: str, root: Path | None = None) -> dict[str, Any]:
    """Aggregate counts + averages."""
    perf = load_performance(brand, root)
    records = perf.get("records", [])
    if not records:
        return {"samples": 0, "brand": brand, "win_threshold": perf.get("win_threshold", 0.65)}
    scores = [r.get("score", 0) for r in records]
    threshold = perf.get("win_threshold", 0.65)
    wins = [r for r in records if r.get("score", 0) >= threshold]
    return {
        "samples": len(records),
        "wins": len(wins),
        "win_rate": round(len(wins) / len(records), 3) if records else 0,
        "win_threshold": threshold,
        "avg_score": round(statistics.mean(scores), 3) if scores else 0,
        "median_score": round(statistics.median(scores), 3) if scores else 0,
        "score_range": [round(min(scores), 3), round(max(scores), 3)] if scores else [0, 0],
        "sources": {s: sum(1 for r in records if r.get("source") == s) for s in {"ig", "ga4", "gmb", "manual", "import"}},
    }


# ---------------------------------------------------------------------------
# Score calculation
# ---------------------------------------------------------------------------

# Default decision criteria — these weights encode what counts as a win
# based on Christelle's brief: "sales / clicks / bookings"
DEFAULT_CRITERIA = {
    "click_weight": 0.50,
    "booking_weight": 0.40,
    "engagement_weight": 0.10,
}


def _safe_norm(value: float, p50: float, p95: float) -> float:
    """Normalise a metric to [0, 1] using a soft sigmoid between p50 and p95.

    p50 -> 0.5
    p95 -> 0.95
    values below p50 fall off but never below 0
    values above p95 saturate at 1.0
    """
    if p95 == p50:
        return 0.5
    # Sigmoid centred at p50, scaled so p95 -> 0.95
    k = math.log(0.95 / 0.05) / (p95 - p50)  # inverse temp
    try:
        return 1.0 / (1.0 + math.exp(-k * (value - p50)))
    except OverflowError:
        return 0.0 if value < p50 else 1.0


def compute_score(
    captured_signal: dict[str, Any],
    criteria: dict[str, float] | None = None,
) -> float:
    """Compute the composite win score from a single record's signals.

    We compute three sub-scores:
      click_score     = (link_clicks + ga_sessions)             — stop scroll + drive traffic
      booking_score   = (bookings + ga_conversions + gmb_calls) — drive action
      engagement_score = (likes + saves + comments) / reach     — stop scroll quality

    Each is normalised using a soft sigmoid based on hand-tuned typical
    ranges (so a post with 100 likes and 5 saves scores higher than one
    with 5 likes and 0 saves). Then they're weighted-summed per the
    decision criteria. The result is clamped to [0, 1].
    """
    criteria = {**DEFAULT_CRITERIA, **(criteria or {})}

    sig = {k: float(v or 0) for k, v in captured_signal.items() if isinstance(v, (int, float))}

    clicks = sig.get("link_clicks", 0) + sig.get("ga_sessions", 0)
    bookings = sig.get("bookings", 0) + sig.get("ga_conversions", 0) + sig.get("gmb_calls", 0)
    reach = sig.get("reach", 0) or sig.get("impressions", 0) or 1
    engagement = sig.get("likes", 0) + sig.get("saves", 0) + sig.get("comments", 0)
    engagement_rate = engagement / max(reach, 1)

    # Typical ranges per the brief — these are sensible mid-points for a
    # single post in a 2-week window. Will be re-tuned by the scorer when
    # real data accumulates.
    click_score = _safe_norm(clicks, p50=10, p95=80)
    booking_score = _safe_norm(bookings, p50=1, p95=10)
    engagement_score = _safe_norm(engagement_rate * 100, p50=2.0, p95=10.0)

    composite = (
        click_score * criteria["click_weight"]
        + booking_score * criteria["booking_weight"]
        + engagement_score * criteria["engagement_weight"]
    )
    return max(0.0, min(1.0, round(composite, 4)))


# ---------------------------------------------------------------------------
# Scoring / correlation — turn records into learned signals
# ---------------------------------------------------------------------------


def compute_learned_signals(
    brand: str,
    *,
    root: Path | None = None,
    min_samples: int = 5,
) -> dict[str, Any]:
    """Correlate DNA attributes with composite scores across all records.

    Returns a learned-signals document. If there are fewer than
    `min_samples` records, returns a "not enough data" stub that the
    router knows to ignore.
    """
    perf = load_performance(brand, root)
    records = perf.get("records", [])
    threshold = perf.get("win_threshold", 0.65)

    if len(records) < min_samples:
        return {
            "version": 1,
            "brand": brand,
            "updated": time.time(),
            "samples": len(records),
            "win_threshold": threshold,
            "ready": False,
            "preferences": {},
            "anti_preferences": {},
            "decision_criteria": DEFAULT_CRITERIA,
            "_note": f"need at least {min_samples} samples; have {len(records)}",
        }

    winners = [r for r in records if r.get("score", 0) >= threshold]
    losers = [r for r in records if r.get("score", 0) < threshold]

    prefs: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    anti: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for rec in winners:
        _accumulate(prefs, rec)
    for rec in losers:
        _accumulate(anti, rec)

    # Convert to averages
    pref_avg = _flatten_to_averages(prefs)
    anti_avg = _flatten_to_averages(anti)

    # Compute palette centroid (weighted by winner score)
    centroid = _palette_centroid(winners)

    return {
        "version": 1,
        "brand": brand,
        "updated": time.time(),
        "samples": len(records),
        "wins": len(winners),
        "losses": len(losers),
        "win_threshold": threshold,
        "ready": True,
        "preferences": pref_avg,
        "anti_preferences": anti_avg,
        "palette_centroid_hex": centroid,
        "decision_criteria": DEFAULT_CRITERIA,
    }


def _accumulate(
    bucket: dict[str, dict[str, list[float]]],
    rec: dict[str, Any],
) -> None:
    """Add this record's DNA into the accumulator, weighted by score."""
    dna = rec.get("dna_snapshot", {}) or {}
    score = rec.get("score", 0) or 0
    if score <= 0:
        return

    # Luminance bucket
    lum = dna.get("luminance", {}) or {}
    bucket_name = lum.get("bucket") if isinstance(lum, dict) else None
    if bucket_name:
        bucket["luminance_bucket"][bucket_name].append(score)

    # Mood keywords
    for m in dna.get("mood", []) or []:
        bucket["mood"][m].append(score)

    # Orientation
    orientation = dna.get("orientation")
    if orientation:
        bucket["orientation"][orientation].append(score)

    # Product tags
    for p in dna.get("product_tags", []) or []:
        bucket["product_tags"][p].append(score)

    # Typography
    typo = dna.get("typography", {}) or {}
    family = typo.get("primary_family") if isinstance(typo, dict) else None
    if family:
        bucket["typography_family"][family].append(score)


def _flatten_to_averages(
    bucket: dict[str, dict[str, list[float]]],
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for category, items in bucket.items():
        cat_out: dict[str, float] = {}
        for key, vals in items.items():
            if vals:
                cat_out[key] = round(sum(vals) / len(vals), 3)
        if cat_out:
            out[category] = cat_out
    return out


def _palette_centroid(records: list[dict[str, Any]]) -> list[str]:
    """Weighted-average of palettes across winners, return top-3 hex codes."""
    try:
        from PIL import ImageColor
    except Exception:
        return []
    rgb_acc = [0.0, 0.0, 0.0]
    weight_total = 0.0
    for rec in records:
        dna = rec.get("dna_snapshot", {}) or {}
        score = rec.get("score", 0) or 0
        if score <= 0:
            continue
        palette = dna.get("palette", []) or []
        for hexcol in palette[:3]:
            try:
                v = ImageColor.getrgb(hexcol)
                if len(v) == 4:
                    v = v[:3]
                rgb_acc[0] += v[0] * score
                rgb_acc[1] += v[1] * score
                rgb_acc[2] += v[2] * score
                weight_total += score
            except Exception:
                pass
    if weight_total == 0:
        return []
    r = int(rgb_acc[0] / weight_total)
    g = int(rgb_acc[1] / weight_total)
    b = int(rgb_acc[2] / weight_total)
    return ["#" + "".join(f"{c:02x}" for c in (r, g, b))]


def save_learned_signals(
    signals: dict[str, Any],
    brand: str,
    root: Path | None = None,
) -> Path:
    p = _learned_path(brand, root)
    signals["updated"] = time.time()
    p.write_text(json.dumps(signals, indent=2, default=str))
    return p


def load_learned_signals(brand: str, root: Path | None = None) -> dict[str, Any]:
    p = _learned_path(brand, root)
    if not p.exists():
        # Compute on first read
        signals = compute_learned_signals(brand, root=root)
        save_learned_signals(signals, brand, root)
        return signals
    try:
        return json.loads(p.read_text())
    except Exception:
        return compute_learned_signals(brand, root=root)


# ---------------------------------------------------------------------------
# Signals -> prompt fragment
# ---------------------------------------------------------------------------


def signals_to_prompt(signals: dict[str, Any]) -> str:
    """Render the learned signals as a "WIN PROFILE" prompt fragment.

    The router prepends this to every generation prompt so the generator
    leans toward what has actually moved the needle.
    """
    if not signals or not signals.get("ready"):
        return ""

    parts: list[str] = ["LEARNED WIN PROFILE (based on prior post performance):"]

    # Palette centroid
    centroid = signals.get("palette_centroid_hex") or []
    if centroid:
        parts.append(f"Winning colour palette leans toward: {', '.join(centroid[:3])}.")

    # Preferences
    prefs = signals.get("preferences", {}) or {}
    anti = signals.get("anti_preferences", {}) or {}

    # Luminance
    if prefs.get("luminance_bucket"):
        ranked = sorted(prefs["luminance_bucket"].items(), key=lambda x: -x[1])
        top = ranked[0]
        parts.append(f"Best-performing lighting: {top[0]} (avg score {top[1]}).")
    if anti.get("luminance_bucket"):
        ranked = sorted(anti["luminance_bucket"].items(), key=lambda x: x[1])
        bot = ranked[0]
        if bot[1] < 0.5:
            parts.append(f"Avoid lighting: {bot[0]} (avg score {bot[1]}).")

    # Mood
    if prefs.get("mood"):
        ranked = sorted(prefs["mood"].items(), key=lambda x: -x[1])
        top3 = [f"{m} ({s})" for m, s in ranked[:3]]
        parts.append(f"Best-performing moods: {', '.join(top3)}.")

    # Orientation
    if prefs.get("orientation"):
        ranked = sorted(prefs["orientation"].items(), key=lambda x: -x[1])
        top = ranked[0]
        parts.append(f"Best-performing orientation: {top[0]} (avg score {top[1]}).")

    # Products
    if prefs.get("product_tags"):
        ranked = sorted(prefs["product_tags"].items(), key=lambda x: -x[1])
        top3 = [f"{p} ({s})" for p, s in ranked[:3]]
        parts.append(f"Best-performing product focus: {', '.join(top3)}.")

    # Typography
    if prefs.get("typography_family"):
        ranked = sorted(prefs["typography_family"].items(), key=lambda x: -x[1])
        top = ranked[0]
        parts.append(f"Best-performing typography: {top[0]} (avg score {top[1]}).")

    if len(parts) == 1:
        return ""

    return " ".join(parts)


# ---------------------------------------------------------------------------
# DNA snapshot helper — capture the DNA at the moment a record is created
# ---------------------------------------------------------------------------


def snapshot_from_reference(ref_dna: dict[str, Any]) -> dict[str, Any]:
    """Extract a flat DNA snapshot from a Reference DNA dict."""
    return {
        "palette": list(ref_dna.get("palette", []) or []),
        "mood": list(ref_dna.get("mood", []) or []),
        "luminance": dict(ref_dna.get("luminance", {}) or {}),
        "orientation": ref_dna.get("orientation"),
        "product_tags": list(ref_dna.get("product_tags", []) or []),
        "typography": dict(ref_dna.get("typography", {}) or {}),
    }


def snapshot_from_generated(
    prompt: str,
    palette_hint: list[str] | None = None,
    mood_hint: list[str] | None = None,
    product_hint: list[str] | None = None,
) -> dict[str, Any]:
    """Build a synthetic DNA snapshot for a generated image (we don't have
    pixels yet — just hints from the prompt)."""
    return {
        "palette": list(palette_hint or []),
        "mood": list(mood_hint or []),
        "luminance": {"bucket": "unknown", "value": None},
        "orientation": None,
        "product_tags": list(product_hint or []),
        "typography": {},
        "_provenance": "prompt-derived",
        "_prompt": prompt[:500],
    }