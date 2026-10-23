"""Ad tracking health: does each ad's link carry usable UTMs, and does Google Analytics see its visits?

Read-only on Meta and on GA4. The ads_brief job keeps the result under ads-tracking/latest.json.

What it checks, per running ad:
    where the button goes      website, lead form, messaging (never reaches the site), or unknown
    what its UTMs say          read from the creative's URL parameters and the link itself
    what is wrong with them    missing, incomplete, a placeholder typed literally, a whole URL pasted in
    what GA4 saw               paid sessions in the last 28 days, joined on the Meta ad id

Meta's own tagging puts the campaign id and ad id into GA4's campaign and content fields, so an ad joins
exactly even when nobody typed a UTM. A name-based UTM is still worth having: it can be read in GA4.
"""
from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import re
import tempfile
import urllib.parse

from . import ads_brain, ads_naming

SCHEMA = "https://campaign-os/ads-tracking/v1"
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content")
# The convention proposed on 2026-10-20 (research/ads-measurement-naming-utm-ga4). Differences are information,
# not faults, until the convention is agreed.
PROPOSED = {"utm_source": "meta", "utm_medium": "paid_social"}
# GA4 session mediums that mean paid traffic here: Meta's own tagging says "paid"; hand-typed ones vary.
PAID_MEDIUMS = {"paid", "paid_social", "cpc", "ppc", "meta_leads", "leads"}
_MACRO = re.compile(r"\{\{\s*([^}]*?)\s*\}\}|%7B%7B(.*?)%7D%7D", re.I)


def parse_params(url_tags, link_url) -> tuple[dict, list[str]]:
    """Merge the creative's URL parameters with any in the link. Returns (params, problems)."""
    problems, params = [], {}
    tags = (url_tags or "").strip()
    if "://" in tags:
        problems.append("URL_IN_TAGS")
        tags = urllib.parse.urlparse(tags).query
    tags = tags.lstrip("?")
    for src in (urllib.parse.urlparse(link_url or "").query, tags):
        for k, v in urllib.parse.parse_qsl(src, keep_blank_values=True):
            params[k.lower()] = v
    for k, v in params.items():
        if k in UTM_KEYS and (v == "" or v.lower() in ("none", "null", "undefined")):
            problems.append("EMPTY_VALUE")
    for m in _MACRO.finditer(urllib.parse.unquote(tags)):
        token = (m.group(1) or m.group(2) or "").strip()
        # Meta's real macros look like {{campaign.name}}; a bare word was typed by hand and will arrive as text.
        if "." not in token:
            problems.append("PLACEHOLDER_LITERAL")
            break
    return params, sorted(set(problems))


def _kind(dest: dict) -> str:
    status = (dest or {}).get("status")
    if status == "RESOLVED":
        return "WEBSITE"
    return {"LEAD_FORM": "LEAD_FORM", "MESSAGING": "MESSAGING"}.get(status, "UNKNOWN")


def _host(url) -> str | None:
    if not url:
        return None
    return urllib.parse.urlparse(url if "://" in url else "https://" + url).hostname


def performance(ad: dict, seen: dict | None, kind: str) -> dict:
    """One ad's results in one place: Meta's spend and outcomes, Google Analytics' visits and what they did.

    Nothing here is guessed. A figure that cannot exist (cost per visit for an ad nobody visited, GA4 numbers for a
    lead-form ad) is None, never zero, so a table never says "R0" for something unknown.
    """
    cur = ad.get("current") or {}
    spend = float(cur.get("spend") or 0)
    leads, messages = int(cur.get("leads") or 0), int(cur.get("messages") or 0)
    sessions = (seen or {}).get("sessions", 0)
    engaged = (seen or {}).get("engaged", 0)
    on_site = kind in ("WEBSITE", "UNKNOWN") and sessions > 0
    clicks = int(cur.get("link_clicks") or 0)
    return {
        "impressions": int(cur.get("impressions") or 0), "leads": leads, "messages": messages,
        "cost_per_lead": round(spend / leads, 2) if leads else None,
        "cost_per_message": round(spend / messages, 2) if messages else None,
        "cost_per_session": round(spend / sessions, 2) if on_site else None,
        "engaged_pct": round(100 * engaged / sessions, 1) if on_site else None,
        # Clicks Meta counted that never became a Google Analytics visit (slow page, bounced early, blockers).
        "click_to_session_pct": round(100 * sessions / clicks, 1) if on_site and clicks else None,
        "key_events": (seen or {}).get("key_events", 0) if on_site else None,
    }


