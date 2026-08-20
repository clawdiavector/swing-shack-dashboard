"""campaign_brief.py — full campaign brief generator for from-idea pipeline.

Built 2026-08-20. Closes the gap on the 'one-button does everything'
campaign brief that a real agency brief would have. For each channel
the brief includes:
  - Full caption (already produced by gbp_daily_poster.py / the
    from-idea route's per-channel prompts)
  - Image prompt (model suggestion, prompt text, aspect ratio,
    text overlay or 'no overlay')
  - UTM link (per-channel template with source/medium/campaign/content)
  - Hook formula (one of: question, bold_claim, story_seed, contrarian, list)
  - Paid ad budget recommendation (best-practice for the brand's market)
  - Expected outcome (engagement rate, CTR, reach estimate based on
    industry baselines for the channel + brand size)

The full brief is computed server-side once and persisted on the
campaign identity so the user can come back and find it later (the
review queue shows a 'see brief' link per asset).

The brief is read-only — destructive writes (live publishes) stay
gated behind the per-asset approve+schedule flow per
agent-destructive-write-discipline.
"""

from __future__ import annotations

import datetime as _dt
import re as _re
import urllib.parse as _urlparse
from typing import Optional


# ── UTM template per channel ────────────────────────────────────────
# Best-practice UTM convention for South African market. Source tells
# analytics where the click came from (gmb/local, instagram, etc.),
# medium tells what kind (organic, paid, bio-link), campaign ties back
# to the campaign_id, content lets you A/B variations on the same source.


def build_utm(channel: str, *, campaign_id: str, content_tag: Optional[str] = None,
              domain: str = "swingshack.co.za") -> dict:
    """Build the per-channel UTM link for the campaign.

    Returns: { url, tracking_url (with UTM), source, medium, campaign, content }
    All channels point to a single destination (the booking page) since
    the builder's job is to drive bookings. Add destination overrides per
    channel later if needed (e.g. a TikTok creator profile link).
    """
    base_url = f"https://{domain}/book"
    # Strip the campaign_id down to alphanumeric + dash (UTM safe)
    safe_cid = _re.sub(r'[^a-z0-9-]', '-', campaign_id.lower()).strip('-')[:90]

    channel_config = {
        "gmb":       {"source": "gmb",            "medium": "local_post", "default_content": "cta-swing-analysis"},
        "instagram": {"source": "instagram",       "medium": "social",     "default_content": "link_in_bio"},
        "facebook":  {"source": "facebook",        "medium": "social",     "default_content": "post_caption"},
        "x":         {"source": "twitter",         "medium": "social",     "default_content": "tweet_link"},
        "tiktok":    {"source": "tiktok",          "medium": "social",     "default_content": "bio_link"},
    }.get(channel, {"source": channel, "medium": "social", "default_content": "post_link"})

    content = content_tag or channel_config["default_content"]
    qs = {
        "utm_source": channel_config["source"],
        "utm_medium": channel_config["medium"],
        "utm_campaign": safe_cid,
        "utm_content": content,
    }
    tracking_url = base_url + "?" + _urlparse.urlencode(qs)
    return {
        "url": base_url,
        "tracking_url": tracking_url,
        "source": channel_config["source"],
        "medium": channel_config["medium"],
        "campaign": safe_cid,
        "content": content,
    }


# ── Image prompt per channel ────────────────────────────────────────
# Each channel gets a recommended model + a per-channel-focused prompt +
# aspect ratio. Models: Nano Banana = default; Gemini 3 Pro = hero
# compositions; Ideogram 3 = text-heavy; FLUX 1.1 = humans; Grok for X.

_IMAGE_MODELS_BY_CHANNEL = {
    "instagram": "nano-banana",  # moody, editorial, lifestyle
    "facebook": "nano-banana",   # similar editorial, larger text tolerance
    "gmb": "gemini-3-pro",       # hero/landscape — storefront + signage
    "tiktok": "grok",            # punchy, contrasty, attention-grabbing
    "x": "grok",                 # simple graphic / quote
}


