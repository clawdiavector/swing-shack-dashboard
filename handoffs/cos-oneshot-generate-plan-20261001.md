# Creative one-shot Phase 2 — generate and regen: implementation plan

**Date:** 2026-10-01
**Job:** `job-20261001-cos-oneshot-generate-plan` (read-only plan)
**Run:** `20261001T202426-plan-bfc759`
**Branch:** `plan/cos-oneshot-generate`
**Base:** `integrate/campaign-os-brand-lanes-v1`
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/plan/cos-oneshot-generate`
**Grounded against:** `a34153e5ef7d6c5b0ad81fb2873316d651b42b73`

**Builds on:** Phase 1 prompt pipeline (`handoffs/cos-oneshot-prompt-ready-for-testing-20261001.md`,
feature commit `b87d4dba`) and the day desk (`handoffs/cos-oneshot-calendar-ready-for-testing-20261001.md`,
feature commit `0df245ca`). Both are merged into the base.

**Scope of this ticket:** the operator action that generates one-shot cards for a chosen day through
the existing Create path into Review, the one-shot engine behind it, and regen. No live provider call
in any test. No publish changes.

---

## 0. Grounding — every claim below was measured today

### 0.1 `render_mode` already exists and already reaches the day desk

- `_lib/marketing_calendar.py:54` — `VALID_RENDER_MODES = ("template", "oneshot")`, `DEFAULT_RENDER_MODE = "template"`.
- `_lib/marketing_calendar.py:58-61` — `render_mode_for_record()`; absent / unknown / empty → `template`.
- `_lib/marketing_calendar.py:660-671` — `_EDITABLE_MOMENT_FIELDS` includes `render_mode`.
- `_lib/marketing_calendar.py:711-717` — `set_fields()` validates `render_mode` against the enum and raises on anything else.
- `_lib/unified_inbox.py:1327` — `week_board` rows carry `"render_mode": render_mode_for_record(record)`.
- `_lib/unified_inbox.py:2219` — `edit_item()` accepts `render_mode` for `calendar_candidate`.
- `web/src/components/posting/PostCard.tsx:302-323` — the Template / One-shot radio pair, saved on blur.

**Nothing reads `render_mode` to change what gets generated.** That is this ticket.

### 0.2 The Create path is a single, well-defined branch point

`_lib/l5_create_enqueue.py:16-57` — `create_actions_for_moment(brand_id, item_id, phase=...)` is the one
function that decides which L5 actions a moment gets:

- `phase="lodge"` → `["draft_caption"]` (+ `draft_gbp` when GBP is an intended channel)
- `phase="image"` → `["draft_gen_slots" | "draft_photo", "compose_post"]`
- `phase="all"` → caption + image + gbp

Callers: `_lib/unified_inbox.py:1651` (`_maybe_enqueue_l5_create`, lodge phase) and
`_lib/jobs/layer5/draft_assets.py:789` (`_maybe_enqueue_image_pipeline_after_caption`, image phase).
`_lib/l5_create_enqueue.py:86-92` already consults `check_brand_image_submit` before queuing `draft_photo`.

**Consequence:** one-shot routing is a branch inside `create_actions_for_moment`, not a parallel pipeline.

### 0.3 `typography` is hard-coded `False` in exactly two places

- `_lib/jobs/layer5/draft_assets.py:1113-1118` — `pick_model({... "typography": False ...})`
- `_lib/jobs/layer5/create_photo_compose.py:210-215` — same

Both **stay `False`**. The template lane composites text with Pillow afterwards
(`_lib/brand_overlay.py:263-325`), so asking the model for typography there is a regression, not a feature.

### 0.4 `pick_model` routes typography, but `_model_allowed` blocks unverified models

- `_lib/creative_director.py:450-460` — `typography: True` → `ideogram/ideogram-3` on `krea`, or
  `google/gemini-2.5-flash-image` on `openrouter` when Krea is not connected.
- `_lib/creative_director.py:407-418` — `_model_allowed()` returns `False` unless `caps["verified"]` is
  truthy. It also gates `CAMPAIGN_OS_IMAGE_MODEL_FORCE` (`:425-437`).
- `_lib/creative_director.py:59-83` — `_MODEL_CAPABILITIES`. **There is no `recraft/` entry at all.**
  The only mention of Recraft in the repo is a free-text `prompt()` example in
  `marketer-workspace.html:1112`.
- `_lib/creative_director.py:590-595` — `recommend_model()` subtracts `1.0` from any model without
  `verified: True`, with the reason string `"unverified — Krea upstream doesn't accept"`.

### 0.5 The negative prompt currently forbids the thing one-shot needs

- `_lib/creative_director.py:101-107` — `_TEXT_LOGO_NEGATIVES` = `no text in the image`, `no fake logos`,
  `no garbled text`, `no watermarks`, `no AI-hallucinated brand names`.
- `_lib/creative_director.py:366` — `build_negative_prompt()` appends it **unconditionally**.
- `_lib/creative_director.py:175-177` — `_OUTPUT_STYLE_DEFAULT = "photograph, no text, no logo, no watermark, no UI"`.
- `_lib/creative_director.py:163-174` — `_SECTION_ORDER` = JOB, BRAND, SUBJECT, REFERENCE, PRODUCT,
  COMPOSITION, LIGHTING, CAMERA, OUTPUT STYLE, NEGATIVE.
- `_lib/creative_director.py:889-900` — `_assemble_wire_prompt()` drops the NEGATIVE section from the
  provider-bound string and flattens the rest to prose in `_SECTION_ORDER`.

**Consequence:** a one-shot prompt cannot simply reuse the default negatives. It needs a text-literal
mode that drops the text negatives, keeps the logo negatives (the logo is composited, not generated),
and adds "no text other than the quoted line".

### 0.6 Instagram 4:5 is silently coerced to 1:1 today — measured

- `_lib/image_gen_router.py:154` — `_VALID_SIZES = {"1024x1024", "1024x1792", "1792x1024", "1536x1024", "1024x1536"}`.
- `_lib/image_gen_router.py:878` — `size = size if size in _VALID_SIZES else "1024x1024"`. No error, no warning.
- `marketer-workspace.html:1073` and `:1127` already POST `size: '1024x1280'` to `/api/image/generate`.
  **Those two call sites have been generating square images.**
- `_lib/llm_spend.py:24-29` — `MODELLED_IMAGE_USD` has no `1024x1280` key, so cost falls to
  `MODELLED_IMAGE_DEFAULT = 0.05`.
- `_lib/jobs/layer5/image_draft_context.py:12,526` — `VALID_ASPECTS` is the three-size set; an aspect
  outside it is replaced.
- `_lib/jobs/layer5/asset_qc.py:15,96` — `VALID_IMAGE_SIZES` is the same three; a 4:5 draft would fail QC.
- `_lib/jobs/layer5/draft_assets.py:37` — a third copy of the same frozenset, **currently unreferenced**.

**Consequence:** "Instagram 4:5 only" is five one-line edits, not an assumption. Without them the
one-shot lane would ship square images and nobody would see an error.

### 0.7 The `.meta.json` sidecar already carries prompt, model and cost

- `_lib/image_gen_router.py:1265-1292` — the persistence sidecar dict: `prompt`, `prompt_used`,
  `revised_prompt`, `negative_prompt`, `sections`, `model_routing`, `model`, `provider`,
  `cost_estimate_usd`, `cost_usd`, `source`, `usage`, `size`, `provider_job_id`, `saved_at`.
- `_lib/image_gen_router.py:727-766` — `_persist()` writes it to
  `<output_base>/<brand>/images/gen-<brand>-<ts>.png.meta.json`.
- `_lib/jobs/layer5/draft_assets.py:1282-1290` — the draft sidecar already copies `prompt_used`, `model`,
  `provider`, `cost_usd` and stores the router sidecar path as `router_sidecar_path`.

**Consequence:** nothing new needs computing for the review surface. The data is already on disk; it is
simply never projected into `meta` and never rendered.

### 0.8 The review projection is an explicit allowlist in two places

- `_lib/unified_inbox.py:665-700` — list path: `photo_candidates`, `qc`, `composed`, `archetype`,
  `brief`, `reference_used` are copied from the draft sidecar into `meta`.
- `_lib/unified_inbox.py:1786-1795` — single-item path: the same copies, minus `brief`.
- `web/src/components/ReviewDraftDetail.tsx` (481 lines) renders `meta`. Grepping it for
  `prompt|model|cost` returns only two caption lines (`:127-128`) — **no prompt, model or cost is
  displayed anywhere on the review surface today.**

### 0.9 The daily image cap

- `_lib/image_submit_quota.py` — `CAMPAIGN_OS_MAX_IMAGES_PER_DAY` (default `2`),
  `check_brand_image_submit()` / `record_brand_image_submit()`, per-brand counters in
  `$DATA_DIR/image-submit-count/<UTC day>.json`.
- `_lib/ops_layers.py:280-295` — `brand_images_today()` returns `{images_today, cap, at_cap}` for the UI.
- Gates today: `_lib/l5_create_enqueue.py:86-92` (enqueue), `_lib/jobs/layer5/draft_assets.py:1101-1106`
  (cook), `app.py:18582-18588` (`/api/ops/queue`), `_lib/draft_review_actions.py:358-366` (regenerate).

### 0.10 "Meme Lord flavour" is produced but never stored

- `app.py:20778-20806` — `/api/intel/meme_apply` returns `caption_options`:
  `[{"flavour": "sarcastic", ...}, {"flavour": "wholesome", ...}, {"flavour": "hard-truth", ...}]`.
- `_lib/marketing_calendar.py:69` / `_lib/campaigns.py:26` — `meme_lord` is a valid `origin` kind.
- `_lib/marketing_calendar.py:74` / `_lib/campaigns.py:32` — `humour` is a valid `process`.
- **No field anywhere persists a chosen flavour or its text onto a calendar record.** Grep for
  `flavour|sarcastic|wholesome|hard_truth` across `_lib/` returns nothing.

**This is the one gap in the ticket that needs a decision, not just code.** See §9.

---

## 1. The single most important thing in this plan

**The one-shot lane must be additive at every gate it touches, and the template lane must be
bit-identical after this change.**

Five of the files this touches are shared with the template lane: `creative_director.py`,
`image_gen_router.py`, `l5_create_enqueue.py`, `unified_inbox.py`, `llm_spend.py`. Every edit in them is
either a new keyword argument defaulting to the current behaviour, a new dict key, or a new enum member.
No existing default changes. Specifically:

- `typography` stays `False` at `draft_assets.py:1117` and `create_photo_compose.py:214`.
- `build_negative_prompt()` keeps emitting the text negatives unless the new flag is passed.
- `create_actions_for_moment()` returns exactly today's list when `render_mode` is `template`.
- `_model_allowed()` keeps refusing unverified models for automatic routing.

The acceptance criteria in §8 include a regression assertion for each of these.

---

## 2. Track A — the one-shot prompt (`_lib/creative_director.py`)

### 2.1 New section and new arguments

Add two sections to `_SECTION_ORDER` (`:163-174`), positioned so the assembled order is **scene, then
the literal line in quotes, then placement**:

```
JOB, BRAND, SUBJECT, REFERENCE, PRODUCT, COMPOSITION, LIGHTING, CAMERA,
LITERAL TEXT, TEXT PLACEMENT, OUTPUT STYLE, NEGATIVE
```

`compose_prompt()` (`:180-198`) gains three keyword arguments, all defaulting to the current behaviour:

| Argument | Type | Default | Meaning |
|---|---|---|---|
| `literal_text` | `str \| None` | `None` | The exact line the model must render, verbatim |
| `text_placement` | `str \| None` | `None` | Where it sits; falls back to a brand-safe default when `literal_text` is set |
| `render_text` | `bool` | `False` | Master switch: suppress text negatives, relax OUTPUT STYLE |

When `literal_text` is set and non-empty:

- `LITERAL TEXT` content is `Render this exact line, character for character: "<literal_text>"`.
  The quotes are part of the prompt. Nothing else goes in this section.
- `TEXT PLACEMENT` content is `text_placement` or the default
  `Upper third, generous overlay-safe margins, high contrast against the plate, single line unless it
  wraps naturally. Leave the bottom-right corner clear for a logo lockup.`
- `OUTPUT STYLE` must not contradict it: when `render_text` is true the default (`:175-177`) is replaced
  with `photograph with one rendered text line, no logo, no watermark, no UI`.

`_section_to_prose()` (`:876-886`) needs cases for both new keys. `LITERAL TEXT` must be passed through
**without** `.replace("\n", " ")` mangling the quoted string and without the `JOB` trailing-period rule.

### 2.2 The negative prompt

`build_negative_prompt()` (`:330-391`) gains `render_text: bool = False`. When true:

- **Drop:** `no text in the image`, `no garbled text` (from `_TEXT_LOGO_NEGATIVES`, `:101-107`).
- **Keep:** `no fake logos`, `no watermarks`, `no AI-hallucinated brand names` — the logo is composited
  from the asset file, so a generated logo is still a defect.
- **Add:** `no text other than the quoted line`, `no misspelled words`, `no duplicated text`,
  `no extra captions`, `no subtitle bars`.

When false, the function's output is byte-identical to today. Assert that in a test.

### 2.3 Length fitting

`_fit_master_prompt_length()` (`:935+`) trims sections to stay under `_PROMPT_MIN_CHARS` / the 1200-char
wire ceiling Phase 1 established. **`LITERAL TEXT` must be exempt from every trim path** —
`_trim_brand_composition_rules` and `_drop_subject_lines` already only touch BRAND and SUBJECT, but add
an explicit guard plus a test with a long literal line, because a truncated quoted string is a silently
wrong image.

### 2.4 Recraft, selectable and unverified

Add one entry to `_MODEL_CAPABILITIES` (`:59-83`):

```python
# Recraft v3 — listed for operator opt-in only. NOT live-verified on Krea.
# No capability scores: nobody has measured this model. Do not invent them.
# Kyle's live run fills these in and flips verified.
"recraft/recraft-v3": {"category": "image", "verified": False},
```

The omitted keys fall through to `recommend_model()`'s `0.5` defaults (`:552-559`), so the model scores
neutrally and then takes the existing `-1.0` unverified penalty (`:590-595`). **No fabricated numbers go
in this table.** The reason string for the penalty already reads correctly.

Selectability, without weakening automatic routing:

- `_model_allowed()` (`:407-418`) gains `allow_unverified: bool = False`. The `verified` check at `:418`
  becomes `return bool(caps.get("verified", False)) or allow_unverified`. Everything else in the function
  is unchanged, so `wired: False` and `edit_only` still hard-block.
- `pick_model()` (`:420-485`) gains `requested_model: str | None = None`. When supplied and
  `_model_allowed(requested_model, allow_unverified=True)` passes, return it immediately with
  `{"model", "provider", "reason", "unverified": True}` where `reason` is
  `"operator-selected model (unverified — no live run yet)"`. This branch sits **after** the
  `CAMPAIGN_OS_IMAGE_MODEL_FORCE` block and **before** `needs_reference`.
- Automatic routing is untouched: with no `requested_model`, `pick_model` cannot return Recraft, because
  it is not `ideogram-3`, not `_FLUX_ULTRA`, not `_GEMINI_FLASH_IMAGE`, and `_model_allowed` still fails
  for it at `:480`.

The `unverified: True` flag rides into the draft sidecar inside `model_routing["pick_model"]`
(`draft_assets.py:1177` sets `model_routing["pick_model"] = routing`) and is shown on the review surface
as an "unverified model" chip (§7).

### 2.5 Typography requirement — where `True` is passed

`typography: True` is passed in **exactly one new place**: the one-shot job's `pick_model` call (§3.4).
The two existing call sites keep `False`:

- `_lib/jobs/layer5/draft_assets.py:1117` — unchanged
- `_lib/jobs/layer5/create_photo_compose.py:214` — unchanged

---

## 3. Track B — the one-shot job (`_lib/jobs/layer5/draft_oneshot.py`, new)

A new leaf module alongside `draft_gen_slots.py` and `create_photo_compose.py`. It is the only thing in
the repo that passes `typography: True`.

### 3.1 Action name and registration

New action `draft_oneshot`, agent `cos-image`.

- `_lib/jobs/layer5/draft_assets.py:30` — add to `CREATE_ACTIONS`.
- `_lib/jobs/layer5/draft_assets.py:33` — `PROCESS_ACTIONS` picks it up transitively.
- It is **not** added to `_PHOTO_EQUIV` (`:35`). One-shot and template photo are different lanes; letting
  them dedupe against each other would let a template photo suppress a one-shot submit.
- `app.py:18569` — add `draft_oneshot` to `allowed_actions` on `/api/ops/queue`.
- Whatever dispatch table maps action → handler in the L5 runner gets the new entry (same shape as
  `draft_gen_slots`).

### 3.2 Literal copy resolution — the card is the source of truth

A pure function, unit-testable without any provider:

```python
def literal_line_for_card(brand_id: str, item_id: str, record: dict) -> tuple[str, str]:
    """Return (line, source). Raises OneshotCopyMissing when there is nothing to render."""
