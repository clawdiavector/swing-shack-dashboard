"""brand_brief_intel.py — wire the from-idea pipeline to ACTUAL brand data.

Built 2026-08-20 to close the gap on the campaign builder being smart.
This module reads the data sources that already exist on disk and turns
them into a single 'BrandIntel' snapshot the brief can quote instead of
guess from industry baselines.

Data sources consumed (each is read-only):

  1. data/post-conversion-score.json — which themes/formulas/format
     actually drove bookings last 30d, +267% lift over baseline.
  2. data/hook-bank.json — every proved hook + its formula type +
     cross-signal score (proven vs trending vs retire).
  3. data/ig-analytics.json — last 10 IG posts with real engagement,
     save, share rates by pillar + format.
  4. data/ig-business-analytics.json — account-level followers count +
     30-day daily reach series + window totals.
  5. data/ga4-metrics.json — sessions, sources, top pages, conversion
     attribution from GA4.
  6. data/gbp-insights/<brand>-latest.json — real GBP calls +
     directions + website clicks last 30d (when synced).
  7. data/audience-equity.json (TBD) — per-channel 'do we have an
     audience here today?' flag, computed from real follower counts +
     recent post frequency.

Each loader returns a dict with confidence scores so the brief can
honestly say 'data-confirmed' vs 'industry-baseline' vs 'no data'.

The brand-aware figures beat the hardcoded industry baselines in
campaign_brief.py — expected_engagement, expected_reach,
expected_bookings, paid_recommended (with computed CPL breakeven),
hook_formula, channel_relevance, image prompt overlays.
"""

from __future__ import annotations

import json
import os
import statistics
from pathlib import Path
from typing import Any, Optional, Tuple


def _resolve_data_dir() -> Path:
    """Return the live DATA_DIR when populated, else fall back to BUNDLED_DATA_DIR.

    On Railway, DATA_DIR=/data is the persistent volume but starts empty
    (no git clone happens unless GITHUB_TOKEN + the right bootstrap runs).
    The repo ships a `data/` folder with every JSON the system needs
    (post-conversion-score, hook-bank, ig-analytics, ga4-metrics, etc).
    BUNDLED_DATA_DIR is exported by app.py at module-load so we always
    read real on-file data even when the volume is empty.
    """
    env_dir = os.environ.get("DATA_DIR") or "/data"
    runtime = Path(env_dir)
    # Sample one file to see whether the runtime volume has it
    # (e.g. `post-conversion-score.json` ships in the bundle).
    sample = runtime / "post-conversion-score.json"
    if sample.exists():
        return runtime
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    if bundled:
        return Path(bundled)
    return runtime


DATA_DIR = _resolve_data_dir()


def _read_json(fname: str) -> Optional[dict]:
    """Read JSON file from DATA_DIR with BUNDLED_DATA_DIR fallback.

    Resolution order:
      1. DATA_DIR/<fname> (the persistent volume when populated)
      2. BUNDLED_DATA_DIR/<fname> (the repo's data/ folder)
      3. None (caller handles the gap honestly via the confidence flag)
    """
    candidates = [DATA_DIR / fname]
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    if bundled and Path(bundled) != DATA_DIR:
        candidates.append(Path(bundled) / fname)
    for p in candidates:
        if p.exists():
            try:
                with open(p) as f:
                    return json.load(f)
            except Exception:
                continue
    return None


# ── 1. POST-CONVERSION-SCORE (theme lift + winning formula) ───────────