def image_brief(channel: str, idea: str, *, brand_id: str = "swing-shack",
                neighbourhood: Optional[str] = None, pillar: Optional[str] = None) -> dict:
    """Return an image brief for one channel.

    The user runs the prompt through the model in the Image Lab (or via
    /api/image/brand-dna for brand-aware composition). The model choice
    is per-channel so we don't ship moody editorial stills to X (which
    needs readable quote cards) or punchy TikTok thumbnails to GBP
    (which needs heros + signage).
    """
    model = _IMAGE_MODELS_BY_CHANNEL.get(channel, "nano-banana")
    aspect = {
        "instagram": "4:5",    # vertical, maximum in-feed real estate
        "tiktok":    "9:16",   # full-vertical
        "facebook":  "1:1",    # square, works in feed + sidebar
        "gmb":       "4:3",    # landscape hero
        "x":         "16:9",   # landscape card
    }.get(channel, "1:1")

    # Per-channel prompt scaffolding — the brand_dna + bible overlays
    # render-time overlays (logo placement + colour palette + bay refs).
    base_subject = idea.strip().rstrip(".").rstrip("?")
    prompts = {
        "instagram": (
            f"Editorial photograph inside a TrackMan-equipped indoor golf bay, "
            f"mid-swing overhead shot, warm lighting, ball-flight trail visible. "
            f"Subject: {base_subject}. "
            f"Tone: confident, premium, not stock-photo. "
            f"Composition: subject slightly right of centre, ball-flight left-to-right."
        ),
        "facebook": (
            f"Wide-angle indoor golf scene, golfer at the hitting area with a TrackMan "
            f"screen behind showing launch data. Subject: {base_subject}. "
            f"Inclusion: a partner / friend watching adds community feel. "
            f"Mood: warm, mid-day, inclusive."
        ),
        "gmb": (
            f"Photograph of the Swing Shack storefront + signage, clearly visible "
            f"and well-lit, OPEN sign. Subject: {base_subject}. "
            f"Layer text overlay top-left: 'Indoor Golf — Johannesburg'. "
            f"Bottom-right: 'Book R250' badge. "
            f"Local SEO priority — entrance + signage must be legible."
        ),
        "tiktok": (
            f"Vertical 9:16 frame, close-up of TrackMan screen showing launch "
            f"data + face angle, golfer's reaction visible behind. "
            f"Subject: {base_subject}. "
            f"Mood: punchy, contrasty, attention-grabbing. "
            f"Text overlays: hook on line 1, CTA on line 3."
        ),
        "x": (
            f"Clean quote-card composition, dark background, large readable "
            f"type: '{base_subject}'. "
            f"Bottom-right: Swing Shack mark. "
            f"Aesthetic: minimal, high-contrast, scannable in 0.5s."
        ),
    }
    return {
        "model": model,
        "prompt": prompts.get(channel, prompts["instagram"]),
        "aspect_ratio": aspect,
        "overlay_text": _suggest_overlay(channel, base_subject, neighbourhood),
        "negative_prompts": ["people with arms in pockets", "stock-photo smiles", "cluttered text", "watermarks"],
    }


def _suggest_overlay(channel: str, base_subject: str, neighbourhood: Optional[str]) -> dict:
    """Text overlay suggestions for the image — split by channel.
    'no overlay' for channels that keep captions fully in the caption
    (most editorial), 'forced overlay' for channels that demand in-image
    text (GBP needs signage, TikTok demands a hook)."""
    if channel == "gmb":
        return {"position": "top-left", "line_1": "Indoor Golf", "line_2": neighbourhood or "Johannesburg", "style": "bold sans-serif"}
    if channel == "tiktok":
        return {"position": "line 1 of 3", "line_1": base_subject[:50], "line_2": None, "style": "heavy contrast text"}
    if channel == "x":
        return {"position": "centered", "line_1": base_subject[:100], "line_2": "swingshack.co.za", "style": "minimal sans-serif"}
    return {"position": "none", "line_1": None, "line_2": None, "style": "captions carry the message"}


# ── Hook formula per channel ────────────────────────────────────────
# Hook formula taxonomy: question / bold_claim / story_seed / contrarian / list / stat.
# A/B test against your own historical winners + formula mixing.

_HOOK_FORMULAS = {
    "instagram": "bold_claim + story_seed",  # IG thrives on hook + soft follow
    "facebook":  "question + community ask",  # FB thrives on conversation starts
    "gmb":       "local-intent question",     # Google rewards local queries
    "tiktok":    "bold_claim + contrarian",    # TikTok demands a hook that earns the watch
    "x":         "punchy stat or list",       # X rewards dense single-pass reads
}


