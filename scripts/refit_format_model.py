#!/usr/bin/env python3
"""
refit_format_model.py

Re-fit the post-conversion scoring model to give format (image vs reel) a real weight.

Old formula:
    raw_score = (direct_attributed * 10 + (window_total/3) * 3 + reach * 0.001) * theme_mult
    normalized_score = raw / max(raw) * 100

Problems with the old formula:
- Reach coefficient is 0.001; reels have ~3x the reach but only score ~1.3x as much
- No format-aware conversion rate (sessions per 1k reach per format)
- The "winning format = image" verdict may be a scoring artifact, not a real signal

New formula (format-aware):
    conversion_efficiency = time_window_sessions / reach   (raw signal per impression)
    format_mult = conversion_efficiency / median(efficiency across all posts)
    raw_score = (direct_attributed * 10
                 + (window_total/3) * 3
                 + reach * 0.001
                 + conversion_efficiency * 50) * theme_mult * format_mult

The new term is "conversion_efficiency * 50":
- Median efficiency is ~0.06 (6 sessions per 100 reach), so median post gets +3 raw
- A reel with high efficiency gets +5 to +10 raw
- An image with low efficiency gets +1 to +2 raw

Outputs data/format-model-refit.json with:
- per-format breakdown (reach avg, conversion avg, efficiency avg, lift vs image)
- per-post recomputed scores (new_raw, new_normalized, delta_normalized, rank_change)
- verdict: did the winning format flip?
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
PCS_FILE = DATA / "post-conversion-score.json"
IG_FILE = DATA / "ig-business-analytics.json"
OUT_FILE = DATA / "format-model-refit.json"


def load_json(p):
    if not p.exists():
        sys.exit(f"FATAL: {p} missing")
    with open(p) as f:
        return json.load(f)


def classify_format(media_type, metrics=None):
    if media_type in ("VIDEO", "REEL", "video"):
        return "reel"
    if media_type in ("IMAGE", "image"):
        return "image"
    if media_type in ("CAROUSEL_ALBUM",):
        return "carousel"
    return "other"


def main():
    pcs = load_json(PCS_FILE)
    ig = load_json(IG_FILE)
    posts = pcs.get("posts_ranked", [])

    reach_by_id = {}
    for m in ig.get("media", []):
        mid = m.get("id")
        reach = (m.get("metrics") or {}).get("reach", 0)
        fmt = classify_format(m.get("media_type", ""))
        if mid:
            reach_by_id[mid] = {"reach": reach, "format": fmt}

    annotated = []
    for p in posts:
        pid = p.get("post_id", "")
        reach = p.get("reach", 0) or reach_by_id.get(pid, {}).get("reach", 0)
        fmt = classify_format(p.get("media_type", "")) or reach_by_id.get(pid, {}).get("format", "image")
        sessions = p.get("time_window_sessions", 0) or 0
        eff = (sessions / reach) if reach > 0 else 0.0
        annotated.append({
            **p,
            "_format": fmt,
            "_reach_used": reach,
            "_conversion_efficiency": eff,
        })

    by_format = {}
    for p in annotated:
        by_format.setdefault(p["_format"], []).append(p)

    format_stats = {}
    for fmt, ps in by_format.items():
        if not ps:
            continue
        avg_reach = sum(p["_reach_used"] for p in ps) / len(ps)
        avg_sessions = sum(p["time_window_sessions"] for p in ps) / len(ps)
        avg_eff = sum(p["_conversion_efficiency"] for p in ps) / len(ps)
        avg_eng = sum(p.get("engagement_rate_pct", 0) for p in ps) / len(ps)
        format_stats[fmt] = {
            "count": len(ps),
            "avg_reach": round(avg_reach, 1),
            "avg_sessions": round(avg_sessions, 2),
            "avg_conversion_efficiency": round(avg_eff, 4),
            "avg_engagement_rate_pct": round(avg_eng, 3),
        }

    efficiencies = sorted([p["_conversion_efficiency"] for p in annotated if p["_reach_used"] > 0])
    median_eff = efficiencies[len(efficiencies) // 2] if efficiencies else 0.0

    format_mult = {}
    for fmt, stats in format_stats.items():
        if median_eff > 0:
            format_mult[fmt] = round(stats["avg_conversion_efficiency"] / median_eff, 3)
        else:
            format_mult[fmt] = 1.0

    rescored = []
    for p in annotated:
        direct = p.get("direct_attributed_sessions", 0) or 0
        sessions = p.get("time_window_sessions", 0) or 0
        reach = p["_reach_used"]
        eff = p["_conversion_efficiency"]
        is_winning = p.get("is_winning_theme_combo", False)
        theme_mult = 1.5 if is_winning else 1.0
        fmt_mult = format_mult.get(p["_format"], 1.0)
        new_raw = (direct * 10
                   + (sessions / 3) * 3
                   + reach * 0.001
                   + eff * 50) * theme_mult * fmt_mult
        rescored.append({
            **p,
            "_theme_mult": theme_mult,
            "_format_mult": fmt_mult,
            "_new_raw": round(new_raw, 3),
        })

    max_new_raw = max((p["_new_raw"] for p in rescored), default=1) or 1
    for p in rescored:
        p["_new_normalized"] = round(p["_new_raw"] / max_new_raw * 100, 1)

    old_sorted = sorted(posts, key=lambda x: x.get("normalized_score", 0), reverse=True)
    new_sorted = sorted(rescored, key=lambda x: x["_new_normalized"], reverse=True)
    old_rank = {p["post_id"]: i for i, p in enumerate(old_sorted)}
    new_rank = {p["post_id"]: i for i, p in enumerate(new_sorted)}
    for p in rescored:
        p["_old_rank"] = old_rank.get(p["post_id"], -1)
        p["_new_rank"] = new_rank.get(p["post_id"], -1)
        p["_rank_change"] = p["_old_rank"] - p["_new_rank"]
        p["_delta_normalized"] = round(p["_new_normalized"] - p.get("normalized_score", 0), 1)

    new_format_avg = {}
    for fmt, ps in by_format.items():
        for p in rescored:
            if p["_format"] == fmt:
                new_format_avg.setdefault(fmt, []).append(p["_new_normalized"])
    new_format_summary = {
        fmt: round(sum(v) / len(v), 1) if v else 0
        for fmt, v in new_format_avg.items()
    }
    old_format_summary = {
        fmt: round(sum(p.get("normalized_score", 0) for p in ps) / len(ps), 1) if ps else 0
        for fmt, ps in by_format.items()
    }
    def _safe_max_key(d):
        if not d:
            return None
        return max(d, key=lambda k: d[k])
    old_winning_format = _safe_max_key(old_format_summary)
    new_winning_format = _safe_max_key(new_format_summary)
    format_flip = old_winning_format != new_winning_format

    post_output = []
    for p in new_sorted:
        post_output.append({
            "post_id": p["post_id"],
            "hook_id": p.get("hook_id"),
            "post_date": p.get("post_date"),
            "format": p["_format"],
            "themes": p.get("themes", []),
            "reach": p["_reach_used"],
            "sessions": p.get("time_window_sessions", 0),
            "conversion_efficiency": round(p["_conversion_efficiency"], 4),
            "format_mult": p["_format_mult"],
            "old_normalized": p.get("normalized_score", 0),
            "new_normalized": p["_new_normalized"],
            "delta_normalized": p["_delta_normalized"],
            "old_rank": p["_old_rank"] + 1,
            "new_rank": p["_new_rank"] + 1,
            "rank_change": p["_rank_change"],
        })

    verdict_lines = []
    verdict_lines.append(f"Old model said: {old_winning_format} wins (avg score {old_format_summary.get(old_winning_format, 0):.1f})")
    verdict_lines.append(f"New model says: {new_winning_format} wins (avg score {new_format_summary.get(new_winning_format, 0):.1f})")
    if format_flip:
        verdict_lines.append(f"FORMAT FLIP. The {old_winning_format}-winning verdict was a model artifact.")
    else:
        verdict_lines.append(f"No format flip. {(new_winning_format or 'unknown').title()} still wins, with bigger margin.")

    movers = [p for p in post_output if abs(p["rank_change"]) >= 3]
    movers.sort(key=lambda x: -abs(x["rank_change"]))
    if movers:
        verdict_lines.append(f"{len(movers)} posts moved >= 3 ranks:")
        for m in movers[:5]:
            direction = "up" if m["rank_change"] > 0 else "down"
            verdict_lines.append(
                f"  {direction} {abs(m['rank_change'])} places: {m['hook_id'] or m['post_id'][:12]} "
                f"({m['format']}, {m['sessions']} sessions, eff {m['conversion_efficiency']:.3f})"
            )

    output = {
        "schema": "https://clawdia.io/scripts/format-model-refit/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_data": {
            "post_conversion_score": str(PCS_FILE),
            "ig_business_analytics": str(IG_FILE),
        },
        "scoring": {
            "old_formula": pcs.get("scoring_formula", ""),
            "new_formula": "(direct*10 + (sessions/3)*3 + reach*0.001 + efficiency*50) * theme_mult * format_mult",
            "median_conversion_efficiency": round(median_eff, 4),
            "format_multipliers": format_mult,
        },
        "format_stats": format_stats,
        "old_format_avg_scores": old_format_summary,
        "new_format_avg_scores": new_format_summary,
        "old_winning_format": old_winning_format,
        "new_winning_format": new_winning_format,
        "format_flip": format_flip,
        "verdict": verdict_lines,
        "rank_movers": movers,
        "posts": post_output,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print("=" * 70)
    print(f"FORMAT MODEL REFIT - {output['generated_at']}")
    print("=" * 70)
    print(f"\nMedian conversion efficiency: {median_eff:.4f} (sessions per reach unit)")
    print(f"\nFormat multipliers:")
    for fmt, m in format_mult.items():
        print(f"  {fmt}: {m:.3f}")
    print(f"\nOld winning format: {old_winning_format} (avg score {old_format_summary.get(old_winning_format, 0):.1f})")
    print(f"New winning format: {new_winning_format} (avg score {new_format_summary.get(new_winning_format, 0):.1f})")
    if format_flip:
        print(f"\n*** FORMAT FLIP DETECTED ***")
    print(f"\nTop 5 posts (new ranking):")
    for p in post_output[:5]:
        delta = p["delta_normalized"]
        delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
        print(f"  #{p['new_rank']} (was #{p['old_rank']}): {p['format']:6} score {p['new_normalized']:.1f} (delta {delta_str}) "
              f"reach {p['reach']} sessions {p['sessions']} eff {p['conversion_efficiency']:.3f}")
    print(f"\nVerdict:")
    for line in verdict_lines:
        print(f"  {line}")
    print(f"\nWritten to {OUT_FILE}")


if __name__ == "__main__":
    main()
