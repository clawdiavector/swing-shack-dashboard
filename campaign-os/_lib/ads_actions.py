"""Ads actions — the one place Campaign OS may change a Meta ad.

``ads_brain`` and ``ads_brief`` stay read-only. This module makes two kinds of
change, each only after a person has seen exactly what will change, and each can
be undone:

    pause_ad        pause one ad, or put it back
    set_end_date    give an open-ended ad set a decision date (its end date),
                    or take that date off again

The shape of every change:

    preview()  reads the ad from Meta (read only) and returns what would change,
               with a short-lived signed ticket that names that exact change.
    apply()    takes the ticket, re-reads the ad, refuses if it moved since the
               preview, pauses it, and writes the audit entry.
    undo()     puts the ad back to the status it had, if it is still as we left it.

Nothing happens unless ``ADS_WRITES_ENABLED=1``. With it off, preview still works
and apply / undo refuse. Network access goes through the ``graph`` callable so the
tests never reach Meta.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

GRAPH_BASE = "https://graph.facebook.com"
TICKET_SALT = "ads-pause-ticket"
TICKET_MAX_AGE = 10 * 60
# Only these moves are allowed. Anything else is refused, not guessed at.
PAUSABLE = {"ACTIVE"}
RESTORABLE = {"ACTIVE"}
# A decision date is a short test window, not a way to schedule far ahead.
MAX_END_DAYS = 90
SAST = _dt.timezone(_dt.timedelta(hours=2))


class ActionRefused(Exception):
    """A change we will not make. The message is safe to show a person."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def writes_enabled() -> bool:
    return os.environ.get("ADS_WRITES_ENABLED") == "1"


def graph_call(method: str, path: str, token: str, params: dict | None = None,
               *, version: str = "v26.0", timeout: int = 20) -> dict:
    """One Graph API call. GET carries the token in the query, POST in the body."""
    url = f"{GRAPH_BASE}/{version}/{path.lstrip('/')}"
    data = None
    if method == "GET":
        q = dict(params or {}, access_token=token)
        url += "?" + urllib.parse.urlencode(q)
    else:
        data = urllib.parse.urlencode(dict(params or {}, access_token=token)).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode() or "{}")
        except ValueError:
            body = {}
        err = body.get("error") or {}
        # Meta's plain-language reason is in error_user_msg; "Invalid parameter" alone says nothing.
        msg = err.get("error_user_msg") or err.get("message") or f"Meta answered HTTP {e.code}"
        title = err.get("error_user_title")
        raise ActionRefused(f"Meta said: {title + ': ' if title and err.get('error_user_msg') else ''}{msg[:240]}", 502) from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise ActionRefused("Could not reach Meta. Nothing was changed.", 502) from None


def _read_ad(graph, token: str, ad_id: str) -> dict:
    return graph("GET", ad_id, token, {"fields": "id,name,status,effective_status,account_id"})


def _check_ad(ad: dict, ad_id: str, account_id: str) -> None:
    if str(ad.get("id")) != str(ad_id):
        raise ActionRefused("Meta did not return that ad.", 404)
    # account_id comes back without the act_ prefix.
    if f"act_{ad.get('account_id')}" != account_id:
        raise ActionRefused("That ad does not belong to this brand's ad account.", 403)


def _valid_ad_id(ad_id) -> str:
    s = str(ad_id or "")
    if not s.isdigit():
        raise ActionRefused("ad_id must be the numeric Meta ad id.")
    return s


def preview(brand_id: str, ad_id, *, graph, token: str, account_id: str, signer) -> dict:
    """What pausing this ad would change. Reads only."""
    ad_id = _valid_ad_id(ad_id)
    ad = _read_ad(graph, token, ad_id)
    _check_ad(ad, ad_id, account_id)
    status = ad.get("status")
    if status not in PAUSABLE:
        raise ActionRefused(f"This ad is {str(status).lower()}, so there is nothing to pause.")
    ticket = signer.dumps({"b": brand_id, "ad": ad_id, "before": status})
    return {
        "ad_id": ad_id, "ad_name": ad.get("name"), "brand_id": brand_id,
        "status_now": status, "effective_status": ad.get("effective_status"),
        "will_set": "PAUSED", "ticket": ticket, "ticket_valid_minutes": TICKET_MAX_AGE // 60,
        "writes_enabled": writes_enabled(),
    }


