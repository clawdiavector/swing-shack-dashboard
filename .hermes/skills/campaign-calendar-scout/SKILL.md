---
name: campaign-calendar-scout
description: Use when scouting upcoming marketing moments for a brand's calendar. Reads brand calendar context from Campaign OS, researches a defined horizon, scores relevance against the brand's pillars + North Stars, and writes candidates/watchlist via the Campaign OS API. Never assumes the active brand from conversational memory; brand_id is an explicit input.
---

# Campaign Calendar Scout

A reusable procedure for turning "upcoming moments" into "candidate
calendar entries" for a specific brand. **Brand-agnostic by design** —
Stick is the first configured instance but the Scout must work for any
brand whose context exists at `GET /api/calendar/context/<brand_id>`.

This skill contains the procedure and reasoning. Per-brand strategy
(pillars, North Stars, scouting profile, lead-time rules) is loaded from
Campaign OS at runtime. **Do not put Stick-specific strategy in here.**

---

## RESEARCH INTEGRITY RULE (NON-NEGOTIABLE)

> **Fresh external facts require external verification. Model memory
> may suggest search terms but may never serve as evidence.**

Hermes reasoning CAN decide: *"Solheim Cup sounds relevant to Stick."*

Hermes research MUST establish: *"When is it actually happening?"*

If fresh research tooling is unavailable, STOP THE SCOUT RUN and return
`research_status = unavailable`. Do not manufacture a "credible" run
from training data.

**Fail-closed behaviour:**

```
WEB/SOURCE ACCESS WORKING
  → research
  → verify
  → candidate (verification_status=verified_primary)

WEB/SOURCE ACCESS UNAVAILABLE
  → no external candidates written
  → explicit Scout health warning returned
```

Before writing any externally-sourced candidate, call
`GET /api/calendar/scout-health`. If `can_write_external_candidates`
is `false`, STOP.

---

## When to use this skill

Use when you are asked to:

- "Scout next 90 days for Stick"
- "What upcoming moments matter for the brand?"
- "Build a watchlist for swing-shack"
- "Generate calendar candidates for {brand_id} over {horizon_days}"

Do **not** use this skill for:

- Generating creative / copy
- Approving / publishing
- Performance optimisation
- Automatic daily Scout runs (not yet — see "Cron" section)

---

## Inputs (always required)

- `brand_id` — explicit operating brand (`swing-shack`, `stick`, or
  `bag-drop`). Never inferred from chat memory. **Reject if the user
  passes `takomo`** — that is a `product_brand` under `stick`, not an
  operating brand.
- `horizon_days` — default 120. Scout research window starting today.

## Step 1 — Load brand context

```text
GET /api/calendar/context/<brand_id>?horizon_days=120
```

This is the contract. The response includes:

- `brand` (timezone, configured flag)
- `pillars[]` — each with `name`, `always_active`, `colour`,
  `north_star_metric`, `north_star_target`, `derived_weekly_target`
- `scouting_profile.interest_areas` — golf_events / womens_golf /
  creator_culture / retail_commercial
- `lead_time_rules` — per-class overrides on research_start /
  planning_start / production_deadline / campaign_live_start
- `existing_calendar[]` — already-persisted candidates to avoid duplicates
- `existing_watchlist[]` — already-persisted watchlist items to avoid
  re-promotion noise
- `valid_brand_ids`, `valid_record_types`, `valid_statuses`,
  `valid_lead_time_classes`
- `product_brands[]` — confirms takomo belongs to stick

If the response says `configured=false` or 404, refuse to write candidates.
Tell the user the brand needs a `calendar_config.json` first.

## Step 2 — Decide the research lanes

From `scouting_profile.interest_areas`, decide which lanes are worth
researching this horizon. Stick's seed covers:

- **golf_events** (South African, Sunshine Tour, majors, DP World Tour,
  PGA Tour where relevant, LPGA, LET, Solheim Cup, Ryder Cup, Walker
  Cup, Presidents Cup, TGL, WTGL, notable amateur golf)
- **womens_golf** (LPGA, LET, Solheim Cup, women's majors, SA women
  golfers, participation/culture — meaningful weight, not afterthought)
- **creator_culture** (YGT, Takomo creator activity, Internet
  Invitational, creator tournaments, YouTube developments, emerging
  moments)
- **retail_commercial** (Christmas, Black Friday, Father's Day, Mother's
  Day where relevant, Valentine's where relevant, SA public holidays,
  school holidays, payday/commercial periods, gifting periods,
  apparel/fashion moments)

The Scout is not limited to the seed list — discovering adjacent
relevant sources/entities is part of the job. But every candidate
needs a *plausible marketing relationship* to at least one pillar,
active campaign, audience, product/product_brand, commercial
objective, or strategic territory.

## Step 3 — Research a defined future horizon

**MANDATORY FIRST CALL:**

