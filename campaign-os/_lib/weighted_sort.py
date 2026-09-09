"""weighted_sort.py — Channel ranking algorithm for Campaign OS.

Built 2026-08-21 to answer: "where should we publish next?"

Ranks every publishing channel by a 0-100 score across 4 axes:

  data_coverage     (0-25)  Are we getting real engagement numbers?
                             Real > baseline > missing. Heavy bonus for channels
                             with live IG/FB engagement data flowing.

  engagement_vel    (0-25)  Is the audience actually doing something?
                             IG engagement_rate, FB page_post_engagements,
                             GBP search-impression velocity.

  conversion_pot    (0-25)  Can we measure + optimize conversions here?
                             CAPI-enabled Meta, GBP click-actions, TIKTOK event
                             tracking, X Basic vs ad trails.

  cost_efficiency   (0-25)  Free beats paid at equivalent quality.
                             Meta free, GBP free, TIKTOK free, X Basic $100/mo.
                             Cost penalty scales monthly, normalized to be out
                             of 100.

Total = sum of 4 axes, 0-100.

The algorithm is intentionally simple: weighted sum, deterministic,
auditable. Channel operators can inspect why a channel scored 67 by
inspecting each axis's source.
"""

from __future__ import annotations

from typing import Any


# Axis weights — total sums to 25 (so summed score = 100 max).
AXIS_MAX = 25


def _data_coverage(intel: dict[str, Any]) -> tuple[float, list[str]]:
    """0-25 based on whether the channel has live data."""
    reasons = []
    out = 0.0
    # IG: full engagement data is the gold standard for "has real numbers"
    ig = intel.get("ig_analytics", {})
    if ig.get("ok"):
        posts = ig.get("post_count", 0) or 0
        if posts >= 30:
            out += 25
            reasons.append(f"IG has {posts} posts with engagement data ✓")
        elif posts >= 10:
            out += 18
            reasons.append(f"IG has {posts} posts (10-29 range, partial coverage)")
        else:
            out += 10
            reasons.append(f"IG has only {posts} posts — limited history")
    else:
        reasons.append("IG: no live engagement data")

    # FB: page-level engagement metrics
    fb = intel.get("facebook_analytics", {})
    if fb.get("ok") and fb.get("post_count", 0) > 0:
        # Even partial data is meaningful for FB
        out += 6 if not intel.get("facebook_business", {}).get("ok") else 12
        reasons.append(f"FB: {fb.get('post_count')} posts present")
    return min(out, 25), reasons


def _engagement_velocity(intel: dict[str, Any]) -> tuple[float, list[str]]:
    """0-25 based on whether the audience is engaging now."""
    reasons = []
    out = 0.0
    ig = intel.get("ig_analytics", {})
    if ig.get("ok"):
        med = ig.get("median_engagement_pct", 0) or 0
        # Calibrated: 2%+ on IG is strong; <0.5% is weak
        if med >= 3.0:
            out += 25
            reasons.append(f"IG median engagement {med}% — excellent")
        elif med >= 2.0:
            out += 20
            reasons.append(f"IG median engagement {med}% — good")
        elif med >= 1.0:
            out += 13
            reasons.append(f"IG median engagement {med}% — mid")
        else:
            out += 5
            reasons.append(f"IG median engagement {med}% — low")
    fb = intel.get("facebook_business", {})
    if fb.get("ok"):
        fan_count = fb.get("followers_count", 0) or 0
        if fan_count >= 1000:
            out += 5
            reasons.append(f"FB fan count {fan_count} — viable audience")
        elif fan_count >= 100:
            out += 2
            reasons.append(f"FB fan count {fan_count} — small audience")
    return min(out, 25), reasons


def _conversion_potential(intel: dict[str, Any], token_kind: str = "capi_system_user") -> tuple[float, list[str]]:
    """0-25 based on whether we can measure + optimize conversions."""
    reasons = []
    out = 0.0
    has_capi = token_kind == "capi_system_user"
    if has_capi:
        out += 18
        reasons.append("CAPI System User token live — full conversion API access")
    else:
        out += 8
        reasons.append("Legacy META token — limited conversion scope")
    # GBP: Google Business Profile click-tracking is solid
    gbp = intel.get("gbp_analytics", {})
    if gbp.get("ok"):
        out += 7
        reasons.append("GBP click-actions measurable in Google Business Profile")
    return min(out, 25), reasons


