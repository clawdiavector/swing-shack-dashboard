# Plan — Creative One-Shot Mode + Prompt Pipeline Cleanup

Read `context.md` first for the diagnosis this plan is built on. This file is the
design and the testing/growth strategy. `task-list.md` is the executable checklist.

## Goal

Two things, kept deliberately separate:

1. **Fix the prompt pipeline** so brand-aware generation (template backgrounds, product
   shots, anything going through `creative_director`/`brand_dna`) stops contradicting
   itself and stops drowning the actual creative ask in boilerplate. This benefits the
   existing template/overlay production path too, even though its *behaviour*
   (overlay=True, no baked text) doesn't change.
2. **Add a one-shot creative mode** that can deliberately do what Kyle did by hand —
   bake final copy + logo into the image via Ideogram/Recraft — as an explicit, opt-in,
   human-reviewed path, not a replacement for the template pipeline.

Plus: make the prompt that produced any given image visible wherever Kyle actually
reviews drafts, and wire Stick into the same learning loop Swing Shack already has.

## The two-path architecture (the dividing line)

This is the answer to "fine lines between brand, creative, correctness, consistency":

| | **Template / Overlay** (existing, default) | **One-Shot Creative** (new, opt-in) |
|---|---|---|
| When | Scheduled calendar posts, anything with a CTA/price/compliance copy | Hero posts, campaign moments, exploratory/editorial looks |
| Text | AI generates background only; exact copy composited deterministically afterward | AI bakes the literal approved copy into the image directly |
| Logo | Composited from the real asset file, pixel-exact every time | Either omitted (safer) or AI-rendered and manually verified every time |
| Model | `typography: False` always; flux/gemini class | `typography: True` allowed; Ideogram 4.0 / Recraft V4 class |
| Guarantee | Zero drift, 100% correct copy, scales unattended | Higher creative ceiling, non-zero risk of wrong/garbled text |
| Review | Can run unattended (cron-driven) within existing caps | **Always** human-proofed before publish, no exceptions |

Rule of thumb: if a wrong word in the image would be a real problem (wrong offer, wrong
CTA, banned phrase, misspelled brand name), it goes through the template pipeline. If
it's a one-off hero piece a human will look at before it goes anywhere, one-shot mode is
fair game.

## Phase 1 — Stop the bleeding (prompt pipeline cleanup)

Fixes that improve *every* existing generation, template backgrounds included, without
changing any pipeline behaviour flags.

1. **Correct `data/brand-directory/stick/bible-visual.json` content.** Replace the
   true-black/signal-red `look_and_feel_keywords` and the matching `visual_philosophy`
   line with the real navy/teal/mint language, and move `confidence` off `"draft"` once
   corrected. This alone should stop the red/orange drift seen in testing.
2. **Add a confidence gate.** `creative_director._build_brand_block()` and
   `brand_dna.build_system_message()` should both either (a) skip
   `look_and_feel_keywords` entirely when `confidence == "draft"`, or (b) prefix them
   with a visibly lower-trust framing the model is less likely to anchor on. Prevents
   this exact failure mode recurring for any brand whose bible drifts out of date again.
   Pair with a lint check (Phase 1, item 4) so drift is caught before it reaches a
   prompt at all.
3. **De-duplicate the double brand injection.** `image_gen_router.py`'s Krea/OpenRouter
   branches currently run `creative_director.compose_prompt()` *and*
   `brand_dna.build_system_message()` and nest one inside the other. Pick one as the
   source of truth for the BRAND block (recommend `creative_director`, since it's the
   one with job-type-aware model routing and the structured sections Kyle's workspace
   UI already partially renders) and have the other either stop running for this path
   or only contribute the parts the first doesn't cover (e.g. keep `brand_dna`'s
   reference-image attachment handling if `creative_director` doesn't have an
   equivalent — check before removing).
4. **Strip bracket labels from the string actually sent to the model.** Keep
   `sections: list[dict]` as the structured return value for UI rendering (that's
   genuinely useful, keep it), but have `_assemble_master_prompt()` produce a flowing,
   unlabeled paragraph for the text actually POSTed to the provider — no `[JOB]`,
   `[BRAND]`, `[NEGATIVE]` literal headers in the wire prompt. This is the single
   highest-leverage fix for the "lots of text saying what something should look like"
   problem Kyle flagged — it's the gap between what I hand-wrote (one tight paragraph)
   and what the pipeline currently sends (a labeled document).