def _log_path(brand_id: str) -> str:
    return f"brands/{brand_id}/ads-actions/log.json"


def load_log(brand_id: str, read) -> list:
    return (read(_log_path(brand_id)) or {}).get("entries") or []


def _save(brand_id: str, entries: list, write) -> None:
    write(_log_path(brand_id), {"schema": "https://campaign-os/ads-actions/v1", "entries": entries})


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def apply(brand_id: str, ticket: str, *, graph, token: str, account_id: str, signer,
          read, write, by: str = "dashboard") -> dict:
    """Pause the ad the ticket names, then log it."""
    if not writes_enabled():
        raise ActionRefused("One-click ad changes are switched off.", 403)
    try:
        t = signer.loads(ticket, max_age=TICKET_MAX_AGE)
    except Exception:
        raise ActionRefused("That confirmation has expired. Open the preview again.", 400) from None
    if t.get("b") != brand_id:
        raise ActionRefused("That confirmation is for a different brand.", 403)
    if t.get("k") == "rename":
        return _apply_rename(brand_id, t, graph=graph, token=token, account_id=account_id,
                             read=read, write=write, by=by)
    if t.get("k") == "tags":
        return _apply_tags(brand_id, t, graph=graph, token=token, account_id=account_id,
                           read=read, write=write, by=by)
    if t.get("k") == "budget":
        return _apply_budget(brand_id, t, graph=graph, token=token, account_id=account_id,
                             read=read, write=write, by=by)
    if t.get("k") == "end_date":
        return _apply_end_date(brand_id, t, graph=graph, token=token, account_id=account_id,
                               read=read, write=write, by=by)
    ad_id = _valid_ad_id(t.get("ad"))
    ad = _read_ad(graph, token, ad_id)
    _check_ad(ad, ad_id, account_id)
    if ad.get("status") != t.get("before"):
        raise ActionRefused("The ad changed since you looked. Open the preview again.", 409)
    res = graph("POST", ad_id, token, {"status": "PAUSED"})
    if not res.get("success"):
        raise ActionRefused("Meta did not confirm the pause. Check Ads Manager.", 502)
    entry = {
        "id": uuid.uuid4().hex[:12], "at": _now(), "by": by, "kind": "pause_ad",
        "ad_id": ad_id, "ad_name": ad.get("name"), "before": t["before"], "after": "PAUSED",
        "undone_at": None,
    }
    entries = load_log(brand_id, read)
    entries.append(entry)
    _save(brand_id, entries, write)
    return entry


