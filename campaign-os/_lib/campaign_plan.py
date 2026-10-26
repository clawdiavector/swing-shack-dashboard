"""campaign_plan.py — turn a brief into a dated, editable plan.

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
EDITABLE_ITEM_FIELDS = (
    "title", "due", "kind", "channel", "note", "owner", "budget", "shots", "asked",
    "operator_offer",
)
# (a post step also carries `draft`: set only by request_draft, never edited by hand)

# What to capture on a shoot step: the exact shots, one per line, as the person
# who will shoot should read them. And who has been asked, and when, so a plan
# shows which shoots are still waiting to be requested.
MAX_SHOTS = 20
MAX_SHOT_LEN = 200


def parse_shots(v):
    """(ok, list, error). A list of strings, or text with one shot per line."""
    if v is None:
        return True, [], ""
    if isinstance(v, str):
        v = v.splitlines()
    if not isinstance(v, (list, tuple)):
        return False, [], "shots must be a list, one shot per line"
    out = [str(x).strip().lstrip("-•*").strip() for x in v if str(x).strip()]
    if len(out) > MAX_SHOTS:
        return False, [], f"at most {MAX_SHOTS} shots"
    if any(len(x) > MAX_SHOT_LEN for x in out):
        return False, [], f"each shot must be under {MAX_SHOT_LEN} characters"
    return True, out, ""

# A boost's planned budget, in rand. A plan only records the number: nothing is
# spent, and nothing is sent to Meta, from here.
MAX_BUDGET = 1_000_000


def parse_budget(v):
    """(ok, value, error). Empty clears the budget; otherwise a number from 0 up."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return True, None, ""
    try:
        n = float(str(v).replace(",", "").replace("R", "").strip())
    except ValueError:
        return False, None, "budget must be a number of rand"
    if n != n or n < 0 or n > MAX_BUDGET:   # n != n catches NaN
        return False, None, f"budget must be between 0 and {MAX_BUDGET:,}"
    return True, (int(n) if n == int(n) else round(n, 2)), ""



