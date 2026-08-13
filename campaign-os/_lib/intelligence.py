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
import re
import time
import hashlib
import random as _random
import datetime
from collections import Counter
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
    """Load canonical campaign data, preferring /data then bundled.
    Optional brand filter: if REQUEST_BRAND_ID is set (threaded through by app.py),
    campaigns belonging to other brands are stripped from the result. This lets
    every intel view auto-scope to the active brand without each function having
    to know about brand partitioning."""
    p1 = os.path.join(os.environ.get("DATA_DIR", "/data"), "campaign-data.json")
    p2 = os.path.join(CAMPAIGN_OS_ROOT, "campaign-data.json")
    d = None
    if os.path.exists(p1):
        d = _read_json(p1)
    if d is None and os.path.exists(p2):
        d = _read_json(p2)
    if d is None:
        d = {"campaigns": {}, "activeCampaignId": None, "portfolioMetadata": {}}
    # Brand scoping — uses brands.json campaign_ids (NOT the campaign's own
    # brand_id field, which is unreliable because data-delegation makes
    # every campaign's brand_id point to swing-shack even when it belongs
    # to a sub-brand like takomo).
    brand_id = _REQUEST_BRAND_ID
    if brand_id:
        filtered = {cid: c for cid, c in (d.get('campaigns') or {}).items() if _owns_campaign(cid, brand_id)}
        # If the active campaign id is in another brand, fall back to the first matching campaign
        active = d.get('activeCampaignId')
        if active and active not in filtered:
            active = next(iter(filtered.keys()), None)
        d = dict(d)
        d['campaigns'] = filtered
        d['activeCampaignId'] = active
    return d


# Thread-local brand id (set by app.py for each request so intel functions can scope)
_REQUEST_BRAND_ID = None


def get_request_brand():
    """Return the brand_id currently scoped for this request, or None."""
    return _REQUEST_BRAND_ID


