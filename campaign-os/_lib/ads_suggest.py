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

from . import ads_creative, ads_learn, ads_naming

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

AD_TYPES = ("lead_form", "messages", "traffic", "awareness")
TYPE_LABEL = {"lead_form": "Leads (instant form)", "messages": "Messages (chats)", "traffic": "Traffic (website visits)",
              "awareness": "Awareness (video views)", "animated_still": "Animated still first"}
OBJECTIVE_OF = {"lead_form": "OUTCOME_LEADS", "messages": "OUTCOME_ENGAGEMENT", "traffic": "OUTCOME_TRAFFIC",
                "awareness": "OUTCOME_AWARENESS", "animated_still": "OUTCOME_ENGAGEMENT"}
_DM_CUE = re.compile(r"\bdm\b|direct message|message us|whatsapp|inbox us|send us a message", re.I)
_WEB_CUE = re.compile(r"link in (?:our )?bio|book online|our (?:web)?site|website|\.co\.za|shop online|online store",
                      re.I)
_BOOK_CUE = re.compile(r"\bbook\b|booking|reserve|sign up|claim", re.I)
# A no-offer reel earns awareness money only when it clearly beat the brand's usual post.
AWARENESS_LIFT = 1.5

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
        "home": "https://stickgolf.co.za/",
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
        "home": "https://swingshack.co.za/",
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


def _n(x, word) -> str:
    return f"{x:,} {word}{'' if x == 1 else 's'}"


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


def unit_costs(brief: dict) -> dict:
    """The brand's own cost per result in the last 7 days, per ad type, where it has one."""
    ads = ((brief or {}).get("numbers_7d") or {}).get("ads") or []
    chats = [a for a in ads if a.get("messages")]
    visits = [a for a in ads if a.get("landing_page_views") and not a.get("leads") and not a.get("messages")]

    def per(rows, key):
        n = sum(a[key] for a in rows)
        return round(sum(a.get("spend") or 0 for a in rows) / n, 2) if n else None
    return {"lead_form": _brand_cpl(brief), "messages": per(chats, "messages"),
            "traffic": per(visits, "landing_page_views"), "awareness": None}


# What a week-long test aims for, per type, and what one result is called.
_TARGET = {"lead_form": (LEADS_PER_WEEK_TARGET, "lead"), "messages": (5, "chat"), "traffic": (50, "page visit"),
           "awareness": (None, "view")}


