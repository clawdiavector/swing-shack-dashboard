# Context — Creative One-Shot Mode + Prompt Pipeline Cleanup

Read this first. `plan.md` is the design, `task-list.md` is the checklist. This file is
the "why" and the state of the world so a fresh session (human or agent) doesn't have
to re-derive it.

## Why this exists

Kyle manually prompted Krea.ai directly (outside Campaign OS) for Stick and Swing Shack
social posts, using Ideogram 4.0 and Recraft V4 with hand-written, flowing, specific
prompts that baked the final copy and logo directly into the image. Results were
consistently good — on-brand, correct text, correct colours.

Side by side, Campaign OS's own generation pipeline (`image_gen_router.py` +
`creative_director.py` + `brand_dna.py`) has been producing noticeably worse output for
the same kind of ask: garbled baked-in text, and at least one Stick generation that came
out in red/orange instead of navy/teal/mint.

This doc set captures the diagnosis of *why*, and the plan to fix it without breaking
the parts of the pipeline that already work correctly (the template/overlay production
path — see `data/brand-directory/*/templates/*/spec.json` — is NOT broken and is not in
scope for behaviour changes).

## Current architecture (as of this plan)

Three layers, in call order for a brand-aware generation:

1. **`campaign-os/_lib/creative_director.py`** — brand-aware prompt compiler. Loads
   `data/brand-directory/<brand>/bible-visual.json` + `palette/brand.json`
   (`_load_brand_context`, line ~639), builds a structured prompt as bracketed sections
   (`[JOB]`, `[BRAND]`, `[SUBJECT]`, `[NEGATIVE]`, etc. — `_assemble_master_prompt`,
   line ~774), and scores/recommends a model (`recommend_model`, line ~422;
   `pick_model`, line ~352) against a hardcoded capability matrix (`_MODEL_CAPABILITIES`,
   line ~59).
2. **`campaign-os/_lib/brand_dna.py`** — a *second*, independent brand-context loader.
   Also reads `bible-visual.json` (`load_brand_context`, line ~176) and builds its own
   system message (`build_system_message`, line ~238) with palette + look-and-feel
   keywords + a hardcoded negative tail.
3. **`campaign-os/_lib/image_gen_router.py`** — the actual HTTP layer (OpenAI, Krea,
   OpenRouter). For Krea/OpenRouter calls with a `brand_id`, it calls **both** (1) and
   (2) and concatenates their output (`generate_image`, line ~1035 for Krea, ~1119 for
   OpenRouter) before sending to the provider.

Real production image generation (the daily calendar pipeline) enters through two job
files, not through the dev-facing `/api/creative/*` routes:

- `campaign-os/_lib/jobs/layer5/draft_assets.py` — `_process_image_row`, line ~1219
- `campaign-os/_lib/jobs/layer5/create_photo_compose.py` — line ~207

Both call `creative_director.pick_model()` with **`"typography": False"` hardcoded**.
Both call `generate_image_with_persistence()` without passing `output_style`, so it
silently defaults to `creative_director._OUTPUT_STYLE_DEFAULT =
"photograph, no text, no logo, no watermark, no UI"`.

Dev/inspection-only surfaces that already exist and are **not** part of the production
job path:

- `POST /api/creative/compile` (`app.py:7684`) — wraps `compose_prompt()` directly,
  does accept a caller-supplied `output_style`.
- `POST /api/creative/model-route` (`app.py:7789`) — wraps `recommend_model()` for
  inspection only, does not generate anything.
- `POST /api/creative/from-reference-and-product` (`app.py:7735`).

## Confirmed root causes (full diagnosis in prior session, condensed here)

