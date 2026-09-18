"""Refresh competitor-tracker.json from Instagram business_discovery + diffs."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from ._io import as_dict, as_list, atomic_write, read_json, repo_root, utc_date, utc_now_iso, io_for_job

JOB_NAME = "competitor_tracker"

OUTPUT = "competitor-tracker.json"
GRAPH_VERSION = "v19.0"


def _parse_instagram_username(social: Any) -> Optional[str]:
    if not social or not isinstance(social, str):
        return None
    s = social.strip().lower()
    if s.startswith("instagram/"):
        return s.split("/", 1)[1].strip() or None
    if s.startswith("@"):
        return s[1:].strip() or None
    if re.fullmatch(r"[a-z0-9._]+", s):
        return s
    return None


def _load_meta_creds() -> Optional[dict[str, str]]:
    import os

    if os.environ.get("META_SYSTEM_USER_TOKEN"):
        return {
            "token": os.environ["META_SYSTEM_USER_TOKEN"].strip(),
            "ig_id": os.environ.get("META_INSTAGRAM_BUSINESS_ACCOUNT_ID", "17841456713897671").strip(),
        }
    try:
        from _lib.meta_live_fetch import _load_token  # noqa: PLC0415

        creds = _load_token()
        if creds and creds.get("access_token") and creds.get("instagram_account_id"):
            return {
                "token": creds["access_token"],
                "ig_id": str(creds["instagram_account_id"]),
            }
    except Exception:
        pass
    return None


def _graph_get(url: str, timeout: int = 20) -> tuple[Optional[dict], Optional[str]]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        return None, f"HTTP {exc.code}: {body}"
    except Exception as exc:
        return None, str(exc)[:300]


def _fetch_competitor_ig(
    ig_id: str,
    token: str,
    username: str,
) -> tuple[Optional[dict], Optional[str]]:
    fields = (
        f"business_discovery.username({username})"
        "{username,followers_count,media_count,"
        "media.limit(12){id,caption,timestamp,like_count,comments_count,media_type,permalink}}"
    )
    q = urllib.parse.urlencode({"fields": fields, "access_token": token})
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{ig_id}?{q}"
    body, err = _graph_get(url)
    if err:
        return None, err
    bd = (body or {}).get("business_discovery") if isinstance(body, dict) else None
    if not isinstance(bd, dict):
        return None, "business_discovery missing (check token scopes / username)"
    return bd, None


def _posting_frequency(post_dates: list[str]) -> str:
    if not post_dates:
        return "unknown"
    if len(post_dates) < 2:
        return "infrequent"
    parsed = sorted(datetime.fromisoformat(d.replace("Z", "+00:00")) for d in post_dates if d)
    if len(parsed) < 2:
        return "unknown"
    span_days = max(1, (parsed[-1] - parsed[0]).days)
    per_week = len(parsed) / span_days * 7
    if per_week >= 5:
        return "daily"
    if per_week >= 3:
        return "3x/week"
    if per_week >= 2:
        return "2x/week"
    if per_week >= 1:
        return "weekly"
    return "infrequent"


def _infer_threat(freq: str, followers: int) -> str:
    if freq in ("daily", "3x/week") and followers >= 5000:
        return "high"
    if freq in ("daily", "3x/week", "2x/week"):
        return "medium"
    if freq == "weekly":
        return "medium"
    return "low"


def _build_changes(
    prev: dict[str, Any],
    updated: dict[str, Any],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    today = utc_date()
    prev_by_id = {c.get("id"): c for c in as_list(prev.get("competitors")) if c.get("id")}
    for comp in as_list(updated.get("competitors")):
        cid = comp.get("id")
        if not cid:
            continue
        old = prev_by_id.get(cid) or {}
        old_post = old.get("last_post")
        new_post = comp.get("last_post")
        old_freq = old.get("posting_frequency")
        new_freq = comp.get("posting_frequency")
        name = comp.get("name") or cid

        if new_post and old_post and new_post != old_post:
            changes.append({
                "competitor": name,
                "change_type": "new_post",
                "what_changed": "new_instagram_post",
                "from": old_post,
                "to": new_post,
                "date": today,
                "threat_level": comp.get("threat", "medium"),
                "opportunity_level": "medium",
                "detail": f"Latest IG post moved from {old_post} to {new_post}.",
                "response": "Review their angle and counter with your pillar content this week.",
                "source": "competitor_tracker_job",
            })
        elif old_freq and new_freq and old_freq != new_freq:
            changes.append({
                "competitor": name,
                "change_type": "posting_frequency",
                "what_changed": "posting_frequency_shift",
                "from": old_freq,
                "to": new_freq,
                "date": today,
                "threat_level": "medium" if new_freq in ("daily", "3x/week") else "low",
                "opportunity_level": "high" if new_freq in ("infrequent", "unknown") else "medium",
                "detail": f"Posting cadence shifted {old_freq} → {new_freq}.",
                "response": (
                    "Increase IG cadence if they stepped up; own educational angle if they went quiet."
                ),
                "source": "competitor_tracker_job",
            })
        elif not old.get("last_fetch_ok") and comp.get("last_fetch_ok"):
            changes.append({
                "competitor": name,
                "change_type": "social_feed_live",
                "what_changed": "instagram_feed_now_tracked",
                "date": today,
                "threat_level": comp.get("threat", "low"),
                "opportunity_level": "medium",
                "detail": "Instagram feed is now tracked live via Graph API.",
                "source": "competitor_tracker_job",
            })

    # Keep recent manual changes (max 20 total)
    prev_changes = [
        c for c in as_list(prev.get("changes"))
        if isinstance(c, dict) and c.get("source") != "competitor_tracker_job"
    ]
    merged = changes + prev_changes
    return merged[:20]


def _refresh_competitors(
    competitors: list[dict],
    creds: Optional[dict[str, str]],
) -> tuple[list[dict], int, list[str]]:
    refreshed: list[dict] = []
    fetched = 0
    errors: list[str] = []
    now = utc_now_iso()

    for comp in competitors:
        if not isinstance(comp, dict):
            continue
        row = dict(comp)
        row["last_updated"] = now
        username = _parse_instagram_username(row.get("social"))
        if not username or not creds:
            row["last_fetch_ok"] = False
            if not username:
                row.setdefault("fetch_note", "no instagram handle configured")
            else:
                row.setdefault("fetch_note", "Meta token missing")
            refreshed.append(row)
            continue

        bd, err = _fetch_competitor_ig(creds["ig_id"], creds["token"], username)
        if err or not bd:
            row["last_fetch_ok"] = False
            row["fetch_error"] = (err or "empty business_discovery")[:200]
            refreshed.append(row)
            errors.append(f"{row.get('name', username)}: {row['fetch_error']}")
            continue

        media = as_list(bd.get("media"))
        post_dates: list[str] = []
        recent_posts: list[dict] = []
        for m in media:
            if not isinstance(m, dict):
                continue
            ts = (m.get("timestamp") or "")[:10]
            if ts:
                post_dates.append(m.get("timestamp") or ts)
            recent_posts.append({
                "date": ts,
                "caption_preview": (m.get("caption") or "")[:120],
                "likes": m.get("like_count"),
                "comments": m.get("comments_count"),
                "media_type": m.get("media_type"),
                "permalink": m.get("permalink"),
            })

        freq = _posting_frequency(post_dates)
        followers = int(bd.get("followers_count") or 0)
        last_post = max((d[:10] for d in post_dates if d), default=row.get("last_post"))

        row.update({
            "last_fetch_ok": True,
            "instagram_username": bd.get("username") or username,
            "followers_count": followers,
            "media_count": int(bd.get("media_count") or len(media)),
            "posting_frequency": freq,
            "last_post": last_post,
            "threat": _infer_threat(freq, followers),
            "recent_posts": recent_posts[:5],
            "fetch_error": None,
        })
        fetched += 1
        refreshed.append(row)

    return refreshed, fetched, errors


def run(*, brand: str | None = None) -> dict:
    """Refresh competitor social signals and write competitor-tracker.json."""
    io = io_for_job(JOB_NAME, brand)
    prev = as_dict(io.read(OUTPUT))
    competitors = as_list(prev.get("competitors"))
    if not competitors:
        seed_path = repo_root() / "data" / OUTPUT
        if seed_path.is_file():
            prev = as_dict(json.loads(seed_path.read_text(encoding="utf-8")))
            competitors = as_list(prev.get("competitors"))

    if not competitors:
        return {"ok": False, "error": "no competitors configured in competitor-tracker.json"}

    creds = _load_meta_creds()
    updated_comps, fetched, errors = _refresh_competitors(competitors, creds)
    changes = _build_changes(prev, {"competitors": updated_comps})

    active_threats = sum(
        1 for c in updated_comps
        if c.get("threat") == "high" and c.get("last_fetch_ok")
    )
    top_threat = next(
        (f"{c.get('name')} — {c.get('posting_frequency')} posting" for c in updated_comps
         if c.get("threat") == "high"),
        None,
    )

    payload = {
        "schema": prev.get("schema") or "https://clawdia.io/agents/competitor-tracker/v1",
        "generated": utc_now_iso(),
        "summary": {
            "total_competitors": len(updated_comps),
            "active_threats": active_threats,
            "total_changes": len(changes),
            "top_threat": top_threat or prev.get("summary", {}).get("top_threat"),
            "instagram_profiles_fetched": fetched,
        },
        "competitors": updated_comps,
        "changes": changes,
    }
    io.write(OUTPUT, payload)

    if fetched == 0 and errors and not creds:
        return {"ok": False, "error": errors[0] if errors else "Meta token missing", "rows": 0}
    return {"ok": True, "rows": fetched, "changes": len(changes), "warnings": errors[:3]}
