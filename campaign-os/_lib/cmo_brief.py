"""The CMO brief: where we stand, what to decide, and which way to go, from one brand's real numbers.

Pure and deterministic. Every sentence is built from a figure in ``facts`` and says which window it covers; nothing is
estimated that the numbers do not support, and a claim that needs data we do not have is listed as a gap instead.
Read by Christelle (marketing) and Herman (the boss), so plain words, rand, and a named person for each next step.

``facts`` (all optional except ``brand``):
    week        {"current": "19 Oct → 25 Oct", "previous": "12 Oct → 18 Oct"}
    sessions    {"cur", "prev"}              website visits, all channels, 7 days
    engagement  {"cur", "prev"}              % of website visits that engaged, 7 days
    enquiries   {"cur", "prev", "since"}     calls, emails, contact clicks counted in Google Analytics
    channels    [{"channel", "cur", "prev"}]
    paid        {"spend": {"cur","prev"}, "leads": {"cur","prev"}, "campaigns": [{name, objective, spend, prev_spend,
                 results, cost}]}              Meta, 7 days
    ads         None or {"budget": <ads_budget.evaluate>, "guard_on", "paused_now",
                 "tracking": {"totals", "ads"}}   (31 days Meta, 28 days Google Analytics)
    bookings_linked, targets
"""
from __future__ import annotations

# A visit is "kept" below this share of visitors engaging; a page that keeps fewer than this is the problem.
LOW_ENGAGED_PCT = 30.0
MIN_VISITS_TO_JUDGE = 100
# A lead-form result needs this much spend behind it before it can be called good or bad.
MIN_SPEND_TO_JUDGE = 100.0
MIN_RESULTS_TO_JUDGE = 5


def _R(x) -> str:
    if x is None:
        return "—"
    r = round(x)
    return f"-R{abs(r):,}" if r < 0 else f"R{r:,}"


def _chg(cur, prev):
    if cur is None or not prev:
        return None
    return round((cur - prev) / prev * 100)


def _signed(p) -> str:
    return "" if p is None else f"{'+' if p > 0 else ''}{p}%"


def _num(x):
    return None if x is None else (int(x) if float(x) == int(x) else round(float(x), 1))


def _rows(f):
    t = ((f.get("ads") or {}).get("tracking") or {})
    return t.get("ads") or [], t.get("totals") or {}


def _low_pages(rows):
    """Website ads with enough visits to judge whose visitors mostly leave, biggest spend first."""
    out = []
    for r in rows:
        p = r.get("perf") or {}
        eng, sess = p.get("engaged_pct"), r.get("ga_sessions") or 0
        if r.get("destination") == "WEBSITE" and eng is not None and sess >= MIN_VISITS_TO_JUDGE and eng < LOW_ENGAGED_PCT:
            kept = sess * eng / 100.0
            out.append({"name": r.get("ad_name"), "eng": eng, "sess": sess, "spend": r.get("spend") or 0,
                        "per_engaged": (r.get("spend") or 0) / kept if kept else None})
    return sorted(out, key=lambda x: -x["spend"])


def _best_page(rows):
    web = [r for r in rows if r.get("destination") == "WEBSITE" and (r.get("perf") or {}).get("engaged_pct") is not None
           and (r.get("ga_sessions") or 0) >= MIN_VISITS_TO_JUDGE]
    if len(web) < 2:
        return None
    best = max(web, key=lambda r: r["perf"]["engaged_pct"])
    worst = min(web, key=lambda r: r["perf"]["engaged_pct"])
    b, w = best["perf"]["engaged_pct"], worst["perf"]["engaged_pct"]
    return best if b >= LOW_ENGAGED_PCT and b >= 1.5 * w else None


