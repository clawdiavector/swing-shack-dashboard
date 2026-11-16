"""One-click build: turn an Ad suggestion into a real Meta ad, switched off, for a person to check and switch on.

Same rules as _lib/ads_actions (the only other place Campaign OS writes to Meta):

    preview()   reads only: finds the brand's Facebook Page and Instagram account through the ad account, and
                returns every call it would make, with a short-lived signed ticket naming exactly those calls.
    apply()     needs ADS_WRITES_ENABLED=1 and the ticket. Makes the calls in order (form, campaign, ad set,
                creative, ad), every object PAUSED. If one fails, whatever was already made is removed again.
                Logged in brands/<brand>/ads-actions/log.json as kind "build_ad".
    undo        through ads_actions.undo(): removes the ad, creative, ad set and campaign (and archives the form),
                but only while the ad is still switched off. Once someone has switched it on, it refuses.

Nothing here ever sets anything ACTIVE. Field names follow the Marketing API as documented; they have not been
run against the live account yet, so the first real build should be watched in Ads Manager.
"""
from __future__ import annotations

import datetime as _dt
import json
import uuid

from . import ads_actions as aa

TICKET_MAX_AGE = aa.TICKET_MAX_AGE
_GOAL = {"lead_form": "LEAD_GENERATION", "messages": "CONVERSATIONS", "traffic": "LANDING_PAGE_VIEWS",
         "awareness": "THRUPLAY"}
_DESTINATION = {"lead_form": "ON_AD", "messages": "MESSAGING_INSTAGRAM_DIRECT_MESSENGER", "traffic": "WEBSITE"}
_CTA = {"Book now": "BOOK_NOW", "Sign up": "SIGN_UP", "Learn more": "LEARN_MORE", "Shop now": "SHOP_NOW",
        "Send message": "MESSAGE_PAGE"}
# Where each brand's ads are aimed, as Meta address strings (no guessed coordinates).
_PLACE = {"stick": ("Paarl, Western Cape, South Africa", 50),
          "swing-shack": ("1 Garden Road, Bordeaux, Randburg, South Africa", 25)}
_ORDER = ("form", "campaign", "adset", "creative", "ad")


def _j(obj) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _sast(day: _dt.date, end: bool = False) -> str:
    return f"{day.isoformat()}T{'23:59:00' if end else '00:00:00'}+0200"


def plan_calls(s: dict, *, brand_id: str, account_id: str, identity: dict) -> list:
    """Every Graph call that builds this suggestion, in order. Pure. "{form_id}" style values are filled in from
    earlier answers when the calls are made."""
    kind = s["ad_type"]
    if kind not in _GOAL or not s.get("spend"):
        raise aa.ActionRefused("This suggestion cannot be built as an ad yet.")
    names, page, ig = s["names"], identity["page_id"], identity["ig_user_id"]
    days = [_dt.date.fromisoformat(s["schedule"]["start"]), _dt.date.fromisoformat(s["schedule"]["end"])]
    place, radius = _PLACE.get(brand_id, (None, None))
    calls = []
    if kind == "lead_form":
        f = s["form"]
        questions = [{"type": "FULL_NAME"}, {"type": "PHONE"}, {"type": "EMAIL"}]
        for i, q in enumerate([q for q in f["questions"] if q.get("options")], 1):
            questions.append({"type": "CUSTOM", "key": f"q{i}", "label": q["label"],
                              "options": [{"value": o, "key": f"q{i}_{n}"} for n, o in enumerate(q["options"], 1)]})
        calls.append({"step": "form", "method": "POST", "path": f"{page}/leadgen_forms", "token": "page", "params": {
            "name": f["name"], "locale": "EN_US", "is_optimized_for_quality": "true",
            "questions": _j(questions),
            "context_card": _j({"title": f["headline"], "content": [f["description"]], "style": "PARAGRAPH_STYLE"}),
            "privacy_policy": _j({"url": f["privacy_url"], "link_text": "Privacy policy"}),
            "thank_you_page": _j({"title": f["thank_you"]["headline"], "body": f["thank_you"]["text"],
                                  "button_type": "VIEW_WEBSITE", "button_text": f["thank_you"]["button"],
                                  "website_url": f["thank_you"]["button_url"]}),
        }})
    calls.append({"step": "campaign", "method": "POST", "path": f"{account_id}/campaigns", "token": "ads", "params": {
        "name": names["campaign"], "objective": s["objective"], "status": "PAUSED", "buying_type": "AUCTION",
        "special_ad_categories": "[]", "is_adset_budget_sharing_enabled": "false"}})
    targeting = {"targeting_automation": {"advantage_audience": 1}}
    if place:
        targeting["geo_locations"] = {"custom_locations": [{"address_string": place, "radius": radius,
                                                            "distance_unit": "kilometer"}]}
    adset = {"name": names["adset"], "campaign_id": "{campaign_id}", "status": "PAUSED",
             "daily_budget": str(int(round(s["spend"]["daily"] * 100))), "billing_event": "IMPRESSIONS",
             "optimization_goal": _GOAL[kind], "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
             "targeting": _j(targeting), "start_time": _sast(days[0]), "end_time": _sast(days[1], end=True)}
    if kind in _DESTINATION:
        adset["destination_type"] = _DESTINATION[kind]
    if kind in ("lead_form", "messages"):
        adset["promoted_object"] = _j({"page_id": page})
    calls.append({"step": "adset", "method": "POST", "path": f"{account_id}/adsets", "token": "ads", "params": adset})
    cta = {"type": _CTA.get(s["cta"], "LEARN_MORE")}
    if kind == "lead_form":
        cta["value"] = {"lead_gen_form_id": "{form_id}"}
    elif kind == "messages":
        cta["value"] = {"app_destination": "MESSENGER"}
    else:
        cta["value"] = {"link": s["landing_url"]}
    calls.append({"step": "creative", "method": "POST", "path": f"{account_id}/adcreatives", "token": "ads", "params": {
        "name": f"{names['ad']}_creative", "object_id": page, "instagram_user_id": ig,
        "source_instagram_media_id": str(s["post_id"]), "call_to_action": _j(cta), "url_tags": s["url_params"]}})
    calls.append({"step": "ad", "method": "POST", "path": f"{account_id}/ads", "token": "ads", "params": {
        "name": names["ad"], "adset_id": "{adset_id}", "creative": _j({"creative_id": "{creative_id}"}),
        "status": "PAUSED"}})
    return calls


