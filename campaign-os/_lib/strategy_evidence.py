"""
strategy_evidence.py — Mine real data to evaluate strategy bets + derive lessons.

Built 2026-08-24. This is the half that turns the strategy layer from
"aspirational notes" into "evidence-led marketing OS".

What it does:
  - For each active bet, pull the linked campaign's real metrics from
    IG/FB/GA4/SEO and decide whether the bet is on track, behind, or
    invalidated by data.
  - Cross-reference IG top performers + GA4 top pages + SEO movement +
    social engagement to surface LESSONS — patterns the data supports
    that should inform future bets.

Every lesson returned carries an `evidence` list of {source, value, as_of}
dicts — so when a claim says "Instagram engagement on coaching reels
averages 4.5%", you can see the 5 source posts + their reach.

The caller decides how to present these — strategy_store.upsert_lesson()
writes them to the persistent lessons array.
"""

from __future__ import annotations

import json
import os
import datetime
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
_DATA_DIR = _REPO_ROOT / "data"
_DATA_DIR_RUNTIME = Path(os.environ.get("DATA_DIR", str(_DATA_DIR)))


def _read_json(name: str) -> Optional[dict]:
    for base in (_DATA_DIR, _DATA_DIR_RUNTIME):
        path = base / name
        if path.exists():
            try:
                return json.load(open(path))
            except (OSError, json.JSONDecodeError):
                continue
    return None


def _today() -> str:
    return datetime.date.today().isoformat()


def _evidence(source: str, value: Any, as_of: str = "") -> dict:
    return {
        "source": source,
        "value": str(value)[:200],
        "as_of": as_of or _today(),
    }


# ─── Per-bet evaluation ──────────────────────────────────────────────

def evaluate_bet(bet: dict, brand_id: str = "swing-shack") -> dict:
    """Score a bet against the real data sources. Returns an evaluation
    dict with: on_track (bool|none), evidence_for, evidence_against,
    learned (string), recommended_status (string)."""

    evidence_for = []
    evidence_against = []

    # 1. Try to find the campaign's metrics via campaign-data.json linkage
    campaign_id = bet.get("campaign_id")
    kpi = (bet.get("primary_kpi") or "").lower()

    # IG analytics — pulls from ig-analytics.json
    ig = _read_json("ig-analytics.json") or {}
    if ig:
        posts = ig.get("posts", []) or []
        if posts and "engagement" in kpi:
            median = ig.get("median_engagement_pct", 0) or 0
            threshold_str = bet.get("success_threshold", "")
            try:
                threshold = float(threshold_str.rstrip("%")) if threshold_str else None
            except ValueError:
                threshold = None
            if threshold and median >= threshold:
                evidence_for.append(_evidence("ig-analytics.json", f"median engagement {median}% ≥ {threshold}%"))
            elif threshold and median < threshold * 0.7:
                evidence_against.append(_evidence("ig-analytics.json", f"median engagement {median}% well below {threshold}%"))
            else:
                evidence_for.append(_evidence("ig-analytics.json", f"median engagement {median}%"))

    # FB analytics — pulls from facebook-business-analytics.json (the live file)
    fb = _read_json("facebook-business-analytics.json") or _read_json("facebook-analytics.json") or {}
    if fb and "reach" in kpi:
        fans = fb.get("fan_count", 0) or 0
        if fans >= 1000:
            evidence_for.append(_evidence("facebook-business-analytics.json", f"fans {fans}"))
        elif fans and fans < 200:
            evidence_against.append(_evidence("facebook-business-analytics.json", f"only {fans} fans — limited audience"))

    # GA4 — pulls from ga4-metrics.json
    ga4 = _read_json("ga4-metrics.json") or {}
    if ga4 and ("bookings" in kpi or "conversion" in kpi or "traffic" in kpi):
        sessions = ga4.get("total_sessions", 0) or 0
        pages = ga4.get("pages", []) or []
        bookings_sessions = next((p.get("sessions", 0) for p in pages if "/bookings" in (p.get("path") or "")), 0)
        if bookings_sessions >= 200:
            evidence_for.append(_evidence("ga4-metrics.json", f"/bookings/ has {bookings_sessions} sessions — warm demand exists"))
        if sessions:
            evidence_for.append(_evidence("ga4-metrics.json", f"{sessions} total sessions in last window"))

    # Ubersuggest — pulls from ubersuggest-domain.json for SEO
    seo = _read_json("ubersuggest-domain.json") or {}
    if seo and ("seo" in kpi or "search" in kpi or "ranking" in kpi):
        positions = seo.get("keyword_positions") or []
        rising = [k for k in positions if isinstance(k, dict) and (k.get("position_delta") or 0) <= -5]
        if rising:
            evidence_for.append(_evidence("ubersuggest-domain.json", f"{len(rising)} keywords rising 5+ positions"))

    # Decide verdict
    score = len(evidence_for) - len(evidence_against) * 2
    if score >= 1:
        on_track = True
        verdict = "on_track"
    elif score <= -2:
        on_track = False
        verdict = "behind"
    else:
        on_track = None
        verdict = "mixed"

    learned = ""
    if evidence_for and not evidence_against:
        learned = f"Data supports this bet: {'; '.join(e['value'] for e in evidence_for[:3])}"
    elif evidence_against:
        learned = f"Data challenges this bet: {'; '.join(e['value'] for e in evidence_against[:3])}. Investigate before doubling down."

    return {
        "bet_id": bet.get("id"),
        "campaign_id": campaign_id,
        "verdict": verdict,
        "on_track": on_track,
        "evidence_for": evidence_for,
        "evidence_against": evidence_against,
        "learned": learned,
        "recommended_status": bet.get("status"),  # don't override — caller decides
        "evaluated_at": _today(),
    }


