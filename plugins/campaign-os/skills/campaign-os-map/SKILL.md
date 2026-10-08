---
name: campaign-os-map
description: >-
  What already exists in Campaign OS and on the Mac — lib modules, deterministic
  template renderer, brand templates, Meta/Krea wrappers, the Hermes fleet, and
  which specs are known wrong. Load BEFORE building anything for Campaign OS,
  swing-shack-dashboard, Stick or Swing Shack, and before reaching for an image
  model to produce a layout.
---

# Campaign OS — what already exists

The repo looks sparse and is not. On 2026-10-05 a full day went into
art-directing a poster that an existing template rendered deterministically, and
an hour into scraping Instagram while a Graph API wrapper sat unused. **Search
here first.**

## The reflex

| Before you… | Check |
|---|---|
| prompt an image model for a layout | `/render-post --list` — it may already be measured |
| trust a model id, size or template budget | `/verify-specs` — free, and seven specs were wrong in one day |
| write an API client | `grep -l <service> campaign-os/_lib/*.py` |
| build retrieval or context assembly | `_lib/p11_context_engine.py` (2,700 lines, already does it) |
| pull a brand's real feed | `/audit-social <brand>` — never scrape Instagram HTML |
| schedule anything | the Mac's launchd plists — it may already be scheduled and dormant |

Repo commands live in `.claude/commands/`. This skill lives in
`.claude/skills/campaign-os-map/` in the repo and is symlinked into
`~/.claude/skills/`, so it loads everywhere while staying versioned with the code
it describes.

## Rendering — deterministic, no model

`_lib/archetype_compose.py` → `compose_post_for_channels(brand_id, archetype, channels, fields, photo_bytes)`
renders a measured spec with PIL. ~200ms, pixel-identical, correct text every time.

```python
doc = archetypes.load_archetypes_doc("swing-shack")
arc = next(a for a in doc["archetypes"] if a["id"] == "ss-fitting-headline")
res = compose_post_for_channels(brand_id="swing-shack", archetype=arc,
        channels=["instagram"], fields={...}, photo_bytes=photo)
```

`fields` is keyed by each zone's `source` (e.g. `caption_hook`, `service_lockup`,
`cta`). A zone may append its own `text_suffix` — `ss-service-promo`'s
`service_lockup` adds ` @`, so pass `"BALL FITTING"`, never `"BALL FITTING @"`.

**Templates that exist.** Swing Shack: `fitting-headline`, `service-promo`,
`did-you-know`, `discount-code`, `lesson-corner`, `price-list`, `price-package`,
`sale-offer`, `zen-venue-promo`. Stick: `shop-corner`, `service-hero`,
`service-frame`, plus locations. Specs live in
`data/brand-directory/<brand>/visual-spec/archetypes.json`; packs with references,
photos and golden renders under `templates/<name>/`.

**No template exists** for Stick's `@ stick` partner panel (a navy block holding the
partner's logo, `@`, then the wordmark — it moves position per post), nor for the
flat-navy offer card. Both recur across the feed. `campaign-os-template` measures
new ones from reference images.

## Brand imagery — canonical Drive roots

Raw images are not in git. Google Drive is the source of truth, pulled by
`scripts/ingest_public_drive_folder.py`. Ingest uses the **per-brand children**
in `BRAND_PUBLIC_ROOTS` and **refuses to run for a brand it has no root for**.
It used to default `--folder-id` to Stick's root for every brand, so
`--brand swing-shack` alone filed Stick's imagery under Swing Shack with nothing
to catch it (md5 dedupe is per-brand).

The folder people share is the **parent**, not either child. On 2026-10-05
`list_public_folder` image ids were compared (public embed, images only;
logos and other non-images were not counted):

| Role | Folder id | Evidence |
|---|---|---|
| Parent. The share link. Not an ingest root. | `1-zxzR3aYVgfIgLGF-nHHssM_N6zunGOL` | 442 images. Set equals the union of the two children. |
| Ingest root, stick | `1k5icaxY3AKBD9z2-oIO6i42PUnq1gYUG` | 306 images, all inside the parent. `Products` 182, `Other` 54, `Services` 34, `Location/In Store Photos for walkthrough` 24 (HEIC), `Location/Photos of iron sets` 12. |
| Ingest root, swing-shack | `1n9pHD6hwr7oEfRBAGBriRrsqv_I-qGge` | 136 images, all inside the parent. Zero files shared with Stick. `Products` 66, `Services` 54, `Swing Shack RAW` 14, `Others` 2. |

`drive.map_names_roots` in `scripts/verify_specs.py` fails if this skill drops
any of those three ids, or drops an id that `BRAND_PUBLIC_ROOTS` still has.

