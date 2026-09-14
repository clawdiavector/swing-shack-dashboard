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

### Concurrency controller (MANDATORY — do not bypass)

Do NOT call web_search / web_extract across lanes in parallel. The
Hermes provider (Firecrawl) has a 14 req/min cap and parallel subagents
tripped it during Slice 0.1 v1. Invoke research through the Campaign
OS helper:

```python
from marketing_calendar import batch_research_calls, MAX_FIRECRAWL_HEAVY_LANES

results = batch_research_calls(
    lambda spec: call_research_lane(spec),  # your lane implementation
    [
        {"name": "south_african_local", "firecrawl_heavy": True,  "params": {...}},
        {"name": "womens_golf",         "firecrawl_heavy": True,  "params": {...}},
        {"name": "global_golf",         "firecrawl_heavy": True,  "params": {...}},
        {"name": "creator_culture",     "firecrawl_heavy": True,  "params": {...}},
        {"name": "retail_commercial",   "firecrawl_heavy": False, "params": {...}},
    ],
)
```

The helper enforces:
- Maximum 2 simultaneous Firecrawl-heavy lanes (per batch).
- 3 batches in sequence with 1.0s inter-batch pause.
- Exponential backoff (1s, 2s, 4s + jitter) on 429 rate limits.
- 3 attempts per lane before recording research degradation.

If a lane hits a persistent rate limit, **do NOT** fallback to a
secondary discovery URL (e.g. Wikipedia) — record research_degradation
and proceed without that lane's primary verification.

Provider concurrency proof is auto-generated by
`POST /api/calendar/v2/concurrency-test` — keep observed max ≤ 2.

### Hermes web backend (PITFALL — SearXNG vs Firecrawl)

Hermes web research is configured by `hermes config set web.backend`.

- `ddgs` alone is NOT sufficient — `web.backend` is the primary switch.
- `searxng` returns "SEARXNG_URL is not set" if no instance is
  configured. Do NOT try to spin up SearXNG unless you have a concrete
  reason.
- **Recommended:** `hermes config set web.backend firecrawl` — same
  key handles both search and extract, no extra infra required.
  `FIRECRAWL_API_KEY` must be set in env.

Verify the backend works before relying on it. The Slice 0.1 v1
close-out failed because the Scout used SearXNG without a configured
instance — and substituted model memory. The Slice 0.1 v2 fix was to
flip to Firecrawl.

If the active backend returns an error, do NOT silently fall back to
memory. Return `research_status=unavailable` and stop.

### Required source verification metadata

Every externally discovered candidate must include:

```text
source_url       # the URL you read
source_domain    # e.g. rydercup.com, lpga.com, gov.za
source_title     # title of the page you read
source_class     # 'primary_official' | 'primary_lpga' | 'primary_brand' |
                 #  'primary_creator' | 'secondary_news' | 'secondary_aggregator'
source_origin    # 'external' | 'deterministic_calendar' | 'internal_strategy'
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
evidence[]           # structured fact-claim records (one per cited fact):
  source_url, source_title, retrieved_at,
  fact_type           # event_date | event_window | event_reference | holiday_date
  supported_value     # the value being supported (date / range / reference)
  exact_text          # short quote from the source (≤200 chars)
  source_class, verification_status, source_origin
conflicting_sources[] # when sources disagreed:
  source_url, source_title,
  discrepancy         # short description of the conflict
  resolution          # how the conflict was resolved (which source won + why)
  suppressed_value    # the value from the losing source
```

For a hard calendar date (event_start / event_end), prefer
`verified_primary`. Secondary reporting may help discovery but should
not silently override primary sources.

### Source precedence (PITFALL — Nedbank root cause)

When multiple sources disagree on a hard calendar date, prefer in this
order:

1. **Event organiser's own site** (e.g. `nedbankgolfchallenge.com`,
   `presidentscup.com`, `solheimcup.com`, `alfreddunhillchampionship.com`).
   These beat any governing-tour schedule, even if the tour page is
   more recently updated. The Nedbank bug from Slice 0.1 v2 audit:
   `europeantour.com/dpworld-tour/schedule/` said Dec 4-7 2026; the
   official `nedbankgolfchallenge.com/spectators/information/` said
   3-6 December. The organiser site wins. Use the event-organiser site
   whenever available.

2. **Governing tour / official league** (e.g. `europeantour.com`,
   `pgatour.com`, `lpga.com`, `tglgolf.com`, `solheimcup.com`,
   `presidentscup.com`, `rydercup.com` — note some of these are both
   governing AND organiser, e.g. Presidents Cup is run by PGA Tour).