```

Resolution order:

1. **Humour cards** — `process == "humour"` or `origin == "meme_lord"`
   (`_lib/marketing_calendar.py:69,74`): use the **stored Meme Lord flavour** on the card. Source string
   `meme_lord:<flavour>`.
2. **Every other one-shot type:** the card `headline`, falling back to the card `title`
   (`record["title"]`, the field the day desk edits). Source `card:headline` / `card:title`.
   When the card also carries a CTA, it is appended as a second line and included in the quoted string.
3. **Nothing resolvable:** raise `OneshotCopyMissing`. The job returns an error for that row, writes no
   draft, **spends nothing**, and the moment stays visible on the day desk with the reason. A one-shot
   card with no copy is an operator problem, not something to paper over with a generated line.

**No LLM is called to invent the line.** The literal copy comes from the card, full stop.

### 3.3 4:5 only

Instagram 4:5 is `1024x1280`. §0.6 shows it is currently coerced to square. Five edits:

| File | Line | Change |
|---|---|---|
| `_lib/image_gen_router.py` | 154 | add `"1024x1280"` to `_VALID_SIZES` |
| `_lib/llm_spend.py` | 24-29 | add `"1024x1280": 0.05` to `MODELLED_IMAGE_USD` |
| `_lib/jobs/layer5/image_draft_context.py` | 12 | add `"1024x1280"` to `VALID_ASPECTS` |
| `_lib/jobs/layer5/asset_qc.py` | 15 | add `"1024x1280"` to `VALID_IMAGE_SIZES` |
| `_lib/jobs/layer5/draft_assets.py` | 37 | add `"1024x1280"` to `VALID_IMAGE_SIZES` (dead constant; keep the three copies consistent) |

> **Note for the implementer, and for Kyle:** these edits also fix
> `marketer-workspace.html:1073` and `:1127`, which have been asking for `1024x1280` and receiving
> `1024x1024`. That is a pre-existing bug, not a regression introduced here. The cost of a 4:5 image is
> set to `0.05` deliberately — it is the existing `MODELLED_IMAGE_DEFAULT`, so adding the key changes no
> number, it only makes the value explicit instead of a fallback. Kyle's live run replaces it with a
> measured figure.

The one-shot job hard-codes `size = "1024x1280"` and never reads `ctx.aspect`. There is no landscape or
square one-shot in this ticket. A test asserts the kwarg the mocked `generate_image` receives is exactly
`1024x1280`.

### 3.4 Generate

Sequence inside the job, per queue row:

1. Resolve `brand_id`, `item_id`, and the calendar `record`. Read `render_mode_for_record(record)`;
   if it is not `oneshot`, retire the row and return (defence in depth — a template card must never
   reach this job even if something enqueues it by mistake).
2. `literal_line_for_card(...)` → the line. On `OneshotCopyMissing`, error out before any spend.
3. Build the context with the existing `build_image_draft_context(brand_id, item_id)`
   (`image_draft_context.py`), then build the scene prompt. Scene comes from the card's post type and
   pillar, exactly as `background_plate_scene_prompt()` does (`image_draft_context.py:100-131`), but
   **without** its `_BACKGROUND_PLATE_SUFFIX` (`:94-98`) — that suffix says "no text, no letters, no
   logos, no typography", which is precisely wrong here.
4. `compose_prompt(brand_id=..., job=<scene>, literal_text=<line>, text_placement=<default or card>,
   render_text=True, format_aspect="4:5", ...)`. Send `wire_prompt` to the provider;
   keep `master_prompt`, `sections` and `negative_prompt` for the sidecar and the UI.
5. Spend and cap gates, in this order — the existing order in `draft_assets.py:1092-1109`:
   `llm_spend.modelled_image_cost("1024x1280")` → `llm_spend.check("image", est)` →
   `check_brand_image_submit(brand_id)` → the new one-shot sub-cap (§3.5) →
   `llm_spend.write_approval_receipt(...)` → `record_brand_image_submit(brand_id)` →
   `record_oneshot_submit(brand_id)`.
6. `pick_model({"needs_reference": False, "photoreal": False, "typography": True, "edit": False},
   requested_model=<card opt-in or None>)`. **This is the only `typography: True` in the repo.**
7. `generate_image_with_persistence(prompt=wire_prompt, size="1024x1280", negative_prompt=...,
   cost_action="draft_oneshot", ...)` — the router writes the `.meta.json` sidecar itself (§0.7).
8. Composite the logo (§3.6).
9. `_write_draft(...)` with `action="draft_oneshot"`, reusing the existing draft asset id for this
   moment when one exists (§6).

**`compose_post` is never enqueued for a one-shot card.** The model rendered the text; there is nothing
for the Pillow compose step to add but a second, conflicting headline.

### 3.5 One oneshot submit per brand per day, inside the global cap

The ticket is specific: **one** one-shot submit per brand per day, and that submit is also counted
against `CAMPAIGN_OS_MAX_IMAGES_PER_DAY`. Two counters, nested.

Extend `_lib/image_submit_quota.py` with a parallel pair that reuses the same day file and lock:

```python
ONESHOT_MAX_PER_DAY = 1