# ── Paid ad budget per channel ──────────────────────────────────────
# Best-practice for SA market. GBP local-intent posts are FREE — the
# only "spend" is the team's time to engage with reviews. Facebook +
# Instagram paid amplification is the cheapest reach. TikTok Spark Ads
# unlock the algorithm. X is expensive relative to the audience size
# for the brand, so we mark it as 'organic only by default'.

def paid_ad_plan(channel: str, *, brand_size: str = "local") -> dict:
    """Paid ad budget recommendation per channel for a local brand.

    Returns: {
      channel, recommended: bool, daily_budget_zar: float,
      objective: str, target: str, expected_reach: str, rationale
    }
    """
    plans = {
        "gmb": {
            "channel": "gmb",
            "recommended": False,
            "daily_budget_zar": 0,
            "objective": "organic local post + review engagement",
            "target": "local-intent searchers within 5km radius",
            "expected_reach": "5-20% of view-to-actions on the post",
            "rationale": "Google GBP local-intent posts are free; spend time on review replies + photo uploads instead.",
        },
        "instagram": {
            "channel": "instagram",
            "recommended": True,
            "daily_budget_zar": 150,
            "objective": "post engagement + profile visit",
            "target": "Johannesburg golf-curious, 25-55, interests ['golf', 'fitness', 'trackman']",
            "expected_reach": "1,200-3,500 reach per day at R150/day",
            "rationale": "Cheapest SA reach for golf/lifestyle. Boosted post + carousel both work well.",
        },
        "facebook": {
            "channel": "facebook",
            "recommended": True,
            "daily_budget_zar": 200,
            "objective": "post engagement + link click",
            "target": "Johannesburg 30-65, lookalike from page followers",
            "expected_reach": "1,500-4,000 reach per day at R200/day",
            "rationale": "FB algorithm favours longer captions + link clicks — perfect for free-swing-analysis CTAs.",
        },
        "tiktok": {
            "channel": "tiktok",
            "recommended": True,
            "daily_budget_zar": 250,
            "objective": "video views + profile visit",
            "target": "Johannesburg 18-40, interests ['golf', 'sport', 'lifestyle']",
            "expected_reach": "800-2,500 views per day at R250/day (Spark Ads)",
            "rationale": "TikTok Spark Ads unlock the algorithm — well worth R250/day for a 15s swing-data clip.",
        },
        "x": {
            "channel": "x",
            "recommended": False,
            "daily_budget_zar": 0,
            "objective": "organic tweet + hashtag",
            "target": "SA golf Twitter, #golfRSA, swing-data creators",
            "expected_reach": "200-1,000 organic impressions per tweet at this brand size",
            "rationale": "X is small in SA golf and paid X is expensive per impression. Organic-only by default unless you specifically want UGC creator collabs.",
        },
    }
    return plans.get(channel, plans["instagram"])


# ── Expected outcomes per channel ──────────────────────────────────
# Conservative ranges based on industry baselines (HubSpot 2024, Hootsuite,
# Rival IQ 2025). For a brand with <5K social followers in the SA golf
# market. Adjust upward if follower count > 20K.

def expected_outcomes(channel: str, *, cta: str = "") -> dict:
    """Industry-baseline expected outcomes per channel.

    Returns: { engagement_rate, ctr, expected_reach, expected_clicks,
    conversion_rate_estimate, expected_bookings }
    """
    outcomes = {
        "gmb": {
            "engagement_rate": "0.05-0.20 (call+website+directions)",
            "ctr": "n/a (calls/directions not link-driven)",
            "expected_reach": "100-300 local impressions/day",
            "expected_clicks": "5-15 website clicks/day",
            "conversion_rate_estimate": "5-10% of clicks → bookings",
            "expected_bookings": "0.3-1.5/day from GBP alone at this brand size",
        },
        "instagram": {
            "engagement_rate": "1.5-3.5%",
            "ctr": "0.8-2.0% on link-in-bio",
            "expected_reach": "20-40% of followers per post",
            "expected_clicks": "8-25 link-in-bio clicks per post",
            "conversion_rate_estimate": "3-7% of bio clicks → bookings",
            "expected_bookings": "0.2-1.7 per post (organic + R150 boost)",
        },
        "facebook": {
            "engagement_rate": "0.8-2.5%",
            "ctr": "1.0-2.5% on link post",
            "expected_reach": "30-60% of followers per post",
            "expected_clicks": "12-35 link clicks per post",
            "conversion_rate_estimate": "2-5% of clicks → bookings",
            "expected_bookings": "0.3-1.7 per post (organic + R200 boost)",
        },
        "tiktok": {
            "engagement_rate": "4-9%",
            "ctr": "0.5-1.5% on bio link",
            "expected_reach": "varies wildly; 500-50,000 views possible",
            "expected_clicks": "3-15 bio clicks per video",
            "conversion_rate_estimate": "2-6% of clicks → bookings",
            "expected_bookings": "0.1-1.0 per video (organic + R250 boost)",
        },
        "x": {
            "engagement_rate": "0.5-1.5%",
            "ctr": "1.5-3.5% on link tweet",
            "expected_reach": "200-1,500 impressions per tweet",
            "expected_clicks": "3-15 link clicks per tweet",
            "conversion_rate_estimate": "2-4% of clicks → bookings",
            "expected_bookings": "0.05-0.6 per tweet (organic only by default)",
        },
    }
    return outcomes.get(channel, outcomes["instagram"])


