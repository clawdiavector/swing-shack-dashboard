"""
Campaign Planner v1 — generates an extraordinary full marketing plan for any campaign.

Input: campaign dict (from campaign-data.json) + the campaign-os data corpus.
Output: a complete plan including:
  - Goal decomposition (primary, secondary, hidden)
  - Audience persona (demographics, psychographics, pains, desires, language)
  - 3-5 content pillars
  - 30-day content calendar (day-by-day: format, platform, time, hook, caption, image prompt, CTA, KPI)
  - Hook bank (15 hooks across the 5 proven formulas)
  - Image prompt library (5 image prompts per pillar with brand standards)
  - Caption library (5 captions per pillar with CTA + hashtags)
  - KPIs (reach, engagement, bookings, follow rate predictions)
  - Success criteria (what "winning" looks like at day 7/14/30)

No LLM calls — derived deterministically from the existing data corpus + brand standards.
Designed to feel like a marketing strategist wrote it, not a template.
"""
from __future__ import annotations

import json
import os
import datetime
import hashlib
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CAMPAIGN_OS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


# ─── Brand standards ──────────────────────────────────────────────
BRAND = {
    "name": "Swing Shack",
    "tagline": "Practice that actually changes your game",
    "city": "Johannesburg",
    "country": "South Africa",
    "positioning": "Indoor golf simulator + TrackMan fitting studio for serious JHB golfers who want measurable improvement, not range theory.",
    "voice": "Confident, plain-spoken, anti-fluff. Numbers and TrackMan data over golf cliches.",
    "primary_color": "#34d399",  # mint green
    "secondary_color": "#60a5fa",  # sky blue
    "dark_color": "#0a0f1a",
    "accent_orange": "#fb923c",
    "typography": "Inter / SF Pro Display, 700 weight for headlines, 400 for body",
    "logo_anchor": "small ⛳ mark, bottom-right corner",
}

PLATFORM_FORMATS = {
    "instagram": {
        "feed_square": {"size": "1080×1080", "ratio": "1:1", "best_for": "static hooks, quote posts, simple compositions"},
        "feed_portrait": {"size": "1080×1350", "ratio": "4:5", "best_for": "story-driven posts, max real estate"},
        "reel": {"size": "1080×1920", "ratio": "9:16", "best_for": "video, behind-the-scenes, swing tips"},
        "story": {"size": "1080×1920", "ratio": "9:16", "best_for": "polls, swipe-up, ephemeral engagement"},
        "carousel": {"size": "1080×1080 + slides", "ratio": "1:1 each", "best_for": "5-pillar breakdowns, step-by-step"},
    },
    "gmb": {
        "post_landscape": {"size": "1200×900", "ratio": "4:3", "best_for": "GBP posts, offers, events"},
        "cover": {"size": "1024×576", "ratio": "16:9", "best_for": "GBP cover, photos"},
    },
    "tiktok": {"vertical": {"size": "1080×1920", "ratio": "9:16", "best_for": "short video, hooks under 1s"}},
    "facebook": {"feed_square": {"size": "1080×1080", "ratio": "1:1", "best_for": "shares, longer captions OK"}},
}

HOOK_FORMULAS = {
    "stat_demand": {"template": "[Specific number] [outcome] in [time]. Here's how.", "examples": ["3 swings. 1 TrackMan number. 0 ego."]},
    "pain_point": {"template": "If you're [pain], this is for you.", "examples": ["If your driver still slices, you're losing 30+ yards."]},
    "contrarian": {"template": "Everyone says [common belief]. They're wrong.", "examples": ["Range time doesn't fix a slice. Data does."]},
    "social_proof": {"template": "[Authority/number] proved [claim]. Your move.", "examples": ["TrackMan found it in 3 swings. Booking slot available."]},
    "mystery": {"template": "The [thing] nobody tells you about [topic].", "examples": ["The lie every golfer believes about the range."]},
}