def _today() -> date:
    """Today in Johannesburg, where the team works, not the server's UTC day."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Africa/Johannesburg")).date()
    except Exception:  # no tz database: fall back to the server's day
        return date.today()


def refresh_late(plan: Optional[dict], today: Optional[date] = None) -> Optional[dict]:
    """Set each step's `late` from its date and today. A step is late when its
    date has passed and it is not done or removed. Derived on every read, so a
    step that goes overdue later turns red without anyone editing it."""
    if not plan:
        return plan
    today = today or _today()
    for i in plan.get("items") or []:
        due = _parse_date(i.get("due"))
        i["late"] = bool(due and due < today and i.get("status") not in ("done", "removed"))
    return plan


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
    """(window start date, event name) — backward-compatible alias."""
    window, _peak, name = _dates_from_brief(brief)
    return window, name


def _dates_from_brief(brief: dict) -> tuple[Optional[date], Optional[date], str]:
    """(window_start, peak_date, event name).

    Multi-week campaigns keep `timing.event_date` as the window start and
    `timing.peak_date` as the commercial peak (e.g. Black Friday). Single-day
    events use the same date for both when peak is omitted.
    """
    src = brief.get("source_opportunity") or {}
    timing = brief.get("timing") or {}
    opp = brief.get("opportunity") or {}
    window = (_parse_date(timing.get("event_date"))
              or _parse_date(src.get("date")))
    peak = (_parse_date(timing.get("peak_date"))
            or _parse_date(src.get("public_peak"))
            or window)
    if window and peak and peak < window:
        peak = window
    name = src.get("name") or opp.get("what") or brief.get("brief_id") or ""
    return window, peak, str(name)


def _row_anchor(kind: str, *, multi_window: bool) -> str:
    """Every template row counts back from the peak. (Counting runway steps back from
    the start of a multi-week window put "Pick the offer" in August.)"""
    return "peak"


def _anchor_day(plan_or_brief: dict, anchor: str) -> Optional[date]:
    if anchor == "window":
        return (_parse_date(plan_or_brief.get("window_start"))
                or _parse_date(plan_or_brief.get("event_date")))
    return (_parse_date(plan_or_brief.get("peak_date"))
            or _parse_date(plan_or_brief.get("event_date")))


def _item(offset: int, kind: str, title: str, channel: str, owner: str,
          note: str, anchor_day: date, today: date, *, source: str,
          anchor: str = "peak") -> dict:
    due = anchor_day - timedelta(days=offset)
    return {
        "item_id": "it-" + uuid.uuid4().hex[:8],
        "kind": kind,
        "title": title,
        "due": due.isoformat(),
        "days_before_event": offset,
        "anchor": anchor,
        "channel": channel,
        "owner": owner,
        "note": note,
        "needs_real_video": kind == "boost" or "real video" in title.lower(),
        "late": due < today,
        "status": "proposed",
        "source": source,
    }


def build_items(peak_day: date, today: Optional[date] = None,
                profile: str = "standard", duration_days: int = 0,
                *, window_start: Optional[date] = None) -> list[dict]:
    """Proposed checklist shaped by `profile` (see plan_profiles).

    Every step counts back from `peak_day`. `window_start` is only the first day of a
    multi-week window. A step already past is flagged late, never moved.
    """
    today = today or _today()
    window_start = window_start or peak_day
    multi = window_start != peak_day
    lead = (peak_day - today).days
    rows = rows_for(profile, lead, duration_days)
    items = []
    for r in rows:
        anchor = _row_anchor(r[1], multi_window=multi)
        items.append(_item(*r, peak_day, today, source="template", anchor=anchor))
    items.sort(key=lambda i: (i["due"], KIND_RANK.get(i["kind"], 9)))
    return items


def reanchor_plan_from_brief(plan: dict, brief: dict,
                             today: Optional[date] = None) -> dict:
    """Re-date template steps from the brief's window/peak timing.

    Keeps operator edits (status, notes, custom items). For a full rebuild with
    a new profile, use ``propose_plan(..., force=True)`` which supersedes the
    old plan.
    """
    today = today or _today()
    window, peak, _ = _dates_from_brief(brief)
    if not peak:
        return plan
    if not window:
        window = peak
    plan["event_date"] = window.isoformat()
    plan["window_start"] = window.isoformat()
    plan["peak_date"] = peak.isoformat()
    multi = window != peak
    for item in plan.get("items") or []:
        if item.get("source") != "template":
            continue
        anchor = item.get("anchor") or _row_anchor(item.get("kind") or "", multi_window=multi)
        item["anchor"] = anchor
        anchor_d = window if anchor == "window" else peak
        off = int(item.get("days_before_event") or 0)
        due = anchor_d - timedelta(days=off)
        item["due"] = due.isoformat()
        item["late"] = due < today and item.get("status") not in ("done", "removed")
    plan["items"].sort(key=lambda i: (i["due"], KIND_RANK.get(i["kind"], 9)))
    plan["updated_at"] = _now_iso()
    return plan


def _attach_offer_step_payload(plan: dict, brief: dict) -> None:
    """Copy the offer options onto the retail offer-decide step: suggestions, every stock
    line, and the brand's services. Read-only; the operator picks or types anything."""
    block = brief.get("candidate_offers") or {}
    lines = block.get("items") or []
    catalogue = block.get("catalogue") or []
    services = block.get("services") or []
    if not (lines or catalogue or services):
        return
    for item in plan.get("items") or []:
        if item.get("kind") != "decide":
            continue
        if "offer" not in (item.get("title") or "").lower():
            continue
        item["candidate_offers"] = lines
        item["offer_catalogue"] = catalogue
        item["offer_services"] = services
        item["offer_focus"] = block.get("focus_product") or ""
        item["offer_note"] = block.get("note") or ""
        item.setdefault(
            "operator_offer",
            {"selected_name": "", "price": "", "discount": ""},
        )
        break


# What to capture, as a starting point the person who shoots can change. Real
# photos and real people only (Christelle's rules): nothing here asks for a
# generated product, venue or person. Marked `shots_suggested` until edited.
_SHOTS_BY_BRAND = {
    "stick": [
        "The real product in hand, natural light, plain background behind it",
        "A customer or staff member trying it in the shop, not posed",
        "The shelf or display where it sits, wide enough to show the shop",
    ],
    "swing-shack": [
        "A real player mid-swing in a bay with the screen visible",
        "The lounge or bar with people in it, wide, as a visitor would see it",
        "A detail close-up: club, ball on the tee, the screen data",
    ],
    "bag-drop": [
        "The real product on a plain background, whole and sharp",
        "The same product being used or carried",
        "A tidy flat lay of the product with what it comes with",
    ],
}
_VIDEO_SHOTS = [
    "One person on camera saying it in their own words, one take, 10 to 15 seconds",
    "The same person showing the real product or space",
    "Vertical 9:16, steady, good light, sound on",
]


