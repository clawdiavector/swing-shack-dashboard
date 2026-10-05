# Task List — Creative One-Shot Mode + Prompt Pipeline Cleanup

Checklist form of `plan.md`. Each task: file(s), what to do, how to know it's done.
Work phases in order — Phase 1 is low-risk and benefits the existing pipeline
immediately; Phases 2-3 are additive (new mode, doesn't touch existing behaviour);
Phase 4 is ongoing, not a one-time checklist.

Effort tags: **S** = under an hour, **M** = a focused session, **L** = multi-session.

## Status update — 2026-10-02

Real build moved faster than this doc. A one-shot creative mode
(`draft_oneshot.py`, `finalize_draft_oneshot_from_krea_poll`,
`oneshot_model` operator override) already shipped, ahead of most of Phase 2
below — treat Phase 2 as "verify what exists matches this shape" not "build
from scratch."

What's actually landed, verified against the real code (not assumed):

- **Async plumbing (this doc's old P-A/B/C/D, diagnosed 2026-10-02 against a
  "not generating images" report)** — shipped in `main@f95987b9` the same
  day: `background_plate=True` on the Krea call, `image_jobs_state`
  submit/waiting handoff, `"draft_oneshot"` added to the poller's action
  filter, and a dedicated `finalize_draft_oneshot_from_krea_poll()` completion
  path. Confirmed by reading current `draft_oneshot.py` +
  `krea_poll_draft_images.py` line by line — this is done, not a TODO.
- **Render-text prompt formulation (new finding, higher priority than
  anything below)** — even with plumbing fixed, a live A/B test (same
  model, same literal line, COS wire vs. a hand-written short prompt) showed
  the COS wire reliably produced garbled hallucinated body text while the
  short prompt didn't. Root cause: `_build_brand_block()` was injecting
  brand-strategy prose (`Philosophy:`, `Composition rules:`, and a
  `text_policy` line that literally says "no model-rendered text") right
  next to the literal-text instruction, plus a `"You are creating:"` meta
  preamble, in a ~1000+ char prompt. **Fixed 2026-10-02** in
  `creative_director.py`: `render_text=True` jobs now get a stripped BRAND
  block (colour-hex anchor only), no JOB preamble, no `subject_bias.lean_toward`
  injection, no default composition/lighting padding, and a tighter 550-char
  cap (`_PROMPT_MAX_CHARS_RENDER_TEXT`) instead of 1200. Verified by
  simulation: output now matches the hand-written prompt's shape and length
  (527 chars). Full test suite run before/after: 49 pre-existing failures
  unrelated to this change, identical count both sides — zero regressions.
  P1-4 below (strip bracket labels from the wire prompt) was *also* already
  done separately (`wire_prompt` / `_assemble_wire_prompt`) — this status
  note supersedes that task's "not started" framing.

## Status update — 2026-10-02 (round 2, same day)

Formulation fix from round 1 wasn't enough on its own — live-tested against
your exact failing case (same model, Ideogram 3.0) and it still produced
garbled extra text (a fake tagline below the headline, garbled UI-looking
text on the mentioned TrackMan monitor and an overhead fixture). Root-caused
against a working reference prompt you supplied (same scene shape, same
model, clean both times):

- **"No other text" must be inline, not only in the separate
  `negative_prompt` field.** The working reference prompt states it directly
  in the main sentence; the COS wire's equivalent constraint only lived in
  `negative_prompt`, which wasn't attached in your test (and per Krea's own
  docs, isn't a true structured field for every model — it's cargo that can
  get lost). **Fixed**: `compose_prompt()`'s LITERAL TEXT section now reads
  `Render this exact line, character for character: "<line>". No other text
  anywhere in the image.` — inline, directly adjacent to the quote.