3. **Official venue** (e.g. Royal Johannesburg & Kensington for Alfred
   Dunhill, when they post their own calendar).

4. **Official brand / creator channel** (Takomo's own pages for Takomo
   ambassador activity; goodgoodgolf.com press releases).

5. **Reputable secondary news** (progolfnow.com, golf.com, SCMP,
   Wikipedia as last resort).

A current official event schedule can beat an older official tour
article. Recency alone does NOT override hierarchy. If credible current
sources conflict and cannot be confidently reconciled, set
`verification_status=conflicting` and `trusted_for_planning=false`. Do
not silently pick one.

### Season-year guard (PITFALL — Alfred Dunhill root cause)

NEVER infer `calendar_year` from:
- The URL (e.g. `championship-2026` in the URL slug)
- The article title (e.g. "Alfred Dunhill Championship 2026")
- The season label (e.g. "2026 DP World Tour season")
- The Race to Dubai season or any tour season

The Alfred Dunhill bug from Slice 0.1 v1 audit: europeantour.com's
"Alfred Dunhill Championship 2026" page describes the Dec 11-14 2025
event (which opens the 2026 DP World Tour season). The URL says 2026;
the actual calendar year of the event is 2025.

Only the actual `event_start`/`event_end` calendar year counts.
When URL year + season year + title year disagree with event dates,
trust the event dates, persist the disagreement in `conflicting_sources[]`,
and set `calendar_year` from the dates.

### Required date-confidence metadata

```text
date_confidence:
  confirmed_date          # official source gives exact date. Can enter calendar.
  announced_window        # official source gives month/season/window only.
                          # Calendar entry with event_start/event_end bracketing
                          # the announced window; lifecycle=upcoming.
  expected_unannounced    # no official schedule yet. WATCHLIST only.
                          # Do NOT invent a date to make the calendar look complete.
  unannounced             # the only sources you found describe a different
                          # calendar year (e.g. season label ≠ calendar year).
                          # Move to WATCHLIST, do NOT write a calendar entry.
```

### Required event-lifecycle metadata