def check_brand_oneshot_submit(brand_id: str) -> tuple[bool, str]
def record_brand_oneshot_submit(brand_id: str) -> dict[str, int]
def oneshot_count_for_brand(brand_id: str, *, day: str | None = None) -> int
```

Storage: a sibling key in the same `$DATA_DIR/image-submit-count/<day>.json` document —
`{"schema": ..., "date": ..., "brands": {...}, "oneshot_brands": {...}}`. `_load()` (`:39-57`) gains a
`oneshot_brands` default exactly like the existing `brands` default, so an old day file loads clean.

Both gates must pass, and **both counters increment on a submit**:

- `check_brand_image_submit` → the global `CAMPAIGN_OS_MAX_IMAGES_PER_DAY` (default 2)
- `check_brand_oneshot_submit` → the one-shot sub-cap (1)

So with the default cap of 2, a brand can do one one-shot and one template image per day, or two template
images, but never two one-shots. If `CAMPAIGN_OS_MAX_IMAGES_PER_DAY=0` the global gate refuses first —
the sub-cap never gets to say yes. A test covers that ordering explicitly.

The enqueue side mirrors it: `_lib/l5_create_enqueue.py:86-92` already skips `draft_photo` at cap; add the
same guard for `draft_oneshot` using the one-shot checker, so the row is never queued when it cannot cook.

### 3.6 Logo — composited from the asset file by default

Default path, for every one-shot card:

- `_lib/brand_overlay.py:65-79` — `_find_logo(brand_id)` searches `logo.png`, `logo.svg`, `logo.jpg`,
  `assets/logo.png`, `brand-logo.png` across the `DATA_DIR` / `BUNDLED_DATA_DIR` / repo brand dirs
  (`:50-63`).
- `_lib/brand_overlay.py:226-261` — `overlay_logo_only(image_bytes, brand_id, position="bottom-right")`
  scales to 20% of width and pastes with alpha. Reuse it as-is.
- The prompt's `TEXT PLACEMENT` default already reserves the bottom-right corner (§2.1), and the negative
  keeps `no fake logos` (§2.2), so the generated plate should have an empty corner to paste into.
- When `_find_logo` returns `None`, `overlay_logo_only` returns the bytes unchanged — that is today's
  behaviour and it is acceptable. Record `logo_source: "missing"` in the sidecar so Review can say so.

Opt-in AI logo, with the warning:

- New card field `oneshot_ai_logo` (boolean), added to `_EDITABLE_MOMENT_FIELDS`
  (`marketing_calendar.py:660-671`) and coerced to a real bool in `set_fields` next to the `render_mode`
  validation (`:711-717`), plus `unified_inbox.py:2219`'s editable tuple.
- When true: skip the composite, drop `no fake logos` from the negatives, and extend `TEXT PLACEMENT`
  with the brand's logo lockup description.
- **The drift warning is mandatory and stored, not just rendered.** The sidecar gets
  `logo_source: "ai"` and `logo_drift_warning: "AI-rendered logo. The mark will drift from the brand
  asset — proportions, spacing and letterforms are not reproducible. Check it before approving."`
  Review shows it as a red chip on the draft (§7). The day desk shows it on the checkbox itself.

