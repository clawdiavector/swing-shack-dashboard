"""Refresh booking-events.json + leads.json from GA4 signals and Reddit trends."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from ._io import as_dict, as_list, atomic_write, read_json, repo_root, utc_date, utc_now_iso, io_for_job

JOB_NAME = "booking_truth"
from . import ga4_report

BOOKING_OUT = "booking-events.json"
LEADS_OUT = "leads.json"
LEAD_QUALITY_OUT = "lead-quality.json"

# GA4 event / page signals mapped to booking-events inventory rows.
EVENT_SIGNALS: dict[str, list[str]] = {
    "booking_started": ["page_view", "session_start"],
    "service_selected": ["service_selected", "select_service", "form_start"],
    "booking_completed": ["booking_completed", "purchase", "booking_confirmed", "form_submit"],
    "booking_value_proxy": ["booking_completed", "purchase"],
    "contact_form_submit": ["generate_lead", "form_submit", "contact"],
    "whatsapp_click": ["whatsapp_click", "click_whatsapp"],
}


def _load_booking_template() -> dict:
    existing = as_dict(io.read(BOOKING_OUT))
    if existing.get("events"):
        return existing
    seed = repo_root() / "data" / BOOKING_OUT
    if seed.is_file():
        return as_dict(json.loads(seed.read_text(encoding="utf-8")))
    return {
        "schema": "https://clawdia.io/agents/booking-event-mapper/v1",
        "events": [],
    }


def _fetch_ga4_event_counts(property_id: str, bearer: str, start: str, end: str) -> dict[str, int]:
    body = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": "eventName"}],
        "metrics": [{"name": "eventCount"}],
        "limit": 200,
    }
    report = ga4_report._run_ga4_report(property_id, bearer, body)
    counts: dict[str, int] = {}
    for row in report.get("rows") or []:
        dims = row.get("dimensionValues") or []
        metrics = row.get("metricValues") or []
        name = dims[0].get("value") if dims else ""
        count = int((metrics[0].get("value") if metrics else 0) or 0)
        if name:
            counts[name] = count
    return counts


def _fetch_booking_page_sessions(property_id: str, bearer: str, start: str, end: str) -> int:
    body = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": "pagePath"}],
        "metrics": [{"name": "sessions"}],
        "limit": 50,
        "dimensionFilter": {
            "filter": {
                "fieldName": "pagePath",
                "stringFilter": {"value": "/book", "matchType": "CONTAINS"},
            }
        },
    }
    report = ga4_report._run_ga4_report(property_id, bearer, body)
    total = 0
    for row in report.get("rows") or []:
        metrics = row.get("metricValues") or []
        total += int((metrics[0].get("value") if metrics else 0) or 0)
    return total


def _event_measurable(event_id: str, ga_counts: dict[str, int], booking_sessions: int) -> tuple[bool, int, str]:
    signals = EVENT_SIGNALS.get(event_id, [])
    matched = 0
    matched_names: list[str] = []
    for sig in signals:
        if ga_counts.get(sig, 0) > 0:
            matched += ga_counts[sig]
            matched_names.append(sig)

    if event_id == "booking_started" and booking_sessions > 0:
        return True, booking_sessions, f"/book sessions={booking_sessions}"

    if matched > 0:
        return True, matched, f"GA4 events: {', '.join(matched_names)}"

    return False, 0, "No GA4 signal in last 28 days"


def _reddit_leads() -> list[dict]:
    reddit = as_dict(io.read("reddit-trends.json"))
    leads: list[dict] = []
    idx = 0
    for src in ("hot_pain_points", "trends", "top_posts"):
        for item in as_list(reddit.get(src))[:15]:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or item.get("pain_point") or "").strip()
            if not title:
                continue
            idx += 1
            score = int(item.get("score") or item.get("heat") or 5)
            leads.append({
                "id": f"lead-{utc_date()}-{idx}",
                "url": item.get("url") or item.get("permalink") or "https://reddit.com/r/golf",
                "title": title[:120],
                "source": item.get("subreddit") or src,
                "dateFound": utc_date(),
                "problem": (item.get("selftext_snippet") or item.get("summary") or title)[:200],
                "service": "coaching" if "lesson" in title.lower() else "fitting" if "fit" in title.lower() else "other",
                "location": "SA" if "south africa" in title.lower() or " sa" in title.lower() else "international",
                "intent": "high" if score >= 40 else "medium",
                "score": min(10, max(1, score // 10 if score > 10 else score)),
                "status": "new",
            })
    return leads[:25]


def run(*, brand: str | None = None) -> dict:
    """Update booking funnel measurability + refresh lead inventory."""
    io = io_for_job(JOB_NAME, brand)
    template = _load_booking_template()
    events_in = as_list(template.get("events"))
    if not events_in:
        return {"ok": False, "error": f"{BOOKING_OUT} has no events inventory"}

    missing = ga4_report._missing_env_error()
    ga_counts: dict[str, int] = {}
    booking_sessions = 0
    ga_ok = False
    if not missing:
        end = date.today()
        start = end - timedelta(days=28)
        try:
            property_id, _ = ga4_report._resolve_ga4_creds()
            bearer = ga4_report._get_ga4_bearer()
            ga_counts = _fetch_ga4_event_counts(property_id, bearer, start.isoformat(), end.isoformat())
            booking_sessions = _fetch_booking_page_sessions(
                property_id, bearer, start.isoformat(), end.isoformat()
            )
            ga_ok = True
        except RuntimeError:
            ga_ok = False

    updated_events: list[dict] = []
    measurable = 0
    for ev in events_in:
        if not isinstance(ev, dict):
            continue
        row = dict(ev)
        event_id = row.get("event_id") or ""
        if ga_ok:
            is_measurable, count, note = _event_measurable(event_id, ga_counts, booking_sessions)
            row["current_measurable"] = is_measurable
            row["ga4_count_last_28d"] = count
            row["ga4_probe_note"] = note
            row["last_probed_at"] = utc_now_iso()
            if is_measurable:
                measurable += 1
        updated_events.append(row)

    priority_one_unmeasured = sum(
        1 for e in updated_events
        if e.get("priority") == 1 and not e.get("current_measurable")
    )

    booking_payload = {
        "schema": template.get("schema") or "https://clawdia.io/agents/booking-event-mapper/v1",
        "generated": utc_now_iso(),
        "events": updated_events,
        "summary": {
            "measurable": measurable,
            "total": len(updated_events),
            "priority_one_unmeasured": priority_one_unmeasured,
            "ga4_probe_ok": ga_ok,
        },
    }
    io.write(BOOKING_OUT, booking_payload)

    # Leads: merge Reddit-derived prospects with any existing non-stale manual leads.
    existing_leads = as_dict(io.read(LEADS_OUT))
    preserved = [
        l for l in as_list(existing_leads.get("leads"))
        if isinstance(l, dict) and l.get("status") not in ("new",)
    ]
    fresh = _reddit_leads()
    seen_titles = {re.sub(r"\s+", " ", (l.get("title") or "").lower()) for l in preserved}
    merged = list(preserved)
    for lead in fresh:
        key = re.sub(r"\s+", " ", (lead.get("title") or "").lower())
        if key and key not in seen_titles:
            merged.append(lead)
            seen_titles.add(key)

    leads_payload = {
        "updated": utc_now_iso(),
        "source": "layer1/booking_truth.py",
        "leads": merged[:40],
        "summary": {
            "total": len(merged[:40]),
            "new_from_reddit": len(fresh),
            "preserved": len(preserved),
        },
    }
    io.write(LEADS_OUT, leads_payload)

    high_intent = [l for l in merged if l.get("intent") == "high"]
    lead_quality_payload = {
        "schema": "https://clawdia.io/agents/lead-quality-scorer/v1",
        "updated": utc_now_iso(),
        "summary": {
            "total_leads": len(merged),
            "high_intent": len(high_intent),
            "medium_intent": sum(1 for l in merged if l.get("intent") == "medium"),
            "sources": ["reddit-trends.json", LEADS_OUT],
        },
        "top_leads": sorted(merged, key=lambda l: l.get("score", 0), reverse=True)[:10],
    }
    io.write(LEAD_QUALITY_OUT, lead_quality_payload)

    out = {
        "ok": True,
        "rows": measurable + len(fresh),
        "measurable_events": measurable,
        "leads": len(merged[:40]),
        "ga4_probe_ok": ga_ok,
    }
    if not ga_ok and missing:
        out["warning"] = missing
    return out