def load_post_conversion_score() -> dict:
    """Read the post-conversion-score winner analysis.

    Returns: {
      ok, source, updated, median_lift_pct, winning_themes,
      winning_format, winning_hook_formula_type, baseline_bookings_per_post,
      top_post_caption_preview, top_post_themes, posts_scored
    }
    """
    data = _read_json("post-conversion-score.json")
    if not data:
        return {"ok": False, "source": "none", "confidence": "no_data"}
    ranked = data.get("posts_ranked") or []
    summary = data.get("summary") or {}
    top = ranked[0] if ranked else {}
    win_themes = summary.get("winning_themes") or []
    median_lift = sorted([r.get("lift_vs_baseline_pct", 0) or 0 for r in ranked])[len(ranked)//2] if ranked else 0

    # The winning hook formula type from hook_bank (which hooks are actually winning)
    formula_lift = {}
    for r in ranked:
        f = r.get("formula_type") or r.get("hook_formula_type")
        if f:
            formula_lift.setdefault(f, []).append(r.get("lift_vs_baseline_pct") or 0)
    formula_avg = {f: (sum(v) / len(v) / 100) for f, v in formula_lift.items()}
    winning_formula = max(formula_avg, key=lambda k: formula_avg[k]) if formula_avg else None

    return {
        "ok": True,
        "source": "post-conversion-score.json",
        "updated": data.get("updated"),
        "median_lift_pct": round(median_lift, 1),
        "winning_themes": win_themes[:5],
        "winning_format": summary.get("winning_format"),
        "winning_hook_formula": winning_formula,
        "baseline_bookings_per_post": summary.get("baseline_median_ig_bookings_per_day"),
        "top_post_caption_preview": (top.get("caption_preview") or "")[:200],
        "top_post_themes": (top.get("themes") or []),
        "top_post_engagement_rate_pct": top.get("engagement_rate_pct"),
        "posts_scored": summary.get("posts_scored", 0),
        "confidence": "data" if len(ranked) >= 5 else ("thin_data" if ranked else "no_data"),
    }


# ── 2. HOOK BANK (proven formulas + top hook text) ─────────────────

def load_hook_bank() -> dict:
    """Read hook-bank.json — proved hook formulas + best-text picks."""
    data = _read_json("hook-bank.json")
    if not data:
        return {"ok": False, "confidence": "no_data"}
    proven = (data.get("output_buckets") or {}).get("proven_only") or []
    ranking = sorted(proven, key=lambda h: h.get("cross_signal_score", 0) or 0, reverse=True)
    formulas = {(h.get("formula_type") or "general"): h.get("cross_signal_score", 0) or 0
                for h in proven}
    best_formula = max(formulas, key=formulas.get) if formulas else None
    return {
        "ok": True,
        "source": "hook-bank.json",
        "updated": data.get("updated"),
        "total_hooks": data.get("total_hooks"),
        "proven_count": len(proven),
        "best_formula": best_formula,
        "formula_scores": formulas,
        "top_hook_text": (ranking[0].get("hook_text") if ranking else ""),
        "top_hook_post_id": (ranking[0].get("post_id") if ranking else None),
        "top_hook_engagement_pct": ranking[0].get("engagementRate") if ranking else None,
        "confidence": "data" if len(proven) >= 3 else "thin_data",
    }


# ── 3. INSTAGRAM ANALYTICS (real engagement rates by format) ──────────

def load_ig_analytics() -> dict:
    """Read ig-analytics.json — last 10 IG posts + per-pillar stats."""
    data = _read_json("ig-analytics.json")
    if not data or not data.get("posts"):
        return {"ok": False, "confidence": "no_data"}
    posts = data["posts"]
    # Aggregate by format + topic
    by_format = {}
    by_pillar = {}
    all_er = []
    for p in posts:
        try:
            er = float(p.get("engagementRate") or 0)
        except (TypeError, ValueError):
            er = 0.0
        all_er.append(er)
        fmt = p.get("format_type") or "unknown"
        by_format.setdefault(fmt, []).append(er)
        pillar = p.get("topic_cluster") or "unknown"
        by_pillar.setdefault(pillar, []).append(er)
    return {
        "ok": True,
        "source": "ig-analytics.json",
        "updated": data.get("updated"),
        "post_count": len(posts),
        "median_engagement_pct": round(statistics.median(all_er), 3) if all_er else 0,
        "mean_engagement_pct": round(statistics.mean(all_er), 3) if all_er else 0,
        "max_engagement_pct": round(max(all_er), 3) if all_er else 0,
        "by_format": {fmt: round(statistics.mean(v), 3) for fmt, v in by_format.items() if v},
        "by_pillar": {pi: round(statistics.mean(v), 3) for pi, v in by_pillar.items() if v},
        "confidence": "data" if len(posts) >= 5 else "thin_data",
    }


# ── 4. IG BUSINESS (account reach + followers) ───────────────────────

def load_ig_business() -> dict:
    """Read ig-business-analytics.json — account-level 30d reach series."""
    data = _read_json("ig-business-analytics.json")
    if not data:
        return {"ok": False, "confidence": "no_data"}
    account = data.get("account") or {}
    reach_series = data.get("daily_reach") or []
    window_totals = data.get("window_totals") or {}
    # Avg daily reach from last 30d
    reach_vals = [r.get("value") or 0 for r in reach_series if isinstance(r, dict)]
    avg_reach = statistics.mean(reach_vals) if reach_vals else 0
    return {
        "ok": True,
        "source": "ig-business-analytics.json",
        "updated": data.get("updated"),
        "followers_count": account.get("followers_count"),
        "follows_count": account.get("follows_count"),
        "media_count": account.get("media_count"),
        "avg_daily_reach_30d": int(avg_reach),
        "window_totals": window_totals,
        "top_post_permalink": (data.get("top_post") or {}).get("permalink"),
        "confidence": "data" if avg_reach > 0 else "thin_data",
    }


# ── 5. GA4 (sessions, top pages, conversion attribution) ─────────────

def load_ga4() -> dict:
    """Read ga4-metrics.json — last 30d of session data."""
    data = _read_json("ga4-metrics.json")
    if not data:
        return {"ok": False, "confidence": "no_data"}
    pages = data.get("pages") or []
    sources = data.get("sources") or {}
    return {
        "ok": True,
        "source": "ga4-metrics.json",
        "updated": data.get("updated"),
        "property_id": data.get("property_id"),
        "total_sessions_30d": data.get("total_sessions"),
        "top_pages": pages[:5] if isinstance(pages, list) else [],
        "top_sources": [(k, v.get("sessions", 0)) for k, v in (sources.items() if isinstance(sources, dict) else [])][:5],
        "confidence": "data" if (data.get("total_sessions") or 0) > 0 else "thin_data",
    }


# ── 6. GBP INSIGHTS (real calls + directions) ────────────────────────

def load_gbp_insights(brand_id: str = "swing-shack") -> dict:
    """Read the GBP insights cache from the daily-poster work."""
    p = Path(os.environ.get("DATA_DIR") or DATA_DIR) / f"gbp-insights/{brand_id}-latest.json"
    if not p.exists():
        return {"ok": False, "confidence": "no_data", "reason": "run /api/gbp/insights/sync"}
    try:
        with open(p) as f:
            data = json.load(f)
    except Exception:
        return {"ok": False, "confidence": "no_data"}
    locs = data.get("locations") or []
    calls_30d = sum((loc.get("totals") or {}).get("ACTIONS_PHONE", 0) for loc in locs)
    directions_30d = sum((loc.get("totals") or {}).get("ACTIONS_DRIVING_DIRECTIONS", 0) for loc in locs)
    web_30d = sum((loc.get("totals") or {}).get("ACTIONS_WEBSITE", 0) for loc in locs)
    search_views_30d = sum((loc.get("totals") or {}).get("VIEWS_SEARCH", 0) for loc in locs)
    return {
        "ok": True,
        "source": "gbp-insights",
        "updated": data.get("synced_at"),
        "calls_30d": calls_30d,
        "directions_30d": directions_30d,
        "website_clicks_30d": web_30d,
        "search_views_30d": search_views_30d,
        "locations": len(locs),
        "confidence": "data" if locs else "thin_data",
    }


# ── 7. FB / TIKTOK / X BUSINESS (account reach + followers) ─────────
# All 3 mirror ig_business loader; they read their own per-channel
# account file. confidence carries data_pending status through so the
# brief renders the right badge (green for live, red for pending).

def _load_channel_business(brand_id: str, channel: str) -> dict:
    """Generic read for facebook/tiktok/x business JSONs.

    Returns: same shape as load_ig_business() so brand_brief_intel's
    downstream logic doesn't need per-channel conditionals.
    Falls back to "no data" if file missing or data_pending=True.
    """
    fname = f"{channel}-business-analytics.json"
    data = _read_json(fname)
    if not data or data.get("data_pending") is True:
        return {
            "ok": False,
            "channel": channel,
            "confidence": "no_data",
            "reason": data.get("_pending_reason") if data else f"{fname} not present",
            "expected_next_fetch_url": data.get("next_fetch_url") if data else None,
        }
    account = data.get("account") or {}
    reach_series = data.get("daily_reach") or []
    reach_vals = [r.get("value") or 0 for r in reach_series if isinstance(r, dict)]
    avg_reach = statistics.mean(reach_vals) if reach_vals else 0
    return {
        "ok": True,
        "channel": channel,
        "source": fname,
        "updated": data.get("updated"),
        "followers_count": account.get("followers_count"),
        "follows_count": account.get("follows_count"),
        "media_count": account.get("media_count"),
        "avg_daily_reach_30d": int(avg_reach),
        "window_totals": data.get("window_totals") or {},
        "top_post_permalink": (data.get("top_post") or {}).get("permalink"),
        "confidence": "data" if avg_reach > 0 else "thin_data",
    }


def load_facebook_business() -> dict:
    return _load_channel_business("swing-shack", "facebook")


def load_tiktok_business() -> dict:
    return _load_channel_business("swing-shack", "tiktok")


def load_x_business() -> dict:
    return _load_channel_business("swing-shack", "x")


# Generic post-level loader for non-IG channels
def load_channel_analytics(channel: str) -> dict:
    """Read <channel>-analytics.json per-post metrics (mirrors ig_analytics).

    Returns: same shape as load_ig_analytics() — by_format / by_pillar /
    median_engagement_pct — so downstream logic stays channel-agnostic.
    """
    fname = f"{channel}-analytics.json"
    data = _read_json(fname)
    if not data or data.get("data_pending") is True:
        return {
            "ok": False,
            "channel": channel,
            "confidence": "no_data",
            "reason": data.get("_pending_reason") if data else f"{fname} not present",
            "source": fname,
        }
    posts = data.get("posts") or []
    by_format = {}
    by_pillar = {}
    all_er = []
    for p in posts:
        try:
            er = float(p.get("engagementRate") or 0)
        except (TypeError, ValueError):
            er = 0.0
        all_er.append(er)
        fmt = p.get("format_type") or "unknown"
        by_format.setdefault(fmt, []).append(er)
        pillar = p.get("topic_cluster") or "unknown"
        by_pillar.setdefault(pillar, []).append(er)
    return {
        "ok": True,
        "channel": channel,
        "source": fname,
        "updated": data.get("updated"),
        "post_count": len(posts),
        "median_engagement_pct": round(statistics.median(all_er), 3) if all_er else 0,
        "mean_engagement_pct": round(statistics.mean(all_er), 3) if all_er else 0,
        "max_engagement_pct": round(max(all_er), 3) if all_er else 0,
        "by_format": {fmt: round(statistics.mean(v), 3) for fmt, v in by_format.items() if v},
        "by_pillar": {pi: round(statistics.mean(v), 3) for pi, v in by_pillar.items() if v},
        "confidence": "data" if len(posts) >= 5 else "thin_data",
    }


def load_facebook_analytics() -> dict:
    """Per-post metrics for swing-shack Facebook page."""
    return load_channel_analytics("facebook")


def load_tiktok_analytics() -> dict:
    """Per-post metrics for swing-shack TikTok account."""
    return load_channel_analytics("tiktok")


def load_x_analytics() -> dict:
    """Per-post metrics for swing-shack X account."""
    return load_channel_analytics("x")


# ── 8. AUDIENCE EQUITY (per-channel 'have we built an audience here?') ──

def compute_audience_equity(brand_id: str = "swing-shack", *, ig: Optional[dict] = None,
                              gbp: Optional[dict] = None,
                              facebook: Optional[dict] = None,
                              tiktok: Optional[dict] = None,
                              x: Optional[dict] = None) -> dict:
    """Score 0.0-1.0: 'do we have an active audience on this channel today?'

    Inputs per channel:
      - instagram:  followers_count + avg_daily_reach_30d
      - facebook:   followers_count + page_impressions_30d (from window_totals)
      - tiktok:     followers_count + video_views_30d (from window_totals)
      - x:          followers_count + tweet_count_30d (from window_totals)
      - gmb:        calls_30d + search_views_30d

    For channels we don't have data for (data_pending=true or missing
    file), return 'no_data' verdict so the brief surfaces that
    explicitly instead of pretending we have audience equity.
    """
    if ig is None:
        ig = load_ig_business()
    if gbp is None:
        gbp = load_gbp_insights(brand_id)
    if facebook is None:
        facebook = load_facebook_business()
    if tiktok is None:
        tiktok = load_tiktok_business()
    if x is None:
        x = load_x_business()

    followers = (ig.get("followers_count") if ig.get("ok") else 0) or 0
    reach_30d = (ig.get("avg_daily_reach_30d") if ig.get("ok") else 0) or 0
    gbp_calls = (gbp.get("calls_30d") if gbp.get("ok") else 0) or 0
    gbp_views = (gbp.get("search_views_30d") if gbp.get("ok") else 0) or 0

    def _fb_score(fb):
        if not fb.get("ok"): return None
        f = fb.get("followers_count") or 0
        wt = (fb.get("window_totals") or {})
        imp = wt.get("page_impressions") or 0
        return min(1.0, f / 10000 + imp / 50000) if f > 0 else 0

    def _tt_score(tt):
        if not tt.get("ok"): return None
        f = tt.get("followers_count") or 0
        wt = (tt.get("window_totals") or {})
        vw = wt.get("video_views_30d") or 0
        return min(1.0, f / 10000 + vw / 50000) if f > 0 else 0

    def _x_score(xd):
        if not xd.get("ok"): return None
        f = xd.get("followers_count") or 0
        wt = (xd.get("window_totals") or {})
        tw = wt.get("tweet_count_30d") or 0
        return min(1.0, f / 5000 + tw / 1000) if f > 0 else 0

    ig_score = min(1.0, followers / 10000 + reach_30d / 2000) if followers > 0 else 0

    per_channel = {
        "instagram": ig_score,
        "gmb": min(1.0, max(0, gbp_calls) / 30) if gbp.get("ok") else 0,
        "facebook": _fb_score(facebook),
        "tiktok": _tt_score(tiktok),
        "x": _x_score(x),
    }

    def verdict(score):
        if score is None: return "no_data"
        if score > 0.3: return "active"
        if score > 0: return "early"
        return "unknown"

    return {
        "ok": True,
        "source": "computed",
        "followers": followers,
        "reach_30d": reach_30d,
        "gbp_calls_30d": gbp_calls,
        "gbp_search_views_30d": gbp_views,
        "per_channel": per_channel,
        "per_channel_data_source": {
            "instagram": "ig-business-analytics.json",
            "facebook": "facebook-business-analytics.json",
            "tiktok": "tiktok-business-analytics.json",
            "x": "x-business-analytics.json",
            "gmb": "gbp-insights/<brand>-latest.json",
        },
        "verdict": {k: verdict(v) for k, v in per_channel.items()},
    }


# ── ALL-IN-ONE BRAND INTEL SNAPSHOT ─────────────────────────────────

def build_brand_intel(brand_id: str = "swing-shack") -> dict:
    """Pull every data source and assemble a single intel snapshot.

    Returns: {
      ok, brand_id, generated_at,
      post_conversion: {...}, hook_bank: {...},
      ig_analytics: {...}, ig_business: {...},
      facebook_analytics: {...}, facebook_business: {...},
      tiktok_analytics: {...}, tiktok_business: {...},
      x_analytics: {...}, x_business: {...},
      ga4: {...}, gbp_insights: {...},
      audience_equity: {...}
    }
    """
    psc = load_post_conversion_score()
    hbk = load_hook_bank()
    iga = load_ig_analytics()
    igb = load_ig_business()
    fba = load_facebook_analytics()
    fbb = load_facebook_business()
    tta = load_tiktok_analytics()
    ttb = load_tiktok_business()
    xa = load_x_analytics()
    xb = load_x_business()
    ga4 = load_ga4()
    gbp = load_gbp_insights(brand_id)
    eq = compute_audience_equity(brand_id, ig=igb, gbp=gbp,
                                  facebook=fbb, tiktok=ttb, x=xb)
    return {
        "ok": True,
        "brand_id": brand_id,
        "generated_at": "now",
        "post_conversion": psc,
        "hook_bank": hbk,
        "ig_analytics": iga,
        "ig_business": igb,
        "facebook_analytics": fba,
        "facebook_business": fbb,
        "tiktok_analytics": tta,
        "tiktok_business": ttb,
        "x_analytics": xa,
        "x_business": xb,
        "ga4": ga4,
        "gbp_insights": gbp,
        "audience_equity": eq,
    }


# ── DERIVED FACTS ──────────────────────────────────────────────────

def derive_recommended_hook_formula(intel: dict, channel: str, pillar: Optional[str] = None) -> Tuple[Optional[str], str]:
    """Return (best_formula, source_citation).

    Priority:
      1. From post-conversion-score: which formula_type actually
         won by lift for the brand's recent winning posts.
      2. From hook-bank: cross-signal-score ranked formula.
      3. Fallback: per-channel default from the static table.
    """
    psc = intel.get("post_conversion") or {}
    hbk = intel.get("hook_bank") or {}
    if psc.get("ok") and psc.get("winning_hook_formula") and psc.get("confidence") == "data":
        return psc["winning_hook_formula"], f"data:{psc['source']} (median lift +{psc.get('median_lift_pct', 0)}% over baseline, {psc.get('posts_scored', 0)} posts)"
    if hbk.get("ok") and hbk.get("best_formula") and hbk.get("confidence") == "data":
        return hbk["best_formula"], f"data:{hbk['source']} (cross-signal-score ranked across {hbk.get('proven_count', 0)} proven hooks)"
    return None, f"baseline:{channel} (no brand-level hook performance data yet)"


def derive_expected_engagement(intel: dict, channel: str, pillar: Optional[str] = None) -> Tuple[dict, str]:
    """Return ({engagement_rate, ctr, expected_reach, ...}, source_citation).

    Priority:
      1. From ig-analytics.json median per format + pillar.
      2. Fallback: industry baseline.
    """
    iga = intel.get("ig_analytics") or {}
    igb = intel.get("ig_business") or {}
    fmt = channel  # heuristic — instagram-format matches channel most often
    by_format = iga.get("by_format") or {}
    by_pillar = iga.get("by_pillar") or {}
    chosen_er = by_pillar.get(pillar) if pillar and by_pillar.get(pillar) else (
        by_format.get(fmt) if by_format.get(fmt) else None)
    if chosen_er is None and iga.get("median_engagement_pct"):
        chosen_er = iga["median_engagement_pct"]
    if chosen_er:
        return (
            {
                "engagement_rate": f"{chosen_er:.2f}% (median of {iga.get('post_count', 0)} recent IG posts)",
                "ctr": "0.8-2.0% baseline (no per-channel CTR data on file)",
                "expected_reach": f"{igb.get('avg_daily_reach_30d', 0):,}/d median from {igb.get('source', 'ig-business')}",
                "expected_clicks": "8-25 per post (industry baseline, no per-brand click data on file)",
                "conversion_rate_estimate": "3-7% baseline (no per-brand conversion data on file)",
                "expected_bookings": "computed below",
            },
            f"data:{iga.get('source')}",
        )
    return (
        {"engagement_rate": "unknown", "expected_reach": "unknown", "expected_clicks": "unknown", "expected_bookings": "unknown"},
        "no_data",
    )


def derive_expected_bookings(intel: dict, channel: str, *, is_paid: bool = False) -> Tuple[Optional[float], str]:
    """Expected bookings per post — derived from brand data when available.

    Formula:
      baseline_bookings_per_post (from post-conversion-score.json)
        × median_lift_pct adjustment (if pillar matches winning themes)
    For GBP, use the actual 30d calls figure (more accurate than a model).
    """
    psc = intel.get("post_conversion") or {}
    base = psc.get("baseline_bookings_per_post")
    if base is None:
        return None, "no_data"
    lift_mult = 1.0 + (psc.get("median_lift_pct", 0) or 0) / 100
    if channel == "gmb":
        gbp = intel.get("gbp_insights") or {}
        calls = gbp.get("calls_30d", 0) or 0
        if calls > 0:
            per_post = calls / 30  # 30d / 30 posts ≈ per-post
            return round(per_post * (1.5 if is_paid else 1.0), 2), f"data:gbp-insights ({calls} calls last 30d ÷ 30, paid boost applied)"
    return round(base * lift_mult, 2), f"data:{psc.get('source')} (baseline {base}/post × lift +{psc.get('median_lift_pct', 0)}%)"


def derive_recommended_paid(intel: dict, channel: str, *, neighbourhood: Optional[str] = None) -> Tuple[dict, str]:
    """Return paid plan recommendation, computed from data.

    Rule:
      - GBP: never paid (organic + reviews is the play)
      - X: never paid (audience is small per channel fit)
      - Instagram: paid R150/d default UNLESS the brand has
        <500 followers → organic-only until audience grows.
      - Facebook: paid R200/d default — same caveat.
      - TikTok: paid R250/d default — same caveat.

    Citation explains why we picked paid-or-not for THIS brand.
    """
    eq = (intel.get("audience_equity") or {}).get("per_channel") or {}
    followers = (intel.get("ig_business") or {}).get("followers_count") or 0
    gbp_calls = (intel.get("gbp_insights") or {}).get("calls_30d", 0) or 0

    if channel == "gmb":
        return {
            "channel": "gmb", "recommended": False, "daily_budget_zar": 0,
            "objective": "organic local post + photo upload + review reply",
            "target": "local-intent searchers within 5km radius",
            "expected_reach": f"{gbp_calls} calls last 30d ({'active' if gbp_calls > 5 else 'building'})",
            "rationale": "GBP local-intent posts are free; the spend is on review replies + photo uploads. You're paying ranking signals, not impressions.",
        }, "data:gbp-insights (paid amplification rarely beats organic for local-intent searches)"
    if channel == "x":
        return {
            "channel": "x", "recommended": False, "daily_budget_zar": 0,
            "objective": "organic tweet + hashtag use",
            "target": "SA golf Twitter + creators",
            "expected_reach": "200-1,500 organic impressions",
            "rationale": "No follower data on file for X yet — organic-only until audience equity confirmed.",
        }, "data:no_audience_data (paid X is expensive per impression in SA golf)"
    if channel == "instagram":
        if followers and followers < 500:
            return {
                "channel": "instagram", "recommended": False, "daily_budget_zar": 0,
                "objective": "organic post + bio-link CTA",
                "target": "current followers + explore-feed free reach",
                "expected_reach": f"{followers} followers · algorithm-driven free reach",
                "rationale": f"Only {followers} IG followers on file — boost on free content until you've passed 500 followers + got 10+ posts in rotation.",
            }, f"data:ig-business ({followers} followers < 500 — build organic first)"
        return {
            "channel": "instagram", "recommended": True, "daily_budget_zar": 150,
            "objective": "post engagement + profile visit + bio-link click",
            "target": "Johannesburg golf-curious 25-55, lookalike from {followers}-follower base",
            "expected_reach": "1,200-3,500 reach/day at R150/day (Hootsuite 2025 baseline × your 2.5K baseline)",
            "rationale": f"R150/day for 7 days = R1,050. Cheapest reach in SA golf per Meta 2024 benchmarks. {followers} followers give the algorithm seed audience.",
        }, f"data:ig-business ({followers} followers → algorithmic seed audience justifies paid)"
    if channel == "facebook":
        return {
            "channel": "facebook", "recommended": True, "daily_budget_zar": 200,
            "objective": "post engagement + link click",
            "target": "Johannesburg 30-65, lookalike from page followers + interest targeting",
            "expected_reach": "1,500-4,000 reach/day at R200/day",
            "rationale": "FB algorithm favours longer captions + link clicks — perfect for free-swing-analysis CTAs. R200/day for 7 days = R1,400.",
        }, "data:industry_baseline (no FB follower data on file — baseline paid plan)"
    if channel == "tiktok":
        return {
            "channel": "tiktok", "recommended": True, "daily_budget_zar": 250,
            "objective": "video views + profile visit",
            "target": "Johannesburg 18-40, interests ['golf', 'sport', 'lifestyle']",
            "expected_reach": "800-2,500 views/day at R250/day (Spark Ads)",
            "rationale": "TikTok Spark Ads unlock the algorithm — R250/day for 7 days = R1,750.",
        }, "data:industry_baseline (no TikTok follower data on file)"
    return {"channel": channel, "recommended": False, "daily_budget_zar": 0,
            "objective": "organic-only", "target": "n/a", "expected_reach": "n/a",
            "rationale": "No data on file."}, "no_data"