def _spend(kind: str, cost: float | None, source: str | None = None) -> dict:
    target, unit = _TARGET[kind]
    daily = FLOOR_DAILY
    if cost and target:
        daily = max(FLOOR_DAILY, min(MAX_DAILY, math.ceil(cost * target / TEST_DAYS / 5) * 5))
    total = daily * TEST_DAYS
    if cost:
        n = int(total // cost)
        each = _r(cost) if cost >= 10 else f"R{cost:.2f}"
        where = source or f"the brand's cost per {unit} in the last 7 days"
        text = f"about {n:,} {unit}{'s' if n != 1 else ''} at about {each} each ({where})"
    elif kind == "awareness":
        n, text = None, ("no cost per view on record; Ads Manager shows the estimated reach on the ad set. "
                         "The real result is the audience of people who watched it")
    else:
        n, text = None, f"no cost per {unit} on record yet; this first week sets it"
    return {"daily": daily, "days": TEST_DAYS, "total": total, "expected_results": n, "expected_text": text,
            "unit_cost": cost}


def _cost_for(kind: str, theme, costs: dict, learned: dict | None) -> tuple[float | None, str | None]:
    """What one result costs: from suggested ads that ran (same subject first, then same type), else the last 7 days."""
    ld = learned or {}
    for bucket in (((ld.get("by_type_theme") or {}).get(f"{kind}:{theme}")), (ld.get("by_type") or {}).get(kind)):
        if bucket and bucket.get("cost_per_result"):
            n = bucket["tests"]
            return bucket["cost_per_result"], f"from {n} suggested ad{'s' if n != 1 else ''} that ran"
    return costs.get(kind), None


def choose_type(theme, caption: str, site: dict, *, standout: bool, costs: dict,
                learned: dict | None = None) -> dict:
    """Score each ad type on what the post offers and what its caption asks people to do. Highest wins; on a tie,
    leads, then messages, then traffic, then awareness. Returns the type, the reason and why not the others."""
    service, product = theme in LEAD_THEMES, theme in PRODUCT_THEMES
    dm, web, book = bool(_DM_CUE.search(caption)), bool(_WEB_CUE.search(caption)), bool(_BOOK_CUE.search(caption))
    own_page = bool(theme and site.get(theme))
    score = {
        "lead_form": (2 if service else 0) + (1 if service and book else 0),
        "messages": (2 if product else 0) + (3 if dm and (service or product) else 0),
        "traffic": (3 + (1 if own_page else 0)) if web and (service or product) else 0,
        "awareness": 3 if not theme and standout else 0,
    }
    record = []
    for k in AD_TYPES:
        if score[k]:
            nudge, line = ads_learn.adjust(learned, k, theme)
            score[k] = max(0, score[k] + nudge)
            if line:
                record.append(line)
    kind = max(AD_TYPES, key=lambda k: (score[k], -AD_TYPES.index(k)))
    cpl = costs.get("lead_form")
    if kind == "lead_form":
        reason = ("A service people book" + (", and the caption asks them to book" if book else "")
                  + ". An instant form takes their name and number without leaving Instagram"
                  + (f"; lead forms are the brand's only priced result (about {_r(cpl)} a lead)." if cpl else "."))
    elif kind == "messages":
        reason = (("The caption asks people to message" if dm else "A product people ask about before they buy")
                  + ": stock, price, sizes. A chat is the shortest way to the sale, and it is how the shops sell now.")
    elif kind == "traffic":
        reason = ("The caption sends people to the website"
                  + (f", and {site.get(theme)} is a page for this exact offer" if own_page else "")
                  + ". Paying for page visits matches what the post asks people to do.")
    else:
        reason = ("Nothing to book or buy, but it clearly beat the brand's usual post. Paying for views builds an "
                  "audience of people who watched it, and the next leads or messages ad goes to them first.")
    if record:
        reason += " " + " ".join(record)
    leans = "Possible, but the caption leans harder towards the type chosen."
    why_not = {
        "lead_form": ("Nothing to book here, so a form has nothing to ask for." if not service else
                      "A form would work, but the caption points people elsewhere, so the ad would contradict the post."),
        "messages": ("The caption does not invite a chat and it is not a product people ask about."
                     if not (dm or product) else leans),
        "traffic": ("The caption does not send people to the website. Traffic ads were paused on 26 Oct until landing "
                    "pages were fixed, so only use one where the post itself points to a page." if not web else leans),
        "awareness": ("There is an offer: pay for the action (a lead, chat or visit), not only for views." if theme else
                      "Its numbers are not far enough above the brand's usual post to pay for views."),
    }
    return {"ad_type": kind, "type_reason": reason,
            "alternatives": [{"ad_type": k, "label": TYPE_LABEL[k], "why_not": why_not[k]}
                             for k in AD_TYPES if k != kind]}


def _fund(need_daily: float, state: dict) -> dict:
    """Unused room first; then the weakest running ad sets, topped up by whatever room is left; then an ask."""
    need = need_daily * TEST_DAYS
    if state["room"] >= need:
        left = ("" if state["room"] == state["free"] else
                f"; after the suggestions above, {_r(state['room'])} is still free")
        text = (f"Unused room in the {_r(state['budget'])} weekly budget: the running ad sets are set to "
                f"{_r(state['committed'])} a week, which leaves {_r(state['free'])}{left}. "
                f"This test uses {_r(need)} of it.")
        state["room"] -= need
        return {"source": "room", "text": text}
    got, moves = state["room"] / TEST_DAYS, []
    for d in state["donors"]:
        if got >= need_daily:
            break
        if d["daily"] <= 0:
            continue
        take = min(d["daily"], need_daily - got)
        moves.append((d, take))
        got += take
    if moves and got >= need_daily - 0.01:
        lines = []
        for d, take in moves:
            if not d["results"]:
                lines.append(f"Pause {d['name']}: {_r(d['spend'])} spent in the last 7 days for no leads or chats. "
                             f"Use {_r(take)} a day of its {_r(d['daily'])} here.")
            else:
                lines.append(f"Lower {d['name']} from {_r(d['daily'])} to {_r(d['daily'] - take)} a day: "
                             f"{_r(d['spend'] / d['results'])} a result in the last 7 days, well above the brand's usual.")
            d["daily"] -= take
        if state["room"] > 0:
            lines.append(f"The other {_r(state['room'])} comes from the unused room in the weekly budget.")
            state["room"] = 0.0
        lines.append("The weekly total stays the same.")
        return {"source": "move", "from": moves[0][0]["name"], "moves": [d["name"] for d, _ in moves],
                "text": " ".join(lines)}
    if moves:
        part = ", ".join(f"{d['name']} ({_r(d['daily'])} a day, "
                         + ("no leads or chats" if not d["results"] else "costly results") + ")" for d, _ in moves)
        short = need - got * TEST_DAYS
        return {"source": "extra", "moves": [d["name"] for d, _ in moves], "extra_amount": round(short, 2),
                "text": (f"Not enough room or weak spend to cover all of it. Part can come from {part}"
                         + (" and the unused room" if state["room"] > 0 else "")
                         + f"; the other {_r(short)} for this week-long test needs Herman's yes.")}
    if not state["budget"]:
        text = f"No weekly ad budget is set. Ask Herman for {_r(need)} for this week-long test."
    else:
        text = (f"The {_r(state['budget'])} weekly budget is already set to be spent and no running ad set is weak "
                f"enough to take from. Ask Herman for an extra {_r(need)} for this week-long test.")
    return {"source": "extra", "text": text, "extra_amount": need}


# ── settings ─────────────────────────────────────────────────────────────

def _names(brand: str, objective: str, theme: str, fmt: str, today: _dt.date) -> dict:
    short = ads_naming.BRAND_SHORT.get(brand, ads_naming.slug(brand))
    campaign = f"{short}_{ads_naming.OBJECTIVE_SHORT.get(objective, 'other')}_{theme}_{ads_naming.month_tag(today)}"
    return {"campaign": campaign, "adset": f"{campaign}_set", "ad": f"{theme}_{fmt}_v1"}


def _tags(names: dict, content: str | None = None) -> str:
    return (f"utm_source=meta&utm_medium=paid_social&utm_campaign={names['campaign']}"
            f"&utm_content={content or names['ad']}&utm_id={{{{ad.id}}}}")


def _form(theme: str, site: dict, names: dict, opening: str | None) -> dict:
    headline, cta, extra = _FORM_COPY[theme]
    return {
        "name": f"{names['campaign']}_form", "type": "Higher intent",
        "why_type": ("Adds a review screen before the form is sent, so fewer people tap through by accident. "
                     "Since 1 Oct, 93 leads gave 1 booking in ClubLab (wiki: research/lead-conversion-check-2026-11-13)."),
        "headline": headline, "description": opening or headline, "cta": cta,
        "questions": _CONTACT + [dict(q) for q in extra],
        "privacy_url": site["privacy"],
        "thank_you": {"headline": "Thanks, we have your details",
                      "text": "We will be in touch to find a time that suits you.",
                      "button": "Book now",
                      "button_url": f"{site['bookings']}?" + _tags(names, f"{names['ad']}_thankyou").split("&utm_id")[0]},
    }


def _setup(s: dict, brand: str, site: dict, today: _dt.date) -> list[dict]:
    start = today + _dt.timedelta(days=1)
    end = start + _dt.timedelta(days=TEST_DAYS - 1)
    kind = s["ad_type"]
    lead = kind == "lead_form"
    n = s["names"]
    objective = {"lead_form": "Leads", "messages": "Engagement", "traffic": "Traffic", "awareness": "Awareness"}[kind]
    location = {"lead_form": "Instant forms", "messages": "Message apps: Instagram and Messenger",
                "traffic": "Website", "awareness": "Not asked for this objective"}[kind]
    goal = {"lead_form": "Maximise number of leads", "messages": "Maximise number of conversations",
            "traffic": "Maximise number of landing page views",
            "awareness": "Maximise ThruPlay views (people who watch 15 seconds or the whole reel)"}[kind]
    destination = {"lead_form": f"Instant form {n['campaign']}_form", "messages": "Instagram Direct and Messenger",
                   "traffic": "Website", "awareness": "Website (only for those who tap the button)"}[kind]
    campaign = [("Name", n["campaign"]), ("Buying type", "Auction"),
                ("Objective", objective),
                ("Special ad categories", "None"),
                ("Advantage+ campaign budget", "Off: the budget sits on the ad set, where the budget guard pauses it")]
    adset = [("Name", n["adset"]),
             ("Conversion location", location),
             ("Performance goal", goal),
             ("Budget", f"Daily budget {_r(s['spend']['daily'])}"),
             ("Schedule", f"Start {start:%d %b %Y} 00:00, end {end:%d %b %Y} 23:59 (South Africa time)"),
             ("Location", site["location"]),
             ("Audience", (f"Custom audience {s['audience']} (people who watched at least half the awareness "
                           "reel), with Advantage+ audience on so Meta can go wider once they have seen it")
              if s.get("audience") else "Advantage+ audience on, no interests added: let Meta find the people"),
             ("Placements", "Advantage+ placements (the reel fits Reels, Stories and Feed)")]
    ad = [("Name", n["ad"]),
          ("Identity", f"{BRAND_NAMES.get(brand, brand)} Facebook Page and Instagram account"),
          ("Ad setup", f"Use existing post: Instagram, pick {s['permalink']}"),
          ("Primary text", "Kept from the post, so its likes and comments carry over"),
          ("Call to action button", s["cta"]),
          ("Destination", destination)]
    if kind in ("traffic", "awareness"):
        ad += [("Website URL", s["landing_url"]), ("Meta pixel", "On (website events), so visits and bookings count")]
    ad.append(("URL parameters", s["url_params"]))
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
    elif kind == "messages":
        rows = [("Greeting", s["greeting"])] + [(f"Question {i}", q) for i, q in enumerate(s["starters"], 1)]
        out.append({"title": "Message template", "rows": rows})
    elif kind == "awareness":
        out.append({"title": "Audience to build", "rows": [
            ("Custom audience", f"Audiences, Create, Custom audience, Video: people who watched at least 50% of this "
                                f"reel (ThruPlay), last 30 days. Name it {n['campaign']}_watched50"),
            ("Use it", "After the 7 days, aim the next leads or messages ad for this brand at this audience first"),
        ]})
    out.append({"title": "Tracking and follow-up", "rows": [
        ("Website link", f"{s['landing_url']}?{s['url_params']}"),
        ("Where results land", {"lead_form": "Meta Leads Center (Business Suite, All tools, Leads Center)",
                                "messages": "The Instagram and Messenger inbox",
                                "traffic": "Google Analytics, paid social, by campaign name; bookings in ClubLab",
                                "awareness": "Ads Manager: ThruPlays and reach; the audience fills over the week"}[kind]),
        ("Follow up", {"lead_form": "The same working day, by WhatsApp or a call; note the booking in the leads sheet",
                       "messages": "Reply the same working day; note any sale in the leads sheet",
                       "traffic": "Check page visits and bookings after 3 days; stop early if visitors leave at once",
                       "awareness": "Build the next ad for the watched audience before this one ends"}[kind]),
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
    if s.get("audience"):
        out.append("The watched audience needs at least 100 people in it. If Ads Manager says it is too small, "
                   "run the ad without it.")
    if s["ad_type"] == "traffic":
        out.append("Open the landing page on a phone first: it must load fast and show the Book button without "
                   "scrolling. Traffic ads were paused on 26 Oct because visitors left the landing pages.")
    if s["theme"] == "assessment":
        out.append("Free assessment, not a fitting: keep fitting details out of the form and the reply.")
    return out


# ── build ────────────────────────────────────────────────────────────────

def build(brand_id: str, *, outcomes: list, media: list, running: dict | None, settings: dict | None,
          figures: dict | None, brief: dict | None, today: _dt.date, learned: dict | None = None,
          audiences: list | None = None) -> dict:
    site = SITES.get(brand_id) or {}
    by_id = {str(m.get("id")): m for m in media or [] if isinstance(m, dict)}
    used = set((running or {}).get("bodies") or []) - {""}
    taken = set((running or {}).get("post_ids") or [])
    cutoff = today - _dt.timedelta(days=WINDOW_DAYS)
    costs = unit_costs(brief or {})
    budget = weekly_budget(settings or {}, today)
    committed = float((figures or {}).get("daily_run_rate") or 0) * 7
    free = max(0.0, budget - committed)
    state = {"budget": budget, "committed": committed, "room": free, "free": free,
             "donors": donors(figures or {}, brief or {})}

    rows = []
    for o in outcomes or []:
        pid = str(o.get("post_id") or "")
        m = by_id.get(pid) or {}
        rows.append({**o, "post_id": pid, "caption": m.get("caption_preview") or o.get("caption_preview") or "",
                     "saves": m.get("saves") or 0, "shares": m.get("shares") or 0,
                     "thumbnail": m.get("thumbnail_url") or m.get("media_url") or ""})
    rows.sort(key=lambda r: (-(r.get("score") or 0), -(r.get("reach") or 0)))
    scores = sorted(r.get("score") or 0 for r in rows if (r.get("reach") or 0))
    reaches = sorted(r.get("reach") or 0 for r in rows if (r.get("reach") or 0))
    typical_score = scores[len(scores) // 2] if scores else 0
    typical_reach = reaches[len(reaches) // 2] if reaches else 0

    follow = (audiences or [None])[0]
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
        standout = (fmt == "reel" and (r.get("score") or 0) >= AWARENESS_LIFT * typical_score > 0
                    and (r.get("reach") or 0) >= typical_reach)
        if not theme and not standout:
            skip("No offer in it, and its numbers are not far above the brand's usual post. "
                 "Good for the feed, not for ad money.")
            continue
        if not theme and "brand" in seen:
            skip("A stronger no-offer reel is suggested above for awareness.")
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
        seen.add(theme or "brand")
        pick = (choose_type(theme, cap, site, standout=standout, costs=costs, learned=learned) if video else
                {"ad_type": "animated_still", "type_reason": "A product photo cannot run as it is; animated, it can "
                 "run as a messages ad.", "alternatives": []})
        kind = pick["ad_type"]
        objective = OBJECTIVE_OF[kind]
        names = _names(brand_id, objective, theme or "brand", "reel" if video else "animated", today)
        landing = (site.get("home") if not theme else
                   site.get(theme) or site.get("product" if product else "bookings")) or ""
        s = {
            "brand_id": brand_id, "post_id": pid, "permalink": r.get("permalink"), "thumbnail": r["thumbnail"],
            "caption": cap, "posted": day.isoformat(), "format": fmt, "theme": theme,
            "reach": r.get("reach") or 0, "saves": r["saves"], "shares": r["shares"], "score": r.get("score"),
            "score_basis": r.get("score_basis"),
            "ad_type": kind, "objective": objective, "ready": video, "names": names,
            "type_label": TYPE_LABEL[kind], "type_reason": pick["type_reason"], "alternatives": pick["alternatives"],
            "landing_url": landing, "url_params": _tags(names),
        }
        basis = ("including visits to the website it sent" if r.get("score_basis") == "conversion_backed"
                 else "from reach, likes, comments, saves and shares")
        s["why"] = (f"Reached {s['reach']:,} people, with {_n(s['saves'], 'save')} and {_n(s['shares'], 'share')}. "
                    + (f"The best {theme} post of the last {WINDOW_DAYS} days by score ({s['score']}, {basis})." if theme else
                     f"Score {s['score']} against {typical_score} for the brand's usual post ({basis})."))
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
        s["spend"] = _spend(kind, *_cost_for(kind, theme, costs, learned))
        s["funding"] = _fund(s["spend"]["daily"], state)
        s["form"] = None
        if kind == "lead_form":
            s["form"] = _form(theme, site, names, ads_creative.opening(cap))
            s["cta"] = s["form"]["cta"]
        elif kind == "traffic":
            s["cta"] = "Book now" if theme in LEAD_THEMES else "Shop now"
        elif kind == "awareness":
            s["cta"] = "Learn more"
        else:
            s["cta"] = "Send message"
            s["greeting"] = "Hi! Ask us anything about what you saw in the post."
            s["starters"] = ["Is it in stock?", "What does it cost?", "Can I come in and try it?"]
        s["audience"] = None
        if follow and kind in ("lead_form", "messages"):
            s["audience"] = follow["name"]
            s["type_reason"] += (f" Aim it first at {follow['name']}: the people who watched the awareness reel "
                                 f"that started {follow['started']}, so they already know the brand.")
            follow = None
        s["schedule"] = {"start": (today + _dt.timedelta(days=1)).isoformat(),
                         "end": (today + _dt.timedelta(days=TEST_DAYS)).isoformat()}
        s["setup"] = _setup(s, brand_id, site, today)
        s["checks"] = _checks(s, cap)
        suggestions.append(s)

    return {
        "schema": SCHEMA, "brand_id": brand_id, "date": today.isoformat(),
        "budget": {"weekly": round(budget, 2), "committed": round(committed, 2),
                   "room_before": round(max(0.0, budget - committed), 2), "room_after": round(state["room"], 2),
                   "cost_per_lead": costs.get("lead_form"), "unit_costs": costs,
                   "typical_score": typical_score},
        "learned": learned or {},
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

_KIND_LABEL = {"lead_form": "Leads ad (instant form)", "messages": "Messages ad", "traffic": "Traffic ad (website)",
               "awareness": "Awareness ad (video views)", "animated_still": "Animated still first"}
_SOURCE_LABEL = {"room": "From unused budget", "move": "Moved from a weak ad set", "extra": "Needs Herman's yes"}


def _e(x) -> str:
    return escape(str(x if x is not None else ""))


def _value(v: str) -> str:
    if v.startswith("http") or "utm_" in v:
        return f"<code>{_e(v)}</code>"
    return _e(v)


def _card(i: int, s: dict) -> str:
    first = _e((s["caption"] or "").split("\n")[0][:120])
    img = f'<img src="{_e(s["thumbnail"])}" alt="" loading="lazy" onerror="this.style.visibility=&quot;hidden&quot;">' if s.get("thumbnail") else ""
    head = (f'<div class="top">{img}<div><h3>{i}. {_e((s["theme"] or "brand").capitalize())} {_e(s["format"])}: '
            f'{_KIND_LABEL[s["ad_type"]]}</h3><p>{first}</p>'
            f'<p class="mute">Posted {_e(s["posted"])} &middot; <a href="{_e(s["permalink"])}" target="_blank" '
            f'rel="noopener">open the post</a></p><p>{_e(s["why"])}</p></div></div>')
    if s["ad_type"] == "animated_still":
        todo = "".join(f"<li>{_e(c)}</li>" for c in s["checks"])
        return f'<div class="sg">{head}<p><b>{_e(s["todo"])}.</b></p><ul>{todo}</ul></div>'
    sp, fu = s["spend"], s["funding"]
    alts = "".join(f"<li><b>{_e(a['label'])}:</b> {_e(a['why_not'])}</li>" for a in s.get("alternatives") or [])
    typ = (f'<p><b>Why this type:</b> {_e(s.get("type_reason"))}</p>'
           + (f'<details><summary class="mute">Other types considered</summary><ul>{alts}</ul></details>'
              if alts else ""))
    money = (f'<div class="money"><div><b>{_r(sp["daily"])}</b> a day</div><div><b>{sp["days"]}</b> days</div>'
             f'<div><b>{_r(sp["total"])}</b> in all</div></div><p>Expected result: {_e(sp["expected_text"])}.</p>'
             f'<p><b class="src-{fu["source"]}">{_SOURCE_LABEL[fu["source"]]}.</b> {_e(fu["text"])}</p>')
    secs = "".join(
        f'<details{" open" if j == 0 else ""}><summary><b>{_e(sec["title"])}</b></summary><table>'
        + "".join(f"<tr><td>{_e(k)}</td><td>{_value(str(v))}</td></tr>" for k, v in sec["rows"])
        + "</table></details>" for j, sec in enumerate(s["setup"]))
    checks = "".join(f"<li>{_e(c)}</li>" for c in s["checks"])
    build = (f'<form method="post" action="/ads-brief/build"><input type="hidden" name="brand" value="{_e(s.get("brand_id"))}">'
             f'<input type="hidden" name="post_id" value="{_e(s["post_id"])}"><input type="hidden" name="ad_type" '
             f'value="{_e(s["ad_type"])}"><button type="submit">Build in Meta (switched off)</button> '
             '<span class="mute">Shows everything first; nothing is made until you confirm.</span></form>')
    return f'<div class="sg">{head}{typ}{money}{build}<h4>How to set it up in Ads Manager</h4>{secs}<h4>Before it goes live</h4><ul>{checks}</ul></div>'


def _past(log: list) -> str:
    rows = [e for e in log or [] if e.get("status") in ("RUNNING", "DONE")]
    if not rows:
        return ""
    rows.sort(key=lambda e: e.get("started") or "", reverse=True)
    body = []
    for e in rows[:20]:
        ex, ac = e.get("expected") or {}, e.get("actual") or {}
        unit = ex.get("unit") or "result"
        exp = f"{_r(ex['cost_per_result'])} a {unit}" if ex.get("cost_per_result") else "no estimate"
        got = (f"{ac.get('results', 0)} {unit}s for {_r(ac.get('spend') or 0)}"
               + (f" ({_r(ac['cost_per_result'])} each)" if ac.get("cost_per_result") else ""))
        verdict = (ads_learn.VERDICT_TEXT.get(e.get("verdict"), "") if e["status"] == "DONE"
                   else f"Running since {e.get('started')}")
        body.append(f'<tr><td><a href="{_e(e.get("permalink"))}" target="_blank" rel="noopener">'
                    f'{_e((e.get("caption") or "")[:60]) or "(post)"}</a><br><span class="mute">'
                    f'{_e(TYPE_LABEL.get(e["ad_type"], e["ad_type"]))}</span></td><td>{_e(exp)}</td>'
                    f'<td>{_e(got)}</td><td><b>{_e(verdict)}</b></td></tr>')
    return ('<h3>How past suggestions did</h3><div class="scroll"><table><tr><th>Ad</th><th>Expected</th>'
            '<th>Got</th><th>Verdict</th></tr>' + "".join(body) + '</table></div>'
            '<p class="mute">Matched to the ads that ran by campaign name or caption. Judged after 7 days on the '
            "ad's own result; bookings are not linked yet.</p>")


def _ahead(ahead: dict | None) -> str:
    if not ahead or not (ahead.get("items") or ahead.get("stock_gaps")):
        return ""
    w = ahead.get("window") or {}
    out = [f'<h3>Coming up: ads to plan for {_e(w.get("start"))} to {_e(w.get("end"))}</h3>']
    for it in ahead.get("items") or []:
        label = _KIND_LABEL.get(it["ad_type"], it["ad_type"])
        cost = (f'{_r(it["spend"]["daily"])} a day from {_e(it["start"])} for {it["spend"]["days"]} days '
                f'({_r(it["spend"]["total"])}). ' if it.get("spend") else "")
        out.append(f'<div class="sg"><b>{_e(it["title"])}</b>: {_e(label)}'
                   f'<p class="mute">{_e(it["why"])}</p>'
                   + (f'<p>{_e(it["type_reason"])}</p>' if it.get("type_reason") else "")
                   + f'<p>{cost}{_e(it["money"])}</p></div>')
    gaps = ahead.get("stock_gaps") or []
    if gaps:
        lis = "".join(f'<li><b>{_e(g["name"])}</b> ({_e(g["status"])} in stock'
                      + (f', {_e(g["qty"])} on hand' if g.get("qty") is not None else "")
                      + f'): {_e(g["todo"])}</li>' for g in gaps)
        out.append(f'<p><b>In stock, no post planned:</b></p><ul>{lis}</ul>')
    return "".join(out)


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
    parts.append(_ahead(doc.get("ahead")))
    parts.append(_past(doc.get("log")))
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


_PLAIN_TYPE = {"lead_form": "a booking enquiry form ad", "messages": "a chat ad (people message us)",
               "traffic": "a website visit ad", "awareness": "a video ad that warms people up for a later offer"}
_PLAIN_UNIT = {"lead": "enquiries", "chat": "chats", "page visit": "website visits", "view": "views"}


def herman_text(docs: list) -> str:
    """One message for Herman: a numbered yes or no per ad, cost and where the money comes from, plain words.
    Ads that need money over the budget come first, because only he can say yes to those."""
    items = [(d, s) for d in docs for s in d.get("suggestions") or [] if s.get("spend")]
    order = {"extra": 0, "move": 1, "room": 2}
    items.sort(key=lambda it: order.get((it[1].get("funding") or {}).get("source"), 3))
    date = max((d.get("date") or "" for d in docs), default="")
    start = _dt.date.fromisoformat(date) + _dt.timedelta(days=1) if date else None
    head = f"Ads for the week from {start.day} {start:%b}." if start else "Ads for the week."
    out = [head + " Please reply with the numbers you say yes to (for example: yes 1 and 3).", ""]
    total = over = 0.0
    for i, (d, s) in enumerate(items, 1):
        sp, fu = s["spend"], s.get("funding") or {}
        first = re.sub(r"\s+", " ", (s.get("caption") or "").split("\n")[0]).strip()
        first = first if len(first) <= 60 else first[:60].rsplit(" ", 1)[0].rstrip(".,;:!?") + "..."
        unit = (s.get("names") and ads_learn.UNIT.get(s["ad_type"])) or "result"
        expect = (f"Expect about {sp['expected_results']} {_PLAIN_UNIT.get(unit, unit)}."
                  if sp.get("expected_results") else "First time, so no estimate yet.")
        if fu.get("source") == "room":
            money = "from this week's unused budget."
        elif fu.get("source") == "move":
            money = "moved from a running ad that is not working, so the week's total stays the same."
        else:
            extra = fu.get("extra_amount") or sp["total"]
            over += extra
            money = f"needs {_r(extra)} extra, over the budget."
        total += sp["total"]
        what = f"{(s.get('theme') or 'brand')} {s.get('format') or 'post'}"
        out.append(f"{i}. {BRAND_NAMES.get(d.get('brand_id'), d.get('brand_id'))}: run the {what} \"{first}\" as "
                   f"{_PLAIN_TYPE[s['ad_type']]}. {_r(sp['daily'])} a day for {sp['days']} days = {_r(sp['total'])}. "
                   f"{expect} Money: {money}")
    if not items:
        out.append("No ads to decide this week.")
    else:
        out += ["", f"Total: {_r(total)} for {len(items)} ad{'s' if len(items) != 1 else ''}"
                + (f", of which {_r(over)} is over the budget." if over else ", all within the budget.")]
    return "\n".join(out)


def render_html(docs: list, missing: list | None = None) -> str:
    from . import ads_brief
    note = herman_text(docs)
    rows = min(24, note.count("\n") + 2)
    body = (f"<style>{_CSS}</style>"
            f'<details><summary><b>For Herman</b>: the week\'s ads as one numbered list to copy into an email</summary>'
            f'<textarea readonly rows="{rows}" style="width:100%;font:inherit">{_e(note)}</textarea>'
            '<p class="mute">Nothing is sent from here. Copy it into one email to Herman.</p></details>'
            + "".join(_section(d) for d in docs))
    for brand in missing or []:
        body += (f'<h2>{_e(BRAND_NAMES.get(brand, brand))}</h2><p class="mute">No posts on file yet. '
                 'They are read from Instagram by the morning jobs.</p>')
    date = max((d.get("date") or "" for d in docs), default="")
    sub = (f"{_e(date)} &middot; your own posts that should become ads, what each costs, where the money comes from "
           "and every setting &middot; suggestions only, nothing here changes an ad")
    return ads_brief._page("Ad suggestions", "suggest", sub, body)