1. **Stale draft brand file actively contradicts itself for Stick.**
   `data/brand-directory/stick/bible-visual.json` is marked `"confidence": "draft"` and
   still carries `look_and_feel_keywords: ["true black", "signal red accent", ...]` —
   known-stale per Kyle's own correction weeks earlier (live templates are navy `#073C52`
   / teal `#00B3BA` / mint `#24FFAF`, confirmed in every `templates/*/spec.json` and in
   `palette/brand.json`). Nothing in `creative_director.py` or `brand_dna.py` checks the
   `confidence` field — both load it unconditionally. `brand_dna.build_system_message()`
   even emits the contradiction in one message: "...do not drift to stock-photo
   teal/green or bright orange. [...] Look and feel: true black, signal red accent...".
   Swing Shack's `bible-visual.json` does **not** have this problem — its keywords
   already match its real palette — which is why this is a Stick-specific, file-content
   bug, not a universal code bug.

2. **Production pipeline cannot route to a typography-capable model.**
   `pick_model()` can choose `ideogram/ideogram-3` for typography jobs, but both real
   call sites hardcode `"typography": False"`. Separately, **Recraft is entirely absent**
   from `_MODEL_CAPABILITIES` in `creative_director.py`, despite being one of the two
   models (with Ideogram 4.0) that worked in manual testing. Even a code change to flip
   `typography: True` could not select Recraft today — it has to be added to the matrix
   first.