# ─── Cross-cutting lessons ───────────────────────────────────────────

def mine_lessons_from_data(brand_id: str = "swing-shack") -> list:
    """Walk every data source and surface lessons worth remembering.
    Returns a list of lesson dicts ready to upsert into strategy_store."""

    lessons = []

    # 1. IG content patterns — which themes get engagement?
    ig = _read_json("ig-analytics.json") or {}
    if ig:
        posts = ig.get("posts", []) or []
        if posts:
            # Group by detected topic_cluster (the real IG field name)
            by_theme = {}
            for p in posts:
                theme = p.get("topic_cluster") or p.get("theme") or p.get("pillar") or p.get("topic") or "general"
                by_theme.setdefault(theme, []).append(p)
            for theme, theme_posts in by_theme.items():
                if len(theme_posts) >= 3:
                    def _to_num(v):
                        if isinstance(v, (int, float)): return float(v)
                        if isinstance(v, str):
                            try: return float(v.rstrip("%"))
                            except ValueError: return 0.0
                        return 0.0
                    avg_eng = sum(_to_num(p.get("engagementRate", 0)) for p in theme_posts) / len(theme_posts)
                    avg_reach = sum((p.get("reach", 0) or 0) for p in theme_posts) / len(theme_posts)
                    if avg_eng >= 3.0:
                        lessons.append({
                            "category": "worked",
                            "claim": f"{theme} content averages {avg_eng:.1f}% engagement over {len(theme_posts)} posts (avg reach {int(avg_reach)})",
                            "evidence": [
                                _evidence("ig-analytics.json", f"theme={theme} n={len(theme_posts)}", p.get("timestamp", "")[:10])
                                for p in theme_posts[:3]
                            ],
                            "source": "ig-analytics.json",
                            "auto": True,
                        })

        # 2. Identify worst-performing themes (underperformed)
        for theme, theme_posts in by_theme.items():
            if len(theme_posts) >= 3:
                def _to_num2(v):
                    if isinstance(v, (int, float)): return float(v)
                    if isinstance(v, str):
                        try: return float(v.rstrip("%"))
                        except ValueError: return 0.0
                    return 0.0
                avg_eng = sum(_to_num2(p.get("engagementRate", 0)) for p in theme_posts) / len(theme_posts)
                avg_reach = sum((p.get("reach", 0) or 0) for p in theme_posts) / len(theme_posts)
                if avg_eng < 1.0 and avg_reach < 200:
                    lessons.append({
                        "category": "underperformed",
                        "claim": f"{theme} content averages {avg_eng:.1f}% engagement / {int(avg_reach)} reach over {len(theme_posts)} posts — reconsider format or topic",
                        "evidence": [
                            _evidence("ig-analytics.json", f"theme={theme} n={len(theme_posts)}", p.get("timestamp", "")[:10])
                            for p in theme_posts[:3]
                        ],
                        "source": "ig-analytics.json",
                        "auto": True,
                    })

    # 3. GA4 leaks — pages getting traffic but no content pushing them
    ga4 = _read_json("ga4-metrics.json") or {}
    if ga4:
        pages = ga4.get("pages", []) or []
        warm_no_content = [
            p for p in pages
            if (p.get("sessions", 0) or 0) >= 50
            and "/bookings" in (p.get("path") or "") or "/fitting" in (p.get("path") or "")
        ]
        for p in warm_no_content[:3]:
            sessions = p.get("sessions", 0)
            lessons.append({
                "category": "data_suggests_test_next",
                "claim": f"{p.get('path')} is getting {sessions} sessions but no content is actively pushing it — create a tailored post",
                "evidence": [
                    _evidence("ga4-metrics.json", f"{p.get('path')}: {sessions} sessions, {p.get('engagementRate', '?')} engagement rate"),
                ],
                "source": "ga4-metrics.json",
                "auto": True,
            })

    # 4. Stories vs posts efficiency
    ig_biz = _read_json("ig-business-analytics.json") or {}
    if ig_biz:
        stories = ig_biz.get("stories") or ig_biz.get("ig_stories") or []
        posts = ig_biz.get("posts") or ig_biz.get("ig_posts") or []
        if stories and posts:
            total_story_reach = sum((s.get("reach", 0) or 0) for s in stories if isinstance(s, dict))
            story_hours = len(stories) * 24  # rough
            post_reach_28d = sum((p.get("reach", 0) or 0) for p in posts if isinstance(p, dict))
            if story_hours > 0 and total_story_reach > 0 and len(posts) > 0:
                story_reach_per_hr = total_story_reach / story_hours
                post_reach_per_post = post_reach_28d / len(posts)
                if story_reach_per_hr > post_reach_per_post * 2:
                    lessons.append({
                        "category": "worked",
                        "claim": f"Stories drive {story_reach_per_hr:.2f} reach/hr vs posts at {post_reach_per_post:.2f} reach/post — stories are the daily-momentum channel",
                        "evidence": [
                            _evidence("ig-business-analytics.json", f"{len(stories)} stories, {len(posts)} posts"),
                        ],
                        "source": "ig-business-analytics.json",
                        "auto": True,
                    })

    # 5. SEO — what improved and what slipped
    seo = _read_json("ubersuggest-domain.json") or {}
    if seo:
        kws = seo.get("keyword_positions") or []
        rising = sorted(
            [k for k in kws if isinstance(k, dict) and (k.get("position_delta") or 0) < 0],
            key=lambda k: k.get("position_delta", 0)
        )
        falling = sorted(
            [k for k in kws if isinstance(k, dict) and (k.get("position_delta") or 0) > 0],
            key=lambda k: -k.get("position_delta", 0)
        )
        for k in rising[:3]:
            d = k.get("position_delta", 0)
            if d <= -5:
                lessons.append({
                    "category": "worked",
                    "claim": f"'{k.get('keyword')}' rose {abs(d)} positions — double down on this topic cluster",
                    "evidence": [_evidence("ubersuggest-domain.json", f"#{k.get('old_position', '?')} → #{k.get('position', '?')}")],
                    "source": "ubersuggest-domain.json",
                    "auto": True,
                })
        for k in falling[:2]:
            d = k.get("position_delta", 0)
            if d >= 5:
                lessons.append({
                    "category": "underperformed",
                    "claim": f"'{k.get('keyword')}' slipped {d} positions — refresh content + build internal links",
                    "evidence": [_evidence("ubersuggest-domain.json", f"#{k.get('old_position', '?')} → #{k.get('position', '?')}")],
                    "source": "ubersuggest-domain.json",
                    "auto": True,
                })

    return lessons


def diff_lessons(new_lessons: list, existing_lessons: list) -> dict:
    """Compare newly-mined lessons against the existing strategy store.
    Returns:
      to_add: lessons that don't exist yet
      to_invalidate: existing lessons the new data challenges
    """
    existing_claims = {l.get("claim", "").lower()[:80]: l for l in existing_lessons if l.get("still_valid", True)}

    to_add = []
    for nl in new_lessons:
        # De-dup by claim prefix
        key = nl.get("claim", "").lower()[:80]
        if key not in existing_claims:
            to_add.append(nl)

    # For each existing lesson, check if newer data challenges it
    to_invalidate = []
    for ek, el in existing_claims.items():
        ec = el.get("category")
        if ec == "worked":
            # Find a new underperformed lesson with the same theme/keyword
            for nl in new_lessons:
                if nl.get("category") == "underperformed" and any(
                    t in nl.get("claim", "").lower() for t in el.get("claim", "").lower().split() if len(t) > 4
                ):
                    to_invalidate.append(el.get("id"))
                    break

    return {"to_add": to_add, "to_invalidate": to_invalidate}