def audit_ad(ad: dict, tags: dict, ga: dict, flexible: set | None = None) -> dict:
    """One ad's tracking picture. ``tags`` is {ad_id: url_tags}; ``ga`` is {ad_id: {...sessions}}."""
    dest = ad.get("destination") or {}
    kind = _kind(dest)
    link = dest.get("url") or (ad.get("creative") or {}).get("link_url")
    params, problems = parse_params(tags.get(ad["ad_id"]), link)
    utm = {k: params.get(k) for k in UTM_KEYS}
    issues = list(problems)
    if kind == "WEBSITE":
        have = [k for k in UTM_KEYS[:3] if params.get(k)]
        if not any(params.get(k) for k in UTM_KEYS):
            issues.append("NO_UTM")
        elif len(have) < 3:
            issues.append("INCOMPLETE_UTM")
    seen = ga.get(ad["ad_id"])
    notes = []
    if kind == "WEBSITE" and seen and "NO_UTM" in issues:
        notes.append("Seen in GA4 by Meta's ad id only; no readable UTM.")
    if kind in ("LEAD_FORM", "MESSAGING"):
        notes.append("Never reaches the website: measured in Meta (leads, messages), not GA4.")
    if kind == "UNKNOWN":
        notes.append(dest.get("reason") or "Destination could not be read.")
    if kind == "WEBSITE" and utm.get("utm_source") and utm["utm_source"] != PROPOSED["utm_source"]:
        notes.append(f"Source '{utm['utm_source']}' differs from the proposed 'meta'.")
    if kind == "WEBSITE" and utm.get("utm_medium") and utm["utm_medium"] != PROPOSED["utm_medium"]:
        notes.append(f"Medium '{utm['utm_medium']}' differs from the proposed 'paid_social'.")
    return {
        "ad_id": ad["ad_id"], "ad_name": ad.get("ad_name"),
        "campaign": (ad.get("campaign") or {}).get("name"),
        "destination": kind, "host": _host(dest.get("url")),
        "utm": utm, "issues": sorted(set(issues)), "notes": notes,
        "ids": {"campaign": (ad.get("campaign") or {}).get("id"), "adset": (ad.get("adset") or {}).get("id")},
        "names": {"ad": ad.get("ad_name"), "adset": (ad.get("adset") or {}).get("name"),
                  "campaign": (ad.get("campaign") or {}).get("name")},
        "current_tags": tags.get(ad["ad_id"]) or "",
        "tags_fixable": ad["ad_id"] not in (flexible or set()),
        "ga_sessions": (seen or {}).get("sessions", 0), "ga_engaged": (seen or {}).get("engaged", 0),
        "ga_key_events": (seen or {}).get("key_events", 0),
        "spend": (ad.get("current") or {}).get("spend", 0),
        "link_clicks": (ad.get("current") or {}).get("link_clicks", 0),
        "landing_page_views": (ad.get("current") or {}).get("landing_page_views", 0),
        "perf": performance(ad, seen, kind),
    }


def join_ga(rows: list[list], ad_ids: set[str]) -> tuple[dict, dict]:
    """Join GA4 rows to ads on the Meta ad id. Rows are [source, medium, campaign, content, sessions, engaged,
    (key events)].

    Returns ({ad_id: {sessions, engaged}}, {"paid_sessions", "matched", "unmatched"}).
    """
    by_ad, paid, matched = {}, 0, 0
    for src, med, camp, content, sessions, engaged, *rest in rows:
        s, e = int(float(sessions or 0)), int(float(engaged or 0))
        k = int(float(rest[0] or 0)) if rest else 0
        is_paid = med.lower() in PAID_MEDIUMS
        if not is_paid:
            continue
        paid += s
        hit = next((x for x in (content, camp) if x in ad_ids), None)
        if hit:
            cur = by_ad.setdefault(hit, {"sessions": 0, "engaged": 0})
            cur["sessions"] += s
            cur["engaged"] += e
            if rest:  # only rows that carry the key-events column add it
                cur["key_events"] = cur.get("key_events", 0) + k
            matched += s
    return by_ad, {"paid_sessions": paid, "matched": matched, "unmatched": paid - matched}


def summarise(ads: list[dict], totals: dict) -> dict:
    web = [a for a in ads if a["destination"] == "WEBSITE"]
    return {
        "running_ads": len(ads), "website_ads": len(web),
        "website_with_complete_utm": sum(1 for a in web if not any(
            i in a["issues"] for i in ("NO_UTM", "INCOMPLETE_UTM"))),
        "website_with_problems": sum(1 for a in web if a["issues"]),
        "never_reach_site": sum(1 for a in ads if a["destination"] in ("LEAD_FORM", "MESSAGING")),
        "unknown_destination": sum(1 for a in ads if a["destination"] == "UNKNOWN"),
        "ga_paid_sessions": totals.get("paid_sessions"), "ga_matched": totals.get("matched"),
    }


# ── reads (read-only) ───────────────────────────────────────────────────────

