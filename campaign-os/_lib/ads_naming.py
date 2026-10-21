"""One naming rule and one UTM template for Meta ads, so reports in Meta and Google Analytics read the same.

The rule (proposed 2026-10-20, research/ads-measurement-naming-utm-ga4):

    campaign   <brand>_<objective>_<subject>_<monthYY>           ss_traffic_fitting_oct26
    ad set     <campaign>_set                                     ss_traffic_fitting_oct26_set
    ad         <subject>_<format>_v<n>                            fitting_video_v1
    UTM tags   utm_source=meta & utm_medium=paid_social & utm_campaign=<campaign> & utm_content=<ad>
               & utm_id=<Meta ad id>

The Meta ad id stays in ``utm_id`` so an ad still joins to Google Analytics after any rename. Pure functions only;
the changes themselves are made through _lib/ads_actions (preview, approve, undo).
"""
from __future__ import annotations

import datetime as _dt
import re

from . import ads_creative

BRAND_SHORT = {"swing-shack": "ss", "stick": "stick", "bag-drop": "bd"}
OBJECTIVE_SHORT = {
    "OUTCOME_TRAFFIC": "traffic", "LINK_CLICKS": "traffic", "OUTCOME_LEADS": "leads", "LEAD_GENERATION": "leads",
    "OUTCOME_ENGAGEMENT": "messages", "MESSAGES": "messages", "OUTCOME_AWARENESS": "awareness",
    "BRAND_AWARENESS": "awareness", "REACH": "awareness", "OUTCOME_SALES": "sales", "CONVERSIONS": "sales",
}
# When an ad is about several things, the one named first here wins.
THEME_ORDER = ("fitting", "coaching", "putter", "irons", "driver", "grip", "bags", "membership", "retail")
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
NAME_MAX = 100


def slug(text, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")[:limit].strip("_")


def month_tag(day: _dt.date) -> str:
    return f"{MONTHS[day.month - 1]}{day:%y}"


def theme(ad: dict) -> str:
    c = ad.get("creative") or {}
    found = ads_creative.subject((ad.get("campaign") or {}).get("name"), ad.get("ad_name"), c.get("title"), c.get("body"))
    return next((t for t in THEME_ORDER if t in found), "general")


def objective(ad: dict) -> str:
    return OBJECTIVE_SHORT.get(str((ad.get("campaign") or {}).get("objective") or "").upper(), "other")


def _day(ad: dict, today: _dt.date) -> _dt.date:
    start = (ad.get("adset") or {}).get("start_time") or (ad.get("campaign") or {}).get("start_time")
    try:
        return _dt.datetime.strptime(str(start), "%Y-%m-%dT%H:%M:%S%z").date()
    except ValueError:
        return today


def proposed(ad: dict, brand: str, today: _dt.date, *, version: int = 1) -> dict:
    """The standard names and tags for one ad. ``version`` separates two ads of the same subject and format."""
    t, fmt = theme(ad), (ad.get("creative") or {}).get("media_type") or "ad"
    campaign = f"{BRAND_SHORT.get(brand, slug(brand))}_{objective(ad)}_{t}_{month_tag(_day(ad, today))}"
    ad_slug = f"{t}_{slug(fmt)}_v{version}"
    return {
        "campaign_name": campaign[:NAME_MAX], "adset_name": f"{campaign}_set"[:NAME_MAX], "ad_name": ad_slug[:NAME_MAX],
        "url_tags": (f"utm_source=meta&utm_medium=paid_social&utm_campaign={campaign}&utm_content={ad_slug}"
                     f"&utm_id={ad.get('ad_id')}"),
    }


def valid_name(name) -> str:
    """A name Meta will take and a person can read, or ValueError with why not."""
    n = re.sub(r"\s+", " ", str(name or "")).strip()
    if not n:
        raise ValueError("The name is empty.")
    if len(n) > NAME_MAX:
        raise ValueError(f"A name can be at most {NAME_MAX} characters.")
    if any(ord(ch) < 32 for ch in n):
        raise ValueError("The name has a control character in it.")
    return n


def valid_tags(tags) -> str:
    """URL parameters for an ad: key=value pairs joined by &, no leading ?, no whole URL."""
    t = str(tags or "").strip().lstrip("?")
    if not t or "://" in t:
        raise ValueError("URL parameters look like utm_source=meta&utm_medium=paid_social, not a whole link.")
    if len(t) > 1000 or " " in t:
        raise ValueError("URL parameters cannot contain spaces and must be under 1,000 characters.")
    pairs = [p for p in t.split("&") if p]
    if not pairs or any("=" not in p or p.startswith("=") for p in pairs):
        raise ValueError("Every URL parameter needs a name and a value, like utm_source=meta.")
    keys = {p.split("=", 1)[0].lower() for p in pairs}
    if not {"utm_source", "utm_medium", "utm_campaign"} <= keys:
        raise ValueError("URL parameters need at least utm_source, utm_medium and utm_campaign.")
    return t
