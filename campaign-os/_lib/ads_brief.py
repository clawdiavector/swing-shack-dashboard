"""Ads brief — the daily and weekly read of what the ads brain found.

Pure functions over two inputs from ``_lib.ads_brain``:

    scored   score_snapshot() of the 31-day window. Scoring V1 is frozen and
             was measured on 31 days; the brief never scores a shorter window.
    recent   an insights-only snapshot of the last 7 days against the 7 before,
             for the numbers.

Plus the previous run's state, so the brief can say what is new, what was
resolved, and how many days each finding has been open. Nothing here talks to
Meta or changes an ad.
"""
from __future__ import annotations

import datetime as _dt
import html

SCHEMA = "https://campaign-os/ads-brief/v1"
BRAND_NAMES = {"stick": "Stick", "swing-shack": "Swing Shack"}
MAX_EVENTS = 400

# Order for "do next". Presentation only: it picks which findings lead the
# brief and does not change what the scoring found. (rule, status or None).
ACTION_PRIORITY = (
    ("lead_ads_not_running", None),
    ("click_goal_leak", None),
    ("fatigue", None),
    ("cost_per_lead_rising", None),
    ("spend_mix", "REALLOCATE"),
    ("below_average_ranking", None),
    ("home_page_destination", "HOME_PAGE"),
    ("single_ad_no_test", "MULTIPLE_CREATIVES_DELIVERY_CONCENTRATED"),
    ("open_ended_non_lead", "DECISION_DATE"),
    ("cpm_rising", None),
)


