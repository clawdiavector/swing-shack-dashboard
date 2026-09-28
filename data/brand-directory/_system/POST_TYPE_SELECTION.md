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
| `story_banner` | `ss-story-banner` | `story-banner` | `cos-tpl2-ss-story-banner-pack` | wave2 pack revives; pin recommended |

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

## 5.4 Wave 2 — archetype ↔ `post_type` map

Wave2 template program (`cos-tpl2-*`). **Doc-only ticket** — archetype JSON and compare sheets land on sibling feat branches. Merge **`cos-tpl2-p0-cap`** before stacking multiple **new id** branches: integrate had SS **11** + Stick **10** ids against schema cap **12**; P0 raises the cap to **24** (`feat/cos-tpl2-p0-cap-template`).

**Kyle decision (documented here):** manifest token **`social_lab`** vs implement synonyms **`contest`**, **`giveaway`**, **`challenge`**. Primary tag **`social_lab`**; all four belong in `post_type_in` for `ss-social-lab`.

**Event family:** Ryder Cup and other one-offs stay taxonomy exceptions; wave2 still ships `ss-event-poster` + `post_type` **`event_poster`** (and alias **`event`**) for tagged event rows — do not auto-select from pillar alone.

**Service frame disambiguation:** wave1 promo frame uses **`service_promo`** → `ss-service-frame`. Optional explicit legacy tag **`service_frame`** → `ss-service-frame` only if Kyle wants it separate from `service_promo` (see optional rule below).

### 5.4.1 Swing Shack (wave2)

| Archetype id | `post_type` (primary) | `post_type_in` / synonyms | Pack slug | Plan id | New id? |
|---|---|---|---|---|---|
| `ss-ladies-clinic` | `clinic_invite` | `clinic_invite` | `ladies-clinic` | `cos-tpl2-ss-ladies-clinic` | **yes** |
| `ss-price-list` | `price_list` | `price_list`, `package_list`, `rate_card` *(integrate)* | `price-list` | `cos-tpl2-ss-price-list-pack` | no (pack QA) |
| `ss-event-poster` | `event_poster` | `event_poster`, `event` | `event-poster` | `cos-tpl2-ss-ryder-cup` | **yes** |
| `ss-service-frame` | `service_frame` *(doc alias)* | use **`service_promo`** for promo frame (wave1); `service_frame` = optional explicit tag | `service-frame` | `cos-tpl2-ss-service-frame-pack` | no (pack) |
| `ss-social-lab` | `social_lab` | **`social_lab`**, **`contest`**, **`giveaway`**, **`challenge`** | `social-lab` | `cos-tpl2-ss-social-lab` | **yes** |
| `ss-story-banner` | `story_banner` | `story_banner` *(pin recommended — weak auto use)* | `story-banner` | `cos-tpl2-ss-story-banner-pack` | no |
| `ss-zen-venue-promo` | `venue_promo` | `venue_promo` | `zen-venue-promo` | `cos-tpl2-ss-zen-stage` | **yes** |

**New SS archetype ids in wave2:** 4 (`ss-ladies-clinic`, `ss-event-poster`, `ss-social-lab`, `ss-zen-venue-promo`).

### 5.4.2 Stick (wave2)

| Archetype id | `post_type` (primary) | Rule / synonyms | Pack slug | Plan id | New id? |
|---|---|---|---|---|---|
| `stick-service-end` | `service_end` | existing | `service-end` | `cos-tpl2-stick-end-v2` | no (v2/goldens) |
| `stick-service-frame` | `service_frame` | pillar rule today; optional explicit `service_frame` | `service-frame` | `cos-tpl2-stick-frame-story-goldens` | no (story goldens) |
| `stick-service-start` | `service_start` | existing | `service-start` | `cos-tpl2-stick-start-variants` | no (variants) |
| `stick-venue-post` | `venue_post` | **`subject: "venue"`** *(live)* + **`venue_post`** synonym (wave2 doc) | `venue-post` | `cos-tpl2-stick-venue-post-pack` | no (pack) |
| `stick-hiring` | `hiring` | `hiring` | `hiring` | `cos-tpl2-stick-hiring` | **yes** |
| `stick-open-sign` | `open_sign` | `open_sign` | `open-sign` | `cos-tpl2-stick-open-sign` | **yes** |
| `stick-shop-corner` | `shop_corner` | `shop_corner` | `shop-corner` | `cos-tpl2-stick-shop-corner` | **yes** |

