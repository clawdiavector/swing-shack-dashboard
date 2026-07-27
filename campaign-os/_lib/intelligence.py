"""
Campaign OS Intelligence — pure-Python aggregator that turns the 167 JSON
data files into one live, opinionated view per request.

Design rules:
- No LLM calls. All output is derived from existing campaign-os/data JSON.
- Every endpoint returns JSON in {ok, data, summary, ts} envelope.
- Pure functions where possible. Defensive reads — missing file = empty.
- Aggregations are computed once per call; cheap enough for the volume.
"""
from __future__ import annotations

import json
import os
import glob
import datetime
from typing import Any, Dict, List, Optional, Tuple

# Repo root (one level up from campaign-os/)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(REPO_ROOT, "data")

CAMPAIGN_OS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _runtime_data_file(name: str) -> str:
    """Prefer the persistent runtime disk, then the bundled data corpus."""
    runtime_dir = os.environ.get("DATA_DIR")
    if runtime_dir:
        candidate = os.path.join(runtime_dir, name)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(DATA_DIR, name)


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _all_data_files() -> List[str]:
    if not os.path.isdir(DATA_DIR):
        return []
    return sorted(glob.glob(os.path.join(DATA_DIR, "*.json")))


def _campaign_data() -> Dict[str, Any]:
    """Load canonical campaign data, preferring /data then bundled."""
    p1 = os.path.join(os.environ.get("DATA_DIR", "/data"), "campaign-data.json")
    p2 = os.path.join(CAMPAIGN_OS_ROOT, "campaign-data.json")
    if os.path.exists(p1):
        d = _read_json(p1)
        if d:
            return d
    if os.path.exists(p2):
        d = _read_json(p2)
        if d:
            return d
    return {"campaigns": {}, "activeCampaignId": None, "portfolioMetadata": {}}


# ─── BRIEF / HOME ──────────────────────────────────────────────────────

def morning_brief() -> Dict[str, Any]:
    """Synthesize 'what should Christelle do today?' from all signals."""
    cd = _campaign_data()
    campaigns = cd.get("campaigns", {})

    # Count assets by status across all campaigns
    counts = {"approved": 0, "draft": 0, "blocked": 0, "review": 0, "published": 0, "scheduled": 0, "total": 0}
    needs_review = []
    ready_to_publish = []
    overdue = []

    for cid, c in campaigns.items():
        for aid, asset in (c.get("assets") or {}).items():
            counts["total"] += 1
            aps = asset.get("approvalStatus", "")
            if aps == "approved":
                counts["approved"] += 1
                ps = asset.get("publishStatus", "")
                if ps in ("draft", "queued", "ready"):
                    ready_to_publish.append({"campaignId": cid, "assetId": aid, "name": asset.get("name", aid)})
                elif ps == "scheduled":
                    counts["scheduled"] += 1
            elif aps in ("revisionRequested",):
                counts["review"] += 1
                needs_review.append({"campaignId": cid, "assetId": aid, "name": asset.get("name", aid), "issue": asset.get("revisionRequest", "")})
            elif aps == "rejected":
                counts["blocked"] += 1
            else:
                counts["draft"] += 1

    # Pull top recommendations from data/
    do_first = (_read_json(os.path.join(DATA_DIR, "recommendation-scores.json")) or {}).get("do_first") or []
    missed = (_read_json(os.path.join(DATA_DIR, "missed-opportunities.json")) or {})
    missed_list = missed.get("opportunities", []) if isinstance(missed, dict) else []
    high_impact_missed = [m for m in missed_list if isinstance(m, dict) and m.get("severity") == "high"][:3]

    # Quick wins from SEO
    seo = _read_json(os.path.join(DATA_DIR, "seo-rankings.json")) or {}
    quick_wins = seo.get("quick_wins", [])[:3] if isinstance(seo, dict) else []

    # Today's content ideas
    ideas = _read_json(os.path.join(DATA_DIR, "content-ideas.json")) or {}
    post_today = ideas.get("post_today", []) if isinstance(ideas, dict) else []

    return {
        "ok": True,
        "ts": _now_iso(),
        "summary": (
            f"{counts['total']} assets in flight. "
            f"{len(needs_review)} need review. "
            f"{len(ready_to_publish)} ready to publish."
        ),
        "counts": counts,
        "do_first": do_first[:5] if isinstance(do_first, list) else [],
        "needs_review": needs_review[:10],
        "ready_to_publish": ready_to_publish[:10],
        "missed_high_impact": high_impact_missed,
        "seo_quick_wins": quick_wins,
        "post_today": post_today[:5] if isinstance(post_today, list) else [],
    }


# ─── CALENDAR ──────────────────────────────────────────────────────────

