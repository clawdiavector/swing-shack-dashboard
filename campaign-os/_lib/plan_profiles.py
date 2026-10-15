"""plan_profiles.py — the shape of a plan depends on what kind of date it is.

A Black Friday push needs weeks of lead time, product shot in advance and a
run of countdown posts. A public holiday needs one post and a story. A season
needs a post every week for as long as it runs. Six shapes cover what the
calendar holds; `classify()` picks one from what is known about the date, and
the operator can pick another.

Rows are (days before the event, kind, title, channel, owner, note); a negative
number is after the event. Lead times follow the house classes in
marketing_calendar.DEFAULT_LEAD_TIME_TEMPLATE (major retail: production
deadline 21 days out; major sporting event: 14; normal campaign: 7).

A boost is only proposed together with a shoot for real video, and only when
the lead time allows both (ads use real human video only).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

Row = Tuple[int, str, str, str, str, str]

IG_FEED, IG_STORY = "instagram_feed", "instagram_story"
BOOST_VIDEO_TITLE = "Shoot a short real video with a person on camera"
BOOST_VIDEO_NOTE = "Needed for the boost. Ads use real human video only."


def _boost(offset: int, what: str) -> Row:
    return (offset, "boost", what, IG_FEED, "marketing",
            "Budget and audience to be set by the operator. Stop once the date has passed.")


# ── the shapes ────────────────────────────────────────────────────────

STANDARD: List[Row] = [
    (21, "research", "Confirm the date and the facts", "", "marketing",
     "Check the event date, venue, and anything we plan to say about it."),
    (14, "decide", "Pick the angle and approve the shot list", "", "marketing",
     "Choose one idea from the brief. This plan assumes it; change the idea here if you prefer another."),
    (12, "shoot", "Shoot real photos of the product or the space", "", "team",
     "Real photos only: no generated products or fake venue shots."),
    (9, "edit", "Pick the best shots and draft the captions", "", "marketing",
     "Captions go through the brand's voice check before review."),
    (7, "review", "Production deadline: everything approved", "", "marketing",
     "Anything not approved by now will not make the launch."),
    (6, "post", "Teaser post", IG_FEED, "marketing", "First public mention."),
    (3, "story", "Story countdown", IG_STORY, "marketing", "Three days to go."),
    (1, "story", "Reminder story", IG_STORY, "marketing", "Last nudge before the day."),
    (0, "post", "Event day post", IG_FEED, "marketing", "The main post."),
    (-2, "post", "Follow-up or recap post", IG_FEED, "marketing", "Thank-you, results or what's next."),
]

RETAIL_PUSH: List[Row] = [
    (60, "decide", "Pick the offer and the angle", "", "marketing",
     "What are we selling, at what price, and what is the one idea? Choose from the brief."),
    (45, "research", "Confirm stock and prices", "", "marketing",
     "Only promote what we hold. Check stock, sizes and prices with the shop."),
    (35, "shoot", "Shoot real photos of the products", "", "team",
     "Real product only: no generated products. Shoot enough for teasers, the offer and the countdown."),
    (28, "edit", "Pick the best shots and draft the captions", "", "marketing",
     "Captions go through the brand's voice check before review."),
    (21, "review", "Production deadline: everything approved", "", "marketing",
     "Anything not approved by now will not make the push."),
    (14, "post", "Teaser post", IG_FEED, "marketing", "First public mention. No prices yet."),
    (10, "post", "Product highlight post", IG_FEED, "marketing", "Show the product that leads the offer."),
    (7, "post", "Offer details post", IG_FEED, "marketing", "Dates, what is included, how to buy or DM."),
    (3, "story", "Story countdown", IG_STORY, "marketing", "Three days to go."),
    (2, "story", "Story: best sellers", IG_STORY, "marketing", "Real product, real price."),
    (1, "story", "Last-chance reminder story", IG_STORY, "marketing", "Last nudge before it starts."),
    (0, "post", "Launch day post", IG_FEED, "marketing", "The main post."),
    (-3, "story", "Story: last call", IG_STORY, "marketing", "If the offer is still running."),
    (-5, "post", "Recap or thank-you post", IG_FEED, "marketing", "What sold, what is left, what is next."),
]
RETAIL_PUSH_BOOST: List[Row] = [
    (35, "shoot", BOOST_VIDEO_TITLE, "", "team", BOOST_VIDEO_NOTE),
    _boost(7, "Boost the best-performing teaser or offer post"),
]

SPORT_EVENT: List[Row] = [
    (30, "research", "Check the fixture, the broadcast and what we can say", "", "marketing",
     "Confirm date and kick-off. Say nothing about results or players we cannot stand behind."),
    (21, "decide", "Pick the angle", "", "marketing",
     "How does this tie to Stick: fitting, clubs, gear? Choose one idea from the brief."),
    (17, "shoot", "Shoot real photos in the shop or at the range", "", "team",
     "Real photos only: no generated products or fake venue shots."),
    (14, "review", "Production deadline: everything approved", "", "marketing",
     "Anything not approved by now will not make it."),
    (7, "post", "Teaser post", IG_FEED, "marketing", "First public mention."),
    (3, "story", "Story countdown", IG_STORY, "marketing", "Three days to go."),
    (1, "story", "Reminder story", IG_STORY, "marketing", "Tomorrow."),
    (0, "story", "Game-day story", IG_STORY, "marketing", "Keep it light and in the moment."),
    (0, "post", "Game-day post", IG_FEED, "marketing", "The main post."),
    (-1, "post", "Reaction post", IG_FEED, "marketing",
     "Written after the result, not before. A reaction, not a script."),
]
SPORT_EVENT_BOOST: List[Row] = [
    (17, "shoot", BOOST_VIDEO_TITLE, "", "team", BOOST_VIDEO_NOTE),
    _boost(5, "Boost the best-performing teaser"),
]

SERVICE_PUSH: List[Row] = [
    (21, "decide", "Pick the offer and the booking path", "", "marketing",
     "What are we asking people to book, and does the booking link work? Choose from the brief."),
    (14, "shoot", "Shoot real fitting or coaching footage", "", "team",
     "A real session with a real customer or coach, with permission. Photos and clips."),
    (10, "edit", "Pick the best shots and draft the captions", "", "marketing",
     "Captions go through the brand's voice check before review."),
    (7, "review", "Production deadline: everything approved", "", "marketing",
     "Anything not approved by now will not make the launch."),
    (5, "post", "Teaser post", IG_FEED, "marketing", "First public mention."),
    (3, "story", "Story with the booking link", IG_STORY, "marketing", "Show how to book."),
    (1, "story", "Booking reminder story", IG_STORY, "marketing", "Slots left, if that is true."),
    (0, "post", "Main post", IG_FEED, "marketing", "The main post, with the call to book."),
    (-3, "post", "Follow-up post: how it went", IG_FEED, "marketing", "A real result or a real comment."),
]
SERVICE_PUSH_BOOST: List[Row] = [
    (14, "shoot", BOOST_VIDEO_TITLE, "", "team", BOOST_VIDEO_NOTE),
    _boost(5, "Boost the best-performing teaser to people who can book"),
]

LIGHT: List[Row] = [
    (7, "research", "Confirm the date and the facts", "", "marketing",
     "Check the date and anything we plan to say about it."),
    (3, "edit", "Draft the caption and pick a photo", "", "marketing",
     "Real photo only. Caption goes through the brand's voice check."),
    (1, "review", "Approve the post", "", "marketing", "Anything not approved by now will not go."),
    (0, "post", "Post", IG_FEED, "marketing", "One post for the day."),
    (0, "story", "Story", IG_STORY, "marketing", "Optional: a story to match."),
]

SEASON_START: List[Row] = [
    (30, "decide", "Decide the shape of the season", "", "marketing",
     "What is the one idea running through it? How often do we post? Choose from the brief."),
    (21, "shoot", "Shoot a batch of real photos and clips", "", "team",
     "Shoot enough for the first weeks in one go. Real photos only."),
    (14, "edit", "Pick the best shots and draft the first captions", "", "marketing",
     "Captions go through the brand's voice check before review."),
    (10, "review", "Approve the opening posts", "", "marketing",
     "Anything not approved by now will not make the launch."),
    (3, "story", "Story countdown", IG_STORY, "marketing", "Three days to the start."),
    (0, "post", "Launch post", IG_FEED, "marketing", "The season starts."),
    (0, "story", "Launch story", IG_STORY, "marketing", "A story to match."),
]
SEASON_BOOST: List[Row] = [
    (21, "shoot", BOOST_VIDEO_TITLE, "", "team", BOOST_VIDEO_NOTE),
]

MAX_SEASON_WEEKS = 8


def season_rows(duration_days: int) -> List[Row]:
    """A post every week of the season, a mid-season boost, and a wrap-up."""
    rows: List[Row] = []
    weeks = max(0, min(MAX_SEASON_WEEKS, (duration_days - 1) // 7))
    for k in range(1, weeks + 1):
        rows.append((-7 * k, "post", f"Week {k + 1} post", IG_FEED, "marketing",
                     "Keep the idea running. Reuse the batch shot at the start."))
    if duration_days > 7:
        rows.append((-(duration_days - 1), "post", "Wrap-up post", IG_FEED, "marketing",
                     "Close the season: thank people, say what is next."))
    return rows


# ── choosing a shape ──────────────────────────────────────────────────

PROFILES: Dict[str, Dict[str, Any]] = {
    "standard": {"label": "Standard", "boost_min_lead": 14},
    "retail_push": {"label": "Retail push", "boost_min_lead": 42},
    "sport_event": {"label": "Sport event", "boost_min_lead": 21},
    "service_push": {"label": "Service push", "boost_min_lead": 21},
    "season": {"label": "Season", "boost_min_lead": 28},
    "light": {"label": "Light touch", "boost_min_lead": 10 ** 6},
}

_ARC_RE = re.compile(r"\barc\b")
_SPORT_RE = re.compile(
    r"\b(sport|golf|rugby|springboks?|open|masters|ryder|cup|tournament|championships?|"
    r"tour|pga|wimbledon|olympics?|epic)\b")


def _words(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def _pillar_names(pillars: Any) -> List[str]:
    if isinstance(pillars, dict):
        return [str(k).lower() for k in pillars]
    if isinstance(pillars, (list, tuple)):
        return [str(p.get("pillar_id") or p.get("id") or "") if isinstance(p, dict) else str(p)
                for p in pillars if p]
    return []


def classify(meta: Optional[Dict[str, Any]], name: str = "") -> Tuple[str, str]:
    """(profile, plain-language reason) from what is known about the date.

    meta may hold: tier, shopping_moment, category, duration_days,
    lead_time_class, pillars. Anything missing is simply not used.
    """
    m = meta or {}
    tier = m.get("tier") or ""
    lead_class = m.get("lead_time_class") or ""
    duration = int(m.get("duration_days") or 0)
    category = _words(m.get("category"))
    blob = _words(name, category)

    if lead_class == "major_retail":
        return "retail_push", "It is marked as a major retail moment."
    if lead_class == "major_sporting_event":
        return "sport_event", "It is marked as a major sporting event."
    if lead_class in ("content_moment", "reactive_opportunity"):
        return "light", "It is marked as a light content moment."
    if _ARC_RE.search(category):
        return "season", "It is an ongoing arc, so it needs a steady run of posts."
    if m.get("shopping_moment") or "shopping" in category or "retail" in category:
        if tier == "C-PIN":
            return "light", "A small shopping date: one post is enough."
        return "retail_push", "It is a shopping moment, so it needs product shot early and a run of posts."
    if duration >= 30:
        return "season", f"It runs for {duration} days, so it needs a steady run of posts."
    if _SPORT_RE.search(blob):
        if tier == "C-PIN":
            return "light", "A small sport date: one post is enough."
        return "sport_event", "It is a sporting event, so the posts follow the build-up and the day."
    if duration >= 14:
        return "season", f"It runs for {duration} days, so it needs a steady run of posts."
    pillars = " ".join(_pillar_names(m.get("pillars")))
    if "fitting" in pillars or "coaching" in pillars:
        return "service_push", "It is for fitting or coaching, so the aim is bookings."
    if tier == "C-PIN":
        return "light", "A smaller date: one post and a story."
    return "standard", "No special type, so the standard shape."


def event_kind(e: Dict[str, Any]) -> str:
    """The type of a calendar entry, for its icon: one of PROFILES, worked out
    from the entry's own fields (tier, category, shopping_moment, pillars,
    lead_time_class, start and end). The same rules choose a plan's shape, so
    the icon and the plan always agree."""
    start = str(e.get("start") or e.get("event_start") or e.get("date") or "")[:10]
    end = str(e.get("end") or e.get("event_end") or "")[:10]
    duration = 0
    try:
        if start and end:
            from datetime import date as _d
            duration = (_d.fromisoformat(end) - _d.fromisoformat(start)).days + 1
    except ValueError:
        duration = 0
    lead = e.get("lead_time_class")
    meta = {
        "tier": e.get("tier"),
        "category": e.get("category"),
        "shopping_moment": bool(e.get("shopping_moment")),
        "pillars": e.get("pillars"),
        "lead_time_class": None if lead == "normal_campaign" else lead,  # the default is not a choice
        "duration_days": duration,
    }
    return classify(meta, str(e.get("name") or e.get("title") or ""))[0]


def rows_for(profile: str, lead_days: int, duration_days: int = 0) -> List[Row]:
    """The rows for a shape, with the boost and its real-video shoot added only
    when the lead time allows both."""
    profile = profile if profile in PROFILES else "standard"
    rows: List[Row] = []
    boost: List[Row] = []
    if profile == "retail_push":
        rows, boost = list(RETAIL_PUSH), RETAIL_PUSH_BOOST
    elif profile == "sport_event":
        rows, boost = list(SPORT_EVENT), SPORT_EVENT_BOOST
    elif profile == "service_push":
        rows, boost = list(SERVICE_PUSH), SERVICE_PUSH_BOOST
    elif profile == "light":
        rows = list(LIGHT)
    elif profile == "season":
        rows = list(SEASON_START) + season_rows(duration_days or 14)
        boost = SEASON_BOOST + [_boost(-7 * min(3, max(1, (duration_days or 14) // 14)),
                                       "Boost the best-performing post so far")]
    else:
        rows = list(STANDARD)
        boost = [(12, "shoot", BOOST_VIDEO_TITLE, "", "team", BOOST_VIDEO_NOTE),
                 _boost(5, "Boost the best-performing teaser")]
    if boost and lead_days >= PROFILES[profile]["boost_min_lead"]:
        rows += boost
    return rows
