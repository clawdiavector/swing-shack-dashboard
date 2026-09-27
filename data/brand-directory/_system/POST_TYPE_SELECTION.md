# Calendar `post_type` and archetype selection

Authoritative selection tables and tagging notes for Swing Shack and Stick compose templates.
Engine behaviour is documented in plan handoff `cos-tpl-post-type-doc-plan-20260927` (read-only plan tier).

---

## Open issues

Corrections to older context docs (measured at integrate base `681c453e`):

1. **Archetype cap is 8**, not 4. Raised in commit `e59e56ac` (`archetype_schema_data.json` → `properties.archetypes.maxItems: 8`). Four archetypes per brand is current usage, not the ceiling.
2. **`ss-service-promo` is a proposed rename of `ss-service-frame`**, not a separate archetype id. The live SS service template id is **`ss-service-frame`**. The roadmap row `service_promo` → `ss-service-promo` should be read as naming drift until Kyle decides §4(1) in the plan.
3. **Pillar rules do not fire on real calendar records today.** Records carry plural `pillars` (list); `select_archetype` reads singular `pillar_id` / `pillar` only. Effect: SS and Stick pillar `pillar_in` rules miss; candidates fall through to `selection.default` (`ss-photo-post`, `stick-photo-band-post`). Phase B fix queued (needs Kyle approval — changes live Stick selection).

---

## 5.1 Swing Shack — `post_type` selection table

| `post_type` | Archetype | Pack slug | Ticket | Status |
|---|---|---|---|---|
| `service_promo` | `ss-service-frame` *(proposed id rename: `ss-service-promo` — see Open issues)* | `service-promo` | `cos-tpl-ss-promo-fitting` | not built (pack); frame **live** as `ss-service-frame` |
| `tip`, `did_you_know`, `myth` | `ss-did-you-know` | `did-you-know` | — (shipped) | **live on integrate** |
| `price_package` | `ss-price-package` | `price-package` | `cos-tpl-ss-price-package` | not built |
| `sale_offer` | `ss-sale-offer` | `sale-offer` | `cos-tpl-ss-sale-offer` | not built |
| `discount_code` | `ss-discount-code` | `discount-code` | `cos-tpl-ss-discount` | not built |
| `lesson` | `ss-lesson-corner` | `lesson-corner` | `cos-tpl-ss-lessons` | not built |
| `fitting_headline` | `ss-fitting-headline` | `fitting-headline` | `cos-tpl-ss-fitting-headline` | not built |
| *(default)* | `ss-photo-post` | — | — | live |
| *(pillar `fitting` / `coaching`)* | `ss-service-frame` | — | — | live, **unreachable** until plural `pillars` fix (Phase B §3.1) |
| *(unused)* | `ss-story-banner` | — | — | retire candidate; no selection rule |

---

## 5.2 Stick — `post_type` selection table

| `post_type` | Archetype | Pack slug | Ticket | Status |
|---|---|---|---|---|
| `service_start` | `stick-service-start` | `service-start` | `cos-tpl-stick-start` | not built |
| `service_end` | `stick-service-end` | `service-end` | `cos-tpl-stick-end` | not built |
| `service_square` | `stick-service-square` | `service-square` | `cos-tpl-stick-square` | not built |
| `brand_statement` | `stick-brand-statement` | `brand-statement` | `cos-tpl-stick-statement` | not built |
| `location` | `stick-location-drive` | `location-drive` | `cos-tpl-stick-locations` | not built — refs unpicked, `Stick/Other/` |
| `staff_profile` | `stick-coach-profile` | `coach-profile` | `cos-tpl-stick-coach-profile` | not built — refs unpicked, `Stick/Other/` |
| *(default)* | `stick-photo-band-post` | — | — | live |
| *(pillar `service` / `assessment` / `fitting` / `coaching`)* | `stick-service-frame` | — | — | live, **unreachable** until plural `pillars` fix (Phase B §3.1) |
| *(`has_product_item: true`)* | `stick-product-post` | — | — | live, works |
| *(`subject == "venue"`)* | `stick-venue-post` | — | — | live, case-sensitive (Phase B §3.4) |

All 13 proposed `post_type` values are distinct and brand-disjoint.

---

## 5.3 Rule ordering (`selection.rules`)

In `select_archetype()`, **every matching rule is evaluated; the last match wins** (no `break`). Appending a broad rule after a specific one silently overrides the specific choice.

Recommended order (specificity increases downward; new `post_type_in` rules belong at the **bottom**):

1. `has_product_item: true` → `<brand>-product-post` (Stick only; keep first)
2. `pillar_in: [...]` → `<brand>-service-frame` (broad; keep near top)
3. `subject: "venue"` → `stick-venue-post` (Stick only)
4. …N. `post_type_in: [<one value>]` → one archetype per rule (mutually exclusive values; order within this block is free)