5. **Scope and shorten the negative prompt; stop always appending it as prose.** For
   providers/models with a real negative-prompt parameter, send it there. For providers
   without one (most of the wired paths today), fold only the brand- and job-specific
   negatives inline near the relevant subject instead of appending the full 20+ item
   global/golf list every time — the global quality rules (no distorted hands, no extra
   fingers, etc.) are mostly irrelevant noise for a flat gradient background or a
   product shot and just dilute signal.
6. **Add a brand-visual lint**, sibling to the existing `.github/workflows/lint-brand-copy.yml`.
   At minimum: flag any `bible-visual.json` whose `look_and_feel_keywords` /
   `visual_philosophy` text contains a colour word that isn't one of the hex names in
   that brand's `palette/brand.json` (simple keyword/hex cross-check, not a full colour
   parser). Would have caught the Stick contradiction automatically.

## Phase 2 — One-shot creative mode

1. **New job type / mode flag**, e.g. `job_type="creative_oneshot"` (or reuse the
   existing `"poster"` job_type in `_infer_requirements`/`recommend_model` if it already
   fits — check `requirements.get("job_type") == "poster"` weighting before inventing a
   new one; `"poster"` already weights typography at 0.40, which is close to what's
   needed). Confirm with Kyle (`context.md` open question 1) whether this needs to be
   schedulable or stays a manual/interactive trigger before deciding if it needs a
   `JobSpec`.
2. **Unlock typography routing for this mode only.** The two production call sites
   (`draft_assets.py`, `create_photo_compose.py`) keep `typography: False` — do not
   change their default. The new one-shot entry point passes `typography: True`
   deliberately.
3. **Add Recraft to `_MODEL_CAPABILITIES`.** Needs real capability scores — don't guess
   them, run a handful of live test generations across job types (apparel/equipment/
   poster) with Recraft V4 and score fidelity/photorealism/material/typography from
   actual results, the same way the existing entries were presumably calibrated.
   `"verified": True` only after a live-tested call succeeds (matches the existing
   convention — see the comments already in the matrix about what's live-verified vs
   not).
4. **Explicit output_style override for this mode.** Do not rely on
   `_OUTPUT_STYLE_DEFAULT`'s "no text" default — the caller must pass an
   `output_style` (or equivalent param) that describes exactly how the baked text
   should look (placement, colour, weight), matching the technique proven in manual
   testing: scene description, then the literal final copy in quotes, then styling
   instructions for that copy.
5. **Feed real approved copy, not inferred wording.** The literal headline/CTA strings
   must come from `data/brand-directory/<brand>/copy/{headlines.md,ctas.md}` (or
   whatever the calendar/content item already resolved), not be left for the model to
   paraphrase from brand philosophy text. This is the same discipline used when hand
   writing the working prompts earlier in this project.
6. **Logo handling stays conservative by default.** Baking the literal logo file into
   an AI generation is not reliable (confirmed by the Kling o1 "Learn begins hen"
   garbled CTA band in testing). Default one-shot mode to *not* asking the model to
   render the logo — composite it afterward the same way the template pipeline does —
   and only allow AI-rendered logo attempts as an explicit opt-in with a loud UI warning
   (the `_PRESERVE_TRIGGERS` / "logo-preserve likely to drift" warning machinery in
   `image_gen_router.py` already exists for a similar case — reuse that pattern).

## Phase 3 — Prompt traceability in the UI Kyle actually uses

1. Resolve `context.md` open question 2 — confirm which surface is the real daily
   review flow.
2. If `visualizer.html` / `marketer-workspace.html` are dev tools and not the daily
   flow, add an equivalent "show the prompt" panel (prompt_used, negative_prompt,
   model + why it was picked, cost) to the real one, reading straight from the
   `.meta.json` sidecar that's already being written — no new data capture needed,
   this is a UI task only.
3. Make this visible specifically wherever Kyle approves/rejects a draft, not buried in
   a separate debug page — the whole point is catching a bad prompt before it becomes a
   bad post, not after.

## Testing strategy

### Automated

- `cd campaign-os && python3 -m pytest --collect-only -q` before and after every change
  in this plan, to catch count drift (do not hardcode a number anywhere — see
  `conventions.md`).
