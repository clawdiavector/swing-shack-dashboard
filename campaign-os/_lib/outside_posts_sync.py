"""Sync live Meta + Postiz posts; unmatched ones land on the Plan calendar (T9).

Matching order (spec): Postiz id first, then published time (±30 min) and caption.
Stories are first-class posts (date, brand, image, link).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

OUTSIDE_POST_TYPE = "posted-outside-campaign-os"
OUTSIDE_LABEL = "Posted outside Campaign OS"
MATCH_WINDOW_MINUTES = 30
LOOKBACK_DAYS = 14

SAST = ZoneInfo("Africa/Johannesburg")


@dataclass(frozen=True)
class ObservedPost:
    platform: str  # instagram | facebook
    kind: str  # feed | reel | story
    external_id: str
    published_at: str  # ISO-8601
    caption: str
    permalink: str
    thumbnail_url: str
    postiz_post_id: str | None = None


@dataclass
class MatchIndex:
    postiz_ids: set[str]
    media_ids: set[str]
    timed_captions: list[tuple[dt.datetime, str]]


def normalize_caption(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"[^\w\s#@]", "", t)
    return t


def _parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _data_dir() -> Path:
    env = os.environ.get("DATA_DIR")
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return Path("/data/campaign-os")


def _load_meta_index() -> dict[str, Any]:
    from _lib.post_links import _load_index

    return _load_index(_data_dir() / "meta-post-index.json")


def build_match_index(brand_id: str) -> MatchIndex:
    """Campaign OS / Postiz identities we already know about for this brand."""
    postiz_ids: set[str] = set()
    media_ids: set[str] = set()
    timed_captions: list[tuple[dt.datetime, str]] = []

    idx = _load_meta_index()
    for mid, link in (idx.get("by_media_id") or {}).items():
        if str((link or {}).get("brand_id") or brand_id) == brand_id:
            media_ids.add(str(mid))
            pid = (link or {}).get("postiz_post_id")
            if pid:
                postiz_ids.add(str(pid))
    for link in (idx.get("by_asset_id") or {}).values():
        if not isinstance(link, dict):
            continue
        if str(link.get("brand_id") or brand_id) != brand_id:
            continue
        pid = link.get("postiz_post_id")
        if pid:
            postiz_ids.add(str(pid))
        mid = link.get("platform_media_id")
        if mid:
            media_ids.add(str(mid))

    from _lib.marketing_calendar import list_records, latest_revisions

    for rec in latest_revisions(list_records(brand_id) or []):
        if str(rec.get("post_type") or "") == OUTSIDE_POST_TYPE:
            continue
        pz = rec.get("postiz")
        if isinstance(pz, list):
            for row in pz:
                if isinstance(row, dict):
                    pid = row.get("postId") or row.get("id")
                    if pid:
                        postiz_ids.add(str(pid))
        elif isinstance(pz, dict):
            pid = pz.get("postId") or pz.get("id")
            if pid:
                postiz_ids.add(str(pid))
        for key in ("postiz_post_id", "platform_media_id", "ig_media_id"):
            val = rec.get(key)
            if val:
                if key == "postiz_post_id":
                    postiz_ids.add(str(val))
                else:
                    media_ids.add(str(val))
        when = _parse_ts(rec.get("publish_at") or rec.get("published_at"))
        if not when:
            day = (rec.get("event_start") or rec.get("event_date") or "")[:10]
            if day:
                when = dt.datetime.fromisoformat(day).replace(tzinfo=SAST).astimezone(dt.timezone.utc)
        cap = normalize_caption(str(rec.get("caption") or rec.get("title") or ""))
        if when and cap:
            timed_captions.append((when, cap))

    return MatchIndex(postiz_ids=postiz_ids, media_ids=media_ids, timed_captions=timed_captions)


def matches_campaign_os(obs: ObservedPost, index: MatchIndex) -> bool:
    if obs.postiz_post_id and str(obs.postiz_post_id) in index.postiz_ids:
        return True
    if obs.external_id and str(obs.external_id) in index.media_ids:
        return True
    when = _parse_ts(obs.published_at)
    cap = normalize_caption(obs.caption)
    if not when or not cap:
        return False
    window = dt.timedelta(minutes=MATCH_WINDOW_MINUTES)
    for other_when, other_cap in index.timed_captions:
        if other_cap != cap:
            continue
        if abs(when - other_when) <= window:
            return True
    return False


def _event_key(brand_id: str, obs: ObservedPost) -> str:
    return f"{brand_id}:outside-{obs.platform}-{obs.kind}-{obs.external_id}"


def _local_day(iso_ts: str) -> str:
    when = _parse_ts(iso_ts)
    if not when:
        return dt.datetime.now(SAST).date().isoformat()
    return when.astimezone(SAST).date().isoformat()


def upsert_outside_calendar_item(brand_id: str, obs: ObservedPost) -> dict[str, Any]:
    from _lib import marketing_calendar as mc

    day = _local_day(obs.published_at)
    title = (obs.caption.split("\n", 1)[0] if obs.caption else "").strip()
    if not title:
        title = {"story": "Instagram story", "reel": "Instagram reel", "feed": "Instagram post"}.get(
            obs.kind, "Outside post"
        )
    if obs.platform == "facebook":
        title = title or "Facebook post"
    record = {
        "event_key": _event_key(brand_id, obs),
        "brand_id": brand_id,
        "type": "moment",
        "status": "approved",
        "title": title[:200],
        "event_date": day,
        "event_start": day,
        "event_end": day,
        "source_origin": "external",
        "source_type": "outside_posts_sync",
        "created_by": "outside_posts_sync",
        "post_type": OUTSIDE_POST_TYPE,
        "postiz_mode": "posted",
        "lane": "human",
        "channel": obs.platform,
        "primary_channel": obs.platform,
        "media_kind": obs.kind,
        "caption": (obs.caption or "")[:500],
        "permalink": obs.permalink or None,
        "thumbnail_url": obs.thumbnail_url or None,
        "platform_media_id": obs.external_id,
        "outside_label": OUTSIDE_LABEL,
        "verification_status": "verified_external_publish",
    }
    upsert = getattr(mc, "upsert_event", None)
    if upsert is None:
        raise RuntimeError("marketing_calendar.upsert_event missing")
    return upsert(brand_id, record, skip_guards=True)


def _ig_media_rows(brand_id: str) -> list[dict[str, Any]]:
    from _lib.meta_api import list_recent_posts_for_brand

    resp = list_recent_posts_for_brand(brand_id, limit=50)
    return list(resp.get("data") or [])


def _ig_story_rows(brand_id: str) -> list[dict[str, Any]]:
    from _lib.meta_api import get_ig_stories

    resp = get_ig_stories(limit=50, with_insights=False, brand_id=brand_id)
    return list(resp.get("data") or [])


def _fb_post_rows(brand_id: str) -> list[dict[str, Any]]:
    from _lib.meta_api import load_brand_integration, resolve_credentials_for_brand

    cfg = load_brand_integration(brand_id)
    page_id = cfg.get("facebook_page_id") or cfg.get("page_id")
    creds = resolve_credentials_for_brand(brand_id, cfg)
    token = creds.get("token")
    if not page_id or not token:
        return []
    import urllib.parse
    import urllib.request

    fields = "id,message,created_time,permalink_url,full_picture"
    url = (
        f"https://graph.facebook.com/v19.0/{page_id}/posts?"
        f"fields={urllib.parse.quote(fields)}&limit=30&access_token={urllib.parse.quote(token)}"
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            body = json.loads(resp.read().decode())
    except Exception:
        return []
    return list(body.get("data") or [])


def _postiz_rows(brand_id: str, since: dt.date, until: dt.date) -> list[dict[str, Any]]:
    from _lib import postiz_client as pz

    integrations, err = pz.list_integrations(brand_id=brand_id)
    if err or not integrations:
        return []
    items = integrations if isinstance(integrations, list) else (
        (integrations or {}).get("integrations") or (integrations or {}).get("identities") or []
    )
    out: list[dict[str, Any]] = []
    start = since.isoformat()
    end = until.isoformat()
    for ig in items:
        if not isinstance(ig, dict) or ig.get("disabled"):
            continue
        iid = ig.get("id")
        if not iid:
            continue
        posts, perr = pz.list_posts(
            str(iid),
            start_date=start,
            end_date=end,
            state="PUBLISHED",
            limit=50,
        )
        if perr or not posts:
            continue
        rows = posts if isinstance(posts, list) else (posts or {}).get("posts") or (posts or {}).get("data") or []
        for row in rows:
            if isinstance(row, dict):
                row = {**row, "_postiz_integration_id": iid}
                out.append(row)
    return out


def _observed_from_ig_media(row: dict[str, Any]) -> ObservedPost:
    mtype = str(row.get("media_type") or "IMAGE").upper()
    product = str(row.get("media_product_type") or "").upper()
    kind = "reel" if mtype == "VIDEO" or product == "REELS" else "feed"
    return ObservedPost(
        platform="instagram",
        kind=kind,
        external_id=str(row.get("id") or ""),
        published_at=str(row.get("timestamp") or ""),
        caption=str(row.get("caption") or ""),
        permalink=str(row.get("permalink") or ""),
        thumbnail_url=str(row.get("thumbnail_url") or row.get("media_url") or ""),
        postiz_post_id=None,
    )


def _observed_from_ig_story(row: dict[str, Any]) -> ObservedPost:
    return ObservedPost(
        platform="instagram",
        kind="story",
        external_id=str(row.get("id") or ""),
        published_at=str(row.get("timestamp") or ""),
        caption="",
        permalink=str(row.get("permalink") or ""),
        thumbnail_url=str(row.get("media_url") or row.get("thumbnail_url") or ""),
        postiz_post_id=None,
    )


def _observed_from_fb(row: dict[str, Any]) -> ObservedPost:
    return ObservedPost(
        platform="facebook",
        kind="feed",
        external_id=str(row.get("id") or ""),
        published_at=str(row.get("created_time") or ""),
        caption=str(row.get("message") or ""),
        permalink=str(row.get("permalink_url") or ""),
        thumbnail_url=str(row.get("full_picture") or ""),
        postiz_post_id=None,
    )


def _observed_from_postiz(row: dict[str, Any]) -> ObservedPost | None:
    pid = str(row.get("postId") or row.get("id") or "")
    if not pid:
        return None
    content = row.get("content") or row.get("description") or ""
    if isinstance(content, list):
        content = " ".join(str(x) for x in content)
    when = row.get("publishDate") or row.get("publishedAt") or row.get("createdAt") or ""
    link = row.get("releaseURL") or row.get("releaseUrl") or row.get("permalink") or ""
    return ObservedPost(
        platform="postiz",
        kind="feed",
        external_id=pid,
        published_at=str(when),
        caption=str(content or ""),
        permalink=str(link or ""),
        thumbnail_url="",
        postiz_post_id=pid,
    )


def fetch_observed_posts(brand_id: str, *, now: dt.datetime | None = None) -> list[ObservedPost]:
    """Live Meta + Postiz read-back. Raises on hard Meta auth failures."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=LOOKBACK_DAYS)
    seen: set[tuple[str, str, str]] = set()
    out: list[ObservedPost] = []

    def add(obs: ObservedPost) -> None:
        if not obs.external_id:
            return
        when = _parse_ts(obs.published_at)
        if when and when < cutoff:
            return
        key = (obs.platform, obs.kind, obs.external_id)
        if key in seen:
            return
        seen.add(key)
        out.append(obs)

    for row in _ig_media_rows(brand_id):
        add(_observed_from_ig_media(row))
    for row in _ig_story_rows(brand_id):
        add(_observed_from_ig_story(row))
    for row in _fb_post_rows(brand_id):
        add(_observed_from_fb(row))
    until = now.astimezone(SAST).date()
    since = (now - dt.timedelta(days=LOOKBACK_DAYS)).astimezone(SAST).date()
    for row in _postiz_rows(brand_id, since, until):
        obs = _observed_from_postiz(row)
        if obs:
            add(obs)
    return out


def sync_brand(brand_id: str, *, fetch_live: bool = True) -> dict[str, Any]:
    try:
        observed = fetch_observed_posts(brand_id) if fetch_live else []
    except Exception as exc:
        return {"ok": False, "brand_id": brand_id, "error": str(exc)[:300]}
    index = build_match_index(brand_id)
    matched = 0
    outside_written = 0
    actions: list[str] = []
    for obs in observed:
        if matches_campaign_os(obs, index):
            matched += 1
            continue
        if obs.platform == "postiz":
            continue
        result = upsert_outside_calendar_item(brand_id, obs)
        actions.append(str(result.get("action") or "unknown"))
        if result.get("action") in ("created", "updated"):
            outside_written += 1
    return {
        "ok": True,
        "brand_id": brand_id,
        "observed": len(observed),
        "matched": matched,
        "outside_written": outside_written,
        "actions_sample": actions[:5],
    }


def run(*, brand: str | None = None) -> dict[str, Any]:
    if not brand:
        return {"ok": False, "error": "brand required"}
    return sync_brand(brand, fetch_live=True)