**These ids are inside Stick. Do not ingest them as roots.**

| Id | What it is |
|---|---|
| `1WIYGaZAPCJvqIDyatroENqx-4DqCNgMz` | 36 images, all inside Stick: `In Store Photos for walkthrough` and `Photos of iron sets`. |
| `1FYeac0rVLezYFcS_02Yqsn7fOw1ecghd` | Stick's `Services` subfolder, 34 images, all inside Stick. `tests/test_google_drive_public.py` calls it `SERVICES_FOLDER_ID`. Ingesting it directly lands files at the images root instead of under `Services/`. |

**Not this library.** `scripts/weekly_drive_scrape.py` comments
`1hnkOUDX4mthQFcCktS5Caw7C7QU1ihH3` as Stick. That folder has 11 uuid-named
jpegs and shares zero image ids with Stick or the parent. The script also
hardcodes `/Users/fivefriday/...`, which `AGENTS.md` already calls a dead path.
Leave it commented.

The Swing Shack root is **publicly listable**, so the public HTTP path works for
it. Its only `source.json` entry was a 2026-07-29 OAuth run that errored on all
122 files and downloaded none, which is why `images/` held 121 `.visual-dna.json`
files and no actual images for months.

`gd.list_public_folder()` returns `folder` as the **relative path label**, not a
boolean. Truth-testing it counts every file as a subfolder.

## Social — Meta Graph, already wrapped

`_lib/meta_api.py`: `list_recent_posts`, `list_recent_posts_for_brand`,
`get_post_insights`, `get_post_comments`, `list_page_posts`,
`get_page_post_insights`. Credentials resolve per brand via
`data/integrations/<brand>/instagram.json` → `credential_env`.

`scripts/audit_social.py <brand>` walks `paging.next` for the whole catalogue with
insights and full-resolution images. **Known bug:** requests image metrics for all
media, so reels return nothing — on Stick that is 130 of 261 posts.

Do not scrape Instagram HTML. Logged out it yields 12 posts as 640px centre-crops,
and the `oh=` signature covers the transform so URLs can't be rewritten for full
resolution.

## Paid ads — Meta Marketing API, read-only

Both ad accounts are wired in (`_META_ADS_ACCOUNT_FOR_BRAND` in `app.py`).
Nothing in this repo can change an ad.

| Need | Use |
|---|---|
| campaign totals, current vs previous window | `GET /api/meta/ads/cache/<brand>?period_days=31` |
| every ad scored, with one action each | `GET /api/meta/ads/brain/<brand>` (`&refresh=1` to re-read Meta) |
| the rules and thresholds | `_lib/ads_brain.py` → `score_snapshot()`, `THRESHOLDS` |
| the morning brief, both brands | `/ads-brief` (written by the `ads_brief` job, 07:15 SAST) |
| creative tests proposed and tracked | `_lib/ads_creative.py`, shown on the brief |

**Ad creative is real human video.** Christelle's rule, from her own testing: real
people on video outperform everything else, and static vs video has already been
tested (video won). The one exception is retail, where an animated still of the
product can be an ad. Do not propose, render or generate a plain static image, or a
generated video, as an ad. Image generation and the measured post templates are for
organic feed content: retail and service information, and keeping the feed full.
Scoring's `all_video` rule was retired in v1.1 for contradicting this.

`ads_brain.fetch_snapshot()` reads at ad level: quality rankings, placements, the
ad set's performance goal, creative copy, media type and destination link.
`score_snapshot()` is pure and deterministic — no model.

**`data/meta-ads.json` is synthetic** (built from Instagram posts in August). Never
read it for ads work.

**Do not open an ad's editor in Ads Manager to read it.** On 2026-10-08 opening
`/adsmanager/manage/ads/edit` for one ad left an unpublished "Creative" draft on it
with nothing typed. Read creative through the API.

**Meta says `ACTIVE` for a campaign whose `stop_time` has passed.** Ads Manager
shows it as Completed. `ads_brain._is_running()` checks the dates.

## Image generation — Krea

See the `krea-lab` skill for model ids, schemas and the resolution allowlist.
Campaign OS calls it through `_lib/image_gen_router.py` → `_lib/krea_mcp.py`.

## The Mac — `fives-mac-mini`, M4 / 16 GB

Reached from the Linux desk over Tailscale via
`agent-control/bin/mac-bridge-client.py dispatch --wait --prompt '…'`.
SSH is **off** (port 22 refused), so the bridge is the only shell. Taildrop works
(`tailscale file cp <file> omarchy:` → `tailscale file get <dir>`).

