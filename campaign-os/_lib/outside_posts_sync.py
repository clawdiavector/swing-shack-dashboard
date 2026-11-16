"""Sync live Meta + Postiz posts; unmatched ones land on the Plan calendar (T9).

Matching order (spec): Postiz id first, then published time (±30 min) and caption.
Stories are first-class posts (date, brand, image, link).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass, field
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
    platform: str  # instagram | facebook | postiz
    kind: str  # feed | reel | story
    external_id: str
    published_at: str  # ISO-8601
    caption: str
    permalink: str
    thumbnail_url: str
    postiz_post_id: str | None = None
    target: str = ""  # postiz only: where it went (instagram | facebook | tiktok | gbp | ...)


@dataclass
class MatchIndex:
    postiz_ids: set[str]
    media_ids: set[str]
    timed_captions: list[tuple[dt.datetime, str]]
    permalinks: set[str] = field(default_factory=set)
    # Stories Postiz sent, by time and platform: Meta gives a story no caption to match on.
    postiz_stories: list[tuple[dt.datetime, str]] = field(default_factory=list)


# Postiz sends that count on the calendar. Google posts come from the approve-once
# queue, which the calendar already shows; YouTube has no slot.
POSTIZ_COUNTED_TARGETS = ("instagram", "facebook", "tiktok")
_POSTIZ_TARGETS = (("instagram", "instagram"), ("facebook", "facebook"), ("tiktok", "tiktok"),
                   ("gmb", "gbp"), ("google", "gbp"), ("youtube", "youtube"))


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


def _norm_link(url: str) -> str:
    return (url or "").strip().split("?", 1)[0].rstrip("/").lower()


def add_postiz_observations(index: MatchIndex, observed: Iterable[ObservedPost]) -> None:
    """Fold live Postiz read-back into the match index (verify C1).

    Before, Postiz observations were fetched and dropped, so a Meta post whose
    Postiz id never reached the local index matched only by caption and time.
    Now its id, release link and caption+time all count.
    """
    for obs in observed:
        if obs.platform != "postiz":
            continue
        if obs.postiz_post_id:
            index.postiz_ids.add(str(obs.postiz_post_id))
        link = _norm_link(obs.permalink)
        if link:
            index.permalinks.add(link)
        when = _parse_ts(obs.published_at)
        cap = normalize_caption(obs.caption)
        if when and cap:
            index.timed_captions.append((when, cap))
        if when and obs.kind == "story" and obs.target:
            index.postiz_stories.append((when, obs.target))


def matches_campaign_os(obs: ObservedPost, index: MatchIndex) -> bool:
    if obs.postiz_post_id and str(obs.postiz_post_id) in index.postiz_ids:
        return True
    if obs.external_id and str(obs.external_id) in index.media_ids:
        return True
    if obs.permalink and _norm_link(obs.permalink) in index.permalinks:
        return True
    when = _parse_ts(obs.published_at)
    cap = normalize_caption(obs.caption)
    window = dt.timedelta(minutes=MATCH_WINDOW_MINUTES)
    if when and obs.kind == "story" and not cap:
        if any(target == obs.platform and abs(when - other) <= window for other, target in index.postiz_stories):
            return True
    if not when or not cap:
        return False
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
        title = "Facebook story" if obs.kind == "story" and not obs.caption else (title or "Facebook post")
    if obs.platform == "tiktok" and not obs.caption:
        title = "TikTok"
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


def _fb_page_and_token(brand_id: str) -> tuple[str, str]:
    from _lib.meta_api import load_brand_integration, resolve_credentials_for_brand

    cfg = load_brand_integration(brand_id)
    page_id = str(cfg.get("facebook_page_id") or cfg.get("page_id") or "")
    creds = resolve_credentials_for_brand(brand_id, cfg)
    return page_id, str(creds.get("token") or "")


def _fb_get(page_id: str, edge: str, fields: str, token: str) -> list[dict[str, Any]]:
    """GET /{page_id}/{edge}. The token goes in the Authorization header, never the
    URL, so an exception or proxy log can't carry it (verify C5)."""
    import urllib.parse
    import urllib.request

    url = (
        f"https://graph.facebook.com/v19.0/{page_id}/{edge}?"
        f"fields={urllib.parse.quote(fields)}&limit=30"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode())
    except Exception:
        return []
    return list(body.get("data") or [])