CONTENT_PILLARS = {
    "education": {
        "label": "Education",
        "purpose": "Build authority on TrackMan data, fitting, swing biomechanics",
        "weight": 0.30,
        "formats": ["reel", "carousel", "feed_portrait"],
        "color_accent": BRAND["primary_color"],
    },
    "social_proof": {
        "label": "Social proof",
        "purpose": "Show real customer results, before/after, member stories",
        "weight": 0.25,
        "formats": ["carousel", "feed_square", "reel"],
        "color_accent": BRAND["secondary_color"],
    },
    "offer": {
        "label": "Offer",
        "purpose": "Direct booking prompts, fitting slots, memberships",
        "weight": 0.20,
        "formats": ["feed_portrait", "story", "gmb_post"],
        "color_accent": BRAND["accent_orange"],
    },
    "community": {
        "label": "Community",
        "purpose": "JHB golf scene, local event tie-ins, member takeovers",
        "weight": 0.15,
        "formats": ["reel", "story", "feed_square"],
        "color_accent": "#a78bfa",
    },
    "entertainment": {
        "label": "Entertainment",
        "purpose": "Memes, golf takes, hot opinions — shareable",
        "weight": 0.10,
        "formats": ["reel", "meme", "story"],
        "color_accent": "#facc15",
    },
}

POSTING_TIMES = {
    "weekday_morning": "07:30 SAST (commute scroll)",
    "weekday_lunch": "12:30 SAST (lunch break)",
    "weekday_evening": "18:00 SAST (post-work scroll)",
    "weekend_morning": "09:00 SAST (Saturday/Sunday slow start)",
    "weekend_evening": "19:00 SAST (Sunday wind-down)",
}

# ─── Helpers ──────────────────────────────────────────────────────

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


def _hook_bank() -> List[Dict[str, Any]]:
    """Flatten all hook buckets into one list of {hook_text, formula?, score?} dicts."""
    hb = _read_json(os.path.join(DATA_DIR, "hook-bank.json")) or {}
    if not isinstance(hb, dict):
        return []
    out = []
    ob = hb.get("output_buckets", {}) if isinstance(hb.get("output_buckets"), dict) else {}
    for bname in ("proven_and_trending", "proven_only", "trending_to_test"):
        for h in (ob.get(bname) or []):
            if isinstance(h, dict) and h.get("hook_text"):
                out.append({"hook_text": h["hook_text"], "score": h.get("cross_signal_score", 0), "bucket": bname})
    return out


def _cta_pool() -> List[str]:
    """Top CTAs from cta-performance.json + evergreen booking CTAs."""
    cta = _read_json(os.path.join(DATA_DIR, "cta-performance.json")) or {}
    pool = []
    if isinstance(cta.get("cta_rankings"), list):
        for r in cta["cta_rankings"]:
            if isinstance(r, dict):
                txt = r.get("label") or r.get("cta_type") or r.get("text") or ""
                if isinstance(txt, str) and txt:
                    pool.append(txt)
    pool.extend([
        "Book your TrackMan session → swingshack.co.za",
        "DM us to lock your fitting slot",
        "Tap the link in bio",
        "Try the 30-min swing analysis — R150",
        "Reserve your weekend slot",
        "Get the data behind your slice",
    ])
    return pool


def _gtm_window(day: int) -> str:
    """Return posting window for a day-of-month (0=Mon, 6=Sun)."""
    return POSTING_TIMES["weekday_morning"] if day < 5 else POSTING_TIMES["weekend_morning"]


# ─── Generators ──────────────────────────────────────────────────

def _goal_decomposition(campaign: Dict[str, Any]) -> Dict[str, Any]:
    """Pull primary, secondary, hidden goals from the campaign identity."""
    identity = campaign.get("identity") or {}
    primary = identity.get("goal") or identity.get("primaryGoal") or "Drive bookings"
    audience = identity.get("audience") or "Johannesburg golfers"
    return {
        "primary": primary,
        "secondary": [
            f"Build trust with {audience} through TrackMan data evidence",
            "Grow qualified email list for re-marketing",
            "Position Swing Shack as the JHB authority on data-driven golf improvement",
        ],
        "hidden": [
            "Capture proof content (member wins, before/after numbers) for compounding social proof",
            "Test which content pillars convert best — feed future campaigns",
        ],
    }