```text
event_lifecycle:
  upcoming             # in the future
  live                 # event is happening now
  recently_completed   # within the past ~30 days — still has reactive content potential
  completed            # fully completed; keep record for history
  postponed            # organiser pushed the date; recheck weekly until resolved
  cancelled            # event will not happen; recheck yearly in case of reschedule
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
- `event_window_start` / `event_window_end` (full event window incl. practice; separate from competition)
- `competition_start` / `competition_end` (competition rounds only — may differ from event_window)
- `event_window_label` — human-readable e.g. "Tournament event (Thu–Sun)"
- `source_urls[]` — at least one cited URL per candidate
- `source_domain`, `source_title`, `source_class`, `source_origin`, `retrieved_at` — per source above
- `verification_status` — per above
- `date_confidence` — per above (note: `unannounced` means the only sources found describe a different calendar year)
- `event_lifecycle` — per above
- `opportunity_mode` — per above
- `calendar_year` — int, derived from event dates (NEVER from URL/season/title — see Season-year guard)
- `season_label` — str, e.g. "2026-27" for events in a season that spans years
- `pillars[]` — which pillar(s) this supports (by `pillar_id`)
- `relevance_score` — float 0.0–1.0
- `relevance_reason` — short prose
- `commercial_relevance`, `audience_relevance`, `brand_relevance`, `timeliness` — short notes
- `confidence` — low / medium / high
- `status` — `candidate` (calendar-worthy now) or `watchlist` (monitor)
- `lead_time_class` — `major_retail` / `major_sporting_event` / `normal_campaign` / `reactive_opportunity` / `content_moment`
- `suggested_angles[]` — 1–3 short marketing angles
- `created_by` — `hermes-scout`
- `event_key` — brand-scoped logical identity (`<brand_id>:<slug>[:<calendar_year>]`); generated from title + calendar_year, NOT from title alone. Two revisions of the SAME real-world event share the same event_key.
- `schema_version` — must be `"0.2"`
- `evidence[]` — structured fact-claim records (per source above)
- `conflicting_sources[]` — structured conflict records (per source above)
- `trusted_for_planning` — auto-computed by API; True ONLY when verified_primary + confirmed_date/announced_window + source_urls non-empty

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

**Use the v2 idempotent upsert, NOT the v1 candidates endpoint.**

The v1 `POST /api/calendar/candidates` always appends. Running the
Scout twice would create duplicate logical events. The v2
`POST /api/calendar/v2/upsert` checks the `event_key` and either
creates, updates, or no-ops.

For each candidate that passes the gate:

```text
POST /api/calendar/v2/upsert
{
  "brand_id": "stick",
  "type": "moment",
  "status": "candidate",     # or "watchlist" for expected_unannounced
  "title": "Nedbank Golf Challenge 2026",
  "event_start": "2026-12-03",
  "event_end":   "2026-12-06",
  "event_window_start": "2026-12-03",
  "event_window_end":   "2026-12-06",
  "event_window_label":  "Tournament event (Thu–Sun)",
  "calendar_year": 2026,
  "season_label": "2026",
  "source_urls": ["https://www.nedbankgolfchallenge.com/spectators/information/"],
  "source_domain": "nedbankgolfchallenge.com",
  "source_title": "Event Information — Nedbank Golf Challenge",
  "source_class": "primary_official",
  "source_origin": "external",
  "retrieved_at": "2026-09-14T07:00:00Z",
  "verification_status": "verified_primary",
  "date_confidence": "confirmed_date",
  "event_lifecycle": "upcoming",
  "opportunity_mode": "planned",
  "pillars": ["stick-fitting", "stick-coaching"],
  "relevance_score": 0.85,
  "relevance_reason": "...",
  "commercial_relevance": "...",
  "audience_relevance": "...",
  "brand_relevance": "...",
  "timeliness": "85 days out — production deadline still open",
  "confidence": "high",
  "lead_time_class": "major_sporting_event",
  "suggested_angles": ["..."],
  "evidence": [
    {
      "source_url": "https://www.nedbankgolfchallenge.com/spectators/information/",
      "source_title": "Event Information — Nedbank Golf Challenge",
      "retrieved_at": "2026-09-14T07:00:00Z",
      "fact_type": "event_date",
      "supported_value": "2026-12-03..2026-12-06",
      "exact_text": "The 2026 Nedbank Golf Challenge will take place at Sun City from 3 - 6 December 2026",
      "source_class": "primary_official",
      "verification_status": "verified_primary",
      "source_origin": "external"
    }
  ],
  "conflicting_sources": [
    {
      "source_url": "https://www.europeantour.com/dpworld-tour/schedule/",
      "source_title": "DP World Tour Schedule — stale",
      "discrepancy": "shows 2026-12-04..2026-12-07",
      "resolution": "Official event site + Instagram both confirm 3-6 December. DPWT page is stale; organiser site wins.",
      "suppressed_value": "2026-12-04..2026-12-07"
    }
  ],
  "created_by": "hermes-scout"
}
```

The upsert returns one of three actions:
- `created` — first time this event_key seen (revision=1, change_type=new_event)
- `updated` — material change detected (revision=N+1, change_type set, supersedes_calendar_id populated)
- `noop` — nothing material changed; only `last_checked_at` updated on the existing line

**PITFALL — change_type ordering:** when prev.status was `watchlist` and
the new record is a candidate, return `change_type=promotion`, NOT
`verification_change` even though verification_status changed too. The
promotion check must run BEFORE verification_change.

**PITFALL — object identity in jsonl iteration:** when iterating jsonl
lines to find "the latest revision" of a calendar_id, do NOT compare
parsed objects with `is` — each `json.loads` call produces a new
object. Use `(calendar_id, created_at or last_verified_at)` as the
composite key, not object identity. (Slice 0.2 first migration had this
bug — every record scanned but nothing migrated.)

**PITFALL — staleness logic direction:** the reminder trust gate fires
only when the reverify window has passed. A record is stale when
`now > reverify_after`, NOT when `lv_dt > ra_dt`. The latter is
clock-skew (last_verified in the future relative to reverify_after).

The API auto-computes:
- `event_key` — from brand_id + title slug + calendar_year
- `lead_time_schedule` (research_start / planning_start /
  production_deadline / campaign_live_start / event_date) using the
  brand's `lead_time_rules`
- `lead_time_days` — days between `planning_start` and `event_date`
- `calendar_id` — assigned on persistence
- `revision`, `change_type`, `changed_fields`, `supersedes_calendar_id`
- `last_verified_at`, `last_checked_at`, `reverify_after`
- `trusted_for_planning` — True ONLY when verification_status =
  verified_primary AND date_confidence ∈ {confirmed_date, announced_window}
  AND source_urls non-empty. Downstream planning reminders / Morning Brief
  / automatic content planning MUST filter on `trusted_for_planning=true`.

## Step 6b — Reminder trust gate (consumer)

Planning reminders for external moments MUST filter on the trust gate
before firing. Use the campaign OS helper:

```python
from marketing_calendar import can_fire_planning_reminder

