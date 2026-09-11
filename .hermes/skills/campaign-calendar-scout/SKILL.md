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

Use the available `web_search` / `web_extract` tools to discover
events, tournaments, retail moments, creator moments, etc. Each
candidate must carry **source URLs**.

Required fields per candidate:

- `calendar_id` — leave blank; Campaign OS assigns
- `brand_id` — the input brand
- `title`
- `type` — one of `campaign` / `content` / `moment` / `reminder` /
  `watchlist`
- `event_start` / `event_end` (ISO 8601)
- `source_urls[]` — at least one cited URL
- `source_type` — `scout`
- `pillars[]` — which pillar(s) this supports (by `pillar_id`)
- `relevance_score` — float 0.0–1.0
- `relevance_reason` — short prose
- `commercial_relevance`, `audience_relevance`, `brand_relevance`,
  `timeliness` — short notes
- `confidence` — low / medium / high
- `status` — `candidate` (calendar-worthy now) or `watchlist` (monitor)
- `lead_time_class` — `major_retail` / `major_sporting_event` /
  `normal_campaign` / `reactive_opportunity` / `content_moment`
- `suggested_angles[]` — 1–3 short marketing angles
- `created_by` — `hermes-scout`

## Step 4 — Score relevance

For each candidate, score against the pillars:

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

1. **Source required**: every candidate has at least one `source_url`.
2. **Pillar tie required**: at least one `pillar_id` in `pillars[]`.
3. **No duplicate**: `title` not already in `existing_calendar` or
   `existing_watchlist`.
4. **Type-valid**: matches `valid_record_types`.
5. **Brand-isolated**: `brand_id` is an operating brand.
6. **Date parseable**: `event_start` is ISO 8601.
7. **Lead-time class valid**: in `valid_lead_time_classes`.

## Step 6 — Write via the Campaign OS API

For each candidate that passes the gate:

```text
POST /api/calendar/candidates
{
  "brand_id": "stick",
  "type": "moment",
  "status": "candidate",     // or "watchlist"
  "title": "...",
  "event_start": "2026-12-25",
  "event_end":   "2026-12-25",
  "source_urls": ["..."],
  "pillars": ["stick-retail"],
  "relevance_score": 0.85,
  "relevance_reason": "...",
  "commercial_relevance": "...",
  "audience_relevance": "...",
  "brand_relevance": "...",
  "timeliness": "...",
  "confidence": "high",
  "lead_time_class": "major_retail",
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

## Step 7 — Report

Return the brief's required shape:

```text
high relevance      (relevance_score >= 0.7)
medium relevance    (0.4 <= score < 0.7)
watchlist           (status='watchlist')
ignored_count       (how many golf trivia were deliberately rejected)
```

For each high-relevance candidate, show:

- event / moment
- source URL
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
`hermes cronjob` with this skill attached.

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
