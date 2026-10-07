# Campaign OS — working notes for Claude

Marketing OS for **Swing Shack**, **Stick** and **Bag Drop**. Flask app in
`campaign-os/`, brand data in `data/brand-directory/`, deployed to Railway from
`main`.

Read [`AGENTS.md`](AGENTS.md) for the standing rules — branch policy, what not to
touch, data safety. This file is the orientation that stops the mistakes we
actually keep making.

## Search before you build

This repo looks sparse and is not. 109 lib modules, a 2,700-line retrieval
engine, a deterministic PIL composer, 13 measured post templates across two
brands, wrapped clients for Meta Graph and Krea.

On 2026-10-05 a full day went into art-directing a poster that
`archetype_compose.compose_post_for_channels()` already rendered from an existing
template — the "winning prompt" turned out to be a description of a reference
image sitting in `templates/fitting-headline/references/`. The same day, an hour
went into scraping Instagram while `_lib/meta_api.py` sat unused.

**Load the `campaign-os-map` skill before building anything.** It lists what
exists, what's a stub, and what's measurably wrong.

The marketing capability ships as a plugin in this repo —
[`plugins/campaign-os/`](plugins/campaign-os/README.md): four commands
(`/audit-social`, `/render-post`, `/schedule-post`, `/verify-specs`) and six skills
(`campaign-os-map`, `campaign-os`, `campaign-os-template`, `krea-lab`,
`brand-voice-truth`, `schedule-from-anywhere`). Install it
with `/plugin marketplace add .` then `/plugin install campaign-os@campaign-os`.
Onboarding a teammate: [`docs/ONBOARDING-MARKETING.md`](docs/ONBOARDING-MARKETING.md).

| Before you… | Check |
|---|---|
| prompt an image model for a layout | `data/brand-directory/<brand>/templates/` |
| write an API client | `grep -l <service> campaign-os/_lib/*.py` |
| build context assembly or retrieval | `_lib/p11_context_engine.py` |
| schedule a job | the Mac's launchd plists — it may exist and be dormant |

## Deterministic beats generated

If a layout is known, render it. `compose_post_for_channels()` produces
pixel-identical output in ~200ms with correct text, free. An image model garbles
type, drifts off palette, invents logos, and costs credits and one-shot slots per
attempt.

Nothing should run at a higher tier than its uncertainty requires:
**lab → script → job → Hermes agent.** Reach for Krea only for genuinely new
looks or photography that doesn't exist, then measure the winner into a template
with `campaign-os-template` so it graduates down.

## Brand data

`data/brand-directory/<brand>/` — palette, typography, voice, copy bank,
`visual-spec/archetypes.json` (template specs), `templates/<name>/` (references,
photos, golden renders).

**Raw images are not in git.** They live in Google Drive as source of truth and
are pulled by `campaign-os/scripts/ingest_public_drive_folder.py`. Which folder
is the share link, which two are the per-brand ingest roots, and which ids are
subsets rather than roots is the "Brand imagery" section of `campaign-os-map`.
The ingest script's constants are the children only. Note the
`.gitignore` pattern only matches one level, so files under `images/<subdir>/`
currently escape it — ~421 MB is committed that shouldn't be.

**The brand bibles drift from the real feed.** Stick's tagline
"Better begins here." appears in 173 of 258 captions and closes 121 of them, and is in no brand file; the
bible is entirely fitting/TrackMan while 39% of posts are product arrivals. Treat
`feedback/instagram-audit.json` as the source of real voice.

## Hosts

| | Linux desk (omarchy) | Mac (fives-mac-mini) |
|---|---|---|
| Interactive Claude | yes | not installed |
| Hermes agents (34 profiles) | never | yes |
| Scheduled jobs | never | yes |
| Railway CLI | no | yes |

Linux plans and spawns; the Mac executes and schedules. Reach the Mac with
`agent-control/bin/mac-bridge-client.py dispatch --wait --prompt '…'` — SSH is off,
so the bridge is the only shell.

## Prod

`https://swing-shack-dashboard-production.up.railway.app`, auto-deploys from
`main`. `COS_JOB_TOKEN` reaches `/api/jobs/*` and the `DUAL_AUTH_PATHS` subset of
`/api/ops/*`. Everything else — `/api/krea/*`, `/api/meta/*`, `/api/ops/runbook` —
is session-cookie only and returns 401 to bearer.

**Never push `main` without Kyle or Christelle approving it in the current message.**
Either of them can approve their own merge — the rule stops agents shipping to prod
unasked, not people.

## Verify, don't trust

Specs here drift from reality silently and nothing checks. Six were found wrong in
one day by probing live. Before relying on a model id, a resolution, a scrim value
or a template cap, confirm it — the `krea-lab` skill has the method, and the
failures are free.