def calendar_view(days: int = 14, start: Optional[str] = None) -> Dict[str, Any]:
    """Build a calendar from campaign assets, sidecar schedules, and queue items."""
    cd = _campaign_data()
    campaigns = cd.get("campaigns", {})
    schedule_manifest = _read_json(_runtime_data_file("scheduled-items.json")) or {}
    schedule_items = schedule_manifest.get("scheduled", []) if isinstance(schedule_manifest, dict) else []
    schedule_map = {}
    for item in schedule_items if isinstance(schedule_items, list) else []:
        if isinstance(item, dict):
            for key in (item.get("assetId"), item.get("asset_id"), item.get("item_id"), item.get("publish_id"), item.get("id")):
                if key:
                    schedule_map[key] = item

    try:
        start_date = datetime.date.fromisoformat(start[:10]) if start else datetime.date.today()
    except (TypeError, ValueError):
        start_date = datetime.date.today()
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    seen = set()
    seen_asset_ids = set()

    def add_slot(slot: Dict[str, Any], scheduled_for: Optional[str]):
        if not scheduled_for:
            return
        try:
            d = datetime.datetime.fromisoformat(str(scheduled_for).replace("Z", "+00:00")).date()
        except (ValueError, AttributeError):
            return
        slot["scheduledFor"] = scheduled_for
        slot.setdefault("source", "campaign")
        slot.setdefault("color", _calendar_color(slot.get("pillar"), slot.get("brand"), slot.get("platform")))
        key = (slot.get("assetId"), slot.get("source"), d.isoformat())
        if key in seen:
            return
        seen.add(key)
        seen_asset_ids.add(slot.get("assetId"))
        by_day.setdefault(d.isoformat(), []).append(slot)

    for cid, c in campaigns.items():
        cname = c.get("identity", {}).get("name", cid)
        identity = c.get("identity") or {}
        for aid, asset in (c.get("assets") or {}).items():
            override = schedule_map.get(aid) or {}
            slot = {
                "source": "calendar" if override else "campaign",
                "campaignId": cid,
                "campaignName": cname,
                "assetId": aid,
                "name": asset.get("name", aid),
                "caption": asset.get("caption", "")[:180],
                "approvalStatus": asset.get("approvalStatus", "draft"),
                "publishStatus": asset.get("publishStatus", "draft"),
                "platform": asset.get("platform") or asset.get("integration", "instagram"),
                "brand": identity.get("brand") or identity.get("business") or "Swing Shack",
                "pillar": asset.get("pillarName") or asset.get("pillar") or "",
            }
            slot.update({k: v for k, v in override.items() if k in ("brand", "pillar", "platform", "campaignId") and v})
            add_slot(slot, override.get("scheduledFor") or asset.get("scheduledFor") or asset.get("publishDate"))

    pq = _read_json(_runtime_data_file("publish-queue.json")) or {}
    queued = pq.get("queued", []) if isinstance(pq, dict) else []
    if not isinstance(queued, list):
        queued = []
    for i, it in enumerate(queued[:100]):
        if not isinstance(it, dict):
            continue
        asset_id = it.get("assetId") or it.get("asset_id") or it.get("item_id") or it.get("publish_id") or f"queue-{i}"
        if asset_id in seen_asset_ids and asset_id not in schedule_map:
            continue
        if asset_id in schedule_map:
            scheduled_for = schedule_map[asset_id].get("scheduledFor")
        else:
            scheduled_for = it.get("publishDate") or it.get("publish_at") or it.get("date")
            if not scheduled_for:
                # Preserve the existing useful queue preview, but make it a
                # real, addressable calendar slot for drag/drop.
                per_day = max(1, len(queued) // max(days, 1))
                scheduled_for = (start_date + datetime.timedelta(days=min(i // per_day, max(days - 1, 0)))).isoformat() + "T09:00:00Z"
        slot = {
            "source": "queue",
            "assetId": asset_id,
            "campaignId": it.get("campaignId") or it.get("campaign_id"),
            "campaignName": it.get("campaignName") or it.get("campaign_name") or "Publisher queue",
            "name": (it.get("caption_preview") or it.get("caption") or it.get("name") or it.get("linked_hook_id", "—"))[:90],
            "caption": it.get("caption") or it.get("caption_preview", ""),
            "approvalStatus": it.get("approvalStatus", "approved"),
            "publishStatus": "scheduled" if scheduled_for else it.get("status", "queued"),
            "platform": it.get("platform", "instagram"),
            "brand": it.get("brand") or "Swing Shack",
            "pillar": it.get("pillarName") or it.get("pillar") or "",
            "postizId": it.get("postiz_post_id") or it.get("postizId"),
            "queueIndex": i,
        }
        override = schedule_map.get(asset_id) or {}
        if override:
            slot.update({k: v for k, v in override.items() if k in ("brand", "pillar", "platform", "campaignId") and v})
        add_slot(slot, scheduled_for)

    # Sidecar-only copies have no entry in campaign-data.json or the publisher
    # queue. They still need to render immediately after a duplicate drop.
    for item in schedule_items if isinstance(schedule_items, list) else []:
        if not isinstance(item, dict):
            continue
        asset_id = item.get("assetId") or item.get("asset_id") or item.get("item_id") or item.get("publish_id")
        if not asset_id or asset_id in seen_asset_ids:
            continue
        slot = {
            "source": "calendar",
            "assetId": asset_id,
            "campaignId": item.get("campaignId"),
            "campaignName": item.get("campaignName") or "Calendar copy",
            "name": (item.get("name") or item.get("caption") or asset_id)[:90],
            "caption": item.get("caption", ""),
            "approvalStatus": item.get("approvalStatus", "draft"),
            "publishStatus": item.get("publishStatus", "scheduled"),
            "platform": item.get("platform", "instagram"),
            "brand": item.get("brand") or "Swing Shack",
            "pillar": item.get("pillar") or item.get("pillarName") or "",
        }
        add_slot(slot, item.get("scheduledFor") or item.get("publishDate"))

    days_list = []
    for i in range(max(1, min(int(days or 14), 60))):
        d = start_date + datetime.timedelta(days=i)
        key = d.isoformat()
        slots = sorted(by_day.get(key, []), key=lambda x: x.get("scheduledFor", ""))
        days_list.append({"date": key, "weekday": d.strftime("%a"), "slots": slots, "count": len(slots)})
    total_scheduled = sum(day["count"] for day in days_list)
    return {"ok": True, "ts": _now_iso(), "today": start_date.isoformat(), "days": days_list, "totalScheduled": total_scheduled}


def _calendar_color(pillar: Any, brand: Any, platform: Any) -> str:
    palette = {
        "education": "#34d399", "education & authority": "#34d399",
        "social proof": "#60a5fa", "offer": "#fb923c", "community": "#a78bfa",
        "entertainment": "#facc15", "instagram": "#f472b6", "tiktok": "#e6ecf5",
        "gmb": "#60a5fa", "swing shack": "#34d399", "stick": "#fb923c", "bag drop": "#a78bfa",
    }
    for value in (pillar, brand, platform):
        key = str(value or "").strip().lower()
        if key in palette:
            return palette[key]
    return "#34d399"


# ─── REVIEW INBOX ──────────────────────────────────────────────────────

def review_inbox() -> Dict[str, Any]:
    """All assets needing decision, sorted by priority."""
    cd = _campaign_data()
    campaigns = cd.get("campaigns", {})

    pending = []
    approved = []
    rejected = []

    for cid, c in campaigns.items():
        cname = c.get("identity", {}).get("name", cid)
        for aid, asset in (c.get("assets") or {}).items():
            aps = asset.get("approvalStatus", "draft")
            if aps == "approved":
                approved.append({"campaignId": cid, "campaignName": cname, "assetId": aid, "name": asset.get("name", aid), "caption": asset.get("caption", "")[:120], "publishStatus": asset.get("publishStatus"), "updatedAt": asset.get("updatedAt")})
            elif aps in ("rejected",):
                rejected.append({"campaignId": cid, "campaignName": cname, "assetId": aid, "name": asset.get("name", aid), "reason": asset.get("rejectionReason", ""), "updatedAt": asset.get("updatedAt")})
            else:
                pending.append({"campaignId": cid, "campaignName": cname, "assetId": aid, "name": asset.get("name", aid), "caption": asset.get("caption", "")[:200], "approvalStatus": aps, "platform": asset.get("platform") or asset.get("integration", "instagram"), "updatedAt": asset.get("updatedAt")})

    return {
        "ok": True,
        "ts": _now_iso(),
        "summary": f"{len(pending)} pending review · {len(approved)} approved · {len(rejected)} rejected",
        "pending": pending,
        "approved": approved[:20],
        "rejected": rejected[:10],
    }


# ─── HOOKS ─────────────────────────────────────────────────────────────

def hooks_view() -> Dict[str, Any]:
    """Hook bank — watched and worked + formulas + recent + by kind."""
    hb = _read_json(os.path.join(DATA_DIR, "hook-bank.json")) or {}
    if not isinstance(hb, dict):
        return {"ok": False, "error": "hook-bank.json unreadable"}
    ob = hb.get("output_buckets", {}) if isinstance(hb.get("output_buckets"), dict) else {}
    # Flatten all buckets into a single list of hooks for convenience
    all_hooks = []
    for bucket_name in ("proven_and_trending", "proven_only", "trending_to_test"):
        for h in (ob.get(bucket_name) or []):
            if isinstance(h, dict):
                h["_bucket"] = bucket_name
                all_hooks.append(h)
    return {
        "ok": True,
        "ts": _now_iso(),
        "total": hb.get("total_hooks", 0),
        "watched_and_worked": hb.get("watched_and_worked", [])[:30],
        "hook_formulas": hb.get("hook_formulas", [])[:20],
        "output_buckets": ob,
        "all_hooks": all_hooks[:50],
        "cross_signal_sources": hb.get("cross_signal_sources", []),
    }


# ─── MEMES ─────────────────────────────────────────────────────────────

def memes_view() -> Dict[str, Any]:
    """Meme ideas + captions + variants + performance."""
    ideas = _read_json(os.path.join(DATA_DIR, "content-ideas.json")) or {}
    memes = ideas.get("memes", []) if isinstance(ideas, dict) else []
    captions = _read_json(os.path.join(DATA_DIR, "captions.json")) or {}
    cap_list = captions.get("captions", []) if isinstance(captions, dict) else []
    variants = _read_json(os.path.join(DATA_DIR, "caption-variants.json")) or {}
    var_list = variants.get("variants", []) if isinstance(variants, dict) else []
    return {
        "ok": True,
        "ts": _now_iso(),
        "summary": f"{len(memes)} meme ideas · {len(cap_list)} captions · {len(var_list)} variants",
        "memes": memes[:30],
        "captions": cap_list[:30],
        "variants": var_list[:30],
    }


# ─── BILLBOARDS ────────────────────────────────────────────────────────

def billboards_view() -> Dict[str, Any]:
    """Billboard / hero / banner concepts."""
    ideas = _read_json(os.path.join(DATA_DIR, "content-ideas.json")) or {}
    billboards = ideas.get("billboards", []) if isinstance(ideas, dict) else []
    briefs = _read_json(os.path.join(DATA_DIR, "visual-briefs.json")) or {}
    brief_list = briefs.get("briefs", []) if isinstance(briefs, dict) else []
    return {
        "ok": True,
        "ts": _now_iso(),
        "summary": f"{len(billboards)} billboard concepts · {len(brief_list)} visual briefs",
        "billboards": billboards[:30],
        "briefs": brief_list[:30],
    }


# ─── CAPTION STUDIO ───────────────────────────────────────────────────

def caption_studio() -> Dict[str, Any]:
    """All captions + variants + CTAs + platform splits."""
    caps = _read_json(os.path.join(DATA_DIR, "captions.json")) or {}
    variants = _read_json(os.path.join(DATA_DIR, "caption-variants.json")) or {}
    cta = _read_json(os.path.join(DATA_DIR, "cta-performance.json")) or {}
    return {
        "ok": True,
        "ts": _now_iso(),
        "captions": caps.get("captions", []) if isinstance(caps, dict) else [],
        "by_format": caps.get("by_format", {}) if isinstance(caps, dict) else {},
        "by_platform": caps.get("by_platform", {}) if isinstance(caps, dict) else {},
        "variants": variants.get("variants", []) if isinstance(variants, dict) else [],
        "cta_rankings": cta.get("cta_rankings", []) if isinstance(cta, dict) else [],
        "best_cta": cta.get("best_cta") if isinstance(cta, dict) else None,
    }


# ─── PERFORMANCE ───────────────────────────────────────────────────────

def performance_view() -> Dict[str, Any]:
    """Instagram + GA4 + GBP + SEO performance with explanatory insights."""
    ig = _read_json(os.path.join(DATA_DIR, "ig-analytics.json")) or {}
    ga4 = _read_json(os.path.join(DATA_DIR, "ga4-metrics.json")) or {}
    seo = _read_json(os.path.join(DATA_DIR, "seo-audit.json")) or {}
    seo_rank = _read_json(os.path.join(DATA_DIR, "seo-rankings.json")) or {}
    website = _read_json(os.path.join(DATA_DIR, "website-insights.json")) or {}
    ab = _read_json(os.path.join(DATA_DIR, "ab-tests.json")) or {}
    gmb = _read_json(os.path.join(DATA_DIR, "gbp-input.json")) or {}

    ig_posts = ig.get("posts", []) if isinstance(ig, dict) else []

    def _er(p):
        try:
            v = p.get("engagementRate", 0) if isinstance(p, dict) else 0
            return float(v) if v else 0.0
        except (ValueError, TypeError):
            return 0.0

    # Sort by engagement rate, take top 10
    top_ig = sorted([p for p in ig_posts if isinstance(p, dict)], key=_er, reverse=True)[:10]

    insights = []
    if ig_posts:
        er_avg = sum(_er(p) for p in ig_posts) / max(len(ig_posts), 1)
        insights.append({"label": "Instagram avg engagement rate", "value": f"{er_avg:.2f}%", "kind": "kpi"})
        if top_ig:
            top = top_ig[0]
            cap = top.get("hook_text") or top.get("captionPreview") or top.get("caption") or ""
            cap = cap[:80]
            insights.append({"label": "Top performer", "value": cap, "kind": "winner"})

    if isinstance(ga4, dict):
        insights.append({"label": "GA4 sessions", "value": str(ga4.get("total_sessions", "—")), "kind": "kpi"})
    if isinstance(seo_rank, dict):
        rising = seo_rank.get("rising_keywords", [])
        if isinstance(rising, list) and rising:
            insights.append({"label": "Rising keywords", "value": ", ".join(str(k) for k in rising[:3]), "kind": "trend-up"})

    return {
        "ok": True,
        "ts": _now_iso(),
        "insights": insights,
        "instagram": {
            "total_posts": ig.get("total_posts", len(ig_posts) if isinstance(ig_posts, list) else 0),
            "top_posts": top_ig,
        },
        "ga4": {
            "total_sessions": ga4.get("total_sessions"),
            "pages": ga4.get("pages", [])[:10] if isinstance(ga4, dict) else [],
        },
        "seo": {
            "audit_summary": (seo.get("summary", {}) if isinstance(seo, dict) else {}),
            "rankings_summary": (seo_rank.get("summary", {}) if isinstance(seo_rank, dict) else {}),
            "rising": (seo_rank.get("rising_keywords", []) if isinstance(seo_rank, dict) else []),
            "falling": (seo_rank.get("falling_keywords", []) if isinstance(seo_rank, dict) else []),
            "keywords": (seo_rank.get("keywords", []) if isinstance(seo_rank, dict) else []),
            "quick_wins": (seo_rank.get("quick_wins", []) if isinstance(seo_rank, dict) else []),
        },
        "website": website if isinstance(website, dict) else {},
        "ab_tests": (ab.get("tests", []) if isinstance(ab, dict) else []),
        "gbp": gmb if isinstance(gmb, dict) else {},
    }


# ─── LEARNING ─────────────────────────────────────────────────────────

def learning_view() -> Dict[str, Any]:
    """What worked, what failed, what to repeat."""
    rep = _read_json(os.path.join(DATA_DIR, "weekly-learnings.json")) or {}
    rec = _read_json(os.path.join(DATA_DIR, "recommendation-outcomes.json")) or {}
    trend = _read_json(os.path.join(DATA_DIR, "trend-delta.json")) or {}
    cta = _read_json(os.path.join(DATA_DIR, "cta-performance.json")) or {}
    fail = _read_json(os.path.join(DATA_DIR, "failure-patterns.json")) or {}
    conf = _read_json(os.path.join(DATA_DIR, "confidence-calibration.json")) or {}
    return {
        "ok": True,
        "ts": _now_iso(),
        "what_worked": (rep.get("what_worked", []) if isinstance(rep, dict) else []),
        "what_failed": (rep.get("what_failed", []) if isinstance(rep, dict) else []),
        "recommendation_outcomes": (rec.get("learned_signals", []) if isinstance(rec, dict) else []),
        "best_recommendation": (rec.get("best_recommendation") if isinstance(rec, dict) else None),
        "trend_delta": (trend.get("hook_trends", []) if isinstance(trend, dict) else []),
        "cta_rankings": (cta.get("cta_rankings", []) if isinstance(cta, dict) else []),
        "failure_patterns": (fail.get("patterns", []) if isinstance(fail, dict) else []),
        "confidence_bands": (conf.get("honest_confidence_bands", {}) if isinstance(conf, dict) else {}),
    }


# ─── GENERATORS (intelligence helpers) ─────────────────────────────────

def _signal_pool() -> Dict[str, List[Any]]:
    def _as_list(v, cap=200):
        if isinstance(v, list):
            return v[:cap]
        if isinstance(v, dict):
            # Convert dict → list of {key, value} items, drop empty values
            out = []
            for k, val in v.items():
                if isinstance(val, (str, int, float)):
                    out.append({"key": k, "value": val})
                elif isinstance(val, dict):
                    out.append({"key": k, **val})
                elif isinstance(val, list):
                    for it in val:
                        if isinstance(it, dict):
                            out.append({"key": k, **it})
                        else:
                            out.append({"key": k, "value": it})
            return out
        return []
    return {
        "reddit_pain_points": _as_list((((_read_json(os.path.join(DATA_DIR, "reddit-opportunities.json")) or {}).get("opportunities", [])) or [])),
        "golf_news": _as_list((((_read_json(os.path.join(DATA_DIR, "golf-news.json")) or {}).get("news", [])) or [])),
        "youtube_trends": _as_list((((_read_json(os.path.join(DATA_DIR, "youtube-trends.json")) or {}).get("trending_themes", [])) or [])),
        "youtube_ideas": _as_list((((_read_json(os.path.join(DATA_DIR, "youtube-ideas.json")) or {}).get("ideas", [])) or [])),
        "competitor_changes": _as_list((((_read_json(os.path.join(DATA_DIR, "competitor-tracker.json")) or {}).get("changes", [])) or [])),
        "missed_opportunities": _as_list((((_read_json(os.path.join(DATA_DIR, "missed-opportunities.json")) or {}).get("opportunities", [])) or [])),
        "faq_opportunities": _as_list((((_read_json(os.path.join(DATA_DIR, "faq-opportunities.json")) or {}).get("faqs", [])) or [])),
        "forum_opportunities": _as_list((((_read_json(os.path.join(DATA_DIR, "forum-opportunities.json")) or {}).get("opportunities", [])) or [])),
        "reddit_trends": _as_list((((_read_json(os.path.join(DATA_DIR, "reddit-trends.json")) or {}).get("trends", [])) or [])),
        "reddit_replies": _as_list((((_read_json(os.path.join(DATA_DIR, "reddit-replies.json")) or {}).get("replies", [])) or [])),
        "seo_audit": [(_read_json(os.path.join(DATA_DIR, "seo-audit.json")) or {})],
        "seo_rankings": [(_read_json(os.path.join(DATA_DIR, "seo-rankings.json")) or {})],
        "local_opportunities": _as_list((((_read_json(os.path.join(DATA_DIR, "offer-opportunities.json")) or {}).get("offers", [])) or [])),
        "seasonal_opportunities": _as_list((((_read_json(os.path.join(DATA_DIR, "merchandising-board.json")) or {}).get("sections", [])) or [])),
    }


def generate_hooks(n: int = 10) -> Dict[str, Any]:
    """Build hook ideas from signals."""
    pool = _signal_pool()
    out = []
    # From reddit pain points
    for r in pool["reddit_pain_points"][:n]:
        if not isinstance(r, dict):
            continue
        ang = r.get("suggested_angle") or r.get("angle") or r.get("title") or r.get("pain_point") or r.get("trend_pain_point") or r.get("thread_topic") or ""
        if isinstance(ang, str) and ang:
            out.append({"hook": f"The golf truth nobody tells you: {ang[:80]}", "source": "reddit", "kind": "pain-point"})
        if len(out) >= n:
            break
    # From golf news
    if len(out) < n:
        for n_ in pool["golf_news"][:n]:
            if not isinstance(n_, dict):
                continue
            t = n_.get("title") or n_.get("headline") or n_.get("name") or n_.get("summary") or ""
            if isinstance(t, str) and t:
                out.append({"hook": f"While everyone is talking about {t[:60]}...", "source": "golf-news", "kind": "trend-jack"})
            if len(out) >= n:
                break
    # From missed opportunities (use hook field directly if available)
    if len(out) < n:
        for m in pool["missed_opportunities"][:n]:
            if not isinstance(m, dict):
                continue
            t = m.get("hook") or m.get("title") or m.get("issue") or m.get("suggested_fix") or m.get("suggestion") or m.get("summary") or ""
            if isinstance(t, str) and t and len(t) > 15:
                # If it's a complete hook (looks like a sentence), use as-is
                if any(t.lower().startswith(w) for w in ['the ', 'why ', 'how ', 'what ', 'this ', 'have you', 'need to', 'stop ', 'your ', 'here']):
                    out.append({"hook": t[:120], "source": "missed-opp", "kind": "gap-fix"})
                else:
                    out.append({"hook": f"You're losing bookings because: {t[:60]}", "source": "missed-opp", "kind": "gap-fix"})
            if len(out) >= n:
                break
    # Fallback to evergreen templates if still empty
    if not out:
        templates = [
            "The lie every golfer believes about the range",
            "Why your slice won't fix itself in 2026",
            "The 30-minute test that changed this golfer's game",
            "What your TrackMan sees that you don't",
            "Driver fitting: what nobody tells you about shafts",
            "The real reason your iron shots fly short",
            "How Johannesburg weather affects your swing speed",
            "Why indoor practice beats range sessions",
            "The mistake 80% of golfers make on the downswing",
            "What fitting actually fixes (it's not the club)",
        ]
        for t in templates[:n]:
            out.append({"hook": t, "source": "evergreen", "kind": "evergreen"})
    return {"ok": True, "ts": _now_iso(), "generated": out[:n], "count": len(out)}


def generate_captions(asset_id: Optional[str] = None, n: int = 5) -> Dict[str, Any]:
    """Build caption variations from campaign asset + hook pool."""
    cd = _campaign_data()
    asset = None
    campaign_name = ""
    if asset_id:
        for cid, c in cd.get("campaigns", {}).items():
            if asset_id in (c.get("assets") or {}):
                asset = c["assets"][asset_id]
                campaign_name = c.get("identity", {}).get("name", cid)
                break
    if not asset:
        return {"ok": False, "error": "Asset not found", "asset_id": asset_id}

    pool = generate_hooks(8).get("generated", [])
    name = asset.get("name", "")
    platform = asset.get("platform") or asset.get("integration", "instagram")
    audience = asset.get("audience", "") if isinstance(asset.get("audience"), str) else ""
    base_caption = asset.get("caption") or asset.get("text") or ""
    if not base_caption:
        # Try hook from the hook bank for this campaign
        hb = _read_json(os.path.join(DATA_DIR, "hook-bank.json")) or {}
        buckets = hb.get("output_buckets", {}) if isinstance(hb.get("output_buckets"), dict) else {}
        for bname in ("proven_and_trending", "proven_only", "trending_to_test"):
            for h in (buckets.get(bname) or []):
                if isinstance(h, dict) and h.get("hook_text"):
                    base_caption = h["hook_text"]
                    break
                if base_caption:
                    break
            if base_caption:
                break
    if not base_caption:
        base_caption = f"{name or campaign_name or 'your post'} — book your session at swingshack.co.za"

    out = []
    for i, hook in enumerate(pool[:n]):
        title = hook.get("hook", "") if isinstance(hook, dict) else ""
        if not title:
            continue
        body = f"{title}\n\n{base_caption[:240]}\n\nBook a session → swingshack.co.za"
        out.append({
            "variant": i + 1,
            "hook": title,
            "body": body,
            "cta": "Book a session",
            "platform": platform,
            "source": hook.get("source") if isinstance(hook, dict) else None,
        })
    return {"ok": True, "ts": _now_iso(), "asset": asset_id, "campaign": campaign_name, "variants": out, "count": len(out)}


def generate_ctas(n: int = 5) -> Dict[str, Any]:
    """Generate CTA variations from CTA performance + offer data."""
    cta = _read_json(os.path.join(DATA_DIR, "cta-performance.json")) or {}
    rankings = cta.get("cta_rankings", []) if isinstance(cta, dict) else []
    best = cta.get("best_cta") if isinstance(cta, dict) else None

    pool = []
    if isinstance(rankings, list):
        for r in rankings[:n*2]:
            if isinstance(r, dict):
                cta_text = r.get("cta") or r.get("text") or r.get("copy", "")
                if isinstance(cta_text, str) and cta_text:
                    pool.append({"cta": cta_text, "source": "performance", "perf": r.get("score") or r.get("cvr")})

    if not pool:
        pool = [
            {"cta": "Book a Practice Session → swingshack.co.za", "source": "default"},
            {"cta": "Try the TrackMan — 30 mins, R150", "source": "default"},
            {"cta": "DM us to lock your fitting slot", "source": "default"},
            {"cta": "Tap the link in bio to book", "source": "default"},
            {"cta": "Free swing analysis this week", "source": "default"},
        ]
    return {"ok": True, "ts": _now_iso(), "ctas": pool[:n], "best_cta": best, "count": min(n, len(pool))}


def generate_headlines(n: int = 5) -> Dict[str, Any]:
    """Headline templates + golf-news angles."""
    pool = _signal_pool()
    out = []
    templates = [
        "Why {audience} are switching to {service}",
        "The {n}-minute test that fixes your {problem}",
        "{audience}: stop doing {mistake}",
        "What your pro wishes you'd do at the range",
        "Indoor golf in JHB: the real difference",
    ]
    angles = pool["golf_news"][:5] + pool["reddit_pain_points"][:5]
    for i, ang in enumerate(angles):
        if not isinstance(ang, dict):
            continue
        seed = ang.get("title") or ang.get("angle") or ang.get("pain_point", "your swing")
        if isinstance(seed, str) and seed:
            tmpl = templates[i % len(templates)]
            headline = tmpl.format(audience="Johannesburg golfers", service="TrackMan fitting", n="30", problem="slice", mistake="this at the range")
            out.append({"headline": headline, "seed": seed[:80], "source": ang.get("source") or "pool"})
        if len(out) >= n:
            break
    return {"ok": True, "ts": _now_iso(), "headlines": out, "count": len(out)}


def reddit_outreach() -> Dict[str, Any]:
    pool = _signal_pool()
    return {
        "ok": True,
        "ts": _now_iso(),
        "pain_points": pool["reddit_pain_points"][:20],
        "trends": pool["reddit_trends"][:20],
        "replies": pool["reddit_replies"][:20],
        "summary": f"{len(pool['reddit_pain_points'])} pain points · {len(pool['reddit_trends'])} trends · {len(pool['reddit_replies'])} replies ready",
    }


def gbp_suggestions() -> Dict[str, Any]:
    inp = _read_json(os.path.join(DATA_DIR, "gbp-input.json")) or {}
    out = _read_json(os.path.join(DATA_DIR, "gbp-output.json")) or {}
    return {
        "ok": True,
        "ts": _now_iso(),
        "input": inp if isinstance(inp, dict) else {},
        "last_post": out if isinstance(out, dict) else {},
    }


def seo_assistant() -> Dict[str, Any]:
    audit = _read_json(os.path.join(DATA_DIR, "seo-audit.json")) or {}
    rank = _read_json(os.path.join(DATA_DIR, "seo-rankings.json")) or {}
    geo = _read_json(os.path.join(DATA_DIR, "geo-audit.json")) or {}
    fixes = _read_json(os.path.join(DATA_DIR, "landing-page-fixes.json")) or {}
    return {
        "ok": True,
        "ts": _now_iso(),
        "audit": audit if isinstance(audit, dict) else {},
        "rankings": rank if isinstance(rank, dict) else {},
        "geo": geo if isinstance(geo, dict) else {},
        "fixes": fixes.get("fixes", []) if isinstance(fixes, dict) else [],
    }


def faq_generator(n: int = 10) -> Dict[str, Any]:
    faq = _read_json(os.path.join(DATA_DIR, "faq-opportunities.json")) or {}
    list_ = faq.get("faqs", []) if isinstance(faq, dict) else []
    return {"ok": True, "ts": _now_iso(), "faqs": list_[:n], "count": min(n, len(list_))}


def trend_catcher() -> Dict[str, Any]:
    pool = _signal_pool()
    # Golf news: also pull post_ideas + story_today + reel_today
    gn = _read_json(os.path.join(DATA_DIR, "golf-news.json")) or {}
    golf_news_combined = []
    if isinstance(gn, dict):
        for key in ("news", "post_ideas", "story_today", "reel_today"):
            v = gn.get(key) or []
            if isinstance(v, list):
                golf_news_combined.extend([{**x, "_src": key} for x in v if isinstance(x, dict)])

    # Reddit trends: also pull hot_pain_points + top_posts
    rt = _read_json(os.path.join(DATA_DIR, "reddit-trends.json")) or {}
    reddit_combined = []
    if isinstance(rt, dict):
        for key in ("trends", "trend_clusters", "hot_pain_points", "top_posts"):
            v = rt.get(key) or []
            if isinstance(v, list):
                reddit_combined.extend([{**x, "_src": key} for x in v if isinstance(x, dict)])

    return {
        "ok": True,
        "ts": _now_iso(),
        "reddit": reddit_combined[:20] or pool["reddit_trends"][:20],
        "youtube": pool["youtube_trends"][:20],
        "golf_news": golf_news_combined[:20] or pool["golf_news"][:20],
        "competitor_changes": pool["competitor_changes"][:20],
        "summary": f"{len(reddit_combined)} reddit · {len(pool['youtube_trends'])} youtube · {len(golf_news_combined)} news · {len(pool['competitor_changes'])} competitor",
    }


# ─── OPPORTUNITIES / IDEAS ─────────────────────────────────────────────

def opportunities_view() -> Dict[str, Any]:
    ideas = _read_json(os.path.join(DATA_DIR, "content-ideas.json")) or {}
    missed = _read_json(os.path.join(DATA_DIR, "missed-opportunities.json")) or {}
    upsell = _read_json(os.path.join(DATA_DIR, "upsell-opportunities.json")) or {}
    bundle = _read_json(os.path.join(DATA_DIR, "bundle-opportunities.json")) or {}
    land = _read_json(os.path.join(DATA_DIR, "landing-page-fixes.json")) or {}
    cap = _read_json(os.path.join(DATA_DIR, "lead-capture-fixes.json")) or {}
    funnel = _read_json(os.path.join(DATA_DIR, "funnel-leaks.json")) or {}
    return {
        "ok": True,
        "ts": _now_iso(),
        "ideas": (ideas.get("ideas", []) if isinstance(ideas, dict) else [])[:30],
        "post_today": (ideas.get("post_today", []) if isinstance(ideas, dict) else [])[:10],
        "this_week": (ideas.get("this_week", []) if isinstance(ideas, dict) else [])[:10],
        "reels": (ideas.get("reels", []) if isinstance(ideas, dict) else [])[:10],
        "missed": (missed.get("opportunities", []) if isinstance(missed, dict) else [])[:20],
        "upsells": (upsell.get("upsells", []) if isinstance(upsell, dict) else [])[:10],
        "bundles": (bundle.get("bundles", []) if isinstance(bundle, dict) else [])[:10],
        "landing_fixes": (land.get("fixes", []) if isinstance(land, dict) else [])[:10],
        "lead_capture_fixes": (cap.get("fixes", []) if isinstance(cap, dict) else [])[:10],
        "funnel_leaks": (funnel.get("leaks", []) if isinstance(funnel, dict) else [])[:10],
    }


# ─── POSTIZ (live) ─────────────────────────────────────────────────────

def postiz_overview() -> Dict[str, Any]:
    """Live state from publishing-references.json (canonical mirror) + queue."""
    refs = _read_json(os.path.join(DATA_DIR, "publishing-references.json")) or {}
    queue = _read_json(os.path.join(DATA_DIR, "publish-queue.json")) or {}
    items = queue.get("queued", []) if isinstance(queue, dict) else []
    sched = _read_json(os.path.join(DATA_DIR, "scheduled-items.json")) or {}
    published = _read_json(os.path.join(DATA_DIR, "published-items.json")) or {}
    return {
        "ok": True,
        "ts": _now_iso(),
        "summary": (
            f"Publishing refs: {refs.get('count', 0)}. "
            f"Queue: {len(items) if isinstance(items, list) else 0}. "
            f"Scheduled: {len(sched.get('scheduled', [])) if isinstance(sched, dict) else 0}. "
            f"Published: {published.get('total', 0) if isinstance(published, dict) else 0}."
        ),
        "publishing_refs": refs if isinstance(refs, dict) else {},
        "queue": (items[:30] if isinstance(items, list) else []),
        "scheduled": (sched.get("scheduled", []) if isinstance(sched, dict) else [])[:30],
        "published": ((published.get("published", []) if isinstance(published, dict) else [])[:20]),
        "note": "Live Postiz sync runs via the truth_collector webhook. This view is the canonical mirror.",
    }


# ─── SEARCH ────────────────────────────────────────────────────────────

def universal_search(q: str, limit: int = 30) -> Dict[str, Any]:
    """Search across every data file by substring match."""
    if not q or len(q.strip()) < 2:
        return {"ok": False, "error": "Query must be at least 2 chars", "results": []}

    needle = q.strip().lower()
    results = []

    # Campaigns + assets
    cd = _campaign_data()
    for cid, c in cd.get("campaigns", {}).items():
        cname = c.get("identity", {}).get("name", cid)
        if needle in cname.lower() or needle in cid.lower():
            results.append({"kind": "campaign", "id": cid, "title": cname, "score": 100})
        for aid, asset in (c.get("assets") or {}).items():
            fields_text = " ".join(str(v) for v in [
                asset.get("name"), asset.get("caption"), asset.get("visualBrief"),
                asset.get("approvalStatus"), asset.get("publishStatus")
            ] if v).lower()
            if needle in fields_text:
                results.append({"kind": "asset", "id": aid, "campaignId": cid, "title": asset.get("name", aid), "score": 80})

    # Scan data files
    for f in _all_data_files():
        fname = os.path.basename(f).replace(".json", "")
        try:
            d = _read_json(f)
        except Exception:
            continue
        if not d:
            continue
        items = d if isinstance(d, list) else (d.get("items") or d.get("queue") or d.get("ideas") or d.get("posts") or d.get("opportunities") or d.get("faqs") or d.get("experiments") or d.get("trends") or d.get("news") or d.get("variants") or d.get("captions") or d.get("briefs") or d.get("bundles") or d.get("fixes") or [])
        if not isinstance(items, list):
            continue
        for it in items[:200]:
            if not isinstance(it, dict):
                continue
            text_blob = json.dumps(it, ensure_ascii=False).lower()
            if needle in text_blob:
                title = (
                    it.get("title") or it.get("name") or it.get("caption") or
                    it.get("hook") or it.get("headline") or it.get("cta") or
                    it.get("angle") or it.get("pain_point") or it.get("issue")
                )
                if not isinstance(title, str):
                    title = str(it)[:80]
                results.append({"kind": fname, "id": str(it.get("id") or it.get("assetId") or it.get("post_id") or ""), "title": title[:120], "score": 50})

    results.sort(key=lambda r: -(r.get("score", 0)))
    return {"ok": True, "ts": _now_iso(), "query": q, "count": len(results), "results": results[:limit]}


# ─── INSIGHTS / EXPLAIN ────────────────────────────────────────────────

def explain_performance() -> Dict[str, Any]:
    """Generate natural-language insights from performance data."""
    insights = []
    ig = _read_json(os.path.join(DATA_DIR, "ig-analytics.json")) or {}
    seo = _read_json(os.path.join(DATA_DIR, "seo-rankings.json")) or {}
    ga4 = _read_json(os.path.join(DATA_DIR, "ga4-metrics.json")) or {}
    rec = _read_json(os.path.join(DATA_DIR, "recommendation-outcomes.json")) or {}
    win = rec.get("best_recommendation") if isinstance(rec, dict) else None

    posts = ig.get("posts", []) if isinstance(ig, dict) else []

    def _er(p):
        try:
            return float(p.get("engagementRate", 0) or 0) if isinstance(p, dict) else 0
        except (ValueError, TypeError):
            return 0

    if posts:
        er_avg = sum(_er(p) for p in posts) / max(len(posts), 1)
        top = sorted([p for p in posts if isinstance(p, dict)], key=_er, reverse=True)[:3]
        for t in top:
            cap = t.get("hook_text") or t.get("captionPreview") or t.get("caption") or ""
            cap = cap[:60]
            ter = _er(t)
            if er_avg > 0 and ter > 0:
                pct = ((ter - er_avg) / er_avg * 100)
                direction = "better" if pct >= 0 else "worse"
                claim = f"\"{cap}…\" is performing {abs(pct):.0f}% {direction} than your Instagram average."
            else:
                claim = f"\"{cap}…\" is one of your top Instagram posts by engagement."
            insights.append({
                "claim": claim,
                "evidence": {"post_id": t.get("id"), "er": ter, "avg": round(er_avg, 2)},
                "kind": "ig-winner",
            })

    if isinstance(seo, dict):
        rising = seo.get("rising_keywords", []) or []
        if rising:
            insights.append({
                "claim": f"Your search visibility is climbing on: {', '.join(str(k) for k in rising[:3])}. Add supporting content to lock the gains.",
                "evidence": {"keywords": rising[:5]},
                "kind": "seo-trend-up",
            })
        falling = seo.get("falling_keywords", []) or []
        if falling:
            insights.append({
                "claim": f"Watch out: {', '.join(str(k) for k in falling[:3])} lost positions this week.",
                "evidence": {"keywords": falling[:5]},
                "kind": "seo-trend-down",
            })

    if isinstance(ga4, dict):
        s = ga4.get("total_sessions")
        if s:
            insights.append({"claim": f"Weekly sessions: {s}.", "evidence": {"ga4_sessions": s}, "kind": "traffic"})

    if isinstance(win, dict):
        insights.append({
            "claim": f"Best recommendation type right now: {win.get('type', '—')}.",
            "evidence": win,
            "kind": "best-rec",
        })

    return {"ok": True, "ts": _now_iso(), "insights": insights, "count": len(insights)}


# ─── AGENTS / HEALTH ───────────────────────────────────────────────────

def agents_view() -> Dict[str, Any]:
    runs = _read_json(os.path.join(DATA_DIR, "agent-runs.json")) or {}
    health = _read_json(os.path.join(DATA_DIR, "system-health.json")) or {}
    integration = _read_json(os.path.join(DATA_DIR, "integration-health.json")) or {}
    agents_field = runs.get("agents") if isinstance(runs, dict) else None
    out = []
    if isinstance(agents_field, list):
        out = agents_field[:30]
    elif isinstance(agents_field, dict):
        for agent_id, runs_list in list(agents_field.items())[:30]:
            last_run = runs_list[-1] if isinstance(runs_list, list) and runs_list else (runs_list if isinstance(runs_list, dict) else {})
            if isinstance(last_run, dict):
                out.append({
                    "agent_id": agent_id,
                    "runs": len(runs_list) if isinstance(runs_list, list) else 1,
                    "last_status": last_run.get("status", "—"),
                    "last_run": last_run.get("ts") or last_run.get("generated") or last_run.get("updated"),
                })
            else:
                out.append({"agent_id": agent_id, "runs": len(runs_list) if isinstance(runs_list, list) else 1})
    return {
        "ok": True,
        "ts": _now_iso(),
        "agents": out,
        "system_health": health if isinstance(health, dict) else {},
        "integration_health": integration if isinstance(integration, dict) else {},
    }


# ─── ASSETS / PORTFOLIO ────────────────────────────────────────────────

def assets_view() -> Dict[str, Any]:
    cd = _campaign_data()
    out = []
    for cid, c in cd.get("campaigns", {}).items():
        cname = c.get("identity", {}).get("name", cid)
        for aid, asset in (c.get("assets") or {}).items():
            out.append({
                "campaignId": cid,
                "campaignName": cname,
                "assetId": aid,
                "name": asset.get("name", aid),
                "kind": asset.get("kind", ""),
                "approvalStatus": asset.get("approvalStatus", ""),
                "captionStatus": asset.get("captionStatus", ""),
                "visualStatus": asset.get("visualStatus", ""),
                "publishStatus": asset.get("publishStatus", ""),
                "platform": asset.get("platform") or asset.get("integration", "instagram"),
                "updatedAt": asset.get("updatedAt"),
            })
    return {"ok": True, "ts": _now_iso(), "assets": out, "count": len(out)}


# ─── INDEX ─────────────────────────────────────────────────────────────

INTELLIGENCE_FUNCS = {
    "morning_brief": morning_brief,
    "calendar": calendar_view,
    "review_inbox": review_inbox,
    "hooks": hooks_view,
    "memes": memes_view,
    "billboards": billboards_view,
    "caption_studio": caption_studio,
    "performance": performance_view,
    "learning": learning_view,
    "hooks_generate": lambda: generate_hooks(10),
    "captions_generate": lambda: generate_captions(None, 5),
    "ctas_generate": lambda: generate_ctas(5),
    "headlines_generate": lambda: generate_headlines(5),
    "reddit_outreach": reddit_outreach,
    "gbp_suggestions": gbp_suggestions,
    "seo_assistant": seo_assistant,
    "faq_generator": faq_generator,
    "trend_catcher": trend_catcher,
    "opportunities": opportunities_view,
    "postiz": postiz_overview,
    "assets": assets_view,
    "agents": agents_view,
    "explain": explain_performance,
}