- **Naming a screen/monitor in the scene gives a text-strong model a second
  surface to hallucinate onto.** The `post_type == "coaching_promo"` scene
  string is hardcoded in `image_draft_context.py` and always says "TrackMan
  launch monitor glow" — that's where the garbled on-screen text came from.
  `oneshot_scene_prompt()`'s old behaviour stripped the background-plate
  suffix (which banned all text, wrong for render-text jobs) down to
  nothing, leaving no replacement safety net. **Fixed**: added
  `_RENDER_TEXT_SCENE_SUFFIX` in `draft_oneshot.py` — keeps the
  non-text-related safety ("single unified photograph," "no people
  required"), replaces the blanket text ban with an explicit "any monitor
  or screen visible is dark / unreadable glow, not legible content."
- Verified by simulating the exact failing case end to end — new wire prompt
  carries both fixes, 833 chars (down from the original uncapped
  double-composed ~3100, though still over the 550 target since the scene
  text itself is JOB content, not padding, and isn't subject to the trim
  loop — noted as a minor follow-up, not a quality risk).
- **Model research**: confirmed Ideogram 4.0 is real and live on Krea
  (`ideogram-v4` web slug) and is a genuine text-rendering upgrade over 3.0
  per Ideogram's own benchmarks — but the "good" reference result was
  actually tagged Ideogram **3.0** in Krea's UI, not 4.0 as assumed. Added
  `ideogram/ideogram-4` and corrected the stale `recraft/recraft-v3` entry
  to `recraft/recraft-v4` (kept v3 too — a test pins to it) in
  `_MODEL_CAPABILITIES`, both marked `verified: False` pending one real
  Krea call — scores are from published benchmarks, not live-tested here.
  Do not flip to `verified: True` without an actual successful call through
  Krea's MCP.
- Full targeted test run (32 tests across oneshot/model-select/wire-prompt
  suites): all green, no regressions.


## Status update — 2026-10-05 (the prompt rewrite)

Rounds 1 and 2 above were subtractive — they took bad content *out* of the
wire. The gen after them was better but still nowhere near the hand prompts,
because nothing was ever put *in*: the scene stayed a one-sentence empty bay,
the line stayed the calendar card's own title, and there was no type direction
at all. This round is the additive half.

New module `_lib/jobs/layer5/oneshot_art_direction.py` — scenes, type spec and
closing line, written against the reference set.

1. **Scene per post type.** A recipe for each of the five one-shot-eligible
   post types, split into two treatments. `fitting_headline`, `coaching_promo`
   and `service_hero` get a *photo*: a named hero subject (irons on a rack
   catching rim light; a figure from behind at the top of a backswing; a row of
   bays with one lit), accent lighting over the palette's field colour, and the
   "premium sports-apparel campaign photography, photo-real, shallow depth of
   field" phrase both winners used. `zine_collage` and `humour_card` get a
   *collage*: the named style, base + accent colours, and an explicit list of
   cutouts. Unmapped post types fall back to the old background-plate scene
   rather than failing. `background_plate_scene_prompt` is untouched — the
   template/overlay path still wants a quiet plate.
2. **Real headline, and a refusal.** `oneshot_copy_for_card()` replaces the
   `headline → title → generate anyway` ladder. It reads the calendar record's
   `headline`/`cta`, then falls back to the caption draft's `compose_headline`/
   `compose_cta` — the approved poster copy the *template* path already
   overlays, which one-shot had simply never looked at. With neither, it
   raises, and the row lands as `error` with a `copy:` note instead of
   painting a planning label onto a poster. A headline that equals the card
   title is refused for the same reason. `enqueue_oneshot_day` pre-flights
   through the same function, so these cards get skipped with a readable reason
   rather than burning a gen.
3. **One art-director paragraph.** `compose_prompt()` takes
   `literal_text_spec=` (the caller's own art-directed type direction — size,
   case, colour hex, position, "no background box", with the lines quoted in
   the case being asked for) which replaces both the generic LITERAL TEXT
   sentence and the separate TEXT PLACEMENT section, and `brand_colours_inline=`
   to drop the dangling "Colour anchor: …" fragment when the caller already
   names the hexes where they apply. The logo-lockup sentence is gone — the job
   composites the real asset, so the prompt says "keep the bottom-right corner
   clear" and never the word logo. OUTPUT STYLE now passes a caller-supplied
   full sentence through instead of wrapping it in "Render as …", so the wire
   ends the way the references did: "No other text, no logo, no watermark. 4:5
   portrait aspect ratio." The render-text cap went 550 → 1100; 550 was below
   the length of the prompts that actually won, and the trim loop cannot shrink
   a render-text prompt anyway (JOB and LITERAL TEXT are both exempt), so the
   real control is recipe length, which `test_oneshot_art_direction.py` holds.
4. **Models.** `ideogram/ideogram-4` and `recraft/recraft-v4` are in
   `_MODEL_CAPABILITIES`. One-shots now default to `ONESHOT_DEFAULT_MODEL =
   "ideogram/ideogram-4"` instead of ideogram-3, with a single automatic retry
   on `_ONESHOT_FALLBACK_MODEL = "ideogram/ideogram-3"` when Krea's upstream
   rejects the id — the hedge that makes defaulting to an unverified model
   string safe. Recraft V4 stays the operator pick via `oneshot_model` on the
   card and is now selectable (it was pinned to the stale v3 string). The
   generic `typography` branch in `pick_model` still routes to ideogram-3; only
   the one-shot route moved.

Tests: `tests/test_oneshot_art_direction.py` (new) covers per-post-type scenes,
treatment split, the full type spec, the budget, and what must never appear in
the wire. `tests/jobs/test_draft_oneshot.py` gains the title-only refusal, the
caption-draft copy fallback, default/override routing, and the model-rejection
fallback; its fixture now carries a real headline, because a title-only card no
longer generates.

**Still needs a live run, not code:** `ideogram/ideogram-4` and
`recraft/recraft-v4` are both `verified: False` and the exact Krea MCP model
strings have never been confirmed from here (no Krea credentials locally).
`GET /api/krea/models?category=image` on prod returns the real ids. Flip
`verified` only after a successful call, per the note already in
`creative_director.py`. The 2 Oct review card (`TPL · COACHING-POSTER-V1`) is
the old failed render and should be sent back, not approved.

---

What's still genuinely open from the phases below: P1-1 (Stick's
`bible-visual.json` content fix — lower urgency now since render-text jobs
no longer read `philosophy`/`look_and_feel_keywords` at all, but still worth
doing for non-render-text jobs), P1-6 (CI lint), the literal-line content
guard (a real headline required instead of falling back to the calendar
card's generic `title`), live-verifying ideogram-4/recraft-v4 against Krea's
actual MCP, and everything in Phase 4.

---

## Phase 0 — Before touching code

- [ ] **(S)** Resolve `context.md` open questions 1-4 with Kyle. Specifically: is
      one-shot mode interactive-only or also schedulable; where's the real daily
      review surface; confirm the `data/` edit in P1-1 is fine for this session;
      which other brands need the bible-visual.json audit.
- [ ] **(S)** `cd campaign-os && python3 -m pytest --collect-only -q` — record the
      current count locally (not in a committed doc) as your own before/after baseline.
      Do not put a specific number in any committed file per `conventions.md`.
- [ ] **(S)** Confirm target branch. Per `docs/dev/conventions.md`, feature work should
      land on `feat/*` → `integrate/campaign-os-brand-lanes-v1`, not `main`. Current
      repo state is on `main` — create the feature branch before the first code change.

## Phase 1 — Prompt pipeline cleanup (fixes existing generation quality, zero behaviour-flag changes)

- [ ] **(S) P1-1 — Fix Stick's `bible-visual.json` content.**
      File: `data/brand-directory/stick/bible-visual.json`.
      Replace `look_and_feel_keywords`, `visual_philosophy`, `philosophy`,
      `negative_prompts` entries that reference true-black/signal-red with
      navy `#073C52` / teal `#00B3BA` / mint `#24FFAF` language, consistent with
      `data/brand-directory/stick/palette/brand.json` and every
      `templates/*/spec.json`. Bump `"confidence"` from `"draft"` once corrected —
      only after Kyle or whoever owns brand content confirms it reads correctly.
      **Done when**: no colour word in the file contradicts `palette/brand.json`.

- [ ] **(M) P1-2 — Confidence gate in both brand-context loaders.**
      Files: `campaign-os/_lib/creative_director.py` (`_build_brand_block`, ~line 659),
      `campaign-os/_lib/brand_dna.py` (`build_system_message`, ~line 238).
      Add: if `bible.get("confidence") == "draft"`, either skip
      `look_and_feel_keywords` or clearly down-weight it in the emitted text (e.g.
      prefix "Unverified style notes, treat with caution:"). Add a unit test for both
      functions covering a draft-confidence fixture.
      **Done when**: a fixture brand with `confidence: draft` and contradictory
      keywords does not emit those keywords (or emits them clearly flagged) in either
      function's output.

- [ ] **(M) P1-3 — De-duplicate double brand injection.**
      File: `campaign-os/_lib/image_gen_router.py`, Krea branch ~line 1035-1057,
      OpenRouter branch ~line 1128-1151.
      Decide and implement: pick `creative_director.compose_prompt()` as the single
      BRAND-block source for these paths; stop also calling
      `brand_dna.build_system_message()` for the brand/philosophy/negative content —
      but first check whether `brand_dna.build_image_messages()` does something
      `creative_director` doesn't (reference-image attachment handling) and keep only
      that part if so.
      **Done when**: a brand-aware Krea/OpenRouter call emits one BRAND block, not two
      nested ones. Existing `test_p0_brand_context.py` and
      `test_image_pipeline_p2_provider.py` still pass or are updated to match the new
      shape.

- [ ] **(M) P1-4 — Strip bracket labels from the wire prompt.**
      File: `campaign-os/_lib/creative_director.py`, `_assemble_master_prompt`
      (~line 774).
      Keep `sections: list[dict]` as-is for UI consumption. Add a second assembly path
      (or a flag) that joins section *content* into flowing prose without the
      `[KEY]\n` literal headers for whatever string actually gets POSTed to the
      provider. Update `_compose_full_prompt` in `image_gen_router.py` to use the
      prose form, not `result.get("master_prompt")` as currently written if that's the
      labeled form.
      **Done when**: the string sent to Krea/OpenAI/OpenRouter for a brand-aware call
      contains no literal `[JOB]`/`[BRAND]`/`[NEGATIVE]` substrings. Add a test
      asserting this.

- [ ] **(M) P1-5 — Scope and shorten negative-prompt injection.**
      File: `campaign-os/_lib/creative_director.py`, `build_negative_prompt`
      (~line 290), `GLOBAL_NEGATIVES`/`GOLF_NEGATIVES` (~line 87-103).
      For providers without a structured negative field, trim what's injected inline
      to brand- and job-relevant items only (skip global anatomy/hands negatives for a
      flat-background or product-only job where they're meaningless). Consider: only
      include `GOLF_NEGATIVES` when the job actually has a club/ball/equipment subject;
      only include hand/anatomy negatives when `human_direction` is set.
      **Done when**: a flat-gradient-background job's composed prompt doesn't carry
      "no distorted hands, no extra fingers" noise unrelated to the ask.

- [ ] **(M) P1-6 — Brand-visual lint, CI-wired.**
      New file: likely `.github/workflows/lint-brand-visual.yml`, sibling to the
      existing `lint-brand-copy.yml` (read that file first — same shape, same
      trigger pattern). Script: cross-check every `bible-visual.json`'s colour-word
      mentions against its `palette/brand.json` hex names; fail CI on a mismatch.
      Also add the equivalent as a `campaign-os/tests/` pytest per `plan.md` Testing
      section, so it also runs locally, not only on push.
      **Done when**: CI fails if someone reintroduces the Stick-style contradiction in
      any brand's bible-visual.json; `pytest` catches it locally too.

## Phase 2 — One-shot creative mode

- [ ] **(M) P2-1 — Decide mode shape with Kyle** (depends on Phase 0 answer). Either
      reuse `job_type="poster"` in `creative_director._infer_requirements` or add a
      new `job_type="creative_oneshot"` with its own weight profile in
      `recommend_model()`. Document the decision at the top of this file once made.

- [ ] **(M) P2-2 — Add Recraft to `_MODEL_CAPABILITIES`.**
      File: `campaign-os/_lib/creative_director.py`, ~line 59-83.
      Run live test generations (use the golden prompt set, Phase "Testing") across a
      few job types with Recraft V4 through Krea, score fidelity/photorealism/
      material/typography from actual results, set `"verified": True` only after a
      live call succeeds through the real Krea MCP path (not assumed).
      **Done when**: `_model_allowed("recraft/recraft-v4")` (or whatever the Krea
      model id turns out to be — confirm via Krea's model list, don't guess the
      string) returns `True` and `pick_model()` can select it for a typography job.

- [ ] **(M) P2-3 — Unlock typography for one-shot entry point only.**
      New/modified caller (location depends on P2-1's decision — likely a new function
      alongside `_process_image_row` in `draft_assets.py`, or a new
      `/api/creative/generate-oneshot` route if it's interactive-only per Kyle's
      answer). Passes `typography: True` to `pick_model()`.
      **Explicitly do not** change the `typography: False` hardcoding in the existing
      `draft_assets.py:1223` / `create_photo_compose.py:210` call sites — those stay
      as-is for the template/overlay path.
      **Done when**: triggering one-shot mode for a brand with approved copy routes to
      `ideogram-3` or Recraft, verified by checking `result.model` / the sidecar.

- [ ] **(M) P2-4 — Explicit output_style for one-shot mode.**
      Do not rely on `creative_director._OUTPUT_STYLE_DEFAULT`. Build the one-shot
      prompt the way the manual-testing prompts were written: scene/style description,
      then the literal copy in quotes, then placement/colour/weight instructions for
      that copy. Pull the literal copy from
      `data/brand-directory/<brand>/copy/{headlines.md,ctas.md}` or the resolved
      calendar item's copy field — never let the model improvise wording.
      **Done when**: a one-shot generation for a known calendar item bakes in the
      exact approved headline/CTA text, verified by manual proof (see
      `plan.md` → Testing → Proofreading checklist).

- [ ] **(S) P2-5 — Logo stays composited by default; AI logo render is an explicit opt-in.**
      Reuse the existing `_PRESERVE_TRIGGERS` / "logo-preserve likely to drift"
      warning pattern in `image_gen_router.py` (~line 308-317) for this mode's logo
      toggle. Default off.
      **Done when**: one-shot mode without the opt-in produces no baked logo attempt;
      with the opt-in, the UI surfaces the existing drift warning.

## Phase 3 — Prompt traceability in the review UI

- [ ] **(S) P3-1 — Confirm the real review surface** (depends on Phase 0 answer 2).
      Check `image-lab.html`, `image-portal.html`, and the Campaign Heroes `/app`
      React desk under `web/` for existing draft-review UI.
- [ ] **(M) P3-2 — Add/extend the "show the prompt" panel** on that surface:
      `prompt_used`, `negative_prompt`, `model` + `model_routing.why`, `cost_usd` —
      all already in the `.meta.json` sidecar, no new capture needed (see
      `context.md` → "Things that already exist"). If `visualizer.html`/
      `marketer-workspace.html` already cover this adequately and ARE where Kyle
      reviews drafts, this task may already be done — verify before building anything
      new.
      **Done when**: Kyle can see, next to any generated draft, the exact prompt and
      model that produced it, without opening a `.meta.json` file by hand.

## Phase 4 — Growth / refinement (ongoing, not a one-time checklist)

- [ ] **(M) P4-1 — Trace Swing Shack's `image-performance.json` ingestion path** in
      `campaign-os/_lib/feedback_loop.py` (not yet read in this plan — do that first)
      to find what currently writes to it, then replicate for Stick: create
      `data/brand-directory/stick/feedback/{image-performance.json,learned-signals.json}`
      scaffolding and wire the same ingestion.
- [ ] **(L) P4-2 — Repeat P4-1 for Bag Drop and Takomo** once Stick is proven out.
- [ ] **(ongoing) P4-3 — Monthly-ish pass on `_MODEL_CAPABILITIES`**: re-verify
      `verified: True` flags, add new Krea models worth scoring, retire dropped ones.
- [ ] **(ongoing) P4-4 — Quarterly-ish brand bible confidence review**: re-check every
      brand's `bible-visual.json` `confidence` field against its current live
      templates; this is literally how Stick's went stale.
- [ ] **(ongoing) P4-5 — Grow the golden prompt set** (`golden-prompts.md`, created in
      Phase 1 testing) as templates/brands/job types are added.
- [ ] **(L) P4-6 — A/B template-overlay vs one-shot** once one-shot mode has shipped
      enough posts to have `feedback_loop` data for both paths on comparable post
      types.