def _cost_efficiency(platform: str) -> tuple[float, list[str]]:
    """0-25 based on monthly cost vs capability."""
    # All channels we use are essentially free. X Basic is the $100/mo outlier.
    if platform == "x":
        return 8.0, [f"X Basic tier $100/mo — cost penalty (out of 25)"]
    elif platform == "facebook":
        return 22.0, [f"FB Page + Ads API free for organic + posting — strong cost efficiency"]
    elif platform == "instagram":
        return 22.0, [f"IG via Meta API free — strong cost efficiency"]
    elif platform == "gbp":
        return 23.0, [f"GBP API free — best cost efficiency"]
    elif platform == "tiktok":
        return 18.0, [f"TT free for organic; paid requires Business Display API"]
    elif platform == "youtube":
        return 18.0, [f"YT via Postiz free for publishing"]
    return 12.0, [f"{platform}: unknown cost profile"]


def compute_channel_weights(intel: dict[str, Any]) -> list[dict[str, Any]]:
    """Rank all channels for the given brand intel.

    Returns a list of { channel, total_score, axes[] } sorted by total
    descending. Each channel's score is the sum of 4 axes, each
    0-25, total 0-100.
    """
    token_kind = (intel.get("meta_token_kind") or "long_lived_user").lower()
    # Channels to score. Order matches the brief's display order.
    channels = [
        ("instagram", "Instagram (organic + paid via Meta)"),
        ("facebook", "Facebook (organic + paid via Meta)"),
        ("gbp", "Google Business Profile"),
        ("tiktok", "TikTok (organic, free; paid via Business Display API)"),
        ("x", "X / Twitter (Basic tier $100/mo)"),
        ("youtube", "YouTube (via Postiz)"),
        ("linkedin", "LinkedIn (via Postiz, paid for sponsored)"),
    ]

    ranked = []
    for key, label in channels:
        if key == "gbp":
            dc, dc_rsns = _data_coverage_gbp(intel)
            ev, ev_rsns = _engagement_velocity_gbp(intel)
            cp = 7  # always
            ce, ce_rsn = _cost_efficiency("gbp")
            total = dc + ev + cp + ce
            ranked.append({
                "channel": key,
                "label": label,
                "total_score": round(total, 1),
                "axes": [
                    {"name": "data_coverage", "score": round(dc, 1), "max": AXIS_MAX, "reasons": dc_rsns},
                    {"name": "engagement_velocity", "score": round(ev, 1), "max": AXIS_MAX, "reasons": ev_rsns},
                    {"name": "conversion_potential", "score": cp, "max": AXIS_MAX, "reasons": ["GBP click-actions measurable"]},
                    {"name": "cost_efficiency", "score": ce, "max": AXIS_MAX, "reasons": [ce_rsn]},
                ],
            })
        elif key == "instagram":
            dc, dc_rsns = _data_coverage(intel)
            ev, ev_rsns = _engagement_velocity(intel)
            cp, cp_rsns = _conversion_potential(intel, token_kind)
            ce, ce_rsn = _cost_efficiency("instagram")
            total = dc + ev + cp + ce
            ranked.append({
                "channel": key,
                "label": label,
                "total_score": round(total, 1),
                "axes": [
                    {"name": "data_coverage", "score": round(dc, 1), "max": AXIS_MAX, "reasons": dc_rsns},
                    {"name": "engagement_velocity", "score": round(ev, 1), "max": AXIS_MAX, "reasons": ev_rsns},
                    {"name": "conversion_potential", "score": cp, "max": AXIS_MAX, "reasons": cp_rsns},
                    {"name": "cost_efficiency", "score": ce, "max": AXIS_MAX, "reasons": [ce_rsn]},
                ],
            })
        elif key == "facebook":
            dc, dc_rsns = _data_coverage_fb(intel)
            ev, ev_rsns = _engagement_velocity_fb(intel)
            cp, cp_rsns = _conversion_potential(intel, token_kind)
            ce, ce_rsn = _cost_efficiency("facebook")
            total = dc + ev + cp + ce
            ranked.append({
                "channel": key,
                "label": label,
                "total_score": round(total, 1),
                "axes": [
                    {"name": "data_coverage", "score": round(dc, 1), "max": AXIS_MAX, "reasons": dc_rsns},
                    {"name": "engagement_velocity", "score": round(ev, 1), "max": AXIS_MAX, "reasons": ev_rsns},
                    {"name": "conversion_potential", "score": cp, "max": AXIS_MAX, "reasons": cp_rsns},
                    {"name": "cost_efficiency", "score": ce, "max": AXIS_MAX, "reasons": [ce_rsn]},
                ],
            })
        elif key in ("x", "tiktok", "youtube", "linkedin"):
            dc = 0
            ev = 0
            cp = 0
            ce, ce_rsn = _cost_efficiency(key)
            total = dc + ev + cp + ce
            reasons_meta = {
                "x": ["X analytics token not configured — no live engagement data", "X requires Basic tier $100/mo for v2 analytics"],
                "tiktok": ["TikTok Business Display API token not configured", "TikTok organic is free but engagement data needs API"],
                "youtube": ["YouTube analytics not wired — Postiz proxies only"],
                "linkedin": ["LinkedIn analytics not wired — Postiz proxies only"],
            }.get(key, [])
            ranked.append({
                "channel": key,
                "label": label,
                "total_score": round(total, 1),
                "axes": [
                    {"name": "data_coverage", "score": 0, "max": AXIS_MAX, "reasons": reasons_meta[:1]},
                    {"name": "engagement_velocity", "score": 0, "max": AXIS_MAX, "reasons": ["No live engagement data"]},
                    {"name": "conversion_potential", "score": 0, "max": AXIS_MAX, "reasons": ["Conversion API not wired"]},
                    {"name": "cost_efficiency", "score": ce, "max": AXIS_MAX, "reasons": [ce_rsn]},
                ],
            })

    ranked.sort(key=lambda x: x["total_score"], reverse=True)
    return ranked