**New Stick archetype ids in wave2:** 3 (`stick-hiring`, `stick-open-sign`, `stick-shop-corner`).

### 5.4.3 Wave 2 `post_type_in` rules (append at bottom of `selection.rules`)

Append **after** existing pillar / product / venue rules (§5.3 — last match wins).

**Swing Shack:**

```json
{"when": {"post_type_in": ["clinic_invite"]}, "use": "ss-ladies-clinic"}
{"when": {"post_type_in": ["event_poster", "event"]}, "use": "ss-event-poster"}
{"when": {"post_type_in": ["social_lab", "contest", "giveaway", "challenge"]}, "use": "ss-social-lab"}
{"when": {"post_type_in": ["venue_promo"]}, "use": "ss-zen-venue-promo"}
{"when": {"post_type_in": ["story_banner"]}, "use": "ss-story-banner"}
```

Optional explicit legacy frame tag (only if Kyle wants disambiguation from `service_promo`):

```json
{"when": {"post_type_in": ["service_frame"]}, "use": "ss-service-frame"}
```

**Stick** — keep existing `subject: "venue"` → `stick-venue-post`; add:

```json
{"when": {"post_type_in": ["hiring"]}, "use": "stick-hiring"}
{"when": {"post_type_in": ["open_sign"]}, "use": "stick-open-sign"}
{"when": {"post_type_in": ["shop_corner"]}, "use": "stick-shop-corner"}
{"when": {"post_type_in": ["venue_post"]}, "use": "stick-venue-post"}
```

Individual wave2 feat branches may be **ahead of integrate** on ids and rules; this section is the program map once merged.

---

## 6. Lodge flow — example calendar envelope (wave2)

**Engine:** `select_archetype()` in `campaign-os/_lib/archetypes.py` — pinned `template_id` / `archetype_id` wins, then **last matching** `selection.rules` entry, else `selection.default`. After inbox **lodge** (`POST …/inbox/…/approve` with `mode: "lodge"`), L5 `compose_post` reads the same calendar row via `_moment_context`.

**§3.2 caveat (still true):** upsert-only `post_type` backfill is a **noop** until Phase B. Tag at **create** (Flow A below), then lodge.

### 6.1 Field names (create → lodge → compose)

| Field | Role in lodge flow |
|---|---|
| `date` / `event_date` | Go-live date on the moment (required for lodge — `no_date` blocks lodge in inbox UI) |
| `brand_id` | Operating brand (`swing-shack`, `stick`, …) |
| `type` | Record type (`moment` for compose posts) |
| `title` | Human title; becomes `lodged_title` on sandbox rows after lodge |
| `post_type` | Primary wave2 tag (Flow A — must be on revision 1) |
| `archetype_id` / `template_id` | Optional pin; always wins over rules when id exists |
| `archetype_pack` | Pack slug from §5.4 tables (authoring / QA reference — not a selection key today) |
| `pillars` | Pillar ids (plural list on create; pillar rules still Phase B §3.1) |
| `channels` / `primary_channel` | Intended surfaces; lodge may default `primary_channel` |
| `week_theme` | Optional campaign-week label when the row sits in a themed week |
| `lanes` | Optional brand-lane ids when routing content in a multi-lane week |
| `item_type` | Inbox envelope: `calendar_candidate` (item id `calendar_candidate:<brand>:<calendar_id>`) |

