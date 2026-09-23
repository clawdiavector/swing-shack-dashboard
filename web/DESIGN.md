# Campaign Heroes — DESIGN.md

Product register. Daily is the review gate: phone (~390), iPad portrait (~768)
and landscape (~1024), desktop. Other main pages reuse this vocabulary after
Daily is signed off.

## Voice

- Marketer: brief, inbox, studio, schedule, go live
- CEO: waiting on you, this week, pipeline, brands, what shipped, what it did
- Page titles and empty states use those words. No L1–L8 on the rail.

## Color (Campaign OS dark — same as the classic desk)

Kyle preferred the old desk. Heroes reuses those tokens, not a beige admin theme.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0a0f1a` | Canvas |
| `--bg2` | `#101727` | Cards / rail |
| `--bd` | `#22304d` | Borders |
| `--tx` | `#e6ecf5` | Type |
| `--ac` | `#34d399` | Go / shipped / links |
| `--yel` | `#fbbf24` | Waiting, primary CTA, current nav |

Accent is brass only on primary actions, current nav, and waiting counts.
No full-saturation fills on idle chrome.

## Type

- UI: `"Space Grotesk", Inter, ui-sans-serif, system-ui, sans-serif` (self-hosted in the Vite bundle for production CSP)
- CEO numbers / Daily kicker: `Fraunces, Georgia, ui-serif, serif`
- Root `html { font-size: 18px }` — rem tokens read 1.125× a 16px baseline.
- Scale (rem, not fluid): 12 / 14 / 16 / 20 / 28 / 40
- Line length for prose ~65ch. Stats can be dense.

## Layout

- Phone: bottom nav (8 items, Other last). Content 16px inset.
- iPad: compact top rail + optional split (list | detail).
- Desktop: 272px left rail (`lg` breakpoint), 32px content gutter, max 1680px content width.
- Cards: 12px radius, 1px `--rule`, no drop shadows heavier than 8px.

## Components

Every control: default, hover, focus, active, disabled.
Loading: skeleton bars, not a centered spinner.
Empty: teach the next action (“Nothing waiting — go to Studio”).

## Motion

150–200ms opacity/transform on nav and cards. No page-load choreography.

## Breakpoints

- `sm` 390 — phone
- `md` 768 — iPad portrait
- `lg` 1024 — iPad landscape / small laptop
- `xl` 1280 — desktop rail

## Ops

Native `/app/ops` with tabs **Jobs · Agents · Accounts** (`?tab=jobs|agents|accounts`).
Legacy inbound links use `?layer=jobs|agents`; other `?layer=` values land on Jobs with a
Classic link. Verdict badges: OK → green, LATE/STUCK → gold, FAILED → red, NEVER → mute.

Classic `/ops`, `/ops/jobs`, and `/connected-accounts` stay live — each tab has “Open in Classic”.

## Studio

Native work surfaces live under `/app/create/<cluster>` with optional `?tab=` inside a cluster
(post · captions · copy · images · memes), under `/app/calendar`, `/app/calendar/ideas`, and
`/app/calendar/lanes`, and under `/app/publish/queue`, `/app/publish/postiz`, `/app/publish/gbp`, and `/app/publish/socials`.
Tab strips use `FilterChips` like Ops. Every interactive
control carries a `Tip`. Every cluster page includes a **ClassicLink** raw anchor to the matching
`/?page=…` or standalone HTML — never route Classic URLs through `Button`/`IconTile` (native round trip).

Build a post picks a **calendar moment** and a **product** from selects; operators do
not type ids, and each select keeps a "type an id instead" escape. Products come from
`/api/products/line-items?brand_id=` — the catalog `POST /api/build-post/draft`
resolves against. `/api/lanes/products` is a different catalog and is not used here.

## Calendar

Native surfaces: `/app/calendar` (full month), `/app/calendar/ideas` (backlog),
`/app/calendar/lanes` (themes · timeline · right-now).

`?date=YYYY-MM-DD` is the calendar's deep-link contract and is honoured on all three:
it sets the visible month and the selected day, and it is the park target on Ideas.
Missing or malformed falls back to today, never an error. Every day-selection and
month-step writes `?date=` back with `replace:true`.

