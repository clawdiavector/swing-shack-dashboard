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

- UI: `"IBM Plex Sans", ui-sans-serif, system-ui, sans-serif`
- CEO numbers / Daily kicker: `"IBM Plex Serif", ui-serif, Georgia, serif`
- Scale (rem, not fluid): 12 / 14 / 16 / 20 / 28 / 40
- Line length for prose ~65ch. Stats can be dense.

## Layout

- Phone: bottom nav (8 items, Other last). Content 16px inset.
- iPad: compact top rail + optional split (list | detail).
- Desktop: 220px left rail, 32px content gutter, max 1120px.
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
(post · captions · copy · images · memes). Tab strips use `FilterChips` like Ops. Every interactive
control carries a `Tip`. Every cluster page includes a **ClassicLink** raw anchor to the matching
`/?page=…` or standalone HTML — never route Classic URLs through `Button`/`IconTile` (native round trip).

Leftover HTML and standalone pages (`image-lab.html`, `visualizer.html`, `meme-lab.html`,
`campaign-os.html` sections) stay on disk and served; Heroes does not delete them.

## Daily (first designed page)

1. Kicker: Today · brand · date
2. Do this now (one sentence + primary button)
3. Waiting on you (count → Review)
4. This week / Today reports (two panels)
5. Queue cards from `/api/today/panel`
6. What’s live (link to existing Socials)

## Other

Leftover pages stay linked. Do not 410 or delete files.