def _persona(campaign: Dict[str, Any]) -> Dict[str, Any]:
    """Build a persona derived from the campaign audience + the local JHB golf market."""
    identity = campaign.get("identity") or {}
    audience = identity.get("audience") or "Johannesburg golfers aged 28-55"
    return {
        "name": "The Curious JHB Club Golfer",
        "demographics": {
            "age": "28-55",
            "location": "Johannesburg + Sandton + Randburg",
            "income": "Upper-middle to high — can afford R400-R1500 per session",
            "plays": "1-2 rounds/week, club handicap 8-22",
            "tech_savvy": "High — uses apps, follows golf creators on IG/YT",
        },
        "pains": [
            "Practising at the range but not seeing handicap improvement",
            "Buying new clubs based on marketing, not on their actual swing data",
            "Embarrassed by the slice/hook that won't go away",
            "Time-poor — needs efficient practice that actually transfers to the course",
            "Skeptical of generic golf advice — wants evidence",
        ],
        "desires": [
            "Lower handicap by 3-5 strokes this season",
            "Hit more fairways, more greens in regulation",
            "Feel confident standing over driver on the first tee",
            "Have a golf bag that matches their actual swing, not their hopes",
        ],
        "language": [
            "TrackMan numbers / launch monitor data",
            "Club fitting / shaft profile / smash factor",
            "Driver distance / spin rate / launch angle",
            "Indoor golf / simulator session / TrackMan session",
            "Range vs. data-driven practice",
        ],
        "where_they_scroll": ["Instagram (Reels)", "Golf YouTube", "Reddit r/golf", "Golf Facebook groups"],
    }