`?id=<calendar_id>` selects a moment and opens the moment panel on `/app/calendar`.
Unlike the one-shot params (`?item=` `?asset=` `?post=` `?hook_id=`), **`?id=` is
sticky** — it is the deep link to a moment. Closing the panel deletes `?id=` and keeps
`?date=`, `replace:true`. An `?id=` that matches no moment in the loaded month renders
no panel and no error. Moment rows link with a relative `?date=&id=` — they do not
round-trip `/tool/calendar`.

Moment stamps are **date-only** — "Public holiday · Thursday 24 September". A calendar
record is not a scheduled post; `Goes live` and a midnight clock are wrong for it.

Inside a page, `?tab=` selects the view (Ideas: ideas · today · week · missed · upsells ·
bundles · leaks. Lanes: now · month · timeline), as in Ops and Studio.

Classic `/?page=calendar`, `/?page=ideas` and `/?page=planning` stay live — each native
page carries a ClassicLink raw anchor to its classic page.

## Review

Pending unified inbox rows sort **newest first** by `created_at` (stale still badges on
the row; sort order does not pin old holidays above fresh work).

Review names the thing in human words. `calendar_candidate` → "Proposed calendar
moment", `draft_asset` → "Draft post", `publish_request` → "Ready to queue",
`proposal` → "Proposal"; an unknown type degrades to its Title-Cased raw value.
Every piece states what it is, for which brand, on which platform, and what Approve
does — **Approve never publishes**. Raw ids (campaign, asset, item) live in a collapsed
"Technical ids" block, never in the headline.

## Publish

`/app/publish` is the hub (brand-scoped counts from `/api/today/panel`). Native surfaces:
`/app/publish/queue` (drafts · scheduled · published · failed), `/app/publish/postiz`
(credentials · channels · mode), `/app/publish/gbp` (`?tab=plans|suggestions|drafts` — GBP
plans and GMB drafts share one page because they are one surface).

`?tab=` selects the view, as in Ops and Studio, and is written back with `replace:true`.
`?item=` / `?asset=` arrive from Review and select a queue row; they are consumed once,
never sticky. Missing or malformed params fall back to the default tab, never an error.

The publish queue is **not brand-scoped** — `/api/intel/postiz` reads flat files and its rows
carry no brand key. The page says so out loud. GBP daily-poster and GMB drafts *are*
brand-scoped and always send `brand_id` from `useBrand()`.

Live actions — GBP daily publish, GMB draft publish, Postiz cancel/reschedule — are labelled
"(live)", never "schedule". The two destructive ones sit behind a typed confirm naming the
brand. `PUBLISH_MODE=sandbox` gates the dispatch job only, so the mode badge says that and
never implies the page is safe. No bulk publish, no auto-retry. Secrets are rendered as
configured ✓/✗ only.

Classic `/?page=publish`, `/?page=postiz`, `/?page=gbp` and `/?page=gmb` stay live — each
native page carries a ClassicLink raw anchor to its classic page.

## Socials

Native surface: `/app/publish/socials` (`?tab=posts|health`, default `posts`). `?days=30|90|365`
(default `90`) and `?type=IMAGE|VIDEO|CAROUSEL_ALBUM` filter the grid (type is client-side).
`?post=` opens the detail panel once, then drops from the URL.

`/api/socials/*` reads the **default Meta account** (env), not the brand chip — the page states that
and shows brand wiring from `/api/connected-accounts/status`. Per-brand Graph threading is deferred
(P5b); do not imply the feed follows the header chip.

Classic `/?page=socials` stays live — native page carries a ClassicLink raw anchor.

## Results

`/app/results` is the hub. **P4a** native surfaces: `/app/results/week` (`?tab=summary|hooks|failures|agents`)
and `/app/results/worked` (`?tab=posts|recipes|ctas|patterns|traffic`). Reach, trends, and SEO stay Classic
until P4b.

`/results/week` fetches **both** weekly reports: brand-true KPIs from `/api/weekly-report?format=json` and
portfolio-wide detail from `/api/intel/weekly_report` (interpretation, hooks, agents). Say which is which on
the page — do not show intel numbers under the wrong brand chip. When `data_source_brand_id` differs from
the active brand, show a delegation badge.

