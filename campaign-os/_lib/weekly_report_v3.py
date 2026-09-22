"""weekly_report_v3.py — Weekly Marketing Report V3.5 (visual redesign + complete data).

Renderer-only. Sits on top of Reporting Intelligence V2.4.1 (frozen).

V3.5 changes vs V3.4:
  • Visual: HTML/PDF are a polished management document — header
    block, KPI cards, tables, side-by-side worked/needs-attention,
    action cards, NS target cards. No markdown artefacts in HTML.
  • Complete data: in addition to GA4 + Meta Ads, pulls Meta organic
    (Instagram + Facebook page), SEO (Ubersuggest via /api/seo/overview),
    and GBP for brands where applicable.
  • Same plain-English V3.4 wording, same period contract, same
    period-aware paid-media cache.
"""
from __future__ import annotations

import datetime
import html as _html
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Period-aware Instagram post lookup (V3.6).
import datetime as _dt_mod

# 'as_of' may be a date or datetime
def _parse_published_at(value) -> Optional[_dt_mod.datetime]:
    """Parse an ISO-8601 Instagram post timestamp into tz-aware UTC datetime."""
    if not value:
        return None
    if isinstance(value, _dt_mod.datetime):
        dt = value
    else:
        s = str(value).strip()
        try:
            s_clean = s.replace("Z", "+00:00") if s.endswith("Z") else s
            dt = _dt_mod.datetime.fromisoformat(s_clean)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt_mod.timezone.utc)
    return dt

def _in_report_week(value, cur_start: str, cur_end: str) -> bool:
    """True if a post timestamp falls inside the report week (inclusive)."""
    dt = _parse_published_at(value)
    if dt is None:
        return False
    try:
        start = _dt_mod.datetime.fromisoformat(cur_start).replace(
            tzinfo=_dt_mod.timezone.utc)
        end_excl = (_dt_mod.datetime.fromisoformat(cur_end)
                      + _dt_mod.timedelta(days=1)).replace(
                          tzinfo=_dt_mod.timezone.utc)
    except Exception:
        return False
    return start <= dt < end_excl

# ── data root / brand facts ─────────────────────────────────────

def _data_root() -> Path:
    env = os.environ.get("CAMPAIGN_OS_DATA_DIR")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent / "data"