Always include normal moment fields (`channels`, `verification_status` when sourced externally, etc.) — same as wave1 examples in §7.

### 6.2 Worked example — ladies clinic invite (create, then lodge)

**Step 1 — create candidate** (local dev: `$HOST` = job port, e.g. `http://127.0.0.1:3019`; set `DATA_DIR` + session or bearer as usual):

```bash
curl -sS -X POST "$HOST/api/calendar/candidates" \
  -H 'Content-Type: application/json' \
  -d '{
  "brand_id": "swing-shack",
  "type": "moment",
  "title": "Ladies clinic — March intake",
  "date": "2026-03-15",
  "post_type": "clinic_invite",
  "pillars": ["coaching"],
  "channels": ["instagram"],
  "week_theme": "coaching_march",
  "lanes": ["coaching"],
  "archetype_id": "",
  "archetype_pack": "ladies-clinic",
  "template_id": ""
}'
```

Expected selection once `ss-ladies-clinic` and §5.4.3 rules exist: **`ss-ladies-clinic`** via `post_type_in: ["clinic_invite"]` (or pin `template_id` / `archetype_id`: `"ss-ladies-clinic"`).

**Step 2 — lodge** from inbox (`mode: "lodge"`) enqueues draft + compose jobs; compose uses `post_type`, pin, and product/pillar/subject fields from the persisted row — not upsert-only tagging.

**Other wave2 seed shapes** (copy-paste — not committed to git `data/`):

| Archetype | `post_type` at create | Optional pin |
|---|---|---|
| `ss-event-poster` | `"event_poster"` | pin |
| `ss-social-lab` | `"social_lab"` or `"contest"` | pin |
| `ss-zen-venue-promo` | `"venue_promo"` | pin |
| `ss-story-banner` | `"story_banner"` | pin (recommended) |
| `ss-price-list` | `"price_list"` | pin |
| `stick-hiring` | `"hiring"` | pin |
| `stick-open-sign` | `"open_sign"` | pin |
| `stick-shop-corner` | `"shop_corner"` | pin |
| `stick-venue-post` | `"venue_post"` or `"subject": "venue"` | pin |

---

## 7. Example calendar fields per archetype

Records live at `$DATA_DIR/intelligence/marketing-calendar/<brand>.jsonl` (runtime volume, not git). `post_type` and `template_id` persist on create/upsert paths that write the full record; there is no separate enum in schema.

### Per-archetype minimum field set

| Archetype | Minimum fields on the record | Also honoured |
|---|---|---|
| `ss-did-you-know` | `post_type`: `"tip"` \| `"did_you_know"` \| `"myth"` | `template_id` pin (if id exists) |
| `ss-service-frame` | After Phase B §3.1: `pillars: ["fitting"]` or `["coaching"]`, no products. Today: singular `pillar_id` / `pillar` only (not what `add_candidate` writes) | `template_id` pin |
| `ss-photo-post` | *(none — brand default)* | — |
| `ss-story-banner` | `post_type: "story_banner"` *(wave2 rule)* | `template_id` pin (recommended) |
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
| `ss-ladies-clinic` | `post_type: "clinic_invite"` | `template_id` pin |
| `ss-event-poster` | `post_type: "event_poster"` or `"event"` | `template_id` pin |
| `ss-social-lab` | `post_type: "social_lab"` \| `"contest"` \| `"giveaway"` \| `"challenge"` | `template_id` pin |
| `ss-zen-venue-promo` | `post_type: "venue_promo"` | `template_id` pin |
| `ss-price-list` | `post_type: "price_list"` | `template_id` pin |
| `stick-hiring` | `post_type: "hiring"` | `template_id` pin |
| `stick-open-sign` | `post_type: "open_sign"` | `template_id` pin |
| `stick-shop-corner` | `post_type: "shop_corner"` | `template_id` pin |
| `stick-venue-post` | `post_type: "venue_post"` or `subject: "venue"` | `template_id` pin |

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