def sast_today(now: _dt.datetime | None = None) -> _dt.date:
    """The business day in South Africa (UTC+2, no daylight saving)."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return (now + _dt.timedelta(hours=2)).date()


def finding_key(f: dict) -> str:
    return "|".join((f["rule"], f.get("status") or "", f.get("ad_id") or f.get("level") or ""))


def _money(x) -> str:
    return "n/a" if x is None else (f"R{x:,.0f}" if x >= 100 else f"R{x:,.2f}")


def _totals(ads: list, window: str) -> dict:
    rows = [a[window] for a in ads if a.get(window)]
    t = {k: sum(r.get(k) or 0 for r in rows)
         for k in ("spend", "impressions", "link_clicks", "landing_page_views", "leads", "messages")}
    t["spend"] = round(t["spend"], 2)
    # Same definition as the brain's summary: spend on the ads that produced leads.
    lead_spend = sum(r.get("spend") or 0 for r in rows if r.get("leads"))
    t["cost_per_lead"] = round(lead_spend / t["leads"], 2) if t["leads"] else None
    return t


def _change(cur, prev):
    if cur is None or not prev:
        return None
    return round((cur - prev) / prev, 3)


def _numbers(recent: dict) -> dict:
    ads = recent.get("ads") or []
    cur, prev = _totals(ads, "current"), _totals(ads, "previous")
    return {
        "window": (recent.get("period") or {}).get("current"),
        "previous_window": (recent.get("period") or {}).get("previous"),
        "current": cur,
        "previous": prev,
        "change": {k: _change(cur.get(k), prev.get(k))
                   for k in ("spend", "leads", "cost_per_lead", "landing_page_views")},
        "ads": sorted(
            ({"ad_id": a["ad_id"], "ad_name": a["ad_name"],
              "campaign_name": (a.get("campaign") or {}).get("name"),
              "spend": a["current"]["spend"], "leads": a["current"]["leads"],
              "messages": a["current"]["messages"],
              "landing_page_views": a["current"]["landing_page_views"],
              "link_clicks": a["current"]["link_clicks"],
              "previous_spend": (a.get("previous") or {}).get("spend"),
              "previous_leads": (a.get("previous") or {}).get("leads")}
             for a in ads if a["current"]["spend"] > 0),
            key=lambda r: -r["spend"]),
    }


def _slim(f: dict, first_seen: str, today: _dt.date) -> dict:
    return {
        "key": finding_key(f), "rule": f["rule"], "status": f.get("status"),
        "severity": f["severity"], "level": f["level"],
        "ad_name": f.get("ad_name"), "campaign_name": f.get("campaign_name"),
        "what": f["what"], "action": f["action"],
        "first_seen": first_seen,
        "days_open": (today - _dt.date.fromisoformat(first_seen)).days,
    }


def top_actions(open_findings: list, limit: int = 3) -> list:
    """One line per rule, in ACTION_PRIORITY order, naming every ad it covers."""
    out = []
    for rule, status in ACTION_PRIORITY:
        hits = [f for f in open_findings
                if f["rule"] == rule and (status is None or f.get("status") == status)]
        if not hits:
            continue
        # Same rule can carry different actions (ranking diagnoses); keep them apart.
        by_action: dict = {}
        for f in hits:
            by_action.setdefault(f["action"], []).append(f)
        for action, group in by_action.items():
            out.append({
                "rule": rule, "status": group[0].get("status"), "severity": group[0]["severity"],
                "action": action, "why": group[0]["what"],
                "ads": [f["ad_name"] for f in group if f.get("ad_name")],
                "days_open": max(f["days_open"] for f in group),
            })
            if len(out) == limit:
                return out
    return out


def build_daily(brand_id: str, scored: dict, recent: dict, state: dict | None,
                today: _dt.date) -> tuple[dict, dict, list]:
    """Returns (brief, new_state, events). ``state`` is the previous run's
    new_state, or None on the first run."""
    day = today.isoformat()
    prev = (state or {}).get("findings") or {}
    baseline = state is None
    current = {finding_key(f): f for f in scored.get("findings") or []}

    open_findings, new_state_findings = [], {}
    for key, f in current.items():
        first_seen = (prev.get(key) or {}).get("first_seen") or day
        slim = _slim(f, first_seen, today)
        open_findings.append(slim)
        new_state_findings[key] = {k: slim[k] for k in
                                   ("rule", "status", "severity", "ad_name", "what", "action",
                                    "first_seen")}
    new = [] if baseline else [f for f in open_findings if f["key"] not in prev]
    resolved = [dict(v, key=k, resolved_on=day,
                     days_open=(today - _dt.date.fromisoformat(v["first_seen"])).days)
                for k, v in prev.items() if k not in current]
    # A failed read must not look like everything got fixed.
    read_failed = not (scored.get("summary") or {}).get("ads_delivered") and bool(scored.get("errors"))
    if read_failed:
        resolved, new_state_findings = [], dict(prev)

    events = ([{"date": day, "event": "opened", **{k: f[k] for k in
                ("key", "rule", "status", "severity", "ad_name", "what")}} for f in new]
              + [{"date": day, "event": "resolved", **{k: f.get(k) for k in
                  ("key", "rule", "status", "severity", "ad_name", "what", "days_open")}}
                 for f in resolved])

    actionable = [f for f in open_findings if f["severity"] in ("high", "medium")]
    brief = {
        "schema": SCHEMA, "kind": "daily", "brand_id": brand_id,
        "brand_name": BRAND_NAMES.get(brand_id, brand_id), "date": day,
        "scoring_version": scored.get("scoring_version"),
        "scoring_window": (scored.get("period") or {}).get("current"),
        "baseline": baseline, "read_failed": read_failed,
        "headline": {"actions": len(actionable), "new": len(new), "resolved": len(resolved),
                     "open": len(open_findings)},
        "summary_31d": scored.get("summary"),
        "numbers_7d": _numbers(recent),
        "top_actions": top_actions(open_findings),
        "new": new, "resolved": resolved,
        "open": sorted(open_findings,
                       key=lambda f: ({"high": 0, "medium": 1, "low": 2, "info": 3}[f["severity"]],
                                      -f["days_open"])),
        "rules_not_fired": scored.get("rules_not_fired") or [],
        "errors": sorted(set((scored.get("errors") or []) + (recent.get("errors") or []))),
        "note": "Recommendations only. Nothing here changes an ad.",
    }
    return brief, {"schema": SCHEMA, "last_brief_date": day, "findings": new_state_findings}, events


def build_weekly(daily: dict, events: list, today: _dt.date) -> dict:
    """The week ending yesterday: the daily's 7-day numbers plus what was
    opened and resolved in the last seven briefs."""
    since = (today - _dt.timedelta(days=6)).isoformat()
    week = [e for e in events or [] if since <= e.get("date", "") <= today.isoformat()]
    out = dict(daily)
    out.update({
        "kind": "weekly",
        "week": daily["numbers_7d"]["window"],
        "opened_this_week": [e for e in week if e["event"] == "opened"],
        "resolved_this_week": [e for e in week if e["event"] == "resolved"],
        "open_over_7_days": [f for f in daily["open"]
                             if f["days_open"] >= 7 and f["severity"] in ("high", "medium")],
    })
    out.pop("new", None)
    out.pop("resolved", None)
    return out


def merge_events(existing: list, new: list) -> list:
    return ((existing or []) + (new or []))[-MAX_EVENTS:]


# ── page ─────────────────────────────────────────────────────────────────

_CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#1c1d1f;--mute:#6b6f76;--line:#e3e1da;--high:#b3261e;
--med:#9a5b00;--low:#5b6470;--good:#1f6f43}
@media (prefers-color-scheme:dark){:root{--bg:#141516;--card:#1d1f21;--ink:#ececec;
--mute:#9aa0a6;--line:#2e3134;--high:#ff8a80;--med:#f2b866;--low:#a9b1bb;--good:#7fd1a2}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;margin:32px 0 4px}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:24px 0 8px}
.sub{color:var(--mute);margin:0 0 16px}.tabs a{display:inline-block;padding:6px 14px;
border:1px solid var(--line);border-radius:999px;margin-right:8px;color:var(--ink);
text-decoration:none}.tabs a.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.tile,.item{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile b{display:block;font-size:22px}.tile span{color:var(--mute);font-size:13px}
.item{margin-bottom:10px}.item p{margin:4px 0 0}.tag{font-size:12px;font-weight:600;
text-transform:uppercase;letter-spacing:.04em}.high{color:var(--high)}.medium{color:var(--med)}
.low,.info{color:var(--low)}.good{color:var(--good)}.mute{color:var(--mute);font-size:14px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left;white-space:normal}th{color:var(--mute);font-weight:600}
.warn{border-color:var(--high)}
"""


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _delta(change, lower_is_better=False, neutral=False) -> str:
    """Green when the number moved the right way. Spend is neither good nor bad."""
    if change is None:
        return '<span>no comparison</span>'
    if abs(change) < 0.005:
        return '<span>no change vs the 7 days before</span>'
    cls = "good" if (not neutral and (change < 0) == lower_is_better) else ""
    return f'<span class="{cls}">{change:+.0%} vs the 7 days before</span>'


