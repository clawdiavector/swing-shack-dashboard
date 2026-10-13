"""campaign_plan.py — turn an approved brief into a dated, editable plan.

A brief says WHAT the campaign is for. A plan says WHAT TO DO and WHEN,
working backwards from the event date: research, decide, shoot, edit,
review, post, boost.

Deterministic — no LLM, no captions, no images. Nothing here touches the
live calendar or publishes anything; approving a plan only records the
operator's yes. Putting the posts on the calendar is the next step.

Rules baked in (Christelle's standing rules):
  * Ads use real human video only. A boost item is only proposed together
    with a shoot item for real video, and carries needs_real_video=True.
  * No fake product or venue imagery: shoot items ask for real photos/video.
  * Dates already in the past are not silently moved; the item is flagged
    `late` so the operator sees it and decides.

Storage: <DATA_DIR>/plans/<brand_id>/<plan_id>.json — one plan per brief.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from _lib.plan_profiles import PROFILES, classify, rows_for

ALLOWED_BRAND_IDS = ("swing-shack", "stick", "bag-drop")

PLAN_PROPOSED = "proposed"      # editable, nothing committed
PLAN_APPROVED = "approved"      # operator said yes; locked until reopened
PLAN_SUPERSEDED = "superseded"  # replaced by a newer plan for the same brief

ITEM_KINDS = ("research", "decide", "shoot", "edit", "review", "post",
              "story", "boost")
ITEM_STATUSES = ("proposed", "kept", "removed", "done")
KIND_RANK = {k: i for i, k in enumerate(ITEM_KINDS)}
EDITABLE_ITEM_FIELDS = ("title", "due", "kind", "channel", "note", "owner")



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_dir() -> str:
    return os.environ.get("DATA_DIR", "data")


def _plans_dir(brand_id: str) -> str:
    if brand_id not in ALLOWED_BRAND_IDS:
        raise ValueError(f"unknown brand_id: {brand_id}")
    return os.path.join(_data_dir(), "plans", brand_id)


def _plan_path(brand_id: str, plan_id: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_\-]{4,40}", plan_id or ""):
        raise ValueError(f"invalid plan_id format: {plan_id}")
    return os.path.join(_plans_dir(brand_id), plan_id + ".json")


def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_plan(plan: dict) -> None:
    p = _plan_path(plan["brand_id"], plan["plan_id"])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def _parse_date(s: Any) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _event_from_brief(brief: dict) -> tuple[Optional[date], str]:
    """(event date, event name) from a brief, tolerant of older shapes."""
    src = brief.get("source_opportunity") or {}
    timing = brief.get("timing") or {}
    opp = brief.get("opportunity") or {}
    d = (_parse_date(timing.get("event_date"))
         or _parse_date(src.get("date")))
    name = src.get("name") or opp.get("what") or brief.get("brief_id") or ""
    return d, str(name)


def _item(offset: int, kind: str, title: str, channel: str, owner: str,
          note: str, event_day: date, today: date, *, source: str) -> dict:
    due = event_day - timedelta(days=offset)
    return {
        "item_id": "it-" + uuid.uuid4().hex[:8],
        "kind": kind,
        "title": title,
        "due": due.isoformat(),
        "days_before_event": offset,
        "channel": channel,
        "owner": owner,
        "note": note,
        "needs_real_video": kind == "boost" or "real video" in title.lower(),
        "late": due < today,
        "status": "proposed",
        "source": source,
    }


def build_items(event_day: date, today: Optional[date] = None,
                profile: str = "standard", duration_days: int = 0) -> list[dict]:
    """The proposed checklist for an event on `event_day`, soonest first,
    shaped by `profile` (see plan_profiles)."""
    today = today or date.today()
    lead = (event_day - today).days
    rows = rows_for(profile, lead, duration_days)
    items = [_item(*r, event_day, today, source="template") for r in rows]
    items.sort(key=lambda i: (i["due"], KIND_RANK.get(i["kind"], 9)))
    return items


def _find_plan_for_brief(brand_id: str, brief_id: str) -> Optional[dict]:
    d = _plans_dir(brand_id)
    if not os.path.isdir(d):
        return None
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        p = _read_json(os.path.join(d, fn))
        if (p and p.get("brief_id") == brief_id
                and p.get("status") != PLAN_SUPERSEDED):
            return p
    return None


def _duration_days(brief: dict, event_meta: Optional[dict]) -> int:
    n = int((event_meta or {}).get("duration_days") or 0)
    if n:
        return n
    src = brief.get("source_opportunity") or {}
    return int(src.get("duration_days") or 0)


def propose_plan(brand_id: str, brief: dict, *, force: bool = False,
                 today: Optional[date] = None, event_meta: Optional[dict] = None,
                 profile: Optional[str] = None) -> dict:
    """Build and store a proposed plan for a brief.

    The plan's shape follows the kind of date: `profile` if the operator chose
    one, otherwise worked out from `event_meta` (tier, category, duration,
    pillars...) and the brief. See plan_profiles.

    Refuses a rejected or superseded brief and a brief with no event date.
    One live plan per brief: a second call returns the existing plan unless
    `force`, which supersedes it.
    """
    if brand_id not in ALLOWED_BRAND_IDS:
        return {"ok": False, "error": f"unknown brand_id: {brand_id}"}
    if not brief:
        return {"ok": False, "error": "brief not found"}
    if brief.get("status") in ("rejected", "superseded"):
        return {"ok": False,
                "error": f"brief is {brief.get('status')}; no plan for it"}
    event_day, name = _event_from_brief(brief)
    if not event_day:
        return {"ok": False,
                "error": "the brief has no event date; pin one first"}
    brief_id = brief.get("brief_id")
    existing = _find_plan_for_brief(brand_id, brief_id)
    if existing and not force:
        return {"ok": True, "plan": existing, "existing": True}
    if existing:
        existing["status"] = PLAN_SUPERSEDED
        existing["updated_at"] = _now_iso()
        _write_plan(existing)
    meta = dict(event_meta or {})
    meta.setdefault("pillars", (brief.get("source_opportunity") or {}).get("pillars"))
    meta.setdefault("duration_days", _duration_days(brief, event_meta))
    # The type of the date is what it is; the shape of the plan can be overridden.
    event_kind, auto_reason = classify(meta, name)
    if profile in PROFILES:
        chosen, reason = profile, "Chosen by you."
    else:
        chosen, reason = event_kind, auto_reason
    duration = _duration_days(brief, event_meta)
    now = _now_iso()
    plan = {
        "plan_id": "pln-" + uuid.uuid4().hex[:10],
        "brand_id": brand_id,
        "brief_id": brief_id,
        "brief_status": brief.get("status"),
        "event_name": name,
        "event_date": event_day.isoformat(),
        "status": PLAN_PROPOSED,
        "created_at": now,
        "updated_at": now,
        "approved_at": None,
        "approved_by": None,
        "event_kind": event_kind,
        "profile": chosen,
        "profile_label": PROFILES[chosen]["label"],
        "profile_reason": reason,
        "items": build_items(event_day, today, chosen, duration),
        "edit_log": [],
    }
    _write_plan(plan)
    return {"ok": True, "plan": plan, "existing": False}


def sync_brief_status(plan: Optional[dict], brief: Optional[dict]) -> Optional[dict]:
    """Copy the brief's current status onto the plan, so a brief approved
    after the plan was proposed does not leave the plan stuck. Saves only
    when it changed."""
    if plan and brief and brief.get("status") != plan.get("brief_status"):
        plan["brief_status"] = brief.get("status")
        plan["updated_at"] = _now_iso()
        _write_plan(plan)
    return plan


def get_plan(brand_id: str, plan_id: str) -> Optional[dict]:
    return _read_json(_plan_path(brand_id, plan_id))


def list_plans(brand_id: str, status: Optional[str] = None) -> list[dict]:
    d = _plans_dir(brand_id)
    out: list[dict] = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            p = _read_json(os.path.join(d, fn))
            if p and (not status or p.get("status") == status):
                out.append(p)
    return out


def _log(plan: dict, actor: str, what: str, item_id: str = "") -> None:
    plan["edit_log"].append({"at": _now_iso(), "actor": actor,
                             "what": what, "item_id": item_id})
    plan["updated_at"] = _now_iso()


def _editable(plan: Optional[dict]) -> Optional[str]:
    """Error string when the plan cannot be edited, else None."""
    if not plan:
        return "plan not found"
    if plan.get("status") == PLAN_SUPERSEDED:
        return "plan is superseded"
    if plan.get("status") == PLAN_APPROVED:
        return "plan is approved; reopen it to edit"
    return None


def edit_item(brand_id: str, plan_id: str, item_id: str, patch: dict,
              actor: str = "operator") -> dict:
    """Change an item's wording, date, kind, channel, owner or note, or its
    status (kept / removed / done). Removed items stay in the file so the
    change can be undone."""
    plan = get_plan(brand_id, plan_id)
    err = _editable(plan)
    if err and not (plan and plan.get("status") == PLAN_APPROVED
                    and set(patch) == {"status"}
                    and patch.get("status") == "done"):
        return {"ok": False, "error": err}
    item = next((i for i in plan["items"] if i["item_id"] == item_id), None)
    if not item:
        return {"ok": False, "error": "item not found"}
    changed = []
    for k, v in (patch or {}).items():
        if k == "status":
            if v not in ITEM_STATUSES:
                return {"ok": False, "error": f"invalid status: {v}"}
        elif k == "kind":
            if v not in ITEM_KINDS:
                return {"ok": False, "error": f"invalid kind: {v}"}
        elif k == "due":
            d = _parse_date(v)
            if not d:
                return {"ok": False, "error": "due must be YYYY-MM-DD"}
            v = d.isoformat()
        elif k not in EDITABLE_ITEM_FIELDS:
            return {"ok": False, "error": f"cannot edit field: {k}"}
        if item.get(k) != v:
            item[k] = v
            changed.append(k)
    if "due" in changed:
        ev = _parse_date(plan["event_date"])
        item["days_before_event"] = (ev - _parse_date(item["due"])).days
        item["late"] = _parse_date(item["due"]) < date.today()
        item["source"] = "operator"
    if changed:
        item["needs_real_video"] = (item["kind"] == "boost"
                                    or "real video" in item["title"].lower())
        _log(plan, actor, "edited " + ", ".join(changed), item_id)
        _write_plan(plan)
    return {"ok": True, "plan": plan, "item": item}


def add_item(brand_id: str, plan_id: str, item: dict,
             actor: str = "operator") -> dict:
    """Add an operator item. Needs a title and a due date."""
    plan = get_plan(brand_id, plan_id)
    err = _editable(plan)
    if err:
        return {"ok": False, "error": err}
    due = _parse_date(item.get("due"))
    title = (item.get("title") or "").strip()
    kind = item.get("kind") or "post"
    if not title or not due:
        return {"ok": False, "error": "title and due (YYYY-MM-DD) required"}
    if kind not in ITEM_KINDS:
        return {"ok": False, "error": f"invalid kind: {kind}"}
    ev = _parse_date(plan["event_date"])
    new = {
        "item_id": "it-" + uuid.uuid4().hex[:8],
        "kind": kind,
        "title": title,
        "due": due.isoformat(),
        "days_before_event": (ev - due).days,
        "channel": item.get("channel") or "",
        "owner": item.get("owner") or "marketing",
        "note": item.get("note") or "",
        "needs_real_video": kind == "boost" or "real video" in title.lower(),
        "late": due < date.today(),
        "status": "kept",
        "source": "operator",
    }
    plan["items"].append(new)
    plan["items"].sort(key=lambda i: (i["due"], i["kind"]))
    _log(plan, actor, "added item", new["item_id"])
    _write_plan(plan)
    return {"ok": True, "plan": plan, "item": new}


def approve_plan(brand_id: str, plan_id: str, actor: str = "operator") -> dict:
    """Record the operator's yes. Does NOT create calendar entries — that is
    a separate, explicit step. Refused while the brief is not approved or a
    boost has no real-video shoot item left in the plan."""
    plan = get_plan(brand_id, plan_id)
    err = _editable(plan)
    if err:
        return {"ok": False, "error": err}
    if plan.get("brief_status") != "approved":
        return {"ok": False,
                "error": "the brief is not approved yet; approve it first"}
    live = [i for i in plan["items"] if i["status"] != "removed"]
    if not live:
        return {"ok": False, "error": "every item is removed"}
    has_video = any(i["kind"] == "shoot" and i["needs_real_video"]
                    for i in live)
    if any(i["kind"] == "boost" for i in live) and not has_video:
        return {"ok": False,
                "error": ("a boost needs real human video, but no video "
                          "shoot is left in the plan. Add one or remove "
                          "the boost.")}
    for i in live:
        if i["status"] == "proposed":
            i["status"] = "kept"
    plan["status"] = PLAN_APPROVED
    plan["approved_at"] = _now_iso()
    plan["approved_by"] = actor
    _log(plan, actor, "approved plan")
    _write_plan(plan)
    return {"ok": True, "plan": plan}


def reopen_plan(brand_id: str, plan_id: str, actor: str = "operator") -> dict:
    plan = get_plan(brand_id, plan_id)
    if not plan or plan.get("status") != PLAN_APPROVED:
        return {"ok": False, "error": "only an approved plan can be reopened"}
    if plan.get("placed_at"):
        return {"ok": False,
                "error": "take the plan off the calendar before reopening it"}
    plan["status"] = PLAN_PROPOSED
    plan["approved_at"] = None
    plan["approved_by"] = None
    _log(plan, actor, "reopened plan")
    _write_plan(plan)
    return {"ok": True, "plan": plan}


# ── Step 3: put an approved plan on the calendar, and take it off again ──
#
# Posts and stories become `content` entries; every other step (check, decide,
# shoot, edit, approve, boost) becomes a `reminder`, so the dates show up on
# the calendar without the scheduler trying to make a post from them. Nothing
# is published and no image is generated. "Taking it off" marks the entries
# ignored (the calendar store is append-only, so nothing is deleted).

_CALENDAR_TYPE = {"post": "content", "story": "content"}


def _calendar_record(plan: dict, item: dict) -> dict:
    kind = item["kind"]
    return {
        "type": _CALENDAR_TYPE.get(kind, "reminder"),
        "title": f"{item['title']} — {plan['event_name']}",
        "event_date": item["due"],
        "event_start": item["due"],
        "event_end": item["due"],
        "primary_channel": item.get("channel") or "",
        "angle": item.get("note") or "",
        "source_type": "operator",
        "created_by": "plan:" + plan["plan_id"],
        "plan_id": plan["plan_id"],
        "plan_item_id": item["item_id"],
        "plan_item_kind": kind,
        "event_kind": plan.get("event_kind") or plan.get("profile"),
        "brief_id": plan.get("brief_id"),
    }


def place_on_calendar(brand_id: str, plan_id: str, actor: str = "operator",
                      add_record=None) -> dict:
    """Create a calendar entry for every kept step that is not already on it.
    Needs an approved plan. Safe to repeat: steps already placed are skipped.
    `add_record(brand_id, record, initial_status)` is injectable for tests."""
    plan = get_plan(brand_id, plan_id)
    if not plan:
        return {"ok": False, "error": "plan not found"}
    if plan.get("status") != PLAN_APPROVED:
        return {"ok": False,
                "error": "approve the plan before putting it on the calendar"}
    if add_record is None:
        from _lib.marketing_calendar import add_candidate as add_record  # noqa: PLC0415
    created, failed = [], []
    for item in plan["items"]:
        if item["status"] == "removed" or item.get("calendar_id"):
            continue
        try:
            rec = add_record(brand_id, _calendar_record(plan, item), "approved")
        except Exception as e:  # keep going; report what did not land
            failed.append({"item_id": item["item_id"], "error": str(e)})
            continue
        item["calendar_id"] = rec.get("calendar_id", "")
        created.append(item["calendar_id"])
    if created:
        plan["placed_at"] = _now_iso()
        _log(plan, actor, f"put {len(created)} steps on the calendar")
        _write_plan(plan)
    out = {"ok": not failed, "plan": plan, "placed": len(created),
           "failed": failed}
    if failed:
        out["error"] = f"{len(failed)} steps could not be placed"
    return out


def take_off_calendar(brand_id: str, plan_id: str, actor: str = "operator",
                      transition=None) -> dict:
    """Undo: mark this plan's calendar entries ignored and clear the links.
    `transition(brand_id, calendar_id, status, reason=...)` is injectable."""
    plan = get_plan(brand_id, plan_id)
    if not plan:
        return {"ok": False, "error": "plan not found"}
    if transition is None:
        from _lib.marketing_calendar import transition_status as transition  # noqa: PLC0415
    removed, failed = 0, []
    for item in plan["items"]:
        cid = item.get("calendar_id")
        if not cid:
            continue
        try:
            transition(brand_id, cid, "ignored", reason="plan taken off calendar")
            item["calendar_id"] = ""
            removed += 1
        except Exception as e:
            failed.append({"item_id": item["item_id"], "error": str(e)})
    if removed:
        if not any(i.get("calendar_id") for i in plan["items"]):
            plan["placed_at"] = None
        _log(plan, actor, f"took {removed} steps off the calendar")
        _write_plan(plan)
    out = {"ok": not failed, "plan": plan, "removed": removed,
           "failed": failed}
    if failed:
        out["error"] = f"{len(failed)} steps could not be taken off"
    return out