| | |
|---|---|
| Hermes | v0.21.3, **34 profiles**, **18 running as gateways** |
| Claude Code | **not installed** |
| Cursor CLI | installed (`cursor-agent`) |
| Railway CLI | installed and linked to `heartfelt-wholeness` |
| Repos | `agent-control`, `swing-shack-dashboard-main`, `ClubLabKnowledgeBase` |

**Campaign OS Hermes profiles:** `cos-foreman`, `cos-scout`, `cos-caption`,
`cos-image`, `cos-interpreter`, `cos-reactive`, `cos-triage`, `mark-insight`.
**A v2 set also exists:** `imagegen_v2`, `copywriter_v2`, `forge_v2`, `lab_v2`,
`memories_v2`, `retina_v2`, `scout_v2`.

**Dormant automation.** `hermes cron list` reports *no scheduled jobs* while its
cron files and ticker heartbeats remain. launchd plists exist but are not running
for: `ig-business-fetch`, `meta-analytics`, `meta-token-refresh`,
`competitor-tracker`, `freshness-check`, `postiz-analytics`, `ubersuggest-fetch`,
`ubersuggest-refresh`, `path2-chain`. **Check whether a job already exists before
writing one.**

## Prod

`https://swing-shack-dashboard-production.up.railway.app`, auto-deploys from
`main`. `COS_JOB_TOKEN` (bearer) reaches `/api/jobs/*` and the `DUAL_AUTH_PATHS`
subset of `/api/ops/*`. Everything else — `/api/krea/*`, `/api/ops/runbook`,
`/api/meta/*` — is **session-cookie only**, so bearer returns 401.

## Known wrong

`/verify-specs` now checks all of this on demand, for free
(`scripts/verify_specs.py`). Run it instead of trusting the list below.

**Fixed 2026-10-05, verified by probing:**

- **Krea model ids were dead.** The one-shot path routed to
  `ideogram/ideogram-4`, which does not exist — the 4.x line ships as
  `ideogram/ideogram-4.5` and `ideogram/ideogram-4.5-precise`. `krea_mcp`
  and `app.py` defaulted to `flux-fast`, never a Krea id at all, and `app.py`
  also sent `ideogram/turbo` (live: `ideogram/ideogram-2-turbo`). A dead id can
  only 422, which is worth remembering when reading the one-shot plan docs.
  **Model ids are namespaced** — `bfl/`, `ideogram/`, `recraft/`, `krea/`.
  33 image models are live; `recraft-v3` and `recraft-v4` in
  `creative_director`'s registry are both gone, superseded by
  `recraft/recraft-v4.1-flash`.
- **`brand_dna.build_system_message()`** called every brand "a premium indoor
  golf studio in Johannesburg, SA". Stick is a fitting studio, workshop and
  retailer in **Paarl, Western Cape**. It now builds that sentence from
  `knowledge.json` → `verified_facts` (`verified_location`,
  `verified_business_mix`) and refuses to guess when they are absent.
- **The reels-metrics bug.** `audit_social.py` now holds one metric set per
  media type and narrows the request until the API accepts it, and prints an
  insights-coverage table so a blanked media type is visible.
- **Ingest could cross brands** — see the Drive section above.

**Still wrong, deliberately left:**

- **`ss-service-promo` has no partner-logo zone.** Real Services posts put a
  partner mark beside the lockup. Needs measuring with `campaign-os-template`.
- **Declared copy budgets are not safe limits.** 7 of 14 renderable packs
  cannot compose copy filled to their own `max_lines × max_chars_per_line`:
  `ss-did-you-know`, `ss-price-package`, `ss-price-list`, `ss-sale-offer`,
  `ss-service-promo`, `stick-coach-profile` and one more. Copy generation must
  stay under the declared number, not at it. Not fixed by guessing new values —
  changing a wrap width changes the layout, so these get re-measured against
  golden renders.
- **`_KREA_ASPECT_PIXELS`** is internally consistent and 4:5 normalises
  correctly, but the per-model size allowlist is still unverified against each
  model's own schema.

**Beware the plausible-looking check.** Three checks failed on their first run
because the *check* was wrong, not the code: measuring `max_lines` at
`max_font_px` when the composer shrinks to `min_font_px`, calling
`_inject_openrouter_references` positionally when it is keyword-only, and
filling zones with copy that did not match their shape. The zone rects were
measured from visible ink, so box height is roughly cap height, not line pitch —
font-metric geometry against those rects mis-reports working templates. Ask the
composer, not the metrics.

## Related

`campaign-os` (ops hub) · `krea-lab` (provider facts) ·
`campaign-os-template` (measure a template from reference images) ·
`agent-control-mac-bridge` (Mac dispatch)
