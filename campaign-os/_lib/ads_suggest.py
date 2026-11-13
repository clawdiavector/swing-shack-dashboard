"""Ad suggestions: which of a brand's own posts to turn into a Meta ad, and exactly how.

Reads what the jobs already keep (pure; nothing here reaches Meta or changes an ad):

    post-outcomes.json            the last 30-60 days of Instagram posts, scored (layer7/post_outcomes)
    ig-business-analytics.json    the same posts with saves, shares and a thumbnail (meta_refresh)
    ads-suggest/running.json      captions of the ads running now, so a post is never suggested twice (ads_brief job)
    ads-budget/settings.json      the brand's budget and its period (a person sets it)
    ads-budget/figures.json       what the live ad sets are set to spend (ads_brief job)
    ads-brief/latest.json         last 7 days per ad: spend, leads, cost per lead (ads_brief job)

For each post it decides:

    is it ad material      real human video only (Christelle's rule). A retail product photo becomes a job to
                           animate it; any other still stays organic.
    what kind of ad        a service (fitting, free assessment, coaching, membership) is a lead-form ad; a product
                           is a messages ad, because Stick and Swing Shack sell products in the DMs.
    what it costs          a 7-day test, sized from the brand's own cost per lead, never under the floor.
    where the money is     unused room in the weekly budget first, then the weakest running ad set, then an ask.
    every setting          names, objective, audience, placements, button, form questions, thank-you link and UTMs.
"""
from __future__ import annotations

import calendar
import datetime as _dt
import math
import re
from html import escape

from . import ads_creative, ads_naming

SCHEMA = "https://campaign-os/ads-suggest/v1"
WINDOW_DAYS = 60
TEST_DAYS = 7
# The smallest daily budget a lead ad set has run on here: stick_leads_fitting_may26_set, R30 a day (26 Oct 2026).
FLOOR_DAILY = 30
MAX_DAILY = 100
LEADS_PER_WEEK_TARGET = 5
MAX_RUNNABLE = 4
MAX_STILLS = 2

LEAD_THEMES = ("assessment", "fitting", "coaching", "membership")
PRODUCT_THEMES = ("putter", "irons", "driver", "grip", "bags", "retail")
_PRICE = re.compile(r"\bR\s?\d[\d ,]*|\b\d+\s?/\s?pm\b|\bper month\b", re.I)
_DEAL = re.compile(r"\d+\s?%|black friday|\bsale\b|\bspecial\b|\boff\b|\bdeal\b", re.I)

BRAND_NAMES = {"stick": "Stick", "swing-shack": "Swing Shack", "bag-drop": "Bag Drop"}

# Landing pages, all checked live on 13 Nov 2026 (HTTP 200). Privacy wording lives on the policies / terms page.
SITES = {
    "stick": {
        "fitting": "https://stickgolf.co.za/club-fitting-at-stick/",
        "coaching": "https://stickgolf.co.za/coaching-at-stick/",
        "assessment": "https://stickgolf.co.za/bookings/",
        "membership": "https://stickgolf.co.za/bookings/",
        "product": "https://stickgolf.co.za/brands/",
        "bookings": "https://stickgolf.co.za/bookings/",
        "privacy": "https://stickgolf.co.za/policies/",
        "location": "Paarl, Western Cape, plus 50 km (reaches Cape Town and the Winelands, Stick's customer area)",
    },
    "swing-shack": {
        "fitting": "https://swingshack.co.za/club-fitting/",
        "coaching": "https://swingshack.co.za/product-category/lesson/",
        "assessment": "https://swingshack.co.za/free-club-assessment/",
        "membership": "https://swingshack.co.za/membership/",
        "product": "https://swingshack.co.za/",
        "bookings": "https://swingshack.co.za/bookings/",
        "privacy": "https://swingshack.co.za/terms-conditions/",
        "location": "Old Parktonian Sports Club, Randburg, Johannesburg, plus 25 km",
    },
}