def _section(brief: dict) -> str:
    n = brief["numbers_7d"]
    cur, ch = n["current"], n["change"]
    win = n.get("window") or {}
    h = brief["headline"]
    parts = [f'<h2>{_e(brief["brand_name"])}</h2>',
             f'<p class="sub">{h["actions"]} to act on · {h["new"]} new · '
             f'{h["resolved"]} resolved · last 7 days {_e(win.get("since"))} to {_e(win.get("until"))}</p>']
    if brief.get("read_failed"):
        parts.append('<div class="item warn"><b>Meta could not be read for this brief.</b>'
                     '<p>Findings below are carried over from the last good run.</p></div>')
    parts.append('<div class="tiles">'
                 f'<div class="tile"><b>{_money(cur["spend"])}</b><div>spend</div>{_delta(ch["spend"], neutral=True)}</div>'
                 f'<div class="tile"><b>{cur["leads"]}</b><div>leads</div>{_delta(ch["leads"])}</div>'
                 f'<div class="tile"><b>{_money(cur["cost_per_lead"])}</b><div>cost per lead</div>'
                 f'{_delta(ch["cost_per_lead"], lower_is_better=True)}</div>'
                 f'<div class="tile"><b>{cur["landing_page_views"]:,}</b><div>page visits</div>'
                 f'{_delta(ch["landing_page_views"])}</div></div>')

    parts.append('<h3>Do next</h3>')
    if not brief["top_actions"]:
        parts.append('<p class="mute">Nothing needs action.</p>')
    for i, a in enumerate(brief["top_actions"], 1):
        ads = f' <span class="mute">({_e(", ".join(a["ads"]))})</span>' if a["ads"] else ""
        age = f' · open {a["days_open"]} days' if a["days_open"] else ""
        parts.append(f'<div class="item"><span class="tag {a["severity"]}">{a["severity"]}{age}</span>'
                     f'<p><b>{i}. {_e(a["action"])}</b>{ads}</p><p class="mute">{_e(a["why"])}</p></div>')

    parts.append(_creative_section(brief.get("creative")))

    def listing(title, rows, empty, resolved=False):
        parts.append(f'<h3>{title}</h3>')
        if not rows:
            parts.append(f'<p class="mute">{empty}</p>')
        for f in rows:
            who = f' <span class="mute">{_e(f.get("ad_name"))}</span>' if f.get("ad_name") else ""
            tag = ('<span class="tag good">resolved</span>' if resolved
                   else f'<span class="tag {f["severity"]}">{f["severity"]}</span>')
            parts.append(f'<div class="item">{tag}{who}<p>{_e(f["what"])}</p></div>')

    if brief["kind"] == "weekly":
        listing("Opened this week", brief["opened_this_week"], "Nothing new this week.")
        listing("Resolved this week", brief["resolved_this_week"], "Nothing resolved this week.",
                resolved=True)
        listing("Open for a week or more", brief["open_over_7_days"],
                "Nothing has been open that long.")
    elif brief["baseline"]:
        parts.append('<h3>New since the last brief</h3><p class="mute">This is the first brief, '
                     'so everything below is the starting point.</p>')
    else:
        listing("New since the last brief", brief["new"], "Nothing new.")
        listing("Resolved since the last brief", brief["resolved"], "Nothing resolved.", resolved=True)

    parts.append('<h3>Ads, last 7 days</h3><div class="scroll"><table><tr><th>Ad</th><th>Spend</th>'
                 '<th>Leads</th><th>Chats</th><th>Page visits</th><th>Spend before</th></tr>')
    for r in n["ads"]:
        parts.append(f'<tr><td>{_e(r["ad_name"])}<br><span class="mute">{_e(r["campaign_name"])}</span>'
                     f'</td><td>{_money(r["spend"])}</td><td>{r["leads"]}</td><td>{r["messages"]}</td>'
                     f'<td>{r["landing_page_views"]:,}</td><td>{_money(r["previous_spend"])}</td></tr>')
    parts.append('</table></div>')

    rest = [f for f in brief["open"]]
    parts.append(f'<details><summary class="mute">All {len(rest)} open findings</summary>')
    for f in rest:
        who = f' <span class="mute">{_e(f.get("ad_name"))}</span>' if f.get("ad_name") else ""
        parts.append(f'<div class="item"><span class="tag {f["severity"]}">{f["severity"]} · open '
                     f'{f["days_open"]} days</span>{who}<p>{_e(f["what"])}</p>'
                     f'<p class="mute">{_e(f["action"])}</p></div>')
    parts.append('</details>')
    if brief["errors"]:
        parts.append('<p class="mute">Meta read notes: ' + _e("; ".join(brief["errors"])[:400]) + '</p>')
    return "".join(parts)


