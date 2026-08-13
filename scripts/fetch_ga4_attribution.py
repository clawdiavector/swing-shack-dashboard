#!/usr/bin/env python3
"""
fetch_ga4_attribution.py - Pull post-to-conversion attribution data from GA4.

Joins IG posts (by hook_id) to GA4 sessions to /bookings/, /club-fitting/,
and other high-intent pages attributed via UTM content.

Output: data/ga4-attribution.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

try:
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GARequest
except ImportError:
    print("google-auth not installed", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard"
CREDS_FILE = os.path.join(REPO_ROOT, "credentials", "google-service-account.json")
PROPERTY_ID = "427380680"
OUTPUT_FILE = os.path.join(REPO_ROOT, "data", "ga4-attribution.json")


def _get_token() -> str:
    creds = service_account.Credentials.from_service_account_file(
        CREDS_FILE,
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    creds.refresh(GARequest())
    return creds.token


def _run_ga4_query(token: str, body: dict) -> dict:
    """Run a GA4 Data API query using a temp curl config file for auth."""
    config_body = "header = \"Content-Type: application/json\"\nheader = \"Authorization: Bearer " + token + "\"\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".curl", delete=False) as cf:
        cf.write(config_body)
        config_path = cf.name
    try:
        cmd = [
            "curl", "-s", "-X", "POST",
            f"https://analyticsdata.googleapis.com/v1beta/properties/{PROPERTY_ID}:runReport",
            "-K", config_path,
            "-d", json.dumps(body),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        try:
            return json.loads(result.stdout) if result.stdout else {"_stderr": result.stderr}
        except Exception as e:
            return {"_parse_error": str(e), "_raw": result.stdout[:500]}
    finally:
        try:
            os.unlink(config_path)
        except OSError:
            pass


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fetch_instagram_post_attribution(token, start_str, end_str):
    """Pull IG sessions to high-intent pages grouped by UTM content (hook_id)."""
    rows_out = []
    for page_filter in ("/bookings/", "/club-fitting/", "/membership/", "/customer-portal/"):
        body = {
            "dateRanges": [{"startDate": start_str, "endDate": end_str}],
            "dimensions": [
                {"name": "sessionManualAdContent"},
                {"name": "pagePath"},
            ],
            "metrics": [
                {"name": "sessions"},
                {"name": "engagementRate"},
                {"name": "conversions"},
            ],
            "limit": 50,
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
            "dimensionFilter": {
                "andGroup": {
                    "expressions": [
                        {"filter": {"fieldName": "sessionSource",
                                    "stringFilter": {"value": "instagram", "matchType": "EXACT"}}},
                        {"filter": {"fieldName": "pagePath",
                                    "stringFilter": {"value": page_filter, "matchType": "CONTAINS"}}},
                    ]
                },
            },
        }
        result = _run_ga4_query(token, body)
        if "rows" in result:
            for r in result["rows"]:
                utm_content = r["dimensionValues"][0]["value"]
                path = r["dimensionValues"][1]["value"]
                sess = _int(r["metricValues"][0]["value"])
                er = _float(r["metricValues"][1]["value"])
                conv = _int(r["metricValues"][2]["value"])
                if sess == 0:
                    continue
                rows_out.append({
                    "hook_id": utm_content,
                    "page_path": path,
                    "sessions": sess,
                    "engagement_rate": er,
                    "conversions": conv,
                    "source": "instagram",
                    "high_intent_match": page_filter,
                })
    return rows_out


def fetch_booking_completion_proxy(token, start_str, end_str):
    """
    /bookings/ pages with clientEmail/serviceId/packageRedeem in URL
    are PROXY booking completions - Amelia booking plugin populates
    these on the post-submit confirmation page. This is the closest
    signal to VERIFIED_REVENUE we can get without a booking_completed
    GA4 event being instrumented.

    Uses landingPagePlusQueryString to capture the full URL with params.
    """
    body = {
        "dateRanges": [{"startDate": start_str, "endDate": end_str}],
        "dimensions": [
            {"name": "landingPagePlusQueryString"},
            {"name": "sessionSource"},
            {"name": "sessionMedium"},
            {"name": "sessionCampaignId"},
        ],
        "metrics": [
            {"name": "sessions"},
            {"name": "engagementRate"},
            {"name": "totalUsers"},
        ],
        "limit": 200,
        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        "dimensionFilter": {
            "filter": {
                "fieldName": "landingPagePlusQueryString",
                "stringFilter": {"value": "/bookings/", "matchType": "CONTAINS"},
            },
        },
    }
    result = _run_ga4_query(token, body)
    if "rows" not in result:
        return {"total_sessions": 0, "completion_proxy_sessions": 0, "browse_sessions": 0,
                "by_source": [], "completion_proxy_paths": [], "browse_paths": [],
                "completions_by_source": []}

    completion_proxy = []
    browse_only = []
    by_source = {}
    completions_by_source = {}
    for r in result["rows"]:
        url = r["dimensionValues"][0]["value"]
        src = r["dimensionValues"][1]["value"]
        med = r["dimensionValues"][2]["value"]
        camp = r["dimensionValues"][3]["value"]
        sess = _int(r["metricValues"][0]["value"])
        er = _float(r["metricValues"][1]["value"])
        users = _int(r["metricValues"][2]["value"])
        is_completion = any(p in url.lower() for p in (
            "clientemail", "facilityid", "serviceid", "packageredeem", "success", "confirmed", "portalroute=activate"
        ))
        entry = {
            "url": url, "source": src, "medium": med, "campaign": camp,
            "sessions": sess, "engagement_rate": er, "users": users
        }
        if is_completion:
            completion_proxy.append(entry)
            completions_by_source[src] = completions_by_source.get(src, 0) + sess
        else:
            browse_only.append(entry)
        by_source[src] = by_source.get(src, 0) + sess

    return {
        "total_sessions": sum(e["sessions"] for e in completion_proxy) + sum(e["sessions"] for e in browse_only),
        "completion_proxy_sessions": sum(e["sessions"] for e in completion_proxy),
        "browse_sessions": sum(e["sessions"] for e in browse_only),
        "completion_proxy_count": len(completion_proxy),
        "browse_count": len(browse_only),
        "completion_proxy_paths": completion_proxy[:30],
        "browse_paths": browse_only[:30],
        "by_source": [{"source": k, "sessions": v} for k, v in sorted(by_source.items(), key=lambda kv: -kv[1])],
        "completions_by_source": [{"source": k, "sessions": v} for k, v in
                                   sorted(completions_by_source.items(), key=lambda kv: -kv[1])],
    }


def fetch_session_scoped_event_signals(token, start_str, end_str):
    """Pull all tracked event counts in window."""
    body = {
        "dateRanges": [{"startDate": start_str, "endDate": end_str}],
        "dimensions": [{"name": "eventName"}],
        "metrics": [{"name": "eventCount"}],
        "limit": 30,
        "orderBys": [{"metric": {"metricName": "eventCount"}, "desc": True}],
    }
    result = _run_ga4_query(token, body)
    if "rows" not in result:
        return {"events": [], "total_events": 0}
    events = []
    for r in result["rows"]:
        name = r["dimensionValues"][0]["value"]
        count = _int(r["metricValues"][0]["value"])
        events.append({"event_name": name, "count": count})
    return {"events": events, "total_events": sum(e["count"] for e in events)}


def join_to_ig_posts(attribution_rows, ig_business):
    """Match each GA4 hook_id to a real IG post."""
    media_by_hook = {}
    for m in (ig_business.get("media") or []):
        hook_id = m.get("hook_id") or ""
        if hook_id:
            media_by_hook[hook_id] = m

    enriched = []
    for row in attribution_rows:
        hook_id = row["hook_id"]
        post = media_by_hook.get(hook_id)
        if not post:
            # Loose prefix match
            for k, v in media_by_hook.items():
                if k.startswith(hook_id[:25]) or hook_id.startswith(k[:25]):
                    post = v
                    break
        is_booking_intent = any(p in row["page_path"].lower() for p in ("bookings", "club-fitting", "membership"))
        if post:
            reach = _int((post.get("metrics") or {}).get("reach", 0))
            likes = _int((post.get("metrics") or {}).get("likes", 0))
            comments = _int((post.get("metrics") or {}).get("comments", 0))
            er_pct = _float(post.get("engagement_rate_pct", 0))
            cap = (post.get("caption_preview") or "")[:100]
            permalink = post.get("permalink", "")
            timestamp = post.get("timestamp", "")
            sessions_per_1k_reach = round((row["sessions"] / reach * 1000), 3) if reach > 0 else 0
            enriched.append({
                **row,
                "post_id": post.get("id"),
                "post_timestamp": timestamp,
                "post_caption_preview": cap,
                "post_permalink": permalink,
                "post_reach": reach,
                "post_likes": likes,
                "post_comments": comments,
                "post_engagement_rate_pct": er_pct,
                "sessions_per_1k_reach": sessions_per_1k_reach,
                "matched": True,
                "is_booking_intent": is_booking_intent,
            })
        else:
            enriched.append({**row, "matched": False, "is_booking_intent": is_booking_intent})
    return enriched


def main():
    print("=== fetch_ga4_attribution.py ===")
    end_date = datetime(2026, 8, 13)
    start_date = end_date - timedelta(days=30)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    print(f"Window: {start_str} to {end_str}")

    token = _get_token()
    print("Auth: OK")

    print("\n[1/3] IG post -> high-intent page attribution...")
    raw_attribution = fetch_instagram_post_attribution(token, start_str, end_str)
    print(f"  Found {len(raw_attribution)} IG attribution rows")

    ig_business_path = os.path.join(REPO_ROOT, "data", "ig-business-analytics.json")
    ig_business = {}
    if os.path.exists(ig_business_path):
        with open(ig_business_path) as f:
            ig_business = json.load(f)
        print(f"  Loaded {len(ig_business.get('media') or [])} IG posts for join")

    enriched = join_to_ig_posts(raw_attribution, ig_business)
    matched_count = sum(1 for e in enriched if e.get("matched"))
    print(f"  Matched {matched_count}/{len(enriched)} hook_ids to IG posts")

    print("\n[2/3] Booking completion proxy...")
    completion = fetch_booking_completion_proxy(token, start_str, end_str)
    print(f"  Total /bookings/ sessions: {completion['total_sessions']}")
    print(f"  Completion-proxy sessions (with clientEmail/serviceId): {completion['completion_proxy_sessions']}")
    print(f"  Browse-only sessions: {completion['browse_sessions']}")
    if completion.get("by_source"):
        print(f"  Top sources to /bookings/:")
        for s in completion["by_source"][:5]:
            print(f"    {s['source']:25s} {s['sessions']:>5d} sessions")

    print("\n[3/3] Currently-tracked events...")
    events = fetch_session_scoped_event_signals(token, start_str, end_str)
    if events.get("events"):
        print(f"  Total events tracked: {events['total_events']}")
        print(f"  Top events:")
        for e in events["events"][:10]:
            print(f"    {e['event_name']:40s} {e['count']:>5d}")

    booking_intent = [e for e in enriched if e.get("is_booking_intent") and e.get("matched")]
    booking_intent.sort(key=lambda r: r.get("sessions_per_1k_reach", 0), reverse=True)
    top_posts = booking_intent[:10]
    print(f"\n  Top {len(top_posts)} IG posts by sessions-per-1k-reach to /bookings/:")
    for r in top_posts:
        print(f"    {r.get('post_timestamp', '')[:10]} hook={r['hook_id'][:30]:30s} "
              f"reach={r.get('post_reach', 0):>5d} sessions={r['sessions']:>3d} "
              f"sessions/1k={r.get('sessions_per_1k_reach', 0):.3f} "
              f"-> {r['page_path']}")

    out = {
        "schema": "https://clawdia.io/agents/ga4-post-attribution/v1",
        "updated": datetime.utcnow().isoformat() + "Z",
        "generated_by": "fetch_ga4_attribution.py",
        "window": {"start": start_str, "end": end_str},
        "property_id": PROPERTY_ID,
        "instagram_post_attribution": enriched,
        "booking_completion_proxy": completion,
        "events_tracked": events,
        "top_converting_posts": top_posts,
        "summary": {
            "ig_attribution_rows": len(enriched),
            "ig_attribution_matched_to_posts": matched_count,
            "total_booking_intent_sessions": sum(e["sessions"] for e in booking_intent),
            "completion_proxy_sessions": completion["completion_proxy_sessions"],
            "browse_only_sessions": completion["browse_sessions"],
            "events_tracked_count": len(events.get("events", [])),
            "has_booking_completed_event": any(
                "booking" in e["event_name"].lower() and "complet" in e["event_name"].lower()
                for e in events.get("events", [])
            ),
            "has_amelia_events": any(
                "amelia" in e["event_name"].lower() for e in events.get("events", [])
            ),
        },
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote: {OUTPUT_FILE}")
    print(f"  Summary: {json.dumps(out['summary'], indent=2)}")


if __name__ == "__main__":
    main()