_WHEN = {"label": "When would you like to come in?",
         "options": ["This week", "In the next two weeks", "This month", "Just looking for now"]}
_FORM_COPY = {
    "fitting": ("Book your fitting", "Book now", [
        {"label": "Which clubs would you like fitted?",
         "options": ["Driver", "Irons", "Wedges", "Putter", "Full bag", "Not sure yet"]}, _WHEN]),
    # A free assessment is not a fitting: no loft, shaft or lie questions (Christelle, 5 Nov).
    "assessment": ("Claim your free club assessment", "Sign up", [
        {"label": "What would you like us to look at?", "options": ["My clubs", "My swing", "Both"]}, _WHEN]),
    "coaching": ("Book a coaching session", "Book now", [
        {"label": "What would you most like to work on?",
         "options": ["Driving", "Iron play", "Short game", "Putting", "A bit of everything"]},
        {"label": "How often do you play?",
         "options": ["Every week", "A few times a month", "Now and then", "Just starting"]}, _WHEN]),
    "membership": ("Find out about membership", "Learn more", [
        {"label": "Have you been to us before?", "options": ["Yes", "No"]}, _WHEN]),
}
_CONTACT = [{"label": "Full name", "prefill": True}, {"label": "Phone number", "prefill": True},
            {"label": "Email", "prefill": True}]


def norm(text) -> str:
    """The same caption key ads_creative uses to tell that a post already runs as an ad."""
    return ads_creative._norm(text)


def _r(x) -> str:
    return f"R{x:,.0f}"