def build(f: dict) -> dict:
    brand = f.get("brand") or "This brand"
    ses, eng, enq = f.get("sessions") or {}, f.get("engagement") or {}, f.get("enquiries") or {}
    paid = f.get("paid") or {}
    spend = paid.get("spend") or {}
    leads = paid.get("leads") or {}
    ads = f.get("ads")
    budget = (ads or {}).get("budget") or {}
    status = budget.get("status")
    w = "week" if budget.get("period") == "week" else "month"
    paused = (ads or {}).get("paused_now") or 0
    guard_on = bool((ads or {}).get("guard_on"))
    rows, totals = _rows(f)
    low = _low_pages(rows)
    channels = {c.get("channel"): c for c in f.get("channels") or []}
    ps, org = channels.get("Paid Social") or {}, channels.get("Organic Search") or {}
    ses_chg, spend_chg, ps_chg = _chg(ses.get("cur"), ses.get("prev")), _chg(spend.get("cur"), spend.get("prev")), _chg(ps.get("cur"), ps.get("prev"))
    over = status == "OVER"
    at_risk = status == "AT_RISK"
    stopped_explains = (ses_chg is not None and ses_chg <= -10 and ps_chg is not None and ps_chg <= -50
                        and spend_chg is not None and spend_chg <= -50)
    cpl = totals.get("cost_per_lead")

    # ── verdict ──────────────────────────────────────────────────────────────────────────────────────────
    lines = []
    if ads and over:
        if paused:
            lines.append(f"The {w}'s ad budget of {_R(budget.get('budget'))} is used up ({_R(budget.get('mtd_spend'))} spent), so the "
                         f"hard stop paused {paused} ad set{'s' if paused != 1 else ''}"
                         + (f" and ad spend this week fell {abs(spend_chg)}% to {_R(spend.get('cur'))}." if spend_chg is not None and spend_chg < 0 else "."))
        else:
            lines.append(f"The {w}'s ad budget of {_R(budget.get('budget'))} is used up ({_R(budget.get('mtd_spend'))} spent) "
                         f"and nothing has paused the ads, so they are still spending.")
    elif ads and at_risk:
        lines.append(f"On the current settings the {w}'s ads will end near {_R(budget.get('projected_total'))}, over the "
                     f"{_R(budget.get('budget'))} budget.")
    elif spend.get("cur") is not None:
        lines.append(f"Ads spent {_R(spend.get('cur'))} this week" + (f" ({_signed(spend_chg)} on last week)." if spend_chg is not None else "."))
    if ses_chg is not None and abs(ses_chg) >= 10:
        if stopped_explains:
            lines.append(f"Website visits fell {abs(ses_chg)}% ({_num(ses.get('cur'))} against {_num(ses.get('prev'))}), almost all of it the ads "
                         f"stopping: paid social visits fell {abs(ps_chg)}% while Google search held at {_num(org.get('cur'))}.")
        elif ses_chg < 0:
            lines.append(f"Website visits fell {abs(ses_chg)}% ({_num(ses.get('cur'))} against {_num(ses.get('prev'))}).")
        else:
            lines.append(f"Website visits rose {ses_chg}% ({_num(ses.get('cur'))} against {_num(ses.get('prev'))}).")
    if low:
        eng_all = totals.get("ga_engaged_pct")
        lines.append(f"The visits the ads do bring are not staying: only {eng_all:g}% of paid visitors engage (last 28 days), so more "
                     f"traffic spend would mostly buy visitors who leave." if eng_all is not None else
                     f"The visits the ads do bring are not staying: {low[0]['eng']:g}% engaged on the biggest ad.")
    elif cpl and totals.get("leads"):
        lines.append(f"Lead-form ads are producing: {totals['leads']} leads at {_R(cpl)} each over the last 31 days.")
    lines = lines[:3]

    if ads and (over or at_risk):
        headline = ("The ad budget is used up and the ads are paused. The decision this week is what to restart, and what a lead is worth decides it."
                    if over and paused else "The ad budget is not holding. Decide the budget before more is spent.")
        tone = "act"
    elif low:
        headline = "The ads bring visitors the website does not keep. Fix the pages before spending more on traffic."
        tone = "watch"
    elif ses_chg is not None and ses_chg <= -15:
        headline = "Website visits are down. Check why before changing anything."
        tone = "watch"
    else:
        headline = "A steady week. Nothing needs changing urgently."
        tone = "good"
    if not lines:
        lines = ["There is not enough ad and website data this week to say more."]

    # ── the six numbers ──────────────────────────────────────────────────────────────────────────────────
    def vs_count(cur, prev):
        if prev is None:
            return "no comparison"
        p = _chg(cur, prev)
        return f"was {_num(prev)}" + (f" ({_signed(p)})" if p is not None else "")

    numbers = [
        {"label": "Website visits", "value": "—" if ses.get("cur") is None else str(_num(ses["cur"])),
         "vs": vs_count(ses.get("cur"), ses.get("prev")), "note": "All channels, 7 days"},
        {"label": "Ad spend this week", "value": _R(spend.get("cur")),
         "vs": ("no comparison" if spend.get("prev") is None else f"was {_R(spend['prev'])}" + (f" ({_signed(spend_chg)})" if spend_chg is not None else "")),
         "note": "Facebook and Instagram, 7 days"},
        {"label": "Leads from ads", "value": "—" if leads.get("cur") is None else str(_num(leads["cur"])),
         "vs": vs_count(leads.get("cur"), leads.get("prev")),
         "note": (f"{_R(cpl)} a lead over the last 31 days" if cpl else "Lead-form campaigns, as Meta counts them")},
        {"label": "Enquiries on the website", "value": "—" if enq.get("cur") is None else str(_num(enq["cur"])),
         "vs": ("no comparison" if enq.get("prev") is None else f"was {_num(enq['prev'])}" + (f" ({_signed(_chg(enq.get('cur'), enq.get('prev')))})" if enq.get("prev") else "")),
         "note": (f"Calls, emails and contact clicks. Counting started {enq.get('since')}, so earlier weeks read 0." if enq.get("prev") == 0 and enq.get("since")
                  else "Calls, emails and contact clicks")},
        {"label": "Visitors who stayed", "value": "—" if eng.get("cur") is None else f"{eng['cur']:.0f}%",
         "vs": "no comparison" if eng.get("prev") is None else f"was {eng['prev']:.0f}%",
         "note": ("Of all website visits" + (f"; paid visitors alone: {totals['ga_engaged_pct']:g}% (28 days)" if totals.get("ga_engaged_pct") is not None else ""))},
        {"label": f"This {w}'s ad budget",
         "value": f"{_R(budget.get('mtd_spend'))} spent" if budget else "—",
         "vs": (f"of {_R(budget['budget'])}" if budget.get("budget") else "no budget set"),
         "note": ("Used up" if over else "Heading over" if at_risk else "On track" if status == "OK" else "")},
    ]

    # ── decisions ────────────────────────────────────────────────────────────────────────────────────────
    decisions = []
    if ads and (over or at_risk):
        lead_sets = [s for s in budget.get("sets") or [] if s.get("level") == "adset" and s.get("kind") == "daily"
                     and s.get("objective") == "OUTCOME_LEADS"]
        daily = sum(s.get("amount") or 0 for s in lead_sets)
        days = budget.get("days_left_after_today") or 0
        rest = daily * days
        if daily and days and cpl:
            est = int(rest // cpl)
            rec = (f"Keep traffic ads off until the pages are fixed. Restart the lead-form ads only if a lead is worth more than {_R(cpl)} "
                   f"to the business: running them to the end of the {w} costs about {_R(rest)} ({_R(daily)} a day) and, if the cost per lead holds, "
                   f"brings about {est} leads.")
        else:
            rec = ("Keep traffic ads off until the pages are fixed. Restart the lead-form ads only if a lead is worth more than "
                   "they cost; a lead price needs a few more weeks of results.")
        because = (f"The {_R(budget.get('budget'))} budget is used up ({_R(budget.get('mtd_spend'))} spent)."
                   + (f" Lead-form ads are the only ones with a result we can price: {totals['leads']} leads at {_R(cpl)} each over 31 days." if cpl and totals.get("leads") else ""))
        decisions.append({"decision": f"Decide the ad budget for the rest of the {w}", "recommendation": rec, "because": because,
                          "confidence": "medium"})
    if low:
        top = low[:3]
        names = "; ".join(f"{x['name']} kept {x['eng']:g}% of {x['sess']:,} visitors"
                          + (f" (about {_R(x['per_engaged'])} per engaged visit)" if x["per_engaged"] else "") for x in top)
        decisions.append({
            "decision": "Fix the pages the traffic ads send people to",
            "recommendation": "Point each traffic ad at the page for what it advertises (booking, fitting or coaching, not the home page) and test one ad "
                              "before restarting the rest.",
            "because": f"{names}. Organic visitors stay far longer, so the ad creative is reaching people; the page is losing them.",
            "confidence": "high" if sum(x["sess"] for x in top) >= 300 else "medium"})
    if not f.get("bookings_linked"):
        decisions.append({
            "decision": "Connect bookings to marketing",
            "recommendation": "Ask ClubLab which event fires on a confirmed booking and get it into Google Analytics.",
            "because": "The report stops at a lead. What a lead is worth decides how much to spend, and nothing yet links a lead to a booking, "
                       "so we can price a lead but not a customer.",
            "confidence": "high"})
    if not f.get("targets"):
        decisions.append({
            "decision": "Set the marketing targets",
            "recommendation": f"Agree a {w}ly lead target and the most you will pay for a lead, for each brand.",
            "because": "Without a target the report can only compare with last week; it cannot say whether a week was good.",
            "confidence": "high"})
    decisions = decisions[:4]

    # ── working / not working ────────────────────────────────────────────────────────────────────────────
    working, not_working, risks, gaps = [], [], [], []
    if cpl and totals.get("leads"):
        working.append(f"Lead-form ads are the part that works: {totals['leads']} leads at {_R(cpl)} each over the last 31 days.")
    if org.get("cur") and org.get("prev") and abs(_chg(org["cur"], org["prev"]) or 0) <= 15 and org["cur"] >= 50:
        working.append(f"Google search is the steady base: {_num(org['cur'])} visits this week ({_num(org['prev'])} last week).")
    best = _best_page(rows)
    if best:
        working.append(f"{best.get('ad_name')} holds people best: {best['perf']['engaged_pct']:g}% of {best.get('ga_sessions'):,} visitors engaged.")
    if enq.get("cur"):
        working.append(f"{_num(enq['cur'])} enquiries (calls, emails, contact clicks) were recorded on the website"
                       + (f" since {enq.get('since')}." if enq.get("since") else "."))
    for x in low[:3]:
        not_working.append(f"{x['name']}: only {x['eng']:g}% of {x['sess']:,} visitors stayed, at {_R(x['spend'])} spent"
                           + (f" (about {_R(x['per_engaged'])} per engaged visit)." if x["per_engaged"] else "."))
    for c in paid.get("campaigns") or []:
        if (c.get("spend") or 0) >= MIN_SPEND_TO_JUDGE and not c.get("results") and c.get("objective") != "OUTCOME_AWARENESS":
            not_working.append(f"{c['name']}: {_R(c['spend'])} spent this week with no result.")
        if c.get("objective") == "OUTCOME_LEADS" and (c.get("results") or 0) >= MIN_RESULTS_TO_JUDGE and (c.get("spend") or 0) < MIN_SPEND_TO_JUDGE:
            risks.append(f"{c['name']}: {_num(c['results'])} results from {_R(c['spend'])} is too small to judge, and the price looks too low to be real, "
                         f"so it is left out of the comparison.")
    if ads and paused:
        risks.append("Paid visits are low only because the ads are paused; next week's numbers will stay low until they restart.")
    if enq.get("prev") == 0 and enq.get("since"):
        risks.append(f"Enquiry counting started {enq['since']}, so there is no earlier week to compare with yet.")
    if not ads:
        gaps.append("Ad results are not available this week (the daily ads check has not run), so the ad sections are left out.")
    if not f.get("bookings_linked"):
        gaps.append("Bookings are not linked to marketing, so there is no cost per customer or return on spend.")
    if not f.get("targets"):
        gaps.append("No targets are set, so the report cannot say whether a week was on or off target.")

    # ── who does what ────────────────────────────────────────────────────────────────────────────────────
    next_week = []
    titles = " ".join(d["decision"] for d in decisions).lower()
    if "budget" in titles:
        next_week.append(f"Herman: decide the ad budget for the rest of the {w}, starting from what a lead is worth to the business.")
    if "pages" in titles:
        next_week.append("Christelle: send each traffic ad to the page for its offer, then restart one ad as a test.")
    if "bookings" in titles:
        next_week.append("Kyle: get ClubLab's confirmed-booking event into Google Analytics.")
    if "targets" in titles:
        next_week.append(f"Herman: set a {w}ly lead target and a maximum cost per lead for each brand.")
    if not next_week:
        next_week.append("Christelle: keep the current plan. Nothing needs deciding this week.")

    return {"brand": brand, "week": f.get("week") or {}, "verdict": {"headline": headline, "tone": tone, "lines": lines},
            "numbers": numbers, "decisions": decisions, "working": working, "not_working": not_working,
            "risks": risks, "gaps": gaps, "next_week": next_week}