def _fb_post_rows(brand_id: str) -> list[dict[str, Any]]:
    page_id, token = _fb_page_and_token(brand_id)
    if not page_id or not token:
        return []
    return _fb_get(page_id, "posts", "id,message,created_time,permalink_url,full_picture", token)


def _fb_story_rows(brand_id: str) -> list[dict[str, Any]]:
    """Facebook Page stories (verify C4). Pages without the edge return []."""
    page_id, token = _fb_page_and_token(brand_id)
    if not page_id or not token:
        return []
    return _fb_get(page_id, "stories", "post_id,status,creation_time,media_type,media_id,url", token)


def _postiz_rows(brand_id: str, since: dt.date, until: dt.date) -> list[dict[str, Any]]:
    from _lib import postiz_client as pz

    integrations, err = pz.list_integrations(brand_id=brand_id)
    if err or not integrations:
        return []
    items = integrations if isinstance(integrations, list) else (
        (integrations or {}).get("integrations") or (integrations or {}).get("identities") or []
    )
    out: list[dict[str, Any]] = []
    # Same window format as the Plan calendar's Postiz read (app._clean_cal_postiz_rows).
    start = since.isoformat() + "T00:00:00.000Z"
    end = until.isoformat() + "T23:59:59.000Z"
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
            brand_id=brand_id,
        )
        if perr or not posts:
            continue
        rows = posts if isinstance(posts, list) else (posts or {}).get("posts") or (posts or {}).get("data") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            state = str(row.get("state") or row.get("status") or "PUBLISHED").upper()
            if state != "PUBLISHED":
                continue
            out.append({**row, "_postiz_integration_id": iid,
                        "_postiz_provider": str(ig.get("providerIdentifier") or ig.get("identifier") or "")})
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


def _observed_from_fb_story(row: dict[str, Any]) -> ObservedPost:
    created = row.get("creation_time") or row.get("created_time") or ""
    if isinstance(created, (int, float)):
        created = dt.datetime.fromtimestamp(created, dt.timezone.utc).isoformat()
    return ObservedPost(
        platform="facebook",
        kind="story",
        external_id=str(row.get("post_id") or row.get("media_id") or row.get("id") or ""),
        published_at=str(created),
        caption="",
        permalink=str(row.get("url") or ""),
        thumbnail_url="",
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
    # Postiz answers every post for the brand whatever account is asked for, so the
    # post's own account wins over the one it was listed under.
    provider = str(((row.get("integration") or {}).get("providerIdentifier")) or row.get("_postiz_provider") or "")
    target = next((name for needle, name in _POSTIZ_TARGETS if needle in provider.lower()), "")
    settings = row.get("settings") or {}
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except ValueError:
            settings = {}
    post_type = str((settings if isinstance(settings, dict) else {}).get("post_type") or "").lower()
    kind = post_type if post_type in ("story", "reel") else "feed"
    return ObservedPost(
        platform="postiz",
        kind=kind,
        external_id=pid,
        published_at=str(when),
        caption=re.sub(r"<[^>]+>", " ", str(content or "")).strip(),
        permalink=str(link or ""),
        thumbnail_url="",
        postiz_post_id=pid,
        target=target,
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
    for row in _fb_story_rows(brand_id):
        if str(row.get("status") or "PUBLISHED").upper() != "PUBLISHED":
            continue
        add(_observed_from_fb_story(row))
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
    # A Postiz send Campaign OS did not make is a post in its own right (a story queued
    # straight in Postiz, a TikTok). Decide before Postiz ids join the index, or all would match.
    postiz_sends = [
        obs for obs in observed
        if obs.platform == "postiz" and obs.target in POSTIZ_COUNTED_TARGETS
        and not matches_campaign_os(obs, index)
    ]
    add_postiz_observations(index, observed)
    matched = 0
    outside_written = 0
    actions: list[str] = []
    for obs in observed:
        if obs.platform == "postiz":
            if obs in postiz_sends:
                # Written once from Postiz; the same post read back from Meta matches it below.
                obs = ObservedPost(platform=obs.target, kind=obs.kind, external_id=f"postiz-{obs.external_id}",
                                   published_at=obs.published_at, caption=obs.caption,
                                   permalink=obs.permalink, thumbnail_url=obs.thumbnail_url,
                                   postiz_post_id=obs.postiz_post_id)
            else:
                matched += 1
                continue
        elif matches_campaign_os(obs, index):
            matched += 1
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