```text
GET /api/calendar/scout-health
```

If `can_write_external_candidates=false`, STOP the run. Return:

```text
research_status: unavailable
candidates_verified: 0
candidates_unverified: 0
research_sources_attempted: 0
research_sources_succeeded: 0
research_sources_failed: 0
message: <scout-health.message>
```

Do not invent candidates. Do not use training memory.

**If web access enabled**, use the available `web_search` /
`web_extract` tools to discover events, tournaments, retail moments,
creator moments, etc. Each candidate MUST carry **source URLs from
primary or secondary sources**.

### Required source verification metadata

Every externally discovered candidate must include:

```text
source_url       # the URL you read
source_domain    # e.g. rydercup.com, lpga.com, gov.za
source_title     # title of the page you read
source_class     # 'primary_official' | 'primary_creator' | 'primary_brand' |
                 #  'secondary_news' | 'secondary_aggregator'
retrieved_at     # ISO 8601 UTC timestamp when you fetched the URL
verification_status:
  verified_primary    # official tournament body / official tour / official
                      # league / official creator/channel / official brand /
                      # official government. Use this for hard calendar dates.
  verified_secondary  # secondary reporting (news, aggregator). Use only when
                      # no primary source is available.
  conflicting         # multiple sources disagree on date/details
  unverified          # you couldn't verify (still on watchlist, do not write
                      # to calendar)
```

For a hard calendar date (event_start / event_end), prefer
`verified_primary`. Secondary reporting may help discovery but should
not silently override primary sources.

### Required date-confidence metadata

```text
date_confidence:
  confirmed_date          # official source gives exact date. Can enter calendar.
  announced_window        # official source gives month/season/window only.
                          # Calendar entry with event_start/event_end bracketing
                          # the announced window; lifecycle=upcoming.
  expected_unannounced    # no official schedule yet. WATCHLIST only.
                          # Do NOT invent a date to make the calendar look complete.
```

### Required event-lifecycle metadata

```text
event_lifecycle:
  upcoming             # in the future
  live                 # event is happening now
  recently_completed   # within the past ~30 days — still has reactive content potential
  expired              # older than that — keep record for history only
```

### Required opportunity-mode metadata

```text
opportunity_mode:
  planned    # research can start now; planning deadline is in the future
  reactive   # event is imminent or live; we missed the planning window — react now
  watch      # no firm date yet — keep on watchlist, promote when announced
```

### Required candidate fields (full schema)

- `calendar_id` — leave blank; Campaign OS assigns
- `brand_id` — the input brand
- `title`
- `type` — one of `campaign` / `content` / `moment` / `reminder` / `watchlist`
- `event_start` / `event_end` (ISO 8601, only if `date_confidence != expected_unannounced`)
- `source_urls[]` — at least one cited URL per candidate
- `source_domain`, `source_title`, `source_class`, `retrieved_at` — per source above
- `verification_status` — per above
- `date_confidence` — per above
- `event_lifecycle` — per above
- `opportunity_mode` — per above
- `pillars[]` — which pillar(s) this supports (by `pillar_id`)
- `relevance_score` — float 0.0–1.0
- `relevance_reason` — short prose
- `commercial_relevance`, `audience_relevance`, `brand_relevance`, `timeliness` — short notes
- `confidence` — low / medium / high
- `status` — `candidate` (calendar-worthy now) or `watchlist` (monitor)
- `lead_time_class` — `major_retail` / `major_sporting_event` / `normal_campaign` / `reactive_opportunity` / `content_moment`
- `suggested_angles[]` — 1–3 short marketing angles
- `created_by` — `hermes-scout`

### Research lanes (Stick default — adjust per brand scouting_profile)

Each lane should be searched independently, not as part of a global golf search:

- **Local SA golf**: Sunshine Tour official schedule, GolfRSA, Gauteng /
  Johannesburg / Paarl-relevant events, SA amateur golf
- **Women's golf**: LPGA, LET, Solheim Cup, women's majors, Sunshine
  Ladies Tour, SA women golfers/events, women's participation stories
- **Global golf events** (where strategically useful): majors, DP World
  Tour, PGA Tour (where relevant), Ryder Cup, Presidents Cup, TGL, WTGL
- **Creator / culture**: YGT, Takomo creator activity, Internet
  Invitational, golf YouTube, creator tournaments. Discover adjacent
  relevant creators/topics — do not only search a static list.
- **Retail / commercial (SA)**: Black Friday, Father's Day, Mother's
  Day, Valentine's Day, SA public holidays (gov.za), school holidays,
  payday/commercial periods, gifting periods, apparel/fashion moments

## Step 4 — Score relevance