def suggest_shots(plan: dict, item: dict) -> list:
    """A short shot list for a shoot step, from the date and the brand. Real people and places only."""
    name = plan.get("event_name") or "the date"
    if item.get("needs_real_video"):
        base = list(_VIDEO_SHOTS)
        base.insert(1, f"Say what {name} is about, and why to come")
        return [x[:MAX_SHOT_LEN] for x in base]
    brand = _SHOTS_BY_BRAND.get(plan.get("brand_id"), _SHOTS_BY_BRAND["stick"])
    return [x[:MAX_SHOT_LEN] for x in [f"Hero shot for {name}: the real place or product the post is about", *brand]]


def _suggest_shots(plan: dict) -> None:
    for it in plan.get("items") or []:
        if it.get("kind") == "shoot" and not it.get("shots"):
            it["shots"] = suggest_shots(plan, it)
            it["shots_suggested"] = True


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
    window, peak, name = _dates_from_brief(brief)
    if not window and not peak:
        return {"ok": False,
                "error": "the brief has no event date; pin one first"}
    if not window:
        window = peak
    if not peak:
        peak = window
    # A brief written before peak_date existed: take the peak from the calendar.
    cal_peak = _parse_date((event_meta or {}).get("public_peak"))
    if cal_peak and window and not (brief.get("timing") or {}).get("peak_date") \
            and peak == window and cal_peak > window:
        peak = cal_peak
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
        "event_date": window.isoformat(),
        "window_start": window.isoformat(),
        "peak_date": peak.isoformat(),
        "status": PLAN_PROPOSED,
        "created_at": now,
        "updated_at": now,
        "approved_at": None,
        "approved_by": None,
        "event_kind": event_kind,
        "profile": chosen,
        "profile_label": PROFILES[chosen]["label"],
        "profile_reason": reason,
        "items": build_items(
            peak, today, chosen, duration, window_start=window),
        "edit_log": [],
    }
    if chosen == "retail_push":
        # Always built fresh: the stock list changes weekly and older briefs hold none.
        from _lib import candidate_offers
        brief = dict(brief, candidate_offers=candidate_offers.build(brand_id))
    _attach_offer_step_payload(plan, brief)
    _suggest_shots(plan)
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


def month_steps(brand_id: str, first: date, last: date) -> list[dict]:
    """Steps of plans that are not on the calendar yet, due between `first` and
    `last`: drafts, and approved plans not yet put on it. Once a plan is on the
    calendar its steps are solid entries there, so they are left out here.
    Superseded plans and removed steps are never listed."""
    out: list[dict] = []
    for p in list_plans(brand_id):
        if p.get("status") == PLAN_SUPERSEDED or p.get("placed_at"):
            continue
        for i in p.get("items") or []:
            due = _parse_date(i.get("due"))
            if i.get("status") == "removed" or not due or not first <= due <= last:
                continue
            out.append({
                "budget": i.get("budget"),
                "key": f"{p['plan_id']}:{i['item_id']}",
                "plan_id": p["plan_id"],
                "item_id": i["item_id"],
                "title": i["title"],
                "step": i["kind"],
                "date": due.isoformat(),
                "late": bool(i.get("late")),
                "channel": i.get("channel") or "",
                "event_name": p.get("event_name") or "",
                "event_date": p.get("event_date") or "",
                "event_kind": p.get("event_kind") or p.get("profile") or "standard",
                "plan_status": p.get("status"),
            })
    out.sort(key=lambda s: (s["date"], s["event_name"], s["title"]))
    return out


def supersede_plan(brand_id: str, plan_id: str) -> bool:
    """Retire a draft plan nobody has acted on (not approved, not on the calendar),
    so it no longer lists or alerts. Returns whether it was retired."""
    plan = get_plan(brand_id, plan_id)
    if not plan or plan.get("status") != PLAN_PROPOSED or plan.get("placed_at"):
        return False
    plan["status"] = PLAN_SUPERSEDED
    _log(plan, "operator", "retired with the approval it was made for")
    _write_plan(plan)
    return True


def get_plan(brand_id: str, plan_id: str) -> Optional[dict]:
    return refresh_late(_read_json(_plan_path(brand_id, plan_id)))


