# COS templates — Phase A doc implement

**Date:** 2026-09-27  
**Job:** `job-20260927-cos-tpl-post-type-doc-implement`  
**Run:** `20260927T214909-implement-da6874`  
**Branch:** `feat/post-type-doc-template`  
**Base:** `integrate/campaign-os-brand-lanes-v1` @ `681c453e`  
**Plan:** `plan/post-type-doc/handoffs/cos-tpl-post-type-doc-plan-20260927.md`

## Scope delivered (Phase A only)

| Deliverable | Path |
|---|---|
| Selection + tagging doc | `data/brand-directory/_system/POST_TYPE_SELECTION.md` |
| Rule-order marker (Swing Shack) | `data/brand-directory/swing-shack/visual-spec/archetypes.json` → `_selection_rules_note` |
| Rule-order marker (Stick) | `data/brand-directory/stick/visual-spec/archetypes.json` → `_selection_rules_note` |
| Skill runtime wiring fix (out of repo) | `~/.agents/skills/campaign-os-template/SKILL.md` § Runtime wiring |

**Phase B is OUT OF SCOPE for this ticket.** Engine fixes for §3.1 (plural `pillars`), §3.2 (persist `post_type` on upsert / tag API), §3.3 (unknown pin), §3.4 (`subject` case), and §4 cap raise depend on **two Kyle decisions** (§4(1) `ss-service-promo` rename vs new id; §3.1 Stick pillar selection behaviour change). Do not land Phase B from this branch.

## Per-archetype minimum calendar field set (both brands)

Copied from plan §7; includes live ids in `archetypes.json` plus program rows not yet built.

### Swing Shack

| Archetype | Minimum fields on the record | Also honoured |
|---|---|---|
| `ss-photo-post` | *(none — brand default)* | — |
| `ss-service-frame` | After Phase B §3.1: `pillars: ["fitting"]` or `["coaching"]`, no products. Today: singular `pillar_id` / `pillar` only | `template_id` pin |
| `ss-story-banner` | *(none — not selected by rules)* | manual pin only |
| `ss-did-you-know` | `post_type`: `"tip"` \| `"did_you_know"` \| `"myth"` | `template_id` pin |
| `ss-price-package` | `post_type: "price_package"` | `template_id` pin |
| `ss-sale-offer` | `post_type: "sale_offer"` | `template_id` pin |
| `ss-discount-code` | `post_type: "discount_code"` | `template_id` pin |
| `ss-lesson-corner` | `post_type: "lesson"` | `template_id` pin |
| `ss-fitting-headline` | `post_type: "fitting_headline"` | `template_id` pin |
| *(program `service_promo` row)* | `post_type: "service_promo"` → live id **`ss-service-frame`** until rename decided | `template_id` pin |

### Stick

| Archetype | Minimum fields on the record | Also honoured |
|---|---|---|
| `stick-photo-band-post` | *(none — brand default)* | — |
| `stick-product-post` | `products: [...]` or `product_ids: [...]` non-empty | — |
| `stick-service-frame` | After Phase B §3.1: matching `pillars`, no products. Today: singular `pillar_id` / `pillar` | `template_id` pin |
| `stick-venue-post` | `subject: "venue"` — **lowercase** | — |
| `stick-service-start` | `post_type: "service_start"` | `template_id` pin |
| `stick-service-end` | `post_type: "service_end"` | `template_id` pin |
| `stick-service-square` | `post_type: "service_square"` | `template_id` pin |
| `stick-brand-statement` | `post_type: "brand_statement"` | `template_id` pin |
| `stick-location-drive` | `post_type: "location"` | `template_id` pin |
| `stick-coach-profile` | `post_type: "staff_profile"` | `template_id` pin |

Pinned `template_id` wins over rules when the id exists (unknown pin: silent fall-through today).

## Verify (Phase A)

```bash
grep -n last-match-wins data/brand-directory/*/visual-spec/archetypes.json
test -f data/brand-directory/_system/POST_TYPE_SELECTION.md
git diff --name-only 681c453e..HEAD
```

Expected diff paths only: `POST_TYPE_SELECTION.md`, both `archetypes.json`, this handoff.

## Not done (explicit)

- No Python, tests, schema cap, packs, or compare sheets.
- `context/campaign-os-content-bank-services-templates.md` not updated (ticket pointed at `_system/POST_TYPE_SELECTION.md` instead).