def _data_coverage_gbp(intel: dict) -> tuple[float, list[str]]:
    """GBP-specific data coverage."""
    gbp = intel.get("gbp_analytics", {})
    if gbp.get("ok"):
        return 18.0, ["GBP daily plans configured — click actions trackable"]
    return 8.0, ["GBP connected but no fresh data yet"]


def _engagement_velocity_gbp(intel: dict) -> tuple[float, list[str]]:
    """GBP-specific engagement velocity."""
    gbp = intel.get("gbp_analytics", {})
    if gbp.get("ok") and "daily_plans_count" in (gbp or {}):
        return 15.0, [f"GBP has {gbp['daily_plans_count']} days of rotating posts active"]
    return 8.0, ["GBP active but velocity metric pending"]


def _data_coverage_fb(intel: dict) -> tuple[float, list[str]]:
    """FB-specific data coverage."""
    fb = intel.get("facebook_analytics", {})
    fb_biz = intel.get("facebook_business", {})
    if (fb.get("ok") and fb.get("post_count", 0) > 0) or (fb_biz.get("ok") and (fb_biz.get("followers_count") or 0) > 0):
        # Partial data is better than no data
        posts = fb.get("post_count", 0) or 0
        score = 12 if posts >= 20 else (8 if posts >= 5 else 4)
        return score, [f"FB: {posts} posts + page-level engagement live (3/6 metrics)"]
    return 0.0, ["FB: no live engagement data"]


def _engagement_velocity_fb(intel: dict) -> tuple[float, list[str]]:
    """FB-specific engagement velocity."""
    fb_biz = intel.get("facebook_business", {})
    fans = fb_biz.get("followers_count", 0) or 0
    # Use the page_post_engagements metric from the cached JSON
    # (we don't have it in the simplified intel but the FB business JSON does)
    if fans >= 1000:
        return 18.0, [f"FB fan count {fans} — strong audience for paid amplification"]
    elif fans >= 200:
        return 12.0, [f"FB fan count {fans} — modest audience"]
    elif fans >= 50:
        return 6.0, [f"FB fan count {fans} — small community"]
    return 2.0, [f"FB fan count {fans} — minimal reach"]