- Extend `campaign-os/tests/test_image_pipeline_p2_provider.py` (already tests
  `pick_model`) with cases for: `typography: True` now reachable for one-shot mode,
  Recraft appearing in `_MODEL_CAPABILITIES` once added, confidence-gated brand blocks
  (draft bible → keywords excluded).
- New test: load every `data/brand-directory/*/bible-visual.json`, assert
  `look_and_feel_keywords` doesn't contain a colour word absent from that brand's
  `palette/brand.json` hex names (same check as the Phase 1 lint, as a unit test so it
  runs in CI, not only on push).
- New test: assert `_assemble_master_prompt()`'s provider-bound output string has no
  literal `[SECTION]` bracket headers once Phase 1 item 4 lands.

### Manual / practical (the part that actually catches creative-quality regressions —
automated tests can't judge "does this look like Stick")

1. **Golden prompt set.** Pick ~10 fixed test cases spanning brands (Stick, Swing Shack,
   at minimum) × job types (apparel, equipment, poster/one-shot) × with/without
   reference image. Keep the exact inputs in this plan's folder
   (`docs/plans/creative-oneshot-mode/golden-prompts.md` — create when Phase 1 starts)
   so "did this get better or worse" is a repeatable comparison, not a vibe check
   against whatever Kyle happened to type that day.
2. **Before/after side-by-side.** Run the golden set through the pipeline before a
   change and after, save both sets of outputs under
   `data/brand-directory/<brand>/images/_test/<date>/`, eyeball them side by side.
   This is cheap (within the existing `CAMPAIGN_OS_DAILY_LLM_CAP_USD` cap) and is the
   actual regression test for prompt-quality changes — a pytest can check the code
   runs, it can't check the output looks right.
3. **Proofreading checklist for one-shot mode specifically**, run on every output before
   it's approved:
   - Every word of baked text matches the approved copy exactly (character by
     character, not "close enough").
   - Colours match the brand's `palette/brand.json` hex values, not vibes.
   - No banned phrase from `voice/do-say-dont-say.md` snuck in.
   - If a logo was AI-rendered (opt-in only), it is correct — if in doubt, redo without
     it and composite the real asset instead.
4. **Local dev loop**: always `export DATA_DIR=/tmp/campaign-os-scratch` per
   `docs/dev/how-to.md` — never test against the real Railway volume, and the cost caps
   there are shared with production unless `DATA_DIR` is pointed elsewhere, so a scratch
   dir also protects the real daily spend cap from test runs.

## Growth / refinement plan

1. **Wire Stick (and Bag Drop, Takomo) into `feedback_loop.py`.** Swing Shack already
   has `data/brand-directory/swing-shack/feedback/{image-performance.json,
   learned-signals.json}` populated; Stick has neither file. Creating them (even empty,
   schema-valid scaffolding) and hooking up whatever currently feeds Swing Shack's
   `image-performance.json` (check `feedback_loop.py` for the ingestion side — not yet
   traced in this plan, needs a follow-up read) is how prompt quality improves on real
   performance data over time instead of one-off manual tuning.
2. **Treat `_MODEL_CAPABILITIES` as a living config, not a one-time table.** As Krea
   adds/changes models (it does — see the "live-verified 2026-08-31" comments already
   in the file), schedule a periodic (monthly?) pass: re-verify `verified: True` flags
   still hold, add new models worth scoring (this plan already adds Recraft; others
   will show up), retire ones Krea drops.
3. **Brand bible confidence as a review cadence, not a one-time fix.** Once Stick's
   `bible-visual.json` is corrected (Phase 1), put a reminder in whatever cadence Kyle
   already uses for brand reviews to re-check `confidence` status for every brand
   quarterly, or whenever templates visibly change — this is exactly how it went stale
   the first time.
4. **Extend the golden prompt set over time** as new templates/brands/job types are
   added, instead of letting it fossilize at the ~10 cases from Phase 1 — it should grow
   roughly in step with the template catalogue.
5. **A/B the two paths once there's real data.** Once one-shot mode has shipped enough
   posts to have performance data in `feedback_loop`, compare its win-rate against the
   template/overlay path's for comparable post types — that's the real answer to "is
   the extra creative ceiling worth the drift risk," not a one-time judgment call.