def undo(brand_id: str, action_id: str, *, graph, token: str, account_id: str,
         read, write, by: str = "dashboard") -> dict:
    """Put the ad back as it was, if nothing else has touched it since."""
    if not writes_enabled():
        raise ActionRefused("One-click ad changes are switched off.", 403)
    entries = load_log(brand_id, read)
    entry = next((e for e in entries if e.get("id") == action_id), None)
    if entry is None:
        raise ActionRefused("No such change.", 404)
    if entry.get("undone_at"):
        raise ActionRefused("That change was already undone.", 409)
    if entry.get("kind", "").startswith("rename_"):
        return _undo_rename(brand_id, entries, entry, graph=graph, token=token, account_id=account_id,
                            write=write, by=by)
    if entry.get("kind") == "set_url_tags":
        return _undo_tags(brand_id, entries, entry, graph=graph, token=token, account_id=account_id,
                          write=write, by=by)
    if entry.get("kind") == "set_adset_budget":
        return _undo_budget(brand_id, entries, entry, graph=graph, token=token, account_id=account_id,
                            write=write, by=by)
    if entry.get("kind") == "pause_adset":
        return _undo_adset_pause(brand_id, entries, entry, graph=graph, token=token, account_id=account_id,
                                 write=write, by=by)
    if entry.get("kind") == "set_end_date":
        return _undo_end_date(brand_id, entries, entry, graph=graph, token=token,
                              account_id=account_id, write=write, by=by)
    if entry.get("before") not in RESTORABLE:
        raise ActionRefused("That change cannot be undone from here.", 400)
    ad = _read_ad(graph, token, entry["ad_id"])
    _check_ad(ad, entry["ad_id"], account_id)
    if ad.get("status") != entry.get("after"):
        raise ActionRefused(
            f"The ad is now {str(ad.get('status')).lower()}, not paused, so it was changed "
            "somewhere else. Check Ads Manager.", 409)
    res = graph("POST", entry["ad_id"], token, {"status": entry["before"]})
    if not res.get("success"):
        raise ActionRefused("Meta did not confirm the undo. Check Ads Manager.", 502)
    entry["undone_at"] = _now()
    entry["undone_by"] = by
    _save(brand_id, entries, write)
    return entry


# ── set_end_date ────────────────────────────────────────────────────────────

_ADSET_FIELDS = "id,name,account_id,adset_id,adset{id,name,effective_status,end_time,start_time}"


def _end_of_day(date: _dt.date) -> str:
    """The end date as Meta wants it: the last minute of that day in South Africa."""
    return _dt.datetime(date.year, date.month, date.day, 23, 59, tzinfo=SAST).isoformat(timespec="seconds")


def _parse_date(value, today: _dt.date) -> _dt.date:
    try:
        d = _dt.date.fromisoformat(str(value))
    except ValueError:
        raise ActionRefused("Pick a date.") from None
    if d <= today:
        raise ActionRefused("The decision date must be after today.")
    if d > today + _dt.timedelta(days=MAX_END_DAYS):
        raise ActionRefused(f"A decision date more than {MAX_END_DAYS} days away is not a decision date.")
    return d


def _read_adset_of(graph, token: str, ad_id: str, account_id: str) -> tuple[dict, dict]:
    ad = graph("GET", ad_id, token, {"fields": _ADSET_FIELDS})
    _check_ad(ad, ad_id, account_id)
    adset = ad.get("adset") or {}
    if not adset.get("id"):
        raise ActionRefused("Meta did not return this ad's ad set.", 502)
    return ad, adset


def preview_end_date(brand_id: str, ad_id, end_date, *, graph, token: str, account_id: str,
                     signer, today: _dt.date | None = None) -> dict:
    """What giving this ad's ad set a decision date would change. Reads only."""
    ad_id = _valid_ad_id(ad_id)
    today = today or _dt.datetime.now(SAST).date()
    day = _parse_date(end_date, today)
    ad, adset = _read_adset_of(graph, token, ad_id, account_id)
    if adset.get("end_time"):
        raise ActionRefused("This ad set already has an end date, so there is nothing to set.")
    end = _end_of_day(day)
    ticket = signer.dumps({"k": "end_date", "b": brand_id, "ad": ad_id, "adset": str(adset["id"]),
                           "end": end})
    return {
        "kind": "set_end_date", "ad_id": ad_id, "ad_name": ad.get("name"), "brand_id": brand_id,
        "adset_id": str(adset["id"]), "adset_name": adset.get("name"),
        "adset_status": adset.get("effective_status"), "end_date": day.isoformat(),
        "will_set": end, "note": "The ad set stops delivering at the end of that day.",
        "ticket": ticket, "ticket_valid_minutes": TICKET_MAX_AGE // 60,
        "writes_enabled": writes_enabled(),
    }


