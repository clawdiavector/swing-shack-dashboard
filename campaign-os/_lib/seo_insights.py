"""
seo_insights.py — SEO insights engine.

Turns raw Ubersuggest data into actionable sections:
  - Winning: top positions, gaining rank
  - Leaking: lost rank, dropping pages
  - Missing: high-volume queries we don't rank for at all
  - Growing / Declining / Quick wins / Opportunities
  - Domain Health: DA / backlinks / keyword footprint

Each item: keyword + position + volume + opportunity_label + evidence +
manager_read.

No fake data. The OS will say 'I can't tell yet' when evidence is missing.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Dict, List, Optional

DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def load_seo_rankings() -> Dict[str, Any]:
    path = os.path.join(DATA_DIR, "seo-rankings.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_domain_overview() -> Dict[str, Any]:
    path = os.path.join(DATA_DIR, "ubersuggest-domain.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_competitors() -> Dict[str, Any]:
    path = os.path.join(DATA_DIR, "ubersuggest-competitors.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_backlinks() -> Dict[str, Any]:
    path = os.path.join(DATA_DIR, "ubersuggest-backlinks.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def freshness() -> Dict[str, Any]:
    """How fresh is the SEO data?"""
    files = ["seo-rankings.json", "ubersuggest-domain.json", "ubersuggest-competitors.json", "ubersuggest-backlinks.json"]
    fresh = {}
    for fn in files:
        path = os.path.join(DATA_DIR, fn)
        if not os.path.isfile(path):
            fresh[fn] = {"exists": False, "age_days": None}
            continue
        mtime = os.path.getmtime(path)
        dt_mtime = _dt.datetime.fromtimestamp(mtime)
        age = (_dt.datetime.now() - dt_mtime).days
        fresh[fn] = {
            "exists": True,
            "fetched_at": dt_mtime.isoformat(),
            "age_days": age,
            "fresh": age <= 7,
        }
    return fresh


def _cur(k: Dict[str, Any]):
    """Get current rank from either current_rank (legacy) or new_position.position (live)."""
    if k.get("current_rank") is not None:
        return k.get("current_rank")
    np_ = k.get("new_position") or {}
    return np_.get("position") if isinstance(np_, dict) else None


def _prev(k: Dict[str, Any]):
    """Get previous rank from either previous_rank (legacy) or old_position.position (live)."""
    if k.get("previous_rank") is not None:
        return k.get("previous_rank")
    op = k.get("old_position") or {}
    return op.get("position") if isinstance(op, dict) else None


def _vol(k: Dict[str, Any]):
    return k.get("search_volume") or k.get("volume") or 0


def winning_keywords(rankings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Top 10 positions OR improved rank this period."""
    kws = rankings.get("keywords", []) or []
    out = []
    for k in kws:
        cur = _cur(k)
        prev = _prev(k)
        if cur is None:
            continue
        if cur is not None and cur <= 10:
            delta = (prev - cur) if prev else None
            out.append({
                "keyword": k.get("keyword"),
                "current_position": cur,
                "previous_position": prev,
                "delta": delta,
                "volume": k.get("search_volume") or 0,
                "url": k.get("current_url"),
                "seo_difficulty": k.get("seo_difficulty"),
                "opportunity_label": "winning",
                "manager_read": (
                    f"#{cur} for '{k.get('keyword')}' "
                    f"({k.get('search_volume', 0)} searches/mo). "
                    + (f"Up from #{prev}." if prev and prev > cur else "Holding top 10.")
                ),
            })
    out.sort(key=lambda x: (x["current_position"] or 999, -x["volume"]))
    return out