# ── Per-channel brief assembly ─────────────────────────────────────

def build_channel_brief(channel: str, *, idea: str, brand_id: str, campaign_id: str,
                        pillar: Optional[str] = None, neighbourhood: Optional[str] = None,
                        content_tag: Optional[str] = None, domain: Optional[str] = None) -> dict:
    """Compose a full brief per channel.

    Returns: {
      channel, image, utm, hook_formula, paid_plan, expected_outcome
    }
    The caption itself is generated by the route's per_channel_prompts
    (so the brief aligns with what's actually shipped).
    """
    dom = domain or ("swingshack.co.za" if brand_id == "swing-shack"
                     else ("sticksa.co.za" if brand_id == "stick" else "bagdropgolf.co.za"))
    return {
        "channel": channel,
        "image": image_brief(channel, idea, brand_id=brand_id,
                              neighbourhood=neighbourhood, pillar=pillar),
        "utm": build_utm(channel, campaign_id=campaign_id, content_tag=content_tag, domain=dom),
        "hook_formula": _HOOK_FORMULAS.get(channel, "bold_claim"),
        "paid_plan": paid_ad_plan(channel),
        "expected_outcome": expected_outcomes(channel),
    }


# ── Tracking sheet (Google Sheet-compatible) ────────────────────────

def tracking_sheet_rows(campaign_id: str, channels: list[str], *,
                         pillar: Optional[str] = None,
                         neighbourhood: Optional[str] = None) -> list[dict]:
    """Generate a tracking-sheet row per channel for the campaign.

    Returns: list of dicts whose keys are column headers you can paste
    straight into a Google Sheet / Excel. Columns:
      campaign_id, channel, asset_id, planned_date, utm_tracking_url,
      image_model, expected_ctr, expected_bookings, paid_recommended,
      paid_daily_zar, hook_formula
    """
    base_date = _dt.date.today()
    rows = []
    for i, ch in enumerate(channels):
        brief = build_channel_brief(ch, idea=campaign_id, brand_id="swing-shack",
                                     campaign_id=campaign_id, pillar=pillar,
                                     neighbourhood=neighbourhood)
        schedule_offset = {"gmb": 1, "instagram": 1, "facebook": 3, "tiktok": 2, "x": 4}.get(ch, 1)
        planned = base_date + _dt.timedelta(days=schedule_offset)
        rows.append({
            "campaign_id": campaign_id,
            "channel": ch,
            "asset_id": f"{campaign_id}-{ch}",
            "planned_date": planned.isoformat(),
            "utm_tracking_url": brief["utm"]["tracking_url"],
            "image_model": brief["image"]["model"],
            "image_aspect_ratio": brief["image"]["aspect_ratio"],
            "expected_ctr": brief["expected_outcome"]["ctr"],
            "expected_bookings": brief["expected_outcome"]["expected_bookings"],
            "paid_recommended": brief["paid_plan"]["recommended"],
            "paid_daily_zar": brief["paid_plan"]["daily_budget_zar"],
            "hook_formula": brief["hook_formula"],
            "overlay_required": "no" if brief["image"]["overlay_text"]["position"] == "none" else "yes",
        })
    return rows


def tracking_sheet_csv(campaign_id: str, channels: list[str], *,
                         pillar: Optional[str] = None,
                         neighbourhood: Optional[str] = None) -> str:
    """Generate a CSV string for the tracking sheet (paste-ready)."""
    import io, csv
    rows = tracking_sheet_rows(campaign_id, channels, pillar=pillar, neighbourhood=neighbourhood)
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()