def _apply_end_date(brand_id, t, *, graph, token, account_id, read, write, by) -> dict:
    ad_id = _valid_ad_id(t.get("ad"))
    ad, adset = _read_adset_of(graph, token, ad_id, account_id)
    if str(adset["id"]) != str(t.get("adset")):
        raise ActionRefused("The ad moved to another ad set since you looked. Open the preview again.", 409)
    if adset.get("end_time"):
        raise ActionRefused("The ad set got an end date since you looked. Open the preview again.", 409)
    res = graph("POST", str(adset["id"]), token, {"end_time": t["end"]})
    if not res.get("success"):
        raise ActionRefused("Meta did not confirm the end date. Check Ads Manager.", 502)
    entry = {
        "id": uuid.uuid4().hex[:12], "at": _now(), "by": by, "kind": "set_end_date",
        "ad_id": ad_id, "ad_name": ad.get("name"), "adset_id": str(adset["id"]),
        "adset_name": adset.get("name"), "before": None, "after": t["end"], "undone_at": None,
    }
    entries = load_log(brand_id, read)
    entries.append(entry)
    _save(brand_id, entries, write)
    return entry


def _same_moment(a, b) -> bool:
    try:
        return (_dt.datetime.fromisoformat(str(a).replace("Z", "+00:00"))
                == _dt.datetime.fromisoformat(str(b).replace("Z", "+00:00")))
    except ValueError:
        return False


def _undo_end_date(brand_id, entries, entry, *, graph, token, account_id, write, by) -> dict:
    ad, adset = _read_adset_of(graph, token, entry["ad_id"], account_id)
    if str(adset["id"]) != str(entry["adset_id"]) or not _same_moment(adset.get("end_time"), entry["after"]):
        raise ActionRefused("The end date is no longer the one we set, so it was changed somewhere else. "
                            "Check Ads Manager.", 409)
    res = graph("POST", str(adset["id"]), token, {"end_time": "0"})
    if not res.get("success"):
        raise ActionRefused("Meta did not confirm removing the end date. Check Ads Manager.", 502)
    entry["undone_at"] = _now()
    entry["undone_by"] = by
    _save(brand_id, entries, write)
    return entry


# ── pause_adset (made by the budget guard) ─────────────────────────────────

def _undo_adset_pause(brand_id, entries, entry, *, graph, token, account_id, write, by) -> dict:
    adset = graph("GET", entry["ad_id"], token, {"fields": "id,name,status,account_id"})
    if f"act_{adset.get('account_id')}" != account_id:
        raise ActionRefused("That ad set does not belong to this brand's ad account.", 403)
    if adset.get("status") != "PAUSED":
        raise ActionRefused(f"The ad set is now {str(adset.get('status')).lower()}, not paused, so it was changed "
                            "somewhere else. Check Ads Manager.", 409)
    res = graph("POST", entry["ad_id"], token, {"status": "ACTIVE"})
    if not res.get("success"):
        raise ActionRefused("Meta did not confirm the undo. Check Ads Manager.", 502)
    entry["undone_at"] = _now()
    entry["undone_by"] = by
    _save(brand_id, entries, write)
    return entry


# ── set_adset_budget ────────────────────────────────────────────────────────

# One step may move a daily budget by at most half either way. Bigger moves are several steps, each looked at.
MAX_BUDGET_STEP = 0.5
_BUDGET_FIELDS = "id,name,account_id,effective_status,daily_budget,lifetime_budget,campaign{id,name}"


def _read_budget_adset(graph, token: str, account_id: str, ad_id=None, adset_id=None) -> dict:
    """The ad set (by its own id, or the one an ad belongs to), checked against the brand's account."""
    if ad_id and not adset_id:
        ad = graph("GET", _valid_ad_id(ad_id), token, {"fields": "id,account_id,adset_id"})
        _check_ad(ad, str(ad_id), account_id)
        adset_id = ad.get("adset_id")
    adset_id = _valid_ad_id(adset_id)
    a = graph("GET", adset_id, token, {"fields": _BUDGET_FIELDS})
    if f"act_{a.get('account_id')}" != account_id:
        raise ActionRefused("That ad set does not belong to this brand's ad account.", 403)
    return a