Sidecar keys: `logo_source` ∈ `{"asset", "ai", "missing"}`, and `logo_asset_path` when `asset`.

---

## 4. Track C — routing one-shot cards, and leaving template cards alone

`_lib/l5_create_enqueue.py:16-57`, `create_actions_for_moment()`:

```python
from _lib.marketing_calendar import render_mode_for_record
# ...
if phase in ("image", "all") and render_mode_for_record(record) == "oneshot":
    image_actions = ["draft_oneshot"]        # no gen_slots, no draft_photo, no compose_post
```

Rules this encodes:

- **One-shot cards** get `draft_oneshot` and nothing else in the image phase. The caption path
  (`draft_caption`, and `draft_gbp` when GBP is intended) is unchanged — the caption is the post body,
  independent of how the image is made.
- **Template cards on that day are not sent to one-shot.** `render_mode_for_record` returns `template`
  for absent, empty and unknown values (`marketing_calendar.py:58-61`), so the existing branch runs
  untouched. A test asserts a mixed day: two cards, one `oneshot`, one with no `render_mode` key at all,
  and the template card's action list is byte-identical to the pre-change list.
- The record lookup needs care: `create_actions_for_moment` currently takes only `brand_id` and `item_id`.
  Add an optional `record: dict | None = None` parameter and, when `None`, resolve it the way
  `unified_inbox._calendar_record_for_key()` does (`unified_inbox.py:1659-1667`). Callers that already
  hold the record pass it, avoiding a re-read.

`_lib/jobs/layer5/draft_assets.py:762-795` (`_maybe_enqueue_image_pipeline_after_caption`) checks for
pending image actions by name at `:780`. Add `draft_oneshot` to that tuple, or a one-shot card will get a
duplicate row on every L5 pass.

---

## 5. Track D — the operator action: generate a day

### 5.1 Endpoint

`POST /api/oneshot/day` in `app.py`, next to the other L5 enqueue routes.

```jsonc
// request
{ "brand_id": "stick", "date": "2026-10-02", "editor": "operator" }

// 200
{
  "ok": true, "brand_id": "stick", "date": "2026-10-02",
  "enqueued": [{"calendar_id": "cal-x", "item_id": "calendar_candidate:stick:cal-x", "row_id": "..."}],
  "skipped": [{"calendar_id": "cal-y", "reason": "render_mode is template"},
              {"calendar_id": "cal-z", "reason": "no literal copy on card"}],
  "cap": {"images_today": 1, "cap": 2, "at_cap": false, "oneshot_today": 1, "oneshot_cap": 1}
}
```

Behaviour:

1. Auth: session (`_is_authed`) — this is an operator action from the day desk, matching
   `/api/inbox/week` (`app.py:18747-18751`). Not the job bearer token.
2. Validate `brand_id` against `VALID_BRAND_IDS` and `date` as an ISO day, the way
   `inbox_week_board` does (`app.py:18757-18783`).
3. Load that one day's records for that brand. Partition on `render_mode_for_record`.
4. For each `oneshot` card, call `enqueue_create_actions(..., phase="image")` — **the existing Create
   path**, unchanged apart from Track C's branch. No bespoke enqueue code in the route.
5. Template cards go in `skipped` with `"render_mode is template"`. They are never enqueued by this route.
6. Cards whose copy cannot be resolved (§3.2) go in `skipped` before anything is queued, so the operator
   sees the whole picture in one response rather than finding failures in Review later.
7. The one-shot sub-cap means **at most one card per brand actually enqueues per day.** When more than one
   one-shot card sits on the day, the first enqueues and the rest land in `skipped` with
   `"oneshot cap reached for <brand> (1/1)"`. Return `200`, not `429` — a partial success is the normal
   case here, and the body says exactly what happened. Return `429` only when nothing could be enqueued
   because the brand was already at cap when the request arrived.

### 5.2 Day desk button

`web/src/pages/WeekBoard.tsx` — in day mode only (`isDayMode`, `:189`), beside the Today / Tomorrow /
date / Week controls (`:208-241`):

- **Generate one-shots** — disabled when the day has no `oneshot` card, or when
  `cap.at_cap` / the one-shot cap is spent. The disabled `title` says which.
- On success: show the per-card outcome (enqueued / skipped + reason) and call the existing `load()`
  (`onRefresh`) so the board reflects the new queue state.
