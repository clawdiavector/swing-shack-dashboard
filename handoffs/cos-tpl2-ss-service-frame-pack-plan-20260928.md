# SS `ss-service-frame` — legacy frame pack: plan (read-only)

**Date:** 2026-09-28
**Job:** `job-20260928-cos-tpl2-ss-service-frame-pack-plan` (Claude, plan tier, **read-only**)
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/plan/cos-tpl2-ss-service-frame-pack`
**Branch:** `plan/cos-tpl2-ss-service-frame-pack` @ `3590ff76` (= `integrate/campaign-os-brand-lanes-v1`)
**Ticket:** `cos-tpl2-ss-service-frame-pack`, seq 11, `handoffs/cos-templates-wave2-ticket-spec.yaml:170-179`
**Program:** `cos-templates-wave2-v1` (`context/campaign-os-templates-wave2-program.md`), item "Legacy packs (story-banner, ss-service-frame, venue-post, price-list) — **pack-only**"
**Skill:** `~/.agents/skills/campaign-os-template/SKILL.md` (not registered in this session's skill list — read directly from disk; same content)
**Downstream:** `feat/cos-tpl2-ss-service-frame-pack-template` and `review/cos-tpl2-ss-service-frame-pack-template` already exist as empty scaffold branches (byte-identical to base) — no prior implementation to reconcile.

**No code edits were made by this job.** `git status --porcelain` shows only the harness's own `.agent-job.json` / `.agent-job/` (untracked, not part of the repo).

---

## 0. Ticket fields

```yaml
slug: cos-tpl2-ss-service-frame-pack
seq: 11
title: "SS ss-service-frame — legacy SS frame template pack"
brand: swing-shack
archetype_id: ss-service-frame
pack_slug: service-frame
post_type_proposed: service_frame
refs: []
refs_note: "Peer stick-service-frame pack; measure SS frame refs if any in Content Bank"
depends_on: [cos-tpl2-ss-story-banner-pack]
```

`template_job.content_bank_refs` (`refs:`) is **empty** — the queue explicitly hands this to the
plan step to go find refs, if any exist, per `refs_note`. §1 is that search.

## 1. Content Bank search — one candidate found and measured

Searched both extracted copies of `~/Downloads/Content Bank-20260925T133008Z-1-001/Content
Bank/Swing Shack/{Services,Others,Products}` (56 files total). Only one filename plausibly reads
as a "frame" ref:

- `Swing Shack/Services/frame1.jpg` — 1081×1921 (`ig_story` block), md5 `719e7b36…`

Measured with the skill's tool:

```
$ python3 ~/.agents/skills/campaign-os-template/scripts/measure_refs.py frame1.jpg --json ...
frame1.jpg  1081x1921  accent #E95105  frame(inset,stroke) {left:(32,6) right:(26,6) top:(26,6) bottom:(26,6)}
  colour lines cap 73 pitch 302:
    y 780-876 (h 96)  x 94-660      "15% OFF"
    y 1082-1133 (h 51) x 123-737    "UNTIL END OF MAY"
  white text rows:
    y 901-1030 (h 129) x 216-1000   "ALL FITTINGS"
```

Visually: near-black vertical gradient field, thin (6px, ~26–32px inset) white frame border,
hand-set left-aligned hero block — orange "15% OFF" / white script "ALL FITTINGS" / green "UNTIL
END OF MAY" — no logo, no CTA, no disclaimer visible in this crop.

## 2. `frame1.jpg` is not new content — it's a draft/partial export of an already-packed creative

Three-way md5 check:

| File | md5 |
|---|---|
| `Content Bank/…/Services/frame1.jpg` | `719e7b36ab88c12f0452acdd8bc2f5c8` |
| `Content Bank/…/Services/fitting_discount_story.jpg` | `45efae8b4ddff3fa4026bd54ae1eeb47` |
| `data/brand-directory/swing-shack/templates/discount-code/references/ref-02.jpg` | `45efae8b4ddff3fa4026bd54ae1eeb47` |
| `data/brand-directory/swing-shack/templates/discount-code/references/ref-01.jpg` | `73db0c92622a41c2be73062aa3620c5f` = `Content Bank/…/Services/fitting_discount_post.jpg` |

`ref-02.jpg` in the **existing, already-shipped `ss-discount-code` pack** (`archetypes.json:1256`,
`description`: *"Measured from Content Bank fitting_discount_post/story… Near-black gradient,
white frame, centred logo, hand-set left hero lines (percent / subject / expiry), rule +
disclaimer, Inter upright CTA block."*) is byte-identical to `fitting_discount_story.jpg`.

`frame1.jpg` is a different byte file but the **same creative**: identical copy ("15% OFF ALL
FITTINGS UNTIL END OF MAY"), identical accent (`#E95105` = the SS palette's `ss_orange_hot`
token), identical frame inset/stroke geometry, identical hero-block position — just cropped
before the logo/rule/disclaimer/CTA-code block that appears lower in `fitting_discount_story.jpg`.
It reads as an earlier or partial export of the same source file, not a distinct design.

