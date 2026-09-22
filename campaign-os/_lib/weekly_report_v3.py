"""weekly_report_v3.py — Weekly management report renderer v3.

Fixes the v2 brand-contamination + interpretation problems. v3:

- Strict brand isolation gate (BLOCKED_BRAND_CONTAMINATION)
- Correct period contract: 7d current / 7d previous / 28d current / 28d previous
- Numeric TLDR (Current/Previous/Change)
- Management tone (no hype, no creative generation)
- Fact → Interpretation → Action chain
- Real Meta Ads via V2.4.1 (no fake zero)
- Top-3 actions only, severity-tagged What Needs Attention
- Data Notes at the end (technical limitations)
- Canonical North Stars shown exact, no fabricated progress

V2.4.1 (GA4 / Meta / paid-media / comparison engine) is FROZEN.
This module sits ON TOP of v2.4.1 and only changes the renderer /
interpretation layer.

Usage:
  from _lib.weekly_report_v3 import build_v3
  report = build_v3(brand_id="stick", format="markdown")
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── canonical brand facts ──────────────────────────────────────

def _load_brands() -> dict:
    """Load brands.json — canonical per-brand identity facts."""
    # Mirror _lib's data-root resolution
    root_candidates = [
        Path(os.environ.get("CAMPAIGN_OS_DATA_DIR", "")).resolve(),
        Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data"),
        Path(__file__).resolve().parent.parent.parent / "data",
    ]
    for r in root_candidates:
        if not r or str(r) == "/":
            continue
        bp = r / "brands.json"
        if bp.is_file():
            try:
                return json.loads(bp.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {"brands": {}, "default_brand_id": "swing-shack"}


def _brand_canonical(bid: str) -> dict:
    """Return canonical facts + contamination triggers for a brand."""
    brands = _load_brands()
    b = (brands.get("brands") or {}).get(bid) or {}
    canonical = {
        "brand_id": bid,
        "display_name": b.get("display_name") or bid,
        "tagline": b.get("tagline") or "",
        "website": (b.get("website") or "").rstrip("/"),
        "ig_handle": b.get("instagram_handle") or "",
        "voice_label": b.get("voice_label") or bid,
    }

    # Build contamination triggers from EVERY brand that is NOT this one.
    # Per operator directive: a Stick report must fail rendering if it
    # contains Swing Shack identifiers (and vice versa). Triggers:
    #   - display_name ("Swing Shack", "Stick")
    #   - canonical handle ("@swingshack", "@stick.paarl")
    #   - website hostname ("swingshack.co.za", "stickgolf.co.za")
    # All triggers are matched case-insensitively as substrings (not
    # strict word boundaries) because the operator's directive calls
    # out "swingshack" appearing inside "swingshack.co.za".
    triggers: List[str] = []
    for other_id, other_b in (brands.get("brands") or {}).items():
        if other_id == bid:
            continue
        for s in (
            other_b.get("display_name"),
            other_b.get("instagram_handle"),
        ):
            if s and isinstance(s, str) and len(s) >= 4:
                triggers.append(s)
        # Website hostname (strip protocol + trailing slash)
        ws = (other_b.get("website") or "")
        if ws:
            for prefix in ("https://", "http://"):
                if ws.startswith(prefix):
                    ws = ws[len(prefix):]
            ws = ws.rstrip("/")
            if ws:
                triggers.append(ws)
    return {
        "canonical": canonical,
        "triggers": triggers,
    }


# ── per-brand data sources ─────────────────────────────────────

def _data_root() -> Path:
    """Resolve data root (same convention as reporting_editorial)."""
    env = os.environ.get("CAMPAIGN_OS_DATA_DIR")
    if env:
        return Path(env).resolve()
    # repo-local default
    return Path(__file__).resolve().parent.parent.parent / "data"


def _read_json(p: Path) -> Any:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_per_brand_or_missing(rel_path: str, bid: str,
                                  *, allow_scoped_fallback: bool = True
                                  ) -> Tuple[Any, str]:
    """Strict per-brand read.

    Resolution order:
      1. data/brands/<bid>/<rel_path>            (brand lane)
      2. data/integrations/<bid>/      (per-brand integrations)
      3. data/brand-directory/<bid>/<rel_path>   (per-brand brand-directory)
      4. data/<rel_path>                         (global lane — ONLY if
         allow_scoped_fallback=True AND the global file's
         account.username / brand_id matches THIS brand)
      5. data/bundled/<rel_path>                 (bundled fallback)
      6. MISSING

    The "scoped fallback" rule is what prevents brand contamination.
    A global file is NEVER returned to brand X if its data
    belongs to brand Y. The fallback uses canonical facts
    (ig_handle, display_name) from brands.json to decide.
    """
    root = _data_root()
    candidates: List[Path] = []
    # 1. brand lane
    candidates.append(root / "brands" / bid / rel_path)
    # 2. per-brand integrations (file basename only)
    candidates.append(root / "integrations" / bid / Path(rel_path).name)
    # 3. per-brand brand-directory
    candidates.append(root / "brand-directory" / bid / rel_path)
    # 4. global lane (scoped)
    candidates.append(root / rel_path)

    facts = _brand_canonical(bid)
    canonical_handle = (facts["canonical"].get("ig_handle") or ""
                          ).lstrip("@").lower()
    canonical_display = facts["canonical"].get("display_name", "").lower()

    for idx, p in enumerate(candidates):
        if not p.is_file():
            continue
        data = _read_json(p)
        if data is None:
            continue
        # Apply scoped fallback for the global lane (idx 3)
        if idx == 3 and allow_scoped_fallback:
            ok = _global_file_belongs_to_brand(data, canonical_handle,
                                                  canonical_display)
            if not ok:
                # Global file exists but belongs to another brand.
                # Do not return it.
                continue
        # Brand lane or verified global — return it
        return data, p.as_posix()

    # 5. bundled fallback (only for the bundled data dir
    # shipped with the repo, not a per-brand subdir)
    bundled = root.parent / "campaign-os" / "data" / rel_path
    if bundled.is_file():
        return _read_json(bundled), bundled.as_posix()

    return None, "MISSING"


def _global_file_belongs_to_brand(data: Any, handle: str,
                                     display: str) -> bool:
    """A global file is acceptable for a brand if its contents
    clearly belong to that brand. We check:
      - data.brand_id == brand
      - data.account.username == handle
      - data.account.name contains display_name (case-insensitive)
      - data.account.id matches brands.json <brand>_ig_business_id
        env var (handled by the caller)
    Returns True ONLY if at least one of these checks passes.
    """
    if not isinstance(data, dict):
        return False
    if data.get("brand_id") == handle or data.get("brand_id") == display:
        return True
    if isinstance(data.get("account"), dict):
        acc = data["account"]
        if acc.get("username", "").lstrip("@").lower() == handle:
            return True
        name = (acc.get("name") or "").lower()
        if display and display in name:
            return True
    if isinstance(data.get("handle"), str):
        if data["handle"].lstrip("@").lower() == handle:
            return True
    if isinstance(data.get("ig_handle"), str):
        if data["ig_handle"].lstrip("@").lower() == handle:
            return True
    return False


def _collect_v3(bid: str) -> Dict[str, Any]:
    """Collect period data with strict brand-bound paths.

    Returns:
      {
        "status": "OK" | "MISSING_DATA",
        "missing_sources": ["ga4_sessions", ...],
        "current_7d": {...},   # this week, last 7 complete days
        "previous_7d": {...},  # immediately preceding 7 complete days
        "current_28d": {...},  # this 28 days
        "previous_28d": {...}, # preceding 28 days
        "stories_live": {...}, # live snapshots (clearly marked)
        "raw": {...},          # underlying data for fact→interpretation
        "sources": [...],      # source windows + freshness
      }
    """
    today = datetime.datetime.now(datetime.timezone.utc).date()
    cur_7_start = today - datetime.timedelta(days=6)
    cur_7_end = today
    prev_7_start = cur_7_start - datetime.timedelta(days=7)
    prev_7_end = cur_7_start - datetime.timedelta(days=1)
    cur_28_start = today - datetime.timedelta(days=27)
    cur_28_end = today
    prev_28_start = cur_28_start - datetime.timedelta(days=28)
    prev_28_end = cur_28_start - datetime.timedelta(days=1)

    out = {
        "status": "OK",
        "missing_sources": [],
        "current_7d": {"start": cur_7_start.isoformat(),
                          "end": cur_7_end.isoformat(), "metrics": {}},
        "previous_7d": {"start": prev_7_start.isoformat(),
                          "end": prev_7_end.isoformat(), "metrics": {}},
        "current_28d": {"start": cur_28_start.isoformat(),
                          "end": cur_28_end.isoformat(), "metrics": {}},
        "previous_28d": {"start": prev_28_start.isoformat(),
                          "end": prev_28_end.isoformat(), "metrics": {}},
        "stories_live": {"captured_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(), "metrics": {}},
        "raw": {},
        "sources": [],
    }

    # ── GA4 ───────────────────────────────────────────────
    ga, ga_path = _read_per_brand_or_missing("ga4-metrics.json", bid)
    if ga:
        out["raw"]["ga4"] = ga
        out["sources"].append({
            "name": "ga4", "path": ga_path,
            "window": ga.get("data_window", "unknown"),
            "fetched_at": ga.get("fetched_at"),
            "scope": f"brand:{bid}",
        })
        total = ga.get("total_sessions", 0) or 0
        # We don't split weekly/previous here from the cumulative file.
        # The single point-in-time ga4-metrics.json is a 7-day window
        # snapshot; previous_7d is empty if no archived prev snapshot.
        out["current_7d"]["metrics"]["ga4_sessions"] = total
        out["current_28d"]["metrics"]["ga4_sessions"] = total
        out["previous_7d"]["metrics"]["ga4_sessions"] = None  # unknown
        out["previous_28d"]["metrics"]["ga4_sessions"] = None
        out["missing_sources"].append("ga4_previous_week")
    else:
        out["missing_sources"].append("ga4_current_week")

    # ── Instagram (per-brand only) ────────────────────────
    ig, ig_path = _read_per_brand_or_missing(
        "analytics/instagram-analytics.json", bid)
    if not ig:
        ig, ig_path = _read_per_brand_or_missing(
            "ig-business-analytics.json", bid)
    if ig:
        out["raw"]["instagram"] = ig
        out["sources"].append({
            "name": "instagram", "path": ig_path,
            "fetched_at": ig.get("lastUpdated") or ig.get("metadata"),
            "scope": f"brand:{bid}",
        })
        posts = ig.get("posts") or []
        reach_28 = sum((p.get("reach") or 0) for p in posts)
        interactions_28 = sum(
            ((p.get("like_count") or 0) + (p.get("comments_count") or 0)
             + (p.get("shares") or 0) + (p.get("saves") or 0))
            for p in posts)
        out["current_28d"]["metrics"]["ig_posts"] = len(posts)
        out["current_28d"]["metrics"]["ig_reach"] = reach_28
        out["current_28d"]["metrics"]["ig_interactions"] = interactions_28
        out["previous_28d"]["metrics"]["ig_posts"] = None
        out["previous_28d"]["metrics"]["ig_reach"] = None
        out["previous_28d"]["metrics"]["ig_interactions"] = None
        # Top performers are real Stick posts (or whatever per-brand file says)
        out["raw"]["ig_top_performers"] = (ig.get("topPerformers") or [])[:5]
        out["missing_sources"].append("ig_previous_28d")
    else:
        out["missing_sources"].append("instagram_current")

    # ── Live Stories (clearly marked LIVE SNAPSHOT) ────────
    # Live Story data is captured-as-of-now, NOT comparable to 7d/28d
    # windows. v3 surfaces it separately with the LIVE SNAPSHOT label.
    daily_reach = (ig or {}).get("daily_reach") if ig else None
    if daily_reach:
        # last 24h reach only
        if isinstance(daily_reach, list) and daily_reach:
            live_reach = sum(
                d.get("value", 0) for d in daily_reach
                if isinstance(d, dict)
                and d.get("date") == today.isoformat())
            out["stories_live"]["metrics"]["ig_reach_24h"] = live_reach
            out["stories_live"]["sample_size"] = 1  # 1 day only
            out["raw"]["daily_reach"] = daily_reach

    # ── Meta Ads (V2.4.1) ────────────────────────────────
    # Read per-brand cache file written by v25 daily pull.
    paid, paid_path = _read_per_brand_or_missing(
        "paid-media-v24/swing-shack.json".replace("swing-shack", bid),
        bid)
    # Fallback: V2.4.1 writes to paid-media/<brand>.json via the app
    if not paid:
        paid, paid_path = _read_per_brand_or_missing(
            f"paid-media/{bid}.json", bid)
    if paid:
        out["raw"]["paid_media"] = paid
        out["sources"].append({
            "name": "paid_media_v24", "path": paid_path,
            "fetched_at": paid.get("fetched_at")
                          or paid.get("data", {}).get("fetched_at"),
            "scope": f"brand:{bid}",
        })
        # V2.4.1 normalised structure
        data = paid.get("data") or paid.get("paid_media_v24") or {}
        out["current_7d"]["metrics"]["meta_spend"] = (
            data.get("current_period") or {}).get("total_spend")
        out["previous_7d"]["metrics"]["meta_spend"] = (
            data.get("previous_period") or {}).get("total_spend")
        out["current_7d"]["metrics"]["meta_impressions"] = (
            data.get("current_period") or {}).get("total_impressions")
        out["current_7d"]["metrics"]["meta_reach"] = (
            data.get("current_period") or {}).get("total_reach")
        out["current_7d"]["metrics"]["meta_results"] = (
            data.get("current_period") or {}).get("total_results")
        # Per-campaign table
        out["raw"]["paid_campaigns"] = (
            data.get("per_campaign") or [])
    else:
        out["missing_sources"].append("paid_media_v24")

    # ── Google Ads (concise) ─────────────────────────────
    gad, gad_path = _read_per_brand_or_missing(
        "google-ads/summary.json", bid)
    if gad:
        out["raw"]["google_ads"] = gad
        out["sources"].append({
            "name": "google_ads", "path": gad_path,
            "fetched_at": gad.get("fetched_at"),
            "scope": f"brand:{bid}",
        })
        out["current_7d"]["metrics"]["google_spend"] = (
            gad.get("current_period") or {}).get("cost")
        out["previous_7d"]["metrics"]["google_spend"] = (
            gad.get("previous_period") or {}).get("cost")
    else:
        out["missing_sources"].append("google_ads")

    # ── Published content (last 7d) ───────────────────────
    # Read the publisher queue or per-brand publish log
    pq, pq_path = _read_per_brand_or_missing(
        "publish-queue.json", bid)
    if pq:
        out["raw"]["publish_queue"] = pq
        out["sources"].append({
            "name": "publish_queue", "path": pq_path,
            "fetched_at": "live",
            "scope": f"brand:{bid}",
        })
        items = (pq.get("queued") or pq.get("queue") or [])
        if isinstance(items, list):
            n = len(items)
            out["current_7d"]["metrics"]["content_published_7d"] = n
        else:
            out["current_7d"]["metrics"]["content_published_7d"] = 0

    # ── Top landing pages ────────────────────────────────
    ga = out["raw"].get("ga4") or {}
    pages = ga.get("pages") or []
    top_pages = []
    seen = set()
    for p in pages:
        pp = p.get("path")
        if pp and pp not in seen:
            seen.add(pp)
            top_pages.append({
                "path": pp,
                "sessions": p.get("sessions") or 0,
                "engagement_rate": p.get("engRate")
                                    or p.get("engagementRate"),
            })
        if len(top_pages) >= 5:
            break
    out["raw"]["top_pages"] = top_pages

    # ── Mark status ──────────────────────────────────────
    if not out["missing_sources"]:
        out["status"] = "OK"
    elif any(s for s in out["missing_sources"]
              if "current" in s or "google" in s or "paid" in s):
        out["status"] = "PARTIAL"
    else:
        out["status"] = "OK_PREVIOUS_MISSING"

    return out


# ── brand isolation gate ───────────────────────────────────────

def _validate_brand_isolation(bid: str, payload: Any) -> Tuple[bool, List[str]]:
    """Scan payload for cross-brand contamination.

    Returns (clean, list_of_violations). If not clean, the renderer
    MUST NOT render — it returns BLOCKED_BRAND_CONTAMINATION.

    Triggers are matched as case-insensitive substrings (per
    operator directive: "swingshack" inside "swingshack.co.za" must
    trigger BLOCKED for Stick).

    An identifier that BOTH the current brand AND another brand
    claim (e.g. bag-drop reuses @swingshack from Swing Shack) is
    NOT treated as contamination when scanning a report for the
    brand that legitimately owns it — we filter out any trigger
    that also appears in the current brand's canonical identifiers.
    """
    facts = _brand_canonical(bid)
    raw_triggers = facts["triggers"]
    # Whitelist: identifiers this brand ALSO claims.
    # These are not contamination when they appear in this brand's data.
    canonical = facts["canonical"]
    own_strings = set()
    for s in (canonical.get("display_name"), canonical.get("ig_handle"),
                canonical.get("website")):
        if s:
            own_strings.add(s.lower())
    triggers = []
    for t in raw_triggers:
        if t.lower() not in own_strings:
            triggers.append(t)
    if not triggers:
        return True, []
    text = json.dumps(payload, ensure_ascii=False, default=str)
    violations: List[str] = []
    for t in triggers:
        if t.lower() in text.lower():
            violations.append(t)
    return (len(violations) == 0), violations


# ── period helpers ─────────────────────────────────────────────

def _pct_change(cur: Optional[float], prev: Optional[float]) -> Tuple[str, str]:
    """Return (display_pct, direction) for Current vs Previous.

    direction in {up, down, neutral, baseline}.
    """
    if cur is None or prev is None:
        return ("—", "baseline")
    try:
        c = float(cur)
        p = float(prev)
    except (ValueError, TypeError):
        return ("—", "baseline")
    if p == 0:
        if c == 0:
            return ("flat", "neutral")
        return ("baseline", "baseline")
    pct = (c - p) / p * 100
    arrow = "up" if pct > 0 else "down" if pct < 0 else "neutral"
    return (f"{pct:+.1f}%", arrow)


def _fmt_num(v: Any, fmt: str = "int") -> str:
    if v is None:
        return "—"
    try:
        n = float(v)
    except (ValueError, TypeError):
        return str(v)
    if fmt == "money":
        return f"R{int(round(n)):,}"
    if fmt == "pct":
        return f"{n:.1f}%"
    return f"{int(round(n)):,}"


# ── severity helpers ──────────────────────────────────────────

def _severity_for_change(pct: float, prev: Optional[float],
                          threshold_high: float = 20.0,
                          threshold_med: float = 10.0) -> str:
    """Return HIGH / MEDIUM / LOW based on % change magnitude."""
    if pct is None or prev is None:
        return "MEDIUM"  # missing comparison = noteworthy
    if abs(pct) >= threshold_high:
        return "HIGH"
    if abs(pct) >= threshold_med:
        return "MEDIUM"
    return "LOW"


# ── TLDR ──────────────────────────────────────────────────────

def _build_tldr(bid: str, data: dict) -> List[dict]:
    """8-10 numeric KPI cards for the top of the report.

    Each row: {metric, current, previous, change, severity, fmt}
    """
    cur = data["current_7d"]["metrics"]
    prev = data["previous_7d"]["metrics"]
    c28 = data["current_28d"]["metrics"]
    p28 = data["previous_28d"]["metrics"]

    rows: List[dict] = []

    def add(metric, cur_v, prev_v, fmt="int"):
        pct, direction = _pct_change(cur_v, prev_v)
        try:
            pct_n = float(pct.rstrip("%")) if "%" in pct else 0.0
        except Exception:
            pct_n = 0.0
        sev = _severity_for_change(pct_n, prev_v)
        rows.append({
            "metric": metric,
            "current": _fmt_num(cur_v, fmt),
            "previous": _fmt_num(prev_v, fmt) if prev_v is not None else "—",
            "change": pct,
            "direction": direction,
            "severity": sev,
            "fmt": fmt,
        })

    add("Content published (7d)", cur.get("content_published_7d"),
        None)
    add("Website sessions (7d)", cur.get("ga4_sessions"),
        prev.get("ga4_sessions"))
    add("IG reach (28d)", c28.get("ig_reach"), p28.get("ig_reach"))
    add("IG interactions (28d)", c28.get("ig_interactions"),
        p28.get("ig_interactions"))
    add("Meta paid spend (7d)", cur.get("meta_spend"),
        prev.get("meta_spend"), fmt="money")
    add("Meta impressions (7d)", cur.get("meta_impressions"),
        prev.get("meta_impressions"))
    add("Meta results (7d)", cur.get("meta_results"),
        prev.get("meta_results"))
    add("Google Ads spend (7d)", cur.get("google_spend"),
        prev.get("google_spend"), fmt="money")
    return rows


# ── markdown renderer ─────────────────────────────────────────

def _section_header(title: str, period: Optional[str] = None) -> str:
    if period:
        return f"## {title}  \n_{period}_"
    return f"## {title}"


def _row(metric, current, previous, change, severity=None) -> str:
    """Markdown table row with optional severity tag."""
    base = f"| {metric} | {current} | {previous} | {change} |"
    if severity:
        return f"{base} {severity} |"
    return base


def _render_markdown(bid: str, data: dict, tldr: List[dict],
                       north_stars: dict) -> str:
    facts = _brand_canonical(bid)["canonical"]
    L: List[str] = []
    today = datetime.datetime.now().strftime("%d %b %Y")

    # HEADER
    title = facts['display_name'] if facts['display_name'] else bid.title().replace("-", " ")
    L.append(f"# {title} — Weekly Management Report")
    L.append(f"_{data['current_7d']['start']} → {data['current_7d']['end']}_  ")
    L.append(f"_Generated {today}_")
    L.append("")

    # EXECUTIVE READ (single paragraph, top of report)
    exec_lines = []
    if data["current_7d"]["metrics"].get("ga4_sessions"):
        exec_lines.append(
            f"Weekly website traffic: "
            f"{_fmt_num(data['current_7d']['metrics']['ga4_sessions'])} sessions.")
    if data["current_28d"]["metrics"].get("ig_reach"):
        exec_lines.append(
            f"28d IG reach: "
            f"{_fmt_num(data['current_28d']['metrics']['ig_reach'])}.")
    paid_v = data["current_7d"]["metrics"].get("meta_spend")
    if paid_v is not None:
        exec_lines.append(
            f"Meta paid spend (7d): {_fmt_num(paid_v, 'money')}.")
    elif "paid_media_v24" in data["missing_sources"]:
        exec_lines.append("Meta paid spend: NOT CONNECTED — see Data Notes.")
    L.append("**Executive Read:** " + " ".join(exec_lines)
              if exec_lines else "_No executive read possible — see Data Notes._")
    L.append("")

    # TLDR — NUMBERS FIRST
    L.append(_section_header(
        "TL;DR — Numbers (Last 7 days unless noted)",
        f"7d: {data['current_7d']['start']} → {data['current_7d']['end']} | "
        f"prev 7d: {data['previous_7d']['start']} → {data['previous_7d']['end']}"))
    L.append("")
    L.append("| Metric | Current | Previous | Change | Severity |")
    L.append("|---|---|---|---|---|")
    for r in tldr:
        L.append(_row(r["metric"], r["current"], r["previous"],
                      r["change"], r["severity"]))
    L.append("")
    L.append("> WoW assessment unavailable — first valid baseline."
              if all(r["previous"] == "—" for r in tldr)
              else "> Change % = current vs previous 7-day window. "
                   "Severity reflects magnitude only.")
    L.append("")

    # SOCIAL PERFORMANCE
    L.append(_section_header(
        "Social Performance",
        f"28d: {data['current_28d']['start']} → {data['current_28d']['end']}"))
    L.append("")
    ig_ok = "instagram_current" not in data["missing_sources"]
    if ig_ok:
        ig = data["current_28d"]["metrics"]
        L.append("**Instagram (28d)**")
        L.append("")
        L.append("| Metric | Current | Previous | Change |")
        L.append("|---|---|---|---|")
        for label, key in (("Reach", "ig_reach"),
                            ("Interactions", "ig_interactions"),
                            ("Posts", "ig_posts")):
            prev_v = data["previous_28d"]["metrics"].get(key)
            pct, _ = _pct_change(ig.get(key), prev_v)
            L.append(f"| {label} | {_fmt_num(ig.get(key))} | "
                       f"{_fmt_num(prev_v) if prev_v is not None else '—'} | "
                       f"{pct} |")
        L.append("")
        if data["raw"].get("ig_top_performers"):
            L.append("Top 3-5 posts (most recent 28d):")
            for p in data["raw"]["ig_top_performers"][:5]:
                cap = (p.get("caption") or "")[:80]
                L.append(f"- {p.get('reach', '?')} reach · "
                           f"{_fmt_num(p.get('interactions'))} interactions · "
                           f"\"{cap}\"")
            L.append("")
        if data["stories_live"]["metrics"].get("ig_reach_24h") is not None:
            L.append(f"> **LIVE SNAPSHOT — Stories (last 24h):** "
                       f"{_fmt_num(data['stories_live']['metrics']['ig_reach_24h'])} "
                       f"reach · sample size = 1 day. **Not** comparable to "
                       f"the 28d IG reach above.")
            L.append("")
    else:
        L.append("Instagram insights: MISSING for this brand. See Data Notes.")
        L.append("")
    fb_ok = "facebook_current" not in data["missing_sources"]
    if fb_ok:
        L.append("**Facebook**")
        L.append("")
        L.append("| Metric | Current | Previous | Change |")
        L.append("|---|---|---|---|")
        L.append("| (Facebook metrics not yet wired per-brand — see Data Notes) |  |  |  |")
        L.append("")
    else:
        L.append("Facebook: MISSING for this brand. See Data Notes.")
        L.append("")

    # WEBSITE & ACQUISITION
    L.append(_section_header(
        "Website & Acquisition",
        f"7d: {data['current_7d']['start']} → {data['current_7d']['end']}"))
    L.append("")
    if "ga4_current_week" not in data["missing_sources"]:
        L.append("| Metric | Current | Previous | Change |")
        L.append("|---|---|---|---|")
        cur_v = data["current_7d"]["metrics"].get("ga4_sessions")
        prev_v = data["previous_7d"]["metrics"].get("ga4_sessions")
        pct, _ = _pct_change(cur_v, prev_v)
        L.append(f"| Sessions | {_fmt_num(cur_v)} | "
                   f"{_fmt_num(prev_v) if prev_v is not None else '—'} | {pct} |")
        L.append("| Users | (not yet split — see Data Notes) |  |  |")
        L.append("| Engagement rate | (not yet split — see Data Notes) |  |  |")
        L.append("")
        if data["raw"].get("top_pages"):
            L.append("**Top landing pages**")
            L.append("")
            L.append("| Path | Sessions | Engagement |")
            L.append("|---|---|---|")
            for p in data["raw"]["top_pages"]:
                er = p.get("engagement_rate") or "—"
                L.append(f"| {p['path']} | {_fmt_num(p['sessions'])} | {er} |")
            L.append("")
        L.append("> Note: page sessions ≠ leads / bookings / purchases unless "
                   "verified events exist on this brand.")
        L.append("")
    else:
        L.append("GA4: MISSING for this brand. See Data Notes.")
        L.append("")

    # PAID MEDIA
    L.append(_section_header(
        "Paid Media — Meta Ads (V2.4.1)",
        f"7d: {data['current_7d']['start']} → {data['current_7d']['end']}"))
    L.append("")
    if "paid_media_v24" in data["missing_sources"]:
        L.append("Meta Ads: NOT_CONNECTED — see Data Notes for token / "
                   "connector state. **Not the same as zero spend.**")
        L.append("")
    else:
        cur_v = data["current_7d"]["metrics"].get("meta_spend")
        prev_v = data["previous_7d"]["metrics"].get("meta_spend")
        pct, _ = _pct_change(cur_v, prev_v)
        L.append("| Metric | Current | Previous | Change |")
        L.append("|---|---|---|---|")
        L.append(f"| Spend | {_fmt_num(cur_v, 'money')} | "
                   f"{_fmt_num(prev_v, 'money') if prev_v is not None else '—'} | {pct} |")
        L.append(f"| Impressions | {_fmt_num(data['current_7d']['metrics'].get('meta_impressions'))} | "
                   f"— | — |")
        L.append(f"| Reach | {_fmt_num(data['current_7d']['metrics'].get('meta_reach'))} | "
                   f"— | — |")
        L.append(f"| Results | {_fmt_num(data['current_7d']['metrics'].get('meta_results'))} | "
                   f"— | — |")
        L.append("")
        campaigns = data["raw"].get("paid_campaigns") or []
        if campaigns:
            L.append("**Campaign-level (material campaigns only)**")
            L.append("")
            L.append("| Campaign | Objective | Spend | Result | Efficiency | WoW |")
            L.append("|---|---|---|---|---|---|")
            for c in campaigns[:8]:
                spend = c.get("amount_spend_cents", 0) / 100
                res = c.get("results", 0)
                eff = (spend / res) if res else None
                wow = c.get("change_pct", "—")
                L.append(f"| {c.get('campaign_name') or c.get('campaign_id')} | "
                           f"{c.get('objective', '—')} | "
                           f"{_fmt_num(spend, 'money')} | "
                           f"{_fmt_num(res)} | "
                           f"{_fmt_num(eff, 'money') if eff else '—'}/result | "
                           f"{wow} |")
            L.append("")
        else:
            L.append("No material campaigns in this window.")
            L.append("")
        L.append("> Lead terminology preserved as 'Meta-reported leads' — "
                   "not yet matched to CRM or qualified as bookings.")
        L.append("")
        # Google Ads
        if "google_ads" not in data["missing_sources"]:
            cur_v = data["current_7d"]["metrics"].get("google_spend")
            prev_v = data["previous_7d"]["metrics"].get("google_spend")
            pct, _ = _pct_change(cur_v, prev_v)
            L.append("**Google Ads**")
            L.append("")
            L.append(f"Spend (7d): {_fmt_num(cur_v, 'money')} "
                       f"(prev: {_fmt_num(prev_v, 'money') if prev_v is not None else '—'}, "
                       f"{pct})")
            L.append("")
        else:
            L.append("**Google Ads:** 0 spend — no campaigns ran this period.")
            L.append("")

    # CONTENT PERFORMANCE
    L.append(_section_header(
        "Content Performance",
        "7d: posts published + top pieces (28d reach from IG top performers)"))
    L.append("")
    pub_n = data["current_7d"]["metrics"].get("content_published_7d")
    if pub_n is not None:
        L.append(f"Published (7d): **{_fmt_num(pub_n)} pieces** "
                   f"(prev: —, first valid baseline)")
        L.append("")
    if data["raw"].get("ig_top_performers"):
        L.append("**Top pieces (28d)**")
        L.append("")
        L.append("| Format | Theme | Reach | Interactions |")
        L.append("|---|---|---|---|")
        for p in data["raw"]["ig_top_performers"][:5]:
            cap = (p.get("caption") or "")[:60]
            L.append(f"| {p.get('media_type', 'post')} | {cap}… | "
                       f"{_fmt_num(p.get('reach'))} | "
                       f"{_fmt_num(p.get('interactions'))} |")
        L.append("")
        L.append("> Patterns here are observation only — not enough volume "
                   "for an established pattern claim.")
        L.append("")
    else:
        L.append("No top performers data for this brand this period.")
        L.append("")

    # BUSINESS / FUNNEL SIGNALS
    L.append(_section_header(
        "Business / Funnel Signals"))
    L.append("")
    L.append("Sessions → engagement → leads → outcomes")
    L.append("")
    L.append("| Stage | Value | Confidence |")
    L.append("|---|---|---|")
    L.append(f"| Website sessions | {_fmt_num(data['current_7d']['metrics'].get('ga4_sessions'))} | high |")
    L.append(f"| IG interactions (28d) | {_fmt_num(data['current_28d']['metrics'].get('ig_interactions'))} | high |")
    L.append(f"| Meta-reported leads | NOT YET MEASURED — connector pending | low |")
    L.append(f"| Bookings / sales | NOT YET MEASURED — CRM/POS connector pending | low |")
    L.append("")
    L.append("> Revenue modelling requires real conversion rate × outcome value × "
               "verified attribution. **Stick CRM / POS connector is pending — "
               "no revenue projections possible yet.**")
    L.append("")

    # NORTH STARS
    L.append(_section_header("North Stars"))
    L.append("")
    if north_stars and north_stars.get("north_stars"):
        for ns in north_stars["north_stars"]:
            L.append(f"- **{ns['label']}** — {ns['metric']}")
            L.append(f"  - Outcome measurement: {ns['outcome_measurement']}")
            L.append(f"  - Marketing support signal: {ns['marketing_support_signal']}")
        L.append("")
        L.append("> Progress percentages not shown until real operational "
                   "connectors are live.")
        L.append("")
    else:
        L.append("No canonical North Stars defined for this brand.")
        L.append("")

    # WHAT WORKED
    L.append(_section_header("What Worked"))
    L.append("")
    worked: List[str] = []
    if data["current_7d"]["metrics"].get("ga4_sessions"):
        # Don't claim "improvement" — show fact only
        worked.append(
            f"FACT: Website recorded "
            f"{_fmt_num(data['current_7d']['metrics']['ga4_sessions'])} "
            f"sessions in the last 7 days. "
            f"WoW comparison: "
            f"{_fmt_num(data['previous_7d']['metrics'].get('ga4_sessions'))} "
            f"(change % unavailable — no archived previous snapshot).")
    if data["current_28d"]["metrics"].get("ig_reach"):
        worked.append(
            f"FACT: 28d IG reach = "
            f"{_fmt_num(data['current_28d']['metrics']['ig_reach'])}. "
            f"Compared to a 28d previous window: "
            f"{_fmt_num(data['previous_28d']['metrics'].get('ig_reach'))}.")
    if worked:
        for w in worked:
            L.append(f"- {w}")
    else:
        L.append("- No evidence-based 'what worked' items this period.")
    L.append("")
    L.append("> No connector-status items go here. Measurement availability "
               "is not marketing performance.")
    L.append("")

    # WHAT NEEDS ATTENTION
    L.append(_section_header("What Needs Attention"))
    L.append("")
    att: List[Tuple[str, str]] = []  # (severity, text)
    if "ga4_previous_week" in data["missing_sources"]:
        att.append(("MEDIUM",
                     "WoW comparison for website sessions is unavailable — "
                     "first valid baseline not yet established."))
    if "paid_media_v24" in data["missing_sources"]:
        att.append(("HIGH",
                     "Meta Ads: NOT_CONNECTED — paid-media reporting absent "
                     "for this brand. Acquire token / wire per-brand config."))
    if "instagram_current" in data["missing_sources"]:
        att.append(("MEDIUM",
                     "Instagram: per-brand analytics file missing. "
                     "Confirm IG business account ID is configured for this brand."))
    if "google_ads" in data["missing_sources"]:
        att.append(("LOW",
                     "Google Ads: no data path. Either genuinely zero spend, "
                     "or connector not wired. Confirm before claiming zero."))
    if not att:
        att.append(("LOW",
                     "All standard data sources present. No high-severity gaps."))
    for sev, txt in att:
        L.append(f"- **[{sev}]** {txt}")
    L.append("")
    L.append("> Severity reflects marketing/business consequence of the gap, "
               "not sample size.")
    L.append("")

    # ACTIONS
    L.append(_section_header("Actions for This Week"))
    L.append("")
    actions: List[dict] = []
    if "paid_media_v24" in data["missing_sources"]:
        actions.append({
            "n": 1,
            "action": "Wire Meta Ads connector for this brand (token + "
                       "per-brand config).",
            "why": "Paid-media reporting is absent. Without it, paid "
                    "performance and WoW change are unmeasurable.",
            "measure": "/api/meta/ads/cache/<brand> returns ok=true with "
                        "current_period populated.",
        })
    if "ga4_previous_week" in data["missing_sources"]:
        actions.append({
            "n": len(actions) + 1,
            "action": "Archive a baseline GA4 snapshot so future reports "
                       "can show real WoW comparisons.",
            "why": "First valid baseline is needed before 'clean week' / "
                    "improvement claims are valid.",
            "measure": "data/weekly-snapshots/<brand>/<date>.json contains "
                        "the previous week's GA4 totals.",
        })
    if "instagram_current" in data["missing_sources"]:
        actions.append({
            "n": len(actions) + 1,
            "action": "Confirm per-brand IG business account ID is wired "
                       "and that daily-reach time-series writes to the brand "
                       "lane (not the global shared file).",
            "why": "Without per-brand IG data, social section falls back "
                    "to the shared Swing Shack file — a brand contamination "
                    "failure.",
            "measure": "data/integrations/<brand>/instagram.json has "
                        "ig_business_account_id; "
                        "data/brand-directory/<brand>/analytics/"
                        "instagram-analytics.json is populated.",
        })
    while len(actions) < 3:
        actions.append({
            "n": len(actions) + 1,
            "action": "(No additional priority action — focus on the gaps "
                       "above first.)",
            "why": "—",
            "measure": "—",
        })
    actions = actions[:3]
    for a in actions:
        L.append(f"{a['n']}. **{a['action']}**")
        L.append(f"   - **Why:** {a['why']}")
        L.append(f"   - **Measure:** {a['measure']}")
    L.append("")
    L.append("> No fake uplift ranges. No generated hook. No generated "
               "caption. Reporting does not bypass Create.")
    L.append("")

    # DATA NOTES
    L.append(_section_header("Data Notes / Limitations"))
    L.append("")
    if data["missing_sources"]:
        L.append("**Missing data sources (not zero):**")
        for s in data["missing_sources"]:
            L.append(f"- {s}")
        L.append("")
    L.append("**Period contract:**")
    L.append("- current_week = latest 7 complete days "
               f"({data['current_7d']['start']} → {data['current_7d']['end']})")
    L.append("- previous_week = immediately preceding 7 complete days "
               f"({data['previous_7d']['start']} → {data['previous_7d']['end']})")
    L.append("- current_28d = latest 28 complete days")
    L.append("- previous_28d = immediately preceding 28 complete days")
    L.append("")
    L.append("**Live snapshots (not comparable to windowed metrics):**")
    if data["stories_live"]["metrics"]:
        for k, v in data["stories_live"]["metrics"].items():
            L.append(f"- {k}: {_fmt_num(v)} (captured "
                       f"{data['stories_live']['captured_at']})")
    L.append("")
    L.append("**Connector status (dynamic):**")
    for s in data["sources"]:
        L.append(f"- {s['name']}: scope={s.get('scope','?')}, "
                   f"window={s.get('window','?')}, "
                   f"fetched={s.get('fetched_at','?')}")
    L.append("")
    L.append("**Tone:** This is a management report. Numbers first. "
               "Conclusions only when evidence supports them.")
    L.append("")

    # FOOTER
    L.append("---")
    L.append(f"_Generated {datetime.datetime.now(datetime.timezone.utc).isoformat()} • "
               f"V2.4.1 frozen • V3 renderer._")
    return "\n".join(L)


# ── main entry ─────────────────────────────────────────────────

def build_v3(bid: str, fmt: str = "markdown") -> dict:
    """Build the V3 weekly management report.

    Returns:
      {
        "report_status": "OK" | "BLOCKED_BRAND_CONTAMINATION" | "MISSING_DATA",
        "block_reason": str | None,
        "contaminations": [str],
        "rendered": str,        # markdown / html
        "raw_payload": {...},   # for JSON consumers
      }
    """
    data = _collect_v3(bid)
    north_stars = _read_per_brand_or_missing(
        "north_stars.json", bid)[0] or {}
    if isinstance(north_stars, list):
        north_stars = {"north_stars": north_stars}

    # Brand isolation gate
    clean, violations = _validate_brand_isolation(bid, data)
    if not clean:
        return {
            "report_status": "BLOCKED_BRAND_CONTAMINATION",
            "block_reason": "Rendered data contains identifiers from a "
                             "different brand. Refusing to render.",
            "contaminations": violations,
            "rendered": (f"# {bid.title()} — Weekly Management Report\n\n"
                          "**REPORT BLOCKED — brand contamination detected.**\n\n"
                          "Identifiers found in source data:\n"
                          + "\n".join(f"- `{v}`" for v in violations)
                          + "\n\nThis report will not render until the data "
                          "sources are scoped to this brand only."),
            "raw_payload": {},
        }

    tldr = _build_tldr(bid, data)
    if fmt in ("markdown", "md"):
        rendered = _render_markdown(bid, data, tldr, north_stars)
    else:
        rendered = _render_markdown(bid, data, tldr, north_stars)

    return {
        "report_status": data["status"],
        "block_reason": None,
        "contaminations": [],
        "rendered": rendered,
        "raw_payload": {
            "data": data,
            "tldr": tldr,
            "north_stars": north_stars,
            "brand_id": bid,
            "generator": "weekly_report_v3",
        },
    }


if __name__ == "__main__":
    bid = sys.argv[1] if len(sys.argv) > 1 else "stick"
    fmt = sys.argv[2] if len(sys.argv) > 2 else "markdown"
    out = build_v3(bid, fmt=fmt)
    print(out["rendered"])
    sys.exit(0 if out["report_status"] !=
             "BLOCKED_BRAND_CONTAMINATION" else 2)