allowed, reason = can_fire_planning_reminder(record)
if not allowed:
    # Skip reminder; log the reason
    return
# Fire the planning reminder
```

The gate refuses to fire for any of these reasons:
- `trusted_for_planning` is False (unverified or insufficient sources)
- `verification_status` is `conflicting`
- `event_lifecycle` is `postponed`, `cancelled`, or `expired`
- `now > reverify_after` (the reverify window has passed without
  re-verification — the record is stale)

Internal strategy campaigns and deterministic calendar dates follow
their own trust path; the external record gate applies only to
externally-sourced events.

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

**Not yet enabled.** The Slice 0.1 close-out brief explicitly forbade
scheduled autonomous Scout runs until the end-to-end workflow is
proven useful. Slice 0.2 (automation readiness) shipped the contracts
needed for cron (`event_key`, revisions, `last_checked_at`,
`reverify_after`, watchlist-due endpoint) but the cron is still a
user-acceptance decision.

When the user approves scheduling:

1. **First call must be `GET /api/calendar/scout-health`.** If
   `can_write_external_candidates=false` OR `overall_state` in
   {`unavailable`, `degraded`}, fail closed — log the run, no writes.
2. Use `MAX_FIRECRAWL_HEAVY_LANES = 2` (see Concurrency below).
3. Use `upsert_event` (POST `/api/calendar/v2/upsert`) NOT the v1
   `POST /api/calendar/candidates`. The upsert is idempotent — repeat
   runs produce no new logical events / no new revisions on
   unchanged records. This is what makes cron safe.
4. On rate-limit signals from Firecrawl: exponential backoff with
   jitter (1s, 2s, 4s); do NOT downgrade primary verification to
   Wikipedia just because the provider is temporarily rate-limited.
5. Check `GET /api/calendar/v2/watchlist-due?brand_id=X` BEFORE
   the main Scout run — items with `next_check_date <= today` or
   `last_checked_at` older than their cadence are the priority
   targets for re-research.

## Subagents

**Enabled.** Slice 0.1 v2 close-out used parallel subagents to handle
5 research lanes (SA local, women's golf, global, creator/culture,
retail/commercial). Subagent delegation IS the right pattern for
multi-lane research because the lanes involve independent judgment
about sources.

**Concurrency cap (PITFALL):**

```text
MAX_FIRECRAWL_HEAVY_LANES = 2     # hard cap; do not raise this without testing
RESEARCH_LANE_BATCHES = [
    # batch 1 — 2 lanes
    ["south_african_local", "womens_golf"],
    # batch 2 — 2 lanes
    ["global_golf", "creator_culture"],
    # batch 3 — 1 lane (less Firecrawl-heavy)
    ["retail_commercial"],
]
```

The Slice 0.1 v2 first run hit Firecrawl's rate limit (14 req/min) by
spawning 5 lanes in parallel. Five parallel Firecrawl-heavy lanes are
NOT safe. Always respect the cap.

Recommended execution model:

```python
from marketing_calendar import batch_research_calls, MAX_FIRECRAWL_HEAVY_LANES

results = batch_research_calls(
    call_fn=lambda spec: research_lane(spec["name"], spec["params"]),
    lane_specs=[
        {"name": "south_african_local", "firecrawl_heavy": True, "params": {...}},
        {"name": "womens_golf", "firecrawl_heavy": True, "params": {...}},
        {"name": "global_golf", "firecrawl_heavy": True, "params": {...}},
        {"name": "creator_culture", "firecrawl_heavy": True, "params": {...}},
        {"name": "retail_commercial", "firecrawl_heavy": False, "params": {...}},
    ],
)
```

Within a batch, lanes run sequentially (not parallel). Between
batches: 1-second pause. On 429 / rate-limit: exponential backoff up
to 3 attempts per lane.

**Subagent rules:**

- Each subagent receives: explicit brand context + its narrow research
  lane + requirement for fresh sources + NO permission to write Calendar
  records. Subagents return candidate evidence to the parent Scout.
- The PARENT Scout: deduplicates across lanes, scores against Stick
  strategy, rejects weak relevance, writes approved candidates via
  `upsert_event`. Subagents research; parent decides.
- A subagent MUST NOT silently fall back to model memory when its
  research tooling is unavailable. It must return
  `research_status=unavailable` and an empty candidate list. The
  parent then has zero externally-verified candidates from that
  lane.

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
