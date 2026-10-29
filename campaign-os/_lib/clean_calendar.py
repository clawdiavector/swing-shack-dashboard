"""The clean calendar: three views anyone can read, and a no-login link for Herman.

Christelle's ask (2026-10-29): one view for what is scheduled, one for what
needs a yes, one for ideas. Every entry says in plain words what it is, why it
is there, where and when it goes, and shows the real image. She shares a link;
Herman opens it without logging in and approves, comments or rejects.

Approving here goes through the same paths as the rest of the app:
  - a ready post: unified_inbox.approve_item (it is then scheduled to send)
  - an idea: the calendar-suggestions approve, then the post-making jobs
This module only reads, words and renders; app.py does the approving.
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SHARE_SCOPE = "calendar_share"
SHARE_MAX_AGE = 14 * 24 * 60 * 60

BRAND_NAMES = {"swing-shack": "Swing Shack", "stick": "Stick", "bag-drop": "Bag Drop"}

_SCHEDULED = frozenset({"scheduled", "released", "posted", "partly_posted", "send_failed"})
# Gone out, or going: the day is history and cannot be dragged.
_SENT = frozenset({"released", "posted", "partly_posted", "send_failed"})
_MAKING = frozenset({"booked", "drafting", "needs_fix", "gap"})

_CHANNEL_NAMES = {
    "instagram": "Instagram", "facebook": "Facebook", "gbp": "Google",
    "tiktok": "TikTok", "linkedin": "LinkedIn", "twitter": "X",
}

_STATUS = {
    "draft_ready": "Waiting for a yes",
    "released": "Sending now",
    "posted": "Posted",
    "partly_posted": "Posted on some channels only",
    "send_failed": "Did not send. Christelle is checking it.",
}
_MAKING_STATUS = "Being made. It comes back here for a yes."

# What a post is, from its template or post type. First match wins.
_WHAT = (
    ("story", "An Instagram story"),
    ("product", "A post showing a product we sell"),
    ("fitting", "A post about club fitting"),
    ("coach", "A post about coaching"),
    ("lesson", "A post about coaching"),
    ("price", "A post with our prices"),
    ("offer", "A post with an offer"),
    ("sale", "A post with an offer"),
    ("discount", "A post with an offer"),
    ("service", "A post about one of our services"),
    ("venue", "A post about the venue"),
    ("location", "A post about the venue"),
    ("did-you-know", "A golf tip"),
)

_IDEA_WHAT = {
    "stock": "Idea: a post about a product on this week's stock list",
    "date": "Idea: a post for this date",
}
IDEA_NEXT = "Approve it and the post gets made. It then comes back under Needs your OK for a final yes."


def _brand(brand_id: str) -> str:
    if brand_id not in BRAND_NAMES:
        raise ValueError(f"'{brand_id}' is not one of our brands")
    return brand_id


# ── share links ─────────────────────────────────────────────────────────────


def mint_share_token(serializer: Any, brand_id: str, who: str = "Herman", plan_id: str | None = None) -> str:
    """A signed link for one brand's calendar, or one campaign's timeline when
    `plan_id` is given, named for the person it is for."""
    who = (who or "").strip()[:40] or "Herman"
    payload = {"scope": SHARE_SCOPE, "brand": _brand(brand_id), "who": who, "v": 1}
    if plan_id:
        payload["plan"] = plan_id
    return serializer.dumps(payload)


def read_share_token(serializer: Any, token: str, *, max_age: int = SHARE_MAX_AGE) -> dict[str, str] | None:
    """{"brand", "who"} (and "plan" for a campaign link) for a good link; None for anything else."""
    from itsdangerous import BadSignature, SignatureExpired

    if not token:
        return None
    try:
        payload = serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict) or payload.get("scope") != SHARE_SCOPE:
        return None
    brand = payload.get("brand")
    if brand not in BRAND_NAMES:
        return None
    out = {"brand": brand, "who": str(payload.get("who") or "Herman")}
    if payload.get("plan"):
        out["plan"] = str(payload["plan"])
    return out


# ── wording ─────────────────────────────────────────────────────────────────


def bucket_for_state(state: str) -> str | None:
    if state in _SCHEDULED:
        return "scheduled"
    if state == "draft_ready":
        return "approval"
    if state in _MAKING:
        return "making"
    return None


def _when(iso: str | None) -> str:
    try:
        d = date.fromisoformat(str(iso or "")[:10])
    except ValueError:
        return "No date yet"
    return f"{d:%a} {d.day} {d:%b}"


def _format(post_type: Any) -> str:
    """story, reel or feed, from a post type or template name (for the daily target)."""
    t = str(post_type or "").lower()
    if "story" in t:
        return "story"
    if "reel" in t or "video" in t:
        return "reel"
    return "feed"


def _where(channels: list[str] | None) -> str:
    names = [_CHANNEL_NAMES.get(c, c.title()) for c in (channels or []) if c]
    if not names:
        return "Instagram"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _what(post_type: str | None) -> str:
    t = str(post_type or "").lower()
    for needle, words in _WHAT:
        if needle in t:
            return words
    return "A feed post"


OUTSIDE_POST_TYPE = "posted-outside-campaign-os"
_POSTIZ_STATUS = {"schedule": "Scheduled in Postiz", "posted": "Posted from Postiz",
                  "draft": "Draft in Postiz. Approve to schedule it."}

# Plan steps that are work, not posts: they go on the To do list.
_TASK_WHAT = {
    "research": "Planning: research", "decide": "Planning: a decision", "shoot": "A shoot",
    "edit": "Editing", "review": "A review", "boost": "A paid boost",
}
_PHASE = {"research": "Planning", "decide": "Planning", "shoot": "Shoot", "edit": "Edit and review",
          "review": "Edit and review", "post": "Posts", "story": "Posts", "boost": "Boost"}


def sast_today() -> date:
    return datetime.now(ZoneInfo("Africa/Johannesburg")).date()


def post_entry(row: dict[str, Any], brand_id: str, *, caption: str = "",
               comments: list[dict[str, Any]] | None = None, today: date | None = None) -> dict[str, Any]:
    """One calendar post (or plan step) in words Herman can read cold. With
    `today`, a past day that is still unmade reads as missed (or overdue)."""
    day = str(row.get("go_live_date") or "")[:10]
    past = today is not None and bool(day) and day < today.isoformat()
    state = str(row.get("state") or "")
    bucket = bucket_for_state(state)
    making = bucket == "making"
    view = "approval" if making else (bucket or "scheduled")
    kind, link = "post", ""
    actions = ["approve", "comment", "reject"] if state == "draft_ready" else ["comment"]
    if state == "scheduled":
        status = f"Goes out {_when(row.get('go_live_date'))}"
    else:
        status = _MAKING_STATUS if making else _STATUS.get(state, state.replace("_", " ").capitalize())
    what = _what(row.get("post_type") or row.get("template_id"))
    has_image = bool(row.get("image_url") or row.get("image_path"))
    step = str(row.get("plan_item_kind") or "")
    postiz_mode = str(row.get("postiz_mode") or "")
    # Records that are not a post Campaign OS is making: label them for what they are.
    if row.get("post_type") == OUTSIDE_POST_TYPE:
        view, making, status = "scheduled", False, "Posted outside Campaign OS"
        link = str(row.get("permalink") or "")
        has_image = has_image or bool(row.get("thumbnail_url"))
    elif postiz_mode in _POSTIZ_STATUS and state not in _SCHEDULED:
        making, status = False, _POSTIZ_STATUS[postiz_mode]
        view = "approval" if postiz_mode == "draft" else "scheduled"
        if postiz_mode == "draft" and row.get("postiz_post_id"):
            actions = ["approve", "comment", "reject"]
    elif step in _TASK_WHAT:
        kind, view, making, actions = "task", "todo", False, ["comment"]
        what = _TASK_WHAT[step]
        if state in _SCHEDULED:
            status = "Done"
        else:
            status = f"{'Overdue since' if past else 'Due'} {_when(row.get('go_live_date'))}"
    # Its day has gone and nothing was made: missed, not still in progress.
    missed = making and past
    if missed:
        making, status = False, "Missed. It was never made."
    channels = row.get("channels_picked") or ([row["primary_channel"]] if row.get("primary_channel") else [])
    return {
        "key": str(row.get("calendar_id") or ""),
        "kind": kind,
        "view": view,
        "making": making,
        "missed": missed,
        "movable": state not in _SENT and row.get("post_type") != OUTSIDE_POST_TYPE,
        "state": state,
        "date": str(row.get("go_live_date") or "")[:10],
        "when": _when(row.get("go_live_date")),
        "where": _where(channels),
        "channels": [str(c).lower() for c in channels if c] or ["instagram"],
        "format": _format(row.get("post_type") or row.get("template_id")),
        "brand_name": BRAND_NAMES.get(brand_id, brand_id),
        "title": str(row.get("title") or "Untitled post"),
        "what": what,
        "why": str(row.get("angle") or "").strip(),
        "caption": caption or "",
        "status": status,
        "has_image": has_image,
        "link": link,
        "plan_id": str(row.get("plan_id") or ""),
        "actions": actions,
        "comments": list(comments or []),
    }


def idea_entry(item: dict[str, Any], brand_id: str, *,
               comments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One suggestion from the month grid, as an idea to approve or turn down."""
    return {
        "key": str(item.get("key") or ""),
        "kind": "idea",
        "view": "ideas",
        "making": False,
        "state": "idea",
        "date": str(item.get("date") or "")[:10],
        "when": _when(item.get("date")),
        "where": "Instagram",
        "brand_name": BRAND_NAMES.get(brand_id, brand_id),
        "title": str(item.get("title") or "Untitled idea"),
        "what": _IDEA_WHAT.get(str(item.get("source") or ""), "Idea: a post for this moment"),
        "why": str(item.get("why") or "").strip(),
        "caption": "",
        "status": "Idea. Not made yet.",
        "next": IDEA_NEXT,
        "movable": False,
        "has_image": False,
        "image": None,
        "actions": ["approve", "comment", "reject"],
        "comments": list(comments or []),
    }