- `web/src/lib/api.ts` gets the typed client call; `web/src/lib/postingWeek.ts` types gain the cap shape.
- Keep the copy plain and em-dash-free — `tests/test_v2026_08_07_nav_clarity.py:121-143` enforces the
  standing no-em-dash rule on published copy, and this is published copy.

---

## 6. Track E — regen replaces that card's draft

The ticket: *"Regen after an edit replaces that card's draft."* Not a second draft beside the first.

`_lib/draft_review_actions.py:343-410`, `regenerate_photo()`, currently enqueues
`(draft_gen_slots|draft_photo, compose_post)` (`:384-403`). Add a one-shot branch:

- Resolve the moment's `render_mode`. When `oneshot`, the action list is `["draft_oneshot"]` — no
  `compose_post`, for the reason in §3.4.
- Keep the existing note-required rule (`:347-349`), the cap check (`:358-366`), the
  `review_regenerate_note` sidecar stamp (`:369`), and the `composed` teardown (`:370-382`).
- The cap check must additionally consult `check_brand_oneshot_submit` for a one-shot card, so regen
  cannot sneak past the sub-cap that §3.5 enforces at submit time.

**Replacement, concretely.** `_write_draft` (`draft_assets.py:409-462`) writes
`campaigns[cid].assets[asset_id]` and `draft-assets/<asset_id>.json`, minting a fresh id when
`asset_id=None` (`:426`). The one-shot job must instead:

1. Look up the existing draft for this moment — `_sidecar_for_moment(item_id)`
   (`draft_assets.py:719-732`) already does exactly this lookup.
2. When one exists **and** its `action == "draft_oneshot"`, reuse its `asset_id`. `_write_draft` then
   overwrites the same asset row and the same `draft-assets/<id>.json` via `atomic_write` (`:461`), so
   the review item keeps its identity, its place in the queue, and its link from the calendar row.
3. The replaced sidecar carries `regen_count` (incremented), `replaced_at`, and the previous
   `router_sidecar_path` in `previous_router_sidecar_paths` so the old `.meta.json` and its cost line
   remain traceable. The old PNG is left on disk — it is cheap, and the cost ledger already references it.
4. When no one-shot draft exists yet, mint a new id as today.

A test asserts: generate, then regen, then exactly **one** draft asset exists for that moment, its
`asset_id` is unchanged, its `regen_count` is `1`, and its `prompt_used` is the new prompt.

---

## 7. Track F — Review shows prompt, model and cost

### 7.1 Server projection

`_lib/unified_inbox.py` — in **both** projection sites (`:665-700` list, `:1786-1795` single item), add
the same block:

```python
if sidecar.get("action") == "draft_oneshot":
    meta["oneshot"] = {
        "prompt_used": sidecar.get("prompt_used"),
        "master_prompt": sidecar.get("master_prompt"),
        "negative_prompt": sidecar.get("negative_prompt"),
        "literal_text": sidecar.get("literal_text"),
        "literal_text_source": sidecar.get("literal_text_source"),
        "model": sidecar.get("model"),
        "provider": sidecar.get("provider"),
        "unverified_model": bool((sidecar.get("model_routing") or {}).get("pick_model", {}).get("unverified")),
        "cost_usd": sidecar.get("cost_usd"),
        "cost_source": sidecar.get("source"),
        "image_size": sidecar.get("image_size"),
        "logo_source": sidecar.get("logo_source"),
        "logo_drift_warning": sidecar.get("logo_drift_warning"),
        "regen_count": sidecar.get("regen_count") or 0,
        "router_sidecar_path": sidecar.get("router_sidecar_path"),
    }
```

Every value already exists on disk (§0.7). `prompt_used`, `model`, `provider`, `cost_usd` and `source`
are written to the draft sidecar at `draft_assets.py:1282-1290` and to the router `.meta.json` at
`image_gen_router.py:1265-1292`.

**Read it from the `.meta.json` when the draft sidecar's copy is missing.** A `router_sidecar_path` that
exists on disk is the authority for `prompt_used`, `model`, `provider` and `cost_usd`; the draft sidecar
is the cache. A small helper reads and JSON-parses that file, returns `{}` on any `OSError` /
`JSONDecodeError`, and never raises into the projection. Doing it this way means a draft written by an
older code path still displays correctly.

Both projection sites must get the block, or the detail page and the list disagree — that is exactly how
`brief` ended up on only one of them today (`:692-699` has it, `:1786-1795` does not).

### 7.2 React

`web/src/lib/api.ts` — add the `oneshot` shape to `InboxItem['meta']`.

`web/src/lib/reviewDraftMeta.ts` — a `oneshotMetaFromInbox(item)` selector plus
`formatOneshotCost(usd)` (fixed 4 decimals, `—` when null), matching the file's existing selector style.

`web/src/components/ReviewDraftDetail.tsx` — a "One-shot" panel, shown only when `meta.oneshot` exists:

- A badge row: model, provider, size, cost. Cost shows `cost_source` so an estimate is not read as billed.
- A red **Unverified model** chip when `unverified_model` is true, reading
  `No live run yet — quality is unmeasured.`
- A red **AI logo** chip carrying `logo_drift_warning` verbatim when `logo_source === "ai"`; a muted
  **Logo missing** chip when `"missing"`.
- The literal line, quoted, with its source (`card:headline`, `meme_lord:sarcastic`, …) — so a reviewer
  can see at a glance whether the right copy was used.
- `prompt_used` in a `<details>`, collapsed, monospace, horizontally scrollable in its own container.
- `Regenerated N×` when `regen_count > 0`.

Tests go in the existing `web/src/components/ReviewDraftDetail.test.tsx`.

---

## 8. Tests — `generate_image` is mocked everywhere, no provider is ever called

### 8.1 The mocking contract

Every test that exercises the one-shot cook path patches
`_lib.image_gen_router.generate_image_with_persistence` with a `MagicMock`, following
`tests/jobs/test_image_spend_and_quota.py:52-67` exactly:

```python
mock_gen = MagicMock()
mock_gen.model = "ideogram/ideogram-3"
mock_gen.provider = "krea"
mock_gen.bytes = PNG_1x1
mock_gen.saved_path = str(png_path)
mock_gen.saved_sidecar_path = str(meta_path)   # a real file the test writes
mock_gen.prompt_used = "..."
mock_gen.provider_job_id = None
with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen):
    draft_oneshot.run()
```

Fixtures set `DATA_DIR` to `tmp_path`, `BUNDLED_DATA_DIR` to the repo `data/`, purge `sys.modules`
(`tests/jobs/test_layer5_create.py::_purge_modules`) because `marketing_calendar` and `intelligence`
capture `DATA_DIR` at import, and set `CAMPAIGN_OS_MAX_IMAGES_PER_DAY` explicitly.

**A hard guard, as its own test:** patch `requests.post` / `requests.request` at module scope to raise,
and assert the whole one-shot suite still passes. No test may reach a network stack. CI's existing
"tests must not write into tracked `data/`" gate (`.github/workflows/ci.yml:49-56`) covers the other half.

### 8.2 New test files

**`campaign-os/tests/test_creative_oneshot_prompt_sections.py`** — pure, no mocks needed:

| # | Assertion |
|---|---|
| A1 | With `literal_text`, `master_prompt` contains `LITERAL TEXT` then `TEXT PLACEMENT`, in that order, after the scene sections |
| A2 | The literal line appears inside double quotes, character for character, in both `master_prompt` and `wire_prompt` |
| A3 | `wire_prompt` order is scene prose → quoted line → placement (index assertions, not substring presence) |
| A4 | `render_text=True` → `negative_prompt` has no `no text in the image` and no `no garbled text`, but still has `no fake logos` and `no watermarks` |
| A5 | `render_text=True` adds `no text other than the quoted line` and `no misspelled words` |
| A6 | **Regression:** with no new arguments, `compose_prompt` and `build_negative_prompt` output is byte-identical to the pre-change baseline (frozen strings in the test) |
| A7 | A 400-char literal line survives `_fit_master_prompt_length` untruncated |
| A8 | `OUTPUT STYLE` under `render_text=True` does not contain `no text` |
| A9 | Phase 1 invariants hold: no `[` in `wire_prompt`, `NEGATIVE` absent from `wire_prompt` |

**`campaign-os/tests/test_creative_oneshot_model_select.py`**:

| # | Assertion |
|---|---|
| B1 | `recraft/recraft-v3` is in `_MODEL_CAPABILITIES` with `verified: False` and **no** `fidelity` / `photorealism` / `typography` / `composition` keys |
| B2 | `pick_model({"typography": True})` with no `requested_model` never returns a `recraft/` model — Krea connected and not |
| B3 | `pick_model(..., requested_model="recraft/recraft-v3")` returns it with `unverified: True` and a reason naming the operator selection |
| B4 | `pick_model(..., requested_model="bfl/flux-1-kontext-dev")` is refused — `edit_only` still blocks |
| B5 | `pick_model(..., requested_model="xai/grok-imagine-2")` is refused — `wired: False` still blocks |
| B6 | `recommend_model` still applies the `-1.0` unverified penalty to the Recraft entry |
| B7 | `_model_allowed("recraft/recraft-v3")` is `False`; with `allow_unverified=True` it is `True` |

**`campaign-os/tests/jobs/test_draft_oneshot.py`** — the cook path:

| # | Assertion |
|---|---|
| C1 | `generate_image_with_persistence` is called with `size="1024x1280"` — exactly, no coercion |
| C2 | It is called with the `wire_prompt`, and that prompt contains the quoted literal line |
| C3 | `pick_model` is called with `typography: True` (the only such call in the repo) |
| C4 | The written draft sidecar has `action="draft_oneshot"`, `prompt_used`, `model`, `provider`, `cost_usd`, `image_size="1024x1280"`, `literal_text`, `literal_text_source` |
| C5 | No `compose_post` row is enqueued for a one-shot moment |
| C6 | Humour card (`process="humour"`) → `literal_text_source` starts with `meme_lord:` and the line is the stored flavour text |
| C7 | Non-humour card → the line is the card headline (and title as fallback), `literal_text_source` is `card:headline` / `card:title` |
| C8 | A one-shot card with no resolvable copy: the row errors, **no draft is written, `llm_spend.today_spend()["calls"] == 0`, and both submit counters stay at 0** |
| C9 | `logo_source == "asset"` and `overlay_logo_only` was called when a brand logo file exists |
| C10 | `oneshot_ai_logo=True` → `logo_source == "ai"`, `logo_drift_warning` is non-empty, `overlay_logo_only` was **not** called, and `no fake logos` is absent from the negatives |
| C11 | No brand logo on disk → `logo_source == "missing"`, no crash, draft still written |
| C12 | `1024x1280` passes `asset_qc.VALID_IMAGE_SIZES` |

**`campaign-os/tests/jobs/test_oneshot_cap.py`**:

| # | Assertion |
|---|---|
| D1 | With `CAMPAIGN_OS_MAX_IMAGES_PER_DAY=2`: first one-shot submits; second one-shot for the same brand is refused with a cap reason |
| D2 | After a one-shot, a **template** `draft_photo` for the same brand still submits — the global cap has room |
| D3 | A one-shot submit increments **both** the global `brands` counter and the `oneshot_brands` counter |
| D4 | `CAMPAIGN_OS_MAX_IMAGES_PER_DAY=0` → the global gate refuses first; the sub-cap is never consulted and nothing is spent |
| D5 | Two different brands each get their own one-shot on the same day |
| D6 | An old-format day file with no `oneshot_brands` key loads without error and treats the count as 0 |
| D7 | `enqueue_create_actions` skips `draft_oneshot` when the one-shot cap is spent |

**`campaign-os/tests/jobs/test_oneshot_routing.py`**:

| # | Assertion |
|---|---|
| E1 | `render_mode="oneshot"` → `create_actions_for_moment(phase="image")` is exactly `["draft_oneshot"]` |
| E2 | `render_mode="template"` → the list is byte-identical to the pre-change baseline |
| E3 | **No `render_mode` key at all** → identical to E2. Template cards on a one-shot day are untouched |
| E4 | `render_mode="nonsense"` → treated as template (via `render_mode_for_record`) |
| E5 | Mixed day, two cards: only the one-shot card gets `draft_oneshot`; the template card's rows are unchanged |
| E6 | `phase="lodge"` is identical for both modes — the caption path does not fork |
| E7 | `draft_oneshot` is not in `_PHOTO_EQUIV`, so a template photo row cannot dedupe a one-shot row away |

**`campaign-os/tests/test_oneshot_day_route.py`** — Flask test client:

| # | Assertion |
|---|---|
| F1 | `POST /api/oneshot/day` with no session → `401` |
| F2 | Invalid `brand_id` → `400`; malformed `date` → `400` |
| F3 | A day with one one-shot and one template card → `enqueued` has the one-shot only; `skipped` names the template card with `render_mode is template` |
| F4 | Two one-shot cards on one day → one enqueued, one skipped with the cap reason, status `200` |
| F5 | Brand already at the one-shot cap when the request arrives → `429`, nothing enqueued |
| F6 | The response `cap` block carries `images_today`, `cap`, `at_cap`, `oneshot_today`, `oneshot_cap` |
| F7 | No provider call happens — this route only enqueues |

**`campaign-os/tests/jobs/test_oneshot_regen.py`**:

| # | Assertion |
|---|---|
| G1 | Generate, then regen → exactly one draft asset exists for the moment |
| G2 | The `asset_id` is unchanged across the regen |
| G3 | `regen_count == 1`, `replaced_at` is set, and `previous_router_sidecar_paths` has the first path |
| G4 | `prompt_used` on the replaced draft is the new prompt, not the old one |
| G5 | Editing the card title then regenerating puts the **new** title in `literal_text` |
| G6 | `regenerate_photo` on a one-shot moment enqueues `draft_oneshot` and **not** `compose_post` |
| G7 | Regen at the one-shot cap is refused with `at_cap` |

**`campaign-os/tests/test_oneshot_review_meta.py`**:

| # | Assertion |
|---|---|
| H1 | `meta["oneshot"]` is present on a `draft_oneshot` item in **both** the list and single-item projections, with identical content |
| H2 | It carries `prompt_used`, `model`, `provider`, `cost_usd`, `cost_source`, `image_size` |
| H3 | Values are read from the `.meta.json` at `router_sidecar_path` when the draft sidecar lacks them |
| H4 | A missing or corrupt `.meta.json` degrades to `None` values without raising |
| H5 | `logo_drift_warning` reaches `meta` when `logo_source == "ai"` |
| H6 | `unverified_model` is `True` when `model_routing.pick_model.unverified` is set |
| H7 | A **template** draft gets no `meta["oneshot"]` key |

### 8.3 Front-end tests