def identity_of(graph, token: str, account_id: str) -> tuple[dict, str | None]:
    """The brand's Facebook Page (the one its ad account promotes), its Instagram account and the Page's token."""
    pages = (graph("GET", f"{account_id}/promote_pages", token, {"fields": "id,name"}) or {}).get("data") or []
    if not pages:
        raise aa.ActionRefused("The ad account has no Facebook Page to run ads from.", 409)
    page_id = str(pages[0]["id"])
    page = graph("GET", page_id, token, {"fields": "id,instagram_business_account,access_token"}) or {}
    ig = (page.get("instagram_business_account") or {}).get("id")
    if not ig:
        raise aa.ActionRefused("The Facebook Page has no Instagram account linked.", 409)
    return {"page_id": page_id, "ig_user_id": str(ig)}, page.get("access_token")


def preview(brand_id: str, s: dict, *, graph, token: str, account_id: str, signer) -> dict:
    """Reads only. What would be made, and the ticket to make exactly that."""
    identity, _ = identity_of(graph, token, account_id)
    calls = plan_calls(s, brand_id=brand_id, account_id=account_id, identity=identity)
    ticket = signer.dumps({"b": brand_id, "k": "build", "key": f"{s['post_id']}:{s['ad_type']}",
                           "names": s["names"], "calls": calls})
    return {"brand_id": brand_id, "identity": identity, "calls": calls, "ticket": ticket,
            "ticket_valid_minutes": TICKET_MAX_AGE // 60, "writes_enabled": aa.writes_enabled(),
            "note": "Everything is created switched off. Check it in Ads Manager, then switch it on there."}


def _fill(value, ids: dict):
    if isinstance(value, str):
        for k, v in ids.items():
            value = value.replace("{" + k + "}", v)
    return value


def _remove(graph, token: str, created: dict, page_token: str | None) -> list:
    """Remove what a build made, newest first. Lead forms cannot be deleted, so they are archived."""
    gone = []
    for step in reversed(_ORDER):
        oid = created.get(step)
        if not oid:
            continue
        if step == "form":
            graph("POST", oid, page_token or token, {"status": "ARCHIVED"})
        else:
            graph("DELETE", oid, token, {})
        gone.append(step)
    return gone


def apply(brand_id: str, ticket: str, *, graph, token: str, account_id: str, signer, read, write,
          by: str = "dashboard") -> dict:
    if not aa.writes_enabled():
        raise aa.ActionRefused("One-click ad changes are switched off.", 403)
    try:
        t = signer.loads(ticket, max_age=TICKET_MAX_AGE)
    except Exception:
        raise aa.ActionRefused("That confirmation has expired. Open the preview again.", 400) from None
    if t.get("b") != brand_id or t.get("k") != "build":
        raise aa.ActionRefused("That confirmation is for something else.", 403)
    _, page_token = identity_of(graph, token, account_id)
    created: dict = {}
    try:
        for c in t["calls"]:
            params = {k: _fill(v, {f"{s}_id": i for s, i in created.items()}) for k, v in c["params"].items()}
            tok = page_token if c["token"] == "page" else token
            if c["token"] == "page" and not tok:
                raise aa.ActionRefused("Meta gave no Page token, so the lead form cannot be made.", 502)
            res = graph(c["method"], c["path"], tok, params) or {}
            if not res.get("id"):
                raise aa.ActionRefused(f"Meta did not return an id for the {c['step']}.", 502)
            created[c["step"]] = str(res["id"])
    except aa.ActionRefused as exc:
        try:
            gone = _remove(graph, token, created, page_token)
            tail = (f" The {', '.join(gone)} already made {'was' if len(gone) == 1 else 'were'} removed again."
                    if gone else " Nothing had been made yet.")
        except aa.ActionRefused:
            tail = f" Some parts could not be removed; check Ads Manager for {t['names']['campaign']}."
        raise aa.ActionRefused(f"{exc}{tail}", getattr(exc, "status", 502)) from None
    entry = {"id": uuid.uuid4().hex[:12], "at": aa._now(), "by": by, "kind": "build_ad", "key": t.get("key"),
             "names": t["names"], "created": created, "status": "PAUSED", "undone_at": None}
    entries = aa.load_log(brand_id, read)
    entries.append(entry)
    aa._save(brand_id, entries, write)
    return entry


