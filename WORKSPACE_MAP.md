# Workspace Map — Campaign OS

**Correction (2026-09-11):** Campaign OS is one Flask-served SPA (`campaign-os/campaign-os.html`), not five
named “workspaces” and not a linear build funnel. Inventory below is generated from the live HTML
(`data-go` nav keys and `id="sec-*"` panels). Supersedes the 2026-07-08 map that still listed Steps 10–15 as upcoming.

**Standalone + connected still holds:** every major capability should work alone and may optionally
attach outputs to a campaign. That design rule did not change — only the inventory did.

## Inventory (verified)

```bash
grep -o 'data-go="[a-z0-9-]*"' campaign-os/campaign-os.html | sort -u | wc -l   # 45
grep -o 'id="sec-[a-z0-9-]*"' campaign-os/campaign-os.html | sort -u | wc -l    # 44
```

**45 nav keys / 44 sections.** The off-by-one is intentional in the markup:
nav key `seo-stack` has **no** `#sec-seo-stack` panel — clicking it navigates to the standalone
`/seo-stack` page (Sarvesh SEO playbook), not an in-SPA section.

Hook Bank, Meme Lord, Billboard Lab, Calendar, and Caption Studio **shipped** — they are rows in the table, not a “next” build order.

## Nav key → section → purpose

| Nav key (`data-go`) | Section id | Purpose |
|---|---|---|
| `brief` | `sec-brief` | Today / daily brief |
| `review` | `sec-review` | Review queue |
| `library` | `sec-library` | Asset library |
| `socials` | `sec-socials` | Socials / IG history |
| `gmb` | `sec-gmb` | GMB drafts |
| `create` | `sec-create` | Create intelligence grid |
| `campaigns` | `sec-campaigns` | Campaigns / brand spine |
| `captions` | `sec-captions` | Caption Studio |
| `headlines` | `sec-headlines` | Headline generator |
| `hooks` | `sec-hooks` | Hook Bank |
| `memes` | `sec-memes` | Meme Lord |
| `imagegen` | `sec-imagegen` | Image generation |
| `billboards` | `sec-billboards` | Billboard Lab |
| `ctas` | `sec-ctas` | CTA generator |
| `hashtagseo` | `sec-hashtagseo` | Hashtags + SEO pack |
| `ideas` | `sec-ideas` | Ideas / opportunities |
| `reddit` | `sec-reddit` | Reddit outreach |
| `faqs` | `sec-faqs` | FAQ opportunities |
| `insights` | `sec-insights` | Insights |
| `trends` | `sec-trends` | Trends |
| `performance` | `sec-performance` | Performance |
| `learning` | `sec-learning` | Learning / long memory |
| `seo` | `sec-seo` | SEO assistant |
| `seo-audit` | `sec-seo-audit` | SEO audit |
| `calendar` | `sec-calendar` | Calendar |
| `publish` | `sec-publish` | Publishing pipeline |
| `postiz` | `sec-postiz` | Postiz |
| `gbp` | `sec-gbp` | GBP daily |
| `agents` | `sec-agents` | Agents & health (UI; live jobs are in `AGENTS.md` §6) |
| `onboarding` | `sec-onboarding` | First-campaign onboarding |
| `brand-settings` | `sec-brand-settings` | Brand settings |
| `agency` | `sec-agency` | Agency dashboard |
| `products` | `sec-products` | Products & pricing |
| `seo-stack` | *(none — external `/seo-stack`)* | SEO Stack (Sarvesh) standalone page |
| `tenants` | `sec-tenants` | Tenant isolation |
| `integrations` | `sec-integrations` | Integrations |
| `abtests` | `sec-abtests` | A/B tests |
| `metaoauth` | `sec-metaoauth` | Meta OAuth |
| `landing` | `sec-landing` | Landing page |
| `ops` | `sec-ops` | Ops runbook |
| `fleet` | `sec-fleet` | Fleet status |
| `herman` | `sec-herman` | Stick Herman demo |
| `planning` | `sec-planning` | Strategic calendar |
| `docs` | `sec-docs` | In-app docs |
| `buildpost` | `sec-buildpost` | Build post |

## Shared objects (still true)

Workspaces (sections) exchange atoms with a stable shape and a `source` field:

| Object | Typical producers | Typical consumers |
|---|---|---|
| `campaign` | Campaigns / Create | Calendar, Review, Publish |
| `idea` | Trends, Ideas | Campaigns, Memes, Billboards |
| `trend` | Trends | Campaigns, Ideas, Calendar |
| `hook` | Hook Bank | Captions, Memes |
| `caption` | Caption Studio | Memes, Calendar, Publish |
| `meme` | Meme Lord | Calendar, Review |
| `billboard line` | Billboard Lab | Calendar, Campaigns |
| `calendar item` | Calendar | Publish |

## The rule for every new capability

> Every major capability must work in two modes: **standalone** (used by itself) and **connected** (can attach outputs to a campaign).

No capability is “inside” another as a trapped modal. New views are top-level nav entries (or true external pages like `seo-stack`), not Campaign Builder sub-screens.

See root `AGENTS.md` for jobs, branches, `$DATA_DIR`, and standing rules.