# ── the month ───────────────────────────────────────────────────────────────


def month_bounds(month: str) -> tuple[date, date]:
    try:
        y, m = (int(p) for p in month.split("-", 1))
        first = date(y, m, 1)
    except (ValueError, AttributeError):
        raise ValueError("month must look like 2026-11") from None
    last = date(y + (m == 12), m % 12 + 1, 1)
    return first, date.fromordinal(last.toordinal() - 1)


def post_rows(brand_id: str, month: str) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """(row, draft) for every dated post in the month, the same rows This week uses."""
    from _lib import unified_inbox as ui  # noqa: PLC0415
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    first, last = month_bounds(month)
    index = ui.build_post_index(brand_id=brand_id)
    now = datetime.now(timezone.utc)
    out = []
    for record in canonical_records(brand_id):
        if str(record.get("status") or "") not in ui._WEEK_MOMENT_STATUSES:
            continue
        go_live = ui._moment_go_live_date(record)
        try:
            d = date.fromisoformat(str(go_live or ""))
        except ValueError:
            continue
        if not first <= d <= last:
            continue
        row = _with_record_fields(ui._post_row_from_record(record, index=index, now=now), record)
        if "holiday" in (row.get("flags") or []) or bucket_for_state(str(row.get("state") or "")) is None:
            continue
        out.append((row, index.drafts.get(str(row.get("calendar_id") or ""))))
    return dedupe_rows(out)