- `web/src/components/ReviewDraftDetail.test.tsx` — the panel renders model / provider / cost /
  size; the unverified chip; the AI-logo drift warning verbatim; the quoted literal line with its source;
  `prompt_used` collapsed in `<details>`; and **nothing at all** when `meta.oneshot` is absent.
- `web/src/lib/postingWeek.test.ts` — the existing 21 tests stay green; add the cap-shape type coverage.
- A new `web/src/pages/WeekBoard.oneshot.test.tsx` — the button is hidden in week mode, disabled with the
  right `title` at cap and when the day has no one-shot card, and calls `load()` on success.
- `npm run build` must pass.

### 8.4 Existing suites that must stay green

`tests/test_creative_oneshot_wire_prompt.py`, `tests/test_brand_visual_lint.py`,
`tests/test_image_pipeline_p2_provider.py`, `tests/jobs/test_image_spend_and_quota.py`,
`tests/jobs/test_layer5_create.py`, `tests/jobs/test_layer5_image_context.py`,
`tests/jobs/test_compose_gate_and_recipe.py`, `tests/jobs/test_gen_background_plate.py`,
`tests/test_render_mode_day_desk_20261002.py`, `tests/test_image_router_v2026_08_06.py`,
`tests/test_v2026_08_07_nav_clarity.py`, and `scripts/lint_brand_visual.py` for all three brands.

> **Known pre-existing failures, not caused by this work:** two tests in
> `tests/test_p0_brand_context.py` (Instagram / Facebook platform spec defaults) fail on the base. The
> Phase 1 handoff records the same two. Do not try to fix them in this ticket; do confirm the count is
> still two.

---

## 9. Acceptance criteria

1. A card with `render_mode="oneshot"` on a chosen day, after the operator action, produces exactly one
   draft in Review with a model-rendered text line.
2. The literal line in the image prompt is the card's own copy, quoted verbatim — the stored Meme Lord
   flavour for a humour card, the headline (or title) for every other one-shot type. Nothing is invented.
3. The prompt order is scene, then the quoted line, then placement — asserted by index, not by substring.
4. `typography` is `True` in exactly one `pick_model` call in the whole repo, and
   `grep -n 'typography' _lib/jobs/layer5/draft_assets.py _lib/jobs/layer5/create_photo_compose.py`
   still shows `False` on both.
5. `recraft/recraft-v3` is selectable by explicit operator choice only, is never returned by automatic
   routing, carries `verified: False`, and has no invented capability scores.
6. Every one-shot image is `1024x1280`. The size reaches the provider kwarg unchanged and passes QC.
7. The logo is composited from the brand asset file by default. `logo_source` records which path ran.
8. AI logo is opt-in per card and always carries the stored drift warning, visible in Review.
9. At most one one-shot submit per brand per UTC day, and that submit also counts against
   `CAMPAIGN_OS_MAX_IMAGES_PER_DAY`. Both counters increment.
10. Template cards on the same day are not sent to one-shot — not by the day action, not by
    `create_actions_for_moment`, not by `regenerate_photo`.
11. `compose_post` is never enqueued for a one-shot card.
12. Review shows `prompt_used`, `model` and `cost` sourced from the existing `.meta.json` sidecar, on both
    the list and detail projections.
13. Regen after an edit replaces that card's draft: same `asset_id`, `regen_count` incremented, new
    prompt, no second draft.
14. No test calls a live provider. The network guard test passes. Spend is zero on every refusal path.
15. `npm run build` passes and the day-desk vitest suites stay green.

---

## 10. Verify tier: **light**

**Recommendation: light**, with four named watch-items rather than a tier bump.

The work is additive at every shared gate (§1): new leaf module, new action name, new keyword arguments
with current-behaviour defaults, new dict keys, one new route, one new button. There is no migration, no
data rewrite, no key, no cron, no publish change, and — by construction — no live provider call. The new
code carries its own unit tests, CI already runs `check_lib_modules`, the allowlist suite, the
tracked-`data/` write gate and the allowlist ratchet.

**Four risks are worth stating so light verify is a decision, not an oversight.**

**Risk 1 — `_model_allowed()` is the global allow-list for image models
(`_lib/creative_director.py:407-418`), and `allow_unverified` punches a hole in it.** If the parameter
leaks into the `CAMPAIGN_OS_IMAGE_MODEL_FORCE` branch (`:425-437`) or into the automatic fallback at
`:480`, every unverified model in the table becomes reachable by env var or by default. **Light verify is
sufficient if and only if B2, B4 and B5 exist** — automatic routing never returns Recraft, and
`edit_only` / `wired: False` still hard-block under the new flag. A reviewer finding any of those missing
is grounds for reject on its own.

**Risk 2 — `build_negative_prompt()` is shared with the template lane
(`_lib/creative_director.py:330-391`).** If `render_text` ends up truthy by accident — a dict passed
where a bool was meant, a `.get()` on a missing key returning something truthy — template images lose
`no text in the image` and start hallucinating text that the Pillow overlay then draws over. A6's
byte-identity regression assertion is the control. It must be a frozen-string comparison, not a
"contains" check.

**Risk 3 — the two-counter cap (§3.5) is the only thing standing between a one-shot card and repeated
paid submits.** The ordering matters: global gate, then sub-cap, then receipt, then both increments. A
counter incremented before a refused gate leaks quota; a gate checked after the receipt leaks money.
D1–D4 pin the ordering, and C8 pins the zero-spend path. Note also that `image_submit_quota` keys on the
**UTC** day (`:20-21`) while the day desk works in SAST — a one-shot at 01:00 SAST counts against the
previous UTC day. That is pre-existing behaviour shared with the template lane; worth a line in the RFT
handoff so Kyle is not surprised, not worth changing here.

**Risk 4 — the `1024x1280` additions change behaviour for two call sites outside this ticket.**
`marketer-workspace.html:1073,1127` have been silently receiving `1024x1024`; after this change they
receive genuine 4:5. That is a fix, but it is a visible change on a surface this ticket does not own.
The RFT handoff must say so explicitly, and the verify step should confirm the Image Lab / marketer
workspace paths still render.

### What light tier explicitly does **not** cover

- Image quality. Whether `ideogram-3` or Recraft actually renders the line legibly is Kyle's live run,
  not a verify job. `verified: False` stays until that run.
- The real cost of a 4:5 generation. `0.05` is the existing default made explicit, not a measurement.
- Krea connectivity and the Recraft endpoint's existence. Neither is exercised by any test here.

---

## 11. Manual test plan — 12 steps

Local, job port **3750** (`runtime.ports.web`). From the worktree:

```bash
WT=/home/kyle/Work/worktrees/swing-shack-dashboard-main/plan/cos-oneshot-generate
export DATA_DIR=$(mktemp -d) BUNDLED_DATA_DIR="$WT/data" COS_JOB_TOKEN=dev-token PORT=3750
export CAMPAIGN_OS_MAX_IMAGES_PER_DAY=2
cd "$WT/campaign-os" && python3 app.py
```