def list_plans(brand_id: str, status: Optional[str] = None) -> list[dict]:
    d = _plans_dir(brand_id)
    out: list[dict] = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            p = _read_json(os.path.join(d, fn))
            if p and (not status or p.get("status") == status):
                out.append(refresh_late(p))
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
    # An approved plan is locked, except for ticking a step done and noting who was asked.
    marks_done = set(patch) == {"status"} and patch.get("status") == "done"
    marks_asked = set(patch) == {"asked"}
    if err and not (plan and plan.get("status") == PLAN_APPROVED and (marks_done or marks_asked)):
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
        elif k == "shots":
            ok, v, why = parse_shots(v)
            if not ok:
                return {"ok": False, "error": why}
            if v and item["kind"] != "shoot":
                return {"ok": False, "error": "only a shoot step has a shot list"}
        elif k == "asked":
            if item["kind"] != "shoot":
                return {"ok": False, "error": "only a shoot step is asked for"}
            name = str(v).strip() if v else ""
            v = {"to": name, "at": _now_iso()} if name else None
        elif k == "budget":
            ok, v, why = parse_budget(v)
            if not ok:
                return {"ok": False, "error": why}
            if v is not None and item["kind"] != "boost":
                return {"ok": False, "error": "only a boost carries a budget"}
        elif k == "operator_offer":
            if not isinstance(v, dict):
                return {"ok": False, "error": "operator_offer must be an object"}
            v = {
                "selected_name": str(v.get("selected_name") or "").strip(),
                "price": str(v.get("price") or "").strip(),
                "discount": str(v.get("discount") or "").strip(),
            }
        elif k not in EDITABLE_ITEM_FIELDS:
            return {"ok": False, "error": f"cannot edit field: {k}"}
        if item.get(k) != v:
            item[k] = v
            changed.append(k)
            if k == "shots":
                item.pop("shots_suggested", None)  # a person has now written it
    if "due" in changed:
        anchor = item.get("anchor") or "peak"
        anchor_d = _anchor_day(plan, anchor) or _parse_date(plan["event_date"])
        item["days_before_event"] = (anchor_d - _parse_date(item["due"])).days
        item["late"] = _parse_date(item["due"]) < _today() and item.get("status") != "done"
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
    ok, shots, why = parse_shots(item.get("shots"))
    if not ok:
        return {"ok": False, "error": why}
    if shots and kind != "shoot":
        return {"ok": False, "error": "only a shoot step has a shot list"}
    ok, budget, why = parse_budget(item.get("budget"))
    if not ok:
        return {"ok": False, "error": why}
    if budget is not None and kind != "boost":
        return {"ok": False, "error": "only a boost carries a budget"}
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
        "late": due < _today(),
        "status": "kept",
        "source": "operator",
    }
    if budget is not None:
        new["budget"] = budget
    if shots:
        new["shots"] = shots
    plan["items"].append(new)
    plan["items"].sort(key=lambda i: (i["due"], i["kind"]))
    _log(plan, actor, "added item", new["item_id"])
    _write_plan(plan)
    return {"ok": True, "plan": plan, "item": new}


def approve_plan(brand_id: str, plan_id: str, actor: str = "operator") -> dict:
    """Record the operator's yes. Does NOT create calendar entries — that is
    a separate, explicit step. Needs a brief on the plan. Refused if a boost
    has no real-video shoot item left."""
    plan = get_plan(brand_id, plan_id)
    err = _editable(plan)
    if err:
        return {"ok": False, "error": err}
    if not plan.get("brief_id"):
        return {"ok": False, "error": "this plan has no brief"}
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

# A post step is a real calendar moment, so the existing Create pipeline can draft it
# (caption now, image after) and it shows on This week. Stories stay plain entries.
_CALENDAR_TYPE = {"post": "moment", "story": "content"}


def post_brief(plan: dict, item: dict) -> str:
    """What the caption writer is told about a planned post. Only what the plan
    knows: which date it is for, which step this is, and the step's own note. No
    offers, prices or claims are invented here."""
    when = plan.get("peak_date") or plan["event_date"]
    bits = [f"{item['title']} for {plan['event_name']} ({when})."]
    if item.get("note"):
        bits.append(str(item["note"]).strip())
    if plan.get("profile_label"):
        bits.append(f"Part of a {plan['profile_label'].lower()} plan.")
    return " ".join(bits)