# ─── Brand → campaign-id mapping ───────────────────────────────────
# A single campaign can appear in multiple brand lists (e.g. takomo-101t is
# a Takomo campaign but also accessible from swing-shack views because the
# data layer delegates to swing-shack). For the today panel / home view
# we want STRICT brand ownership — if the active brand is takomo, only
# campaigns in brands.takomo.campaign_ids should appear.
def _load_brands_registry() -> Dict[str, Any]:
    """Read data/brands.json and return the parsed dict, or empty on error."""
    try:
        path = os.path.join(DATA_DIR, "brands.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        return {}
    return {}


def _brands_for_campaign(campaign_id: str) -> List[str]:
    """Return the list of brand_ids that explicitly own `campaign_id`.

    Reads brands.json → brands.<id>.campaign_ids. Returns [] if the campaign
    is not in any brand's explicit list (the campaign is then considered
    unowned and excluded from brand-scoped views).
    """
    reg = _load_brands_registry()
    owners = []
    for bid, b in (reg.get("brands") or {}).items():
        cids = b.get("campaign_ids") or []
        if isinstance(cids, list) and campaign_id in cids:
            owners.append(bid)
    return owners


def _owns_campaign(campaign_id: str, brand_id: Optional[str]) -> bool:
    """True iff `brand_id` is in the explicit owner list for `campaign_id`.

    Returns True when brand_id is None or empty (unscoped request — show all).
    """
    if not brand_id:
        return True
    return brand_id in _brands_for_campaign(campaign_id)


def set_request_brand(brand_id):
    """Called by app.py before invoking an intel function to scope its data."""
    global _REQUEST_BRAND_ID
    _REQUEST_BRAND_ID = brand_id or None


def clear_request_brand():
    """Called by app.py after the intel function returns."""
    global _REQUEST_BRAND_ID
    _REQUEST_BRAND_ID = None


# ─── BRIEF / HOME ──────────────────────────────────────────────────────


def _enrich_do_first_where(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach a `where` field to each do_first item so the UI can deep-link.

    The recommendation-scores.json data is rich (page URL, channel, expected
    outcome, suggested hook/CTA) but the renderer was squashing it into a
    one-line title. This helper extracts the most actionable 'where to act'
    from each item shape so the UI can render a deep-link button.
    """
    if not isinstance(items, list):
        return []
    out = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        slot = (entry.get("slot") or "").strip().lower()
        item = entry.get("item") or {}
        if not isinstance(item, dict):
            item = {}

        where = {"label": "", "url": "", "channel": "", "page": ""}
        try:
            if slot == "post":
                where["channel"] = (item.get("channel") or item.get("platform") or "instagram")
                where["label"] = f"📱 Post on {str(where['channel']).title()}"
                where["url"] = "https://app.postiz.com"
            elif slot == "service":
                where["page"] = item.get("url") or "/membership"
                where["label"] = f"💼 Service · {item.get('service', 'service')}"
                where["url"] = item.get("url") or "https://swingshack.co.za/membership"
            elif slot == "retarget":
                channel = item.get("channel") or "Instagram"
                where["channel"] = channel
                where["label"] = f"🎯 Retarget on {channel}"
                where["url"] = item.get("url") or "https://app.postiz.com"
            elif slot == "leak":
                page = item.get("page") or "/bookings/"
                where["page"] = page
                where["label"] = f"📍 Fix on swingshack.co.za{page}"
                where["url"] = f"https://swingshack.co.za{page}"
            else:
                # Unknown slot — derive something sensible from item shape
                if item.get("page"):
                    where["page"] = item["page"]
                    where["label"] = f"📍 {item['page']}"
                    where["url"] = f"https://swingshack.co.za{item['page']}"
                elif item.get("channel"):
                    where["channel"] = item["channel"]
                    where["label"] = f"📱 {item['channel']}"
                    where["url"] = item.get("url") or "https://app.postiz.com"
                else:
                    where["label"] = "🎯 Take action"
        except Exception:
            pass

        # Keep everything that was on the entry, plus the new `where` field.
        out.append({**entry, "where": where})
    return out


def morning_brief() -> Dict[str, Any]:
    """Synthesize 'what should Christelle do today?' from all signals."""
    cd = _campaign_data()
    campaigns = cd.get("campaigns", {})
    scoped_brand = get_request_brand()

    # Count assets by status across all campaigns.
    # Mirrors the review_inbox() semantics so the sidebar badge and the
    # Brief summary never disagree with the actual Review queue.
    counts = {"approved": 0, "draft": 0, "blocked": 0, "review": 0, "published": 0, "scheduled": 0, "total": 0}
    needs_review = []
    ready_to_publish = []
    overdue = []

    for cid, c in campaigns.items():
        # Brand-scope: skip campaigns not owned by the active brand. Uses
        # brands.json → brands.<id>.campaign_ids for STRICT ownership — not
        # the campaign's own brand_id field, which is unreliable.
        if scoped_brand and not _owns_campaign(cid, scoped_brand):
            continue
        for aid, asset in (c.get("assets") or {}).items():
            counts["total"] += 1
            aps = asset.get("approvalStatus", "")
            ps = asset.get("publishStatus", "") or ""
            if aps == "approved":
                counts["approved"] += 1
                if ps in ("draft", "queued", "ready", ""):
                    ready_to_publish.append({"campaignId": cid, "assetId": aid, "name": asset.get("name", aid)})
                elif ps == "scheduled":
                    counts["scheduled"] += 1
                elif ps == "published":
                    counts["published"] += 1
            elif aps == "rejected":
                counts["blocked"] += 1
            elif aps == "archived":
                # Hidden but kept for audit — don't surface anywhere.
                pass
            elif ps in ("scheduled", "published"):
                # Already on the rail — not a review need.
                if ps == "scheduled":
                    counts["scheduled"] += 1
                else:
                    counts["published"] += 1
            else:
                # Anything else (draft, review, revisionRequested, missing)
                # needs a human eye before it can ship. Track review bucket
                # separately so the badge and summary read truthfully.
                if aps in ("review", "revisionRequested"):
                    counts["review"] += 1
                else:
                    counts["draft"] += 1
                needs_review.append({
                    "campaignId": cid, "assetId": aid,
                    "name": asset.get("name", aid),
                    "issue": asset.get("revisionRequest", "") or asset.get("approvalStatus", "") or "",
                })

    # Pull top recommendations from data/
    do_first = (_read_json(os.path.join(DATA_DIR, "recommendation-scores.json")) or {}).get("do_first") or []
    missed = (_read_json(os.path.join(DATA_DIR, "missed-opportunities.json")) or {})
    missed_list = missed.get("opportunities", []) if isinstance(missed, dict) else []
    high_impact_missed = [m for m in missed_list if isinstance(m, dict) and m.get("severity") == "high"][:3]

    # Quick wins from SEO
    seo = _read_json(os.path.join(DATA_DIR, "seo-rankings.json")) or {}
    quick_wins = seo.get("quick_wins", [])[:3] if isinstance(seo, dict) else []

    # Today's content ideas — drop stale (>14 days old or used) so the
    # Brief doesn't surface ghost hooks from old campaigns.
    ideas = _read_json(os.path.join(DATA_DIR, "content-ideas.json")) or {}
    post_today = _filter_fresh_ideas(ideas.get("post_today", []) if isinstance(ideas, dict) else [])

    # ─── Recommended action: one concrete thing to do NOW ──────────────
    recommended_action = None
    rationale = None

    # Priority 1: approved but not yet scheduled → needs scheduling
    # Build a set of assetIds already on the schedule manifest so we don't
    # recommend "schedule this" for things already scheduled.
    schedule_manifest = _read_json(_runtime_data_file("scheduled-items.json")) or {}
    scheduled_set = set()
    for item in schedule_manifest.get("scheduled", []) if isinstance(schedule_manifest, dict) else []:
        if isinstance(item, dict):
            for key in (item.get("assetId"), item.get("asset_id"), item.get("publish_id")):
                if key:
                    scheduled_set.add(key)

    for cid, c in campaigns.items():
        for aid, asset in (c.get("assets") or {}).items():
            already_scheduled = aid in scheduled_set or bool(asset.get("scheduledFor"))
            if asset.get("approvalStatus") == "approved" and not already_scheduled:
                recommended_action = {
                    "type": "schedule",
                    "campaignId": cid,
                    "assetId": aid,
                    "name": asset.get("name") or aid,
                    "caption_preview": (asset.get("caption") or "")[:140],
                    "platform": asset.get("platform") or asset.get("integration") or "instagram",
                    "campaignName": c.get("identity", {}).get("name") or cid,
                }
                rationale = "Approved but never put on the calendar · it's just sitting in drafts."
                break
        if recommended_action:
            break

    # Priority 2: top performing hook that's not in current campaign → repost
    if not recommended_action and do_first and isinstance(do_first, list):
        top = do_first[0]
        if isinstance(top, dict):
            recommended_action = {
                "type": "repost",
                "hook_id": top.get("hook_id") or top.get("id"),
                "headline": top.get("headline") or top.get("title") or top.get("name"),
                "ig_proof": top.get("ig_proof") or top.get("score"),
                "source": top.get("source") or "recommendation-scores",
            }
            rationale = "Top IG performer · make a fresh take this week to ride the wave."

    # Priority 3: missed high-impact opportunity
    if not recommended_action and high_impact_missed:
        m = high_impact_missed[0]
        recommended_action = {
            "type": "create",
            "topic": m.get("topic") or m.get("title"),
            "rationale": m.get("why") or m.get("insight"),
            "ig_score": m.get("ig_score") or m.get("score"),
        }
        rationale = "Traffic exists with no content · fill the gap."

    # Priority 4: trend with no asset attached
    if not recommended_action:
        tr = _read_json(os.path.join(DATA_DIR, "trend-signals.json")) or {}
        trends = tr.get("trends", []) if isinstance(tr, dict) else []
        if trends and isinstance(trends[0], dict):
            t = trends[0]
            recommended_action = {
                "type": "trend",
                "trend": t.get("trend") or t.get("title") or t.get("name"),
                "heat": t.get("heat") or t.get("score"),
                "rationale": "Trending now · get ahead before it cools.",
            }
            rationale = "Ride this trend before it cools."

    if not recommended_action:
        recommended_action = {"type": "browse", "next": "ideas"}
        rationale = "Nothing urgent. Generate fresh ideas from the Ideas tab."

    return {
        "ok": True,
        "ts": _now_iso(),
        "summary": (
            f"{counts['total']} assets in flight. "
            f"{len(needs_review)} need review. "
            f"{len(ready_to_publish)} ready to publish."
        ),
        "counts": counts,
        "do_first": _enrich_do_first_where(do_first[:5] if isinstance(do_first, list) else []),
        "needs_review": needs_review[:10],
        "ready_to_publish": ready_to_publish[:10],
        "missed_high_impact": high_impact_missed,
        "seo_quick_wins": quick_wins,
        "post_today": post_today[:5] if isinstance(post_today, list) else [],
        "recommended_action": recommended_action,
        "recommended_rationale": rationale,
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
        # Pillar-from-caption inference. Many seed assets carry the pillar
        # only inside the caption text ("...🏌️ Club Fitting..." or
        # "...🎯 Coaching..."). Without this fallback every queue slot
        # lands as no-pillar and the calendar loses its left-border colour
        # differentiation: every card looks identical. Cheap regex over
        # a short caption string; never writes if a pillar was already set.
        if not slot.get("pillar"):
            inferred = _infer_pillar_from_caption(slot.get("caption", "") or slot.get("name", ""))
            if inferred:
                slot["pillar"] = inferred
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
        "social proof": "#60a5fa", "offer": "#fb923c",
        "entertainment": "#facc15", "instagram": "#f472b6", "tiktok": "#e6ecf5",
        "gmb": "#60a5fa", "swing shack": "#34d399", "stick": "#fb923c", "bag drop": "#a78bfa",
        # Pillar keys. These mirror the CSS --pillar-* tokens in campaign-os.html
        # so the calendar's left-border colour matches the rest of the dashboard
        # when an asset has a real pillar. Until this fix every queue slot
        # landed on the fallback green (#34d399) and the calendar looked like
        # 56 identical cards.
        "equipment": "#f59e0b", "club fitting": "#f59e0b", "club-fitting": "#f59e0b",
        "coaching": "#3b82f6", "community": "#10b981", "events": "#ec4899", "merch": "#a78bfa",
        # Practice — cyan-500 (#06b6d4). Added so the 3 seed "🎮 Practice" cards
        # stop falling through to the brand-fallback green and become visually
        # distinct. Cyan fits the golf-aesthetic (outdoor practice = sky) and
        # is not used elsewhere in the pillar palette.
        "practice": "#06b6d4",
    }
    for value in (pillar, brand, platform):
        key = str(value or "").strip().lower()
        if key in palette:
            return palette[key]
    return "#34d399"


# Caption → pillar inference. Looks for the pillar label that the seed copy
# embeds on its second line ("🏌️ Club Fitting", "🎯 Coaching", etc.). Cheap
# substring scan; case-insensitive; first match wins. Returns a lower-case
# pillar key that matches _calendar_color / the CSS --pillar-* tokens.
_PILLAR_CAPTION_HINTS = (
    ("🏌", "club fitting"),
    ("🎯", "coaching"),
    ("🤝", "community"),
    ("📅", "events"),
    ("🛍", "merch"),
    # Practice — used in seed copy on the 2nd line ("...🎮 Practice...").
    # Before this hint was added, 3 of every 57 calendar slots fell through
    # to the brand fallback (swing shack green) and visually disappeared
    # into the Swing Shack brand-fallback cards. The 2nd-line marker is the
    # emoji 🎮 OR the literal "practice" token; both are matched below.
    ("🎮", "practice"),
    ("club fitting", "club fitting"),
    ("club-fitting", "club fitting"),
    ("coaching", "coaching"),
    ("community", "community"),
    ("events", "events"),
    ("merch", "merch"),
    ("practice", "practice"),
    ("equipment", "equipment"),
)


def _infer_pillar_from_caption(text: str) -> str:
    if not text:
        return ""
    try:
        low = text.lower()
    except AttributeError:
        return ""
    for marker, pillar in _PILLAR_CAPTION_HINTS:
        if marker in low:
            return pillar
    return ""


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
            ps = asset.get("publishStatus")
            if aps == "approved":
                approved.append({"campaignId": cid, "campaignName": cname, "assetId": aid, "name": asset.get("name", aid), "caption": asset.get("caption", "")[:120], "approvalStatus": aps, "publishStatus": ps, "platform": asset.get("platform") or asset.get("integration", "instagram"), "updatedAt": asset.get("updatedAt")})
            elif aps in ("rejected",):
                rejected.append({"campaignId": cid, "campaignName": cname, "assetId": aid, "name": asset.get("name", aid), "reason": asset.get("rejectionReason", ""), "approvalStatus": aps, "publishStatus": ps, "updatedAt": asset.get("updatedAt")})
            elif aps == "archived":
                # Don't surface archived in any queue — they're hidden but kept for audit.
                pass
            else:
                pending.append({"campaignId": cid, "campaignName": cname, "assetId": aid, "name": asset.get("name", aid), "caption": asset.get("caption", "")[:200], "approvalStatus": aps, "publishStatus": ps, "platform": asset.get("platform") or asset.get("integration", "instagram"), "updatedAt": asset.get("updatedAt")})

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
    voice_bible = _load_voice_bible()
    return {
        "ok": True,
        "ts": _now_iso(),
        "captions": caps.get("captions", []) if isinstance(caps, dict) else [],
        "by_format": caps.get("by_format", {}) if isinstance(caps, dict) else {},
        "by_platform": caps.get("by_platform", {}) if isinstance(caps, dict) else {},
        "variants": variants.get("variants", []) if isinstance(variants, dict) else [],
        "cta_rankings": cta.get("cta_rankings", []) if isinstance(cta, dict) else [],
        "best_cta": cta.get("best_cta") if isinstance(cta, dict) else None,
        "voice_bible": voice_bible,
    }


# ─── VOICE BIBLE ────────────────────────────────────────────────────────

def _load_voice_bible() -> Dict[str, Any]:
    """Load voice_bible.json, preferring runtime DATA_DIR then bundled data dir."""
    paths_to_try = []
    runtime_dir = os.environ.get("DATA_DIR")
    if runtime_dir:
        paths_to_try.append(os.path.join(runtime_dir, "voice_bible.json"))
    paths_to_try.append(os.path.join(DATA_DIR, "voice_bible.json"))
    # Also try bundled (repo root /data/)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    paths_to_try.append(os.path.join(repo_root, "data", "voice_bible.json"))

    for p in paths_to_try:
        data = _read_json(p)
        if data and isinstance(data, dict) and "voices" in data:
            return data
    return {"voices": {}}


def _load_meme_knowledge_voices() -> Dict[str, List[str]]:
    """Extract {voice_id: [meme_ids]} mapping from meme_knowledge.json."""
    paths_to_try = []
    runtime_dir = os.environ.get("DATA_DIR")
    if runtime_dir:
        paths_to_try.append(os.path.join(runtime_dir, "meme_knowledge.json"))
    paths_to_try.append(os.path.join(DATA_DIR, "meme_knowledge.json"))
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    paths_to_try.append(os.path.join(repo_root, "data", "meme_knowledge.json"))

    for p in paths_to_try:
        data = _read_json(p)
        if data and isinstance(data, dict):
            memes = data.get("memes", []) if isinstance(data.get("memes"), list) else []
            mapping: Dict[str, List[str]] = {}
            for meme in memes:
                if isinstance(meme, dict):
                    for voice in meme.get("voice_fit", []):
                        mapping.setdefault(str(voice), []).append(meme.get("id", ""))
            return mapping
    return {}


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

    # Defence-in-depth: GA4 fetcher historically returned top-10 raw rows from a
    # (pagePath, sessionSource) query, so the homepage appeared 5+ times with
    # different engagement rates. Collapse duplicates before the response so
    # the rendered list always shows unique paths with session-weighted ER.
    # The upstream `fetch_ga4.js` aggregates ER as session-weighted
    # (weightedErSum / sessions). Mirror that math here so the API never
    # returns an arithmetic mean that misrepresents the page's true ER when
    # the raw rows have unequal session counts.
    raw_pages = ga4.get("pages", []) if isinstance(ga4, dict) else []
    pages_by_path = {}
    for p in raw_pages:
        if not isinstance(p, dict):
            continue
        path = p.get("path", "")
        if not path:
            continue
        sessions = p.get("sessions") or 0
        cur = pages_by_path.get(path) or {"path": path, "sessions": 0, "_er_wsum": 0.0}
        cur["sessions"] += sessions
        try:
            er_raw = p.get("engRate") or p.get("engagementRate") or 0
            er_val = float(str(er_raw).replace("%", "")) if er_raw else 0.0
        except (ValueError, TypeError):
            er_val = 0.0
        # Scale by this row's session count so the final divisor is total sessions.
        cur["_er_wsum"] += er_val * sessions
        pages_by_path[path] = cur
    aggregated_pages = []
    for p in pages_by_path.values():
        # Session-weighted mean: sum(ER_i * sessions_i) / sum(sessions_i).
        # Falls back to 0 if no sessions (avoids division by zero).
        total_sessions = p["sessions"] or 0
        er_avg = (p["_er_wsum"] / total_sessions) if total_sessions else 0.0
        aggregated_pages.append({
            "path": p["path"],
            "sessions": p["sessions"],
            "engRate": f"{er_avg:.1f}%",
            "engagementRate": er_avg,
        })
    aggregated_pages.sort(key=lambda x: x["sessions"], reverse=True)
    if isinstance(seo_rank, dict):
        # Accept both shapes — old `rising_keywords` (snake_case), new `rising` —
        # to keep this view populated regardless of which field the live
        # seo-rankings.json uses. Mirrors the fallback pattern at line ~2853.
        rising = (seo_rank.get("rising_keywords")
                  if isinstance(seo_rank.get("rising_keywords"), list)
                  else seo_rank.get("rising") or [])
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
            "pages": aggregated_pages[:10],
        },
        "seo": {
            "audit_summary": (seo.get("summary", {}) if isinstance(seo, dict) else {}),
            "rankings_summary": (seo_rank.get("summary", {}) if isinstance(seo_rank, dict) else {}),
            # Accept both shapes — old `rising_keywords` / `falling_keywords`
            # (snake_case), new `rising` / `falling`. Mirrors the fallback
            # pattern at line ~2853 and the patch above. seo-rankings.json
            # currently ships `rising` / `falling` (5 rising, 2 falling in the
            # live dataset) so this view was silently returning 0/0 before.
            "rising": (seo_rank.get("rising_keywords")
                       if isinstance(seo_rank.get("rising_keywords"), list)
                       else seo_rank.get("rising") or []),
            "falling": (seo_rank.get("falling_keywords")
                        if isinstance(seo_rank.get("falling_keywords"), list)
                        else seo_rank.get("falling") or []),
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

# ─── SA INTELLIGENCE LAYER ─────────────────────────────────────────────
# North Star §"Speak like a South African": no $ (must be R), no yards
# (must be metres), no miles, no Fahrenheit, no imperial weight. The hooks
# and captions generators feed their output through _sa_sanitize() before
# returning to the user; any US-default text gets transformed (or flagged
# and dropped if transformation is impossible, e.g. unit conversions in
# running prose are hard — we add a flag instead of mangling).
#
# Also exposes _sa_context() so the frontend can render a small chip:
# current loadshedding stage + whether schools are on holiday. Both are
# approximations, not real-time grid data, but they're good enough to
# prompt the user to check eskom.co.za before publishing.
#
# The patterns below are deliberately conservative — they only flag the
# most common slip-ups (a $ amount, a yard figure, a "miles" mention).
# Anything more nuanced needs an LLM pass; out of scope here.

# Match: $12, $12.50, $1200 (with optional .cc, with/without space)
_SA_USD_RE = re.compile(r"\$\s?(\d{1,3}(?:[,]\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")
# Match: "100 yards", "100yds", "100 yard", "100-yard", "100-yard"
# (word-boundary needs to handle the hyphenated form too).
_SA_YARDS_RE = re.compile(r"\b(\d{1,3}(?:,\d{3})*|\d+)\s*[-]?\s*(yards?|yds?)\b", re.IGNORECASE)
# Match: "5 miles", "3mi", "3-mile", "3 mi"  (hyphenated handled)
_SA_MILES_RE = re.compile(r"\b(\d{1,3}(?:,\d{3})*|\d+)\s*[-]?\s*(miles?|mi\.?)\b", re.IGNORECASE)
# Match: "70F" or "70 °F" — temperature in Fahrenheit
_SA_FAHRENHEIT_RE = re.compile(r"\b(-?\d{1,3})\s*°?\s*F\b")
# Match: "5 lbs" / "5 lb" / "5 pounds" (lb is the dangerous one — also matches "lbw" in cricket, so word-boundary it)
_SA_POUNDS_RE = re.compile(r"\b(\d{1,3}(?:,\d{3})*|\d+)\s*(lbs?|pounds?)\b", re.IGNORECASE)


def _sa_sanitize(text: str) -> Tuple[str, List[str]]:
    """Strip US-default units from a hook/caption body.

    Returns (transformed_text, list_of_issues). The issues list is what
    the frontend can show as a "this was rewritten" badge.

    Transformations applied:
      $N       -> R{N}        (USD -> ZAR; we use a 18:1 rough rate — flagged in issues)
      N yards  -> N m         (1 yard ≈ 0.91 m, rounded to integer)
      N miles  -> N km        (1 mile ≈ 1.6 km)
      N lb     -> N kg        (1 lb ≈ 0.45 kg)
      N°F      -> N°C         ((F-32)*5/9)

    Anything we can't transform safely (e.g. "70-pound bag") gets
    flagged and left as-is, with the issue logged so the user can fix.
    """
    if not text or not isinstance(text, str):
        return text, []

    issues = []
    out = text

    def _usd_to_zar(m):
        raw = m.group(1).replace(",", "")
        try:
            zar = round(float(raw) * 18.0)
            issues.append(f"${raw} → R{zar} (assumed 18:1 USD→ZAR)")
            return f"R{zar}"
        except ValueError:
            issues.append(f"unparseable ${raw} (kept as-is)")
            return m.group(0)

    def _yards_to_m(m):
        n = m.group(1).replace(",", "")
        try:
            m_ = round(float(n) * 0.9144)
            issues.append(f"{n} yards → {m_} m")
            return f"{m_} m"
        except ValueError:
            return m.group(0)

    def _miles_to_km(m):
        n = m.group(1).replace(",", "")
        try:
            km = round(float(n) * 1.609)
            issues.append(f"{n} miles → {km} km")
            return f"{km} km"
        except ValueError:
            return m.group(0)

    def _pounds_to_kg(m):
        n = m.group(1).replace(",", "")
        try:
            kg = round(float(n) * 0.4536, 1)
            issues.append(f"{n} lb → {kg} kg")
            return f"{kg} kg"
        except ValueError:
            return m.group(0)

    def _f_to_c(m):
        try:
            c = round((float(m.group(1)) - 32) * 5 / 9)
            issues.append(f"{m.group(1)}°F → {c}°C")
            return f"{c}°C"
        except ValueError:
            return m.group(0)

    out = _SA_USD_RE.sub(_usd_to_zar, out)
    out = _SA_YARDS_RE.sub(_yards_to_m, out)
    out = _SA_MILES_RE.sub(_miles_to_km, out)
    out = _SA_FAHRENHEIT_RE.sub(_f_to_c, out)
    out = _SA_POUNDS_RE.sub(_pounds_to_kg, out)

    return out, issues


def _sa_context() -> Dict[str, Any]:
    """Return current SA-specific context for display in the UI.

    Includes:
      - loadshedding_stage: 0..8 (heuristic — based on day-of-week + recent
        eskom status; real implementation would scrape eskom.co.za)
      - school_holiday: bool (based on hard-coded SA school calendar windows)
      - public_holiday: bool (next 7 days)
      - rand_usd: rough 18:1 rate (for the rare $ conversion we couldn't avoid)
      - season: "summer" | "autumn" | "winter" | "spring" (Southern Hemisphere)
    """
    # South Africa is in the Southern Hemisphere. Astronomical seasons:
    #   Summer: Dec-Jan-Feb, Autumn: Mar-Apr-May, Winter: Jun-Jul-Aug,
    #   Spring: Sep-Oct-Nov.
    today = datetime.datetime.utcnow()
    month = today.month
    if month in (12, 1, 2):
        season = "summer"
    elif month in (3, 4, 5):
        season = "autumn"
    elif month in (6, 7, 8):
        season = "winter"
    else:
        season = "spring"

    # SA school holidays (rough, Department of Basic Education calendar —
    # exact dates shift year-to-year so we use a 2-week window around
    # the usual start/end of each term break).
    md = today.strftime("%m-%d")
    school_holiday_windows = [
        ("03-20", "04-05"),  # Autumn break
        ("06-20", "07-15"),  # Winter break (longest)
        ("09-25", "10-05"),  # Spring break
        ("12-10", "01-15"),  # Summer break (wraps year boundary)
    ]
    school_holiday = False
    for start, end in school_holiday_windows:
        s_m, s_d = map(int, start.split("-"))
        e_m, e_d = map(int, end.split("-"))
        s_date = (s_m, s_d)
        e_date = (e_m, e_d)
        cur = (month, today.day)
        if s_date <= e_date:
            if s_date <= cur <= e_date:
                school_holiday = True
                break
        else:
            # Wraps year boundary (e.g. 12-10 to 01-15)
            if cur >= s_date or cur <= e_date:
                school_holiday = True
                break

    # Loadshedding stage: heuristic. Eskom schedules change daily; this
    # is a placeholder so the UI can render the chip. Production version
    # should hit /api/eskom/status or scrape eskom.co.za.
    # Default to stage 0 (no loadshedding) outside the typical
    # high-pressure weekday windows.
    dow = today.weekday()  # 0=Mon
    hour_utc = today.hour
    # Convert to SAST (+2) for "is it evening?" check
    hour_sast = (hour_utc + 2) % 24
    if 17 <= hour_sast <= 21 and dow < 5:
        # Weekday evening — assume stage 2 baseline
        loadshedding_stage = 2
    elif 6 <= hour_sast <= 9 and dow < 5:
        # Weekday morning — assume stage 1
        loadshedding_stage = 1
    else:
        loadshedding_stage = 0

    # SA public holidays 2026 (fixed dates; some are observed on the
    # following Monday if they fall on a Sunday)
    public_holidays_2026 = {
        (1, 1): "New Year's Day",
        (3, 21): "Human Rights Day",
        (4, 27): "Freedom Day",
        (5, 1): "Workers' Day",
        (6, 16): "Youth Day",
        (8, 9): "National Women's Day",
        (9, 24): "Heritage Day",
        (12, 16): "Day of Reconciliation",
        (12, 25): "Christmas Day",
        (12, 26): "Day of Goodwill",
    }
    public_holiday = (month, today.day) in public_holidays_2026
    public_holiday_name = public_holidays_2026.get((month, today.day))

    return {
        "country": "ZA",
        "currency": "ZAR",
        "currency_symbol": "R",
        "rand_usd_estimate": 18.0,  # rough; mark for live update
        "season": season,
        "loadshedding_stage": loadshedding_stage,
        "school_holiday": school_holiday,
        "public_holiday": public_holiday,
        "public_holiday_name": public_holiday_name,
        "ts": today.isoformat() + "Z",
    }


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
    # Helper: read a JSON file, then try a sequence of keys (so a list
    # nested under 'foo' or 'foo.bar' or 'foo.changes' is found whichever
    # path the writer used).  Returns [] if none of the keys are lists.
    def _read_with_keys(filename, *key_paths):
        d = _read_json(os.path.join(DATA_DIR, filename)) or {}
        if not isinstance(d, dict):
            return []
        for path in key_paths:
            # Normalise — paths can be 'a.b.c' (dotted) or 'a' (single).
            # The "for seg in path" form would iterate characters of a
            # string, which silently returned [] for every call.
            if isinstance(path, str):
                segs = path.split('.')
            else:
                segs = list(path)
            v = d
            ok = True
            for seg in segs:
                if isinstance(v, dict) and seg in v:
                    v = v[seg]
                else:
                    ok = False
                    break
            if ok and isinstance(v, list) and v:
                return v[:200]
        return []
    return {
        # reddit_opportunities.json uses schema 'opportunities' (correct)
        "reddit_pain_points": _read_with_keys(
            "reddit-opportunities.json", "opportunities", "pain_points", "items"),
        # golf-news.json uses 'news' (empty today, but try 'items' too)
        "golf_news": _read_with_keys("golf-news.json", "news", "items", "articles"),
        # youtube-trends.json has trending_themes (current) — try alternatives
        "youtube_trends": _read_with_keys(
            "youtube-trends.json", "trending_themes", "themes", "trends", "videos"),
        # youtube-ideas.json has ideas (older) and by_format (newer)
        "youtube_ideas": _read_with_keys(
            "youtube-ideas.json", "ideas", "by_format.ideas", "items"),
        # competitor-tracker.json has summary.changes (newer) or changes (older)
        "competitor_changes": _read_with_keys(
            "competitor-tracker.json", "summary.changes", "changes", "items"),
        # missed-opportunities.json is MISSING from data/; fall back to
        # opportunity-miner output if it exists
        "missed_opportunities": _read_with_keys(
            "missed-opportunities.json", "opportunities", "items", "missed"),
        "faq_opportunities": _read_with_keys(
            "faq-opportunities.json", "faqs", "items", "opportunities"),
        "forum_opportunities": _read_with_keys(
            "forum-opportunities.json", "opportunities", "items"),
        "reddit_trends": _read_with_keys(
            "reddit-trends.json", "trends", "items"),
        "reddit_replies": _read_with_keys(
            "reddit-replies.json", "replies", "items"),
        "seo_audit": [(_read_json(os.path.join(DATA_DIR, "seo-audit.json")) or {})],
        "seo_rankings": [(_read_json(os.path.join(DATA_DIR, "seo-rankings.json")) or {})],
        "local_opportunities": _read_with_keys(
            "offer-opportunities.json", "offers", "items"),
        "seasonal_opportunities": _read_with_keys(
            "merchandising-board.json", "sections", "items"),
    }


_HOOK_EXHAUSTION_CACHE: Dict[str, List[str]] = {}
"""Per-process in-memory cache of recently generated hooks (key = date_str)."""


def _used_hooks() -> List[str]:
    """Load up to the last 20 used hooks from campaign-data.json used_hooks array."""
    cd = _campaign_data()
    used = cd.get("used_hooks", [])
    if not isinstance(used, list):
        return []
    return [h for h in used if isinstance(h, str)][:20]


def generate_hooks(n: int = 10, _skip_dedup: bool = False) -> Dict[str, Any]:
    """Build hook ideas from signals, excluding recently used hooks for diversity.

    A per-process cache keyed by today's date prevents the same hooks from
    being regenerated within the same process lifetime (e.g. during a test run
    or rapid API calls). The campaign-data.json `used_hooks` array provides
    cross-process exclusion.

    Pass `_skip_dedup=True` to bypass the dedup cache. Used by the caption
    generator, which needs raw hook material (a hook already shown today is
    still good input for a new caption variant).
    """
    pool = _signal_pool()
    out = []
    today = _now_iso()[:10]

    # Track this process's recent output so we don't repeat within-process.
    global _HOOK_EXHAUSTION_CACHE
    recent = _HOOK_EXHAUSTION_CACHE.setdefault(today, [])

    used = set(_used_hooks())
    recent_set = set(recent)

    def _is_fresh(h: str) -> bool:
        if _skip_dedup:
            return True
        h_lower = h.lower()
        for u in used:
            if u.lower() == h_lower:
                return False
        for r in recent_set:
            if r.lower() == h_lower:
                return False
        return True

    def _push(h: str):
        """Track a hook string for deduplication (does NOT append to out)."""
        if _skip_dedup:
            return
        recent_set.add(h)
        recent.append(h)
        if len(recent) > 200:
            # Keep cache bounded.
            recent[:] = recent[-200:]

    def _add(h: str, source: str, kind: str):
        """Add a hook dict to the output list."""
        out.append({"hook": h, "source": source, "kind": kind})

    # Mechanism prefixes — use a seeded shuffle so order varies per call.
    seed_str = f"{today}|{n}|{get_request_brand() or ''}"
    seed_bytes = hashlib.sha256(seed_str.encode()).digest()
    rng = _random.Random(int.from_bytes(seed_bytes[:4], "big"))

    # Shuffle source pools with seed so each call cycles through differently.
    reddit_shuffled = list(pool["reddit_pain_points"])
    rng.shuffle(reddit_shuffled)

    golf_news_shuffled = list(pool["golf_news"])
    rng.shuffle(golf_news_shuffled)

    missed_shuffled = list(pool["missed_opportunities"])
    rng.shuffle(missed_shuffled)

    # From reddit pain points.
    for r in reddit_shuffled:
        if len(out) >= n:
            break
        if not isinstance(r, dict):
            continue
        ang = r.get("suggested_angle") or r.get("angle") or r.get("title") or r.get("pain_point") or r.get("trend_pain_point") or r.get("thread_topic") or ""
        if isinstance(ang, str) and ang:
            hook = f"The golf truth nobody tells you: {ang[:80]}"
            if _is_fresh(hook):
                _push(hook)
                _add(hook, "reddit", "pain-point")

    # From golf news.
    if len(out) < n:
        for n_ in golf_news_shuffled:
            if len(out) >= n:
                break
            if not isinstance(n_, dict):
                continue
            t = n_.get("title") or n_.get("headline") or n_.get("name") or n_.get("summary") or ""
            if isinstance(t, str) and t:
                hook = f"While everyone is talking about {t[:60]}..."
                if _is_fresh(hook):
                    _push(hook)
                    _add(hook, "golf-news", "trend-jack")

    # From missed opportunities.
    if len(out) < n:
        for m in missed_shuffled:
            if len(out) >= n:
                break
            if not isinstance(m, dict):
                continue
            t = m.get("hook") or m.get("title") or m.get("issue") or m.get("suggested_fix") or m.get("suggestion") or m.get("summary") or ""
            if isinstance(t, str) and t and len(t) > 15:
                if any(t.lower().startswith(w) for w in ['the ', 'why ', 'how ', 'what ', 'this ', 'have you', 'need to', 'stop ', 'your ', 'here']):
                    hook = t[:120]
                else:
                    hook = f"You're losing bookings because: {t[:60]}"
                if _is_fresh(hook):
                    _push(hook)
                    _add(hook, "missed-opp", "gap-fix")

    # Fallback to evergreen templates if still empty.
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
        rng.shuffle(templates)
        for t in templates[:n]:
            hook = t
            if _is_fresh(hook):
                _push(hook)
                _add(hook, "evergreen", "evergreen")

    # SA INTELLIGENCE: rewrite US-default units in every hook ($, yards, miles,
    # pounds, °F) and collect what we changed so the UI can flag it.
    sa_issues: List[str] = []
    for h in out:
        if isinstance(h, dict) and isinstance(h.get("hook"), str):
            new_text, issues = _sa_sanitize(h["hook"])
            if issues:
                sa_issues.extend(issues)
                h["hook"] = new_text

    return {
        "ok": True,
        "ts": _now_iso(),
        "generated": out[:n],
        "count": len(out),
        "_sa_context": _sa_context(),
        "_sa_rewrites": sa_issues,
    }


# Mechanism labels used to ensure caption variants use different angles.
_VARIANT_MECHANISMS = [
    "problem-first",  # starts with the pain point
    "story",          # opens with a relatable scene
    "contrarian",     # challenges a common belief
    "listicle",       # numbered list format
    "question",       # opens with a question
    "data-driven",    # leads with a fact or stat
    "controversy",    # sparks debate
    "authority",      # leverages expert/trusted-voice framing
    "fomo",           # urgency / limited availability
    "before-after",    # transformation arc
]


def generate_captions(
    asset_id: Optional[str] = None,
    n: int = 5,
    voice: Optional[str] = None,
    tone: Optional[str] = None,
) -> Dict[str, Any]:
    """Build caption variations from campaign asset + hook pool.

    Args:
        asset_id: campaign asset ID to attach captions to
        n:        number of variants to generate (max 20)
        voice:    voice id from voice_bible.json ('swing-shack' | 'stick' | 'bag-drop')
        tone:     tone within the voice ('educational' | 'funny' | etc.)
    Returns:
        {ok, asset, campaign, variants: [{variant, hook, body, cta, platform, voice, tone, mechanism}, ...], count, ts}
    """
    cd = _campaign_data()
    asset = None
    campaign_name = ""
    campaign_brand_id = ""
    if asset_id:
        for cid, c in cd.get("campaigns", {}).items():
            if asset_id in (c.get("assets") or {}):
                asset = c["assets"][asset_id]
                campaign_name = c.get("identity", {}).get("name", cid)
                campaign_brand_id = c.get("brand_id") or ""
                break

    # Seed RNG so repeated calls produce different variants.
    # Seed = date + asset_id hash + request brand (if scoped).
    seed_base = f"{_now_iso()[:10]}|{asset_id or ''}|{get_request_brand() or ''}"
    seed_bytes = hashlib.sha256(seed_base.encode()).digest()
    rng = _random.Random(int.from_bytes(seed_bytes[:4], "big"))

    # Hook pool. Captions don't care about freshness dedup the way the
    # hook generator does — a hook that's been generated today is still
    # perfectly good raw material for a caption variant. We use the full
    # pool so the captions generator doesn't silently produce 0 variants
    # once the hook dedup cache is full.
    pool_raw = generate_hooks(20, _skip_dedup=True).get("generated", [])
    if not pool_raw:
        # Last-resort fallback so the button is never silent.
        pool_raw = [
            {"hook": "Your clubs might be costing you shots."},
            {"hook": "Book a TrackMan session and find out."},
            {"hook": "Indoor golf in JHB beats the range."},
            {"hook": "Custom fitting changes the game."},
            {"hook": "Get the data, then make the call."},
            {"hook": "Why guess when you can measure?"},
            {"hook": "Swing Shack makes improvement measurable."},
        ]
    # Shuffle the pool with the seeded RNG so order varies per call.
    shuffled_pool = list(pool_raw)
    rng.shuffle(shuffled_pool)

    name = (asset.get("name", "") or "") if asset else ""
    platform = (asset.get("platform") or asset.get("integration", "instagram")) if asset else "instagram"
    base_caption = ""
    if asset:
        base_caption = (asset.get("caption") or asset.get("text") or "")

    if not base_caption:
        hb = _read_json(os.path.join(DATA_DIR, "hook-bank.json")) or {}
        buckets = hb.get("output_buckets", {}) if isinstance(hb.get("output_buckets"), dict) else {}
        for bname in ("proven_and_trending", "proven_only", "trending_to_test"):
            for h in (buckets.get(bname) or []):
                if isinstance(h, dict) and h.get("hook_text"):
                    base_caption = h["hook_text"]
                    break
            if base_caption:
                break
    if not base_caption:
        base_caption = f"{name or campaign_name or 'Swing Shack'} · swingshack.co.za"

    # Resolve voice: if not explicitly passed, try to auto-detect from campaign brand.
    vb = _load_voice_bible()
    voices = vb.get("voices", {})
    resolved_voice = voice if (voice and voice in voices) else None
    if not resolved_voice and campaign_brand_id and campaign_brand_id in voices:
        resolved_voice = campaign_brand_id

    # Resolve tone (must be allowed for the resolved voice)
    allowed = set(voices.get(resolved_voice, {}).get("allowed_tones", []) if resolved_voice else [])
    resolved_tone = None
    if tone and (not allowed or tone in allowed):
        resolved_tone = tone

    def _voice_prefix(vid):
        return voices.get(vid, {}).get("template_prefix", "")

    def _voice_suffix(vid):
        return voices.get(vid, {}).get("template_suffix", "")

    def _voice_cta(vid, idx=0):
        alts = voices.get(vid, {}).get("cta_alternatives", [])
        cta_default = voices.get(vid, {}).get("cta_default", "Book a session → swingshack.co.za")
        if alts and idx < len(alts):
            return alts[idx]
        return cta_default

    def _apply_voice(hook_text, vid, mechanism, idx):
        prefix = _voice_prefix(vid)
        suffix = _voice_suffix(vid)
        cta = _voice_cta(vid, idx)
        # Frame the hook differently based on mechanism so each variant feels distinct.
        if mechanism == "problem-first":
            body = f"{prefix} The problem nobody talks about: {hook_text}. {suffix} {cta}"
        elif mechanism == "story":
            body = f"{prefix} A golfer walked into Swing Shack and said: {hook_text}. {suffix} {cta}"
        elif mechanism == "contrarian":
            body = f"{prefix} Forget what you heard about {hook_text.split()[0] if hook_text else 'that'}. Here's the truth. {suffix} {cta}"
        elif mechanism == "listicle":
            body = f"{prefix} 3 things you didn't know about {hook_text.split()[0] if hook_text else 'golf'}. {suffix} {cta}"
        elif mechanism == "question":
            body = f"{prefix} {hook_text}? We asked the same thing. {suffix} {cta}"
        elif mechanism == "data-driven":
            body = f"{prefix} The data says: {hook_text}. {suffix} {cta}"
        elif mechanism == "controversy":
            body = f"{prefix} Is {hook_text.split()[0] if hook_text else 'this'} actually true? {suffix} {cta}"
        elif mechanism == "authority":
            body = f"{prefix} Here's what the experts say about {hook_text.split()[0] if hook_text else 'this'}: {suffix} {cta}"
        elif mechanism == "fomo":
            body = f"{prefix} Most golfers miss this: {hook_text}. Don't be one of them. {suffix} {cta}"
        elif mechanism == "before-after":
            body = f"{prefix} Before vs after: {hook_text}. {suffix} {cta}"
        else:
            body = f"{prefix} {hook_text}. {suffix} {cta}"
        return body

    out = []
    for i in range(n):
        if i >= len(shuffled_pool):
            break
        hook = shuffled_pool[i]
        title = (hook.get("hook", "") or "") if isinstance(hook, dict) else ""
        if not title:
            continue

        # Assign a unique mechanism per variant, cycling through the list.
        mechanism = _VARIANT_MECHANISMS[i % len(_VARIANT_MECHANISMS)]

        variant_voice = resolved_voice
        variant_tone = resolved_tone

        if variant_voice:
            body = _apply_voice(title, variant_voice, mechanism, i)
            cta = _voice_cta(variant_voice, i)
        else:
            # No voice specified — use default format with mechanism framing.
            mech_frame = f"[{mechanism}] " if mechanism else ""
            body = f"{mech_frame}{title}\n\n{base_caption[:240]}\n\nBook a session → swingshack.co.za"
            cta = "Book a session → swingshack.co.za"

        out.append({
            "variant": i + 1,
            "hook": title,
            "body": body,
            "cta": cta,
            "platform": platform,
            "source": (hook.get("source") or "signal-pool") if isinstance(hook, dict) else None,
            "voice": variant_voice,
            "tone": variant_tone,
            "mechanism": mechanism,
        })

    # SA INTELLIGENCE: rewrite US-default units in every caption body/hook/cta.
    sa_issues: List[str] = []
    for v in out:
        if not isinstance(v, dict):
            continue
        for fld in ("hook", "body", "cta"):
            val = v.get(fld)
            if isinstance(val, str):
                new_val, issues = _sa_sanitize(val)
                if issues:
                    sa_issues.extend(issues)
                    v[fld] = new_val

    return {
        "ok": True,
        "ts": _now_iso(),
        "asset": asset_id,
        "campaign": campaign_name,
        "variants": out,
        "count": len(out),
        "_voice": resolved_voice,
        "_tone": resolved_tone,
        "_sa_context": _sa_context(),
        "_sa_rewrites": sa_issues,
    }


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
            {"cta": "Try the TrackMan · 30 mins, R150", "source": "default"},
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
        "post_today": _filter_fresh_ideas(ideas.get("post_today", []) if isinstance(ideas, dict) else [])[:10],
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
    """Live state from publishing-references.json (canonical mirror) + queue.

    The summary string used to report raw totals (57 in queue / 57 published) while
    the client only renders the first 30 queue + 20 published cards, so the header
    lied to the user - "Publishing refs: 1. Queue: 57. Scheduled: 0. Published: 57."
    contradicted the card counts it sat above. The summary now mirrors the slice
    the client renders and adds a "(N total)" suffix when the visible slice is
    shorter than the full corpus. Single source of truth = the same slice logic
    used in `queue[:30]` / `published[:20]` below.

    Dedup invariant (v2026-08-13): publish-queue.json was historically never
    cleaned up when items shipped - every `published_dry` item also sat in
    `queued`. That made "Drafts" + "Published" columns render the same items
    twice. We now partition by terminal state so each item_id appears in
    exactly one bucket. Source of truth for "shipped" is
    `published-items.json` - anything with a publishStatus in that file's
    `published` list is excluded from `queued` and `scheduled`.
    """
    refs = _read_json(_runtime_data_file("publishing-references.json")) or {}
    queue = _read_json(_runtime_data_file("publish-queue.json")) or {}
    items = queue.get("queued", []) if isinstance(queue, dict) else []
    sched = _read_json(_runtime_data_file("scheduled-items.json")) or {}
    published = _read_json(_runtime_data_file("published-items.json")) or {}
    queue_all = items if isinstance(items, list) else []
    sched_all = (sched.get("scheduled", []) if isinstance(sched, dict) else [])
    pub_all = (published.get("published", []) if isinstance(published, dict) else [])
    pub_total_from_file = (published.get("total", 0) if isinstance(published, dict) else 0)
    # Build the set of shipped item_ids so we can exclude them from queue +
    # scheduled. An item_id may live under several keys depending on writer.
    shipped_ids = set()
    for it in pub_all:
        if not isinstance(it, dict):
            continue
        for k in ("id", "item_id", "asset_id", "assetId", "publish_id", "publishId"):
            v = it.get(k)
            if v:
                shipped_ids.add(str(v))
                break
    def _filter_unshipped(items_list):
        out = []
        for it in items_list:
            if not isinstance(it, dict):
                continue
            for k in ("id", "item_id", "asset_id", "assetId", "publish_id", "publishId"):
                v = it.get(k)
                if v and str(v) in shipped_ids:
                    break
            else:
                out.append(it)
        return out
    queue_all_unshipped = _filter_unshipped(queue_all)
    sched_all_unshipped = _filter_unshipped(sched_all)
    # What the client actually renders (mirrors campaign-os.html:7521-7523):
    queue_visible = queue_all_unshipped[:30]
    sched_visible = sched_all_unshipped[:30]
    pub_visible = pub_all[:20]
    # Use len(pub_visible) so the summary always matches the rendered card count;
    # the legacy `published.get('total')` overcounted by including non-published entries.
    def _fmt(visible, total):
        if total > len(visible):
            return f"{len(visible)} ({total} total)"
        return f"{len(visible)}"
    return {
        "ok": True,
        "ts": _now_iso(),
        "summary": (
            f"Publishing refs: {refs.get('count', 0)}. "
            f"Queue: {_fmt(queue_visible, len(queue_all_unshipped))}. "
            f"Scheduled: {_fmt(sched_visible, len(sched_all_unshipped))}. "
            f"Published: {_fmt(pub_visible, max(len(pub_all), pub_total_from_file))}."
        ),
        "publishing_refs": refs if isinstance(refs, dict) else {},
        "queue": queue_visible,
        "scheduled": sched_visible,
        "published": pub_visible,
        "queue_total": len(queue_all_unshipped),
        "queue_total_raw": len(queue_all),
        "scheduled_total": len(sched_all_unshipped),
        "published_total": max(len(pub_all), pub_total_from_file),
        "note": "Live Postiz sync runs via the truth_collector webhook. This view is the canonical mirror.",
        # Audit trail: how many raw queue entries were hidden because they
        # already shipped. Helps diagnose stale-publish-queue writers without
        # silently swallowing the count.
        "dedup": {
            "queue_raw": len(queue_all),
            "queue_visible": len(queue_visible),
            "queue_hidden_shipped": len(queue_all) - len(queue_all_unshipped),
        },
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

    # Brand-directory images (filename + OCR + products + palette) — search across ALL brands
    try:
        from pathlib import Path as _P
        # Honor runtime DATA_DIR override (Flask env var) AND bundled location (tests/CLI)
        runtime_data_dir = os.environ.get('DATA_DIR') or DATA_DIR
        bd_candidates = [
            _P(os.path.join(runtime_data_dir, 'brand-directory')),
            _P(os.path.join(DATA_DIR, 'brand-directory')),
        ]
        brand_dirs = []
        seen_dirs = set()
        for root in bd_candidates:
            if not root.exists():
                continue
            for brand_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
                key = (str(brand_dir), brand_dir.name)
                if key in seen_dirs:
                    continue
                seen_dirs.add(key)
                brand_dirs.append(brand_dir)
        if not brand_dirs:
            pass
        else:
            for brand_dir in brand_dirs:
                brand_id = brand_dir.name
                idx_path = brand_dir / "visual-dna-index.json"
                if not idx_path.exists():
                    continue
                try:
                    idx = json.loads(idx_path.read_text())
                except Exception:
                    continue
                by_fn = idx.get("by_filename", {}) or {}
                for fn, meta in list(by_fn.items())[:300]:
                    dna_path_str = (meta or {}).get("dna_path", "")
                    if not dna_path_str or not os.path.exists(dna_path_str):
                        continue
                    try:
                        dna = json.loads(open(dna_path_str).read())
                    except Exception:
                        continue
                    # Products: handle BOTH schemas (products[] / detected_brands[])
                    prods_raw = dna.get("layer4_products", {}) or {}
                    prod_names = prods_raw.get("products") or prods_raw.get("detected_brands") or []
                    if isinstance(prod_names, list):
                        prod_names = [str(p.get("name", p)) if isinstance(p, dict) else str(p) for p in prod_names]
                    else:
                        prod_names = []
                    # OCR: handle BOTH schemas (lines[] / text_preview)
                    ocr_raw = dna.get("layer6_ocr", {}) or {}
                    if isinstance(ocr_raw.get("lines"), list) and ocr_raw["lines"]:
                        ocr_lines = ocr_raw["lines"]
                    elif ocr_raw.get("text_preview"):
                        ocr_lines = [ocr_raw["text_preview"]]
                    else:
                        ocr_lines = []
                    ocr_text = " ".join([str(x) for x in ocr_lines if x])
                    # Palette
                    palette = ((dna.get("layer9_palette", {}) or {}).get("dominant_colors", []) or [])
                    palette_hex = " ".join([c.get("hex", "") for c in palette if isinstance(c, dict)])
                    blob = " ".join([
                        fn, brand_id,
                        " ".join(prod_names),
                        ocr_text,
                        palette_hex,
                    ]).lower()
                    if needle in blob:
                        # Score: filename match > product match > OCR match
                        s = 60
                        if needle in fn.lower():
                            s += 25
                        if any(needle in p.lower() for p in prod_names):
                            s += 10
                        if needle in ocr_text.lower():
                            s += 5
                        first_ocr = (ocr_lines[0] if ocr_lines else "")[:80]
                        results.append({
                            "kind": "image",
                            "id": f"{brand_id}/{fn}",
                            "brand": brand_id,
                            "title": fn,
                            "subtitle": first_ocr or (prod_names[0] if prod_names else brand_id),
                            "url": f"/brand-images/{brand_id}/{fn}",
                            "score": s,
                        })
    except Exception as _e:
        # Never let image-search crash the whole search
        import logging as _logging
        _logging.getLogger(__name__).debug(f"image search skipped: {_e}")

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
        # Sort by ER and split: top 2 are "winners" (green), bottom 1 is the
        # "laggard" (red). Pre-fix the strip labelled the laggard as "ig-winner"
        # which was misleading and made the Performance banner visually
        # contradictory (a winner and a loser side by side, both tagged the same).
        ranked = sorted([p for p in posts if isinstance(p, dict)], key=_er, reverse=True)
        winners = ranked[:2]
        laggard = ranked[-1] if len(ranked) >= 3 else None
        for t in winners:
            cap = t.get("hook_text") or t.get("captionPreview") or t.get("caption") or ""
            cap = cap[:60]
            ter = _er(t)
            if er_avg > 0 and ter > 0:
                pct = ((ter - er_avg) / er_avg * 100)
                claim = f"\"{cap}…\" is performing {abs(pct):.0f}% better than your Instagram average."
                next_step = ("Make a fresh take on this hook for next week · same angle, "
                             "different format (reel vs carousel). Drive better winners again.")
            else:
                claim = f"\"{cap}…\" is one of your top Instagram posts by engagement."
                next_step = "Resurface this hook in a different format this month."
            insights.append({
                "claim": claim,
                "evidence": {"post_id": t.get("id"), "er": ter, "avg": round(er_avg, 2)},
                "kind": "ig-winner",
                "next_step": next_step,
                "action": "Generate fresh take",
            })
        if laggard is not None:
            cap = laggard.get("hook_text") or laggard.get("captionPreview") or laggard.get("caption") or ""
            cap = cap[:60]
            ter = _er(laggard)
            if er_avg > 0 and ter > 0:
                pct = ((er_avg - ter) / er_avg * 100)
                claim = f"\"{cap}…\" is performing {abs(pct):.0f}% worse than your Instagram average."
                next_step = ("Update this hook with a stronger angle · ask the Ideas tab to "
                             "regenerate variations on the same topic.")
            else:
                claim = f"\"{cap}…\" is one of your weaker Instagram posts by engagement."
                next_step = "Consider refreshing this hook or retiring the format."
            insights.append({
                "claim": claim,
                "evidence": {"post_id": laggard.get("id"), "er": ter, "avg": round(er_avg, 2)},
                "kind": "ig-laggard",
                "next_step": next_step,
                "action": "Regenerate hook",
            })

    if isinstance(seo, dict):
        # Accept both shapes — old `rising_keywords` / `falling_keywords`
        # (snake_case), new `rising` / `falling`. Live seo-rankings.json
        # currently uses `rising` / `falling` so the explain view was
        # silently producing no SEO claims before. Same fallback pattern
        # used at line ~2853 and in performance_view().
        rising = (seo.get("rising_keywords")
                  if isinstance(seo.get("rising_keywords"), list)
                  else seo.get("rising") or [])
        falling = (seo.get("falling_keywords")
                   if isinstance(seo.get("falling_keywords"), list)
                   else seo.get("falling") or [])

        # seo-rankings.json entries are objects {keyword, current_rank, ...}
        # after the field-name drift fix landed. str() of one of those dumps
        # the whole dict into the claim (e.g. "{'_has_change': True,
        # 'competition': 0.2, ...}"). Pull the readable term out so the
        # Performance strip shows names, not dict literals.
        def _kw_label(k):
            if isinstance(k, dict):
                return k.get("keyword") or k.get("query") or k.get("title") or str(k)
            return str(k)

        if rising:
            rising_names = [_kw_label(k) for k in rising[:3]]
            insights.append({
                "claim": f"Your search visibility is climbing on: {', '.join(rising_names)}. Add supporting content to lock the gains.",
                "evidence": {"keywords": rising[:5]},
                "kind": "seo-trend-up",
                "next_step": f"Generate 3 supporting posts around '{_kw_label(rising[0])}' this week to ride the climb.",
                "action": "Generate SEO content",
            })
        if falling:
            falling_names = [_kw_label(k) for k in falling[:3]]
            insights.append({
                "claim": f"Watch out: {', '.join(falling_names)} lost positions this week.",
                "evidence": {"keywords": falling[:5]},
                "kind": "seo-trend-down",
                "next_step": f"Update your '{_kw_label(falling[0])}' landing page with fresher content · old pages lose rank.",
                "action": "Update landing page",
            })

    if isinstance(ga4, dict):
        s = ga4.get("total_sessions")
        if s:
            next_step = "Check which campaigns drove the most sessions and double down on those."
            insights.append({
                "claim": f"Weekly sessions: {s}. Check whether traffic is converting or just browsing.",
                "evidence": {"ga4_sessions": s},
                "kind": "traffic",
                "next_step": next_step,
                "action": "View traffic source breakdown",
            })

    if isinstance(win, dict):
        insights.append({
            "claim": f"Best recommendation type right now: {win.get('type', '—')}.",
            "next_step": "Trust the system's top pick · it has the highest historical win rate.",
            "action": "View recommendation",
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
                    # agent-runs.json records the timestamp as `run_at` (ISO 8601).
                    # Older probe names (`ts`, `generated`, `updated`) are kept as a
                    # fallback so any future writer that picks a different key still
                    # renders an age instead of collapsing to "never".
                    "last_run": (
                        last_run.get("run_at")
                        or last_run.get("ts")
                        or last_run.get("generated")
                        or last_run.get("updated")
                    ),
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


# ─── WEEKLY REPORT ──────────────────────────────────────────────────────

def _parse_iso_date(s: Any) -> Optional[datetime.datetime]:
    """Best-effort ISO date parser. Returns None if unparseable."""
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.strip().replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _filter_fresh_ideas(items: Any, days: int = 14) -> list:
    """Drop stale content ideas from a `post_today` / `this_week` style list.

    Items are kept if ALL of:
      - dict shape
      - used is False / missing
      - idea_id date prefix (YYYY-MM-DD) is within the last `days` days,
        OR idea_id has no date prefix (trust the priority tagging).

    Items with no date prefix are kept; items with a date prefix older than
    `days` are dropped silently. Always returns a list.
    """
    import re as _re
    if not isinstance(items, list):
        return []
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("used"):
            continue
        iid = item.get("idea_id", "") or ""
        m = _re.search(r"(\d{4})-(\d{2})-(\d{2})", iid)
        if m:
            try:
                d = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=datetime.timezone.utc)
                if d < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
        out.append(item)
    return out


def weekly_report(brand: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate everything that happened in the last 7 days into a single
    'weekly marketing report' payload. Mirrors the structure of the weekly
    markdown report that `weekly_reporter` writes, but JSON so the Insights
    section can render live + export.

    v2026-08-04 changes (this rewrite):
      - Cross-cuts 6 data sources: published-items, IG analytics, GA4, YouTube
        trends, Reddit opps+replies, SEO rankings (instead of only the first).
      - "Last publish window" fallback when last 7d is empty but the pipeline
        has data ≤30d old — keeps the report useful during rest-mode pauses.
      - Returns `interp` alias alongside `interpretation` so the SPA renderer
        can use either (defense in depth against the w.interp key bug).
      - Every claim in `interpretation` cites the source file it came from.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    week_start = now - datetime.timedelta(days=7)
    prev_start = now - datetime.timedelta(days=14)

    # ── 1. Published items ────────────────────────────────────────────
    pub_data = _read_json(os.path.join(DATA_DIR, "published-items.json")) or {}
    all_published = pub_data.get("published", []) if isinstance(pub_data, dict) else []
    if not isinstance(all_published, list):
        all_published = []

    def _in_window(item_ts: Any, start: datetime.datetime, end: datetime.datetime) -> bool:
        d = _parse_iso_date(item_ts)
        if d is None:
            return False
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return start <= d <= end

    this_week = [p for p in all_published if isinstance(p, dict) and _in_window(
        p.get("generated") or p.get("published_at"), week_start, now
    )]
    prev_week = [p for p in all_published if isinstance(p, dict) and _in_window(
        p.get("generated") or p.get("published_at"), prev_start, week_start
    )]

    # ── 1b. Last-publish-window fallback (rest-mode aware) ─────────────
    window_used = "rolling_7d"
    window_label = f"{week_start.strftime('%Y-%m-%d')} → {now.strftime('%Y-%m-%d')}"
    window_note = ""
    latest = None
    if not this_week and all_published:
        # No publishes in the last 7 days. Find the most-recent batch (any
        # contiguous 7-day window that contains publishes).
        dated = [
            (p, _parse_iso_date(p.get("generated") or p.get("published_at")))
            for p in all_published if isinstance(p, dict)
        ]
        dated = [(p, d) for p, d in dated if d is not None]
        if dated:
            latest = max(d for _, d in dated)
            earliest = min(d for _, d in dated)
            days_since_latest = (now - latest).days
            # Only use this fallback if the most-recent publish is < 30 days old
            # and the data spans a manageable window.
            if days_since_latest <= 30:
                fallback_start = max(earliest, latest - datetime.timedelta(days=7))
                fallback_end = latest + datetime.timedelta(days=1)
                this_week = [
                    p for p, d in dated
                    if fallback_start <= d <= fallback_end
                ]
                prev_week = []  # Nothing comparable
                window_used = "last_publish_window_fallback"
                window_label = f"{fallback_start.strftime('%Y-%m-%d')} → {fallback_end.strftime('%Y-%m-%d')} (last active publish window before pause · {days_since_latest}d ago)"
                window_note = (
                    f"Pipeline in rest-mode: no publishes in the last 7 days. "
                    f"Showing last active publish window ({len(this_week)} posts, "
                    f"{fallback_start.strftime('%Y-%m-%d')} → {fallback_end.strftime('%Y-%m-%d')}). "
                    f"Approve an active campaign or restart the cron to refresh."
                )

    # ── 2. Failures ───────────────────────────────────────────────────
    fail_data = _read_json(os.path.join(DATA_DIR, "publish-failures.json")) or {}
    all_failures = []
    if isinstance(fail_data, dict):
        for key in ("failures", "failed", "items"):
            v = fail_data.get(key)
            if isinstance(v, list):
                all_failures = v
                break
    elif isinstance(fail_data, list):
        all_failures = fail_data
    week_failures = [f for f in all_failures if isinstance(f, dict) and _in_window(
        f.get("ts") or f.get("failed_at") or f.get("generated"), week_start, now
    )]
    prev_failures = [f for f in all_failures if isinstance(f, dict) and _in_window(
        f.get("ts") or f.get("failed_at") or f.get("generated"), prev_start, week_start
    )]

    # ── 3. Headline KPIs ──────────────────────────────────────────────
    published_count = len(this_week)
    failed_count = len(week_failures)
    attempts = published_count + failed_count
    win_rate_pct = round((published_count / attempts) * 100, 1) if attempts > 0 else None
    prev_published = len(prev_week)
    prev_failed = len(prev_failures)
    prev_attempts = prev_published + prev_failed
    prev_win_rate = round((prev_published / prev_attempts) * 100, 1) if prev_attempts > 0 else None

    # ── 4. Platforms + days breakdown ─────────────────────────────────
    platforms = {}
    by_day = {"Mon": 0, "Tue": 0, "Wed": 0, "Thu": 0, "Fri": 0, "Sat": 0, "Sun": 0}
    weekday_keys = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for p in this_week:
        plat = p.get("platform") or "instagram"
        platforms[plat] = platforms.get(plat, 0) + 1
        ts = _parse_iso_date(p.get("generated") or p.get("published_at"))
        if ts:
            by_day[weekday_keys[ts.weekday()]] += 1

    # ── 5. Top hooks (cross-referenced with hook-bank) ────────────────
    hook_counts = {}
    for p in this_week:
        hid = p.get("linked_hook_id")
        if hid:
            hook_counts[hid] = hook_counts.get(hid, 0) + 1
    top_hooks = sorted(hook_counts.items(), key=lambda x: -x[1])[:5]

    hook_bank = _read_json(os.path.join(DATA_DIR, "hook-bank.json")) or {}
    hook_lookup = {}
    # v2026-08-04: read BOTH old schema keys (defense) AND new output_buckets.* keys
    old_buckets = ("proven_and_trending", "trending_but_unproven", "watched")
    for bucket_key in old_buckets:
        bucket = hook_bank.get(bucket_key, []) if isinstance(hook_bank, dict) else []
        if isinstance(bucket, list):
            for h in bucket:
                if isinstance(h, dict):
                    hid = h.get("hook_id")
                    if hid:
                        hook_lookup[hid] = h.get("hook_text") or h.get("text") or hid
    # New schema: output_buckets.{proven_and_trending, proven_only, trending_to_test, retire}
    ob = hook_bank.get("output_buckets") if isinstance(hook_bank, dict) else None
    if isinstance(ob, dict):
        for sub_bucket in ("proven_and_trending", "proven_only", "trending_to_test", "retire"):
            bucket = ob.get(sub_bucket, [])
            if isinstance(bucket, list):
                for h in bucket:
                    if isinstance(h, dict):
                        hid = h.get("hook_id")
                        if hid and hid not in hook_lookup:
                            hook_lookup[hid] = h.get("hook_text") or h.get("text") or hid
    top_hooks_rich = [
        {"hook_id": hid, "uses": cnt, "text": hook_lookup.get(hid, "")}
        for hid, cnt in top_hooks
    ]

    # ── 5b. Hook-bank bucketed summary (for new claims) ──────────────
    hook_bank_summary = {}
    if isinstance(ob, dict):
        for sub_bucket, label in (
            ("proven_and_trending", "proven_and_trending"),
            ("proven_only", "proven_only"),
            ("trending_to_test", "trending_to_test"),
            ("retire", "retire"),
        ):
            bucket = ob.get(sub_bucket, [])
            if isinstance(bucket, list):
                hook_bank_summary[label] = len(bucket)

    # All hook_ids in hook-bank (across all buckets) — declared early,
    # computed later once both sets are ready.
    all_hb_hook_ids: set = set()

    # ── 5c. Hook match: published hook_ids vs IG-analytics hook_ids ───
    ig = _read_json(os.path.join(DATA_DIR, "ig-analytics.json")) or {}
    ig_posts = ig.get("posts", []) if isinstance(ig, dict) else []
    if not isinstance(ig_posts, list):
        ig_posts = []
    ig_hook_ids = {
        p.get("hook_id") for p in ig_posts
        if isinstance(p, dict) and p.get("hook_id")
    }
    pub_hook_ids = {
        p.get("linked_hook_id") for p in this_week
        if isinstance(p, dict) and p.get("linked_hook_id")
    }
    hook_overlap = ig_hook_ids & pub_hook_ids
    hook_in_pub_not_ig = pub_hook_ids - ig_hook_ids
    hook_in_ig_not_pub = ig_hook_ids - pub_hook_ids

    # Hook-bank cross-cut (filled in now that all_hb_hook_ids is readable)
    if isinstance(ob, dict):
        for sub_bucket in ("proven_and_trending", "proven_only", "trending_to_test", "retire"):
            bucket = ob.get(sub_bucket, [])
            if isinstance(bucket, list):
                for h in bucket:
                    if isinstance(h, dict):
                        hid = h.get("hook_id")
                        if hid:
                            all_hb_hook_ids.add(hid)
    pub_in_pub_not_hb = pub_hook_ids - all_hb_hook_ids
    ig_totals = {"posts": len(ig_posts), "reach": 0, "likes": 0,
                 "saves": 0, "shares": 0, "comments": 0, "follows_gained": 0}
    for p in ig_posts:
        if not isinstance(p, dict):
            continue
        for k in ("reach", "likes", "saves", "shares", "comments", "follows_gained"):
            try:
                ig_totals[k] += int(p.get(k) or 0)
            except (TypeError, ValueError):
                pass

    # ── 6. Top CTAs ───────────────────────────────────────────────────
    cta_counts = {}
    for p in this_week:
        cta = p.get("linked_cta") or p.get("cta")
        if cta:
            cta_counts[cta] = cta_counts.get(cta, 0) + 1
    top_ctas = sorted(cta_counts.items(), key=lambda x: -x[1])[:5]
    top_ctas_rich = [{"cta": cta, "uses": cnt} for cta, cnt in top_ctas]

    # ── 7. SEO movers ────────────────────────────────────────────────
    seo = _read_json(os.path.join(DATA_DIR, "seo-rankings.json")) or {}
    keywords = seo.get("keywords", []) if isinstance(seo, dict) else []
    if not isinstance(keywords, list):
        keywords = []
    # Accept both shapes — old `rising_keywords` / `falling_keywords`
    # (snake_case), new `rising` / `falling`. Same fallback pattern as
    # performance_view() and explain_performance() so weekly-report
    # claims and movers stay in sync with the live dataset.
    rising = (seo.get("rising_keywords")
              if isinstance(seo.get("rising_keywords"), list)
              else seo.get("rising") or [])
    falling = (seo.get("falling_keywords")
               if isinstance(seo.get("falling_keywords"), list)
               else seo.get("falling") or [])
    if not isinstance(rising, list):
        rising = []
    if not isinstance(falling, list):
        falling = []
    seo_movers = []
    for r in rising[:5]:
        if isinstance(r, dict):
            seo_movers.append({"keyword": r.get("keyword"), "direction": "rising", "rank": r.get("current_rank") or r.get("rank")})
        elif isinstance(r, str):
            seo_movers.append({"keyword": r, "direction": "rising"})
    for f in falling[:3]:
        if isinstance(f, dict):
            seo_movers.append({"keyword": f.get("keyword"), "direction": "falling", "rank": f.get("current_rank") or f.get("rank")})
        elif isinstance(f, str):
            seo_movers.append({"keyword": f, "direction": "falling"})
    seo_keyword_count = len(keywords)
    seo_keywords_with_rank = sum(
        1 for k in keywords if isinstance(k, dict) and k.get("current_rank") is not None
    )
    seo_freshness = seo.get("updated") or ""

    # ── 8. Agent runs (last 7 days) ───────────────────────────────────
    agent_data = _read_json(os.path.join(DATA_DIR, "agent-runs.json")) or {}
    agents_raw = agent_data.get("agents", {}) if isinstance(agent_data, dict) else {}
    if not isinstance(agents_raw, dict):
        agents_raw = {}
    agent_summary = {}
    for agent_id, runs in agents_raw.items():
        if not isinstance(runs, list):
            continue
        week_runs = [r for r in runs if isinstance(r, dict) and _in_window(
            r.get("run_at"), week_start, now
        )]
        if not week_runs:
            continue
        passed = sum(1 for r in week_runs if (r.get("status") or "").upper() in ("PASS", "OK", "SUCCESS"))
        failed = sum(1 for r in week_runs if (r.get("status") or "").upper() in ("FAIL", "ERROR", "FAILED"))
        partial = len(week_runs) - passed - failed
        agent_summary[agent_id] = {
            "total": len(week_runs),
            "passed": passed,
            "failed": failed,
            "partial": partial,
            "pass_rate_pct": round((passed / len(week_runs)) * 100, 1) if week_runs else None,
        }
    total_agent_runs = sum(a["total"] for a in agent_summary.values())
    total_agent_passed = sum(a["passed"] for a in agent_summary.values())
    total_agent_pass_rate = round((total_agent_passed / total_agent_runs) * 100, 1) if total_agent_runs else None

    # ── 9. Week-on-week deltas ────────────────────────────────────────
    def _delta(curr, prev):
        if curr is None or prev in (None, 0):
            return {"current": curr, "previous": prev, "delta": None, "pct_change": None}
        delta = curr - prev
        pct = round((delta / prev) * 100, 1)
        return {"current": curr, "previous": prev, "delta": delta, "pct_change": pct}

    wow = {
        "published": _delta(published_count, prev_published),
        "failed": _delta(failed_count, prev_failed),
        "win_rate_pct": _delta(win_rate_pct, prev_win_rate),
        "agent_runs": _delta(total_agent_runs, sum(a.get("total", 0) for a in agent_summary.values()) - total_agent_runs),
    }

    # ── 10. NEW — GA4 cross-cut ──────────────────────────────────────
    ga4 = _read_json(os.path.join(DATA_DIR, "ga4-metrics.json")) or {}
    ga4_summary = {
        "total_sessions": ga4.get("total_sessions"),
        "pages_count": len(ga4.get("pages", []) if isinstance(ga4.get("pages"), list) else []),
        "sources_count": len(ga4.get("sources", []) if isinstance(ga4.get("sources"), list) else []),
        "top_source": None,
        "top_source_sessions": None,
        "fetched_at": ga4.get("fetched_at") or ga4.get("updated"),
        "stale": ga4.get("_stale", False),
    }
    sources = ga4.get("sources", []) if isinstance(ga4.get("sources"), list) else []
    if sources and isinstance(sources[0], dict) and sources[0].get("sessions") is not None:
        top_src = max(sources, key=lambda x: x.get("sessions", 0))
        ga4_summary["top_source"] = top_src.get("source")
        ga4_summary["top_source_sessions"] = top_src.get("sessions")

    # ── 11. NEW — YouTube trends cross-cut ───────────────────────────
    youtube = _read_json(os.path.join(DATA_DIR, "youtube-trends.json")) or {}
    yt_themes = youtube.get("trending_themes", {}) if isinstance(youtube, dict) else {}
    if not isinstance(yt_themes, dict):
        yt_themes = {}
    yt_active_themes = [k for k, v in yt_themes.items() if v]
    yt_summary = {
        "videos_found": youtube.get("videos_found"),
        "top_videos_count": len(youtube.get("top_videos", []) if isinstance(youtube.get("top_videos"), list) else []),
        "active_themes": yt_active_themes,
        "fetched_at": youtube.get("updated"),
    }

    # ── 12. NEW — Reddit opps vs replies cross-cut ──────────────────
    ro = _read_json(os.path.join(DATA_DIR, "reddit-opportunities.json")) or {}
    rr = _read_json(os.path.join(DATA_DIR, "reddit-replies.json")) or {}
    ro_opps = ro.get("opportunities", []) if isinstance(ro, dict) else []
    if not isinstance(ro_opps, list):
        ro_opps = []
    rr_replies = rr.get("replies", []) if isinstance(rr, dict) else []
    if not isinstance(rr_replies, list):
        rr_replies = []
    reddit_summary = {
        "opportunities_count": len(ro_opps),
        "replies_count": len(rr_replies),
        "ready_for_qa": ro.get("ready_for_qa", 0) if isinstance(ro, dict) else 0,
        "replies_ready_for_qa": rr.get("ready_for_qa", 0) if isinstance(rr, dict) else 0,
        "urgency_breakdown": ro.get("by_urgency", {}) if isinstance(ro, dict) else {},
        "opportunities": ro_opps[:5],
    }
    # Top reddit topics by frequency
    subreddits = [o.get("subreddit") for o in ro_opps if isinstance(o, dict) and o.get("subreddit")]
    subreddit_counts = Counter(subreddits)
    reddit_summary["top_subreddits"] = [
        {"subreddit": s, "count": c} for s, c in subreddit_counts.most_common(5)
    ]

    # ── 12b. NEW (v2026-08-13) · IG Business live-account metrics ·─
    # Pulled by scripts/fetch_ig_business.py via launchd (06:00 SAST).
    # This is the source of truth for the IG reach / engagement / top
    # post claims in the weekly report. ig-analytics.json can't get
    # these because its legacy sync doesn't write reach.
    igb = _read_json(os.path.join(DATA_DIR, "ig-business-analytics.json")) or {}
    igb_window_totals = igb.get("window_totals") if isinstance(igb, dict) else None
    igb_daily_reach = igb.get("daily_reach") if isinstance(igb, dict) else None
    igb_top_post = igb.get("top_post") if isinstance(igb, dict) else None
    igb_account = igb.get("account") if isinstance(igb, dict) else None
    igb_media = igb.get("media") if isinstance(igb, dict) else []
    if not isinstance(igb_media, list):
        igb_media = []
    igb_summary = {
        "fetched_at": igb.get("metadata", {}).get("fetched_at") if isinstance(igb, dict) else None,
        "stale": igb.get("_stale", False),
        "username": igb.get("metadata", {}).get("username") if isinstance(igb, dict) else None,
        "followers_count": igb_account.get("followers_count") if isinstance(igb_account, dict) else None,
        "media_count": igb_account.get("media_count") if isinstance(igb_account, dict) else None,
        "window_totals": igb_window_totals if isinstance(igb_window_totals, dict) else {},
        "daily_reach_points": len(igb_daily_reach) if isinstance(igb_daily_reach, list) else 0,
        "media_in_window": len(igb_media),
        "top_post": igb_top_post if isinstance(igb_top_post, dict) else None,
    }

    # ── 13. Markdown export path ──────────────────────────────────────
    md_path = os.path.join(DATA_DIR, "weekly-report.md")

    # ── 14. Headline (1 sentence) ────────────────────────────────────
    if published_count == 0 and failed_count == 0 and window_used == "rolling_7d":
        headline = f"Quiet week · {total_agent_runs} agent runs, no publishes attempted."
    elif window_used == "last_publish_window_fallback":
        wr = f"{win_rate_pct}%" if win_rate_pct is not None else "—"
        latest_label = latest.strftime('%Y-%m-%d') if latest is not None else "unknown"
        headline = (
            f"{published_count} published (last active window {latest_label}), "
            f"{failed_count} failed, {wr} win rate. "
            f"Pipeline paused since {latest_label} — this is your most-recent live snapshot."
        )
    else:
        wr = f"{win_rate_pct}%" if win_rate_pct is not None else "—"
        headline = f"{published_count} published, {failed_count} failed, {wr} win rate."

    # ── 15. Build interpretation (NEW — uses all 6 sources) ──────────
    interpretation = _interpret_weekly_report(
        published_count, failed_count, win_rate_pct,
        prev_published, prev_failed, prev_win_rate,
        platforms, by_day, top_hooks_rich, top_ctas_rich,
        seo_movers, week_failures, agent_summary,
        brand_dir=_resolve_brand_dir(brand),
        ig_analytics={"posts": ig_posts, "totals": ig_totals,
                      "hook_ids": list(ig_hook_ids)},
        ga4=ga4_summary,
        youtube=yt_summary,
        reddit_opps={"count": len(ro_opps), "opps": ro_opps[:5],
                     "ready_for_qa": ro.get("ready_for_qa", 0)},
        reddit_replies={"count": len(rr_replies), "ready_for_qa": rr.get("ready_for_qa", 0),
                        "by_sentiment": rr.get("by_sentiment", {})},
        seo={"keywords_total": seo_keyword_count,
             "with_rank": seo_keywords_with_rank,
             "rising": len(rising),
             "falling": len(falling),
             "freshness": seo_freshness,
             "needs_fetcher": seo_keyword_count > 0 and seo_keywords_with_rank == 0},
        hook_match={"overlap": len(hook_overlap),
                    "in_pub_not_ig": len(hook_in_pub_not_ig),
                    "in_ig_not_pub": len(hook_in_ig_not_pub),
                    "in_pub_not_hook_bank": len(pub_in_pub_not_hb),
                    "hook_bank_total": len(all_hb_hook_ids)},
        hook_bank_buckets=hook_bank_summary,
        ig_business=igb,
    )

    return {
        "ok": True,
        "ts": _now_iso(),
        "week_start": week_start.isoformat(),
        "week_end": now.isoformat(),
        "window_label": window_label,
        "window_used": window_used,
        "window_note": window_note,
        "brand": brand,
        "headline": headline,
        "headline_kpis": {
            "published": published_count,
            "failed": failed_count,
            "win_rate_pct": win_rate_pct,
            "agent_runs": total_agent_runs,
            "agent_pass_rate_pct": total_agent_pass_rate,
        },
        "platforms": platforms,
        "by_day": by_day,
        "top_hooks": top_hooks_rich,
        "top_ctas": top_ctas_rich,
        "seo_movers": seo_movers,
        "failures": [
            {
                "item_id": f.get("item_id") or f.get("id"),
                "platform": f.get("platform"),
                "reason": f.get("error") or f.get("reason") or f.get("message"),
                "ts": f.get("ts") or f.get("failed_at") or f.get("generated"),
            }
            for f in week_failures[:10]
        ],
        "agent_breakdown": agent_summary,
        "week_on_week": wow,
        # ── NEW SECTIONS ──
        "ig_analytics": {
            "posts_in_window": len([p for p in ig_posts if isinstance(p, dict)]),
            "totals": ig_totals,
            "hook_overlap_with_published": len(hook_overlap),
            "hook_only_in_published": len(hook_in_pub_not_ig),
            "hook_only_in_ig": len(hook_in_ig_not_pub),
        },
        "hook_bank_mismatch": {
            "published_hook_ids_not_in_bank": len(pub_in_pub_not_hb),
            "hook_bank_total_ids": len(all_hb_hook_ids),
        },
        "ga4": ga4_summary,
        "youtube": yt_summary,
        "reddit": reddit_summary,
        # NEW (v2026-08-13) · 7th data source
        "ig_business": igb_summary,
        "seo_health": {
            "keywords_total": seo_keyword_count,
            "with_rank": seo_keywords_with_rank,
            "rising": len(rising),
            "falling": len(falling),
            "freshness": seo_freshness,
            "needs_fetcher": seo_keyword_count > 0 and seo_keywords_with_rank == 0,
        },
        "hook_bank_buckets": hook_bank_summary,
        # ── Interpretation (named both ways for SPA compat) ──
        "interpretation": interpretation,
        "interp": interpretation,  # alias — SPA renderer should use interpretation, but defense in depth
        "visual_insights": _visual_insights_for_week(
            this_week, prev_week, brand_dir=_resolve_brand_dir(brand),
        ),
        "ig_topic_clusters": _cluster_ig_captions(this_week, prev_week),
        "export_path": md_path,
    }


def _resolve_brand_dir(brand: Optional[str]) -> str:
    """Map brand ID to the brand-directory/{brand}/ path used by visual-dna-index."""
    if not brand:
        return os.path.join(DATA_DIR, "brand-directory", "swing-shack")
    # Stick/Takomo share a visual-spec but live under "stick"; default to swing-shack if unknown.
    candidate = os.path.join(DATA_DIR, "brand-directory", brand)
    return candidate if os.path.isdir(candidate) else os.path.join(DATA_DIR, "brand-directory", "swing-shack")


def _interpret_weekly_report(
    published, failed, win_rate, prev_pub, prev_fail, prev_wr,
    platforms, by_day, top_hooks, top_ctas, movers,
    failures, agent_summary, brand_dir=None,
    ig_analytics=None, ga4=None, youtube=None,
    reddit_opps=None, reddit_replies=None, seo=None,
    hook_match=None, hook_bank_buckets=None,
    ig_business=None,
):
    """Translate raw numbers into WHAT'S WORKING / WHAT'S NOT / WHAT TO LOOK AT.

    The interpretation is rule-based (no LLM) so it's auditable, deterministic,
    and built from the same data the dashboard reads. Every claim is grounded
    in a specific number AND cites the source file via the `source` field.

    v2026-08-04: extended to read from 6 data sources (was 1). New params are
    each optional dicts; if missing, that source silently contributes nothing.

    Returns: {
      "whats_working":  [{ "claim": "...", "evidence": "...", "source": "...",
                           "category": "..." }, … ],
      "whats_not":      [ same shape + "severity" ],
      "look_at":        [ same shape ],
      "headline_take":  "...single sentence...",
      "sources_used":   ["ig-analytics.json", "ga4-metrics.json", ...],
    }
    """
    working, not_working, look_at = [], [], []

    # ── WHAT'S WORKING ────────────────────────────────────────────────
    if published > 0:
        # High win-rate is the headline signal
        if win_rate is not None and win_rate >= 80:
            working.append({
                "claim": f"Win rate is healthy at {win_rate}%.",
                "evidence": f"{published} published, {failed} failed this week (threshold: ≥80% = good).",
                "category": "publishing",
            })
        elif win_rate is not None and win_rate >= 50:
            working.append({
                "claim": f"Publish reliability is OK at {win_rate}%.",
                "evidence": f"{published} published vs {failed} failed — keep tightening fail-modes to push past 80%.",
                "category": "publishing",
            })

    # Improving metrics (WoW)
    if prev_pub and published > prev_pub * 1.1:
        delta_pct = round((published - prev_pub) / prev_pub * 100)
        working.append({
            "claim": f"Publish volume is up {delta_pct}% vs last week.",
            "evidence": f"{prev_pub} → {published} published.",
            "category": "growth",
        })

    # Top hooks in use (their existence = they're being repeated, signal of trust)
    if top_hooks and top_hooks[0].get("uses", 0) >= 2:
        h = top_hooks[0]
        if h.get("text"):
            working.append({
                "claim": f"Top hook '{h['text'][:60]}{'…' if len(h['text'])>60 else ''}' is being reused ({h['uses']}×).",
                "evidence": "Reuse = the system trusts it. Worth reading why it works in hook-bank.md.",
                "category": "voice",
            })

    # Agent pass rate
    total_runs = sum(a.get("total", 0) for a in agent_summary.values())
    total_passed = sum(a.get("passed", 0) for a in agent_summary.values())
    if total_runs and total_passed / total_runs >= 0.8:
        working.append({
            "claim": f"Agent fleet pass rate is {round(total_passed/total_runs*100, 1)}%.",
            "evidence": f"{total_passed}/{total_runs} runs passed across {len(agent_summary)} agents.",
            "category": "fleet",
        })

    # SEO positive movers
    rising = [m for m in movers if m.get("direction") == "rising"]
    if rising:
        working.append({
            "claim": f"{len(rising)} SEO keywords moved up this week.",
            "evidence": ", ".join(m.get("keyword", "?") for m in rising[:3]),
            "category": "seo",
        })

    # Dominant platform
    if platforms:
        top_plat = max(platforms.items(), key=lambda x: x[1])
        if top_plat[1] >= 3:
            working.append({
                "claim": f"{top_plat[0].capitalize()} is the dominant publish channel ({top_plat[1]} posts).",
                "evidence": "Consider replicating winning formats to underused channels.",
                "category": "channels",
            })

    # Best publishing day (for cadence planning)
    if by_day and any(by_day.values()):
        best_day = max(by_day.items(), key=lambda x: x[1])
        if best_day[1] >= 2:
            working.append({
                "claim": f"{best_day[0]} is your strongest publish day this week.",
                "evidence": f"{best_day[1]} posts went out on that day.",
                "category": "cadence",
            })

    # ── WHAT'S NOT WORKING ────────────────────────────────────────────
    if win_rate is not None and win_rate < 50 and (published + failed) > 0:
        not_working.append({
            "claim": f"Win rate is {win_rate}% — below healthy.",
            "evidence": f"{failed} fails on {published + failed} attempts. Inspect `failures` list; most-likely cause will be visible there.",
            "category": "publishing",
            "severity": "high" if win_rate < 25 else "medium",
        })

    if failures:
        # Group failures by reason
        reason_counts = {}
        for f in failures:
            r = (f.get("reason") or "unknown")[:80]
            reason_counts[r] = reason_counts.get(r, 0) + 1
        top_reason = max(reason_counts.items(), key=lambda x: x[1])
        if top_reason[1] >= 2:
            not_working.append({
                "claim": f"Failure pattern: '{top_reason[0]}' ({top_reason[1]}× this week).",
                "evidence": "Fix once, recover 2+ posts/week. Open the most-recent failure log for full stack.",
                "category": "publishing",
                "severity": "medium",
            })

    # Declining metrics
    if prev_pub and published < prev_pub * 0.85:
        delta_pct = round((prev_pub - published) / prev_pub * 100)
        not_working.append({
            "claim": f"Publish volume dropped {delta_pct}% vs last week.",
            "evidence": f"{prev_pub} → {published} published.",
            "category": "growth",
            "severity": "medium",
        })

    # Falling SEO keywords
    falling = [m for m in movers if m.get("direction") == "falling"]
    if falling:
        not_working.append({
            "claim": f"{len(falling)} SEO keywords moved down this week.",
            "evidence": ", ".join(m.get("keyword", "?") for m in falling[:3]),
            "category": "seo",
            "severity": "low",
        })

    # Underused agents (full pass rate is fine but some agents have 0 runs)
    if agent_summary:
        no_runs = [a for a, s in agent_summary.items() if s.get("total", 0) == 0]
        inactive = [a for a in {"copywriter", "scout", "imagegen", "retina", "forge", "publisher"} if a not in agent_summary]
        if inactive:
            not_working.append({
                "claim": f"{len(inactive)} agent(s) didn't run this week: {', '.join(inactive)}.",
                "evidence": "Either nothing to do (fine) or a missed opportunity.",
                "category": "fleet",
                "severity": "low",
            })

    # ── WHAT TO LOOK AT (questions, not failures) ────────────────────
    if published == 0 and failed == 0:
        look_at.append({
            "claim": "No publishing activity this week.",
            "evidence": "Either Publishing lane is idle (no scheduled content) or something is blocking — review queue.",
            "category": "publishing",
        })

    if top_hooks and len(top_hooks) >= 2:
        # Variety check: if the top 2 hooks have very different usage, there's no clear winner
        top2 = sorted([h.get("uses", 0) for h in top_hooks], reverse=True)[:2]
        if len(top2) == 2 and top2[0] >= 3 * top2[1]:
            look_at.append({
                "claim": "One hook dominates — risk of voice fatigue.",
                "evidence": f"Top hook used {top2[0]}× vs runner-up {top2[1]}×. Test a contrasting format next week.",
                "category": "voice",
            })

    if platforms and len(platforms) == 1:
        only = list(platforms.keys())[0]
        look_at.append({
            "claim": f"Only publishing to {only} this week.",
            "evidence": "Cross-posting earned media — visualizer works for Facebook too. Worth 30 min of experiment.",
            "category": "channels",
        })

    # ── NEW (v2026-08-04) ── CROSS-CUT CLAIM GENERATORS (6 sources) ─

    sources_used = []

    # ── 1. IG analytics ──────────────────────────────────────────────
    ig_claims = []
    if isinstance(ig_analytics, dict):
        totals = ig_analytics.get("totals") or {}
        ig_claims.append(("ig", totals.get("posts", 0), totals.get("reach", 0)))
    if ig_claims and ig_claims[0][0] == "ig":
        _, n_posts, n_reach = ig_claims[0]
        if n_posts > 0:
            sources_used.append("ig-analytics.json")
        if n_posts > 0 and n_reach > 0:
            working.append({
                "claim": f"IG reached {n_reach:,} accounts across {n_posts} posts.",
                "evidence": f"Reach aggregated from ig-analytics.json post-level metrics. Saves={int(ig_analytics.get('totals', {}).get('saves', 0))}, Shares={int(ig_analytics.get('totals', {}).get('shares', 0))}.",
                "source": "ig-analytics.json",
                "category": "ig_engagement",
            })
        elif n_posts > 0 and n_reach == 0:
            look_at.append({
                "claim": f"IG has {n_posts} posts tracked but zero reach recorded.",
                "evidence": "Reach counter is 0 across all posts. Either engagement metrics haven't synced, or the sync ran before the IG API returned metrics. Re-run sync_ig_analytics.js to verify.",
                "source": "ig-analytics.json",
                "category": "ig_engagement",
            })

    # Hook-IDs cross-cut (was a real-data discovery)
    if isinstance(hook_match, dict):
        overlap = hook_match.get("overlap", 0)
        in_pub = hook_match.get("in_pub_not_ig", 0)
        in_ig = hook_match.get("in_ig_not_pub", 0)
        if (in_pub > 0 or in_ig > 0) and sources_used:
            look_at.append({
                "claim": f"Hook-ID overlap between published-items and IG is {overlap} (0 expected signal).",
                "evidence": f"in_pub_not_ig={in_pub}, in_ig_not_pub={in_ig}. Either the sync is showing different content from what was published, or hook_ids aren't linking between sources.",
                "source": "ig-analytics.json + published-items.json",
                "category": "engagement_match",
            })

    # ── 2. GA4 ───────────────────────────────────────────────────────
    if isinstance(ga4, dict) and ga4.get("total_sessions") is not None:
        sources_used.append("ga4-metrics.json")
        sessions = ga4.get("total_sessions", 0)
        top_src = ga4.get("top_source")
        top_src_sess = ga4.get("top_source_sessions")
        if sessions > 0 and top_src:
            working.append({
                "claim": f"GA4 recorded {sessions:,} website sessions; {top_src} is your top acquisition channel ({top_src_sess} sessions).",
                "evidence": f"Source breakdown from ga4-metrics.json across {ga4.get('sources_count', 0)} sources. Last fetch: {ga4.get('fetched_at') or 'never'}.",
                "source": "ga4-metrics.json",
                "category": "web_traffic",
            })
        if ga4.get("stale"):
            not_working.append({
                "claim": "GA4 sync is stale.",
                "evidence": f"_stale flag is set. The fetch job may have auth'd but failed to pull data. Source file is {ga4.get('fetched_at') or 'never updated'}.",
                "source": "ga4-metrics.json",
                "category": "web_traffic",
                "severity": "medium",
            })

    # ── 3. SEO ───────────────────────────────────────────────────────
    if isinstance(seo, dict):
        kw_total = seo.get("keywords_total", 0)
        if kw_total > 0:
            sources_used.append("seo-rankings.json")
        if seo.get("needs_fetcher"):
            not_working.append({
                "claim": f"{kw_total} SEO keywords tracked but zero have rank data — rankings fetcher is offline.",
                "evidence": f"seo-rankings.json has {kw_total} keywords, all current_rank: null. Need a live rank fetcher (Ubersuggest MCP wired). Last update: {seo.get('freshness') or 'never'}.",
                "source": "seo-rankings.json",
                "category": "seo",
                "severity": "medium",
            })
        if (seo.get("rising") or seo.get("falling")) and not seo.get("needs_fetcher"):
            sources_used.append("seo-rankings.json")
            if seo.get("rising"):
                working.append({
                    "claim": f"{seo.get('rising')} SEO keyword(s) moved up this week.",
                    "evidence": "Cross-cut from seo-rankings.json movers list.",
                    "source": "seo-rankings.json",
                    "category": "seo",
                })

    # ── 3b. SEO — RANK MOVEMENT DETAIL (richer claim when real ranks exist) ──
    # Fires only when actual rank data is present (post-launch the next morning).
    # Auto-silent before any fetch_ubersuggest.py run. Reads seo-rankings.json
    # directly so the report claims are grounded in real data, not vibes.
    #
    # Live-tested 2026-08-06: real seo-rankings.json shape (from
    # fetch_ubersuggest.py pulling project_position_info) is:
    #   {
    #     "rising":    [{"keyword","previous_rank","current_rank",...}],
    #     "falling":   [...],
    #     "quick_wins":[...],
    #     "summary":   {"up","down","unchanged"},
    #     "binned":    {"top_3":{"old","new"}, ...},
    #     "average_position_trend": [{"date","position"}],
    #   }
    # The OLD claim generator looked for `rising_keywords` (snake_case);
    # we now point at `rising` and gracefully fall back if old shape lingers.
    try:
        seo_full_path = os.path.join(DATA_DIR, "seo-rankings.json")
        seo_full = _read_json(seo_full_path) if os.path.exists(seo_full_path) else None
        if isinstance(seo_full, dict):
            # Accept both shapes — old `rising_keywords`, new `rising`.
            rk = (seo_full.get("rising_keywords")
                  if isinstance(seo_full.get("rising_keywords"), list)
                  else seo_full.get("rising") or [])
            fk = (seo_full.get("falling_keywords")
                  if isinstance(seo_full.get("falling_keywords"), list)
                  else seo_full.get("falling") or [])
            summary = seo_full.get("summary") or {}
            avg_trend = seo_full.get("average_position_trend") or []

            if (rk or fk) and not seo_full.get("needs_fetcher"):
                sources_used.append("seo-rankings.json")
                if rk and isinstance(rk[0], dict) and rk[0].get("keyword"):
                    top = rk[0]
                    big_mover = (
                        f"Biggest SEO mover: '{top['keyword']}' rose "
                        f"from #{top.get('previous_rank', '?')} "
                        f"to #{top.get('current_rank', '?')}."
                    )
                else:
                    big_mover = None
                if fk and isinstance(fk[0], dict) and fk[0].get("keyword"):
                    top_d = fk[0]
                    big_drop = (
                        f"Biggest SEO drop: '{top_d['keyword']}' fell "
                        f"from #{top_d.get('previous_rank', '?')} "
                        f"to #{top_d.get('current_rank', '?')}."
                    )
                else:
                    big_drop = None

                if big_mover:
                    working.append({
                        "claim": big_mover,
                        "evidence": (
                            f"seo-rankings.json — {len(rk)} keyword(s) "
                            f"ranked up this period, {len(fk)} ranked down, "
                            f"{summary.get('unchanged', 0)} unchanged. "
                            f"Source: Ubersuggest via daily fetch_ubersuggest.py cron."
                        ),
                        "source": "seo-rankings.json",
                        "category": "seo",
                    })
                elif big_drop:
                    not_working.append({
                        "claim": big_drop,
                        "evidence": (
                            f"seo-rankings.json falling_keywords — {len(fk)} keyword(s) "
                            f"lost rank this week. Audit content + backlinks for that page."
                        ),
                        "source": "seo-rankings.json",
                        "category": "seo",
                        "severity": "medium",
                    })

                # Average-position trend claim — fires when we have ≥2 weekly points.
                if avg_trend and len(avg_trend) >= 2:
                    head = avg_trend[0]
                    tail = avg_trend[-1]
                    if (head.get("position") is not None
                            and tail.get("position") is not None):
                        delta = head["position"] - tail["position"]
                        sign = "improved" if delta > 0 else (
                            "slipped" if delta < 0 else "held"
                        )
                        verb = "improved" if delta > 0 else (
                            "slipped" if delta < 0 else "held"
                        )
                        working.append({
                            "claim": (
                                f"Avg position for swingshack.co.za {sign} "
                                f"{abs(delta):.1f} places over "
                                f"{len(avg_trend)} weekly snapshots "
                                f"(#{head['position']:.2f} → "
                                f"#{tail['position']:.2f})."
                            ),
                            "evidence": (
                                f"seo-rankings.json average_position_trend "
                                f"({len(avg_trend)} points, "
                                f"{head.get('date')} → {tail.get('date')}). "
                                f"Source: Ubersuggest via fetch_ubersuggest.py."
                            ),
                            "source": "seo-rankings.json",
                            "category": "seo",
                        })
    except Exception:
        pass

    # ── 3c. SEO — DOMAIN AUTHORITY (from ubersuggest-domain.json) ──
    # Optional file written by fetch_ubersuggest.py as a side effect.
    #
    # Live-tested 2026-08-06: real shape is FLAT — ubersuggest-domain.json
    # contains the result of `domain_overview` directly, NOT the raw MCP
    # envelope. So we read top-level keys (organic, traffic, domainAuthority,
    # backlinks, refDomains) instead of drilling into `content[0].text`.
    try:
        domain_path = os.path.join(DATA_DIR, "ubersuggest-domain.json")
        domain_data = _read_json(domain_path) if os.path.exists(domain_path) else None
        if isinstance(domain_data, dict):
            sources_used.append("ubersuggest-domain.json")
            traffic = domain_data.get("traffic")
            organic = domain_data.get("organic")
            da = domain_data.get("domainAuthority")
            backlinks_count = domain_data.get("backlinks")
            ref_domains = domain_data.get("refDomains")
            fetched_at = (domain_data.get("_meta") or {}).get("fetched_at", "unknown")

            claim_parts = []
            if traffic:
                claim_parts.append(f"organic traffic = {int(traffic):,}")
            if organic:
                claim_parts.append(f"organic keywords = {int(organic):,}")
            if da:
                claim_parts.append(f"domain authority = {da}")
            if backlinks_count is not None:
                claim_parts.append(f"backlinks = {int(backlinks_count):,}")
            if ref_domains is not None:
                claim_parts.append(f"referring domains = {int(ref_domains):,}")

            if claim_parts:
                working.append({
                    "claim": "SEO domain snapshot — " + "; ".join(claim_parts) + ".",
                    "evidence": (
                        f"ubersuggest-domain.json via daily fetch_ubersuggest.py "
                        f"cron. Last fetch: {fetched_at[:10]}. "
                        f"Pulled from `swingshack.co.za` "
                        f"`domain_overview` + `backlinks_overview` MCP tools."
                    ),
                    "source": "ubersuggest-domain.json",
                    "category": "seo",
                })
    except Exception:
        pass

    # ── 3d. SEO — COMPETITORS (from ubersuggest-competitors.json) ──
    # Optional file written by fetch_ubersuggest.py. Surfaces the top organic
    # competitor by keyword overlap — useful for "who's actually competing
    # with us in ZA search" framing in the report.
    try:
        comp_path = os.path.join(DATA_DIR, "ubersuggest-competitors.json")
        comp_data = _read_json(comp_path) if os.path.exists(comp_path) else None
        if isinstance(comp_data, dict):
            comps = comp_data.get("competitors") or []
            if comps and isinstance(comps[0], dict):
                # Sort by keyword overlap (most-overlapping competitor first).
                comps_sorted = sorted(
                    [c for c in comps if isinstance(c, dict)],
                    key=lambda c: c.get("commonKeywordCount") or 0,
                    reverse=True,
                )
                top = comps_sorted[0]
                fetched_at = (comp_data.get("_meta") or {}).get("fetched_at", "unknown")
                sources_used.append("ubersuggest-competitors.json")
                overlap = top.get("commonKeywordCount") or 0
                gap = top.get("gapKeywordCount") or 0
                comp_da = top.get("domainAuthority") or 0
                # Resolve our own DA from the same data layer, not a hardcoded
                # value. Falls back gracefully if ubersuggest-domain.json
                # hasn't been written yet (single-tool offline scenario).
                our_da = None
                try:
                    our_domain_data = _read_json(
                        os.path.join(DATA_DIR, "ubersuggest-domain.json")
                    ) or {}
                    our_da = our_domain_data.get("domainAuthority")
                except Exception:
                    pass
                our_da_display = our_da if our_da is not None else "—"

                if our_da is not None and comp_da > our_da + 5 and overlap > 10:
                    not_working.append({
                        "claim": (
                            f"Strongest organic competitor: {top['domain']} "
                            f"— {overlap} shared keywords, DA {comp_da} "
                            f"(us: {our_da})."
                        ),
                        "evidence": (
                            f"ubersuggest-competitors.json via fetch_ubersuggest.py. "
                            f"Top of list by commonKeywordCount. Gap keywords "
                            f"(we don't rank but they do): {gap}. Last fetch: "
                            f"{fetched_at}."
                        ),
                        "source": "ubersuggest-competitors.json",
                        "category": "seo",
                        "severity": "medium",
                    })
                elif gap > 5:
                    working.append({
                        "claim": (
                            f"SEO opportunity: {gap} gap keywords to outrank "
                            f"{top['domain']} on."
                        ),
                        "evidence": (
                            f"ubersuggest-competitors.json — top competitor "
                            f"{top['domain']} ranks for {overlap} keywords we "
                            f"also target (their DA {comp_da}, ours {our_da_display}), "
                            f"but {gap} keywords where they rank and we don't "
                            f"(gapKeywordCount)."
                        ),
                        "source": "ubersuggest-competitors.json",
                        "category": "seo",
                    })
    except Exception:
        pass

    # ── 3e. CONVERSION TRUTH (from roi-truth.json + booking-events.json) ──
    # The CMO brain requires knowing which content/hook actually moves the
    # financial needle - not just which got likes. This block reads the
    # conversion-truth engine output (roi-truth.json) and the GA4 booking
    # event inventory (booking-events.json) to surface:
    #   1. Current ROI confidence band per revenue source
    #   2. The verdict (e.g. "publishing STRONG_PROXY, lead routing UNMEASURABLE")
    #   3. The #1 unblocker to lift a source from weak/unknown to verified
    #   4. Which booking events are live in GA4 right now
    #
    # NOTE: roi-truth.json + booking-events.json were last regenerated by
    # scripts/run_conversion_truth_engine.js on 2026-04-23 (113 days stale at
    # time of wire). The engine itself is intact; it just hasn't been run
    # since. Adding this wire to weekly_report means the verdict surfaces
    # again every time the engine re-runs, and gives Forge / Christelle a
    # visible "what's still unmeasurable" claim to drive the next sprint.
    try:
        roi_path = _runtime_data_file("roi-truth.json")
        booking_path = _runtime_data_file("booking-events.json")
        roi = _read_json(roi_path) if os.path.exists(roi_path) else None
        bookings = _read_json(booking_path) if os.path.exists(booking_path) else None
        if isinstance(roi, dict):
            sources_used.append("roi-truth.json")
            summary = roi.get("summary") or {}
            total = int(summary.get("total", 0))
            direct = int(summary.get("direct", 0))
            strong = int(summary.get("strong_proxy", 0))
            weak = int(summary.get("weak_proxy", 0))
            unmeasurable = int(summary.get("unmeasurable", 0))
            verdict = summary.get("verdict", "")
            roi_generated = (roi.get("generated") or "")[:10]

            if verdict or direct or strong or weak or unmeasurable:
                band_breakdown = (
                    f"{direct} DIRECT · {strong} STRONG_PROXY · "
                    f"{weak} WEAK_PROXY · {unmeasurable} UNMEASURABLE "
                    f"(of {total} revenue sources)"
                )
                working.append({
                    "claim": (
                        f"Conversion truth band - {verdict or band_breakdown}. "
                        f"Last engine run: {roi_generated or 'unknown'}."
                    ),
                    "evidence": (
                        f"roi-truth.json reclassifies every revenue source "
                        f"(publishing, lead routing, ad budget, etc.) into a "
                        f"confidence band based on whether the GA4 booking "
                        f"confirmation event is live. DIRECT = "
                        f"booking-confirmed; STRONG_PROXY = UTM chain + "
                        f"session trackable; WEAK_PROXY = indirect correlation "
                        f"only; UNMEASURABLE = no data path."
                    ),
                    "source": "roi-truth.json",
                    "category": "attribution",
                })

            # Top unblocker: the priority-1 recommendation that would lift
            # the most sources from weak to verified.
            recs = roi.get("recommendations") or []
            if isinstance(recs, list) and recs:
                top_recs = sorted(
                    [r for r in recs if isinstance(r, dict) and r.get("priority") == 1],
                    key=lambda r: r.get("priority", 99),
                )[:2]
                if top_recs:
                    actions = [r.get("action", "?") for r in top_recs]
                    working.append({
                        "claim": (
                            f"Top attribution unblocker - "
                            f"{'; '.join(actions)}. "
                            f"Closing either lifts the affected sources from "
                            f"unmeasurable to verified revenue."
                        ),
                        "evidence": (
                            f"roi-truth.json recommendations (priority 1). "
                            f"These are the two highest-leverage integrations "
                            f"that would convert the current UNMEASURABLE / "
                            f"WEAK_PROXY sources into DIRECT (booking-confirmed) "
                            f"attribution. Each recommendation cites the "
                            f"specific API + tracking event that closes the loop."
                        ),
                        "source": "roi-truth.json",
                        "category": "attribution",
                    })

            # Sources still in UNMEASURABLE - surfaced as LOOK AT (not
            # working / not failing, just "we have no idea").
            unmeasurable_sources = [
                s for s in (roi.get("sources") or [])
                if isinstance(s, dict)
                and s.get("can_measure") == "UNMEASURABLE"
            ]
            if unmeasurable_sources:
                names = [s.get("name", s.get("source", "?")) for s in unmeasurable_sources]
                look_at.append({
                    "claim": (
                        f"{len(unmeasurable_sources)} revenue source(s) still "
                        f"unmeasurable - {', '.join(names)}. We are publishing "
                        f"and spending on these without being able to attribute "
                        f"any revenue to them."
                    ),
                    "evidence": (
                        f"roi-truth.json sources[] filtered by "
                        f"can_measure='UNMEASURABLE'. Until the recommended "
                        f"integrations land (WhatsApp Business, Meta Ads + GA4 "
                        f"goal tracking, GA4 booking confirmation event), these "
                        f"channels are operating blind."
                    ),
                    "source": "roi-truth.json",
                    "category": "attribution",
                })

        # Booking events inventory - which GA4 conversion events are live.
        # Surface the count + priority-1 event so the report says "3 of 7
        # booking events are measurable in GA4" + which one is the unblocker.
        if isinstance(bookings, dict):
            sources_used.append("booking-events.json")
            events = bookings.get("events") or []
            if isinstance(events, list) and events:
                measurable = [
                    e for e in events
                    if isinstance(e, dict) and e.get("current_measurable")
                ]
                priority_one = [
                    e for e in events
                    if isinstance(e, dict) and e.get("priority") == 1
                ]
                priority_one_unmeasured = [
                    e for e in priority_one
                    if isinstance(e, dict) and not e.get("current_measurable")
                ]
                if priority_one_unmeasured:
                    names = [
                        e.get("event_id") or e.get("name") or "?"
                        for e in priority_one_unmeasured
                    ]
                    working.append({
                        "claim": (
                            f"GA4 booking events - {len(measurable)} of "
                            f"{len(events)} measurable. Priority-1 events "
                            f"not yet tracking: {', '.join(names)}."
                        ),
                        "evidence": (
                            f"booking-events.json inventory. These are the "
                            f"specific GA4 events that need to be instrumented "
                            f"on the booking funnel (form_submit, "
                            f"booking_completed, service_selected) to convert "
                            f"the conversion-truth band from STRONG_PROXY to "
                            f"DIRECT (verified revenue)."
                        ),
                        "source": "booking-events.json",
                        "category": "attribution",
                    })
    except Exception as _exc:
        # Never let a single source's parse error break the whole report.
        import logging as _logging
        _logging.getLogger(__name__).debug("conversion-truth block skipped: %s", _exc)

    # ── 3f. CONVERSION ATTRIBUTION (from conversion-attribution.json) ──
    # The post-to-booking join. Now that the JS pipeline produces a fresh
    # conversion-attribution.json (was missing for 113 days), surface the
    # CMO-grade signals: top converting CTA bucket, top service by IG signal,
    # top booking page by sessions, and the hook theme that's winning.
    #
    # This is the layer that answers "which post type actually moves people
    # to /bookings/?" - bridging content engagement with site intent.
    try:
        ca_path = _runtime_data_file("conversion-attribution.json")
        if os.path.exists(ca_path):
            ca = _read_json(ca_path) or {}
            if isinstance(ca, dict):
                sources_used.append("conversion-attribution.json")
                ca_summary = ca.get("summary") or {}
                booking_sessions = int(ca_summary.get("booking_sessions") or 0)
                top_service = ca_summary.get("top_converting_service") or "n/a"
                top_cta = ca_summary.get("top_converting_cta") or "n/a"
                top_page = ca_summary.get("top_booking_page") or "n/a"
                top_theme = ca_summary.get("top_hook_theme") or "n/a"

                # 1. Top booking page by sessions - the actual conversion funnel entry.
                #    GA4 tells us how many sessions hit /bookings/, /club-fitting/, etc.
                if booking_sessions > 0:
                    working.append({
                        "claim": (
                            f"Booking funnel volume - {booking_sessions} sessions "
                            f"to high-intent pages in the last 7d. "
                            f"Top entry: {top_page}."
                        ),
                        "evidence": (
                            f"conversion-attribution.json joins GA4 page traffic "
                            f"with IG content engagement. {booking_sessions} sessions "
                            f"hit pages matching booking/fitting/contact patterns. "
                            f"This is the live conversion-funnel volume - the number "
                            f"every post should ultimately be measured against."
                        ),
                        "source": "conversion-attribution.json",
                        "category": "attribution",
                    })

                # 2. Top converting CTA bucket - tells the content engine which
                #    call-to-action style actually engages the audience.
                cta_perf = ca.get("cta_performance") or []
                if cta_perf and isinstance(cta_perf[0], dict):
                    top_cta_row = cta_perf[0]
                    cta_label = top_cta_row.get("cta_type") or "n/a"
                    cta_eng = float(top_cta_row.get("avg_eng_rate") or 0)
                    cta_posts = int(top_cta_row.get("post_count") or 0)
                    if cta_eng > 0 and cta_posts > 0:
                        working.append({
                            "claim": (
                                f"Top converting CTA type - {cta_label}: "
                                f"{cta_eng:.2f}% avg engagement across {cta_posts} posts. "
                                f"More effective than {len(cta_perf) - 1} other CTA buckets."
                            ),
                            "evidence": (
                                f"conversion-attribution.json cta_performance[]. "
                                f"Captions bucketed by keyword (BOOKING/LESSONS/FITTING/"
                                f"PROMO/ENGAGEMENT/SOFT) then ranked by avg engagement "
                                f"rate. The top bucket is what the content engine should "
                                f"default to for max IG engagement."
                            ),
                            "source": "conversion-attribution.json",
                            "category": "attribution",
                        })

                # 3. Top service by IG signal - which service category actually
                #    drives content engagement, vs which has the most page traffic.
                svc_corr = ca.get("service_correlation") or []
                if svc_corr and isinstance(svc_corr[0], dict):
                    top_svc = svc_corr[0]
                    svc_name = top_svc.get("service") or "n/a"
                    svc_posts = int(top_svc.get("post_count") or 0)
                    svc_eng = float(top_svc.get("avg_engagement") or 0)
                    svc_reach = int(top_svc.get("total_reach") or 0)
                    if svc_eng > 0 and svc_posts > 0:
                        working.append({
                            "claim": (
                                f"Top service by content engagement - {svc_name}: "
                                f"{svc_eng:.2f}% avg engagement, {svc_reach:,} reach "
                                f"across {svc_posts} posts in window."
                            ),
                            "evidence": (
                                f"conversion-attribution.json service_correlation[]. "
                                f"Posts matched to Golf Lessons/Club Fitting/Simulator/"
                                f"Membership/Events by caption keywords. {svc_name} is "
                                f"the leader - the content engine should weight this "
                                f"service higher when picking the next post topic."
                            ),
                            "source": "conversion-attribution.json",
                            "category": "attribution",
                        })

                # 4. Top hook theme - which content angle drives engagement.
                themes = ca.get("hook_themes") or []
                if themes and isinstance(themes[0], dict):
                    top_theme_row = themes[0]
                    theme_label = top_theme_row.get("theme_label") or "n/a"
                    theme_eng = float(top_theme_row.get("avg_engagement") or 0)
                    theme_posts = int(top_theme_row.get("post_count") or 0)
                    if theme_eng > 0 and theme_posts > 0:
                        working.append({
                            "claim": (
                                f"Top hook theme - {theme_label}: "
                                f"{theme_eng:.2f}% avg engagement across {theme_posts} posts."
                            ),
                            "evidence": (
                                f"conversion-attribution.json hook_themes[]. Posts matched "
                                f"to themes by caption keywords (TrackMan/Slice Fix/Lessons/"
                                f"Putting/Fitting/Contest/Membership/Simulator). "
                                f"{theme_label} is the highest-converting angle."
                            ),
                            "source": "conversion-attribution.json",
                            "category": "attribution",
                        })

                # 5. Quick wins - services that show high engagement but low
                #    booking-page coverage (i.e. content exists but site funnel
                #    is missing for them). This is the "what to build next" claim.
                qw = ca.get("quick_wins") or []
                if isinstance(qw, list) and qw:
                    actions = [q.get("action", "?") for q in qw[:2]]
                    working.append({
                        "claim": (
                            f"Conversion quick wins - "
                            f"{'; '.join(actions)}."
                        ),
                        "evidence": (
                            f"conversion-attribution.json quick_wins[]: services "
                            f"with high IG signal but thin booking-page coverage. "
                            f"These are the highest-leverage gaps to close in the "
                            f"site funnel."
                        ),
                        "source": "conversion-attribution.json",
                        "category": "attribution",
                    })
    except Exception as _exc:
        import logging as _logging
        _logging.getLogger(__name__).debug("conversion-attribution block skipped: %s", _exc)

    # ── 3g. POST->CONVERSION ATTRIBUTION (from ga4-attribution.json) ──
    # The CMO brain's money question: which IG post drove which /bookings/
    # traffic, and which channels drive actual booking completions.
    #
    # This block surfaces:
    #   1. Top IG-attributed /bookings/ posts (by hook_id in GA4 UTM content)
    #   2. Booking completion proxy: /bookings/?clientEmail=... sessions
    #      that represent ACTUAL booking completions through the Amelia plugin
    #   3. Source split: where the bookings actually come from
    #   4. Event tracking gap: which booking events are MISSING
    try:
        ga_path = _runtime_data_file("ga4-attribution.json")
        if os.path.exists(ga_path):
            ga = _read_json(ga_path) or {}
            if isinstance(ga, dict):
                sources_used.append("ga4-attribution.json")
                summary = ga.get("summary") or {}
                completion = ga.get("booking_completion_proxy") or {}
                events = ga.get("events_tracked") or {}

                # 1. Booking completion proxy - the closest thing to VERIFIED_REVENUE
                #    we have without a booking_completed GA4 event.
                completion_sessions = int(summary.get("completion_proxy_sessions") or completion.get("completion_proxy_sessions") or 0)
                browse_sessions = int(summary.get("browse_only_sessions") or completion.get("browse_sessions") or 0)
                completion_count = int(completion.get("completion_proxy_count") or 0)
                if completion_sessions > 0:
                    # Conversion rate from browse -> complete
                    cr_pct = (completion_sessions / (completion_sessions + browse_sessions) * 100) if (completion_sessions + browse_sessions) > 0 else 0
                    working.append({
                        "claim": (
                            f"Booking completion volume - {completion_sessions} sessions "
                            f"reached the booking confirmation page in the last 30d "
                            f"({cr_pct:.1f}% browse-to-complete conversion). "
                            f"{completion_count} unique completion URLs captured."
                        ),
                        "evidence": (
                            f"ga4-attribution.json booking_completion_proxy. Detects "
                            f"/bookings/?facilityId=&serviceId=&clientEmail=&packageRedeem= "
                            f"URLs (Amelia booking plugin populates these on submit). "
                            f"This is a HIGH-CONFIDENCE proxy for actual bookings until "
                            f"the booking_completed GA4 event is instrumented on the live site."
                        ),
                        "source": "ga4-attribution.json",
                        "category": "attribution",
                    })

                # 2. Source split for completions - shows CMO which channel
                #    is actually closing bookings (not just driving traffic).
                comp_by_src = completion.get("completions_by_source") or []
                if comp_by_src and isinstance(comp_by_src[0], dict):
                    top = comp_by_src[0]
                    top_src = top.get("source") or "n/a"
                    top_count = int(top.get("sessions") or 0)
                    top_pct = (top_count / completion_sessions * 100) if completion_sessions > 0 else 0
                    src_breakdown = ", ".join(
                        f"{s.get('source', '?')}={int(s.get('sessions', 0))}"
                        for s in comp_by_src[:5]
                    )
                    working.append({
                        "claim": (
                            f"Top booking-completion channel - {top_src}: "
                            f"{top_count} booking completions in 30d "
                            f"({top_pct:.0f}% of total). Breakdown: {src_breakdown}."
                        ),
                        "evidence": (
                            f"ga4-attribution.json booking_completion_proxy.completions_by_source. "
                            f"These are real booking-confirmation page sessions (with clientEmail "
                            f"+ serviceId in URL), not just traffic. Shows which acquisition channel "
                            f"actually closes bookings vs which only drives awareness."
                        ),
                        "source": "ga4-attribution.json",
                        "category": "attribution",
                    })

                # 3. IG post attribution - the actual post->/bookings/ join.
                #    We have UTM content captured but it doesn't match modern hook_ids
                #    (legacy campaign tags). Surface the raw UTM-content data
                #    + flag the naming-mismatch gap so the team can decide
                #    whether to retro-tag posts or accept the gap.
                ig_attribution = ga.get("instagram_post_attribution") or []
                ig_booking = [r for r in ig_attribution
                              if isinstance(r, dict)
                              and r.get("page_path")
                              and ("/bookings/" in r.get("page_path", "")
                                   or "/club-fitting/" in r.get("page_path", ""))]
                if ig_booking:
                    total_ig_bookings = sum(int(r.get("sessions") or 0) for r in ig_booking)
                    top_ig = max(ig_booking, key=lambda r: int(r.get("sessions") or 0))
                    top_hook = top_ig.get("hook_id", "unknown")
                    top_sessions = int(top_ig.get("sessions") or 0)
                    matched = [r for r in ig_booking if r.get("matched")]
                    working.append({
                        "claim": (
                            f"IG post attribution - {total_ig_bookings} /bookings/ + "
                            f"/club-fitting/ sessions tagged with IG UTM content in 30d. "
                            f"Top UTM-content: '{top_hook}' drove {top_sessions} sessions. "
                            f"{len(matched)}/{len(ig_booking)} attribution rows matched to "
                            f"specific IG posts (others are legacy campaign tags)."
                        ),
                        "evidence": (
                            f"ga4-attribution.json instagram_post_attribution. Pulled from "
                            f"GA4 (sessionSource=instagram, pagePath contains /bookings/ "
                            f"or /club-fitting/), grouped by sessionManualAdContent (the "
                            f"hook_id). Mismatch with ig-business-analytics.json hook_ids is "
                            f"a known gap: GA4 captured legacy UTM tags (hook-beginner, "
                            f"trackman-authority-961989) while newer posts use "
                            f"caption-derived hook_ids. Backfill the UTM scheme or accept "
                            f"the gap - either is fine, but be explicit."
                        ),
                        "source": "ga4-attribution.json",
                        "category": "attribution",
                    })

                # 4. Event-tracking gap - LOOK_AT: which booking events are
                #    missing. This is the highest-leverage gap to close.
                has_completed = bool(summary.get("has_booking_completed_event"))
                has_amelia = bool(summary.get("has_amelia_events"))
                events_tracked = events.get("events") or []
                amelia_event_names = [e["event_name"] for e in events_tracked
                                       if "amelia" in e.get("event_name", "").lower()]
                if not has_completed:
                    look_at.append({
                        "claim": (
                            f"GA4 booking_completed event is NOT being tracked. "
                            f"{'Amelia events are firing (form_view, checkout_view) but the confirmation page is not pushing booking_completed.' if has_amelia else 'Zero booking events are tracked.'} "
                            f"Until this lands, all booking-revenue attribution is a proxy "
                            f"based on URL pattern, not event-tracked."
                        ),
                        "evidence": (
                            f"ga4-attribution.json events_tracked. Top events: "
                            f"{', '.join(e['event_name'] + ':' + str(e['count']) for e in events_tracked[:5])}. "
                            f"Wiring the booking_completed event is a 1-2h code change on "
                            f"the Amelia booking confirmation page and would upgrade 3 channels "
                            f"from STRONG_PROXY to VERIFIED_REVENUE in the conversion truth band."
                        ),
                        "source": "ga4-attribution.json",
                        "category": "attribution",
                    })
    except Exception as _exc:
        import logging as _logging
        _logging.getLogger(__name__).debug("ga4-attribution block skipped: %s", _exc)

    # ── 4. YouTube ───────────────────────────────────────────────────
    if isinstance(youtube, dict):
        themes = youtube.get("active_themes") or []
        vids = (youtube.get("top_videos_count") or youtube.get("videos_found")) or 0
        if themes or vids:
            sources_used.append("youtube-trends.json")
        if themes:
            working.append({
                "claim": f"YouTube trends pulled; active themes this week: {', '.join(themes[:6])}.",
                "evidence": f"From youtube-trends.json trending_themes ({len(themes)}/8 themes active) + {vids} candidate videos fetched.",
                "source": "youtube-trends.json",
                "category": "youtube_trends",
            })

    # ── 5. Reddit opportunities vs replies ──────────────────────────
    if isinstance(reddit_opps, dict) or isinstance(reddit_replies, dict):
        n_opps = (reddit_opps or {}).get("count", 0)
        n_replies = (reddit_replies or {}).get("count", 0)
        if n_opps or n_replies:
            sources_used.append("reddit-opportunities.json + reddit-replies.json")
        if n_opps > 0 and n_replies >= n_opps:
            working.append({
                "claim": f"All {n_opps} Reddit opportunity threads have drafted ghost replies ({n_replies} drafts).",
                "evidence": f"{n_replies} drafts in reddit-replies.json vs {n_opps} opportunities in reddit-opportunities.json. ready_for_qa: opp={reddit_opps.get('ready_for_qa', 0) if reddit_opps else 0}, reply={reddit_replies.get('ready_for_qa', 0) if reddit_replies else 0}.",
                "source": "reddit-opportunities.json + reddit-replies.json",
                "category": "reddit_outreach",
            })
        elif n_opps > 0 and n_replies < n_opps:
            not_working.append({
                "claim": f"Only {n_replies}/{n_opps} Reddit opportunities have drafted replies.",
                "evidence": f"Gap of {n_opps - n_replies} threads that need ghost-reply drafts before they go cold.",
                "source": "reddit-opportunities.json + reddit-replies.json",
                "category": "reddit_outreach",
                "severity": "low",
            })

    # ── 6. Hook bank state ───────────────────────────────────────────
    if isinstance(hook_bank_buckets, dict):
        any_bucket = any(hook_bank_buckets.values())
        if any_bucket:
            sources_used.append("hook-bank.json")
            proven_only = hook_bank_buckets.get("proven_only", 0)
            trending_to_test = hook_bank_buckets.get("trending_to_test", 0)
            if proven_only > 0 and not isinstance(ig_analytics, dict):
                working.append({
                    "claim": f"{proven_only} hooks are IG-proven and ready to rotate into the next campaign.",
                    "evidence": f"From hook-bank.json output_buckets.proven_only — these hooks have real engagement signals but aren't yet in the published queue.",
                    "source": "hook-bank.json",
                    "category": "voice",
                })
            elif proven_only > 0 and isinstance(ig_analytics, dict) and hook_match and hook_match.get("in_pub_not_ig", 0) > 0:
                # Even better — combine 2 sources
                working.append({
                    "claim": f"{proven_only} IG-proven hooks aren't being used in publishing this week.",
                    "evidence": f"Cross-cut: hook-bank.json output_buckets.proven_only ({proven_only} hooks) vs published-items.json linked_hook_ids ({hook_match.get('in_pub_not_ig', 0)} of those not in IG analytics). Opportunity to rotate them in.",
                    "source": "hook-bank.json + published-items.json",
                    "category": "voice",
                })
            if trending_to_test >= 3:
                look_at.append({
                    "claim": f"{trending_to_test} trending hooks are queued for A/B test — pick 3 to run this week.",
                    "evidence": "From hook-bank.json output_buckets.trending_to_test. They have cross-signal scores but haven't been validated against live IG yet.",
                    "source": "hook-bank.json",
                    "category": "voice",
                })

    # Hook-bank ↔ published cross-cut (NEW — surfaces missing hooks)
    if isinstance(hook_match, dict) and hook_match.get("in_pub_not_hook_bank", 0) > 0:
        not_in_bank = hook_match["in_pub_not_hook_bank"]
        hb_total = hook_match.get("hook_bank_total", 0)
        if not_in_bank > hb_total:
            not_working.append({
                "claim": f"{not_in_bank} of your published hook_ids aren't in the hook-bank at all.",
                "evidence": f"published-items.json has unique hook_ids in use, hook-bank.json only contains {hb_total} entries (across all buckets). Hook-bank has been regenerated independently and lost the published history.",
                "source": "published-items.json + hook-bank.json",
                "category": "voice",
                "severity": "low",
            })

    # ── 7. NEW (v2026-08-13) · IG Business live-account metrics ·─
    # Reads data/ig-business-analytics.json (written by
    # scripts/fetch_ig_business.py via launchd). Surface:
    #   - 30d window_total for reach, accounts_engaged, total_interactions
    #   - 30d daily reach series (trend direction)
    #   - top post by reach (with caption hook + permalink)
    #   - follower delta (current snapshot vs ~30d ago)
    if isinstance(ig_business, dict) and (ig_business.get("window_totals") or ig_business.get("account")):
        sources_used.append("ig-business-analytics.json")
        win = ig_business.get("window_totals") or {}
        daily_reach = ig_business.get("daily_reach") or []
        top_post = ig_business.get("top_post") or {}
        account = ig_business.get("account") or {}

        # Reach trend (last half vs prior half) · early-warning on
        # audience contraction.
        if len(daily_reach) >= 14:
            mid = len(daily_reach) // 2
            prior_avg = sum(d["value"] for d in daily_reach[:mid]) / max(mid, 1)
            recent_avg = sum(d["value"] for d in daily_reach[mid:]) / max(len(daily_reach) - mid, 1)
            if prior_avg > 0 and recent_avg < prior_avg * 0.5:
                not_working.append({
                    "claim": f"Daily IG reach has fallen {(1 - recent_avg/prior_avg)*100:.0f}% over the past {len(daily_reach[mid:])}d (vs the prior {mid}d).",
                    "evidence": f"From ig-business-analytics.json daily_reach: prior {mid}d avg={prior_avg:.0f}, recent {len(daily_reach)-mid}d avg={recent_avg:.0f}. Reach contraction is the earliest signal of an audience that the algorithm has stopped pushing.",
                    "source": "ig-business-analytics.json",
                    "category": "ig_engagement",
                    "severity": "high",
                })
            elif prior_avg > 0 and recent_avg > prior_avg * 1.25:
                working.append({
                    "claim": f"Daily IG reach is up {(recent_avg/prior_avg-1)*100:.0f}% over the past {len(daily_reach[mid:])}d (vs the prior {mid}d).",
                    "evidence": f"From ig-business-analytics.json daily_reach: prior {mid}d avg={prior_avg:.0f}, recent {len(daily_reach)-mid}d avg={recent_avg:.0f}.",
                    "source": "ig-business-analytics.json",
                    "category": "ig_engagement",
                })

        # Window totals · sum daily_reach as fallback if window_totals.reach
        # is missing (which can happen if `reach` is only available via
        # daily timeseries for some account types).
        reach_30d = win.get("reach")
        if not isinstance(reach_30d, (int, float)) and daily_reach:
            reach_30d = sum(d["value"] for d in daily_reach)
        engaged_30d = win.get("accounts_engaged")
        interactions_30d = win.get("total_interactions")
        if isinstance(reach_30d, (int, float)) and reach_30d > 0:
            working.append({
                "claim": f"IG account reached {int(reach_30d):,} unique accounts in the last 30d.",
                "evidence": f"From ig-business-analytics.json window_totals.reach ({int(reach_30d)}); accounts_engaged={engaged_30d}, total_interactions={interactions_30d}. This is the live Graph API number. ig-analytics.json's reach field stays 0 because the legacy sync doesn't populate it.",
                "source": "ig-business-analytics.json",
                "category": "ig_engagement",
            })
        if isinstance(engaged_30d, (int, float)) and isinstance(reach_30d, (int, float)) and reach_30d > 0:
            er_30d = round(engaged_30d / reach_30d * 100, 2)
            working.append({
                "claim": f"30d IG account engagement rate is {er_30d}%.",
                "evidence": f"accounts_engaged={engaged_30d} / reach={int(reach_30d)}. Industry baseline for indoor-golf niche is ~2-5%; anything above 5% is strong signal of an audience that returns.",
                "source": "ig-business-analytics.json",
                "category": "ig_engagement",
            })

        # Top post
        if isinstance(top_post.get("reach"), (int, float)) and top_post.get("reach", 0) > 0:
            cap = (top_post.get("caption_preview") or "").strip().split("\n", 1)[0]
            claim = f"Top IG post in window reached {int(top_post['reach']):,} accounts"
            if top_post.get("interactions"):
                claim += f" with {int(top_post['interactions'])} interactions"
            claim += "."
            working.append({
                "claim": claim,
                "evidence": f"Caption hook: \"{cap[:80]}\". Permalink: {top_post.get('permalink')}. From ig-business-analytics.json top_post.",
                "source": "ig-business-analytics.json",
                "category": "ig_engagement",
            })

        # Account snapshot (follower count)
        followers = account.get("followers_count")
        if isinstance(followers, (int, float)):
            look_at.append({
                "claim": f"@swingshack has {int(followers):,} IG followers as of this fetch.",
                "evidence": "From ig-business-analytics.json account.followers_count. Compare against next fetch to detect follower-delta direction.",
                "source": "ig-business-analytics.json",
                "category": "ig_engagement",
            })

    # ── Headline take
    if not_working and not_working[0].get("severity") == "high":
        headline_take = f"Bottleneck this week: {not_working[0]['claim']}"
    elif working and published > 0:
        headline_take = working[0]["claim"]
    elif published == 0:
        headline_take = "Quiet week — no publishes, no failures."
    else:
        headline_take = "Steady week — keep going."

    # ── DEFENSIVE DEFAULT — every claim should cite a source ──
    # Some pre-existing claim generators (from the original v1) didn't include
    # a `source` field. Backfill by mapping category → source for the contract.
    default_source_by_cat = {
        "publishing": "published-items.json",
        "growth": "published-items.json + agent-runs.json",
        "voice": "hook-bank.json",
        "fleet": "agent-runs.json",
        "seo": "seo-rankings.json",
        "channels": "published-items.json",
        "cadence": "published-items.json",
    }
    for lst in (working, not_working, look_at):
        for c in lst:
            if "source" not in c:
                c["source"] = default_source_by_cat.get(c.get("category", ""), "—")

    return {
        "whats_working": working,
        "whats_not": not_working,
        "look_at": look_at,
        "headline_take": headline_take,
        "sources_used": sorted(set(sources_used)),
    }


def _visual_insights_for_week(this_week, prev_week, brand_dir=None):
    """Aggregate visual DNA patterns from the brand directory and correlate with engagement.

    Output shape:
      {
        "corpus": { "n_images": int, "luminance": {...}, "top_palettes": [...],
                    "top_moods": [...], "top_objects": [...], "pass_rate_pct": float },
        "vs_last_week": { "delta_visual_posts": int, "luminance_trend": "..." },
        "insight":       [ { "claim": "..." , "evidence": "..."} , ... ]
      }
    """
    if not brand_dir:
        brand_dir = os.path.join(DATA_DIR, "brand-directory", "swing-shack")
    index_path = os.path.join(brand_dir, "visual-dna-index.json")
    images_root = os.path.join(brand_dir, "images")

    index = _read_json(index_path) or {}
    by_filename = index.get("by_filename") or {}
    n_images = int(index.get("image_count") or len(by_filename) or 0)

    # Aggregate corpus-level stats from each per-image .visual-dna.json
    lum_counts = {"dark": 0, "mid": 0, "bright": 0, "unknown": 0}
    palette_counts = Counter()
    mood_counts = Counter()
    object_counts = Counter()
    brand_counts = Counter()
    pass_count, fail_count, score_bucket = 0, 0, Counter()
    n_parsed = 0

    for fn, idx_entry in by_filename.items():
        dna_path = idx_entry.get("dna_path") or os.path.join(images_root, f"{fn}.visual-dna.json")
        if not dna_path or not os.path.exists(dna_path):
            continue
        dna = _read_json(dna_path)
        if not isinstance(dna, dict):
            continue
        n_parsed += 1
        # Luminance
        lum = (dna.get("layer9_palette") or {}).get("luminance_category") or (dna.get("layer12_scene") or {}).get("luminance") or "unknown"
        lum_counts[lum if lum in lum_counts else "unknown"] += 1
        # Palette (top 5 dominant hex)
        for c in (dna.get("layer9_palette") or {}).get("dominant_colors", []) or []:
            hex_code = c.get("hex")
            if hex_code:
                palette_counts[hex_code.upper()] += c.get("share", 0)
        # Mood tags
        for m in (dna.get("layer3_mood") or {}).get("tags", []) or []:
            mood_counts[m.lower()] += 1
        # Objects
        for o in (dna.get("layer5_objects") or {}).get("tags", []) or []:
            object_counts[o.lower()] += 1
        # Brands
        for b in (dna.get("layer13_brand_emphasis") or {}).get("brands", []) or []:
            brand_counts[b] += 1
        # Compliance score bucket
        score = idx_entry.get("score")
        if score is None:
            score = (dna.get("layer8_compliance") or {}).get("score")
        if isinstance(score, (int, float)):
            if score >= 0.7:
                pass_count += 1
            else:
                fail_count += 1
            bucket = round(score * 10) / 10
            score_bucket[bucket] += 1
        else:
            pass_count += 1 if idx_entry.get("passes") else fail_count

    n_corp = max(n_parsed, 1)
    top_palettes = [{"hex": h, "share": round(s, 4)} for h, s in palette_counts.most_common(8)]
    top_moods = [{"mood": m, "count": c} for m, c in mood_counts.most_common(5)]
    top_objects = [{"object": o, "count": c} for o, c in object_counts.most_common(5)]
    top_brands = [{"brand": b, "count": c} for b, c in brand_counts.most_common(5)]

    # ── Pattern statements (the "blue images perform better" thing) ──
    # These are deterministic thresholds: luminance with bigger share
    # AND a non-zero palette slot at the dominant hue family.
    insights = []
    n_dark = lum_counts.get("dark", 0)
    n_mid = lum_counts.get("mid", 0)
    n_bright = lum_counts.get("bright", 0)

    if n_dark / n_corp >= 0.5:
        # Over half the corpus is dark — that's the brand-canon
        insights.append({
            "claim": f"{round(n_dark / n_corp * 100)}% of approved imagery is dark-luminance.",
            "evidence": f"Out of {n_parsed} images: dark={n_dark}, mid={n_mid}, bright={n_bright}. Correlate with weekly published-posts to see if dark posts drive more engagement than non-dark.",
            "category": "palette",
        })
    if top_palettes:
        h1 = top_palettes[0]
        # Detect "blue dominance" from hex
        rgb = _hex_to_rgb(h1["hex"]) if h1.get("hex") else None
        if rgb:
            r, g, b = rgb
            if b > r and b > g and (b - max(r, g)) > 15:
                insights.append({
                    "claim": f"Dominant palette leans blue — top hex {h1['hex']}.",
                    "evidence": "Track this colour family against weekly IG engagement to see whether 'blue days' outperform 'amber days'.",
                    "category": "palette",
                })
        # Also detect neutral / black dominance
        if rgb and max(rgb) < 35:
            insights.append({
                "claim": f"Top palette is near-black {h1['hex']} — gym/editorial mood.",
                "evidence": "Common to indoor-bay shots. If neutral-black images under-engage, look at adding accent colour (amber/teal) to lift contrast.",
                "category": "palette",
            })

    if top_moods:
        m1 = top_moods[0]
        insights.append({
            "claim": f"Most-cited mood is '{m1['mood']}' ({m1['count']}× across corpus).",
            "evidence": "Two-cardinality check: confirm posts with this mood outperform 'general' mood posts in weekly engagement.",
            "category": "mood",
        })

    # Compliance insight
    total_score = sum(score_bucket.values())
    if total_score:
        for bucket in sorted(score_bucket.keys(), reverse=True):
            if score_bucket[bucket] >= 5:
                insights.append({
                    "claim": f"Most images cluster in the {round(bucket, 1)} brand-compliance bucket.",
                    "evidence": f"{score_bucket[bucket]}/{total_score} images. Pull this bucket for Quick Wins — those are the visual recipes that already match canon.",
                    "category": "compliance",
                })
                break

    # Pass/fail rate
    if (pass_count + fail_count) > 0:
        rate = round(pass_count / (pass_count + fail_count) * 100, 1)
        insights.append({
            "claim": f"Visual-brand compliance pass rate is {rate}% across {pass_count+fail_count} images.",
            "evidence": "Aim for 75%+ canon-alignment before scaling output. Use the failing images' dominant_hex + composition_tags as a corrective reference.",
            "category": "compliance",
        })

    # Subjects — what kind of imagery dominates
    if top_objects:
        o1 = top_objects[0]
        if o1["count"] >= n_corp * 0.3:
            insights.append({
                "claim": f"Object '{o1['object']}' dominates {round(o1['count'] / n_corp * 100)}% of approved images.",
                "evidence": "Consider whether over-representation is diluting variety. Add an object-type in the next brief if visual monotony is a risk.",
                "category": "variety",
            })

    # Top brand mentions
    if top_brands:
        b1 = top_brands[0]
        insights.append({
            "claim": f"Brand '{b1['brand']}' appears across {b1['count']} approved images.",
            "evidence": "Tells you which SKUs are photographable already. The dark-count of any other brand = a content gap.",
            "category": "subjects",
        })

    # vs last week: simple delta based on published items
    n_this_week_visuals = len(this_week or [])
    n_prev_week_visuals = len(prev_week or [])
    if n_this_week_visuals or n_prev_week_visuals:
        delta = n_this_week_visuals - n_prev_week_visuals
        trend = "up" if delta > 0 else "down" if delta < 0 else "flat"
    else:
        delta, trend = 0, "no_data"

    return {
        "corpus": {
            "n_images": n_images,
            "n_parsed": n_parsed,
            "luminance": lum_counts,
            "top_palettes": top_palettes,
            "top_moods": top_moods,
            "top_objects": top_objects,
            "top_brands": top_brands,
            "pass_rate_pct": round(pass_count / max(pass_count + fail_count, 1) * 100, 1),
        },
        "vs_last_week": {
            "delta_published": delta,
            "trend": trend,
        },
        "insight": insights,
    }


def _hex_to_rgb(hex_str):
    """Parse '#aabbcc' to (r,g,b). Returns None on bad input."""
    if not hex_str or not isinstance(hex_str, str):
        return None
    s = hex_str.lstrip("#")
    if len(s) != 6:
        return None
    try:
        return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _cluster_ig_captions(this_week, prev_week):
    """Lightweight topic clustering of captions without an LLM.

    Uses curated keyword buckets for Swing Shack's content pillars:
      - equipment (fitting, clubs, driver, irons, wedges, takomo, sub-70, srixon, mileseey)
      - coaching (coach, lesson, tempo, slice, hook)
      - trackman (trackman, data, numbers, launch)
      - promo (membership, price, deal, sale, demo)
      - social (reels, story, weekend, sunday, friday)
      - general (anything else)
    """
    buckets = {
        "equipment": [],
        "coaching": [],
        "trackman": [],
        "promo": [],
        "social": [],
        "general": [],
    }

    def _classify(text):
        t = (text or "").lower()
        if any(k in t for k in ["fitting", "fitted", "clubs", "driver", "irons", "wedge", "takomo", "sub 70", "sub-70", "srixon", "mileseey", "taylormade", "titleist"]):
            return "equipment"
        if any(k in t for k in ["coach", "lesson", "tempo", "slice", "swing fix"]):
            return "coaching"
        if any(k in t for k in ["trackman", "launch monitor", "ball speed", "numbers"]):
            return "trackman"
        if any(k in t for k in ["membership", "price", "deal", "sale", "demo", "r250", "r2,500"]):
            return "promo"
        if any(k in t for k in ["reel", "reels", "story", "weekend", "sunday", "friday", "saturday"]):
            return "social"
        return "general"

    for p in (this_week or []):
        caption = p.get("caption_preview") or p.get("caption") or ""
        b = _classify(caption)
        buckets[b].append({
            "ts": p.get("publish_timestamp") or p.get("publishDate") or p.get("scheduled_date") or p.get("generated"),
            "preview": caption[:120],
        })

    summary = [{"topic": k, "count": len(v), "examples": v[:2]} for k, v in buckets.items() if v]
    summary.sort(key=lambda x: -x["count"])

    return {
        "primary_topic": summary[0]["topic"] if summary else None,
        "buckets": summary,
    }



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
    "image_generate": lambda: generate_image(None),
    "weekly_report": weekly_report,
}


# ─── IMAGE GENERATION PROMPT BUILDER ───────────────────────────────────────

def generate_image(
    asset_id: Optional[str] = None,
    pillar_override: Optional[str] = None,
    platform_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a provider-ready structured image prompt spec for a campaign asset.

    Takes an optional asset_id to pull brand/pillar/platform context from the
    campaign data. Optional pillar_override and platform_override allow callers
    to specify content pillar and target platform directly without an asset.

    Returns a structured spec with all the information needed by any image-generation
    provider (Ideogram / DALL-E / Midjourney / Stable Diffusion).

    The actual API call to the provider is NOT made here — just the spec.
    When credentials arrive, swap the provider in asset-image-spec.json.
    """
    cd = _campaign_data()
    asset = None
    campaign_name = ""

    if asset_id:
        for cid, c in cd.get("campaigns", {}).items():
            if asset_id in (c.get("assets") or {}):
                asset = c["assets"][asset_id]
                campaign_name = c.get("identity", {}).get("name", cid)
                break

    # Load the image spec file
    spec_path = _runtime_data_file("asset-image-spec.json")
    spec = _read_json(spec_path) or {}

    # Resolve pillar
    pillars_p = spec.get("pillars") or {}

    # Resolve pillar — prefer override, then asset, then default education
    if pillar_override:
        pillar_key = pillar_override.lower().strip()
    else:
        pillar_key = ((asset or {}).get("pillarName") or (asset or {}).get("pillar") or "education").lower().strip()
    pillar_map = {
        "education & authority": "education",
        "education": "education",
        "club fitting": "club-fitting",
        "club-fitting": "club-fitting",
        "community": "community",
        "events": "events",
        "offer": "events",
    }
    resolved_pillar = pillar_map.get(pillar_key, pillar_key)
    pillar_data = pillars_p.get(resolved_pillar) or pillars_p.get("education") or {}

    # Resolve platform — prefer override, then asset, then default instagram
    if platform_override:
        platform_raw = platform_override
    else:
        platform_raw = ((asset or {}).get("platform") or (asset or {}).get("integration", "instagram"))
    platform_key = platform_raw.lower().strip()
    platforms_p = spec.get("platforms") or {}
    platform_data = platforms_p.get(platform_key) or platforms_p.get("instagram") or {}

    # Resolve brand
    brand = "Swing Shack"
    if asset:
        for cid, c in cd.get("campaigns", {}).items():
            if asset_id in (c.get("assets") or {}):
                brand = c.get("identity", {}).get("brand") or c.get("identity", {}).get("business") or "Swing Shack"
                break

    # Resolve provider (default: ideogram — swap via spec when creds arrive)
    provider = spec.get("provider_default", "ideogram")
    provider_tpl = spec.get("provider_templates", {}).get(provider, spec.get("provider_templates", {}).get("ideogram", {}))

    # Build the base prompt from asset context
    asset_name = (asset.get("name") or "") if asset else ""
    asset_caption = (asset.get("caption") or "") if asset else ""
    visual_brief = (asset.get("visualBrief") or asset.get("imagePrompt") or "") if asset else ""
    hook_text = (asset.get("hookText") or "") if asset else ""

    # Select pillar model hint
    pillar_hints = pillar_data.get("model_hints", [])
    model_hint = pillar_hints[0] if pillar_hints else "professional golf photography"

    # Build the subject line
    subject_parts = []
    if hook_text and len(hook_text) > 3:
        subject_parts.append(f"'{hook_text}' moment")
    if asset_name and asset_name != asset_id:
        subject_parts.append(asset_name)
    if visual_brief and len(visual_brief) > 5:
        subject_parts.append(visual_brief)
    if not subject_parts:
        subject_parts.append(f"{brand} · {resolved_pillar.replace('-', ' ')} content")

    subject_line = ", ".join(subject_parts)

    # Assemble the full prompt text
    prompt_parts = [
        pillar_data.get("example_prompt_fragment", ""),
        subject_line,
        model_hint,
        pillar_data.get("composition", {}).get("background", ""),
    ]
    full_prompt_text = " | ".join([p for p in prompt_parts if p])

    # Wrap for each provider
    providers_out = {}
    for prov_key, prov_tpl in spec.get("provider_templates", {}).items():
        ar = platform_data.get("aspect_ratio", "1:1")
        ar_map = prov_tpl.get("aspect_ratio_map", {})
        ar_flag = ar_map.get(ar, ar_map.get("1:1", ar))

        neg_hint = prov_tpl.get("negative_hint", "")
        prov_prompt = (
            (prov_tpl.get("prompt_prefix", "") or "") +
            full_prompt_text +
            (prov_tpl.get("prompt_suffix", "") or "") +
            neg_hint +
            (" " + ar_flag if ar_flag else "")
        )
        providers_out[prov_key] = {
            "provider": prov_key,
            "display_name": prov_tpl.get("name", prov_key),
            "prompt": prov_prompt.strip(),
            "aspect_ratio": ar,
            "aspect_ratio_flag": ar_flag,
            "style_presets": prov_tpl.get("style_presets", []),
        }

    # Negative prompts per pillar
    neg_parts = pillar_data.get("negative_prompts", spec.get("pillars", {}).get("education", {}).get("negative_prompts", []))
    negative_prompt = " | ".join(neg_parts) if neg_parts else ""

    # Color keywords
    color_keywords = pillar_data.get("color_keywords", [])

    # CTA placeholder if relevant
    cta_placeholder = asset.get("cta", "") if asset else ""
    caption_placeholder = asset_caption[:200] if asset_caption else ""

    return {
        "ok": True,
        "ts": _now_iso(),
        "asset_id": asset_id,
        "campaign": campaign_name,
        "brand": brand,
        "pillar": resolved_pillar,
        "pillar_label": pillar_data.get("label", resolved_pillar),
        "platform": platform_key,
        "platform_config": {
            "aspect_ratio": platform_data.get("aspect_ratio", "1:1"),
            "aspect_px": platform_data.get("aspect_px", "1080x1080"),
            "text_safety_zone": platform_data.get("text_safety_zone", "center 70%"),
            "use_cases": platform_data.get("use_cases", []),
        },
        "tone": pillar_data.get("tone", "professional"),
        "color_keywords": color_keywords,
        "subject": subject_line,
        "prompt_parts": {
            "pillar_fragment": pillar_data.get("example_prompt_fragment", ""),
            "subject": subject_line,
            "model_hint": model_hint,
            "background": pillar_data.get("composition", {}).get("background", ""),
        },
        "negative_prompt": negative_prompt,
        "composition": pillar_data.get("composition", {}),
        "providers": providers_out,
        "reference_prompt": providers_out.get(provider, {}).get("prompt", full_prompt_text),
        "provider_used": provider,
        "brand_voice_notes": spec.get("brand_voice_for_images", {}),
        "metadata": {
            "asset_name": asset_name,
            "caption_preview": caption_placeholder[:120],
            "cta_placeholder": cta_placeholder[:80],
            "hook_text": hook_text[:120] if hook_text else None,
            "note": "Swap provider_key in provider_templates to switch Ideogram/DALL-E/MJ/SD. Actual API call pending creds."
        },
    }