_RESULT_TEXT = {
    "CHALLENGER_WON": "The new creative won.",
    "CONTROL_WON": "The original ad won.",
    "NO_CLEAR_WINNER": "No clear winner after six weeks.",
    "INCONCLUSIVE_LOW_VOLUME": "Not enough results to call it.",
    "INCONCLUSIVE_CONTROL_STOPPED": "The original ad stopped running, so there was nothing to compare.",
}


def _arm_text(arm: dict, label: str) -> str:
    if not arm or not arm.get("results"):
        return f"{_money((arm or {}).get('spend') or 0)} spent, no {label}s yet"
    return (f"{arm['results']:,} {label}s at {_money(arm['cost_per_result'])} each "
            f"({_money(arm['spend'])} spent)")


def _creative_section(creative: dict | None) -> str:
    """Creative tests: proposed, running and recently closed."""
    if not creative:
        return ""
    parts = ['<h3>Creative to test</h3>']
    if not (creative["proposed"] or creative["running"] or creative["closed_recently"]):
        return parts[0] + '<p class="mute">No test to propose today.</p>'
    for t in creative["running"]:
        label = t["metric"]["label"]
        p = t.get("progress") or {}
        body = (f'<p>Original: {_e(_arm_text(p.get("control"), label))}.<br>'
                f'New: {_e(_arm_text(p.get("challenger"), label))}.</p>'
                if p else '<p class="mute">Launched today; numbers from tomorrow.</p>')
        parts.append(f'<div class="item"><span class="tag medium">test running · day '
                     f'{p.get("days", 0)}</span> <span class="mute">{_e(t["campaign_name"])}</span>'
                     f'{body}<p class="mute">{_e(t["design"]["rule"])}</p></div>')
    for t in creative["proposed"]:
        label = t["metric"]["label"]
        d = t["design"]
        rows = ""
        for c in t["challengers"]:
            if c["kind"] == "ORGANIC_POST":
                detail = (f'&ldquo;{_e(c["caption"])}&rdquo; '
                          f'<a href="{_e(c["permalink"])}" rel="noopener">see the post</a>')
            else:
                detail = f'Template <b>{_e(c["archetype"])}</b>. {_e(c["next_step"])}'
            ready = "ready to launch" if c["ready"] else "needs copy first"
            rows += (f'<p><b>{_e(c["title"])}</b> <span class="mute">({_e(c["format"])}, {ready})'
                     f'</span><br>{detail}<br><span class="mute">{_e(c["why"])}</span></p>')
        if d["estimated_days"] is None:
            timing = f'The original has no {label}s yet, so there is no way to estimate how long a test needs.'
        elif d["budget_warning"]:
            timing = (f'At the current budget this needs about {d["estimated_days"]} days, longer '
                      f'than the six-week limit. Raise the budget for the test or treat the result '
                      f'as a pointer.')
        else:
            timing = f'About {d["estimated_days"]} days at the current budget.'
        parts.append(
            f'<div class="item"><span class="tag low">proposed</span> '
            f'<span class="mute">{_e(t["campaign_name"])}</span>'
            f'<p>Test against <b>{_e(t["control"]["ad_name"])}</b> ({_e(t["control"]["format"])}): '
            f'{_e(_arm_text(t["control"], label))}.</p>{rows}'
            f'<p class="mute">{_e(d["how"])} {_e(d["rule"])} {_e(timing)}</p></div>')
    for t in creative["closed_recently"]:
        text = (_RESULT_TEXT.get(t.get("result"), "Closed.") if t["status"] == "DECIDED"
                else "Proposed and not launched within 30 days.")
        p = t.get("progress") or {}
        label = t["metric"]["label"]
        nums = (f'<p class="mute">Original: {_e(_arm_text(p.get("control"), label))}. '
                f'New: {_e(_arm_text(p.get("challenger"), label))}.</p>' if p else "")
        parts.append(f'<div class="item"><span class="tag good">closed</span> '
                     f'<span class="mute">{_e(t["campaign_name"])}</span><p>{_e(text)}</p>{nums}</div>')
    return "".join(parts)


def render_html(briefs: list, kind: str, missing: list | None = None) -> str:
    """One page, every brand stacked. ``missing`` names brands with no brief yet."""
    date = max((b["date"] for b in briefs), default="")
    title = "Weekly ads brief" if kind == "weekly" else "Daily ads brief"
    tabs = (f'<p class="tabs"><a href="/daily">&larr; Daily</a>'
            f'<a href="/ads-brief" class="{"on" if kind != "weekly" else ""}">Daily</a>'
            f'<a href="/ads-brief?kind=weekly" class="{"on" if kind == "weekly" else ""}">Weekly</a></p>')
    body = "".join(_section(b) for b in briefs)
    for brand in missing or []:
        body += (f'<h2>{_e(BRAND_NAMES.get(brand, brand))}</h2>'
                 '<p class="mute">No brief yet. It is written each morning at 07:15.</p>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title}</title><style>{_CSS}</style></head><body><main>'
            f'<h1>{title}</h1><p class="sub">{_e(date)} · Meta ads · recommendations only, '
            f'nothing here changes an ad</p>{tabs}{body}</main></body></html>')