def preview_budget(brand_id: str, *, ad_id=None, adset_id=None, pct=None, daily_budget=None, graph, token: str,
                   account_id: str, signer, context: dict | None = None) -> dict:
    """What changing the ad set's daily budget would do. Reads only. Give ``pct`` (0.2 = up a fifth) or
    ``daily_budget`` in rand."""
    a = _read_budget_adset(graph, token, account_id, ad_id, adset_id)
    before = int(a.get("daily_budget") or 0)
    if not before:
        raise ActionRefused("This ad set has no daily budget of its own (it is a lifetime budget, or the budget "
                            "is set on the campaign), so it cannot be changed here.")
    if a.get("effective_status") not in ("ACTIVE", "PAUSED", "CAMPAIGN_PAUSED", "ADSET_PAUSED"):
        raise ActionRefused(f"This ad set is {str(a.get('effective_status')).lower()}.")
    try:
        after = int(round(float(daily_budget) * 100)) if daily_budget is not None else int(round(before * (1 + float(pct)) / 100) * 100)
    except (TypeError, ValueError):
        raise ActionRefused("Give a percentage or a daily budget in rand.") from None
    if after <= 0 or after == before:
        raise ActionRefused("That would not change the budget.")
    if abs(after / before - 1) > MAX_BUDGET_STEP + 1e-9:
        raise ActionRefused(f"One step can change a daily budget by at most {int(MAX_BUDGET_STEP * 100)}%. "
                            "Make a smaller change, then another.")
    ticket = signer.dumps({"k": "budget", "b": brand_id, "adset": str(a["id"]), "before": before, "after": after})
    return {
        "kind": "set_adset_budget", "adset_id": str(a["id"]), "adset_name": a.get("name"),
        "campaign": (a.get("campaign") or {}).get("name"), "status": a.get("effective_status"),
        "before": before / 100, "after": after / 100, "change_pct": round(100 * (after / before - 1), 1),
        "per_day": (after - before) / 100, "ticket": ticket, "ticket_valid_minutes": TICKET_MAX_AGE // 60,
        "writes_enabled": writes_enabled(), "context": context or {},
    }


def _apply_budget(brand_id, t, *, graph, token, account_id, read, write, by) -> dict:
    a = _read_budget_adset(graph, token, account_id, adset_id=t.get("adset"))
    if int(a.get("daily_budget") or 0) != int(t["before"]):
        raise ActionRefused("The budget changed since you looked. Open the preview again.", 409)
    res = graph("POST", str(a["id"]), token, {"daily_budget": str(int(t["after"]))})
    if not res.get("success"):
        raise ActionRefused("Meta did not confirm the budget change. Check Ads Manager.", 502)
    entry = {"id": uuid.uuid4().hex[:12], "at": _now(), "by": by, "kind": "set_adset_budget",
             "ad_id": str(a["id"]), "ad_name": a.get("name"), "adset_id": str(a["id"]),
             "before": int(t["before"]) / 100, "after": int(t["after"]) / 100, "undone_at": None}
    entries = load_log(brand_id, read)
    entries.append(entry)
    _save(brand_id, entries, write)
    return entry


def _undo_budget(brand_id, entries, entry, *, graph, token, account_id, write, by) -> dict:
    a = _read_budget_adset(graph, token, account_id, adset_id=entry["adset_id"])
    if int(a.get("daily_budget") or 0) != int(round(entry["after"] * 100)):
        raise ActionRefused("The budget is no longer the one we set, so it was changed somewhere else. "
                            "Check Ads Manager.", 409)
    res = graph("POST", str(a["id"]), token, {"daily_budget": str(int(round(entry["before"] * 100)))})
    if not res.get("success"):
        raise ActionRefused("Meta did not confirm putting the budget back. Check Ads Manager.", 502)
    entry["undone_at"] = _now()
    entry["undone_by"] = by
    _save(brand_id, entries, write)
    return entry