| # | Step | Expected |
|---|---|---|
| 1 | `GET /api/health` | `200` |
| 2 | Open `/app/week`, click **Today** | Day desk for SAST today; `?tab=day&date=…` |
| 3 | Pick a day with two candidates. Edit one → **One-shot**; leave the other on Template | One-shot badge yellow on card A; card B unchanged |
| 4 | Confirm card A has a title/headline | Copy is present. An empty card is step 11 |
| 5 | Click **Generate one-shots** | Response names card A enqueued, card B skipped with `render_mode is template` |
| 6 | Run the L5 pass (or wait for the runner) | One draft appears in Review for card A. **None for card B** |
| 7 | Open that draft in Review | One-shot panel shows model, provider, **4:5 / 1024x1280**, cost + cost source, the quoted literal line and its source, `prompt_used` under a collapsed toggle |
| 8 | Check the image | The card's line is rendered in the image. The brand logo is in the bottom-right and matches the asset file, not an approximation |
| 9 | Click **Generate one-shots** again, same day | Refused — one-shot cap reached for that brand |
| 10 | Edit card A's title, then **Regenerate** on the draft with a note | The **same** draft updates. New line in the image. No second draft in Review. Panel shows `Regenerated 1×` |
| 11 | Set a card with no title/headline to One-shot, generate | Skipped with a no-copy reason. No draft, no spend — check `/api/ops/llm-spend` is unchanged |
| 12 | Tick **AI logo** on a card, generate | Review shows the red AI-logo chip with the drift warning. The logo in the image is model-rendered and visibly drifts from the asset |

Prod (after Kyle lands): the same paths on Railway `/app/week` and `/app/review`.

---

## 12. Sequencing for the implement job

Six commits, each independently green:

1. **Sizes** — the five `1024x1280` additions (§3.3) + `test_oneshot_sizes` coverage folded into
   `test_draft_oneshot.py::C1,C12`. Smallest, most cross-cutting; lands first and alone so a bisect
   lands on it cleanly.
2. **Prompt** — `creative_director.py` sections, arguments, negatives, length guard (§2.1-2.3) +
   `test_creative_oneshot_prompt_sections.py`.
3. **Model selection** — Recraft entry + `allow_unverified` / `requested_model` (§2.4) +
   `test_creative_oneshot_model_select.py`.
4. **Quota** — `image_submit_quota.py` one-shot sub-cap (§3.5) + `test_oneshot_cap.py`.
5. **The job + routing** — `draft_oneshot.py`, `create_actions_for_moment` branch, `regenerate_photo`
   branch, card fields (§3, §4, §6) + `test_draft_oneshot.py`, `test_oneshot_routing.py`,
   `test_oneshot_regen.py`.
6. **Surfaces** — `/api/oneshot/day`, the day-desk button, the review projection and panel (§5, §7) +
   `test_oneshot_day_route.py`, `test_oneshot_review_meta.py`, the React tests.

---

## 13. ⛔ One decision for Kyle — implement is blocked on this

**Where is the Meme Lord flavour stored on a humour card?**

The ticket says *"humour cards use the stored Meme Lord flavour"*. Measured today (§0.10): the three
flavours (`sarcastic`, `wholesome`, `hard-truth`) are **generated on demand** by
`/api/intel/meme_apply` (`app.py:20778-20806`) and returned to the caller. **Nothing persists a chosen
flavour, or its text, onto a calendar record.** `origin: "meme_lord"` and `process: "humour"` exist as
enum values (`marketing_calendar.py:69,74`) but carry no copy.

So `literal_line_for_card` has nothing to read for a humour card. Three ways out:

| Option | What it means | Cost |
|---|---|---|
| **A — add the field (recommended)** | New card fields `meme_flavour` (one of `sarcastic` / `wholesome` / `hard-truth`) and `meme_line` (the chosen text), added to `_EDITABLE_MOMENT_FIELDS` and the day-desk edit panel. The operator picks the flavour and the line when they set the card to one-shot. | One enum + one string field, one small UI control. Self-contained, and the stored line is auditable in Review |
| **B — wire Meme Lord to write the card** | `/api/intel/meme_apply` gains a "use this on card X" action that writes the flavour and line onto the calendar record | Touches an intel route this ticket does not own; larger blast radius |
| **C — treat humour like every other type** | Humour cards use `headline` / `title`, same as the rest; the flavour is dropped from scope | Contradicts the ticket wording |

**Recommendation: A.** It satisfies "the literal copy comes from the card" literally — the line is on the
card, visible on the day desk, editable before generate, and shown in Review with
`literal_text_source = "meme_lord:<flavour>"`. B can follow later as a convenience that fills the same
two fields.

Everything else in this plan is specified and unblocked. If A is approved, §3.2's resolution order and
the C6 test stand as written; only the field names move. The implement job can start on commits 1-4
(sizes, prompt, model selection, quota) before this is answered — none of them depend on it.

---

## Appendix — commands that produced every number above

```bash
WT=/home/kyle/Work/worktrees/swing-shack-dashboard-main/plan/cos-oneshot-generate
cd "$WT/campaign-os"

# §0.1
grep -n 'VALID_RENDER_MODES\|render_mode_for_record\|_EDITABLE_MOMENT_FIELDS' _lib/marketing_calendar.py
grep -rn 'render_mode' _lib/unified_inbox.py ../web/src/components/posting/PostCard.tsx

# §0.2
cat _lib/l5_create_enqueue.py
grep -rn 'enqueue_create_actions\|create_actions_for_moment' --include=*.py . | grep -v l5_create_enqueue

# §0.3
grep -n 'typography' _lib/jobs/layer5/draft_assets.py _lib/jobs/layer5/create_photo_compose.py

# §0.4
sed -n 55,100p _lib/creative_director.py            # _MODEL_CAPABILITIES — no recraft
sed -n 393,485p _lib/creative_director.py            # _model_allowed + pick_model
sed -n 580,592p _lib/creative_director.py            # unverified -1.0 penalty
grep -rni 'recraft' --include=*.py --include=*.html .

# §0.5
sed -n 101,115p _lib/creative_director.py            # _TEXT_LOGO_NEGATIVES
sed -n 163,178p _lib/creative_director.py            # _SECTION_ORDER + _OUTPUT_STYLE_DEFAULT
sed -n 360,372p _lib/creative_director.py            # unconditional extend
sed -n 876,900p _lib/creative_director.py            # prose + wire assembly

# §0.6
grep -n '_VALID_SIZES' _lib/image_gen_router.py; sed -n 876,880p _lib/image_gen_router.py
sed -n 24,30p _lib/llm_spend.py
grep -rn 'VALID_ASPECTS\|VALID_IMAGE_SIZES' --include=*.py .
grep -n '1024x1280' marketer-workspace.html

# §0.7
sed -n 727,766p _lib/image_gen_router.py            # _persist
sed -n 1265,1296p _lib/image_gen_router.py          # sidecar dict
sed -n 1275,1295p _lib/jobs/layer5/draft_assets.py  # draft sidecar copies

# §0.8
sed -n 660,700p _lib/unified_inbox.py
sed -n 1786,1796p _lib/unified_inbox.py
grep -n 'prompt\|model\|cost' ../web/src/components/ReviewDraftDetail.tsx

# §0.9
cat _lib/image_submit_quota.py
sed -n 280,296p _lib/ops_layers.py

# §0.10
sed -n 20778,20808p app.py
grep -rn 'flavour\|sarcastic\|wholesome\|hard_truth' --include=*.py _lib/

# §0.2 / §5.1 route shapes
sed -n 18550,18630p app.py                          # /api/ops/queue
sed -n 18746,18798p app.py                          # /api/inbox/week
sed -n 3687,3722p app.py                            # moment fields PATCH
sed -n 343,410p _lib/draft_review_actions.py        # regenerate_photo

# §8.1 mock pattern
sed -n 26,95p tests/jobs/test_image_spend_and_quota.py
```