`/results/worked` merges Classic insights and learnings. The **posts** and **traffic** tabs are brand-true
(via `brand_id` / delegation). **Recipes, CTAs, and patterns** read flat learn files — label those sections
portfolio-wide, not once at the top.

`?tab=` selects the view and is written back with `replace:true`. Missing or malformed falls back to the
default tab, never an error. `?post=` / `?hook_id=` highlight a row once, then drop from the URL (same as
Publish queue `?item=`). SEO deep links in P4b will use **`?sp=`** on the native route (not `?page=`, which
collides with Classic section names) and translate to `page=` at the fetch boundary.

Live actions: weekly snapshot (`POST /api/weekly-report/snapshot`) and share-link mint
(`POST /api/intel/weekly_report/share`) are labelled **(live)**. Share mint requires a typed confirm naming
the brand; show `expires_at` and a copyable link only — never log tokens. Reporting V1 (`/api/reports/v1/`)
is offered only for `swing-shack` and `stick`; other brands get a disabled tile with the reason in words.

Classic `/weekly-report` (public HTML), `/?page=insights`, and `/?page=learning` stay live — native pages
carry ClassicLink raw anchors. Do not widen `PUBLIC_ROUTE_PREFIXES` or move the public weekly page behind
the SPA.

Leftover HTML and standalone pages (`image-lab.html`, `visualizer.html`, `meme-lab.html`,
`campaign-os.html` sections) stay on disk and served; Heroes does not delete them.

## Daily (first designed page)

1. Kicker: Today · brand · date
2. Do this now (one sentence + primary button)
3. Waiting on you (count → Review)
4. This week / Today reports (two panels)
5. Today ticker lists the brand’s **pending unified inbox** (same queue as Review), not
   morning-brief cards alone. Counts/summary still come from `/api/today/panel?brand=`.
6. “What worked” thumbs: `thumbnail_url`, then `media_url` (not VIDEO), then oEmbed
   recovery on image error via `/api/socials/oembed`. Review/Daily queue rows use
   optional list thumbs that hide on `<img>` error (no broken icon, no “no thumb” slot).
7. Shortcuts use native Heroes routes (`/publish/socials`, `/publish/gbp`, `/create/post`,
   `/results/week`).

## Other

Leftover pages stay linked. Do not 410 or delete files.

## After P5

Native surfaces on integrate (signed code):

| Rail | Native route | Landed |
|---|---|---|
| Daily | `/app/daily` | pre-P0 |
| Review | `/app/review`, `/app/review/:itemId` | pre-P0 |
| Ops | `/app/ops` `?tab=jobs\|agents\|accounts` | P0 |
| Create | `/app/create/post` `captions` `copy` `images` `memes` | P1 |
| Calendar | `/app/calendar`, `/calendar/ideas`, `/calendar/lanes` | P2 |
| Publish | `/app/publish/queue` `postiz` `gbp` | P3 |
| Results | `/app/results/week` `worked` | P4a |
| Socials | `/app/publish/socials` | P5 |

Shared contract on native surfaces: `?tab=` selects the view and is written back
`replace:true`; malformed values fall back to the default tab; one-shot params
(`?item=` `?asset=` `?post=` `?hook_id=`) are consumed once; `?date=` is the
calendar deep link; every page has a **ClassicLink** raw anchor; controls carry a
`Tip`; live actions are `(live)`; destructive actions use a typed confirm naming
the brand.

Still Classic (not bugs): `performance`, `trends`, `seo`, and legacy `/?page=review`
— catalog slugs without `native:` until **P4b**. Deferred by design: **P5b** per-brand
Meta Graph (Socials reads default env account); publish queue not brand-scoped;
portfolio-wide learn files on Results; **P7** data review only.

Classic cutover: bare `/` already → `/app/daily`. Optional `HEROES_CUTOVER=true`
(on Railway) maps signed-off `/?page=` slugs to native routes; default off.
`/home.html?page=…` never redirects (ToolFrame embeds). See `RAILWAY.md` §3.