def _date(ts) -> _dt.date | None:
    try:
        return _dt.datetime.strptime(str(ts)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def theme_of(caption: str) -> str | None:
    """The one subject that decides the ad: a service before a product, nothing when there is nothing to sell."""
    low = (caption or "").lower()
    if "assessment" in low:
        return "assessment"
    found = ads_creative.themes_of(caption)
    return next((t for t in LEAD_THEMES + PRODUCT_THEMES if t in found), None)


# ── money ────────────────────────────────────────────────────────────────

def weekly_budget(settings: dict, today: _dt.date) -> float:
    amount = float((settings or {}).get("monthly_budget") or 0)
    if (settings or {}).get("budget_period") == "week":
        return amount
    return amount * 7 / calendar.monthrange(today.year, today.month)[1]


def _brand_cpl(brief: dict) -> float | None:
    nums = (brief or {}).get("numbers_7d") or {}
    cpl = (nums.get("current") or {}).get("cost_per_lead")
    if cpl:
        return float(cpl)
    ads = [a for a in nums.get("ads") or [] if a.get("leads")]
    leads = sum(a["leads"] for a in ads)
    return round(sum(a.get("spend") or 0 for a in ads) / leads, 2) if leads else None


def donors(figures: dict, brief: dict) -> list[dict]:
    """Running daily ad sets worth taking money from, weakest first: spend with no result, then a cost per lead
    over one and a half times the brand's."""
    ads = ((brief or {}).get("numbers_7d") or {}).get("ads") or []
    cpl = _brand_cpl(brief)
    out = []
    for s in (figures or {}).get("sets") or []:
        if s.get("kind") != "daily" or not s.get("amount"):
            continue
        name = str(s.get("name") or "")
        mine = [a for a in ads if a.get("campaign_name") and (name == f"{a['campaign_name']}_set"
                                                              or name.startswith(a["campaign_name"]))]
        spend = sum(a.get("spend") or 0 for a in mine)
        results = sum((a.get("leads") or 0) + (a.get("messages") or 0) for a in mine)
        if spend <= 0:
            continue
        if results == 0:
            out.append({"name": name, "daily": s["amount"], "spend": spend, "results": 0, "rank": (0, -spend)})
        elif cpl and spend / results > 1.5 * cpl:
            out.append({"name": name, "daily": s["amount"], "spend": spend, "results": results,
                        "rank": (1, -(spend / results))})
    return sorted(out, key=lambda d: d["rank"])


def _spend(kind: str, cpl: float | None) -> dict:
    if kind == "lead_form" and cpl:
        daily = max(FLOOR_DAILY, min(MAX_DAILY, math.ceil(cpl * LEADS_PER_WEEK_TARGET / TEST_DAYS / 5) * 5))
    else:
        daily = FLOOR_DAILY
    total = daily * TEST_DAYS
    if kind == "lead_form" and cpl:
        n = int(total // cpl)
        text = f"about {n} lead{'s' if n != 1 else ''} at about {_r(cpl)} each (the brand's cost per lead in the last 7 days)"
    elif kind == "lead_form":
        n, text = None, "no cost per lead on record yet; this first week sets it"
    else:
        n, text = None, "no cost per chat on record yet; this first week sets it"
    return {"daily": daily, "days": TEST_DAYS, "total": total, "expected_results": n, "expected_text": text}


def _fund(need_daily: float, state: dict) -> dict:
    need = need_daily * TEST_DAYS
    if state["room"] >= need:
        text = (f"Unused room in the {_r(state['budget'])} weekly budget: the running ad sets are set to "
                f"{_r(state['committed'])} a week, which leaves {_r(state['room'])}. This test uses {_r(need)} of it.")
        state["room"] -= need
        return {"source": "room", "text": text}
    for d in state["donors"]:
        if d["daily"] >= need_daily:
            why = ("no leads or chats" if not d["results"]
                   else f"{_r(d['spend'] / d['results'])} a result, well above the brand's usual")
            act = "Pause it" if not d["results"] else f"Lower it from {_r(d['daily'])} to {_r(d['daily'] - need_daily)} a day"
            text = (f"Take {_r(need_daily)} a day from {d['name']}: {_r(d['spend'])} spent in the last 7 days for {why}. "
                    f"{act} and give that money to this test, so the weekly total stays the same.")
            d["daily"] -= need_daily
            return {"source": "move", "from": d["name"], "text": text}
    if not state["budget"]:
        text = f"No weekly ad budget is set. Ask Herman for {_r(need)} for this week-long test."
    else:
        text = (f"The {_r(state['budget'])} weekly budget is already set to be spent and no running ad set is weak "
                f"enough to take from. Ask Herman for an extra {_r(need)} for this week-long test.")
    return {"source": "extra", "text": text}


# ── settings ─────────────────────────────────────────────────────────────

def _names(brand: str, objective: str, theme: str, fmt: str, today: _dt.date) -> dict:
    short = ads_naming.BRAND_SHORT.get(brand, ads_naming.slug(brand))
    campaign = f"{short}_{ads_naming.OBJECTIVE_SHORT.get(objective, 'other')}_{theme}_{ads_naming.month_tag(today)}"
    return {"campaign": campaign, "adset": f"{campaign}_set", "ad": f"{theme}_{fmt}_v1"}


def _tags(names: dict, content: str | None = None) -> str:
    return (f"utm_source=meta&utm_medium=paid_social&utm_campaign={names['campaign']}"
            f"&utm_content={content or names['ad']}&utm_id={{{{ad.id}}}}")


def _form(theme: str, site: dict, names: dict, opening: str | None) -> dict:
    headline, button, extra = _FORM_COPY[theme]
    return {
        "name": f"{names['campaign']}_form", "type": "Higher intent",
        "why_type": ("Adds a review screen before the form is sent, so fewer people tap through by accident. "
                     "Since 1 Oct, 93 leads gave 1 booking in ClubLab (wiki: research/lead-conversion-check-2026-11-13)."),
        "headline": headline, "description": opening or headline,
        "questions": _CONTACT + [dict(q) for q in extra],
        "privacy_url": site["privacy"],
        "thank_you": {"headline": "Thanks, we have your details",
                      "text": "We will be in touch to find a time that suits you.",
                      "button": button,
                      "button_url": f"{site['bookings']}?" + _tags(names, f"{names['ad']}_thankyou").split("&utm_id")[0]},
    }


def _setup(s: dict, brand: str, site: dict, today: _dt.date) -> list[dict]:
    start = today + _dt.timedelta(days=1)
    end = start + _dt.timedelta(days=TEST_DAYS - 1)
    lead = s["ad_type"] == "lead_form"
    n = s["names"]
    campaign = [("Name", n["campaign"]), ("Buying type", "Auction"),
                ("Objective", "Leads" if lead else "Engagement"),
                ("Special ad categories", "None"),
                ("Advantage+ campaign budget", "Off: the budget sits on the ad set, where the budget guard pauses it")]
    adset = [("Name", n["adset"]),
             ("Conversion location", "Instant forms" if lead else "Message apps: Instagram and Messenger"),
             ("Performance goal", "Maximise number of leads" if lead else "Maximise number of conversations"),
             ("Budget", f"Daily budget {_r(s['spend']['daily'])}"),
             ("Schedule", f"Start {start:%d %b %Y} 00:00, end {end:%d %b %Y} 23:59 (South Africa time)"),
             ("Location", site["location"]),
             ("Audience", "Advantage+ audience on, no interests added: let Meta find the people"),
             ("Placements", "Advantage+ placements (the reel fits Reels, Stories and Feed)")]
    ad = [("Name", n["ad"]),
          ("Identity", f"{BRAND_NAMES.get(brand, brand)} Facebook Page and Instagram account"),
          ("Ad setup", f"Use existing post: Instagram, pick {s['permalink']}"),
          ("Primary text", "Kept from the post, so its likes and comments carry over"),
          ("Call to action button", s["cta"]),
          ("Destination", f"Instant form {n['campaign']}_form" if lead else "Instagram Direct and Messenger"),
          ("URL parameters", s["url_params"])]
    out = [{"title": "Campaign", "rows": campaign}, {"title": "Ad set", "rows": adset}, {"title": "Ad", "rows": ad}]
    if lead:
        f = s["form"]
        rows = [("Form name", f["name"]), ("Form type", f"{f['type']}. {f['why_type']}"),
                ("Intro headline", f["headline"]), ("Intro text", f["description"])]
        for i, q in enumerate(f["questions"], 1):
            val = q["label"] + (" (filled in by Meta)" if q.get("prefill") else "")
            if q.get("options"):
                val += ": " + " / ".join(q["options"])
            rows.append((f"Question {i}", val))
        rows += [("Privacy policy link", f["privacy_url"]),
                 ("Thank-you screen", f"{f['thank_you']['headline']}. {f['thank_you']['text']}"),
                 ("Thank-you button", f"{f['thank_you']['button']}: {f['thank_you']['button_url']}")]
        out.append({"title": "Instant form", "rows": rows})
    else:
        rows = [("Greeting", s["greeting"])] + [(f"Question {i}", q) for i, q in enumerate(s["starters"], 1)]
        out.append({"title": "Message template", "rows": rows})
    out.append({"title": "Tracking and follow-up", "rows": [
        ("Website link", f"{s['landing_url']}?{s['url_params']}"),
        ("Where results land", "Meta Leads Center (Business Suite, All tools, Leads Center)" if lead
         else "Instagram and Messenger inbox, labelled with the ad name"),
        ("Follow up", "The same working day, by WhatsApp or a call; note the booking in the leads sheet"),
    ]})
    return out


def _checks(s: dict, caption: str) -> list[str]:
    out = ["Music: the reel must use original or licensed sound. Meta may refuse to run a reel with copyrighted "
           "music as an ad.",
           "Read the caption as a stranger would: does it say what they get and what to do?"]
    if _DEAL.search(caption or ""):
        out.append("The caption names a deal: check it is still on for the whole test, or the ad promises "
                   "something that has ended.")
    if _PRICE.search(caption or ""):
        out.append("The caption names a price: check it is the current price (live on the booking site or in "
                   "prices-approved.json) before paying to show it. Swing Shack moved to 2027 prices in November.")
    if s["theme"] == "assessment":
        out.append("Free assessment, not a fitting: keep fitting details out of the form and the reply.")
    return out


# ── build ────────────────────────────────────────────────────────────────

def build(brand_id: str, *, outcomes: list, media: list, running: dict | None, settings: dict | None,
          figures: dict | None, brief: dict | None, today: _dt.date) -> dict:
    site = SITES.get(brand_id) or {}
    by_id = {str(m.get("id")): m for m in media or [] if isinstance(m, dict)}
    used = set((running or {}).get("bodies") or []) - {""}
    taken = set((running or {}).get("post_ids") or [])
    cutoff = today - _dt.timedelta(days=WINDOW_DAYS)
    cpl = _brand_cpl(brief or {})
    budget = weekly_budget(settings or {}, today)
    committed = float((figures or {}).get("daily_run_rate") or 0) * 7
    state = {"budget": budget, "committed": committed, "room": max(0.0, budget - committed),
             "donors": donors(figures or {}, brief or {})}

    rows = []
    for o in outcomes or []:
        pid = str(o.get("post_id") or "")
        m = by_id.get(pid) or {}
        rows.append({**o, "post_id": pid, "caption": m.get("caption_preview") or o.get("caption_preview") or "",
                     "saves": m.get("saves") or 0, "shares": m.get("shares") or 0,
                     "thumbnail": m.get("thumbnail_url") or m.get("media_url") or ""})
    rows.sort(key=lambda r: (-(r.get("score") or 0), -(r.get("reach") or 0)))

    suggestions, skipped, seen = [], [], set()
    runnable = stills = 0
    for r in rows:
        pid, cap, fmt = r["post_id"], r["caption"], r.get("format_type")
        day = _date(r.get("timestamp"))

        def skip(reason):
            skipped.append({"post_id": pid, "permalink": r.get("permalink"), "caption": cap[:100], "reason": reason})

        if not day or day < cutoff:
            skip(f"Older than {WINDOW_DAYS} days.")
            continue
        if not (r.get("reach") or 0):
            skip("Meta returned no reach for it, so there is nothing to judge it on.")
            continue
        if norm(cap) in used or pid in taken:
            skip("Already running as an ad, or in a creative test.")
            continue
        theme = theme_of(cap)
        if not theme:
            skip("No offer in it: nothing to book or buy. Good for the feed, not for ad money.")
            continue
        if theme in seen:
            skip(f"A stronger {theme} post is suggested above.")
            continue
        video = fmt == "reel"
        product = theme in PRODUCT_THEMES
        if not video and not product:
            skip("A still image. Ads here are real human video; film this service instead.")
            continue
        if video and runnable >= MAX_RUNNABLE or not video and stills >= MAX_STILLS:
            skip("Enough suggestions for one week.")
            continue
        seen.add(theme)
        kind = "lead_form" if theme in LEAD_THEMES else ("messages" if video else "animated_still")
        objective = "OUTCOME_LEADS" if kind == "lead_form" else "OUTCOME_ENGAGEMENT"
        names = _names(brand_id, objective, theme, "reel" if video else "animated", today)
        landing = site.get(theme) or site.get("product" if product else "bookings") or ""
        s = {
            "post_id": pid, "permalink": r.get("permalink"), "thumbnail": r["thumbnail"],
            "caption": cap, "posted": day.isoformat(), "format": fmt, "theme": theme,
            "reach": r.get("reach") or 0, "saves": r["saves"], "shares": r["shares"], "score": r.get("score"),
            "score_basis": r.get("score_basis"),
            "ad_type": kind, "objective": objective, "ready": video, "names": names,
            "landing_url": landing, "url_params": _tags(names),
        }
        basis = ("including visits to the website it sent" if r.get("score_basis") == "conversion_backed"
                 else "from reach, likes, comments, saves and shares")
        s["why"] = (f"Reached {s['reach']:,} people, with {s['saves']} saves and {s['shares']} shares. "
                    f"The best {theme} post of the last {WINDOW_DAYS} days by score ({s['score']}, {basis}).")
        if kind == "animated_still":
            stills += 1
            s.update({"spend": None, "funding": None, "form": None, "setup": [], "checks": [
                "Animate the product itself (6 to 10 seconds, the product doing something), then it can run as a "
                "messages ad like a reel.",
                "The product must be the exact real one: check colour against the maker's listing."],
                "todo": "Make an animated still of this product"})
            suggestions.append(s)
            continue
        runnable += 1
        s["spend"] = _spend(kind, cpl)
        s["funding"] = _fund(s["spend"]["daily"], state)
        if kind == "lead_form":
            s["form"] = _form(theme, site, names, ads_creative.opening(cap))
            s["cta"] = s["form"]["thank_you"]["button"]
        else:
            s["form"] = None
            s["cta"] = "Send message"
            s["greeting"] = f"Hi! Ask us anything about what you saw in the post, we reply fast."
            s["starters"] = ["Is it in stock?", "What does it cost?", "Can I come in and try it?"]
        s["setup"] = _setup(s, brand_id, site, today)
        s["checks"] = _checks(s, cap)
        suggestions.append(s)

    return {
        "schema": SCHEMA, "brand_id": brand_id, "date": today.isoformat(),
        "budget": {"weekly": round(budget, 2), "committed": round(committed, 2),
                   "room_before": round(max(0.0, budget - committed), 2), "room_after": round(state["room"], 2),
                   "cost_per_lead": cpl},
        "posts_read": len(rows),
        "counts": {"posts": len(rows), "reels": sum(1 for r in rows if r.get("format_type") == "reel"),
                   "reels_with_reach": sum(1 for r in rows if r.get("format_type") == "reel" and (r.get("reach") or 0))},
        "suggestions": suggestions, "skipped": skipped,
        "running_known": running is not None,
    }


# ── page ─────────────────────────────────────────────────────────────────

_CSS = """
.sg{border:1px solid #ddd;border-radius:10px;padding:14px;margin:14px 0;background:#fff}
.sg .top{display:flex;gap:14px;align-items:flex-start}
.sg img{width:96px;height:120px;object-fit:cover;border-radius:6px;background:#eee;flex:none}
.sg h3{margin:0 0 4px}
.sg table{width:100%;border-collapse:collapse;font-size:14px}
.sg td{border-top:1px solid #eee;padding:5px 6px;vertical-align:top}
.sg td:first-child{width:34%;color:#555}
.sg code{word-break:break-all;font-size:12px}
.money{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}
.money div{border:1px solid #eee;border-radius:8px;padding:6px 10px}
.src-room{color:#1a7f37}.src-move{color:#9a6700}.src-extra{color:#cf222e}
@media (max-width:600px){.sg .top{flex-direction:column}.sg td:first-child{width:40%}}
"""

_KIND_LABEL = {"lead_form": "Lead form ad", "messages": "Messages ad", "animated_still": "Animated still first"}
_SOURCE_LABEL = {"room": "From unused budget", "move": "Moved from a weak ad set", "extra": "Needs Herman's yes"}


def _e(x) -> str:
    return escape(str(x if x is not None else ""))


def _value(v: str) -> str:
    if v.startswith("http") or "utm_" in v:
        return f"<code>{_e(v)}</code>"
    return _e(v)


def _card(i: int, s: dict) -> str:
    first = _e((s["caption"] or "").split("\n")[0][:120])
    img = f'<img src="{_e(s["thumbnail"])}" alt="" loading="lazy">' if s.get("thumbnail") else ""
    head = (f'<div class="top">{img}<div><h3>{i}. {_e(s["theme"].capitalize())} {_e(s["format"])}: '
            f'{_KIND_LABEL[s["ad_type"]]}</h3><p>{first}</p>'
            f'<p class="mute">Posted {_e(s["posted"])} &middot; <a href="{_e(s["permalink"])}" target="_blank" '
            f'rel="noopener">open the post</a></p><p>{_e(s["why"])}</p></div></div>')
    if s["ad_type"] == "animated_still":
        todo = "".join(f"<li>{_e(c)}</li>" for c in s["checks"])
        return f'<div class="sg">{head}<p><b>{_e(s["todo"])}.</b></p><ul>{todo}</ul></div>'
    sp, fu = s["spend"], s["funding"]
    money = (f'<div class="money"><div><b>{_r(sp["daily"])}</b> a day</div><div><b>{sp["days"]}</b> days</div>'
             f'<div><b>{_r(sp["total"])}</b> in all</div></div><p>Expect {_e(sp["expected_text"])}.</p>'
             f'<p><b class="src-{fu["source"]}">{_SOURCE_LABEL[fu["source"]]}.</b> {_e(fu["text"])}</p>')
    secs = "".join(
        f'<details{" open" if j == 0 else ""}><summary><b>{_e(sec["title"])}</b></summary><table>'
        + "".join(f"<tr><td>{_e(k)}</td><td>{_value(str(v))}</td></tr>" for k, v in sec["rows"])
        + "</table></details>" for j, sec in enumerate(s["setup"]))
    checks = "".join(f"<li>{_e(c)}</li>" for c in s["checks"])
    return f'<div class="sg">{head}{money}<h4>How to set it up in Ads Manager</h4>{secs}<h4>Before it goes live</h4><ul>{checks}</ul></div>'


def _section(doc: dict) -> str:
    brand = doc.get("brand_id")
    b = doc.get("budget") or {}
    parts = [f'<h2>{_e(BRAND_NAMES.get(brand, brand))}</h2>']
    if b.get("weekly"):
        parts.append(f'<p class="sub">Weekly budget {_r(b["weekly"])}. Running ad sets are set to {_r(b["committed"])} '
                     f'a week, so {_r(b["room_before"])} is free before these suggestions.</p>')
    else:
        parts.append('<p class="sub">No weekly ad budget is set for this brand yet.</p>')
    if not doc.get("running_known"):
        parts.append('<p class="mute">Could not check which posts already run as ads (the morning ads job has not '
                     'written that yet). Check in Ads Manager before building one.</p>')
    sugg = doc.get("suggestions") or []
    c = doc.get("counts") or {}
    if not sugg:
        why = ""
        if c.get("reels") and not c.get("reels_with_reach"):
            why = (f' Instagram returned no reach for any of the {c["reels"]} reels on file, so none can be ranked. '
                   'This clears when the morning Instagram read brings reel numbers in.')
        parts.append(f'<p class="mute">No post in the last {WINDOW_DAYS} days is ready to be an ad. '
                     f'{doc.get("posts_read", 0)} posts read.{why}</p>')
    parts += [_card(i, s) for i, s in enumerate(sugg, 1)]
    skipped = doc.get("skipped") or []
    if skipped:
        rows = "".join(f'<tr><td><a href="{_e(k.get("permalink"))}" target="_blank" rel="noopener">'
                       f'{_e(k["caption"][:70]) or "(no caption)"}</a></td><td>{_e(k["reason"])}</td></tr>'
                       for k in skipped[:40])
        parts.append(f'<details><summary class="mute">Posts left out, and why ({len(skipped)})</summary>'
                     f'<div class="scroll"><table>{rows}</table></div></details>')
    return "".join(parts)


def render_html(docs: list, missing: list | None = None) -> str:
    from . import ads_brief
    body = f"<style>{_CSS}</style>" + "".join(_section(d) for d in docs)
    for brand in missing or []:
        body += (f'<h2>{_e(BRAND_NAMES.get(brand, brand))}</h2><p class="mute">No posts on file yet. '
                 'They are read from Instagram by the morning jobs.</p>')
    date = max((d.get("date") or "" for d in docs), default="")
    sub = (f"{_e(date)} &middot; your own posts that should become ads, what each costs, where the money comes from "
           "and every setting &middot; suggestions only, nothing here changes an ad")
    return ads_brief._page("Ad suggestions", "suggest", sub, body)