# ── rename (an ad, an ad set or a campaign) ─────────────────────────────────

RENAMEABLE = ("ad", "adset", "campaign")


def _read_named(graph, token: str, account_id: str, obj_id) -> dict:
    obj_id = _valid_ad_id(obj_id)
    o = graph("GET", obj_id, token, {"fields": "id,name,account_id"})
    if f"act_{o.get('account_id')}" != account_id:
        raise ActionRefused("That does not belong to this brand's ad account.", 403)
    return o


def preview_rename(brand_id: str, kind: str, obj_id, new_name, *, graph, token: str, account_id: str, signer) -> dict:
    """What renaming would change. Reads only. Renaming does not touch delivery."""
    from . import ads_naming
    if kind not in RENAMEABLE:
        raise ActionRefused("kind must be ad, adset or campaign.")
    try:
        name = ads_naming.valid_name(new_name)
    except ValueError as e:
        raise ActionRefused(str(e)) from None
    o = _read_named(graph, token, account_id, obj_id)
    if o.get("name") == name:
        raise ActionRefused("It already has that name.")
    ticket = signer.dumps({"k": "rename", "b": brand_id, "kind": kind, "id": str(o["id"]),
                           "before": o.get("name"), "after": name})
    return {"kind": f"rename_{kind}", "object": kind, "id": str(o["id"]), "before": o.get("name"), "after": name,
            "ticket": ticket, "ticket_valid_minutes": TICKET_MAX_AGE // 60, "writes_enabled": writes_enabled()}


def _apply_rename(brand_id, t, *, graph, token, account_id, read, write, by) -> dict:
    o = _read_named(graph, token, account_id, t["id"])
    if o.get("name") != t["before"]:
        raise ActionRefused("The name changed since you looked. Open the preview again.", 409)
    res = graph("POST", str(o["id"]), token, {"name": t["after"]})
    if not res.get("success"):
        raise ActionRefused("Meta did not confirm the new name. Check Ads Manager.", 502)
    entry = {"id": uuid.uuid4().hex[:12], "at": _now(), "by": by, "kind": f"rename_{t['kind']}",
             "ad_id": str(o["id"]), "ad_name": t["after"], "before": t["before"], "after": t["after"], "undone_at": None}
    entries = load_log(brand_id, read)
    entries.append(entry)
    _save(brand_id, entries, write)
    return entry


def _undo_rename(brand_id, entries, entry, *, graph, token, account_id, write, by) -> dict:
    o = _read_named(graph, token, account_id, entry["ad_id"])
    if o.get("name") != entry["after"]:
        raise ActionRefused("The name is no longer the one we set, so it was changed somewhere else. "
                            "Check Ads Manager.", 409)
    res = graph("POST", str(o["id"]), token, {"name": entry["before"]})
    if not res.get("success"):
        raise ActionRefused("Meta did not confirm putting the name back. Check Ads Manager.", 502)
    entry["undone_at"] = _now()
    entry["undone_by"] = by
    _save(brand_id, entries, write)
    return entry


# ── set_url_tags (UTM parameters on an ad's link) ───────────────────────────

_TAG_FIELDS = ("id,name,account_id,creative{id,name,url_tags,object_story_id,effective_object_story_id,"
               "object_story_spec,asset_feed_spec}")


def _creative_payload(creative: dict, tags: str, ad_name: str) -> dict:
    """The new creative: the same content as the old one, with the URL parameters added. Meta will not edit a
    creative in place; the ad is pointed at the copy, and the old creative stays for Undo."""
    if creative.get("asset_feed_spec"):
        raise ActionRefused("This ad uses flexible (dynamic) creative, which cannot be copied here. "
                            "Add the URL parameters in Ads Manager.")
    name = f"{ad_name} (utm)"[:100]
    if creative.get("object_story_spec"):
        return {"name": name, "object_story_spec": creative["object_story_spec"], "url_tags": tags}
    story = creative.get("object_story_id") or creative.get("effective_object_story_id")
    if story:
        return {"name": name, "object_story_id": story, "url_tags": tags}
    raise ActionRefused("This ad's creative has neither a post nor a story spec to copy.")


def preview_tags(brand_id: str, ad_id, url_tags, *, graph, token: str, account_id: str, signer) -> dict:
    """What adding these URL parameters to the ad would change. Reads only. Warns that it swaps the creative."""
    from . import ads_naming
    try:
        tags = ads_naming.valid_tags(url_tags)
    except ValueError as e:
        raise ActionRefused(str(e)) from None
    ad_id = _valid_ad_id(ad_id)
    ad = graph("GET", ad_id, token, {"fields": _TAG_FIELDS})
    _check_ad(ad, ad_id, account_id)
    c = ad.get("creative") or {}
    if (c.get("url_tags") or "") == tags:
        raise ActionRefused("The ad already has those URL parameters.")
    _creative_payload(c, tags, ad.get("name") or ad_id)  # refuses what cannot be copied, before anyone approves
    ticket = signer.dumps({"k": "tags", "b": brand_id, "ad": ad_id, "creative": str(c.get("id")),
                           "before": c.get("url_tags") or "", "after": tags})
    return {"kind": "set_url_tags", "ad_id": ad_id, "ad_name": ad.get("name"), "before": c.get("url_tags") or "",
            "after": tags, "ticket": ticket, "ticket_valid_minutes": TICKET_MAX_AGE // 60,
            "warning": "Meta makes a copy of the ad's creative with these parameters and points the ad at it. The ad "
                       "goes back through Meta's review and its learning starts again.",
            "writes_enabled": writes_enabled()}


def _apply_tags(brand_id, t, *, graph, token, account_id, read, write, by) -> dict:
    ad_id = _valid_ad_id(t["ad"])
    ad = graph("GET", ad_id, token, {"fields": _TAG_FIELDS})
    _check_ad(ad, ad_id, account_id)
    c = ad.get("creative") or {}
    if str(c.get("id")) != t["creative"]:
        raise ActionRefused("The ad's creative changed since you looked. Open the preview again.", 409)
    payload = _creative_payload(c, t["after"], ad.get("name") or ad_id)
    made = graph("POST", f"{account_id}/adcreatives", token,
                 {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in payload.items()})
    new_id = made.get("id")
    if not new_id:
        raise ActionRefused("Meta did not create the new creative. Nothing was changed.", 502)
    res = graph("POST", ad_id, token, {"creative": json.dumps({"creative_id": str(new_id)})})
    if not res.get("success"):
        raise ActionRefused("Meta made the copy but would not point the ad at it. The ad is unchanged.", 502)
    entry = {"id": uuid.uuid4().hex[:12], "at": _now(), "by": by, "kind": "set_url_tags", "ad_id": ad_id,
             "ad_name": ad.get("name"), "before": t["before"], "after": t["after"],
             "creative_before": t["creative"], "creative_after": str(new_id), "undone_at": None}
    entries = load_log(brand_id, read)
    entries.append(entry)
    _save(brand_id, entries, write)
    return entry


def _undo_tags(brand_id, entries, entry, *, graph, token, account_id, write, by) -> dict:
    ad = graph("GET", entry["ad_id"], token, {"fields": "id,account_id,creative{id}"})
    _check_ad(ad, entry["ad_id"], account_id)
    if str((ad.get("creative") or {}).get("id")) != entry["creative_after"]:
        raise ActionRefused("The ad's creative is no longer the one we made, so it was changed somewhere else. "
                            "Check Ads Manager.", 409)
    res = graph("POST", entry["ad_id"], token, {"creative": json.dumps({"creative_id": entry["creative_before"]})})
    if not res.get("success"):
        raise ActionRefused("Meta did not confirm putting the old creative back. Check Ads Manager.", 502)
    entry["undone_at"] = _now()
    entry["undone_by"] = by
    _save(brand_id, entries, write)
    return entry