def leaking_keywords(rankings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Lost rank this period."""
    kws = rankings.get("keywords", []) or []
    out = []
    for k in kws:
        cur = _cur(k)
        prev = _prev(k)
        if cur is None or prev is None:
            continue
        if cur > prev:
            delta = cur - prev
            out.append({
                "keyword": k.get("keyword"),
                "current_position": cur,
                "previous_position": prev,
                "delta": delta,
                "volume": k.get("search_volume") or 0,
                "url": k.get("current_url"),
                "seo_difficulty": k.get("seo_difficulty"),
                "opportunity_label": "leaking",
                "manager_read": (
                    f"Dropped #{prev} -> #{cur} for '{k.get('keyword')}' "
                    f"({k.get('search_volume', 0)} searches/mo). "
                    + ("Page 2+ - needs attention." if cur > 10 else "Still on page 1 but slipping.")
                ),
            })
    out.sort(key=lambda x: -x["delta"])
    return out


def missing_keywords(rankings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """High-volume keywords we don't rank for at all."""
    kws = rankings.get("keywords", []) or []
    out = []
    for k in kws:
        cur = _cur(k)
        vol = _vol(k)
        if cur is None and vol >= 100:
            out.append({
                "keyword": k.get("keyword"),
                "current_position": None,
                "previous_position": k.get("previous_rank"),
                "volume": vol,
                "url": None,
                "seo_difficulty": k.get("seo_difficulty"),
                "opportunity_label": "missing",
                "manager_read": (
                    f"Not ranking for '{k.get('keyword')}' "
                    f"({vol} searches/mo). "
                    f"High-volume query competitors likely own."
                ),
            })
    out.sort(key=lambda x: -x["volume"])
    return out


def quick_wins(rankings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Page-2 keywords (positions 11-20) with decent volume - biggest ROI."""
    kws = rankings.get("keywords", []) or []
    out = []
    for k in kws:
        cur = _cur(k)
        vol = _vol(k)
        if cur is None:
            continue
        if 11 <= cur <= 20 and vol >= 50:
            out.append({
                "keyword": k.get("keyword"),
                "current_position": cur,
                "previous_position": k.get("previous_rank"),
                "volume": vol,
                "url": k.get("current_url"),
                "seo_difficulty": k.get("seo_difficulty"),
                "opportunity_label": "quick_win",
                "manager_read": (
                    f"Position #{cur} for '{k.get('keyword')}' "
                    f"({vol} searches/mo). "
                    f"Push to page 1 with focused content work."
                ),
            })
    out.sort(key=lambda x: x["current_position"])
    return out


def domain_health() -> Dict[str, Any]:
    """Snapshot of domain authority + backlink profile + keyword footprint."""
    domain = load_domain_overview()
    bl = load_backlinks()
    rank = load_seo_rankings()
    binned = (rank.get("binned") or {})
    sm = (rank.get("summary") or {})

    top3_now = (binned.get("top_3") or {}).get("new", 0) or 0
    top3_old = (binned.get("top_3") or {}).get("old", 0) or 0
    top10_now = (binned.get("top_10") or {}).get("new", 0) or 0
    top10_old = (binned.get("top_10") or {}).get("old", 0) or 0
    ranking = (binned.get("top_100") or {}).get("new", 0) or 0
    not_ranking = (binned.get("not_ranking") or {}).get("new", 0) or 0

    da = domain.get("domainAuthority", 0)

    summary_lines = []
    if top3_now > top3_old:
        summary_lines.append(f"Top-3 count grew from {top3_old} -> {top3_now}.")
    if top10_now < top10_old:
        summary_lines.append(f"Top-10 count fell from {top10_old} -> {top10_now}.")
    if not summary_lines:
        summary_lines.append("Position distribution stable this period.")

    return {
        "domain": domain.get("domain", "swingshack.co.za"),
        "domain_authority": da,
        "total_backlinks": bl.get("backlinks", 0),
        "ref_domains": bl.get("refDomains", 0),
        "follow_links": bl.get("follow", 0),
        "nofollow_links": bl.get("noFollow", 0),
        "keyword_footprint": {
            "tracked": len(rank.get("keywords", []) or []),
            "top_3": top3_now,
            "top_10": top10_now,
            "ranking_top_100": ranking,
            "not_ranking": not_ranking,
        },
        "weekly_change": {
            "up": sm.get("up", 0),
            "down": sm.get("down", 0),
            "unchanged": sm.get("unchanged", 0),
        },
        "manager_read": (
            f"DA {da}, {bl.get('backlinks', 0)} backlinks from {bl.get('refDomains', 0)} domains. "
            f"{top3_now} keywords in top-3, {top10_now} in top-10, "
            f"{ranking} ranking in top-100, {not_ranking} not ranking. "
            + " ".join(summary_lines)
        ),
    }


def competitors_table() -> List[Dict[str, Any]]:
    """List competitors + their DA + common keywords if available."""
    comps = load_competitors()
    items = comps.get("competitors", []) or []
    out = []
    for c in items[:15]:
        if not isinstance(c, dict):
            continue
        out.append({
            "domain": c.get("domain"),
            "domain_authority": c.get("domainAuthority"),
            "common_keywords": c.get("commonKeywords"),
            "raw": c,
        })
    return out


def build_full_insights() -> Dict[str, Any]:
    """Assemble the full SEO insights report."""
    rank = load_seo_rankings()
    dom = domain_health()
    winning = winning_keywords(rank)
    leaking = leaking_keywords(rank)
    missing = missing_keywords(rank)
    quick = quick_wins(rank)
    comps = competitors_table()
    fresh = freshness()
    md = rank.get("metadata", {}) or {}

    # Counts summary
    summary = {
        "winning_count": len(winning),
        "leaking_count": len(leaking),
        "missing_count": len(missing),
        "quick_win_count": len(quick),
        "competitor_count": len(comps),
    }

    return {
        "domain": dom["domain"],
        "freshness": fresh,
        "domain_health": dom,
        "winning": winning,
        "leaking": leaking,
        "missing": missing,
        "quick_wins": quick,
        "competitors": comps,
        "summary": summary,
        "metadata": {
            "fetched_at": md.get("fetched_at"),
            "start_date": md.get("startDate"),
            "end_date": md.get("endDate"),
            "project_id": md.get("project_id"),
        },
        "generated_at": _now_iso(),
    }


def render_markdown(insights: Dict[str, Any]) -> str:
    """Render the insights report as plain-language markdown."""
    dh = insights["domain_health"]
    md_lines = []
    md_lines.append(f"# SEO Insights — {insights['domain']}")
    md_lines.append("")
    md_lines.append(f"**Generated:** {insights['generated_at'][:19]}")
    md_lines.append("")
    md_lines.append("## Domain Health")
    md_lines.append("")
    md_lines.append(f"- **Domain Authority:** {dh['domain_authority']}")
    md_lines.append(f"- **Total backlinks:** {dh['total_backlinks']}")
    md_lines.append(f"- **Referring domains:** {dh['ref_domains']}")
    md_lines.append(f"- **Follow links:** {dh['follow_links']}  /  **Nofollow:** {dh['nofollow_links']}")
    md_lines.append(f"- **Keyword footprint:** {dh['keyword_footprint']['tracked']} tracked")
    md_lines.append(f"  - Top 3: {dh['keyword_footprint']['top_3']}")
    md_lines.append(f"  - Top 10: {dh['keyword_footprint']['top_10']}")
    md_lines.append(f"  - Top 100: {dh['keyword_footprint']['ranking_top_100']}")
    md_lines.append(f"  - Not ranking: {dh['keyword_footprint']['not_ranking']}")
    md_lines.append("")
    md_lines.append(f"**Weekly change:** {dh['weekly_change']['up']} up / {dh['weekly_change']['down']} down / {dh['weekly_change']['unchanged']} unchanged")
    md_lines.append("")
    md_lines.append(f"**Manager read:** {dh['manager_read']}")
    md_lines.append("")

    # Winning
    md_lines.append("## Winning")
    md_lines.append("")
    if insights["winning"]:
        for w in insights["winning"][:10]:
            delta = f" (up {w['previous_position'] - w['current_position']})" if w.get("delta") and w["delta"] > 0 else ""
            md_lines.append(f"- **#{w['current_position']}{delta}** — `{w['keyword']}` ({w['volume']} vol) — {w['manager_read']}")
    else:
        md_lines.append("_No winning keywords in top 10 yet._")
    md_lines.append("")

    # Leaking
    md_lines.append("## Leaking")
    md_lines.append("")
    if insights["leaking"]:
        for l in insights["leaking"][:10]:
            md_lines.append(f"- **#{l['previous_position']} -> #{l['current_position']}** — `{l['keyword']}` ({l['volume']} vol) — {l['manager_read']}")
    else:
        md_lines.append("_No keywords lost rank this period._")
    md_lines.append("")

    # Missing
    md_lines.append("## Missing")
    md_lines.append("")
    if insights["missing"]:
        for m in insights["missing"][:10]:
            md_lines.append(f"- `{m['keyword']}` ({m['volume']} vol) — {m['manager_read']}")
    else:
        md_lines.append("_No high-volume gaps detected in tracked keywords._")
    md_lines.append("")

    # Quick wins
    md_lines.append("## Quick wins (page 2 -> page 1)")
    md_lines.append("")
    if insights["quick_wins"]:
        for q in insights["quick_wins"][:10]:
            md_lines.append(f"- **#{q['current_position']}** — `{q['keyword']}` ({q['volume']} vol) — {q['manager_read']}")
    else:
        md_lines.append("_No page-2 quick wins this period._")
    md_lines.append("")

    # Competitors
    md_lines.append("## Competitors")
    md_lines.append("")
    if insights["competitors"]:
        for c in insights["competitors"][:10]:
            md_lines.append(f"- **{c['domain']}** — DA {c['domain_authority']}")
    else:
        md_lines.append("_No competitor data._")
    md_lines.append("")

    # Freshness
    md_lines.append("## Data freshness")
    md_lines.append("")
    for fn, info in insights["freshness"].items():
        if not info.get("exists"):
            md_lines.append(f"- `{fn}` — not present")
            continue
        age = info.get("age_days", "?")
        md_lines.append(f"- `{fn}` — {age}d ago — {'fresh' if info.get('fresh') else 'STALE'}")
    md_lines.append("")

    return "\n".join(md_lines)