def _calendar_record(plan: dict, item: dict) -> dict:
    kind = item["kind"]
    brand_id = plan["brand_id"]
    due = item["due"]
    title = f"{item['title']} — {plan['event_name']}"
    rec = {
        "type": _CALENDAR_TYPE.get(kind, "reminder"),
        "title": title,
        "event_date": due,
        "event_start": due,
        "event_end": due,
        "primary_channel": item.get("channel") or "",
        "angle": (post_brief(plan, item) if item["kind"] == "post" else (item.get("note") or ""))
        + (f" Planned budget: R{item['budget']:,}." if item.get("budget") else ""),
        "planned_budget_zar": item.get("budget"),
        "source_type": "operator",
        "source_origin": "internal_strategy",
        "date_confidence": "confirmed_date",
        "verification_status": "verified_primary",
        "created_by": "plan:" + plan["plan_id"],
        "plan_id": plan["plan_id"],
        "plan_item_id": item["item_id"],
        "plan_item_kind": kind,
        "event_kind": plan.get("event_kind") or plan.get("profile"),
        "brief_id": plan.get("brief_id"),
        # The Plan list / month grid skip rows with no event_key, so a placed
        # step would vanish and only the original campaign date would show.
        "event_key": f"{brand_id}:plan-{plan['plan_id']}-{item['item_id']}",
    }
    if kind == "post":
        rec["post_type"] = item.get("post_type") or "feed"
    pillars = plan.get("pillars")
    if isinstance(pillars, list) and pillars:
        rec["pillars"] = pillars
    return rec


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


def request_draft(brand_id: str, plan_id: str, item_id: str, actor: str = "operator",
                  enqueue=None) -> dict:
    """Ask the existing Create pipeline for a caption draft of a post step.

    The step must be a post, in an approved plan, already on the calendar (that is
    where its moment lives). This queues the same caption draft that approving a
    suggestion queues; the drafting job writes it, and it appears in Approve
    drafts for a person to approve. Nothing is posted and nothing is written here.
    `enqueue(item_id, brand, reason)` is injectable for tests."""
    plan = get_plan(brand_id, plan_id)
    if not plan:
        return {"ok": False, "error": "plan not found"}
    item = next((i for i in plan["items"] if i["item_id"] == item_id), None)
    if not item:
        return {"ok": False, "error": "step not found"}
    if item["kind"] != "post":
        return {"ok": False, "error": "only a post step can be drafted"}
    if item["status"] in ("removed", "done"):
        return {"ok": False, "error": "this step is already " + item["status"]}
    if plan.get("status") != PLAN_APPROVED:
        return {"ok": False, "error": "approve the plan first"}
    cal_id = item.get("calendar_id")
    if not cal_id:
        return {"ok": False, "error": "put the plan on the calendar first"}
    moment = f"calendar_candidate:{brand_id}:{cal_id}"
    if enqueue is None:
        from _lib import unified_inbox  # noqa: PLC0415
        from _lib.l5_create_enqueue import enqueue_create_actions  # noqa: PLC0415

        if unified_inbox._l5_enqueue_suppressed():  # noqa: SLF001
            return {"ok": False, "error": "drafting is switched off on this server"}

        def enqueue(item_id_, brand_, reason_):
            return enqueue_create_actions(item_id=item_id_, brand_id=brand_, reason=reason_, phase="lodge")
    try:
        actions = list(enqueue(moment, brand_id, "plan-step"))
    except Exception as e:  # the pipeline's own failure, reported as it is
        return {"ok": False, "error": f"could not queue the draft: {e}"}
    item["draft"] = {"requested_at": _now_iso(), "by": actor, "moment": moment, "queued": actions}
    _log(plan, actor, "asked for a draft", item_id)
    _write_plan(plan)
    return {"ok": True, "plan": plan, "item": item, "queued": actions}


def request_all_drafts(brand_id: str, plan_id: str, actor: str = "operator",
                       enqueue=None) -> dict:
    """Ask for a caption draft of every post step that has not been asked for yet.

    The same rules as one step: the plan must be approved and on the calendar.
    A step that fails is reported and the rest still go. Drafts land in Approve
    drafts for a person to approve; nothing is posted."""
    plan = get_plan(brand_id, plan_id)
    if not plan:
        return {"ok": False, "error": "plan not found"}
    if plan.get("status") != PLAN_APPROVED:
        return {"ok": False, "error": "approve the plan first"}
    if not plan.get("placed_at"):
        return {"ok": False, "error": "put the plan on the calendar first"}
    asked, already, failed = 0, 0, []
    for it in [i for i in plan["items"] if i["kind"] == "post" and i["status"] not in ("removed", "done")]:
        if it.get("draft"):
            already += 1
            continue
        r = request_draft(brand_id, plan_id, it["item_id"], actor, enqueue=enqueue)
        if r.get("ok"):
            asked += 1
        else:
            failed.append({"item_id": it["item_id"], "title": it["title"], "error": r.get("error", "")})
    return {"ok": not failed, "plan": get_plan(brand_id, plan_id), "asked": asked,
            "already": already, "failed": failed,
            **({"error": f"{len(failed)} drafts could not be asked for"} if failed else {})}


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