def _load_brands() -> dict:
    for r in (_data_root(),
                Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data")):
        bp = r / "brands.json"
        if bp.is_file():
            try:
                return json.loads(bp.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {"brands": {}, "default_brand_id": "swing-shack"}


def _brand_canonical(bid: str) -> dict:
    brands = _load_brands()
    b = (brands.get("brands") or {}).get(bid) or {}
    raw_website = (b.get("website") or "").rstrip("/")
    website = raw_website
    for prefix in ("https://", "http://"):
        if website.startswith(prefix):
            website = website[len(prefix):]
    return {
        "brand_id": bid,
        "display_name": b.get("display_name") or bid,
        "tagline": b.get("tagline") or "",
        "voice_label": b.get("voice_label") or bid,
        "icon": b.get("icon") or "",
        "primary_color": b.get("primary_color") or "#1B1B1B",
        "accent_color": b.get("accent_color") or "#3a4151",
        "website": website,
        "ig_handle": b.get("instagram_handle") or "",
        "audience": b.get("audience") or "",
        "positioning": b.get("positioning") or "",
    }


# ── page metadata (so URLs work in any context) ─────────────────

def _page_meta(bid: str) -> str:
    """Base URL for permalink-based thumbnails + share-token generation."""
    p = os.environ.get("CAMPAIGN_OS_PUBLIC_URL")
    return p or "https://swing-shack-dashboard-production.up.railway.app"


# ── brand isolation ─────────────────────────────────────────────

def _validate_brand_isolation(bid: str, payload: Any
                                  ) -> Tuple[bool, List[str]]:
    facts = _brand_canonical(bid)
    brands = _load_brands()
    own = set()
    for s in (facts.get("display_name"), facts.get("ig_handle"),
                facts.get("website")):
        if s:
            own.add(s.lower())
    name_triggers: List[str] = []
    domain_triggers: List[str] = []
    for other_id, other_b in (brands.get("brands") or {}).items():
        if other_id == bid:
            continue
        s = other_b.get("display_name")
        if s and isinstance(s, str) and len(s) >= 4 and s.lower() not in own:
            name_triggers.append(s)
        ws = (other_b.get("website") or "")
        for prefix in ("https://", "http://"):
            if ws.startswith(prefix):
                ws = ws[len(prefix):]
        ws = ws.rstrip("/")
        if ws and ws.lower() not in own:
            domain_triggers.append(ws)
    if not name_triggers and not domain_triggers:
        return True, []
    text = json.dumps(payload, ensure_ascii=False, default=str)
    violations: List[str] = []
    for t in name_triggers:
        pattern = (r'"(?:path|url|page|account_id|page_id|ig_id|'
                    r'caption|name|title|domain|handle|ig_business|'
                    r'page_url|permalink|link|href|campaign_name|'
                    r'ig_username|source_caption|campaign_id)":\s*'
                    r'"[^"]*' + re.escape(t) + r'[^"]*"')
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(t)
    for t in domain_triggers:
        pattern = (r'"(?:path|url|page_url|link|href|domain|'
                    r'permalink|ig_url|fb_url)":\s*'
                    r'"[^"]*' + re.escape(t) + r'[^"]*"')
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(t)
    return (len(violations) == 0), violations


# ── period contract ─────────────────────────────────────────────

def _compute_periods(as_of: Optional[str] = None) -> Dict[str, str]:
    if as_of:
        try:
            anchor = datetime.date.fromisoformat(as_of)
        except (ValueError, TypeError):
            anchor = datetime.datetime.now(
                datetime.timezone.utc).date() - datetime.timedelta(days=1)
    else:
        anchor = datetime.datetime.now(
            datetime.timezone.utc).date() - datetime.timedelta(days=1)
    cur_end = anchor
    cur_start = anchor - datetime.timedelta(days=6)
    prev_end = cur_start - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=6)
    return {
        "data_complete_through": cur_end.isoformat(),
        "current_week_start": cur_start.isoformat(),
        "current_week_end": cur_end.isoformat(),
        "previous_week_start": prev_start.isoformat(),
        "previous_week_end": prev_end.isoformat(),
    }


def _fmt_period_label(iso_date: str) -> str:
    d = datetime.date.fromisoformat(iso_date)
    return f"{d.day} {d.strftime('%B')} {d.year}"


# ── canonical V2.4.1 read ──────────────────────────────────────

def _read_v24(bid: str, as_of: Optional[str] = None,
                cookie: Optional[str] = None) -> Dict[str, Any]:
    from _lib.reporting_intelligence import build_v24_brand_report
    periods = _compute_periods(as_of)
    try:
        r = build_v24_brand_report(bid, period_days=7, cookie=cookie) or {}
    except Exception as e:
        return {"error": str(e), "bid": bid, "periods": periods}
    r["__periods"] = periods
    r["__bid"] = bid
    return r


# ── V2.4.1 extractors ──────────────────────────────────────────

def _extract_kpi(v24: dict, label: str) -> Dict[str, Any]:
    for row in (v24.get("kpi_scorecard") or {}).get("rows") or []:
        if row.get("label", "").lower() == label.lower():
            return row
    return {}


def _paid_totals_from_campaigns(v24: dict) -> Dict[str, Any]:
    pm = v24.get("paid_media_v24") or {}
    cur = {"total_spend": 0.0, "total_impressions": 0.0,
            "total_reach": 0.0, "total_clicks": 0.0, "total_results": 0.0}
    prev = dict(cur)
    for c in (pm.get("per_campaign") or []):
        c_cur = c.get("current") or {}
        c_prev = c.get("previous") or {}
        cur["total_spend"] += float(c_cur.get("spend") or 0)
        cur["total_impressions"] += float(c_cur.get("impressions") or 0)
        cur["total_reach"] += float(c_cur.get("reach") or 0)
        cur["total_clicks"] += float(c_cur.get("clicks") or 0)
        prev["total_spend"] += float(c_prev.get("spend") or 0)
        prev["total_impressions"] += float(c_prev.get("impressions") or 0)
        prev["total_reach"] += float(c_prev.get("reach") or 0)
        prev["total_clicks"] += float(c_prev.get("clicks") or 0)
        pr = c.get("primary_result") or {}
        if (c.get("objective") == "OUTCOME_LEADS"
                and pr.get("primary_metric_label") == "Meta-reported leads"):
            pv = pr.get("primary_value")
            if isinstance(pv, (int, float)):
                cur["total_results"] += float(pv)
    return {"current_period": cur, "previous_period": prev}


def _compute_paid_efficiency(cur: dict, prev: dict) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    spend = cur.get("total_spend") or 0
    imp = cur.get("total_impressions") or 0
    clicks = cur.get("total_clicks") or 0
    out["ctr"] = (clicks / imp * 100.0) if imp else None
    out["cpc"] = (spend / clicks) if clicks else None
    out["cpm"] = (spend / imp * 1000.0) if imp else None
    return out


# ── North Stars ─────────────────────────────────────────────────

def _extract_north_stars_from_v24(v24: dict) -> List[dict]:
    items = ((v24.get("sections") or {})
              .get("north_stars") or {}).get("items") or {}
    out = []
    for key, payload in items.items():
        if not isinstance(payload, dict):
            continue
        metric = payload.get("target") or ""
        # PENDING/empty metric means configuration still needed
        is_pending = (("PENDING" in (payload.get("label") or "").upper()
                          or "PENDING" in metric.upper()
                          or metric.strip() == ""
                          or metric.strip().endswith("_per_week")))
        out.append({
            "id": key,
            "label": payload.get("label") or key,
            "metric": metric,
            "source": payload.get("source") or "calendar_config.json",
            "pending": is_pending,
        })
    return out


# ── objective → plain-English grouping ──────────────────────────

_OBJECTIVE_GROUP = {
    "OUTCOME_AWARENESS": ("Awareness campaigns", "people reached",
                            "people", "cost per 1,000 people reached"),
    "OUTCOME_TRAFFIC": ("Website traffic campaigns", "website visits",
                          "visits", "cost per website visit"),
    "LINK_CLICKS": ("Website traffic campaigns", "website visits",
                      "visits", "cost per website visit"),
    "OUTCOME_ENGAGEMENT": ("Engagement campaigns", "engagements",
                              "engagements", "cost per engagement"),
    "OUTCOME_LEADS": ("Lead campaigns", "leads", "leads",
                       "cost per lead"),
    "OUTCOME_SALES": ("Sales campaigns", "purchases", "purchases",
                        "cost per purchase"),
}

# Display-name lookup for landing pages (Herman-facing, not URL)
_PAGE_DISPLAY_NAMES = [
    ("/bookings/", "Bookings"),
    ("/club-fitting", "Club Fitting"),
    ("/fitting", "Club Fitting"),
    ("/coaching", "Coaching"),
    ("/membership", "Membership"),
    ("/takomo", "Takomo"),
    ("/avoda", "Avoda"),
    ("/psycho-bunny", "Psycho Bunny"),
    ("/trackman", "TrackMan"),
    ("/lessons", "Coaching"),
]


def _page_display_name(path: str) -> str:
    for needle, label in _PAGE_DISPLAY_NAMES:
        if needle in path:
            return label
    # fallback: humanise the URL
    bits = [b for b in path.strip("/").split("/") if b]
    if not bits:
        return "Home"
    # take the last meaningful segment, drop extension + token ids
    last = bits[-1].split("?")[0]
    last = re.sub(r"-\d{6,}", "", last)
    last = last.replace("-", " ").replace("_", " ")
    return last.title() if last else path


# ── formatting helpers ──────────────────────────────────────────

def _fmt(v: Any, kind: str = "int") -> str:
    if v is None:
        return "—"
    if v in ("", "unknown"):
        return "—"
    try:
        n = float(v)
    except (ValueError, TypeError):
        return str(v)
    if kind == "money":
        return f"R{n:,.2f}"
    if kind == "money_round":
        return f"R{n:,.0f}"
    if kind == "pct":
        return f"{n:.2f}%"
    if kind == "decimal":
        return f"{n:,.2f}"
    if kind == "money_per":
        if n >= 100:
            return f"R{n:,.0f}"
        return f"R{n:,.2f}"
    return f"{int(round(n)):,}"


def _pct(curr, prev) -> Tuple[Optional[float], str]:
    if curr is None or prev is None:
        return (None, "—")
    try:
        c = float(curr); p = float(prev)
    except (ValueError, TypeError):
        return (None, "—")
    if p == 0:
        if c == 0:
            return (0.0, "no change")
        return (None, "no comparison")
    pct = (c - p) / p * 100
    return (pct, f"{pct:+.1f}%")


def _sign(curr, prev) -> str:
    if curr is None or prev is None:
        return "neutral"
    try:
        c = float(curr); p = float(prev)
    except (ValueError, TypeError):
        return "neutral"
    if c > p:
        return "up"
    if c < p:
        return "down"
    return "flat"


# ── read organic (IG + FB) from disk cache ─────────────────────

def _brand_has_instagram_account(bid: str) -> bool:
    """True iff the brand has an Instagram business account available.

    Two paths must agree:
      1. data/integrations/<bid>/instagram.json on disk.
      2. meta_api.load_brand_integration() with env-var overlays
         (so deployments with META_INSTAGRAM_BUSINESS_ACCOUNT_ID_<BRAND>
         set on Railway work even when the local config file says
         configured:false).
    """
    try:
        from _lib import meta_api as _ma
        cfg = _ma.load_brand_integration(bid)
        return bool(cfg.get("ig_business_account_id"))             and bool(cfg.get("configured", True))
    except Exception:
        return False


def _read_instagram_posts_for_brand(bid: str) -> List[Dict[str, Any]]:
    """Load Instagram posts published by THIS brand, with real timestamps.

    Brand-isolation guard:
      1. Calls _lib.meta_api.list_recent_posts_for_brand(bid) which
         resolves the BRAND-SCOPED token + ig_business_account_id.
      2. Returns posts published to the brand's own IG account.
      3. Stick no longer inherits Swing Shack posts — the per-brand
         function uses load_brand_integration() which now overlays
         env-var META_INSTAGRAM_BUSINESS_ACCOUNT_ID_<BRAND> and
         META_SYSTEM_USER_TOKEN_<BRAND>_PAARL onto the config.
      4. Returns [] if no IG account is configured for the brand.
    """
    try:
        from _lib import meta_api as _ma  # type: ignore
        cfg = _ma.load_brand_integration(bid)
        if not cfg.get("ig_business_account_id"):
            return []
        if not cfg.get("configured"):
            return []
        try:
            r = _ma.list_recent_posts_for_brand(bid, limit=25) or {}
        except Exception:
            r = {}
        # Defence: if list_recent_posts returned a different account than
        # what we asked for (stick delegation bug from upstream), reject.
        meta = r.get("_meta") or {}
        if meta.get("ig_account_id") and cfg.get("ig_business_account_id")                 and meta["ig_account_id"] != cfg["ig_business_account_id"]:
            return []
        out: List[Dict[str, Any]] = []
        for p in r.get("data") or []:
            if not isinstance(p, dict):
                continue
            ts = p.get("timestamp")
            dt = _parse_published_at(ts)
            if dt is None:
                continue
            cap = (p.get("caption") or "").strip()
            out.append({
                "id": p.get("id"),
                "media_type": (p.get("media_type") or "IMAGE").upper(),
                "media_product_type": (p.get("media_product_type") or "").upper(),
                "caption": cap,
                "interactions": 0,  # filled below from insights if available
                "reach": 0,
                "likes": 0,
                "comments": 0,
                "saves": 0,
                "shares": 0,
                "permalink": p.get("permalink") or "",
                "thumbnail_url": (p.get("thumbnail_url") or p.get("media_url") or ""),
                "timestamp": ts,
                "published_at": dt,
                "source": f"meta_api.list_recent_posts_for_brand (brand={bid})",
            })
        # Fetch per-media insights so the cards have real engagement numbers.
        for post in out:
            mid = post.get("id")
            if not mid:
                continue
            try:
                ins = _ma.get_post_insights_for_brand(
                    bid, mid, media_type=post.get("media_type")) or {}
                flat = ins.get("_flat") or {}
                post["reach"] = int(flat.get("reach") or 0)
                post["likes"] = int(flat.get("likes") or 0)
                post["comments"] = int(flat.get("comments") or 0)
                post["saves"] = int(flat.get("saved") or 0)
                post["shares"] = int(flat.get("shares") or 0)
                post["interactions"] = (post["likes"]
                                          + post["comments"]
                                          + post["saves"]
                                          + post["shares"])
            except Exception:
                pass
        return out
    except Exception:
        return []


def _read_instagram_stories_for_brand(bid: str) -> List[Dict[str, Any]]:
    """Fetch recent Instagram stories via _lib.meta_api.get_ig_stories().

    Stories expire after 24h on Meta, so this only returns the
    past 24-48h of stories — not the full week. We surface a
    short summary rather than per-story cards so the section
    stays honest about the data window.

    Honors the same brand-isolation guard as
    _read_instagram_posts_for_brand() — only brands with an IG
    business account configured are eligible.
    """
    if not _brand_has_instagram_account(bid):
        return []
    try:
        from _lib import meta_api as _ma  # type: ignore
        out = _ma.get_ig_stories(limit=50, with_insights=True, brand_id=bid) or {}
        meta = out.get("_meta") or {}
        # Fail loud on auth errors so we don't pretend we have stories.
        # If errored, return [] and let the section hide.
        if not meta.get("fetched"):
            return []
        stories: List[Dict[str, Any]] = []
        for s in (out.get("data") or []):
            if not isinstance(s, dict):
                continue
            ts = s.get("timestamp")
            stories.append({
                "id": s.get("id"),
                "media_type": (s.get("media_type") or "IMAGE").upper(),
                "timestamp": ts,
                "published_at": _parse_published_at(ts),
                "permalink": s.get("permalink") or "",
                "reach": int((s.get("reach") or 0)),
                "interactions": int((s.get("total_interactions") or 0)),
                "follows": int((s.get("follows") or 0)),
            })
        return stories
    except Exception:
        return []


def _render_stories(bid: str, periods: Optional[Dict[str, str]] = None) -> str:
    """Render a small 'Stories this week' section if stories exist.

    Stories only persist on Meta for 24h, so the section uses
    lighter styling than Best content and notes the data
    window explicitly. Hidden entirely when no stories exist
    or the IG account isn't configured.
    """
    stories = _read_instagram_stories_for_brand(bid)
    cur_start = (periods or {}).get("current_week_start", "")
    cur_end = (periods or {}).get("current_week_end", "")
    cur_start_dt = (_dt_mod.date.fromisoformat(cur_start)
                      if cur_start else None)
    cur_end_dt = (_dt_mod.date.fromisoformat(cur_end)
                    if cur_end else None)
    # Filter to the report week (or last 24h when week unavailable).
    in_week: List[Dict[str, Any]] = []
    for s in stories:
        pa = s.get("published_at")
        if pa is None:
            continue
        if cur_start_dt and cur_end_dt:
            if not (cur_start_dt <= pa.date() <= cur_end_dt):
                continue
        in_week.append(s)
    has_ig_account = _brand_has_instagram_account(bid)
    if not in_week:
        if not has_ig_account:
            return ""  # brand has no IG account at all — skip silently
        # IG account is configured but no active stories — show honest empty card
        return """
<section id="sec-Stories" class="report-section">
  <div class="section-eyebrow">Stories</div>
  <h2>Stories this week</h2>
  <p class="lead">No active stories in the past 24 hours.</p>
  <div class="content-empty">
    <div class="content-empty-title">No active stories right now.</div>
    <div class="content-empty-meta">Meta expires stories after 24h, so anything
      older in the reporting week is no longer available. The Instagram Graph
      API was called for this brand but returned no currently-live stories.</div>
  </div>
</section>
"""
    in_week.sort(key=lambda s: ((s.get("reach") or 0),
                                  (s.get("interactions") or 0)),
                  reverse=True)
    # Aggregate metrics
    total_reach = sum(s.get("reach", 0) for s in in_week)
    total_int = sum(s.get("interactions", 0) for s in in_week)
    total_follows = sum(s.get("follows", 0) for s in in_week)
    # Render compact tiles
    tiles = ""
    for s in in_week[:8]:  # cap display at 8
        pa = s.get("published_at")
        date_lbl = (pa.strftime("%a %H:%M") if pa else "?")
        med = s.get("media_type", "IMAGE")
        is_video = "VIDEO" in med
        med_word = "Video" if is_video else "Image"
        reach = s.get("reach") or 0
        intrx = s.get("interactions") or 0
        follows = s.get("follows") or 0
        perma = s.get("permalink") or ""
        link_html = (f'<a href="{_esc(perma)}" target="_blank" '
                       f'rel="noopener" class="story-link">View ↗</a>'
                       if perma else "")
        tiles += f"""
        <div class="story-tile">
          <div class="story-head">
            <span class="story-when">{_esc(date_lbl)}</span>
            <span class="story-type">{_esc(med_word)}</span>
          </div>
          <div class="story-stats">
            <span>Reach: <strong>{_esc(_fmt(reach))}</strong></span>
            <span>Interactions: <strong>{_esc(_fmt(intrx))}</strong></span>
            <span>Follows: <strong>{_esc(_fmt(follows))}</strong></span>
          </div>
          {link_html}
        </div>"""
    n = len(in_week)
    noun = "story" if n == 1 else "stories"
    reach_lbl = (f"{_fmt(total_reach)} total reach, "
                  f"{_fmt(total_int)} interactions, "
                  f"{_fmt(total_follows)} follows")
    window_note = ("Stories shown for the past 24 hours only — "
                     "Meta expires stories after 24h, so anything "
                     "older in the reporting week is no longer available.")
    return f"""
<section id="sec-Stories" class="report-section">
  <div class="section-eyebrow">Stories</div>
  <h2>Stories this week</h2>
  <p class="lead">{n} {noun} active in the past 24 hours · {reach_lbl}.</p>
  <p class="lead">{_esc(window_note)}</p>
  <div class="story-grid">{tiles}</div>
</section>
"""


def _read_organic_from_cache(bid: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ig": None, "fb": None}
    ig_brand_map = {
        "swingshack": "swing-shack",
        "stickgolf": "stick",
        "stick.paarl": "stick",
    }
    ig_data = {}
    for r in (_data_root(),
                Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data")):
        for fname in ("ig-business-analytics.json",
                         "analytics/instagram-analytics.json"):
            p = r / fname
            if p.is_file():
                try:
                    raw = json.loads(p.read_text(encoding="utf-8"))
                    username = ((raw.get("account") or {})
                                  .get("username") or "")
                    detected = ig_brand_map.get(
                        username.lower().replace("@", ""))
                    if detected and detected != bid:
                        continue
                    ig_data = raw
                except Exception:
                    continue
                if ig_data:
                    break
        if ig_data:
            break
    if ig_data:
        wt = ig_data.get("window_totals") or {}
        out["ig"] = {
            "status": "LIVE" if wt else "PARTIAL",
            "username": (ig_data.get("account") or {}).get("username"),
            "followers": (ig_data.get("account") or {}).get("followers_count"),
            "media_count": (ig_data.get("account") or {}).get("media_count"),
            "reach": wt.get("reach"),
            "interactions": wt.get("total_interactions"),
            "profile_views": wt.get("profile_views"),
            "profile_links_taps": wt.get("profile_links_taps"),
            "accounts_engaged": wt.get("accounts_engaged"),
            "top_posts": [
                {
                    "id": p.get("id"),
                    "media_type": p.get("media_type"),
                    "caption": (p.get("caption_preview")
                                  or p.get("caption") or "").strip(),
                    "interactions": ((p.get("metrics") or {})
                                          .get("total_interactions")),
                    "reach": ((p.get("metrics") or {})
                                  .get("reach")),
                    "likes": ((p.get("metrics") or {})
                                  .get("likes")),
                    "comments": ((p.get("metrics") or {})
                                       .get("comments")),
                    "permalink": p.get("permalink"),
                    "timestamp": p.get("timestamp"),
                }
                for p in (ig_data.get("media") or [])[:10]
            ],
        }
    fb_data = {}
    for r in (_data_root(),
                Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data")):
        p = r / "fb-page-analytics.json"
        if p.is_file():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                fb_data = raw
            except Exception:
                continue
            if fb_data:
                break
    if fb_data:
        wt = fb_data.get("window_totals") or {}
        page = fb_data.get("page") or {}
        out["fb"] = {
            "status": "LIVE" if wt else "PARTIAL",
            "page_name": page.get("name"),
            "fans": page.get("fan_count"),
            "impressions": wt.get("page_impressions"),
            "engagements": wt.get("page_post_engagements"),
            "clicks": wt.get("page_consumptions") or wt.get("clicks"),
            "top_posts": [
                {
                    "id": p.get("id"),
                    "media_type": p.get("type") or p.get("media_type"),
                    "caption": (p.get("message")
                                  or p.get("message_preview") or "").strip(),
                    "interactions": (
                        (p.get("reactions_total") or 0)
                        + (p.get("comments") or 0)
                        + (p.get("shares") or 0)
                    ),
                    "clicks": p.get("clicks"),
                    "permalink": p.get("permalink"),
                    "timestamp": p.get("timestamp"),
                }
                for p in (fb_data.get("posts") or [])[:10]
            ],
        }
    return out


# ── read SEO from disk cache ───────────────────────────────────

def _read_seo_from_cache(bid: str) -> Dict[str, Any]:
    """Pull Ubersuggest SEO summary for the brand.

    Uses _lib.seo_insights in the same process so we read the
    Railway-fresh disk cache. Only Swing Shack has Ubersuggest
    configured today; other brands return NOT_CONFIGURED.
    """
    if bid != "swing-shack":
        return {"status": "NOT_CONFIGURED"}
    try:
        from _lib import seo_insights  # type: ignore
        dh = seo_insights.domain_health() or {}
        rank = seo_insights.load_seo_rankings() or {}
    except Exception:
        dh = {}
        rank = {}
    if not rank:
        for r in (_data_root(),
                    Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data")):
            p = r / "seo-rankings.json"
            if p.is_file():
                try:
                    rank = json.loads(p.read_text(encoding="utf-8"))
                    break
                except Exception:
                    continue
    if not rank and not dh:
        return {"status": "NOT_CONNECTED"}
    kfp = (dh.get("keyword_footprint") or {})
    wc = (dh.get("weekly_change") or rank.get("weekly_change") or {})
    # fetched_at may live at rank.fetched_at OR rank.metadata.fetched_at
    _meta = rank.get("metadata") or {}
    fetched_at = (rank.get("fetched_at")
                    or _meta.get("fetched_at")
                    or dh.get("fetched_at"))
    return {
        "status": "LIVE" if fetched_at else "PARTIAL",
        "domain_authority": dh.get("domain_authority")
                                or rank.get("domain_authority"),
        "backlinks": dh.get("total_backlinks")
                        or rank.get("backlinks"),
        "ref_domains": dh.get("ref_domains")
                          or rank.get("ref_domains"),
        "top_3": kfp.get("top_3") if kfp.get("top_3") is not None
                    else rank.get("top_3_keywords"),
        "top_10": kfp.get("top_10") if kfp.get("top_10") is not None
                    else rank.get("top_10_keywords"),
        "weekly_change": wc,
        "fetched_at": fetched_at,
        "manager_read": dh.get("manager_read") or rank.get("manager_read"),
    }


def _seo_block(block: dict, fetched_at: str) -> Dict[str, Any]:
    return {
        "status": "LIVE" if fetched_at else "PARTIAL",
        "domain_authority": block.get("domain_authority"),
        "backlinks": block.get("backlinks"),
        "ref_domains": block.get("ref_domains"),
        "top_3": block.get("top_3"),
        "top_10": block.get("top_10"),
        "weekly_change": block.get("weekly_change") or {},
        "fetched_at": fetched_at,
    }


# ── try to enrich SEO with winning/leaking keywords (Railway only) ──

def _read_seo_keywords(bid: str, cookie: Optional[str] = None) -> Dict[str, Any]:
    """Pull winning / leaking / quick-win SEO keywords.

    Uses _lib.seo_insights in the same process (no external HTTP
    hop). Falls back to disk cache if the import fails.
    """
    out = {"winning": [], "leaking": [], "quick_wins": []}
    try:
        from _lib import seo_insights  # type: ignore
        rank = seo_insights.load_seo_rankings()
        out["winning"] = seo_insights.winning_keywords(rank) or []
        out["leaking"] = seo_insights.leaking_keywords(rank) or []
        out["quick_wins"] = seo_insights.quick_wins(rank) or []
        if any(out.values()):
            return out
    except Exception:
        pass
    # Disk cache fallback
    for r in (_data_root(),
                Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data")):
        p = r / "seo-keywords.json"
        if p.is_file():
            try:
                raw = json.loads(p.read_text())
                for cat in ("winning", "leaking", "quick_wins"):
                    out[cat] = raw.get(cat) or raw.get(f"{bid}_{cat}") or []
                return out
            except Exception:
                continue
    return out
    # Fall back to disk cache
    for r in (_data_root(),
                Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data")):
        p = r / "seo-keywords.json"
        if p.is_file():
            try:
                raw = json.loads(p.read_text())
                for cat in ("winning", "leaking", "quick_wins"):
                    out[cat] = raw.get(cat) or raw.get(f"{bid}_{cat}") or []
                return out
            except Exception:
                continue
    return out


# ── marketing actions ───────────────────────────────────────────

def _derive_actions(v24: dict, bid: str) -> List[dict]:
    s = _extract_kpi(v24, "Sessions")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    pm = v24.get("paid_media_v24") or {}
    actions: List[dict] = []
    chans = cm.get("rows") or []
    candidates = [(c, abs((c.get("current_sessions") or 0)
                            - (c.get("previous_sessions") or 0)))
                   for c in chans]
    candidates = [c for c in candidates if c[1] >= 5]
    if candidates:
        candidates.sort(key=lambda t: t[1], reverse=True)
        top_mover = candidates[0][0]
        cur_v = top_mover.get("current_sessions")
        prev_v = top_mover.get("previous_sessions")
        chan = top_mover.get("channel")
        share = top_mover.get("share_of_sessions") or 0
        if cur_v > prev_v:
            suggestion = ("check which pages and search terms brought the "
                            "extra traffic, then use those topics in upcoming "
                            "content")
        else:
            suggestion = ("check why the change happened before scaling or "
                            "pausing anything")
        actions.append({
            "what": f"Watch the {chan} channel closely this week.",
            "why": (f"{chan} changed this week "
                      f"({_fmt(prev_v)} → {_fmt(cur_v)} sessions, "
                      f"{share:.1f}% of all sessions)."),
            "watch": suggestion,
        })
    lead_campaigns = [c for c in (pm.get("per_campaign") or [])
                       if c.get("objective") == "OUTCOME_LEADS"
                       and (c.get("current") or {}).get("spend", 0) > 0]
    if lead_campaigns:
        lead_campaigns.sort(
            key=lambda c: (c.get("current") or {}).get("spend", 0),
            reverse=True)
        c = lead_campaigns[0]
        pr = c.get("primary_result") or {}
        leads_count = pr.get("primary_value")
        cpr = pr.get("primary_cost_per_unit")
        if cpr is not None and leads_count is not None:
            actions.append({
                "what": (f"Keep monitoring '{c.get('campaign_name','?')}' "
                          f"this week."),
                "why": (f"It produced {_fmt(leads_count)} leads at "
                          f"{_fmt(cpr, 'money_per')} per lead."),
                "watch": ("compare cost per lead with last week before "
                            "deciding whether to increase its budget"),
            })
    lead_campaign_names = set()
    for a in actions:
        for token in a.get("what", "").split("'"):
            lead_campaign_names.add(token.strip())
    fitting_or_coaching_campaigns = [
        c for c in (pm.get("per_campaign") or [])
        if (c.get("current") or {}).get("spend", 0) > 0
        and c.get("objective") in ("LINK_CLICKS", "OUTCOME_TRAFFIC")
        and c.get("campaign_name") not in lead_campaign_names
        and any(t in (c.get("campaign_name") or "").lower()
                  for t in ("fit", "coach", "lesson", "assessment"))
    ]
    if fitting_or_coaching_campaigns:
        c = fitting_or_coaching_campaigns[0]
        pr = c.get("primary_result") or {}
        pv = pr.get("primary_value")
        if pv is not None:
            actions.append({
                "what": (f"Keep '{c.get('campaign_name','?')}' running."),
                "why": (f"It brought {_fmt(pv)} website visits this week "
                          f"at {(_fmt(pr.get('primary_cost_per_unit'), 'money_per') or '—')} each."),
                "watch": ("how many of those visits reach the booking page "
                            "and how many continue to fill it in"),
            })
    return actions[:3]


# ── KPI cards + headline numbers ───────────────────────────────

def _kpi_cards(bid: str, v24: dict, periods: Dict[str, str]) -> List[Dict[str, Any]]:
    s = _extract_kpi(v24, "Sessions")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    leads_cur = paid_totals["current_period"].get("total_results")
    paid_social = next((c for c in (cm.get("rows") or [])
                          if c.get("channel") == "Paid Social"), None)
    organic_search = next((c for c in (cm.get("rows") or [])
                            if c.get("channel") == "Organic Search"), None)
    cards: List[Dict[str, Any]] = []
    # Sessions
    cur_v = s.get("current"); prev_v = s.get("previous")
    pct_v, _ = _pct(cur_v, prev_v)
    cards.append({
        "label": "Website sessions",
        "value": _fmt(cur_v),
        "change_pct": pct_v,
        "change_text": _pct(cur_v, prev_v)[1],
        "trend": _sign(cur_v, prev_v),
        "secondary": (f"vs {_fmt(prev_v)} last week" if prev_v is not None else None),
    })
    # Organic Search
    if organic_search:
        cur_v = organic_search.get("current_sessions")
        prev_v = organic_search.get("previous_sessions")
        cards.append({
            "label": "Organic Search",
            "value": _fmt(cur_v),
            "change_pct": _pct(cur_v, prev_v)[0],
            "change_text": _pct(cur_v, prev_v)[1],
            "trend": _sign(cur_v, prev_v),
            "secondary": "sessions from Google",
        })
    # Paid Social
    if paid_social:
        cur_v = paid_social.get("current_sessions")
        prev_v = paid_social.get("previous_sessions")
        cards.append({
            "label": "Paid Social",
            "value": _fmt(cur_v),
            "change_pct": _pct(cur_v, prev_v)[0],
            "change_text": _pct(cur_v, prev_v)[1],
            "trend": _sign(cur_v, prev_v),
            "secondary": "sessions from Meta ads",
        })
    # Meta spend
    cards.append({
        "label": "Meta ad spend",
        "value": _fmt(cur.get("total_spend"), "money"),
        "change_pct": _pct(cur.get("total_spend"),
                          paid_totals["previous_period"].get("total_spend"))[0],
        "change_text": _pct(cur.get("total_spend"),
                          paid_totals["previous_period"].get("total_spend"))[1],
        "trend": _sign(cur.get("total_spend"),
                        paid_totals["previous_period"].get("total_spend")),
        "secondary": "this week on Facebook + Instagram",
    })
    # Meta leads
    cards.append({
        "label": "Meta leads",
        "value": _fmt(leads_cur),
        "change_pct": None,
        "change_text": "from lead campaigns",
        "trend": "neutral",
        "secondary": "bookings not yet linked",
    })
    return cards


# ── Executive narrative ─────────────────────────────────────────

def _build_executive_narrative(bid: str, v24: dict,
                                  organic: Dict[str, Any],
                                  periods: Dict[str, str]) -> str:
    s = _extract_kpi(v24, "Sessions")
    s_cur = s.get("current")
    s_prev = s.get("previous")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    movers = []
    for c in (cm.get("rows") or []):
        cur_v = c.get("current_sessions")
        prev_v = c.get("previous_sessions")
        if cur_v is not None and prev_v is not None:
            movers.append((c.get("channel"), cur_v - prev_v))
    movers.sort(key=lambda t: abs(t[1]), reverse=True)
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    parts: List[str] = []
    if (s_cur is not None and s_prev is not None and s_prev > 0
            and abs(s_cur - s_prev) >= 10):
        pct = (s_cur - s_prev) / s_prev * 100
        if pct > 0:
            parts.append(
                f"Website traffic increased by {abs(s_cur - s_prev)} "
                f"sessions ({pct:.1f}% more) compared with last week.")
        elif pct < 0:
            parts.append(
                f"Website traffic fell by {abs(s_cur - s_prev)} sessions "
                f"({abs(pct):.1f}% less) compared with last week.")
    if movers:
        biggest = movers[0]
        if abs(biggest[1]) >= 5:
            sign_word = "more" if biggest[1] > 0 else "fewer"
            sign_n = abs(biggest[1])
            parts.append(
                f"The {biggest[0]} channel brought {sign_n} {sign_word} "
                f"sessions than last week.")
    if (cur.get("total_impressions", 0) > 0
            and prev.get("total_impressions", 0) > 0):
        imp_pct = ((cur["total_impressions"] - prev["total_impressions"])
                     / prev["total_impressions"] * 100)
        if abs(imp_pct) >= 10:
            if imp_pct > 0:
                parts.append(
                    f"Meta ads reached {abs(imp_pct):.1f}% more people this "
                    f"week than last week.")
            else:
                parts.append(
                    f"Meta ads reached {abs(imp_pct):.1f}% fewer people this "
                    f"week than last week — paid delivery should be watched.")
    if not parts:
        return ("Not enough data yet to summarise the week. Check Data still "
                "missing below.")
    return " ".join(parts[:4])


# ── HTML rendering helpers ─────────────────────────────────────

def _esc(s: Any) -> str:
    if s is None:
        return ""
    return _html.escape(str(s), quote=True)


def _pct_class(pct: Optional[float]) -> str:
    if pct is None:
        return "neutral"
    if pct > 0.5:
        return "up"
    if pct < -0.5:
        return "down"
    return "flat"


# ── HTML render ─────────────────────────────────────────────────

def _render_html(bid: str, v24: dict, organic: Dict[str, Any],
                   seo: Dict[str, Any], seo_kw: Dict[str, Any],
                   periods: Dict[str, str],
                   contamination_block: Optional[str] = None,
                   as_of: Optional[str] = None) -> str:
    facts = _brand_canonical(bid)
    primary = facts["primary_color"]
    accent = facts["accent_color"]
    display = facts["display_name"]
    icon = facts["icon"]
    website = facts["website"]
    if contamination_block:
        return _wrap_html(facts, periods, as_of, "Report Blocked",
                          f"<div class='block'>{_esc(contamination_block)}</div>",
                          primary, accent)
    cards = _kpi_cards(bid, v24, periods)
    exec_text = _build_executive_narrative(bid, v24, organic, periods)
    sections = []
    sections.append(_render_kpi_cards(cards, primary))
    sections.append(_render_executive_card(exec_text, primary, accent))
    sections.append(_render_website_traffic_table(v24))
    sections.append(_render_acquisition(v24, primary, accent))
    sections.append(_render_advertising(v24, primary, accent))
    sections.append(_render_website_pages(v24))
    sections.append(_render_seo(seo, seo_kw, primary, bid))
    sections.append(_render_social(bid, organic, primary))
    sections.append(_render_best_content(bid, organic, primary, periods))
    stories_html = _render_stories(bid, periods)
    if stories_html:
        sections.append(stories_html)
    sections.append(_render_worked_attention(v24, primary))
    sections.append(_render_actions(v24, bid, primary, accent))
    sections.append(_render_targets(v24, primary, accent, bid))
    sections.append(_render_data_missing(v24, organic, seo, primary))
    body = "\n".join(sections)
    title = (f"{display} Weekly Marketing Report — "
              f"{_fmt_period_label(periods['current_week_start'])} → "
              f"{_fmt_period_label(periods['current_week_end'])}")
    return _wrap_html(facts, periods, as_of, title, body, primary, accent,
                      cards=cards, exec_text=exec_text, sections=sections)


def _wrap_html(facts: dict, periods: Dict[str, str],
                  as_of: Optional[str], title: str, body: str,
                  primary: str, accent: str, **ctx) -> str:
    display = facts["display_name"]
    icon = facts["icon"]
    website = facts["website"]
    tagline = facts["tagline"]
    cur_label = (_fmt_period_label(periods["current_week_start"]) + " → "
                  + _fmt_period_label(periods["current_week_end"]))
    prev_label = (_fmt_period_label(periods["previous_week_start"]) + " → "
                    + _fmt_period_label(periods["previous_week_end"]))
    cur_dates = (f"{periods['current_week_start']} → "
                  f"{periods['current_week_end']}")
    prev_dates = (f"{periods['previous_week_start']} → "
                    f"{periods['previous_week_end']}")
    generated = datetime.datetime.now(
        datetime.timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    # Page navigation (sections list, derived from ctx)
    nav_html = ""
    cards = ctx.get("cards") or []
    sections = ctx.get("sections") or []
    section_titles = [
        ("KPI", "Top numbers"),
        ("Executive", "This week"),
        ("Traffic", "Website traffic"),
        ("Acquisition", "Where visitors came from"),
        ("Advertising", "Advertising"),
        ("Pages", "Website pages"),
        ("SEO", "Google search"),
        ("Social", "Social media"),
        ("Content", "Best content"),
        ("Stories", "Stories this week"),
        ("Worked", "What worked & what needs attention"),
        ("Actions", "What we should do this week"),
        ("Targets", "Business targets"),
        ("Missing", "Data still missing"),
    ]
    nav_items = "".join(
        f"<a href='#sec-{sid}'><span class='nav-label'>{slabel}</span></a>"
        for sid, slabel in section_titles
    )
    # Cards HTML
    cards_html = ""
    for sid, _ in section_titles:
        if sid == "KPI":
            continue
        for s in sections:
            if s.lstrip().startswith(f'<section id="sec-{sid}"'):
                cards_html += s.lstrip()
                break
    sections_html = ""
    for sid, slabel in section_titles:
        if sid == "KPI":
            continue
        for s in sections:
            if s.lstrip().startswith(f'<section id="sec-{sid}"'):
                sections_html += s.lstrip()
                break
    kpi_html = ""
    for s in sections:
        if s.lstrip().startswith('<section id="sec-KPI"'):
            kpi_html = s.lstrip()
            break
    # Top-of-report brand switcher
    _all_brands = [("swing-shack", "Swing Shack"), ("stick", "Stick"),
                   ("bag-drop", "Bag Drop")]
    _cur_bid = facts.get("brand_id") or ""
    _pills = ""
    for _b, _label in _all_brands:
        _cls = "topbar-brand-pill current" if _b == _cur_bid else "topbar-brand-pill"
        _href = f"/weekly-report?brand={_b}&as_of={as_of or ''}"
        _pills += (f'<a class="{_cls}" href="{_esc(_href)}">{_esc(_label)}</a>')
    css = _css(primary, accent)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{css}</style>
</head>
<body>
<nav class="report-topbar">
  <a class="topbar-back" href="/weekly-report">← Back to reports dashboard</a>
  <span class="topbar-spacer"></span>
  <span class="topbar-brand-label">Brand:</span>
  {_pills}
</nav>
<header class="page-header">
  <div class="header-inner">
    <div class="brand-block">
      <div class="brand-name">{_esc(icon)} {_esc(display)}</div>
      <div class="brand-tagline">{_esc(tagline)}</div>
      <div class="website"><a href="https://{_esc(website)}" target="_blank" rel="noopener">{_esc(website)}</a></div>
    </div>
    <div class="report-block">
      <div class="report-eyebrow">Weekly Marketing Report</div>
      <div class="report-title">{_esc(cur_label)}</div>
      <div class="report-compare">Compared with {_esc(prev_label)}</div>
      <div class="report-meta">Generated {_esc(generated)}</div>
    </div>
  </div>
  <nav class="page-nav">{nav_items}</nav>
</header>
<main class="report-main">
{kpi_html}
{sections_html}
</main>
<footer class="page-footer">
  <span class="footer-brand">{_esc(display)} Weekly Marketing Report</span>
  <span class="footer-period">{_esc(cur_dates)}</span>
  <span class="footer-page">Page <span class="page-num"></span> of <span class="page-count"></span></span>
</footer>
<script>
  // Page-number injection (works in browser print preview).
  document.addEventListener('DOMContentLoaded', function() {{
    const body = document.body;
    const pageHeightPx = 1122; // ~A4 at 96dpi minus margins
    const total = Math.max(1, Math.ceil(body.scrollHeight / pageHeightPx));
    document.querySelectorAll('.page-num').forEach(el => {{ el.textContent = 1; }});
    document.querySelectorAll('.page-count').forEach(el => {{ el.textContent = total; }});
  }});
</script>
</body>
</html>
"""


def _css(primary: str, accent: str) -> str:
    # Build a derived palette based on the brand's primary/accent.
    return f"""
:root {{
  --brand-primary: {primary};
  --brand-accent: {accent};
  --ink: #14171f;
  --ink-soft: #4a5060;
  --ink-muted: #7a8194;
  --paper: #fbfaf6;
  --card: #ffffff;
  --line: #e7e3d8;
  --line-soft: #efebde;
  --good: #0e8f5e;
  --good-soft: #e3f5ec;
  --warn: #b68108;
  --warn-soft: #fdf2d5;
  --bad: #c4314b;
  --bad-soft: #fce6ea;
  --neutral: #4a5060;
  --neutral-soft: #eef0f3;
  --shadow: 0 1px 0 rgba(0,0,0,.04), 0 2px 8px rgba(20,23,31,.04);
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
              "Helvetica Neue", Arial, sans-serif;
  background: var(--paper);
  color: var(--ink);
  font-size: 14px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}}
a {{ color: inherit; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.page-header {{
  background: linear-gradient(180deg, var(--brand-primary) 0%, var(--brand-primary) 65%, var(--paper) 100%);
  color: #fff;
  padding: 36px 0 0 0;
  margin-bottom: 28px;
}}
.header-inner {{
  max-width: 1140px; margin: 0 auto; padding: 0 32px;
  display: flex; gap: 36px; align-items: flex-end;
  flex-wrap: wrap;
}}
.brand-block {{ flex: 1 1 280px; min-width: 0; }}
.brand-name {{
  font-size: 28px; font-weight: 700; letter-spacing: -0.02em;
  margin-bottom: 6px;
}}
.brand-tagline {{
  font-size: 13px; opacity: .85; margin-bottom: 8px;
  max-width: 38ch;
}}
.website a {{
  font-size: 12px; opacity: .8; color: #fff;
  border-bottom: 1px dotted rgba(255,255,255,.4);
}}
.report-block {{
  flex: 0 0 auto; text-align: right; min-width: 280px;
}}
.report-eyebrow {{
  font-size: 11px; letter-spacing: .15em; text-transform: uppercase;
  opacity: .85; margin-bottom: 6px;
}}
.report-title {{
  font-size: 22px; font-weight: 700; letter-spacing: -0.01em;
  margin-bottom: 4px;
}}
.report-compare {{
  font-size: 13px; opacity: .85;
}}
.report-meta {{
  font-size: 11px; opacity: .65; margin-top: 6px;
}}
.page-nav {{
  max-width: 1140px; margin: 22px auto 0; padding: 10px 32px 0;
  display: flex; gap: 6px; flex-wrap: wrap;
  border-top: 1px solid rgba(255,255,255,.18);
  padding-top: 12px;
}}
.page-nav a {{
  color: rgba(255,255,255,.85); font-size: 11px;
  padding: 6px 10px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,.22);
  letter-spacing: .02em;
}}
.page-nav a:hover {{
  background: rgba(255,255,255,.12);
  text-decoration: none;
}}
.nav-label {{ display: inline-block; }}
.report-main {{
  max-width: 1140px; margin: 0 auto; padding: 0 32px 60px;
}}
section.report-section {{
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 24px 28px;
  margin-bottom: 22px;
  box-shadow: var(--shadow);
  page-break-inside: avoid;
}}
section.report-section .section-eyebrow {{
  font-size: 10px; letter-spacing: .15em; text-transform: uppercase;
  color: var(--brand-primary); font-weight: 700;
  margin-bottom: 6px;
}}
section.report-section h2 {{
  font-size: 18px; font-weight: 700; letter-spacing: -0.01em;
  margin: 0 0 12px 0;
  color: var(--ink);
}}
section.report-section p.lead {{
  color: var(--ink-soft); margin: 0 0 14px 0;
}}
.kpi-row {{
  display: grid; grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 22px;
}}
.kpi-card {{
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 18px 18px 14px;
  box-shadow: var(--shadow);
  page-break-inside: avoid;
  position: relative;
  overflow: hidden;
}}
.kpi-card::before {{
  content: ""; position: absolute; left: 0; top: 0; bottom: 0;
  width: 4px; background: var(--brand-primary); opacity: .85;
}}
.kpi-label {{
  font-size: 10px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--ink-muted); font-weight: 600;
}}
.kpi-value {{
  font-size: 30px; font-weight: 700; letter-spacing: -0.02em;
  margin-top: 6px; color: var(--ink);
  font-variant-numeric: tabular-nums;
}}
.kpi-change {{
  font-size: 13px; font-weight: 600; margin-top: 6px;
  display: flex; align-items: center; gap: 6px;
}}
.kpi-change.up {{ color: var(--good); }}
.kpi-change.down {{ color: var(--bad); }}
.kpi-change.flat {{ color: var(--ink-muted); }}
.kpi-change.neutral {{ color: var(--ink-muted); }}
.kpi-arrow {{ font-size: 12px; }}
.kpi-secondary {{
  font-size: 11px; color: var(--ink-muted); margin-top: 4px;
}}
.exec-card {{
  background: linear-gradient(180deg, var(--brand-accent) 0%, var(--brand-accent) 100%);
  background: var(--card);
  border: 1px solid var(--brand-primary);
  border-left: 5px solid var(--brand-primary);
  border-radius: 12px;
  padding: 22px 26px;
  margin-bottom: 22px;
  page-break-inside: avoid;
}}
.exec-card .section-eyebrow {{
  color: var(--brand-primary); margin-bottom: 6px;
}}
.exec-card .exec-text {{
  font-size: 15px; color: var(--ink); line-height: 1.55;
}}
table.data {{
  width: 100%; border-collapse: collapse; margin: 8px 0 4px;
  font-variant-numeric: tabular-nums;
}}
table.data th, table.data td {{
  text-align: right; padding: 9px 12px; border-bottom: 1px solid var(--line-soft);
  font-size: 13px;
}}
table.data th:first-child, table.data td:first-child {{
  text-align: left; color: var(--ink-soft);
}}
table.data thead th {{
  font-size: 11px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--ink-muted); font-weight: 600;
  border-bottom: 1px solid var(--line);
  background: transparent;
}}
table.data tbody tr:nth-child(odd) {{ background: rgba(0,0,0,.012); }}
table.data .trend-up {{ color: var(--good); font-weight: 600; }}
table.data .trend-down {{ color: var(--bad); font-weight: 600; }}
table.data .trend-flat, table.data .trend-neutral {{ color: var(--ink-muted); }}
.bar {{
  display: inline-block; height: 12px; background: var(--brand-primary);
  border-radius: 4px; vertical-align: middle; margin-right: 10px;
  opacity: .85;
}}
.acq-row {{
  display: flex; align-items: center; gap: 14px;
  margin-bottom: 6px;
  font-variant-numeric: tabular-nums;
}}
.acq-row .acq-label {{ flex: 0 0 180px; color: var(--ink-soft); font-size: 13px; }}
.acq-row .acq-bar {{
  flex: 1; height: 10px; background: var(--line-soft);
  border-radius: 4px; overflow: hidden;
}}
.acq-row .acq-bar > span {{
  display: block; height: 100%;
  background: var(--brand-primary); opacity: .9;
}}
.acq-row .acq-pct {{
  flex: 0 0 80px; text-align: right; font-weight: 600;
  color: var(--ink);
}}
.acq-row .acq-change {{
  flex: 0 0 90px; text-align: right; font-size: 12px;
}}
.acq-row .acq-change.up {{ color: var(--good); }}
.acq-row .acq-change.down {{ color: var(--bad); }}
.acq-row .acq-change.flat {{ color: var(--ink-muted); }}
.ad-summary {{
  display: grid; grid-template-columns: repeat(6, minmax(0,1fr));
  gap: 12px; margin-bottom: 18px;
}}
.ad-cell {{
  background: var(--neutral-soft); border-radius: 10px;
  padding: 12px 14px;
}}
.ad-cell .label {{
  font-size: 10px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--ink-muted); font-weight: 600;
}}
.ad-cell .value {{
  font-size: 18px; font-weight: 700; margin-top: 4px;
  font-variant-numeric: tabular-nums;
}}
.ad-group {{
  border: 1px solid var(--line-soft); border-radius: 10px;
  padding: 16px 18px; margin-bottom: 12px;
  background: rgba(0,0,0,.012);
}}
.ad-group h3 {{
  margin: 0 0 10px 0; font-size: 13px;
  letter-spacing: .06em; text-transform: uppercase;
  color: var(--brand-primary); font-weight: 700;
}}
.campaign-list {{ display: grid; gap: 10px; }}
.campaign-card {{
  background: var(--card); border: 1px solid var(--line);
  border-radius: 8px; padding: 12px 14px;
  page-break-inside: avoid;
}}
.campaign-card .campaign-name {{
  font-weight: 700; font-size: 14px; margin-bottom: 6px;
  color: var(--ink);
}}
.campaign-card dl {{
  display: grid; grid-template-columns: repeat(4, minmax(0,1fr));
  gap: 4px 18px; margin: 0; font-size: 12px;
}}
.campaign-card dt {{
  color: var(--ink-muted); font-size: 11px; font-weight: 500;
  text-transform: uppercase; letter-spacing: .05em;
}}
.campaign-card dd {{
  margin: 0; font-weight: 600; font-variant-numeric: tabular-nums;
}}
.work-attn-grid {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
}}
.work-card, .attn-card {{
  border-radius: 12px; padding: 16px 18px;
  page-break-inside: avoid;
}}
.work-card {{ background: var(--good-soft); border: 1px solid #c9ebd9; }}
.attn-card {{ background: var(--warn-soft); border: 1px solid #efd99a; }}
.work-card .label {{
  font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--good); font-weight: 700;
}}
.attn-card .label {{
  font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--warn); font-weight: 700;
}}
.work-card ul, .attn-card ul {{
  margin: 8px 0 0 0; padding-left: 20px;
}}
.work-card li, .attn-card li {{ font-size: 13px; margin: 4px 0; }}
.action-grid {{
  display: grid; grid-template-columns: repeat(3, minmax(0,1fr));
  gap: 14px;
}}
.action-card {{
  background: var(--card); border: 1px solid var(--brand-primary);
  border-radius: 12px; padding: 18px 20px;
  page-break-inside: avoid;
  position: relative;
}}
.action-card .num {{
  position: absolute; top: -10px; left: 16px;
  background: var(--brand-primary); color: #fff;
  font-weight: 700; font-size: 12px;
  padding: 4px 10px; border-radius: 999px;
}}
.action-card .what {{
  font-weight: 700; font-size: 15px; margin-top: 6px;
}}
.action-card .why {{ color: var(--ink-soft); font-size: 13px; margin: 6px 0; }}
.action-card .watch {{
  font-size: 12px; color: var(--brand-primary);
  background: rgba(0,0,0,.04); border-radius: 6px;
  padding: 6px 10px; margin-top: 8px;
}}
.target-grid {{
  display: grid; grid-template-columns: repeat(3, minmax(0,1fr));
  gap: 14px;
}}
.target-card {{
  border: 1px solid var(--brand-primary); border-radius: 12px;
  padding: 18px 20px; background: var(--card);
}}
.target-card .name {{
  font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--brand-primary); font-weight: 700;
}}
.target-card .metric {{
  font-size: 18px; font-weight: 700; margin-top: 6px;
}}
.target-card.empty {{ opacity: .5; border-style: dashed; }}
.missing-list {{ margin: 6px 0 0; padding-left: 20px; }}
.missing-list li {{ font-size: 13px; margin: 4px 0; color: var(--ink-soft); }}
.content-grid {{
  display: grid; grid-template-columns: repeat(3, minmax(0,1fr));
  gap: 14px;
}}
.content-card {{
  border: 1px solid var(--line); border-radius: 12px;
  background: var(--card); overflow: hidden;
  page-break-inside: avoid;
}}
.content-card .thumb {{
  height: 140px;
  background: linear-gradient(135deg, var(--brand-primary), var(--brand-accent));
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 32px;
}}
.content-card .meta {{ padding: 14px 16px; }}
.content-card .type {{
  font-size: 10px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--brand-primary); font-weight: 700;
}}
.content-card .caption {{ font-size: 13px; margin: 6px 0 10px; line-height: 1.4; }}
.content-card .stats {{
  display: flex; gap: 14px; font-size: 12px;
  color: var(--ink-soft); font-variant-numeric: tabular-nums;
}}
.social-grid {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
}}
.social-card {{
  border: 1px solid var(--line); border-radius: 12px;
  padding: 16px 18px; background: var(--card);
}}
.social-card .name {{
  font-size: 14px; font-weight: 700; margin-bottom: 10px;
  display: flex; gap: 8px; align-items: center;
}}
.social-card .name .dot {{
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--brand-primary);
}}
.social-card .row {{
  display: flex; justify-content: space-between;
  font-size: 13px; padding: 4px 0;
  border-bottom: 1px solid var(--line-soft);
  font-variant-numeric: tabular-nums;
}}
.social-card .row:last-child {{ border-bottom: 0; }}
.social-card .row .label {{ color: var(--ink-muted); }}
.seo-summary {{
  display: grid; grid-template-columns: repeat(3, minmax(0,1fr));
  gap: 12px; margin-bottom: 14px;
}}
.seo-grid2 {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
}}
.seo-card {{ padding: 14px 16px; border-radius: 10px; }}
.seo-card.up {{ background: var(--good-soft); border: 1px solid #c9ebd9; }}
.seo-card.down {{ background: var(--bad-soft); border: 1px solid #efbfc8; }}
.seo-card .name {{
  font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  font-weight: 700;
}}
.seo-card.up .name {{ color: var(--good); }}
.seo-card.down .name {{ color: var(--bad); }}
.seo-card .keyword {{ font-size: 14px; font-weight: 600; margin: 4px 0; }}
.seo-card .meta {{ font-size: 12px; color: var(--ink-soft); }}
.page-footer {{
  max-width: 1140px; margin: 0 auto; padding: 18px 32px 32px;
  font-size: 11px; color: var(--ink-muted);
  display: flex; gap: 18px; flex-wrap: wrap;
  justify-content: space-between;
}}
.block {{
  background: var(--bad-soft); border: 1px solid #efbfc8;
  color: var(--bad); padding: 24px; border-radius: 12px;
  font-family: monospace; white-space: pre-wrap;
}}
.content-card .thumb img {{
  width: 100%; height: 100%; object-fit: cover;
  display: block;
}}
.content-card .thumb-fallback {{
  font-size: 14px; letter-spacing: .04em; font-weight: 600;
}}
.content-card .type-row {{
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 10px; margin-bottom: 6px;
}}
.content-card .type-row .type {{
  margin: 0;
}}
.content-card .pub-date {{
  font-size: 10px; letter-spacing: .04em;
  color: var(--ink-muted); font-weight: 500;
  text-transform: uppercase;
  background: var(--neutral-soft);
  padding: 3px 8px; border-radius: 999px;
  white-space: nowrap;
}}
.content-card .content-permalink {{
  display: inline-block; margin-top: 10px;
  font-size: 12px; font-weight: 600;
  color: var(--brand-primary);
}}
.content-card .content-permalink:hover {{
  text-decoration: underline;
}}
.content-empty {{
  background: var(--neutral-soft); border-radius: 10px;
  padding: 24px; text-align: center;
}}
.content-empty-title {{
  font-weight: 600; color: var(--ink);
  margin-bottom: 6px; font-size: 15px;
}}
.content-empty-meta {{
  font-size: 12px; color: var(--ink-muted); line-height: 1.5;
}}
@media (max-width: 920px) {{
  .kpi-row {{ grid-template-columns: repeat(2, 1fr); }}
  .action-grid {{ grid-template-columns: 1fr; }}
  .target-grid {{ grid-template-columns: 1fr; }}
  .work-attn-grid {{ grid-template-columns: 1fr; }}
  .ad-summary {{ grid-template-columns: repeat(2, 1fr); }}
  .social-grid {{ grid-template-columns: 1fr; }}
  .seo-grid2 {{ grid-template-columns: 1fr; }}
  .content-grid {{ grid-template-columns: 1fr; }}
  .report-block {{ text-align: left; }}
}}
@media print {{
  body {{ background: white; }}
  section.report-section {{ box-shadow: none; }}
  .page-header {{ background: var(--brand-primary); -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .kpi-card, .campaign-card, .target-card, .work-card,
  .attn-card, .exec-card, .content-card, .social-card,
  .action-card, .seo-card {{
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }}
}}
"""


# ── section renderers ──────────────────────────────────────────

def _render_kpi_cards(cards: List[Dict[str, Any]], primary: str) -> str:
    inner = ""
    for c in cards:
        change = c.get("change_text") or "—"
        klass = _pct_class(c.get("change_pct"))
        arrow = {"up": "▲", "down": "▼"}.get(klass, "•")
        secondary = c.get("secondary") or ""
        inner += f"""
        <div class="kpi-card">
          <div class="kpi-label">{_esc(c['label'])}</div>
          <div class="kpi-value">{_esc(c['value'])}</div>
          <div class="kpi-change {klass}"><span class="kpi-arrow">{arrow}</span> {_esc(change)}</div>
          <div class="kpi-secondary">{_esc(secondary)}</div>
        </div>"""
    return f"""<section id="sec-KPI"><div class="kpi-row">{inner}</div></section>"""


def _render_executive_card(exec_text: str, primary: str,
                              accent: str) -> str:
    return f"""
<section id="sec-Executive" class="exec-card">
  <div class="section-eyebrow">This week</div>
  <h2>What happened this week</h2>
  <p class="exec-text">{_esc(exec_text)}</p>
</section>
"""


def _render_website_traffic_table(v24: dict) -> str:
    rows = []
    for label, kind in (
        ("Sessions", "int"),
        ("Users", "int"),
        ("Engaged sessions", "int"),
        ("Engagement rate", "decimal"),
        ("Pageviews", "int"),
    ):
        k = _extract_kpi(v24, label)
        cur_v = k.get("current")
        prev_v = k.get("previous")
        if cur_v is None:
            continue
        _, pct_text = _pct(cur_v, prev_v)
        klass = _pct_class(_pct(cur_v, prev_v)[0])
        rows.append(f"""<tr>
          <td>{_esc(label)}</td>
          <td>{_esc(_fmt(cur_v, kind))}</td>
          <td>{_esc(_fmt(prev_v, kind)) if prev_v is not None else '—'}</td>
          <td class="trend-{klass}">{_esc(pct_text)}</td>
        </tr>""")
    return f"""
<section id="sec-Traffic" class="report-section">
  <div class="section-eyebrow">Website traffic</div>
  <h2>Website traffic</h2>
  <p class="lead">Week-on-week comparison for {len(rows)} traffic metrics.</p>
  <table class="data">
    <thead>
      <tr><th>Metric</th><th>This week</th><th>Last week</th><th>Change</th></tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</section>
"""


def _render_acquisition(v24: dict, primary: str, accent: str) -> str:
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    chans = cm.get("rows") or []
    if not chans:
        return ""
    chans_sorted = sorted(chans,
                            key=lambda c: c.get("current_sessions") or 0,
                            reverse=True)
    total = sum((c.get("current_sessions") or 0) for c in chans_sorted) or 1
    rows_html = ""
    for c in chans_sorted:
        cur_v = c.get("current_sessions")
        prev_v = c.get("previous_sessions")
        share = c.get("share_of_sessions") or 0
        if cur_v is None:
            continue
        _, pct_text = _pct(cur_v, prev_v)
        klass = _pct_class(_pct(cur_v, prev_v)[0])
        bar_w = max(2, min(100, int(share)))
        rows_html += f"""
        <div class="acq-row">
          <span class="acq-label">{_esc(c.get('channel','?'))}</span>
          <span class="acq-bar"><span style="width: {bar_w}%"></span></span>
          <span class="acq-pct">{share:.1f}%</span>
          <span class="acq-change {klass}">{_esc(pct_text)}</span>
        </div>"""
    return f"""
<section id="sec-Acquisition" class="report-section">
  <div class="section-eyebrow">Acquisition</div>
  <h2>Where visitors came from</h2>
  <p class="lead">Share of all website sessions this week, with week-on-week change.</p>
  {rows_html}
</section>
"""


def _render_advertising(v24: dict, primary: str, accent: str) -> str:
    pm = v24.get("paid_media_v24") or {}
    if (pm.get("data_status") or "").upper() != "LIVE":
        return f"""
<section id="sec-Advertising" class="report-section">
  <div class="section-eyebrow">Advertising</div>
  <h2>Advertising</h2>
  <p class="lead">Advertising is not yet connected for this brand.</p>
</section>
"""
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    eff = _compute_paid_efficiency(cur, prev)
    ctr = ((cur.get("total_clicks") or 0)
             / max(cur.get("total_impressions") or 0, 1) * 100)
    cpc = ((cur.get("total_spend") or 0)
             / max(cur.get("total_clicks") or 0, 1))
    summary_cells = [
        ("Spend", _fmt(cur.get("total_spend"), "money")),
        ("People reached", _fmt(cur.get("total_reach"))),
        ("Clicks", _fmt(cur.get("total_clicks"))),
        ("CTR", f"{ctr:.2f}%"),
        ("CPC", f"R{cpc:,.2f}"),
        ("Leads", _fmt(cur.get("total_results"))),
    ]
    summary_html = "".join(
        f"<div class='ad-cell'><div class='label'>{_esc(l)}</div>"
        f"<div class='value'>{_esc(v)}</div></div>"
        for l, v in summary_cells
    )
    by_obj: Dict[str, List[dict]] = {}
    for c in (pm.get("per_campaign") or []):
        if (c.get("current") or {}).get("spend", 0) > 0:
            obj = c.get("objective") or "OUTCOME_OTHER"
            by_obj.setdefault(obj, []).append(c)
    groups_html = ""
    for obj, cs in by_obj.items():
        title, _, _, _ = _OBJECTIVE_GROUP.get(
            obj, ("Other campaigns", "results", "results", "cost per result"))
        cs_sorted = sorted(cs,
                             key=lambda c: (c.get("current") or {}).get("spend", 0),
                             reverse=True)
        cards = ""
        for c in cs_sorted:
            cur_c = c.get("current") or {}
            pr = c.get("primary_result") or {}
            spend = cur_c.get("spend") or 0
            pv = pr.get("primary_value")
            cpr = pr.get("primary_cost_per_unit")
            reach = cur_c.get("reach")
            facts_dl = ""
            facts_dl += f"<dt>Spend</dt><dd>{_esc(_fmt(spend, 'money'))}</dd>"
            if obj == "OUTCOME_AWARENESS":
                if pv is not None:
                    facts_dl += f"<dt>People reached</dt><dd>{_esc(_fmt(pv))}</dd>"
                if cpr is not None:
                    facts_dl += f"<dt>Cost per 1,000 reached</dt><dd>{_esc(_fmt(cpr, 'money_per'))}</dd>"
            elif obj in ("OUTCOME_TRAFFIC", "LINK_CLICKS"):
                if pv is not None:
                    facts_dl += f"<dt>Website visits</dt><dd>{_esc(_fmt(pv))}</dd>"
                if cpr is not None:
                    facts_dl += f"<dt>Cost per visit</dt><dd>{_esc(_fmt(cpr, 'money_per'))}</dd>"
            elif obj == "OUTCOME_ENGAGEMENT":
                if pv is not None:
                    facts_dl += f"<dt>Engagements</dt><dd>{_esc(_fmt(pv))}</dd>"
                if cpr is not None:
                    facts_dl += f"<dt>Cost per engagement</dt><dd>{_esc(_fmt(cpr, 'money_per'))}</dd>"
            elif obj == "OUTCOME_LEADS":
                if pv is not None:
                    facts_dl += f"<dt>Leads</dt><dd>{_esc(_fmt(pv))}</dd>"
                if cpr is not None:
                    facts_dl += f"<dt>Cost per lead</dt><dd>{_esc(_fmt(cpr, 'money_per'))}</dd>"
            else:
                if pv is not None:
                    facts_dl += f"<dt>Result</dt><dd>{_esc(_fmt(pv))}</dd>"
                if cpr is not None:
                    facts_dl += f"<dt>Cost per result</dt><dd>{_esc(_fmt(cpr, 'money_per'))}</dd>"
            if reach and obj != "OUTCOME_AWARENESS":
                facts_dl += f"<dt>People reached</dt><dd>{_esc(_fmt(reach))}</dd>"
            cards += f"""
            <div class="campaign-card">
              <div class="campaign-name">{_esc(c.get('campaign_name','?'))}</div>
              <dl>{facts_dl}</dl>
            </div>"""
        groups_html += f"""
        <div class="ad-group">
          <h3>{_esc(title)}</h3>
          <div class="campaign-list">{cards}</div>
        </div>"""
    return f"""
<section id="sec-Advertising" class="report-section">
  <div class="section-eyebrow">Advertising</div>
  <h2>Advertising on Meta</h2>
  <p class="lead">This week on Facebook and Instagram advertising.</p>
  <div class="ad-summary">{summary_html}</div>
  {groups_html}
</section>
"""


def _render_website_pages(v24: dict) -> str:
    lp = ((v24.get("sections") or {})
            .get("landing_pages") or {})
    sp_list = lp.get("service_pages") or []
    sp_filtered = [sp for sp in sp_list
                     if (sp.get("current_sessions") or 0) > 0]
    if not sp_filtered:
        return ""
    sp_filtered = sorted(sp_filtered,
                          key=lambda s: s.get("current_sessions") or 0,
                          reverse=True)[:6]
    rows = ""
    for sp in sp_filtered:
        cur_s = sp.get("current_sessions")
        prev_s = sp.get("previous_sessions")
        eng = sp.get("engagement_rate") or 0
        _, pct_text = _pct(cur_s, prev_s)
        klass = _pct_class(_pct(cur_s, prev_s)[0])
        display = _page_display_name(sp.get("path") or "")
        rows += f"""
        <tr>
          <td><div>{_esc(display)}</div><div class="kpi-secondary">{_esc(sp.get('path',''))}</div></td>
          <td>{_esc(_fmt(cur_s))}</td>
          <td>{_esc(_fmt(prev_s)) if prev_s is not None else '—'}</td>
          <td class="trend-{klass}">{_esc(pct_text)}</td>
          <td>{eng:.1f}%</td>
        </tr>"""
    return f"""
<section id="sec-Pages" class="report-section">
  <div class="section-eyebrow">Website pages</div>
  <h2>Website pages</h2>
  <p class="lead">Top pages by sessions this week.</p>
  <table class="data">
    <thead>
      <tr><th>Page</th><th>This week</th><th>Last week</th><th>Change</th><th>Engagement</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</section>
"""


def _render_seo(seo: Dict[str, Any], seo_kw: Dict[str, Any],
                  primary: str, bid: str) -> str:
    if seo.get("status") == "NOT_CONNECTED":
        return ""
    if seo.get("status") == "NOT_CONFIGURED":
        return ""
    summary_cells = [
        ("Domain authority", _fmt(seo.get("domain_authority"))),
        ("Backlinks", _fmt(seo.get("backlinks"))),
        ("Referring domains", _fmt(seo.get("ref_domains"))),
        ("Top 3 keywords", _fmt(seo.get("top_3"))),
        ("Top 10 keywords", _fmt(seo.get("top_10"))),
        ("Trending up", _fmt(((seo.get("weekly_change") or {}).get("up")))),
    ]
    summary_html = "".join(
        f"<div class='ad-cell'><div class='label'>{_esc(l)}</div>"
        f"<div class='value'>{_esc(v)}</div></div>"
        for l, v in summary_cells
    )
    fetched_at = seo.get("fetched_at") or ""
    if fetched_at:
        try:
            fetch_dt = datetime.datetime.fromisoformat(
                fetched_at.replace("Z", "+00:00"))
            fetched_label = fetch_dt.strftime("%d %B %Y")
        except Exception:
            fetched_label = fetched_at
    else:
        fetched_label = "unknown"
    # Build winning / leaking lists (top 3 each)
    winning = (seo_kw or {}).get("winning") or []
    leaking = (seo_kw or {}).get("leaking") or []
    def _fmt_kw(kw):
        delta = kw.get("delta", 0)
        cur = kw.get("current_position")
        prev = kw.get("previous_position")
        return (kw.get("keyword") or "?",
                f"#{prev} → #{cur}" if (cur and prev and delta != 0)
                else f"#{cur} (no change)")
    win_html = ""
    for k in winning[:5]:
        kw, motion = _fmt_kw(k)
        win_html += f"""
        <div class="seo-card up">
          <div class="name">Up</div>
          <div class="keyword">{_esc(kw)}</div>
          <div class="meta">{_esc(motion)}</div>
        </div>"""
    leak_html = ""
    for k in leaking[:5]:
        kw, motion = _fmt_kw(k)
        leak_html += f"""
        <div class="seo-card down">
          <div class="name">Down</div>
          <div class="keyword">{_esc(kw)}</div>
          <div class="meta">{_esc(motion)}</div>
        </div>"""
    return f"""
<section id="sec-SEO" class="report-section">
  <div class="section-eyebrow">Google search</div>
  <h2>Google search / SEO</h2>
  <p class="lead">Ubersuggest summary for this brand. Data updated {_esc(fetched_label)}.</p>
  <div class="seo-summary">{summary_html}</div>
  <div class="seo-grid2">
    <div>
      <h3 style="font-size:13px;color:var(--good);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;">Biggest gains</h3>
      {win_html or '<div class="kpi-secondary">No significant upward movement this week.</div>'}
    </div>
    <div>
      <h3 style="font-size:13px;color:var(--bad);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;">Biggest drops</h3>
      {leak_html or '<div class="kpi-secondary">No significant downward movement this week.</div>'}
    </div>
  </div>
</section>
"""


def _render_social(bid: str, organic: Dict[str, Any], primary: str) -> str:
    ig = organic.get("ig") or {}
    fb = organic.get("fb") or {}
    ig_status = ig.get("status", "NOT_CONNECTED")
    fb_status = fb.get("status", "NOT_CONNECTED")
    if ig_status == "NOT_CONNECTED" and fb_status == "NOT_CONNECTED":
        return ""
    ig_html = ""
    if ig_status != "NOT_CONNECTED":
        rows = ""
        for label, key in (
            ("Total interactions", "interactions"),
            ("People reached", "reach"),
            ("Profile visits", "profile_views"),
            ("Profile link taps", "profile_links_taps"),
            ("Accounts engaged", "accounts_engaged"),
            ("Followers", "followers"),
        ):
            v = ig.get(key)
            if v is None:
                continue
            rows += f"""
            <div class="row"><span class="label">{_esc(label)}</span><span>{_esc(_fmt(v))}</span></div>"""
        ig_html = f"""
        <div class="social-card">
          <div class="name"><span class="dot"></span>Instagram <span class="kpi-secondary">{_esc(ig.get('username',''))}</span></div>
          {rows}
        </div>"""
    elif ig_status == "PARTIAL":
        ig_html = """
        <div class="social-card">
          <div class="name"><span class="dot"></span>Instagram</div>
          <div class="kpi-secondary">Instagram reporting is partly set up but the data is not full enough yet.</div>
        </div>"""
    fb_html = ""
    if fb_status != "NOT_CONNECTED":
        rows = ""
        for label, key in (
            ("Reach", "impressions"),
            ("Engagement", "engagements"),
            ("Page visits", "clicks"),
            ("Page fans", "fans"),
        ):
            v = fb.get(key)
            if v is None:
                continue
            rows += f"""
            <div class="row"><span class="label">{_esc(label)}</span><span>{_esc(_fmt(v))}</span></div>"""
        fb_html = f"""
        <div class="social-card">
          <div class="name"><span class="dot"></span>Facebook page</div>
          {rows}
        </div>"""
    elif fb_status == "PARTIAL":
        fb_html = """
        <div class="social-card">
          <div class="name"><span class="dot"></span>Facebook page</div>
          <div class="kpi-secondary">Some Facebook reporting is still unavailable.</div>
        </div>"""
    return f"""
<section id="sec-Social" class="report-section">
  <div class="section-eyebrow">Social media</div>
  <h2>Social media</h2>
  <p class="lead">Last 28 days from each social platform.</p>
  <div class="social-grid">
    {ig_html}
    {fb_html}
  </div>
</section>
"""


def _render_best_content(bid: str, organic: Dict[str, Any],
                           primary: str,
                           periods: Optional[Dict[str, str]] = None) -> str:
    """V3.6: only show posts published during the report week.

    Reads Instagram posts via insights_correlator (in-process, no
    external HTTP). Filters by week. Shows published date on the
    card. Uses the real thumbnail when available, otherwise the
    brand-coloured fallback.

    Never fills empty slots with older posts. If only one post
    was published this week, one card. If none, an honest
    'No new feed posts were published this week.' message.
    """
    cur_start = (periods or {}).get("current_week_start", "")
    cur_end = (periods or {}).get("current_week_end", "")
    cur_end_dt = _dt_mod.date.fromisoformat(cur_end) if cur_end else None
    cur_start_dt = _dt_mod.date.fromisoformat(cur_start) if cur_start else None
    # Load posts for THIS brand (brand-scoped, not delegated)
    posts = _read_instagram_posts_for_brand(bid)
    week_posts: List[Dict[str, Any]] = []
    for p in posts:
        pa = p.get("published_at")
        if pa is None:
            continue
        if cur_start_dt and cur_end_dt:
            if not (cur_start_dt <= pa.date() <= cur_end_dt):
                continue
        week_posts.append(p)
    # Rank by reach, then interactions
    week_posts.sort(
        key=lambda p: ((p.get("reach") or 0), (p.get("interactions") or 0)),
        reverse=True,
    )
    # Section header
    period_label = ""
    if cur_start_dt and cur_end_dt:
        period_label = (f"{cur_start_dt.strftime('%d %B')} → " 
                          f"{cur_end_dt.strftime('%d %B %Y')}")
    if not week_posts:
        # Empty week — honest message. Don't fill slots.
        return f"""
<section id="sec-Content" class="report-section">
  <div class="section-eyebrow">Best content</div>
  <h2>Best content</h2>
  <p class="lead">Posts published between {period_label or 'this period'}.</p>
  <div class="content-empty">
    <div class="content-empty-title">No new feed posts were published this week.</div>
    <div class="content-empty-meta">No new posts were published this week.
      Older posts are kept in the historical archive but never shown
      under "Best content" in the weekly report.</div>
  </div>
</section>
"""
    # Render cards (one per post this week — DO NOT cap to 3)
    cards = ""
    for p in week_posts:
        media_product_type = (p.get("media_product_type") or "").upper()
        media_type = (p.get("media_type") or "IMAGE").upper()
        # media_product_type is more specific (FEED / REELS / STORY)
        # but it's optional and not requested by default.
        if media_product_type == "REELS":
            type_word = "Reel"
        elif media_product_type == "STORY":
            type_word = "Story"
        else:
            type_word = {"VIDEO": "Reel", "IMAGE": "Image",
                           "CAROUSEL_ALBUM": "Carousel",
                           "REEL": "Reel"}.get(media_type, "Post")
        caption = (p.get("caption") or "").replace("\n", " ").strip()
        if len(caption) > 130:
            caption = caption[:127] + "..."
        thumb = p.get("thumbnail_url") or ""
        pa = p.get("published_at")
        pub_date_label = (pa.strftime("%d %b") if pa else "?")
        full_pub_date = (pa.strftime("%d %B %Y") if pa else "")
        # Card
        if thumb:
            thumb_html = (f'<img src="{_esc(thumb)}" alt="{_esc(type_word)} preview" '
                            f'loading="lazy" />')
        else:
            thumb_html = f'<span class="thumb-fallback">IG · {type_word}</span>'
        permalink = p.get("permalink") or ""
        reach = p.get("reach") or 0
        interactions = p.get("interactions") or 0
        permalink_html = (f'<a href="{_esc(permalink)}" target="_blank" '
                            f'rel="noopener" class="content-permalink">'
                            f'View on Instagram ↗</a>' if permalink else '')
        cards += f"""
        <div class="content-card">
          <div class="thumb">{thumb_html}</div>
          <div class="meta">
            <div class="type-row">
              <span class="type">{_esc(type_word)}</span>
              <span class="pub-date" title="{_esc(full_pub_date)}">Published {_esc(pub_date_label)}</span>
            </div>
            <div class="caption">{_esc(caption) or '<span class="kpi-secondary">(no caption)</span>'}</div>
            <div class="stats">
              <span>Reach: <strong>{_esc(_fmt(reach))}</strong></span>
              <span>Interactions: <strong>{_esc(_fmt(interactions))}</strong></span>
            </div>
            {permalink_html}
          </div>
        </div>"""
    count_n = len(week_posts)
    post_word = "post" if count_n == 1 else "posts"
    # How many stories were active during the week (only the past 24h
    # are still retrievable from Meta — surfaced separately in
    # sec-Stories; here we count just the feed posts since stories
    # can't be backfilled past 24h).
    story_count = len(_read_instagram_stories_for_brand(bid))
    lead_parts = []
    if period_label:
        lead_parts.append(
            f"{count_n} {post_word} published between {period_label}. ")
    else:
        lead_parts.append(
            f"{count_n} {post_word} published this week. ")
    lead_parts.append("Ranked by people reached, then interactions. ")
    if story_count > 0:
        s_word = "story" if story_count == 1 else "stories"
        lead_parts.append(
            f"Plus {story_count} active {s_word} in the past 24 hours "
            f"(see Stories this week below).")
    else:
        lead_parts.append(
            "No active stories in the past 24 hours — "
            "see Stories this week below.")
    lead = "".join(lead_parts)
    return f"""
<section id="sec-Content" class="report-section">
  <div class="section-eyebrow">Best content</div>
  <h2>Best content</h2>
  <p class="lead">{_esc(lead)}</p>
  <div class="content-grid">{cards}</div>
</section>
"""


def _render_worked_attention(v24: dict, primary: str) -> str:
    s = _extract_kpi(v24, "Sessions")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    worked: List[str] = []
    attn: List[str] = []
    s_cur = s.get("current"); s_prev = s.get("previous")
    if (s_cur is not None and s_prev is not None and s_prev > 0
            and s_cur > s_prev and (s_cur - s_prev) >= 10):
        pct = (s_cur - s_prev) / s_prev * 100
        worked.append(
            f"Website sessions increased from {_fmt(s_prev)} to "
            f"{_fmt(s_cur)} ({pct:.1f}% more than last week).")
    for ch in (cm.get("rows") or []):
        cur_v = ch.get("current_sessions")
        prev_v = ch.get("previous_sessions")
        if (cur_v is not None and prev_v is not None and cur_v > prev_v
                and (cur_v - prev_v) >= 10
                and ch.get("comparison_status") == "improving"):
            share = ch.get("share_of_sessions") or 0
            worked.append(
                f"{ch.get('channel')} brought more visitors this week "
                f"({_fmt(cur_v)} sessions, up from {_fmt(prev_v)}, "
                f"{share:.1f}% of all sessions).")
    lp = ((v24.get("sections") or {}).get("landing_pages") or {})
    for sp in (lp.get("service_pages") or [])[:3]:
        if (sp.get("current_sessions") or 0) >= 5 and sp.get("engagement_rate", 0) >= 70:
            worked.append(
                f"The page '{_page_display_name(sp.get('path',''))}' had strong "
                f"engagement ({sp.get('engagement_rate'):.1f}% of visitors "
                f"interacted with it, from {_fmt(sp.get('current_sessions'))} "
                f"sessions).")
    pm = v24.get("paid_media_v24") or {}
    for ch in (cm.get("rows") or []):
        cur_v = ch.get("current_sessions")
        prev_v = ch.get("previous_sessions")
        share = ch.get("share_of_sessions") or 0
        if (cur_v is not None and prev_v is not None and cur_v < prev_v
                and (prev_v - cur_v) >= 10 and share >= 10):
            attn.append(
                f"{ch.get('channel')} sessions fell from {_fmt(prev_v)} to "
                f"{_fmt(cur_v)} last week — worth checking why.")
    if (cur.get("total_impressions", 0) > 0
            and prev.get("total_impressions", 0) > 0):
        imp_pct = ((cur["total_impressions"] - prev["total_impressions"])
                     / prev["total_impressions"] * 100)
        if imp_pct <= -15:
            attn.append(
                f"Meta ads reached {abs(imp_pct):.1f}% fewer people this week "
                f"({_fmt(prev['total_impressions'])} → "
                f"{_fmt(cur['total_impressions'])} impressions). "
                f"This is a meaningful drop in delivery.")
    for grp in (pm.get("duplicate_campaigns_visible") or []):
        attn.append(
            f"Two campaigns with the same name are running at the same time "
            f"({grp.get('campaign_count')} campaigns: "
            f"{', '.join((grp.get('campaign_ids') or []))}). "
            f"Check whether both are meant to be active.")
    leads = _extract_kpi(v24, "Verified Leads")
    if leads.get("data_status") == "PENDING":
        attn.append(
            "We still cannot tell how many Meta leads turned into real "
            "bookings — the bookings link to marketing is not in place.")
    if not worked:
        worked.append("Nothing stood out clearly as a positive result this week.")
    if not attn:
        attn.append("Nothing important is asking for attention right now.")
    worked_html = "".join(f"<li>{_esc(w)}</li>" for w in worked)
    attn_html = "".join(f"<li>{_esc(w)}</li>" for w in attn)
    return f"""
<section id="sec-Worked" class="report-section">
  <div class="section-eyebrow">Outcomes</div>
  <h2>What worked & what needs attention</h2>
  <div class="work-attn-grid">
    <div class="work-card">
      <div class="label">What worked</div>
      <ul>{worked_html}</ul>
    </div>
    <div class="attn-card">
      <div class="label">Needs attention</div>
      <ul>{attn_html}</ul>
    </div>
  </div>
</section>
"""


def _render_actions(v24: dict, bid: str, primary: str, accent: str) -> str:
    actions = _derive_actions(v24, bid)
    if not actions:
        return ""
    cards = ""
    for i, a in enumerate(actions, 1):
        cards += f"""
        <div class="action-card">
          <span class="num">{i:02d}</span>
          <div class="what">{_esc(a['what'])}</div>
          <div class="why">{_esc(a['why'])}</div>
          <div class="watch"><strong>Watch:</strong> {_esc(a['watch'])}</div>
        </div>"""
    return f"""
<section id="sec-Actions" class="report-section">
  <div class="section-eyebrow">This week</div>
  <h2>What we should do this week</h2>
  <p class="lead">Maximum three actions, each with evidence and a metric to monitor.</p>
  <div class="action-grid">{cards}</div>
</section>
"""


def _render_targets(v24: dict, primary: str, accent: str, bid: str) -> str:
    ns = _extract_north_stars_from_v24(v24)
    confirmed = [n for n in ns if not n["pending"]]
    pending = [n for n in ns if n["pending"]]
    cards_html = ""
    if confirmed:
        for n in confirmed:
            cards_html += f"""
            <div class="target-card">
              <div class="name">{_esc(n['label'])}</div>
              <div class="metric">{_esc(n['metric'])}</div>
            </div>"""
    if not cards_html:
        # Operator directive: do NOT show unfinished labels in Herman's
        # report. If nothing is confirmed, surface an empty state.
        return ""
    return f"""
<section id="sec-Targets" class="report-section">
  <div class="section-eyebrow">Business targets</div>
  <h2>Business targets</h2>
  <p class="lead">Actual sales and booking results are not connected yet, so this report cannot show progress against these targets.</p>
  <div class="target-grid">{cards_html}</div>
</section>
"""


def _render_data_missing(v24: dict, organic: Dict[str, Any],
                            seo: Dict[str, Any], primary: str) -> str:
    items: List[str] = []
    leads = _extract_kpi(v24, "Verified Leads")
    if leads.get("data_status") == "PENDING":
        items.append(
            "Linking bookings or sales back to marketing leads is not yet "
            "in place — so we cannot show how many leads became real "
            "customers.")
    ig = organic.get("ig") or {}
    if ig.get("status") == "NOT_CONNECTED":
        items.append("Instagram reporting is not set up yet.")
    elif ig.get("status") == "PARTIAL":
        items.append("Instagram reporting is partly set up but the data is "
                       "not full enough yet.")
    fb = organic.get("fb") or {}
    if fb.get("status") == "PARTIAL":
        items.append("Some Facebook reporting is still unavailable.")
    elif fb.get("status") == "NOT_CONNECTED":
        items.append("Facebook page reporting is not set up yet.")
    if seo.get("status") == "NOT_CONNECTED":
        items.append("SEO (Ubersuggest) reporting is not set up yet.")
    if not items:
        items.append("No missing data sources reported this week.")
    items_html = "".join(f"<li>{_esc(i)}</li>" for i in items)
    return f"""
<section id="sec-Missing" class="report-section">
  <div class="section-eyebrow">Data gaps</div>
  <h2>Data still missing</h2>
  <ul class="missing-list">{items_html}</ul>
</section>
"""


# ── markdown rendering (portable text version) ─────────────────

def _render_markdown(bid: str, v24: dict, organic: Dict[str, Any],
                       seo: Dict[str, Any], seo_kw: Dict[str, Any],
                       periods: Dict[str, str],
                       contamination_block: Optional[str] = None,
                       as_of: Optional[str] = None) -> str:
    facts = _brand_canonical(bid)
    display = facts["display_name"]
    if contamination_block:
        return (f"# {display} Weekly Marketing Report — BLOCKED\n\n"
                  f"{contamination_block}")
    cards = _kpi_cards(bid, v24, periods)
    exec_text = _build_executive_narrative(bid, v24, organic, periods)
    cur_label = (f"{_fmt_period_label(periods['current_week_start'])} → "
                  f"{_fmt_period_label(periods['current_week_end'])}")
    prev_label = (f"{_fmt_period_label(periods['previous_week_start'])} → "
                    f"{_fmt_period_label(periods['previous_week_end'])}")
    L: List[str] = []
    L.append(f"# {display} Weekly Marketing Report")
    L.append(f"_{cur_label}_  ")
    L.append(f"_Compared with {prev_label}_")
    L.append("")
    L.append("## This week at a glance")
    L.append("")
    for c in cards:
        L.append(f"- **{c['label']}** — {c['value']} "
                  f"(change vs last week: {c['change_text']})")
    L.append("")
    L.append("**What happened this week:**")
    L.append("")
    L.append(exec_text)
    L.append("")
    L.append("## Website traffic")
    L.append("")
    L.append("| Metric | This week | Last week | Change |")
    L.append("|---|---|---|---|")
    for label, kind in (
        ("Sessions", "int"),
        ("Users", "int"),
        ("Engaged sessions", "int"),
        ("Engagement rate", "decimal"),
        ("Pageviews", "int"),
    ):
        k = _extract_kpi(v24, label)
        cur_v = k.get("current"); prev_v = k.get("previous")
        if cur_v is None:
            continue
        _, pct_text = _pct(cur_v, prev_v)
        L.append(f"| {label} | {_fmt(cur_v, kind)} | "
                  f"{_fmt(prev_v, kind) if prev_v is not None else '—'} | "
                  f"{pct_text} |")
    L.append("")
    L.append("## Where visitors came from")
    L.append("")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    for c in sorted(cm.get("rows") or [],
                     key=lambda c: c.get("current_sessions") or 0,
                     reverse=True):
        cur_v = c.get("current_sessions")
        prev_v = c.get("previous_sessions")
        share = c.get("share_of_sessions") or 0
        if cur_v is None:
            continue
        _, pct_text = _pct(cur_v, prev_v)
        L.append(f"- **{c.get('channel','?')}** — {_fmt(cur_v)} sessions "
                  f"({pct_text} vs {_fmt(prev_v)}, "
                  f"{share:.1f}% of total)")
    L.append("")
    L.append("## Advertising")
    L.append("")
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    ctr = ((cur.get("total_clicks") or 0)
             / max(cur.get("total_impressions") or 0, 1) * 100)
    cpc = ((cur.get("total_spend") or 0)
             / max(cur.get("total_clicks") or 0, 1))
    L.append(f"- Spend: {_fmt(cur.get('total_spend'), 'money')} "
              f"({_pct(cur.get('total_spend'), prev.get('total_spend'))[1]} vs last week)")
    L.append(f"- People reached: {_fmt(cur.get('total_reach'))}")
    L.append(f"- Clicks: {_fmt(cur.get('total_clicks'))}")
    L.append(f"- CTR: {ctr:.2f}%")
    L.append(f"- CPC: R{cpc:,.2f}")
    L.append(f"- Meta leads (lead campaigns): {_fmt(cur.get('total_results'))}")
    L.append("")
    pm = v24.get("paid_media_v24") or {}
    by_obj: Dict[str, List[dict]] = {}
    for c in (pm.get("per_campaign") or []):
        if (c.get("current") or {}).get("spend", 0) > 0:
            obj = c.get("objective") or "OUTCOME_OTHER"
            by_obj.setdefault(obj, []).append(c)
    for obj, cs in by_obj.items():
        title, _, _, _ = _OBJECTIVE_GROUP.get(
            obj, ("Other campaigns", "results", "results", "cost per result"))
        L.append(f"### {title}")
        for c in sorted(cs, key=lambda c: (c.get("current") or {}).get("spend", 0),
                          reverse=True):
            cur_c = c.get("current") or {}
            pr = c.get("primary_result") or {}
            spend = cur_c.get("spend") or 0
            pv = pr.get("primary_value")
            cpr = pr.get("primary_cost_per_unit")
            L.append(f"- **{c.get('campaign_name','?')}** — spend "
                      f"{_fmt(spend, 'money')}")
            if obj == "OUTCOME_AWARENESS" and pv is not None:
                L.append(f"  - People reached: {_fmt(pv)}")
                if cpr is not None:
                    L.append(f"  - Cost per 1,000 reached: "
                              f"{_fmt(cpr, 'money_per')}")
            elif obj in ("OUTCOME_TRAFFIC", "LINK_CLICKS") and pv is not None:
                L.append(f"  - Website visits from this ad: {_fmt(pv)}")
                if cpr is not None:
                    L.append(f"  - Cost per visit: {_fmt(cpr, 'money_per')}")
            elif obj == "OUTCOME_LEADS" and pv is not None:
                L.append(f"  - Leads: {_fmt(pv)}")
                if cpr is not None:
                    L.append(f"  - Cost per lead: {_fmt(cpr, 'money_per')}")
            elif obj == "OUTCOME_ENGAGEMENT" and pv is not None:
                L.append(f"  - Engagements: {_fmt(pv)}")
                if cpr is not None:
                    L.append(f"  - Cost per engagement: {_fmt(cpr, 'money_per')}")
            elif pv is not None:
                L.append(f"  - Result: {_fmt(pv)}")
                if cpr is not None:
                    L.append(f"  - Cost per result: {_fmt(cpr, 'money_per')}")
        L.append("")
    L.append("## Website pages")
    L.append("")
    L.append("| Page | This week | Last week | Change | Engagement |")
    L.append("|---|---|---|---|---|")
    lp = ((v24.get("sections") or {}).get("landing_pages") or {})
    for sp in sorted(lp.get("service_pages") or [],
                       key=lambda s: s.get("current_sessions") or 0,
                       reverse=True)[:6]:
        if (sp.get("current_sessions") or 0) <= 0:
            continue
        _, pct_text = _pct(sp.get("current_sessions"),
                            sp.get("previous_sessions"))
        L.append(f"| {_page_display_name(sp.get('path',''))} | "
                  f"{_fmt(sp.get('current_sessions'))} | "
                  f"{_fmt(sp.get('previous_sessions'))} | "
                  f"{pct_text} | {sp.get('engagement_rate',0):.1f}% |")
    L.append("")
    if seo.get("status") not in ("NOT_CONNECTED", "NOT_CONFIGURED"):
        L.append("## Google search / SEO")
        L.append("")
        L.append(f"- Domain authority: {_fmt(seo.get('domain_authority'))}")
        L.append(f"- Backlinks: {_fmt(seo.get('backlinks'))}")
        L.append(f"- Referring domains: {_fmt(seo.get('ref_domains'))}")
        L.append(f"- Top 3 keywords: {_fmt(seo.get('top_3'))}")
        L.append(f"- Top 10 keywords: {_fmt(seo.get('top_10'))}")
        wc = seo.get("weekly_change") or {}
        L.append(f"- Trending up this week: {wc.get('up', 0)}, "
                  f"down: {wc.get('down', 0)}, unchanged: {wc.get('unchanged', 0)}")
        L.append("")
        winning = (seo_kw or {}).get("winning") or []
        leaking = (seo_kw or {}).get("leaking") or []
        if winning:
            L.append("**Biggest gains:**")
            for k in winning[:5]:
                cur = k.get("current_position"); prev = k.get("previous_position")
                L.append(f"- {k.get('keyword')} — "
                          f"#{prev} → #{cur}" if (cur and prev and cur != prev)
                          else f"- {k.get('keyword')} — #{cur}")
            L.append("")
        if leaking:
            L.append("**Biggest drops:**")
            for k in leaking[:5]:
                cur = k.get("current_position"); prev = k.get("previous_position")
                L.append(f"- {k.get('keyword')} — "
                          f"#{prev} → #{cur}" if (cur and prev and cur != prev)
                          else f"- {k.get('keyword')} — #{cur}")
            L.append("")
    L.append("## Social media")
    L.append("")
    ig = organic.get("ig") or {}
    fb = organic.get("fb") or {}
    if ig.get("status") != "NOT_CONNECTED":
        L.append("**Instagram (last 28 days):**")
        L.append(f"- Total interactions: {_fmt(ig.get('interactions'))}")
        L.append(f"- People reached: {_fmt(ig.get('reach'))}")
        L.append(f"- Profile visits: {_fmt(ig.get('profile_views'))}")
        L.append(f"- Followers: {_fmt(ig.get('followers'))}")
        L.append("")
    if fb.get("status") != "NOT_CONNECTED":
        L.append("**Facebook page (last 28 days):**")
        L.append(f"- Engagements: {_fmt(fb.get('engagements'))}")
        L.append(f"- Reach: {_fmt(fb.get('impressions'))}")
        L.append(f"- Clicks: {_fmt(fb.get('clicks'))}")
        L.append(f"- Page fans: {_fmt(fb.get('fans'))}")
        L.append("")
    L.append("## Best content")
    L.append("")
    # V3.6: filter to report week only
    cur_start_dt = (datetime.date.fromisoformat(periods['current_week_start'])
                      if periods.get('current_week_start') else None)
    cur_end_dt = (datetime.date.fromisoformat(periods['current_week_end'])
                    if periods.get('current_week_end') else None)
    week_posts: List[Dict[str, Any]] = []
    for p in _read_instagram_posts_for_brand(bid):
        pa = p.get("published_at")
        if not pa:
            continue
        if cur_start_dt and cur_end_dt and not (cur_start_dt <= pa.date() <= cur_end_dt):
            continue
        week_posts.append(p)
    week_posts.sort(key=lambda p: ((p.get("reach") or 0), (p.get("interactions") or 0)),
                      reverse=True)
    if not week_posts:
        L.append("No new feed posts were published this week.")
        L.append("")
    else:
        for p in week_posts:
            media_type = (p.get("media_type") or "IMAGE").upper()
            type_word = {"VIDEO": "Reel", "IMAGE": "Image"}.get(media_type, "Post")
            caption = (p.get("caption") or "").replace("\n", " ").strip()
            if len(caption) > 110:
                caption = caption[:107] + "..."
            pa = p.get("published_at")
            pub_date_label = pa.strftime("%d %b %Y") if pa else "unknown date"
            L.append(f"- **{type_word} — published {pub_date_label}:** {caption}")
            L.append(f"  - Reach: {_fmt(p.get('reach'))}, "
                      f"interactions: {_fmt(p.get('interactions'))}")
            if p.get("permalink"):
                L.append(f"  - [View on Instagram]({p['permalink']})")
        L.append("")
    L.append("## What worked")
    L.append("")
    # re-derive briefly
    s = _extract_kpi(v24, "Sessions")
    for ch in (cm.get("rows") or []):
        cur_v = ch.get("current_sessions"); prev_v = ch.get("previous_sessions")
        if (cur_v is not None and prev_v is not None
                and cur_v > prev_v and (cur_v - prev_v) >= 10
                and ch.get("comparison_status") == "improving"):
            share = ch.get("share_of_sessions") or 0
            L.append(f"- {ch.get('channel')} brought more visitors this week "
                      f"({_fmt(cur_v)} vs {_fmt(prev_v)}, "
                      f"{share:.1f}% of total).")
    L.append("")
    L.append("## What needs attention")
    L.append("")
    for ch in (cm.get("rows") or []):
        cur_v = ch.get("current_sessions"); prev_v = ch.get("previous_sessions")
        share = ch.get("share_of_sessions") or 0
        if (cur_v is not None and prev_v is not None and cur_v < prev_v
                and (prev_v - cur_v) >= 10 and share >= 10):
            L.append(f"- {ch.get('channel')} fell from {_fmt(prev_v)} to "
                      f"{_fmt(cur_v)} sessions.")
    leads = _extract_kpi(v24, "Verified Leads")
    if leads.get("data_status") == "PENDING":
        L.append("- Bookings → leads link is not yet in place.")
    L.append("")
    L.append("## What we should do this week")
    L.append("")
    actions = _derive_actions(v24, bid)
    for i, a in enumerate(actions, 1):
        L.append(f"{i}. **{a['what']}**")
        L.append(f"   - Why: {a['why']}")
        L.append(f"   - What to watch: {a['watch']}")
    L.append("")
    confirmed = [n for n in _extract_north_stars_from_v24(v24)
                  if not n["pending"]]
    if confirmed:
        L.append("## Business targets")
        L.append("")
        for n in confirmed:
            L.append(f"- **{n['label']}** — {n['metric']}")
        L.append("")
        L.append("Actual sales and booking results are not connected yet.")
        L.append("")
    L.append("## Data still missing")
    L.append("")
    if leads.get("data_status") == "PENDING":
        L.append("- Linking bookings or sales back to marketing leads is not "
                  "yet in place.")
    if ig.get("status") == "PARTIAL":
        L.append("- Instagram reporting is partly set up but the data is not "
                  "full enough yet.")
    if fb.get("status") == "PARTIAL":
        L.append("- Some Facebook reporting is still unavailable.")
    if seo.get("status") == "NOT_CONNECTED":
        L.append("- SEO (Ubersuggest) reporting is not set up yet.")
    L.append("")
    return "\n".join(L)


# ── main entry ─────────────────────────────────────────────────

def build_v36(bid: str, fmt: str = "markdown",
                as_of: Optional[str] = None,
                cookie: Optional[str] = None) -> dict:
    if bid not in ("stick", "swing-shack", "bag-drop"):
        return {"report_status": "INVALID_BRAND",
                "block_reason": "brand_id must be stick, swing-shack, or bag-drop",
                "contaminations": [],
                "rendered": f"# Invalid brand\n\n`{bid}` is not a managed brand.",
                "raw_payload": {}}
    periods = _compute_periods(as_of)
    v24 = _read_v24(bid, as_of, cookie=cookie)
    if not v24 or "error" in v24:
        return {
            "report_status": "V24_UNAVAILABLE",
            "block_reason": v24.get("error", "V2.4.1 read failed"),
            "contaminations": [],
            "rendered": (f"# {bid.title()} Weekly Marketing Report\n\n"
                          f"V2.4.1 unavailable: "
                          f"{v24.get('error', 'unknown error')}"),
            "raw_payload": {"v24": v24, "periods": periods},
        }
    clean, violations = _validate_brand_isolation(bid, v24)
    if not clean:
        block = ("Identifiers found in V2.4.1 payload:\n"
                  + "\n".join(f"- `{v}`" for v in violations)
                  + "\n\nThis report will not render until the canonical "
                    "V2.4.1 data sources are scoped to this brand only.")
        return {
            "report_status": "BLOCKED_BRAND_CONTAMINATION",
            "block_reason": "V2.4.1 payload contains identifiers from a "
                             "different brand.",
            "contaminations": violations,
            "rendered": _render_html(bid, v24, {}, {}, {}, periods,
                                       contamination_block=block,
                                       as_of=as_of),
            "raw_payload": {"v24": v24, "periods": periods},
        }
    organic = _read_organic_from_cache(bid)
    seo = _read_seo_from_cache(bid)
    seo_kw = _read_seo_keywords(bid, cookie=cookie)
    status = "OK"
    if fmt == "html":
        rendered = _render_html(bid, v24, organic, seo, seo_kw, periods,
                                  as_of=as_of)
    elif fmt == "json":
        rendered = _render_markdown(bid, v24, organic, seo, seo_kw, periods,
                                       as_of=as_of)
    else:
        rendered = _render_markdown(bid, v24, organic, seo, seo_kw, periods,
                                       as_of=as_of)
    return {
        "report_status": status,
        "block_reason": None,
        "contaminations": [],
        "rendered": rendered,
        "raw_payload": {
            "v24": v24,
            "periods": periods,
            "brand_id": bid,
            "generator": "weekly_report_v3.6",
            "as_of": as_of,
            "organic": organic,
            "seo": seo,
            "seo_keywords": seo_kw,
        },
    }


def archive_snapshot_v36(bid: str, as_of: Optional[str] = None,
                            snapshot_root: Optional[Path] = None,
                            cookie: Optional[str] = None) -> Dict[str, Any]:
    out = build_v36(bid, fmt="json", as_of=as_of, cookie=cookie)
    v24 = (out.get("raw_payload") or {}).get("v24") or {}
    periods = (out.get("raw_payload") or {}).get("periods") or {}
    organic = (out.get("raw_payload") or {}).get("organic") or {}
    seo = (out.get("raw_payload") or {}).get("seo") or {}
    snapshot = {
        "schema": "https://campaign-os/weekly-report/v3.6-snapshot",
        "brand_id": bid,
        "as_of": as_of or periods.get("data_complete_through"),
        "current_period": {
            "start": periods.get("current_week_start"),
            "end": periods.get("current_week_end"),
        },
        "previous_period": {
            "start": periods.get("previous_week_start"),
            "end": periods.get("previous_week_end"),
        },
        "data_complete_through": periods.get("data_complete_through"),
        "kpi_values": {},
        "seo": seo,
        "organic_status": {
            "instagram": (organic.get("ig") or {}).get("status"),
            "facebook": (organic.get("fb") or {}).get("status"),
        },
        "report_status": out.get("report_status"),
        "archived_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
    }
    for label in ("Sessions", "Users", "Engaged sessions",
                    "Engagement rate", "Pageviews", "Conversions",
                    "Paid Spend", "Verified Leads"):
        r = _extract_kpi(v24, label)
        snapshot["kpi_values"][label] = {
            "current": r.get("current"),
            "previous": r.get("previous"),
            "data_status": r.get("data_status"),
        }
    pm = v24.get("paid_media_v24") or {}
    pt = _paid_totals_from_campaigns(v24)
    snapshot["kpi_values"]["paid_media_v24"] = {
        "data_status": pm.get("data_status"),
        "freshness": pm.get("freshness"),
        "data_as_of": pm.get("data_as_of"),
        "current_period": pt.get("current_period"),
        "previous_period": pt.get("previous_period"),
    }
    root = snapshot_root or _data_root()
    snap_dir = root / "weekly-snapshots" / bid
    snap_dir.mkdir(parents=True, exist_ok=True)
    fn = snap_dir / f"{snapshot['current_period']['end']}.json"
    fn.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False,
                                default=str), encoding="utf-8")
    snapshot["path"] = fn.as_posix()
    return snapshot


# Backwards-compat aliases for older callers in app.py
def build_v31(*args, **kwargs):
    return build_v36(*args, **kwargs)


def build_v32(*args, **kwargs):
    return build_v36(*args, **kwargs)


def build_v33(*args, **kwargs):
    return build_v36(*args, **kwargs)


def build_v34(*args, **kwargs):
    return build_v36(*args, **kwargs)


def archive_snapshot_v31(*args, **kwargs):
    return archive_snapshot_v36(*args, **kwargs)


def archive_snapshot_v32(*args, **kwargs):
    return archive_snapshot_v36(*args, **kwargs)


def archive_snapshot_v33(*args, **kwargs):
    return archive_snapshot_v36(*args, **kwargs)


def archive_snapshot_v34(*args, **kwargs):
    return archive_snapshot_v36(*args, **kwargs)


if __name__ == "__main__":
    bid = sys.argv[1] if len(sys.argv) > 1 else "stick"
    fmt = sys.argv[2] if len(sys.argv) > 2 else "markdown"
    as_of = sys.argv[3] if len(sys.argv) > 3 else None
    out = build_v35(bid, fmt=fmt, as_of=as_of)
    print(out["rendered"])
    sys.exit(0 if out["report_status"] == "OK" else 2)