def fetch_tag_info(account_id: str, token: str, *, api_version: str | None = None, get=None):
    """Each ad's URL parameters, and which ads use flexible (dynamic) creative. Returns (tags, flexible_ids, error).

    Meta's flexible creative cannot be copied with new parameters from here, so those ads are marked: nearly every ad
    in both accounts is of this kind (found 2026-10-21).
    """
    ver = api_version or ads_brain.DEFAULT_API_VERSION
    if get is None:
        def get(path, params):
            return ads_brain._graph_get(path, token, params)
    rows, err = ads_brain._get_all(get, f"/{ver}/{account_id}/ads",
                                   {"fields": "id,creative{url_tags,asset_feed_spec}", "limit": 200})
    tags = {r["id"]: (r.get("creative") or {}).get("url_tags") for r in rows or []}
    flexible = {r["id"] for r in rows or [] if (r.get("creative") or {}).get("asset_feed_spec")}
    return tags, flexible, err


def fetch_url_tags(account_id: str, token: str, *, api_version: str | None = None, get=None) -> tuple[dict, str | None]:
    tags, _flexible, err = fetch_tag_info(account_id, token, api_version=api_version, get=get)
    return tags, err


def ga4_rows(brand_id: str, days: int = 28) -> tuple[list[list], str | None]:
    """Paid-looking sessions by source, medium, campaign and ad content from GA4. Returns (rows, error)."""
    safe = brand_id.upper().replace("-", "_")
    prop = (os.environ.get(f"GA4_PROPERTY_{safe}") or "").strip()
    raw = os.environ.get(f"GA4_CREDENTIALS_JSON_{safe}")
    if not prop or not raw:
        return [], "GA4 not configured for this brand"
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
        path = os.path.join(tempfile.mkdtemp(), "ga4.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(base64.b64decode(raw.strip()).decode("utf-8"))
        os.chmod(path, 0o600)
        client = BetaAnalyticsDataClient.from_service_account_file(path)
        resp = client.run_report(RunReportRequest(
            property=f"properties/{prop}",
            dimensions=[Dimension(name=d) for d in ("sessionSource", "sessionMedium", "sessionCampaignName",
                                                    "sessionManualAdContent")],
            metrics=[Metric(name="sessions"), Metric(name="engagedSessions"), Metric(name="keyEvents")],
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")], limit=500))
        return [[v.value for v in r.dimension_values] + [v.value for v in r.metric_values] for r in resp.rows], None
    except Exception as exc:  # the ads brief never depends on this
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"


def performance_totals(rows: list[dict]) -> dict:
    """Whole-brand numbers for the table header and the weekly report, from the per-ad rows."""
    spend = sum(r["spend"] or 0 for r in rows)
    leads = sum(r["perf"]["leads"] for r in rows)
    messages = sum(r["perf"]["messages"] for r in rows)
    site = [r for r in rows if r["perf"]["cost_per_session"] is not None]
    sessions = sum(r["ga_sessions"] for r in site)
    engaged = sum(r["ga_engaged"] for r in site)
    return {
        "spend": round(spend, 2), "leads": leads, "messages": messages,
        "cost_per_lead": round(sum(r["spend"] for r in rows if r["perf"]["leads"]) / leads, 2) if leads else None,
        "ga_sessions": sessions, "ga_engaged_pct": round(100 * engaged / sessions, 1) if sessions else None,
        "ga_key_events": sum(r["ga_key_events"] for r in site),
        "site_spend": round(sum(r["spend"] for r in site), 2),
        "cost_per_session": round(sum(r["spend"] for r in site) / sessions, 2) if sessions else None,
    }


def build(brand_id: str, ads: list[dict], tags: dict, ga_rows: list[list], *, today: _dt.date,
          errors: list | None = None, flexible: set | None = None) -> dict:
    """The whole tracking picture for a brand. Pure."""
    # Every ad that delivered in the window, paused or not: the point is to fix links before something is turned back on.
    running = [a for a in ads if a.get("effective_status") not in ("DELETED", "ARCHIVED") and
               ((a.get("current") or {}).get("spend") or 0) > 0]
    by_ad, totals = join_ga(ga_rows, {a["ad_id"] for a in ads})
    audited = sorted((audit_ad(a, tags, by_ad, flexible) for a in running), key=lambda r: -(r["spend"] or 0))
    # The standard name and tags for each; two ads of the same subject and format in one campaign get v1, v2.
    by_id = {a["ad_id"]: a for a in running}
    seen: dict = {}
    for row in audited:
        ad = by_id[row["ad_id"]]
        key = (row["names"]["campaign"], ads_naming.theme(ad), (ad.get("creative") or {}).get("media_type"))
        seen[key] = seen.get(key, 0) + 1
        row["proposal"] = ads_naming.proposed(ad, brand_id, today, version=seen[key])
    return {"schema": SCHEMA, "brand_id": brand_id, "date": today.isoformat(), "ga_days": 28,
            "summary": summarise(audited, totals), "totals": performance_totals(audited), "ads": audited,
            "errors": list(errors or [])[:3]}
