# Workspace Map — Campaign OS

**Correction (2026-07-08):** Campaign OS is NOT a linear funnel. It is **independent workspaces connected by shared objects**. The Campaign Builder is the spine (turns an idea into a launched campaign), but Meme Lord, Billboard Lab, and Trend Catcher are living organs — they run standalone, and may optionally attach their outputs to a campaign.

## Workspaces

### 1. Trend Catcher
Always-on intelligence. No campaign required.
- **Standalone:** open Trend Catcher, see today's brief (top trends, signals, noise). No campaign in scope.
- **Connected:** a recommended trend can spawn an `idea` (attached to a campaign) or a `content opportunity` (standalone post).
- **Inputs:** sources (Reddit, TikTok, Google Trends, GBP, GSC).
- **Outputs:** `trend` (object: signal/noise verdict, source, score, brief).

### 2. Campaign Builder
The spine. Turns an idea into a launched campaign with assets, dates, captions, review.
- **Standalone:** create a campaign from scratch (3-stage wizard).
- **Connected:** accepts a pre-existing `idea` (from Trend Catcher, or pasted), or an attached `trend` that seeded it.
- **Inputs:** `idea` (optional), `trend` (optional), or empty.
- **Outputs:** `campaign` (full shape from Step 9: identity + plan + brief + production + approval + history + media).

### 3. Meme Lord
Social-native humour. Generates meme ideas and captions.
- **Standalone:** open Meme Lord, see prompt bank, generate meme ideas, save winners. No campaign needed.
- **Connected:** a saved meme can be attached to a campaign's `assets` list, or queued for a `calendar item`.
- **Inputs:** `hook` (optional, from Hook Bank), `voice canon` (brand voice).
- **Outputs:** `meme` (object: caption, format, angle, asset ref).

### 4. Billboard Lab
Hero copy. Window screens, billboards, shop displays.
- **Standalone:** open Billboard Lab, generate headline candidates against a `prompt` (a "big idea"), pick the Pineapple-Test-passing line. No campaign needed.
- **Connected:** a saved billboard line can be attached to a campaign as a hero, or queued for a `calendar item`.
- **Inputs:** `big idea` (optional), `voice canon`.
- **Outputs:** `billboard line` (object: text, surface, rationale, test result).

### 5. Calendar
Aggregation view. Shows everything scheduled.
- **Inputs:** campaigns (from Builder), standalone posts (from Meme Lord), billboard runs (from Billboard Lab), trend opportunities (from Trend Catcher).
- **Standalone:** show what's on the calendar. No campaign context required for individual items.
- **Connected:** items can be filtered or grouped by campaign.
- **Outputs:** `calendar item` (the unified scheduling unit, with a `source` field pointing back to its origin workspace).

## Shared objects (the connective tissue)

These are the "atoms" that workspaces read and write. Each has a stable shape and a `source` field so workspaces can find their work later.

| Object | Producing workspaces | Consuming workspaces |
|---|---|---|
| `campaign` | Campaign Builder | Calendar, Review Queue, Approval |
| `idea` | Trend Catcher, Campaign Builder | Campaign Builder (input), Meme Lord, Billboard Lab |
| `trend` | Trend Catcher | Campaign Builder, Meme Lord, Billboard Lab, Calendar |
| `hook` | Meme Lord, Hook Bank | Caption Workspace, Meme Lord |
| `caption` | Caption Workspace | Meme Lord, Calendar |
| `meme` | Meme Lord | Calendar, Review Queue |
| `billboard line` | Billboard Lab | Calendar, Campaign Builder (hero) |
| `asset request` | Campaign Builder brief | Asset Planner (future) |
| `calendar item` | Calendar (aggregator) | Publishing |

## The rule for every new capability

> Every major capability must work in two modes: **standalone** (used by itself) and **connected** (can attach outputs to a campaign).

This means: no workspace is "inside" another. Meme Lord is not a modal inside Campaign Builder. It is a top-level view that Campaign Builder may link to.

## What this changes in Step 10

Step 10 (next) is the **Hook Bank** — itself a standalone workspace. It accepts trends and ideas as inputs, outputs hooks. Hooks can be:
- saved standalone (no campaign), OR
- attached to a campaign as `campaign.hooks[]` (referenced from Stage 2 plan.bigIdea or Stage 3 brief).

The Campaign Builder's Stage 1/2/3 wizard does not change. But from Step 10 onwards, every new view is a top-level workspace, not a Campaign Builder sub-screen.

## Build order (revised)

1. ✅ Campaign Builder Steps 1–9 (campaign creation end-to-end)
2. ⏭ **Step 10:** Hook Bank workspace (standalone + connected)
3. Step 11: Meme Lord workspace (uses Hook Bank)
4. Step 12: Billboard Lab workspace (uses Hook Bank)
5. Step 13: Trend Catcher workspace (feeds Hook Bank)
6. Step 14: Calendar workspace (aggregates everything)
7. Step 15: Caption Workspace (fills campaign.brief.assets)