3. **Negative prompt is not a real negative input for most of these providers.**
   `build_negative_prompt()` returns a long comma list (14 global quality rules + golf
   rules + brand exclusions). For providers without a structured negative field
   (gpt-image-1, OpenRouter chat-completions models), this list is embedded as plain
   text inside the same prompt string the model reads to decide what to draw, under a
   `[NEGATIVE]` label. Per our own Krea research this is the opposite of recommended
   practice for some models (Krea 2 specifically: "overloading negatives can reduce
   output quality").

4. **Double brand-context injection dilutes the actual creative ask.**
   For Krea/OpenRouter + `brand_id`, `image_gen_router.py` runs the prompt through
   *both* `creative_director.compose_prompt()` (bracketed sections) *and*
   `brand_dna.build_system_message()` (prose system message), nesting one inside the
   other (`f"{sys_msg}\n\n---\n\nUSER REQUEST: {enhanced}"`). The job-specific detail —
   what should actually be in the frame — ends up as a small fraction of a long,
   repetitive, label-heavy document, which is consistent with at least one wildly
   off-topic generation Kyle got back.

## Repo conventions this plan must respect

(Source: `docs/dev/conventions.md`, `docs/dev/how-to.md`, `docs/dev/jobs.md` — read
those files directly before implementing, this is a summary.)

- **Branches**: feature work targets `feat/*` → PR → merge to
  `integrate/campaign-os-brand-lanes-v1` first, not `main` directly. Never push
  `main`/`master`/`develop` without Kyle's explicit approval.
- **`data/` is seed-only.** "No automation commits to repo `data/`." The content fix to
  `data/brand-directory/stick/bible-visual.json` (task P1-1) is a manual, interactive,
  Kyle-directed edit in this session — not a scheduled job commit — but confirm this
  reading with Kyle before it lands, and definitely do not wire any *automated* job to
  rewrite brand bible files going forward.
- **No direct writes to `campaign-data.json`** from agents.
- **Tests**: `cd campaign-os && python3 -m pytest --collect-only -q` to count; never
  quote a stale test count in prose.
- **Local run**: `export DATA_DIR=/tmp/campaign-os-scratch; export COS_JOB_TOKEN=dev-token; cd campaign-os && python3 app.py`
  — use a scratch `DATA_DIR`, never point local runs at the real Railway volume.
- **Cost caps already exist and must stay respected**: `CAMPAIGN_OS_MAX_IMAGES_PER_DAY`
  (default 2/brand/day submit cap), `CAMPAIGN_OS_DAILY_LLM_CAP_USD` (default $5/day
  modelled spend cap), enforced in `llm_spend.check()` ahead of every generate call. Any
  new one-shot mode goes through the same `generate_image()` / `generate_image_with_persistence()`
  entry points, so it inherits these caps automatically — do not bypass them.
- **Job registration recipe** (`docs/dev/how-to.md` → "Add a registered job"): copy a
  sibling job in the same layer, define `JobSpec`, register in `registry.py`, add
  pytest under `campaign-os/tests/`, wire cron in `.github/workflows/` only if it needs
  one. A one-shot creative mode is more likely an *interactive* action (operator clicks
  "generate creative post") than a cron job — confirm with Kyle which shape he wants
  before building a scheduler for it.
- **Existing GH workflow to extend, not duplicate**: `.github/workflows/lint-brand-copy.yml`
  already lints brand copy. A brand-*visual*-bible lint (task P1-2) should probably be a
  sibling workflow (`lint-brand-visual.yml`) or an added check in the same one — check
  what `lint-brand-copy.yml` actually runs before deciding.

## Things that already exist and should be reused, not rebuilt

- **Prompt traceability already lands on disk.** `generate_image_with_persistence()` in
  `image_gen_router.py` (line ~1243) already writes `prompt`, `prompt_used`,
  `negative_prompt`, `sections`, `model_routing`, `model`, `provider`, `cost_usd` into
  the `.meta.json` sidecar next to every saved image
  (`data/brand-directory/<brand>/images/gen-<brand>-<ts>.png.meta.json`). The data Kyle
  asked to "see the prompt used to create the post" is already being captured — the gap
  is surfacing it in the UI he actually looks at when reviewing drafts, not capturing it
  in the first place.
- **Partial UI already renders some of this.** `campaign-os/visualizer.html:798` shows a
  truncated `prompt_used`. `campaign-os/marketer-workspace.html:721,1007-1009` shows
  `negative_prompt` and `model_routing.recommended` / `.why`. Neither of these has been
  confirmed (by this plan) to be the surface Kyle actually uses day to day for reviewing
  draft posts — that needs to be found (likely `image-lab.html`, `image-portal.html`, or
  the Campaign Heroes `/app` React desk under `web/`) and either confirmed to already
  show this, or extended.
- **A learning loop already exists for Swing Shack, not Stick.**
  `campaign-os/_lib/feedback_loop.py` reads
  `data/brand-directory/<brand>/feedback/{image-performance.json,learned-signals.json}`
  and feeds a "win profile" fragment back into future prompts
  (`image_gen_router._compose_full_prompt` → Layer 1, line ~392). Swing Shack has both
  files populated (`data/brand-directory/swing-shack/feedback/`). **Stick has neither
  file at all.** This is the natural mechanism for "growth and refinement" Kyle asked
  about — it is not yet wired up for Stick (or presumably Bag Drop / Takomo).

## Non-goals for this plan

- Not changing the default template/overlay production pipeline's behaviour
  (`overlay=True`, `typography=False` stays the default for calendar-driven posts).
  That pipeline is correct for its job (guaranteed-exact logo/CTA/compliance copy at
  scale) and is out of scope.
- Not building a brand-new image provider integration. Krea, OpenAI, OpenRouter are
  already wired; this plan only changes prompt composition, model routing inputs, and
  UI surfacing.
- Not auto-publishing anything the one-shot mode produces. Every output needs a human
  proof-before-publish step (see `plan.md` → Testing).

## Open questions for Kyle (resolve before/while executing `task-list.md`)

1. Is the one-shot creative mode an **interactive operator action** (click "generate
   creative post" in some UI, pick brand + template-or-freeform + copy) or should it
   also be schedulable/cron-able later? Changes whether it needs a `JobSpec` now.
2. Where does Kyle actually review draft images today before approving? (`image-lab.html`?
   `image-portal.html`? Campaign Heroes `/app`?) Needed to know where to add the prompt
   trace panel instead of guessing.
3. Confirm the `data/` "no automation commits" convention doesn't block this
   interactive session from committing the `bible-visual.json` content fix directly.
4. Which brands beyond Stick need the same bible-visual.json audit? (Bag Drop, Takomo
   have entries under `data/brand-directory/` — not yet checked in this plan.)
