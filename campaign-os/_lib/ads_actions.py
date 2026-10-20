"""Ads actions — the one place Campaign OS may change a Meta ad.

``ads_brain`` and ``ads_brief`` stay read-only. This module does one thing: pause
a single ad, or put it back, after a person has seen exactly what will change.

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
        msg = (body.get("error") or {}).get("message") or f"Meta answered HTTP {e.code}"
        raise ActionRefused(f"Meta said: {msg[:200]}", 502) from None
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