def undo(brand_id: str, entries: list, entry: dict, *, graph, token: str, account_id: str, write, by) -> dict:
    ad_id = entry["created"].get("ad")
    if ad_id:
        ad = graph("GET", ad_id, token, {"fields": "id,status,effective_status"}) or {}
        if ad.get("status") != "PAUSED":
            raise aa.ActionRefused("Someone has switched this ad on since it was built, so it is not removed. "
                                   "Pause it instead.", 409)
    page_token = None
    if entry["created"].get("form"):
        try:
            _, page_token = identity_of(graph, token, account_id)
        except aa.ActionRefused:
            page_token = None
    _remove(graph, token, entry["created"], page_token)
    entry["undone_at"] = aa._now()
    entry["undone_by"] = by
    aa._save(brand_id, entries, write)
    return entry


# ── pages ────────────────────────────────────────────────────────────────

_STEP_NAME = {"form": "Lead form", "campaign": "Campaign", "adset": "Ad set", "creative": "Creative",
              "ad": "Ad"}


def _page(title: str, body: str) -> str:
    from . import ads_brief
    return ads_brief._page(title, "suggest", "One-click build &middot; everything is made switched off", body)


def _e(x) -> str:
    from html import escape
    return escape(str(x if x is not None else ""))


def render_preview(p: dict, error: str | None = None) -> str:
    rows = []
    for c in p.get("calls") or []:
        shown = {k: v for k, v in c["params"].items() if k not in ("questions",)}
        detail = "; ".join(f"{k}: {v}" for k, v in shown.items())
        rows.append(f'<tr><td><b>{_STEP_NAME.get(c["step"], c["step"])}</b></td><td><code>{_e(detail)}</code></td></tr>')
    body = (f'<p>This makes {len(p.get("calls") or [])} things in Meta for {_e(p.get("brand_id"))}, every one '
            '<b>switched off</b>. Nothing spends until someone switches the ad on in Ads Manager.</p>'
            f'<div class="scroll"><table>{"".join(rows)}</table></div>')
    if error:
        body = f'<p><b>Could not build:</b> {_e(error)}</p>' + body
    if p.get("writes_enabled"):
        body += (f'<form method="post" action="/ads-brief/build/confirm"><input type="hidden" name="brand" '
                 f'value="{_e(p.get("brand_id"))}"><input type="hidden" name="ticket" value="{_e(p["ticket"])}">'
                 f'<button type="submit">Yes, build it switched off</button> <span class="mute">This confirmation '
                 f'lasts {p.get("ticket_valid_minutes", 10)} minutes.</span></form>')
    else:
        body += ('<p class="mute">Building ads from here is switched off on this site at the moment, so this is a '
                 'preview only. Ask Kyle to switch on one-click ad changes.</p>')
    return _page("Build this ad", body + '<p><a href="/ads-brief?kind=suggest">&larr; Back to Ad suggestions</a></p>')


def render_done(brand_id: str, entry: dict, *, account_id: str) -> str:
    act = str(account_id).replace("act_", "")
    names = entry.get("names") or {}
    link = f"https://adsmanager.facebook.com/adsmanager/manage/campaigns?act={act}"
    body = (f'<p>Built, switched off: campaign <b>{_e(names.get("campaign"))}</b>, ad set {_e(names.get("adset"))}, '
            f'ad {_e(names.get("ad"))}.</p><p>Next: open <a href="{_e(link)}" target="_blank" rel="noopener">'
            'Ads Manager</a>, check the ad preview and the form, then switch the campaign on there.</p>'
            f'<form method="post" action="/ads-brief/build/undo"><input type="hidden" name="brand" '
            f'value="{_e(brand_id)}"><input type="hidden" name="action_id" value="{_e(entry.get("id"))}">'
            '<button type="submit">Undo: remove it again</button> <span class="mute">Only while it is still '
            'switched off.</span></form><p><a href="/ads-brief?kind=suggest">&larr; Back to Ad suggestions</a></p>')
    return _page("Ad built", body)