**Operational rule:** explicit `post_type` rules MUST be appended **after** pillar and product rules so a tagged record beats pillar inference.

Both brands' `visual-spec/archetypes.json` files carry a greppable top-level `_selection_rules_note` as a reminder.

---

## 7. Example calendar fields per archetype

Records live at `$DATA_DIR/intelligence/marketing-calendar/<brand>.jsonl` (runtime volume, not git). `post_type` and `template_id` persist on create/upsert paths that write the full record; there is no separate enum in schema.

### Per-archetype minimum field set

| Archetype | Minimum fields on the record | Also honoured |
|---|---|---|
| `ss-did-you-know` | `post_type`: `"tip"` \| `"did_you_know"` \| `"myth"` | `template_id` pin (if id exists) |
| `ss-service-frame` | After Phase B §3.1: `pillars: ["fitting"]` or `["coaching"]`, no products. Today: singular `pillar_id` / `pillar` only (not what `add_candidate` writes) | `template_id` pin |
| `ss-photo-post` | *(none — brand default)* | — |
| `ss-story-banner` | *(none — not selected by rules)* | manual pin only |
| `ss-price-package` | `post_type: "price_package"` | `template_id` pin |
| `ss-sale-offer` | `post_type: "sale_offer"` | `template_id` pin |
| `ss-discount-code` | `post_type: "discount_code"` | `template_id` pin |
| `ss-lesson-corner` | `post_type: "lesson"` | `template_id` pin |
| `ss-fitting-headline` | `post_type: "fitting_headline"` | `template_id` pin |
| *(future `service_promo` row)* | `post_type: "service_promo"` → intended `ss-service-frame` after rename decision | `template_id` pin |
| `stick-product-post` | `products: [...]` or `product_ids: [...]` non-empty | — |
| `stick-service-frame` | After Phase B §3.1: matching `pillars` list, no products. Today: singular `pillar_id` / `pillar` | `template_id` pin |
| `stick-venue-post` | `subject: "venue"` — **lowercase** | — |
| `stick-photo-band-post` | *(none — brand default)* | — |
| `stick-service-start` | `post_type: "service_start"` | `template_id` pin |
| `stick-service-end` | `post_type: "service_end"` | `template_id` pin |
| `stick-service-square` | `post_type: "service_square"` | `template_id` pin |
| `stick-brand-statement` | `post_type: "brand_statement"` | `template_id` pin |
| `stick-location-drive` | `post_type: "location"` | `template_id` pin |
| `stick-coach-profile` | `post_type: "staff_profile"` | `template_id` pin |

A pinned `template_id` (or `archetype_id` alias on the record) always wins over rules — **only if the id exists**; unknown pins fall through silently today (Phase B §3.3).

### §3.2 caveat — backfill via upsert does not work today

`post_type` and `template_id` are **not** in `MATERIAL_FIELDS`. Tagging an **existing** record with **only** `post_type` via `POST /api/calendar/v2/upsert` returns HTTP 200 `{"ok": true, "action": "noop"}` and **persists nothing**.

- **Flow A (create)** — works: include `post_type` on `POST /api/calendar/candidates`.
- **Flow B (upsert-only tag)** — blocked until Phase B §3.2.
- **Flow C (recompose pin)** — works for a single draft override; does not write the calendar row.

---

## How to tag a candidate

### Flow A — tag at create (works today)

```bash
curl -X POST "$HOST/api/calendar/candidates" -H 'Content-Type: application/json' -d '{
  "brand_id":  "swing-shack",
  "type":      "moment",
  "title":     "Iron fitting — accuracy",
  "pillars":   ["fitting"],
  "post_type": "fitting_headline"
}'
```

`post_type` lands on revision 1. Selection resolves to the matching archetype once that id and its `post_type_in` rule exist (last-match-wins ordering applies).

### Flow B — tag an existing record (blocked — §3.2)

Do **not** rely on upsert with only `post_type` until Phase B lands. Bundling `post_type` with a material-field change works but mislabels revision history; prefer waiting for `POST /api/calendar/v2/tag` (planned).

### Flow C — pin one draft, bypassing rules (works today)

```bash
curl -X POST "$HOST/api/drafts/<draft_id>/recompose" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $JOB_TOKEN" \
  -d '{"archetype_id": "ss-did-you-know"}'
```

Uses **`archetype_id`**, not `template_id`. Requires job auth. Unknown ids hard-fail on recompose. Does not sync the calendar row — draft-only override.

---

## Resolution order (summary)

1. Pinned `template_id` / `archetype_id` on the calendar record (if id exists in `archetypes[]`).
2. Last matching entry in `selection.rules`.
3. `selection.default`.

See `campaign-os/_lib/archetypes.py` (`select_archetype`, `_rule_matches`) for implementation.