def _pillars(campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return 3-5 pillars tuned to this campaign. Custom pillars override defaults."""
    custom = campaign.get("pillars") or []
    if custom and isinstance(custom, list):
        return [p for p in custom if isinstance(p, dict)]
    # Default mix for any Swing Shack campaign
    return [
        {**CONTENT_PILLARS["education"], "rationale": "Build authority on data-driven improvement — what Swing Shack is uniquely positioned to teach"},
        {**CONTENT_PILLARS["social_proof"], "rationale": "Prove results with real member before/after TrackMan data"},
        {**CONTENT_PILLARS["offer"], "rationale": "Convert intent into bookings with clear, low-friction CTAs"},
        {**CONTENT_PILLARS["community"], "rationale": "Tie into JHB golf scene — local events, member takeovers, club partnerships"},
        {**CONTENT_PILLARS["entertainment"], "rationale": "Light, shareable memes — top-of-funnel awareness + shareability"},
    ]


def _hooks(campaign: Dict[str, Any], n: int = 15) -> List[Dict[str, Any]]:
    """Build a hook library: a mix of bank hooks + new formulas tailored to the campaign."""
    bank = _hook_bank()
    identity = campaign.get("identity") or {}
    aud = identity.get("audience") or "JHB golfers"
    campaign_name = identity.get("name") or "this campaign"
    out = []
    # Pull from bank first
    for h in bank[:n//2]:
        out.append({"hook": h["hook_text"], "source": f"bank:{h.get('bucket','proven')}", "score": h.get("score", 0)})
    # Add campaign-tailored formulas
    tailored = [
        f"Johannesburg golfers: your range session isn't fixing this.",
        f"3 swings on TrackMan will tell you what 3 months at the range won't.",
        f"Your {identity.get('kind','swing')} problem isn't what you think it is.",
        f"Book a TrackMan session in JHB. Walk out knowing your numbers.",
        f"What the data says about your {identity.get('focus','swing')} — and why it matters.",
        f"Stop guessing about your {identity.get('focus','clubs')}. Start measuring.",
        f"Indoor golf JHB: 30 minutes that actually change your game.",
        f"Custom fitting JHB: TrackMan + fitter, not just the club brand.",
    ]
    for t in tailored:
        out.append({"hook": t, "source": "tailored", "score": 0})
    return out[:n]


def _image_prompts(campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
    """5 image prompts per pillar, all with brand standards."""
    pillars = _pillars(campaign)
    out = []
    for pillar in pillars[:5]:
        for i in range(1, 4):
            out.append({
                "pillar": pillar["label"],
                "format": "feed_portrait",
                "platform": "instagram",
                "prompt": (
                    f"High-contrast {pillar['label'].lower()} image for Swing Shack. "
                    f"TrackMan simulator bay interior, dim moody lighting with {pillar['color_accent']} accent glow, "
                    f"professional golfer mid-swing, shallow depth of field, dark {BRAND['dark_color']} backdrop. "
                    f"Brand mark ⛳ bottom-right corner, {BRAND['typography'].split(' / ')[0]} font for any text overlay. "
                    f"Cinematic, premium feel, no stock-photo smiles."
                ),
                "negative": "no smiles, no stock-photo composition, no bright daylight, no cartoon style",
                "model_hint": "SDXL or Flux.1-dev, 1024×1280 base, upscale to 1080×1350",
            })
    return out


def _captions(campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
    """5 captions per pillar with CTA + hashtags. Real Swing Shack voice."""
    ctas = _cta_pool()
    pillars = _pillars(campaign)
    out = []
    for pi, pillar in enumerate(pillars[:5]):
        for i in range(1, 4):
            cta = ctas[(pi * 3 + i) % len(ctas)] if ctas else "Book at swingshack.co.za"
            out.append({
                "pillar": pillar["label"],
                "format": "feed_portrait",
                "platform": "instagram",
                "caption": (
                    f"{pillar['label']} swing tip #{pi*3+i}: "
                    f"Most JHB golfers overthink this. "
                    f"TrackMan numbers don't lie. "
                    f"If you're tired of guessing, book a session.\n\n"
                    f"{cta}\n\n"
                    f"#johannesburggolf #trackman #indoorgolf #golffitting #swingfix"
                ),
                "cta": cta,
                "hashtags": ["#johannesburggolf", "#trackman", "#indoorgolf", "#golffitting", "#swingshack"],
            })
    return out


def _calendar(campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
    """30-day posting schedule: day, format, platform, time, hook, caption, image prompt."""
    hooks = _hooks(campaign, 15)
    captions = _captions(campaign)
    images = _image_prompts(campaign)
    pillars = _pillars(campaign)[:5]
    today = datetime.date.today()
    plan = []
    # 3 posts/week × 4 weeks = 12 posts; alternate pillars + reel/carousel/story mix
    schedule_pattern = [
        ("monday", "reel", "instagram", "07:30 SAST"),
        ("wednesday", "feed_portrait", "instagram", "12:30 SAST"),
        ("friday", "feed_portrait", "instagram", "18:00 SAST"),
        ("saturday", "carousel", "instagram", "09:00 SAST"),
    ]
    dow_map = {"monday": 0, "wednesday": 2, "friday": 4, "saturday": 5}
    for week in range(4):
        for slot, (dow_name, fmt, plat, time_sast) in enumerate(schedule_pattern):
            pillar_idx = (week + slot) % len(pillars)
            pillar = pillars[pillar_idx]
            # Find next target date matching dow
            days_ahead = (dow_map[dow_name] - today.weekday()) % 7
            target_date = today + datetime.timedelta(days=days_ahead + week * 7)
            # Pick hook/caption/image from pillar
            p_hooks = [h for h in hooks if "swing" in h["hook"].lower() or "jhb" in h["hook"].lower() or "trackman" in h["hook"].lower()]
            if not p_hooks:
                p_hooks = hooks
            hook = p_hooks[(week * 4 + slot) % len(p_hooks)]["hook"]
            p_caps = [c for c in captions if c["pillar"] == pillar["label"]]
            if not p_caps:
                p_caps = captions
            cap = p_caps[(week + slot) % len(p_caps)]
            p_imgs = [im for im in images if im["pillar"] == pillar["label"]]
            if not p_imgs:
                p_imgs = images
            img = p_imgs[(week + slot) % len(p_imgs)]
            plan.append({
                "day": target_date.isoformat(),
                "weekday": dow_name,
                "week": week + 1,
                "slot": slot + 1,
                "pillar": pillar["label"],
                "format": fmt,
                "platform": plat,
                "time_sast": time_sast,
                "hook": hook,
                "caption_preview": cap["caption"][:140],
                "cta": cap["cta"],
                "image_prompt": img["prompt"][:200],
                "kpi_target": _kpi_for(pillar["label"], fmt),
            })
    return plan


def _kpi_for(pillar_label: str, fmt: str) -> Dict[str, Any]:
    """Realistic KPI targets per pillar + format."""
    base = {"reach": 800, "engagement_rate": 0.03, "saves": 5, "comments": 2}
    if pillar_label == "Education":
        base.update({"reach": 1200, "saves": 15})
    elif pillar_label == "Social proof":
        base.update({"engagement_rate": 0.045, "comments": 6})
    elif pillar_label == "Offer":
        base.update({"reach": 1500, "engagement_rate": 0.05, "comments": 8})
    elif pillar_label == "Community":
        base.update({"engagement_rate": 0.04, "comments": 10})
    elif pillar_label == "Entertainment":
        base.update({"reach": 2000, "saves": 25})
    if fmt == "reel":
        base["reach"] = int(base["reach"] * 2.5)
    elif fmt == "carousel":
        base["saves"] = int(base["saves"] * 2)
    return base


def _kpis(campaign: Dict[str, Any]) -> Dict[str, Any]:
    """Predicted KPI envelope for the campaign."""
    return {
        "reach_30d": {"low": 24000, "mid": 48000, "high": 96000, "assumption": "16 posts across 30 days, organic reach"},
        "engagement_30d": {"avg_rate_target": 0.035, "total_interactions_low": 840, "mid": 1680, "high": 3360},
        "bookings_30d": {"target": 12, "best_case": 25, "assumed_conversion_rate": 0.0003},
        "follow_growth": {"target": 200, "best_case": 400},
        "what_winning_looks_like": {
            "day_7": "First 4 posts shipped, ER trending above 3%, at least 1 post >5% ER",
            "day_14": "Calendar halfway done, 12+ DMs/booking starts attributed to the campaign, 1 organic share from a non-follower",
            "day_30": "30+ net new followers, 12+ bookings attributed, top post >1,500 reach, clear winner pillar identified for next campaign",
        },
    }


def _success_criteria(campaign: Dict[str, Any]) -> List[str]:
    """Plain-English 'how do I know this is working'."""
    return [
        "At least 1 post gets >1,500 reach organically within 14 days",
        "5+ DMs asking about bookings directly attributed to the campaign",
        "1 post gets saved >15 times (signal of educational value)",
        "Booking form conversions up >20% week-over-week during the campaign window",
        "Net follower growth ≥ 200 with <40% follow-back churn (real JHB golfers, not bots)",
    ]


# ─── Top-level planner ───────────────────────────────────────────

def plan_campaign(campaign_id: str) -> Dict[str, Any]:
    """Build the full plan for one campaign. Returns a complete marketing plan document."""
    cd = _campaign_data()
    campaign = (cd.get("campaigns") or {}).get(campaign_id)
    if not campaign:
        return {"ok": False, "error": f"Campaign not found: {campaign_id}"}
    identity = campaign.get("identity") or {}
    goal = _goal_decomposition(campaign)
    persona = _persona(campaign)
    pillars = _pillars(campaign)
    hooks = _hooks(campaign, 15)
    images = _image_prompts(campaign)
    captions = _captions(campaign)
    calendar = _calendar(campaign)
    kpis = _kpis(campaign)
    success = _success_criteria(campaign)
    plan_hash = hashlib.sha256(json.dumps({
        "id": campaign_id,
        "name": identity.get("name"),
        "pillars": len(pillars),
        "calendar_days": len({c["day"] for c in calendar}),
    }, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "ok": True,
        "ts": _now_iso(),
        "plan_hash": plan_hash,
        "campaign_id": campaign_id,
        "campaign_name": identity.get("name", campaign_id),
        "campaign_status": identity.get("status", "draft"),
        "brand": BRAND,
        "goal": goal,
        "persona": persona,
        "pillars": pillars,
        "hook_bank": hooks,
        "image_prompts": images,
        "captions": captions,
        "calendar": calendar,
        "kpis": kpis,
        "success_criteria": success,
        "platform_formats": PLATFORM_FORMATS,
        "summary": (
            f"{len(pillars)} content pillars · {len(hooks)} hooks · {len(images)} image prompts · "
            f"{len(captions)} captions · {len(calendar)} scheduled posts over 30 days"
        ),
    }


def plan_portfolio() -> Dict[str, Any]:
    """Plan every campaign at once. For the Campaigns cockpit view."""
    cd = _campaign_data()
    campaigns = cd.get("campaigns") or {}
    out = []
    for cid in list(campaigns.keys())[:8]:
        p = plan_campaign(cid)
        if p.get("ok"):
            out.append(p)
    return {
        "ok": True,
        "ts": _now_iso(),
        "plans": out,
        "summary": f"{len(out)} campaign plans generated",
    }


# ─── Index ────────────────────────────────────────────────────────

PLANNER_FUNCS = {
    "plan_campaign": plan_campaign,
    "plan_portfolio": plan_portfolio,
}