For each candidate, score against the pillars (NOT against "is this
golf"):

- **High relevance** (≥0.7): directly supports an active pillar +
  commercial objective + has clear marketing angle
- **Medium relevance** (0.4–0.7): supports a pillar but angle is
  indirect or timing is uncertain
- **Watchlist** (<0.4 but worth monitoring): tangential now, may
  become a candidate later
- **Ignored**: golf trivia with no plausible marketing tie — record
  the rejection so the user sees the Scout is filtering

## Step 5 — Quality gate

Before writing, apply these checks:

1. **Web access confirmed**: `GET /api/calendar/scout-health` returned
   `can_write_external_candidates=true`. If not, STOP.
2. **Source required**: every candidate has at least one `source_url`
   AND `verification_status` in {verified_primary, verified_secondary}.
3. **Primary preference**: hard calendar dates should be
   `verified_primary`, not `verified_secondary`.
4. **Date confidence match**: if `date_confidence=confirmed_date`,
   `event_start` must be present and ISO-parseable.
5. **Pillar tie required**: at least one `pillar_id` in `pillars[]`.
6. **No duplicate**: `title` not already in `existing_calendar` or
   `existing_watchlist`.
7. **Type-valid**: matches `valid_record_types`.
8. **Brand-isolated**: `brand_id` is an operating brand.
9. **Lifecycle valid**: `event_lifecycle` in {upcoming, live,
   recently_completed, expired}.
10. **Opportunity mode valid**: `opportunity_mode` in {planned,
    reactive, watch}.

## Step 6 — Write via the Campaign OS API

For each candidate that passes the gate:

```text
POST /api/calendar/candidates
{
  "brand_id": "stick",
  "type": "moment",
  "status": "candidate",     # or "watchlist" for expected_unannounced
  "title": "...",
  "event_start": "2026-09-28",
  "event_end":   "2026-09-28",
  "source_urls": ["https://..."],
  "source_domain": "rydercup.com",
  "source_title": "Ryder Cup 2026 — Official",
  "source_class": "primary_official",
  "retrieved_at": "2026-09-11T13:00:00Z",
  "verification_status": "verified_primary",
  "date_confidence": "confirmed_date",
  "event_lifecycle": "upcoming",
  "opportunity_mode": "planned",
  "pillars": ["stick-fitting"],
  "relevance_score": 0.85,
  "relevance_reason": "...",
  "commercial_relevance": "...",
  "audience_relevance": "...",
  "brand_relevance": "...",
  "timeliness": "...",
  "confidence": "high",
  "lead_time_class": "major_sporting_event",
  "suggested_angles": ["..."],
  "created_by": "hermes-scout"
}
```

The API auto-computes:

- `lead_time_schedule` (research_start / planning_start /
  production_deadline / campaign_live_start / event_date) using the
  brand's `lead_time_rules`
- `lead_time_days` — days between `planning_start` and `event_date`
- `calendar_id` — assigned on persistence
- `trusted_for_planning` — True ONLY when verification_status =
  verified_primary AND date_confidence ∈ {confirmed_date, announced_window}
  AND source_urls non-empty. Downstream planning reminders / Morning Brief
  / automatic content planning MUST filter on `trusted_for_planning=true`.

## Step 7 — Report

Return the brief's required shape, including source-health:

```text
research_status:           available | unavailable
web_access_status:         enabled  | disabled

research_sources_attempted: <N>
research_sources_succeeded: <N>
research_sources_failed:    <N>

candidates_verified:    <count of verified_primary>
candidates_unverified:  <count of others>

high relevance      (relevance_score >= 0.7 AND verified)
medium relevance    (0.4 <= score < 0.7 AND verified)
watchlist           (status='watchlist' OR date_confidence=expected_unannounced)
ignored_count       (how many golf trivia were deliberately rejected)
```

For each high-relevance candidate, show:

- event / moment
- source URL + source_class + retrieved_at
- date / window
- pillar
- North Star supported
- relevance score + reason
- recommended planning start
- suggested use

Plus: a few ignored examples and why they were ignored.

## Cron / scheduling

**Not enabled in Slice 0.1.** The brief explicitly forbids scheduled
autonomous Scout runs until the end-to-end workflow is useful. Use
this skill manually first; once the user sees value, schedule a
`hermes cronjob` with this skill attached. The cronjob MUST check
`/api/calendar/scout-health` first and fail closed if research is
unavailable.

## Subagents

**Not enabled in Slice 0.1.** The Scout may delegate parallel research
lanes later (tournaments, women's golf, creators, retail, local SA)
once there's evidence the workflow needs parallelism.

## Determinism

Use Python-level determinism for:

- Lead-time arithmetic (`compute_lead_time_schedule`)
- Date arithmetic for event windows
- Deduplication against `existing_calendar` + `existing_watchlist`
- Candidate ID assignment

Use agent judgment for:

- Is this relevant?
- Which pillar does it support?
- Why does it matter?
- Should we prepare now?
- Is the angle distinctive?
