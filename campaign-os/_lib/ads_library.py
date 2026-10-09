"""Meta Ad Library — what other advertisers are running on the same subjects.

The Ad Library shows no results, so there is no "winner" to read off it. The
one honest signal is time: an advertiser who has kept paying for the same
video for months has a reason to. So for each subject this lists the
longest-running active video ads and how each one opens.

Two limits, both Meta's:

    Coverage   The API returns ordinary (non-political) ads only where they
               reached the EU or the UK. South African ads are in the Ad
               Library website and not in the API, so every subject also
               carries a link a person can open to see them.
    Access     The API needs a token whose owner has confirmed their identity
               with Meta. Without it every call is refused; that is recorded
               as NO_ACCESS and the links still work.

Read-only. The API's own ad_snapshot_url embeds the access token, so it is
never requested and never stored; links are built from the ad's public id.
"""
from __future__ import annotations

import datetime as _dt
import json
import urllib.parse

from . import ads_brain, ads_history

SCHEMA = "https://campaign-os/ads-library/v1"

# Where the API can see ordinary ads, nearest in language and golf culture.
API_COUNTRIES = ("GB", "IE")
HOME_COUNTRY = "ZA"
MAX_AGE_DAYS = 7
PER_THEME = 5
_FIELDS = ("id,page_id,page_name,ad_creative_bodies,ad_creative_link_titles,"
           "ad_delivery_start_time,publisher_platforms")

# What to search for each subject ads_creative.THEMES knows.
SEARCH_TERMS = {
    "fitting": "golf club fitting",
    "coaching": "golf lessons",
    "putter": "putter fitting",
    "irons": "custom fit irons",
    "driver": "driver fitting",
    "grip": "golf regrip",
    "bags": "golf bag",
    "membership": "indoor golf membership",
    "retail": "golf apparel",
}


def website_link(terms: str, country: str = HOME_COUNTRY) -> str:
    """The Ad Library website search a person can open, no login needed."""
    return "https://www.facebook.com/ads/library/?" + urllib.parse.urlencode({
        "active_status": "active", "ad_type": "all", "country": country,
        "media_type": "video", "q": terms, "search_type": "keyword_unordered"})


def ad_link(library_id) -> str:
    return f"https://www.facebook.com/ads/library/?id={urllib.parse.quote(str(library_id))}"


def _no_access(err: str) -> bool:
    e = (err or "").lower()
    return any(s in e for s in ("(#10)", "permission", "2332002", "confirm", "oauth",
                                "http 401", "http 403"))


def _ad(row: dict, today: _dt.date):
    started = ads_brain._parse_time(row.get("ad_delivery_start_time"))
    body = next((b for b in row.get("ad_creative_bodies") or [] if b), None)
    if not started or not row.get("id"):
        return None
    return {
        "library_id": str(row["id"]), "page_name": row.get("page_name"),
        "page_id": row.get("page_id"), "started": started.date().isoformat(),
        "days_running": (today - started.date()).days,
        "opening": ads_history.opening(body),
        "title": next((t for t in row.get("ad_creative_link_titles") or [] if t), None),
        "platforms": row.get("publisher_platforms") or [],
        "link": ad_link(row["id"]),
    }


def is_stale(research: dict | None, today: _dt.date, themes) -> bool:
    """Re-read weekly, or sooner when a brand starts advertising a new subject."""
    if not research or not research.get("date"):
        return True
    if (today - _dt.date.fromisoformat(research["date"])).days >= MAX_AGE_DAYS:
        return True
    return not set(themes) <= {t["theme"] for t in research.get("themes") or []}


def fetch(themes, token: str, *, get=None, api_version: str | None = None,
          today: _dt.date | None = None, max_pages: int = 2) -> dict:
    """Longest-running active video ads per subject. Stops at the first refusal:
    if the token has no Ad Library access, asking eight more times changes nothing."""
    ver = api_version or ads_brain.DEFAULT_API_VERSION
    if get is None:
        def get(path, params):
            return ads_brain._graph_get(path, token, params)
    today = today or _dt.date.today()
    out = {"schema": SCHEMA, "date": today.isoformat(), "status": "OK",
           "api_countries": list(API_COUNTRIES), "themes": [], "errors": []}
    refused = False
    for theme in sorted(t for t in themes if t in SEARCH_TERMS):
        terms = SEARCH_TERMS[theme]
        entry = {"theme": theme, "terms": terms, "ads": [], "seen": 0,
                 "home_link": website_link(terms),
                 "api_link": website_link(terms, API_COUNTRIES[0])}
        out["themes"].append(entry)
        if refused:
            continue
        rows, err = ads_brain._get_all(get, f"/{ver}/ads_archive", {
            "search_terms": terms, "search_type": "KEYWORD_UNORDERED",
            "ad_reached_countries": json.dumps(list(API_COUNTRIES)),
            "ad_active_status": "ACTIVE", "ad_type": "ALL", "media_type": "VIDEO",
            "fields": _FIELDS, "limit": 100}, max_pages=max_pages)
        if err:
            out["errors"].append(f"{theme}: {err}")
            if _no_access(err):
                out["status"], refused = "NO_ACCESS", True
            if not rows:
                continue
        entry["seen"] = len(rows)
        ads = sorted((a for a in (_ad(r, today) for r in rows) if a and a["opening"]),
                     key=lambda a: -a["days_running"])
        seen_pages: set = set()
        for a in ads:  # one ad per advertiser, so one big spender cannot fill the list
            if a["page_id"] in seen_pages:
                continue
            seen_pages.add(a["page_id"])
            entry["ads"].append(a)
            if len(entry["ads"]) == PER_THEME:
                break
    if out["status"] == "OK" and not any(t["ads"] for t in out["themes"]):
        out["status"] = "ERROR" if out["errors"] else "EMPTY"
    return out