**Conclusion: there is no unclaimed Content Bank source for a distinct "SS service frame" visual
family.** The only candidate is already fully measured and packed under a different archetype
(`ss-discount-code`, `templates/discount-code/`).

## 3. The peer `stick-service-frame` pack is a different family — can't be ported 1:1

Read `data/brand-directory/stick/visual-spec/archetypes.json:216-341` and
`data/brand-directory/stick/templates/service-frame/{spec.json,template.md,references/ref-01.jpg}`.

`stick-service-frame`: solid horizontal navy gradient (`#073D55`→`#063443`), 3-line uppercase
headline top, **full-bleed teal CTA band** (two-line CTA, `FREE` emphasis), footer row = white
wordmark asset (left) + tagline lockup asset (right). `needs_photo: false`, no photo zone at all.
`template.md` "Don't": *"Drop in a photo (this archetype is `needs_photo: false`)."*

`ss-service-frame` today (`data/brand-directory/swing-shack/visual-spec/archetypes.json:136-203`)
is structurally different — it's a bare, never-measured stub:

```json
{
  "id": "ss-service-frame", "name": "Service frame", "canvas": "ig_post",
  "background": { "kind": "solid", "fill": "primary" },
  "zones": {
    "headline": { "rect": {"x0":0.1,"y0":0.2,"x1":0.9,"y1":0.35}, "font_role": "h1",
                  "max_lines": 2, "colour": "neutral_light" },
    "photo":    { "rect": {"x0":0,"y0":0.4,"x1":1,"y1":1}, "optional": true },
    "logo":     { "rect": {"x0":0.1,"y0":0.85,"x1":0.3,"y1":0.95} }
  }
}
```

No CTA-band zone, no footer/tagline zone, photo is *optional* rather than absent, no
`description`, no `template_pack`. `handoffs/…/campaign-os-template-taxonomy-review-20260927.md:35,42`
calls this out explicitly: *"archetypes exist (`ss-photo-post`, `ss-service-frame` **placeholder**,
`ss-story-banner`)"* / *"fitting/coaching pillars → **ss-service-frame** (placeholder)"*.

It **is** live-wired, though: `archetypes.json:2470-2484` selects it for
`pillar_in: [fitting, coaching, ss-fitting, ss-coaching]` with `has_product_item: false`, and
`campaign-os/tests/jobs/test_compose_template_wiring.py:28-31` asserts exactly that rule
(`test_explicit_template_id_on_enrich`'s neighbour — the fitting/coaching→ss-service-frame case
passes today).

No Content Bank asset in the stick pattern (solid field + CTA band + wordmark/tagline footer)
exists for Swing Shack either — the SS refs directories were fully enumerated in §1 and nothing
else matches that shape.

## 4. Recommended scope for the implement step

Given §2–3, there is no source art to measure a pixel-accurate pack from, and fabricating one
in the stick CTA-band shape would ship un-referenced, invented layout — against the skill's core
rule ("deterministic path... accuracy comes from **measuring the references**"). Recommend
packing the **already-wired stub geometry as-is** (generic, explicitly *not* reference-measured),
not porting stick's CTA-band shape:

- `data/brand-directory/swing-shack/templates/service-frame/`
  - `spec.json` — mirror the current archetype zones verbatim (§3 above) plus `measured_from: null`
    / a note field so it's not mistaken for a measured pack later.
  - `template.md` — intent: generic photo-optional service tile, fitting/coaching pillar,
    `has_product_item: false`. State plainly: *no dedicated Content Bank refs; do not confuse with
    peer `stick-service-frame`'s CTA-band family — same archetype name, different shape.*
  - `assets/logo-white.png` — reuse the existing SS mono-light logo asset already vendored in
    `templates/{did-you-know,discount-code,lesson-corner,sale-offer,service-promo}/assets/`.
  - `photos/` — optional; if Cursor wants a non-empty `photo` zone demo, the skill's fallback
    (`SKILL.md` §6) is to crop a text-free stand-in from an existing post (e.g. a clean background
    region of `ironfitting-100.jpg` or `coaching_post.jpg`) and ask Kyle for raw venue shots —
    do **not** invent new photography.
  - `references/` — leave empty or omit; there is nothing genuine to put here (§2). Note this
    explicitly in `template.md` rather than silently having an empty folder.
  - `golden/` — compare render(s) for `ig_post` (and `ig_story` if `canvas_overrides` are added)
    using a placeholder `caption_hook`, both with and without the optional photo, since
    `needs_photo: false` / photo `optional: true` is the one real behavioural fork this archetype has.
- Add the archetype's `template_pack: "templates/service-frame"` pointer once the pack exists.
- Update `handoffs/campaign-os-template-taxonomy-review-20260927.md` "Built:" line.
- Existing selection-wiring test (`test_compose_template_wiring.py`) already covers the rule and
  needs no change unless the archetype's `zones`/`applies_to` shape changes.

## 5. Flag for Kyle — decision needed before the human gate

No dedicated "SS service frame" reference art exists in the Content Bank. The only candidate
(`frame1.jpg`) is a partial/duplicate export of the creative already fully measured and shipped
under `ss-discount-code`. Before Cursor implements, Kyle should pick one:

1. **Accept a generic, non-measured pack** for `ss-service-frame` as scoped in §4 (fastest,
   matches "pack-only" ticket scope, keeps the existing selection rule working).
2. **Supply new source art** if the intent was actually the stick CTA-band family (solid field +
   teal-equivalent CTA band + footer wordmark/tagline) — nothing in Content Bank matches that
   shape for Swing Shack today.
3. **Retire the placeholder** — since the taxonomy doc already flags `ss-service-frame` as a
   placeholder and its only real-world source asset turns out to belong to `ss-discount-code`,
   consider repointing the `fitting`/`coaching` + no-product-item selection rule at an
   already-packed archetype (e.g. `ss-discount-code` or `ss-service-promo`) instead of packing
   the stub at all.

This plan does not choose between them — §4 describes the implement path for option 1, the
lowest-risk default that keeps the dependent ticket chain (`cos-tpl2-stick-venue-post-pack`,
`cos-tpl2-ss-price-list-pack`, …) unblocked, but the compare-sheet human gate is exactly where
Kyle should weigh in on 1 vs. 2 vs. 3.

## Appendix — commands run

```bash
grep -rl "ss-service-frame" --include='*.json' --include='*.ts' --include='*.tsx' --include='*.md' .
grep -n -A 30 "ss-service-frame-pack" agent-control/handoffs/cos-templates-wave2-ticket-spec.yaml
find "$CB/Swing Shack" -maxdepth 2 -type f | sort         # 56 files, one "frame1.jpg"
python3 ~/.agents/skills/campaign-os-template/scripts/measure_refs.py frame1.jpg --json ...
md5sum frame1.jpg fitting_discount_story.jpg templates/discount-code/references/ref-0{1,2}.jpg
grep -n "ss-service-frame" data/brand-directory/swing-shack/visual-spec/archetypes.json
grep -n "stick-service-frame" -A 5 data/brand-directory/stick/visual-spec/archetypes.json
grep -rl "ss-service-frame" --include='*.py' .
git branch -a | grep -iE "story-banner|service-frame|frame-pack"
git diff integrate/campaign-os-brand-lanes-v1...feat/cos-tpl2-ss-service-frame-pack-template --stat
git status --porcelain
```