# Record fields the row builder drops but the wording needs (outside posts,
# Postiz videos, plan steps).
_RECORD_FIELDS = ("postiz_mode", "postiz_post_id", "plan_item_kind", "plan_id", "thumbnail_url", "permalink")


def _with_record_fields(row: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    for k in _RECORD_FIELDS:
        if record.get(k) and not row.get(k):
            row[k] = record[k]
    return row


# How far along a post is; the higher one wins when a post is on the calendar twice.
_PROGRESS = {"booked": 1, "drafting": 2, "gap": 2, "needs_fix": 3, "draft_ready": 4, "scheduled": 5,
             "released": 6, "partly_posted": 6, "send_failed": 6, "posted": 7}


def dedupe_rows(rows: list[tuple[dict[str, Any], Any]]) -> list[tuple[dict[str, Any], Any]]:
    """One entry per post. Approving a suggestion leaves its own record and a
    booked event beside it, same title and day; keep the one furthest along."""
    best: dict[tuple[str, str], int] = {}
    out: list[tuple[dict[str, Any], Any]] = []
    for pair in rows:
        row = pair[0]
        key = (" ".join(str(row.get("title") or "").lower().split()), str(row.get("go_live_date") or ""))
        if key not in best:
            best[key] = len(out)
            out.append(pair)
        elif _PROGRESS.get(str(row.get("state")), 0) > _PROGRESS.get(str(out[best[key]][0].get("state")), 0):
            out[best[key]] = pair
    return out


def find_post(brand_id: str, key: str) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
    """The row and draft for one calendar id, whatever its month."""
    return find_posts(brand_id, {key}).get(key) if key else None


def find_posts(brand_id: str, keys: set[str]) -> dict[str, tuple[dict[str, Any], dict[str, Any] | None]]:
    """Rows and drafts for several calendar ids, reading the post index once."""
    from _lib import unified_inbox as ui  # noqa: PLC0415
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    keys = {k for k in keys if k}
    if not keys:
        return {}
    index = ui.build_post_index(brand_id=brand_id)
    now = datetime.now(timezone.utc)
    out = {}
    for record in canonical_records(brand_id):
        key = str(record.get("calendar_id") or record.get("event_key") or "")
        if key in keys and key not in out:
            row = ui._post_row_from_record(record, index=index, now=now)
            out[key] = (_with_record_fields(row, record), index.drafts.get(key))
    return out


def count_views(entries: list[dict[str, Any]]) -> dict[str, int]:
    """The numbers on the four boxes: things to look at, not ones still being
    made or already missed."""
    counts = {"scheduled": 0, "approval": 0, "ideas": 0, "todo": 0}
    for e in entries:
        if not e["making"] and not e.get("missed"):
            counts[e["view"]] += 1
    return counts


def month_view(brand_id: str, month: str, ideas: list[dict[str, Any]],
               extras: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The month for the three views plus To do. `extras` are entries built
    elsewhere: Postiz-only posts, Google Business posts, draft plan steps."""
    _brand(brand_id)
    first, _ = month_bounds(month)
    notes = comments_by_key(brand_id)
    today = sast_today()
    entries = [
        post_entry(row, brand_id, caption=str((draft or {}).get("caption") or ""), today=today,
                   comments=notes.get(str(row.get("calendar_id") or "")))
        for row, draft in post_rows(brand_id, month)
    ]
    for e in entries:
        e["image"] = f"/api/clean-calendar/{brand_id}/image/{e['key']}" if e["has_image"] else None
    entries += [idea_entry(i, brand_id, comments=notes.get(str(i.get("key") or ""))) for i in ideas]
    for e in extras or []:
        e["comments"] = notes.get(e["key"], [])
        entries.append(e)
    entries.sort(key=lambda e: (e["date"], e["view"], e["title"]))
    counts = count_views(entries)
    from _lib import daily_target  # noqa: PLC0415

    split = daily_target.target_for(brand_id)
    targets = daily_target.day_progress(entries, split, first, month_bounds(month)[1]) if split else {}
    if targets:
        leads = daily_target.day_leads(brand_id, first, month_bounds(month)[1], sum(split.values()))
        for day, t in targets.items():
            t["lead"] = leads[day]
    return {
        "ok": True,
        "brand": brand_id,
        "brand_name": BRAND_NAMES[brand_id],
        "month": f"{first:%Y-%m}",
        "month_label": f"{first:%B %Y}",
        "counts": counts,
        "entries": entries,
        "targets": targets,
    }


def image_target(row: dict[str, Any], draft: dict[str, Any] | None) -> tuple[str, str] | None:
    """("file", path) when the image is a file here, ("app", path) when one of
    the app's own image routes serves it, ("url", url) when it is elsewhere,
    None when there is no image."""
    from _lib import unified_inbox as ui  # noqa: PLC0415

    src = {"image_path": (draft or {}).get("image_path") or row.get("image_path"),
           "image_url": (draft or {}).get("image_url") or row.get("image_url") or row.get("thumbnail_url")}
    path = ui._resolve_image_path(src)
    if path is not None:
        return "file", str(path)
    url = str(src.get("image_url") or "")
    if url.startswith("https://"):
        return "url", url
    if url.startswith("/") and not url.startswith("//"):
        return "app", url.split("?", 1)[0]
    return None


# ── Postiz-only posts ───────────────────────────────────────────────────────
# Stories and drafts made straight in Postiz never become calendar records.
# Published ones are already pulled in by the outside-posts sync (T9), so only
# queued, draft and failed posts are read here.

_SAST = ZoneInfo("Africa/Johannesburg")
_PROVIDERS = (("instagram", "Instagram"), ("facebook", "Facebook"), ("tiktok", "TikTok"),
              ("gmb", "Google"), ("google", "Google"), ("linkedin", "LinkedIn"), ("x", "X"))


def _postiz_day(when: Any) -> date | None:
    try:
        ts = datetime.fromisoformat(str(when or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(_SAST).date()


def postiz_media(row: dict[str, Any]) -> list[dict[str, str]]:
    raw = row.get("image")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = []
    out = []
    for m in raw if isinstance(raw, list) else []:
        if isinstance(m, dict) and m.get("path"):
            out.append({"id": str(m.get("id") or ""), "path": str(m["path"])})
    return out


def _plain(content: Any) -> str:
    text = re.sub(r"(?i)<br\s*/?>|</p>", "\n", str(content or ""))
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def _provider(row: dict[str, Any]) -> str:
    ident = str(((row.get("integration") or {}).get("providerIdentifier")) or "").lower()
    return next((name for needle, name in _PROVIDERS if needle in ident), "Instagram")


def postiz_entries(rows: list[dict[str, Any]], brand_id: str, *, linked_ids: set[str],
                   month: str) -> list[dict[str, Any]]:
    """Postiz posts in the month that Campaign OS has no record of."""
    first, last = month_bounds(month)
    out = []
    for row in rows:
        pid = str(row.get("id") or row.get("postId") or "")
        state = str(row.get("state") or row.get("status") or "").upper()
        day = _postiz_day(row.get("publishDate"))
        if not pid or pid in linked_ids or state == "PUBLISHED" or day is None or not first <= day <= last:
            continue
        caption = _plain(row.get("content"))
        media = postiz_media(row)
        post_type = str((row.get("settings") or {}).get("post_type") or "").lower()
        story = post_type == "story"
        channel = {"Google": "gbp"}.get(_provider(row), _provider(row).lower())
        if state == "DRAFT":
            view, status, actions = "approval", "Draft in Postiz. Approve to schedule it.", ["approve", "comment", "reject"]
        elif state == "ERROR":
            view, status, actions = "approval", "Did not send from Postiz. Christelle is checking it.", ["comment"]
        else:
            view, status, actions = "scheduled", f"Scheduled in Postiz for {_when(day.isoformat())}", ["comment"]
        out.append({
            "key": f"postiz:{pid}", "kind": "postiz", "view": view, "making": False, "state": state.lower(),
            "date": day.isoformat(), "when": _when(day.isoformat()), "where": _provider(row),
            "channels": [channel], "format": _format(post_type),
            "brand_name": BRAND_NAMES.get(brand_id, brand_id),
            "title": (caption.splitlines()[0][:60] if caption else "") or ("Story" if story else "Postiz post"),
            "what": "An Instagram story" if story else "A post made in Postiz",
            "why": "", "caption": caption, "status": status,
            "has_image": bool(media), "image": media[0]["path"] if media else None,
            "link": str(row.get("releaseURL") or ""), "plan_id": "", "actions": actions, "comments": [],
            "movable": state in ("QUEUE", "DRAFT"),
        })
    return out


def schedule_postiz_draft(pz: Any, brand_id: str, row: dict[str, Any]) -> tuple[bool, str]:
    """Approve a Postiz draft: schedule a copy for its date (never sooner than
    five minutes away, postiz_client sees to that), then remove the draft. If
    Postiz refuses the copy, the draft is left exactly as it was."""
    integration = str((row.get("integration") or {}).get("id") or "")
    if not integration:
        return False, "This Postiz post has no channel. Schedule it in Postiz."
    settings = row.get("settings") if isinstance(row.get("settings"), dict) else None
    _, err = pz.create_post(integration, str(row.get("content") or ""), media=postiz_media(row),
                            brand_id=brand_id, publish_date=row.get("publishDate"),
                            platform_settings=settings, draft=False)
    if err:
        return False, f"Postiz did not take it ({err[0]}). The draft is still there."
    _, derr = pz.delete_post(str(row.get("id") or ""), brand_id=brand_id)
    day = _postiz_day(row.get("publishDate"))
    when = _when(day.isoformat()) if day else "its date"
    if derr:
        return True, f"Scheduled in Postiz for {when}. The old draft is still in Postiz; delete it there."
    return True, f"Scheduled in Postiz for {when}."


# ── moving to another day ───────────────────────────────────────────────────


def move_refusal(entry: dict[str, Any], new_day: date, today: date) -> str | None:
    """Why this entry cannot go to `new_day`, in words for Christelle; None when it can."""
    if not entry.get("movable"):
        if entry.get("kind") == "gbp":
            return "Google posts go out one a day in order, so their day cannot be dragged."
        if entry.get("kind") == "idea":
            return "Approve the idea first. Then it has a day you can move."
        if entry.get("state") in _SENT or entry.get("state") == "posted":
            return "This one has already gone out, so its day stays."
        if entry.get("kind") == "task":
            return "Steps in a draft plan move in the plan itself."
        return "This one cannot be moved from here."
    if new_day < today:
        return "That day has passed. Pick today or a day still to come."
    return None


def move_postiz_post(pz: Any, brand_id: str, row: dict[str, Any], new_day: date) -> tuple[bool, str]:
    """Move a Postiz post to `new_day` at the same time of day (SAST), never
    sooner than five minutes from now. If Postiz refuses, nothing changed."""
    old = _postiz_day(row.get("publishDate"))
    try:
        ts = datetime.fromisoformat(str(row.get("publishDate") or "").replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        clock = ts.astimezone(_SAST).timetz().replace(tzinfo=None)
    except ValueError:
        clock = datetime(2000, 1, 1, 9, 0).time()
    target = datetime.combine(new_day, clock, tzinfo=_SAST).astimezone(timezone.utc)
    when, _ = pz.scheduled_at_least(target.isoformat().replace("+00:00", "Z"))
    _, err = pz.reschedule_post(str(row.get("id") or ""), when, brand_id=brand_id)
    if err:
        still = _when(old.isoformat()) if old else "its old day"
        return False, f"Postiz did not take the move ({err[0]}). It is still on {still}."
    return True, f"Moved to {_when(new_day.isoformat())}."


# ── Google Business posts ───────────────────────────────────────────────────

_GBP_WAITING = ("draft", "pending", "review", "needs_review")


def gbp_entries(drafts: list[dict[str, Any]], brand_id: str, *, first_slot: date) -> list[dict[str, Any]]:
    """Google posts go out one a day in the order they were approved, so an
    approved post's day is its place in that queue. Waiting ones follow it."""
    approved = sorted((d for d in drafts if d.get("status") == "approved"), key=lambda d: d.get("approvedAt") or "")
    waiting = [d for d in drafts if str(d.get("status") or "draft") in _GBP_WAITING]
    out = []
    for i, d in enumerate(approved + waiting):
        day = date.fromordinal(first_slot.toordinal() + i)
        ok = d.get("status") == "approved"
        image = str(d.get("imageUrl") or "")
        out.append({
            "key": f"gbp:{d.get('id')}", "kind": "gbp", "view": "scheduled" if ok else "approval",
            "making": False, "state": "scheduled" if ok else "draft_ready",
            "date": day.isoformat(), "when": _when(day.isoformat()), "where": "Google",
            "brand_name": BRAND_NAMES.get(brand_id, brand_id),
            "title": str(d.get("title") or d.get("body") or "Google post")[:60],
            "what": "A Google Business post (shows on Google Maps and search)",
            "why": str(d.get("targetQuery") or "").strip() and f"For people searching “{d['targetQuery']}”.",
            "caption": str(d.get("body") or "").strip(),
            "status": (f"In the Google queue, about {_when(day.isoformat())}" if ok
                       else "Waiting for a yes. Approve to add it to the Google queue."),
            "has_image": bool(image), "image": image or None, "link": "", "plan_id": "", "movable": False,
            "channels": ["gbp"], "format": "feed",
            "actions": ["comment"] if ok else ["approve", "comment", "reject"], "comments": [],
        })
    return out


# ── plans and campaigns ─────────────────────────────────────────────────────


def plan_step_entries(steps: list[dict[str, Any]], brand_id: str) -> list[dict[str, Any]]:
    """Steps of plans not on the calendar yet (campaign_plan.month_steps), as To do."""
    out = []
    for s in steps:
        kind = str(s.get("step") or "")
        out.append({
            "key": f"step:{s.get('key')}", "kind": "task", "view": "todo", "making": False, "state": "planned",
            "date": str(s.get("date") or "")[:10], "when": _when(s.get("date")), "where": "",
            "brand_name": BRAND_NAMES.get(brand_id, brand_id),
            "title": f"{s.get('title')} ({s.get('event_name')})" if s.get("event_name") else str(s.get("title") or ""),
            "what": _TASK_WHAT.get(kind, f"A planned {kind}" if kind else "A planned step"),
            "why": "", "caption": "",
            "status": "In a draft plan" if s.get("plan_status") == "proposed" else "Plan approved, not on the calendar yet",
            "has_image": False, "image": None, "link": "", "plan_id": str(s.get("plan_id") or ""), "movable": False,
            "actions": ["comment"], "comments": [],
        })
    return out


def campaign_list(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    live = [p for p in plans if p.get("status") not in ("superseded", "archived")]
    live.sort(key=lambda p: str(p.get("event_date") or ""))
    return [{"plan_id": p.get("plan_id"), "title": p.get("event_name") or "Untitled campaign",
             "event_date": p.get("event_date"), "when": _when(p.get("event_date")), "status": p.get("status")}
            for p in live]


_KIND_ORDER = ("research", "decide", "shoot", "edit", "review", "post", "story", "boost")


def campaign_timeline(plan: dict[str, Any], entries_by_cal: dict[str, dict[str, Any]],
                      brand_id: str) -> dict[str, Any]:
    """One campaign from first planning step to last boost, with each placed
    post's own card attached."""
    steps = []
    for it in plan.get("items") or []:
        if it.get("status") == "removed":
            continue
        kind = str(it.get("kind") or "")
        entry = entries_by_cal.get(str(it.get("calendar_id") or ""))
        if entry:
            status = entry["status"]
        elif it.get("status") == "done":
            status = "Done"
        elif it.get("late"):
            status = "Late"
        else:
            status = "Coming"
        steps.append({
            "item_id": it.get("item_id"), "date": str(it.get("due") or "")[:10], "when": _when(it.get("due")),
            "phase": _PHASE.get(kind, "Other"), "kind": kind, "title": str(it.get("title") or ""),
            "owner": str(it.get("owner") or ""), "shots": list(it.get("shots") or []),
            "note": str(it.get("note") or ""), "budget": it.get("budget"), "status": status, "entry": entry,
        })
    steps.sort(key=lambda s: (s["date"], _KIND_ORDER.index(s["kind"]) if s["kind"] in _KIND_ORDER else 9))
    phases: list[dict[str, Any]] = []
    for s in steps:
        if phases and phases[-1]["phase"] == s["phase"]:
            phases[-1]["to"] = s["date"]
            phases[-1]["count"] += 1
        else:
            phases.append({"phase": s["phase"], "from": s["date"], "to": s["date"], "count": 1})
    start, peak = plan.get("window_start"), plan.get("peak_date") or plan.get("event_date")
    return {
        "ok": True, "plan_id": plan.get("plan_id"), "brand": brand_id,
        "brand_name": BRAND_NAMES.get(brand_id, brand_id),
        "title": str(plan.get("event_name") or "Untitled campaign"),
        "status": plan.get("status"),
        "dates": (f"Live {_when(start)}, peak {_when(peak)}" if start and start != peak else f"On {_when(peak)}"),
        "phases": phases, "steps": steps,
    }


_PHASE_COLOUR = {"Planning": "#8b80d8", "Shoot": "#e0a030", "Edit and review": "#4f8fd8",
                 "Posts": "#2f9e6e", "Boost": "#d4537e", "Other": "#888780"}


def render_campaign_page(t: dict[str, Any], *, token: str, who: str, printable: bool) -> str:
    """One campaign's timeline: behind Herman's campaign link (with buttons),
    or as the printable page Christelle saves as a PDF (no buttons)."""
    bar = "".join(
        f'<div class="ph" style="flex:{p["count"]};background:{_PHASE_COLOUR.get(p["phase"], "#888")}" '
        f'title="{_esc(p["phase"])}"></div>' for p in t["phases"])
    legend = "".join(
        f'<span><i style="background:{_PHASE_COLOUR.get(p["phase"], "#888")}"></i>{_esc(p["phase"])}: '
        f'{_esc(_when(p["from"]))}{" to " + _esc(_when(p["to"])) if p["to"] != p["from"] else ""}</span>'
        for p in t["phases"])
    rows = []
    for s in t["steps"]:
        extra = ""
        if s["owner"]:
            extra += f'<p class="meta">Who: {_esc(s["owner"])}</p>'
        if s["shots"]:
            extra += "<ul>" + "".join(f"<li>{_esc(x)}</li>" for x in s["shots"]) + "</ul>"
        if s["budget"]:
            extra += f'<p class="meta">Budget: R{_esc(s["budget"])}</p>'
        e = s["entry"]
        if e:
            if e.get("has_image") and token and not printable and e["kind"] == "post":
                src = f"/share/calendar/{_esc(token)}/image/{_esc(e['key'])}"
            else:
                src = _esc(e.get("image") or "")
            if src:
                extra += f'<img src="{src}" alt="The post image" loading="lazy">'
            if e.get("caption"):
                extra += f'<div class="cap">{_esc(e["caption"])}</div>'
            if not printable and token:
                extra += '<div class="btns">' + "".join(
                    f'<button class="act" type="button" data-key="{_esc(e["key"])}" data-kind="{_esc(e["kind"])}" '
                    f'data-action="{a}">{_LABELS[a]}</button>' for a in e["actions"]) + "</div>"
                extra += '<textarea rows="3" aria-label="Your note"></textarea><p class="note" role="status"></p>'
        rows.append(
            f'<article class="card step"><div class="when">{_esc(s["when"])}</div>'
            f'<div class="body"><p class="meta"><i class="dot" style="background:{_PHASE_COLOUR.get(s["phase"], "#888")}"></i>'
            f'{_esc(s["phase"])}</p><h2>{_esc(s["title"])}</h2>'
            f'<p><span class="pill">{_esc(s["status"])}</span></p>{extra}</div></article>')
    hello = f"Hi {_esc(who)}. " if who and not printable else ""
    script = "" if printable else f"<script>{_PAGE_JS}</script>"
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"robots\" content=\"noindex\">"
        f"<title>{_esc(t['title'])}</title><style>{_PAGE_CSS}{_CAMPAIGN_CSS}</style></head>"
        f'<body data-month="" data-start=""><main>'
        f'<div class="top"><h1>{_esc(t["title"])}</h1>'
        f'<button class="act noprint" type="button" onclick="window.print()">Save as PDF</button></div>'
        f'<p class="sub">{hello}{_esc(t["brand_name"])} campaign. {_esc(t["dates"])}. '
        f"Every step from planning to the last post, in date order.</p>"
        f'<div class="bar">{bar}</div><p class="legend">{legend}</p>'
        f'{"".join(rows) or "<p class=empty>No steps in this plan yet.</p>"}'
        f"</main>{script}</body></html>"
    )


_CAMPAIGN_CSS = """
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.bar{display:flex;gap:3px;height:12px;margin:8px 0 6px}.ph{border-radius:4px}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--tx2);margin:0 0 18px}
.legend i,.dot{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.step{flex-direction:row}.step .when{width:92px;flex-shrink:0;font-weight:600;font-size:14px}
.step img{width:160px;border-radius:8px;display:block;margin-top:8px}.step ul{margin:6px 0;padding-left:18px;font-size:14px}
@media (max-width:600px){.step{flex-direction:column}}
@media print{.noprint,.btns,textarea,.note{display:none!important}body{background:#fff;color:#000}
.card{break-inside:avoid;border-color:#ccc}main{max-width:none;padding:0}}
"""


# ── comments ────────────────────────────────────────────────────────────────


def _comments_path() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "calendar-comments.jsonl"


def add_comment(brand_id: str, key: str, who: str, text: str, *, action: str = "comment") -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("write something first")
    row = {
        "brand": _brand(brand_id), "key": key, "who": (who or "someone").strip()[:40],
        "text": text[:2000], "action": action,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    path = _comments_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def comments_by_key(brand_id: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    path = _comments_path()
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("brand") == brand_id and row.get("key"):
            out.setdefault(str(row["key"]), []).append(row)
    return out


# ── Herman's page ───────────────────────────────────────────────────────────

_VIEWS = (
    ("approval", "Needs your OK", "Ready posts waiting for a yes. Read it, look at the picture, then choose."),
    ("ideas", "Ideas", "Ideas only, nothing made yet. Approve one and the post gets made, then comes back under Needs your OK."),
    ("scheduled", "Scheduled", "Already approved and set to go out on these days. Comment if something should change."),
)

_LABELS = {"approve": "Approve", "comment": "Comment", "reject": "Reject"}

_PAGE_CSS = """
:root{--bg:#f6f4ef;--card:#fff;--tx:#1d1d1b;--tx2:#5f5e5a;--bd:#e3e0d8;--ok:#1d7a4f;--okbg:#e6f4ec;
--wait:#8a5a00;--waitbg:#fff4dc;--no:#a32d2d;--accent:#0c447c}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1f1f1d;--tx:#f1efe8;--tx2:#b4b2a9;--bd:#3a3936;
--ok:#7fd3a6;--okbg:#1c3327;--wait:#f0c46a;--waitbg:#3a2e14;--no:#f09595;--accent:#85b7eb}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:24px;margin:0 0 4px}p.sub{color:var(--tx2);margin:0 0 20px}
.tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:8px}
.tab{border:1px solid var(--bd);background:var(--card);border-radius:12px;padding:12px;text-align:left;cursor:pointer;color:var(--tx);font:inherit}
.tab b{display:block;font-size:26px;font-weight:600}.tab span{color:var(--tx2);font-size:14px}
.tab[aria-selected=true]{border:2px solid var(--accent)}
.hint{color:var(--tx2);font-size:14px;margin:12px 0 16px}
.card{display:flex;gap:16px;background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:16px;margin-bottom:12px}
.pic{width:180px;flex-shrink:0}.pic img{width:100%;border-radius:8px;display:block}
.pic .none{aspect-ratio:4/5;border-radius:8px;border:1px dashed var(--bd);display:flex;align-items:center;justify-content:center;color:var(--tx2);font-size:13px;text-align:center;padding:8px}
.body{min-width:0;flex:1}.meta{font-size:13px;color:var(--tx2)}h2{font-size:18px;margin:4px 0 10px}
.row{font-size:15px;margin:0 0 6px}.row b{font-weight:600}
.cap{white-space:pre-wrap;background:var(--bg);border-radius:8px;padding:10px;font-size:14px;margin:8px 0}
.pill{display:inline-block;font-size:12px;font-weight:600;border-radius:99px;padding:2px 10px;background:var(--waitbg);color:var(--wait)}
.pill.ok{background:var(--okbg);color:var(--ok)}
.btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
button.act{font:inherit;font-size:15px;border-radius:8px;padding:8px 16px;border:1px solid var(--bd);background:var(--card);color:var(--tx);cursor:pointer}
button.act[data-action=approve]{background:var(--ok);border-color:var(--ok);color:#fff}
button.act[data-action=reject]{color:var(--no)}
textarea{width:100%;font:inherit;font-size:15px;border:1px solid var(--bd);border-radius:8px;padding:8px;background:var(--card);color:var(--tx);margin-top:10px;display:none}
.note{font-size:14px;margin-top:8px}.err{color:var(--no)}.done{color:var(--ok);font-weight:600}
.said{font-size:14px;color:var(--tx2);border-left:3px solid var(--bd);padding-left:8px;margin:6px 0}
.empty{color:var(--tx2);text-align:center;padding:32px 0}
nav.months{display:flex;justify-content:space-between;margin:16px 0}nav.months a{color:var(--accent)}
@media (max-width:600px){.card{flex-direction:column}.pic{width:100%;max-width:320px}}
"""

_PAGE_JS = """
const tabs=[...document.querySelectorAll('.tab')];
function show(v){tabs.forEach(t=>t.setAttribute('aria-selected',t.dataset.view===v));
document.querySelectorAll('section[data-view]').forEach(s=>s.hidden=s.dataset.view!==v);}
tabs.forEach(t=>t.onclick=()=>show(t.dataset.view));
document.querySelectorAll('button.act').forEach(b=>b.onclick=async()=>{
 const card=b.closest('.card'),box=card.querySelector('textarea'),note=card.querySelector('.note');
 const action=b.dataset.action,need=action!=='approve';
 if(need&&box.style.display!=='block'){box.style.display='block';box.placeholder=action==='reject'?'What should change? (needed)':'Your comment';box.dataset.for=action;box.focus();return;}
 const text=box.value.trim();
 if(need&&!text){note.className='note err';note.textContent=action==='reject'?'Say what should change first.':'Write a comment first.';return;}
 card.querySelectorAll('button').forEach(x=>x.disabled=true);note.className='note';note.textContent='Saving…';
 try{const r=await fetch(location.pathname.replace(/\\/$/,'')+'/act',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({key:b.dataset.key,kind:b.dataset.kind,action,text,month:document.body.dataset.month})});
  const j=await r.json().catch(()=>({}));
  if(!r.ok||!j.ok){throw new Error(j.error||'That did not save.');}
  note.className='note done';note.textContent=j.message||'Saved.';box.style.display='none';
  if(action==='comment'){card.querySelectorAll('button').forEach(x=>x.disabled=false);box.value='';}
 }catch(e){note.className='note err';note.textContent=e.message+' Try again.';card.querySelectorAll('button').forEach(x=>x.disabled=false);}
});
show(document.body.dataset.start);
"""


def _esc(s: Any) -> str:
    return html.escape(str(s or ""), quote=True)


def _card(e: dict[str, Any], token: str) -> str:
    key = _esc(e["key"])
    if e["has_image"]:
        pic = f'<img src="/share/calendar/{_esc(token)}/image/{key}" alt="The post image" loading="lazy">'
    elif e["kind"] == "idea":
        pic = '<div class="none">No picture yet. It gets made after you approve.</div>'
    elif e["making"]:
        pic = '<div class="none">Picture being made</div>'
    else:
        pic = '<div class="none">No picture</div>'
    pill = "pill ok" if e["view"] == "scheduled" else "pill"
    rows = [f'<p class="row"><b>What it is:</b> {_esc(e["what"])}</p>']
    if e["why"]:
        rows.append(f'<p class="row"><b>Why:</b> {_esc(e["why"])}</p>')
    if e.get("next"):
        rows.append(f'<p class="row"><b>If you approve:</b> {_esc(e["next"])}</p>')
    cap = f'<div class="cap">{_esc(e["caption"])}</div>' if e["caption"] else ""
    said = "".join(
        f'<p class="said"><b>{_esc(c.get("who"))}:</b> {_esc(c.get("text"))}</p>' for c in e["comments"][-3:]
    )
    btns = "".join(
        f'<button class="act" type="button" data-key="{key}" data-kind="{_esc(e["kind"])}" '
        f'data-action="{a}">{_LABELS[a]}</button>'
        for a in e["actions"]
    )
    return (
        f'<article class="card"><div class="pic">{pic}</div><div class="body">'
        f'<p class="meta">{_esc(e["brand_name"])} · {_esc(e["where"])} · {_esc(e["when"])}</p>'
        f'<h2>{_esc(e["title"])}</h2><p><span class="{pill}">{_esc(e["status"])}</span></p>'
        f'{"".join(rows)}{cap}{said}<div class="btns">{btns}</div>'
        f'<textarea rows="3" aria-label="Your note"></textarea><p class="note" role="status"></p>'
        f"</div></article>"
    )


def _shift(month: str, step: int) -> str:
    first, _ = month_bounds(month)
    m = first.month - 1 + step
    return f"{first.year + m // 12:04d}-{m % 12 + 1:02d}"


def render_share_page(view: dict[str, Any], *, token: str, who: str) -> str:
    """The page behind Herman's link: three tabs, one card per entry, no login."""
    counts = view["counts"]
    start = next((v for v, *_ in _VIEWS if counts.get(v)), "approval")
    tabs, sections = [], []
    for v, label, hint in _VIEWS:
        tabs.append(f'<button class="tab" type="button" role="tab" data-view="{v}">'
                    f'<b>{counts.get(v, 0)}</b><span>{label}</span></button>')
        cards = [_card(e, token) for e in view["entries"] if e["view"] == v]
        body = "".join(cards) or '<p class="empty">Nothing here this month.</p>'
        sections.append(f'<section data-view="{v}"><p class="hint">{hint}</p>{body}</section>')
    base = f"/share/calendar/{_esc(token)}"
    prev_m, next_m = _shift(view["month"], -1), _shift(view["month"], 1)
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"robots\" content=\"noindex\">"
        f"<title>{_esc(view['brand_name'])} posts</title><style>{_PAGE_CSS}</style></head>"
        f'<body data-month="{_esc(view["month"])}" data-start="{start}"><main>'
        f"<h1>{_esc(view['brand_name'])} posts, {_esc(view['month_label'])}</h1>"
        f'<p class="sub">Hi {_esc(who)}. Here is what is planned. Tap a box to see that list.</p>'
        f'<div class="tabs" role="tablist">{"".join(tabs)}</div>{"".join(sections)}'
        f'<nav class="months"><a href="{base}?month={prev_m}">← Earlier month</a>'
        f'<a href="{base}?month={next_m}">Next month →</a></nav>'
        f"</main><script>{_PAGE_JS}</script></body></html>"
    )


def render_bad_link_page() -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Link expired</title>"
        f"<style>{_PAGE_CSS}</style></head><body><main><h1>This link has expired or is not right</h1>"
        "<p class=\"sub\">Ask Christelle for a new link.</p></main></body></html>"
    )
