# Campaign OS Rebuild Roadmap (v2 — locked business/product-brand model)

> **North star:** Campaign OS behaves like a brand-aware Head of
> Marketing, not a box of disconnected generators.
>
> **Flow:** Today → Opportunity → Brief → Create → Review → Publish
> → Measure → Learn
>
> **Status:** P0 — bleeding stops now. P2/P3 forbidden until P0 is clean.
>
> **Sources:**
> - `heidi.txt` 2026-09-08 14:00 SAST (initial roadmap)
> - `heidi.txt` 2026-09-08 18:00 SAST (business/product-brand correction)
> - Live audit of code + data on 2026-09-08

---

## The locked model (lock this before Heidi touches migration)

```
BUSINESS     = Swing Shack  |  Stick Golf  |  The Bag Drop
PRODUCT BRAND = Takomo  |  L.A.B.  |  PB  |  Vice  |  Titleist  |  …
PRODUCT       = Takomo 101T  |  PB polo  |  Vice Pro Plus  |  …
CAMPAIGN      = "Takomo fitting campaign"  (owned by Stick Golf)
```

The hierarchy is unambiguous:

- A **business** is what Campaign OS manages. There are exactly **3**:
  `swing-shack`, `stick`, `bag-drop`. The brand switcher shows only
  these three.
- A **product brand** is a manufacturer. Takomo is a product brand,
  not a business. It lives **inside** Stick Golf's product catalogue,
  not as a separate workspace.
- A **product** is a specific stocked item (`Takomo 101T`,
  `PB Ashwood Polo`, `Vice Pro Plus`).
- A **campaign** belongs to one business. "Takomo fitting campaign"
  is a Stick Golf campaign that happens to feature Takomo products.

### The two-field rule (everywhere)

Every record carries **both** fields where relevant:

```json
{
  "brand_id": "stick",        // BUSINESS (which workspace owns it)
  "product_brand": "takomo",  // MANUFACTURER (only on product records)
  "product": "Takomo 101T Mallet Putter"
}
```

`brand_id` is **always one of**: `swing-shack` | `stick` | `bag-drop`.
Takomo is **never** a `brand_id`.

`product_brand` is the manufacturer and only appears on product
records, captions that mention a specific product, and visual
references that point at a manufacturer's product imagery.

---

## What changes vs v1 of this plan

| v1 (broken) | v2 (locked) |
|---|---|
| 4 operating brands (swing-shack, stick, takomo, bag-drop) | **3 operating brands only** — takomo is removed from the switcher |
| "Products missing 3 of 4 brands" | "Product catalogue structure is incomplete — Stick already has a product file with manufacturer sub-brands; Swing Shack and Bag Drop still need their service/product structures" |
| `brand_id = "takomo"` is allowed | `brand_id = "takomo"` is **forbidden** anywhere |
| Takomo has its own workspace, Meta connection, calendar, morning brief, campaign memory | **None of those exist for Takomo**. Takomo lives inside Stick's workspace |
| Takomo has its own Visual DNA brand universe | Takomo has **product-fidelity references only** — head shapes, finishes, logos, model markings — inside Stick's product library |
| "Connection Centre green for all 5 integrations" globally | Per **operating brand** + per **configured integration** for that brand |
| Master pass test goes Stick → Takomo → Bag Drop → Swing Shack | Stick Golf → Bag Drop → Swing Shack → Stick Golf (3 not 4) |

---

## The diagnosis (what the audit actually found on 2026-09-08)

### A — Brand/data isolation is broken

- `data/brands.json` currently lists **takomo** as an active
  operating brand (`active: true`, `order: 4`). This must be set
  to `active: false` and removed from the switcher.
- 405 records at `/data/*.json` (top-level) have **no `brand_id`
  field at all**: `NO_BRAND = 405 / 405`. Files affected:
  `captions.json` (20), `caption-variants.json` (20),
  `hook-bank.json`, `approval-queue.json` (88), `publish-queue.json`,
  `published-items.json` (57), `content-ideas.json` (15),
  `blog-drafts.json` (3), `image-prompts.json` (20),
  `visual-briefs.json` (20), `thumbnail-briefs.json` (20),
  `product-priority.json`, `agent-runs.json`, `state.json`.
- `get_brand_id()` exists but only **74 / 468** API routes use
  `<brand_id>` as a path parameter. The other **394** endpoints
  either ignore brand or filter in code (filter bugs → leaks).
- `data/brand-directory/` has **5 subdirs** including `takomo/`
  — but takomo must collapse into stick's product library.
- Swing Shack's brand record is fully populated (`tagline`,
  `audience`, `primary_color`, etc). Stick + Bag Drop records
  have **almost everything `None`**. Stick is the brand that
  does the heavy lifting and it's the most empty.
- `data/brand-guard-report.json` checks voice (text patterns)
  only — does **not** check data isolation.

### B — Product catalogue structure is incomplete

- `data/products/stick.json` exists with **14 items**. Every item
  already carries the right `product_brand` (takomo, lab-golf,
  psycho-bunny, vice, titleist). But no item carries `brand_id`
  (operating) — they only have `product_brand` (manufacturer).
- `data/products/swing-shack.json` and `data/products/bag-drop.json`
  do **not exist**. Swing Shack sells services (TrackMan sessions,
  fittings, coaching, memberships), not discrete stock items.
  Bag Drop sells bags + accessories.
- The catalogue model **already supports the right shape**:
  `product_brand` for manufacturer + `brand_id` for operating
  business. We just need to add `brand_id` to every item and
  build the two missing catalogues.

### C — Visual DNA / assets

| Brand | DNA records | Image files | Notes |
|---|---|---|---|
| swing-shack | 122 | 250 | Full Visual DNA. Only brand with working assets. |
| stick | 0 | 10 | 0 DNA records. 10 stock images. **Needs full Visual DNA build.** |
| takomo | 12 | 2 | Most records broken (image refs missing). **Migrates into stick as product-fidelity subset.** |
| bag-drop | 0 | 0 | **Needs full Visual DNA build from scratch.** |

### D — Meta integration is CRITICAL

```
Meta Ads:    token 649h old, CRITICAL, near expiry
Instagram:   token 388h old, CRITICAL, near expiry
GA4:         read_only, stable
Postiz:      connected, stable
GBP:         stale
```

No server-side OAuth refresh. Error messages shown to Christelle
leak `META_APP_ID + META_ACCESS_TOKEN` paths.

Connection Centre must be **per operating brand**: Swing Shack has
its own Meta connection (likely the live one). Stick may or may
not have one configured. Bag Drop may have a different state. The
dashboard must reflect each operating brand's actual configuration,
not a global "green" check.

### E — Routing + JS errors

- 43 nav items → 42 sections (seo-stack missing).
- **14 of 43** nav targets have no renderer (`landing`, `docs`,
  `abtests`, `ops`, `herman`, `buildpost`, `agency`, `fleet`,
  `products`, `integrations`, `tenants`, `metaoauth`,
  `onboarding`, `brand-settings` falls back to
  `brandSettingsSection`). Most of these silently fall back to
  `renderBrief()`.
- `buildCampaignFromIdea` referenced but **never defined**.
- `/sec-planning` was 404 until commit `62a77d4` — fixed but
  symptomatic.

---

# PHASE 1 — STOP THE BLEEDING (P0)

## 1.0 Lock the model (P0, do this FIRST)

Before any other migration work, lock the business/product-brand
distinction so every later fix builds on the right foundation.

### 1.0a — brands.json: takomo is no longer an operating brand

```diff
- takomo: { id: "takomo", active: true, order: 4, ... }
+ takomo: { id: "takomo", active: false, role: "product_brand", parent: "stick" }
```

### 1.0b — brand switcher shows only 3 businesses

Update `/api/brands` (the SPA's brand dropdown source) to filter
to `active: true` AND `role != "product_brand"`. SPA renders only
`swing-shack`, `stick`, `bag-drop`.

### 1.0c — `get_brand_id()` rejects takomo

```python
def get_brand_id():
    bid = request.headers.get('X-Brand') or request.args.get('brand_id') or request.args.get('brand')
    registry = load_brands_registry()
    if bid and bid not in registry['brands']:
        return registry.get('default_brand_id') or 'swing-shack'
    if bid:
        brand = registry['brands'][bid]
        if brand.get('role') == 'product_brand':
            # Takomo is not an operating brand — collapse to stick
            return brand.get('parent') or 'stick'
        return bid
    return registry.get('default_brand_id') or 'swing-shack'
```

### 1.0d — schema-level guard

Add `data/_system/brand-schema.json` that defines the canonical
brand_id enum:

```json
{
  "operating_brands": ["swing-shack", "stick", "bag-drop"],
  "product_brands": ["takomo", "lab-golf", "psycho-bunny", "vice",
                     "titleist", "puma", "footjoy", "mizuno",
                     "taylormade", "callaway", "ping", "titleist",
                     "bridgestone", "odyssey", "scotty-cameron",
                     "bettinardi", "vice", "srixon", " Cleveland"],
  "rule": "brand_id MUST be in operating_brands. product_brand
           MUST be in product_brands. A record with brand_id ==
           product_brand is invalid."
}
```

Every write/read path validates against this schema.

**PASS CONDITION (1.0):**
- `/api/brands` returns exactly 3 active brands.
- Brand switcher UI shows only 3 brands.
- `GET /api/products/takomo` returns 404 (takomo is not an
  operating brand).
- `GET /api/products/stick?product_brand=takomo` returns 2 items.
- Any record with `brand_id == "takomo"` is rejected on write
  with a 400 explaining the model.

---

## 1.1 Brand isolation (P0)

### 1.1a — every record gets `brand_id`

For each of the 15 top-level data files, add `brand_id` to every
record. Inference rules (per heidi #2 + the locked model):

| Vocabulary in record | brand_id |
|---|---|
| "swing", "Johannesburg", "Paarl", "TrackMan", "club-fitting", "Swing Shack" | `swing-shack` |
| "Stick", "Stick Golf", "fitting voucher", "Built At Stick", "Fit First", "Why It's Here" | `stick` |
| "Bag Drop", "bag drop", "drop-bag" | `bag-drop` |
| "Takomo", "L.A.B.", "PB", "Vice", "Titleist" (product brand mention) | `swing-shack` or `stick` based on surrounding context (default: `stick` if fitting context, `swing-shack` if TrackMan/coaching context) |
| No clear signal | `swing-shack` (default brand, largest dataset) + `brand_inferred: true` |

Takomo product records: `brand_id: "stick"` + `product_brand: "takomo"`.

### 1.1b — every read filters by `get_brand_id()`

```python
def load_records(path):
    """Load + filter a /data/ file by current operating brand."""
    bid = get_brand_id()
    d = json.loads(open(path).read())
    records = d if isinstance(d, list) else (d.get('items') or
                                              d.get('records') or [])
    return [r for r in records
            if r.get('brand_id') == bid
            and r.get('brand_id') in OPERATING_BRANDS]
```

Replace direct file reads for those 15 files with `load_records(path)`.

### 1.1c — product catalogue: add `brand_id` to every item

For `data/products/stick.json` (already exists): add
`brand_id: "stick"` to each of the 14 items. Keep `product_brand`
as-is (takomo, lab-golf, psycho-bunny, vice, titleist).

For `data/products/swing-shack.json` (new): services + apparel +
accessories. Each item gets:
- `brand_id: "swing-shack"`
- `product_brand` (the manufacturer if relevant, or `"swing-shack"` for Swing Shack own-label)

For `data/products/bag-drop.json` (new): bags + accessories + drop
items. Same pattern.

### 1.1d — visual DNA: 3 operating brands, takomo is a fidelity subset

- `data/brand-directory/swing-shack/` — already has 122 DNA
  records. Keep as-is.
- `data/brand-directory/stick/` — **needs full Visual DNA build**:
  - Stick Golf visual identity (palette, typography)
  - Stick photography rules
  - Stick layouts
  - Stick campaign aesthetics
  - **Takomo product-fidelity subset** — accurate head shapes,
    finishes, logos, model markings, shaft/club details, approved
    Takomo imagery, product-specific fidelity rules. This is a
    Stick library subset, not a separate workspace.
- `data/brand-directory/bag-drop/` — needs full Visual DNA build.
- `data/brand-directory/takomo/` — **delete**. Migrate Takomo
  product-fidelity references into Stick's library subset.

### 1.1e — connection per operating brand

- `data/integrations/<brand>/<integration>.json` — store
  connection health per brand.
- swing-shack: live Meta + Instagram + GBP + Shopify + Postiz.
- stick: whatever is configured (currently nothing — start with
  Meta + Postiz only when stick connects its own social account).
- bag-drop: whatever is configured.

The Connection Centre UI reads from `data/integrations/<brand>/`
and shows only the integrations that brand actually has. No fake
green checks for integrations a brand doesn't have.

**PASS CONDITION (1.1):**
```
test/brand-isolation.spec.ts:
  for each brand in [swing-shack, stick, bag-drop]:
    for each page in [/api/captions, /api/hooks,
                     /api/approval-queue, /api/publish-queue,
                     /api/published-items, /api/content-ideas,
                     /api/products, /api/visual-library/search]:
      response = GET(page, headers={X-Brand: brand})
      assert every record has brand_id == brand
      assert brand_id in [swing-shack, stick, bag-drop] (never takomo)
      assert response != response_for_other_brands (no overlap)
  PASS = 0 cross-brand leaks across 3 brands × 8 pages = 24 assertions.
```

---

## 1.2 Routing + JS errors (P0)

### 1.2a — nav targets

Same table as v1. Plus:

- `sec-buildpost` → KEEP + rename to `sec-create` (matches the
  "CREATE" bucket from Phase 2 nav).
- `sec-planning` → rename to `sec-calendar` (matches "Calendar"
  under CAMPAIGNS).

### 1.2b — every referenced function is defined

`tools/check-undefined.js` pre-commit hook. Fix
`buildCampaignFromIdea` (either define it or rename the caller).

### 1.2c — page transitions destroy previous state

Add the `window._secCleanups` pattern. Apply to every render
function that uses `setInterval`/`setTimeout`/listeners.

**PASS CONDITION (1.2):**
- 0 dead navs, 0 undefined function refs, 0 leaked timers.

---

## 1.3 Asset integrity (P0)

### 1.3a — 3 operating brands each have Visual DNA

- swing-shack: already done (122 records).
- stick: build Stick Visual DNA + Takomo product-fidelity subset
  (target: 20+ Visual DNA records + 10+ Takomo product-fidelity
  references).
- bag-drop: build from scratch (target: 12+ Visual DNA records).

### 1.3b — automated asset integrity check

`tools/check-assets.py` runs in CI on every deploy touching
`data/brand-directory/`. Checks:

- Every DNA record → file exists, file > 10 KB, mime matches.
- Every image file → referenced by ≥1 DNA record (no orphans).
- Every product record → has a thumbnail + original + DNA link.

### 1.3c — repair takomo directory

Migrate any useful Takomo product-fidelity references from
`data/brand-directory/takomo/` into Stick's product-fidelity
subset. Delete `data/brand-directory/takomo/` once migrated.

**PASS CONDITION (1.3):**
- 0 broken thumbnails in any operating-brand directory.
- 3 operating brands each have ≥ 12 DNA records.
- Takomo lives as a product-fidelity subset inside Stick, not
  as a top-level brand.

---

## 1.4 Meta + Connection Centre (P0)

### 1.4a — server-side OAuth refresh

`cron_jobs/refresh_meta_tokens.py` runs every 24h at 02:00 SAST:

1. Read Long-Lived User Access Token from
   `credentials/instagram-api-token.json`.
2. Refresh via `GET /oauth/access_token` with
   `grant_type=fb_exchange_token`.
3. Write new token back atomically.
4. Log result to `data/integrations/<brand>/meta.json`.
5. On failure: status `reconnect_required`, post Discord alert
   with one human message: "Instagram needs reconnecting. Click
   <oauth-init-url>." — not a stack trace.

### 1.4b — clean error messages

`friendly_error(integration, exc)` wrapper. Every integration
exception returns:

```json
{
  "ok": false,
  "integration": "instagram",
  "status": "reconnect_required",
  "message": "Instagram needs reconnecting.",
  "action": "click_reconnect_button",
  "reconnect_url": "/api/meta/oauth/start?brand=swing-shack"
}
```

### 1.4c — Connection Centre, per operating brand

`/api/integrations/<brand>/status` aggregates per-brand health:

```json
{
  "ok": true,
  "brand": "swing-shack",
  "integrations": {
    "meta": {"status": "connected", "token_age_hours": 12,
             "capabilities": ["insights", "publishing"]},
    "postiz": {"status": "connected"},
    "ga4": {"status": "connected"},
    "gbp": {"status": "stale", "last_sync_hours": 96},
    "shopify": {"not_configured": true}
  }
}
```

`not_configured` is honest. UI doesn't show a red "fail" — it
shows "Not configured for this brand".

**PASS CONDITION (1.4):**
- Cron refresh runs every 24h.
- `data/integrations/<brand>/meta.json` shows
  `status: "connected"`, `token_age_hours < 50`.
- Connection Centre UI shows health **per brand** + **per configured
  integration for that brand**. No fake green checks.
- 0 raw tracebacks in integration error responses.

---

# PHASE 2 — KILL THE DUPLICATES (P0)

## 2.1 New nav structure (8 buckets)

| Bucket | Sections inside |
|---|---|
| **TODAY** | Morning Brief, Review Queue, Publishing Issues, Performance Anomalies |
| **CREATE** | Build Post (campaigns), Hook Bank, Headlines, CTAs, Captions, Image Gen, Memes, Hashtags/SEO, FAQs |
| **LIBRARY** | All, Approved, Generated, Uploaded, Products, Campaign Assets, Visual DNA |
| **CAMPAIGNS** | Ideas, Briefs, Drafts, Active, Completed, Calendar (Strategic Calendar) |
| **PUBLISH** | Scheduled, Ready, Drafts, Failed, Published (per channel) |
| **INSIGHTS** | Overview, Social, Website, Campaigns, Content, SEO, Competitors, Opportunities, Learning |
| **BRAND** | Brand Bible, Voice, Messaging, Audience, Services, Products, Pricing, Offers, Visual DNA Rules, Banned Language, Product Fidelity |
| **SETTINGS** | Connected Accounts, Integrations, Users, API/Provider, System Health, Permissions |

## 2.2 — what gets deleted

Sections that exist now and have no nav after Phase 2.5:

- `sec-billboards` — collapse into Image Gen.
- `sec-landing` — DELETE (marketing pages live outside the app).
- `sec-docs` — DELETE (move docs to README files).
- `sec-ops` — DELETE (move to `/cockpit-operational`).
- `sec-onboarding` — DELETE (one-time).
- `sec-tenants` — DELETE (multi-tenant admin; not needed by Christelle).

Sections that consolidate:

- `sec-performance` + `sec-learning` + `sec-trends` + `sec-insights`
  → merge into `sec-insights` (tabs).
- `sec-captions` → tab inside Library.
- `sec-hashtagseo` + `sec-seo` + `sec-seo-audit` + `sec-seo-stack`
  → merge into `sec-seo` (tabs).
- `sec-postiz` → hide inside Publish (Postiz is infrastructure,
  not a user-facing tool).
- `sec-imagegen` + `sec-memes` → tabs in Create.
- `sec-hooks` + `sec-headlines` + `sec-ctas` → tabs in Create.
- `sec-faqs` → tab in Create.
- `sec-campaigns` + `sec-brief` + `sec-review` → all under
  CAMPAIGNS bucket.
- `sec-calendar` (legacy month grid) → secondary view under
  Strategic Calendar (already done in 3.18).

## 2.3 — renames

- `sec-planning` → `sec-calendar` (matches "Calendar" in CAMPAIGNS).
- `sec-buildpost` → `sec-create` (matches "Create" bucket).
- `sec-herman` → DELETE.
- `sec-metaoauth` → inside Settings → Connected Accounts.

## 2.4 — visual consistency

Audit every section's CSS classes. Force every section onto the
same token system. Build `tools/css-audit.py` to flag hardcoded
hex colors, hardcoded font sizes, hardcoded spacing.

**PASS CONDITION (Phase 2):**
- Nav shows 8 buckets. 0 dead navs.
- 43 sections → ~20 sections.
- 0 sections using hardcoded colors.

---

# PHASE 3 — FIX THE DATA FOUNDATION (P1)

## 3.1 Brand Knowledge Store (per operating brand)

For each of the 3 operating brands, build
`data/brand-directory/<brand>/brand-knowledge.json`:

```json
{
  "brand_id": "stick",
  "voice": {
    "tone": "direct, dry, SA-flavoured, no fluff",
    "do": ["golf-fluent", "ZAR pricing", "fitting-first", "SA idioms"],
    "do_not": ["motivational rubbish", "AI clichés", "American spelling",
                "dollar pricing", "claims not in stock list"],
    "banned_words": ["unleash", "elevate", "game-changer", "synergy",
                     "passionate", "world-class"]
  },
  "currency": "ZAR",
  "locale": "South Africa, Western Cape focus",
  "operating_business": "stick",
  "products": [
    {
      "id": "takomo-101t",
      "brand_id": "stick",
      "product_brand": "takomo",
      "name": "Takomo 101T Mallet Putter",
      "category": "putter",
      "price_zar": 7899,
      "stock_state": "live",
      "stock_qty": 6,
      "product_fidelity_refs": ["<dna_record_ids for takomo 101T>"]
    }
  ],
  "services": [...],
  "pricing": {
    "iron_fitting": "R1,200",
    "putter_fitting": "R900",
    "private_lesson": "R650/45min"
  },
  "approved_campaigns": [...],
  "approved_examples": [...],
  "banned_language": [...],
  "visual_rules": {
    "primary_colour": "#f0a030",
    "secondary_colour": "#004d5a",
    "do": ["real stock", "fitting context", "golf-fluent copy"],
    "do_not": ["stock photos", "American flags", "$ pricing"]
  },
  "product_fidelity_rules": {
    "for_product_brand: takomo": {
      "must_match": ["stock image", "actual colour", "actual price tier",
                      "head shape", "finish", "logo"],
      "never": ["wrong brand's putter", "wrong model number",
                "blade shape on L.A.B. (L.A.B. is mallet-only)",
                "fake specs"]
    },
    "for_product_brand: lab-golf": {...},
    ...
  },
  "channel_rules": {
    "instagram": {"voice": "casual-direct", "max_caption_chars": 2200,
                  "tag_count": "5-8"},
    "facebook": {"voice": "slightly warmer"},
    "linkedin": {"voice": "professional-direct"}
  }
}
```

Note the `operating_business` field — Campaign OS speaks Stick
throughout, even when marketing Takomo products.

## 3.2 Product catalogue completion

- `data/products/swing-shack.json` — services-focused:
  `trackman_session`, `iron_fitting`, `putter_fitting`,
  `wedge_fitting`, `private_lesson`, `playing_coach_session`,
  `membership_standard`, `membership_premium`. Each gets
  `brand_id: "swing-shack"`, `category: "service"`.
- `data/products/bag-drop.json` — bag-focused:
  `tour_bag`, `stand_bag`, `cart_bag`, `pencil_bag`, accessories.
  Each gets `brand_id: "bag-drop"`.
- `data/products/stick.json` — add `brand_id: "stick"` to all 14
  existing items. Keep `product_brand` as-is. Keep product-fidelity
  refs for Takomo items pointing at stick/visual-dna/.

## 3.3 Asset integrity completion

Already covered in Phase 1.3.

**PASS CONDITION (Phase 3):**
- 3 brands × full `brand-knowledge.json` populated.
- 3 brands × `products/<brand>.json` populated.
- 0 broken assets.
- Every Takomo product in stick's catalogue has product-fidelity
  references that resolve to real files.

---

# PHASE 4 — REBUILD THE AI BRAIN (P1)

## 4.1 Context assembler

`/api/context/<brand>/assemble?objective=...&funnel=...&offer=...&platform=...`

Returns:

```json
{
  "business_context": {
    "brand_id": "stick",
    "voice": {...},
    "banned_words": [...],
    "approved_examples": [...],
    "currency": "ZAR",
    "audience": "Western Cape golfers, 28-55, R150K+ HH income"
  },
  "product_context": {
    "products": [...],
    "product_brand": "takomo",   // when the campaign features Takomo
    "product_fidelity_refs": [...] // takomo visual dna subset
  },
  "campaign_context": {
    "business": "stick",
    "campaign_name": "Takomo fitting campaign",
    "objective": "drive fitting bookings",
    "funnel_stage": "consideration",
    "offer": "R1,200 iron fitting voucher",
    "platform": "instagram",
    "cta": "Book a fitting"
  },
  "performance_context": {
    "strongest_hooks_last_30d": [...],
    "weak_hooks_last_30d": [...],
    "fatigue_alerts": [...],
    "best_cta": "Book a fitting",
    "engagement_baseline": 0.045
  },
  "creative_context": {
    "visual_dna_recs": [
      {"file": "wedgecomp2.jpg", "why": "matches approved Stick coaching look"},
      {"file": "takomo-101t-1.jpg",
       "why": "Takomo product fidelity ref for the 101T head shape"}
    ],
    "approved_images": [...],
    "recent_assets": [...],
    "product_reference": "takomo-101t",
    "brand_colours": ["#f0a030", "#004d5a"],
    "photographic_rules": [...]
  }
}
```

**Key insight:** the assembler always operates at the **business**
level (`brand_id: "stick"`), not the product_brand level. When
the campaign is about Takomo, `product_context.product_brand` is
populated and `creative_context.visual_dna_recs` includes both
Stick's brand DNA AND Takomo's product-fidelity refs.

## 4.2 Hard gates

- ZAR-only pricing. If product has no ZAR price → "Available at
  [Stick/Swing Shack/Bag Drop]. Ask us for current pricing."
  (per heidi #1 verbatim).
- Banned words → regenerate.
- Cross-business content (caption mentions Takomo while
  `brand_id: "swing-shack"`) → reject. Per the locked model,
  Takomo is a product brand of Stick. A Swing Shack post cannot
  market Takomo products because Takomo is not in
  `swing-shack/products/`.
- Reference image SHA256 mismatch → block reference_verified but
  allow if reference_unavailable is honest about it.

**PASS CONDITION (Phase 4):**
- `/api/context/stick/assemble?product_brand=takomo` returns
  Stick's voice + Takomo's product-fidelity refs.
- `/api/context/swing-shack/assemble?product_brand=takomo` rejects
  (Takomo not in swing-shack catalogue).
- `/api/context/bag-drop/assemble?product_brand=takomo` rejects.
- 0 generations produced without going through the assembler.

---

# PHASE 5 — FIX CAPTION GENERATION (P1)

## 5.1 — 5 deliberate creative routes

Replace "give me 5 captions" with named routes: Contrarian, Pain
point, Humour, Proof/data, Story/curiosity. Each route has its own
prompt template, banned words, and rationale.

## 5.2 — similarity detection

```
sim_score = max(
  cosine_sim(new_caption, all_other_returned_captions),
  cosine_sim(new_caption, last_30_published[business]),
  cosine_sim(new_caption, recent_drafts[business])
)
if sim_score > 0.7: regenerate, drop route after 3 attempts
```

## 5.3 — "Why this works"

Every generated caption carries `why_this_works` explaining the
reasoning in 1-2 sentences, surfaced under each caption in the UI.

## 5.4 — private brand scoring

`brand_fit_score` is computed server-side before returning. Any
score < 70 → regenerate (max 3 attempts). Drop the route if still
below 70. UI shows `brand_fit: 94/100`.

**PASS CONDITION (Phase 5):**
- Generate 10 captions for any operating brand → all 5 routes
  represented.
- All 10 captions have non-empty `why_this_works`.
- For any 2 adjacent captions, `sim_score < 0.7`.
- All 10 captions have `brand_fit_score >= 70`.
- 0 banned words, 0 USD pricing, 0 Americanisms.

---

# PHASE 6 — REAL CREATIVE STUDIO (P1)

## 6.1 Image Studio

User journey:
1. What are you creating? (social post / story / paid ad / campaign visual / website hero / product shot)
2. Business (auto-selected)
3. Objective
4. Product (filtered by business — swing-shack can't pick Takomo)
5. Visual direction (Campaign OS recommends DNA refs — Stick's brand DNA + Takomo's product-fidelity subset when relevant)
6. Generate

Tools: Regenerate, Edit, Reframe, Remove object, Add product,
Change environment, Change crop, Resize, Add brand treatment,
Make another direction.

Generated assets return to Library with `source: ai_generated`,
`brand_id` (business), `product_brand` (if product featured),
`campaign_id`, `objective`, `visual_dna_refs`.

## 6.2 Video Studio

Same shape. Format → Business → Objective → Concept / Hook /
Shot list / Voiceover / On-screen text / CTA / Visual references
→ Generate OR Build production brief.

Provider abstraction layer so we're not married to one AI vendor.

**PASS CONDITION (Phase 6):**
- Image Studio generates an asset for any (business, objective,
  product) tuple.
- Generated asset lands in Library with `brand_id` (business) set.
- Video Studio produces a brief PDF or video for any (business,
  format, objective) tuple.
- 0 generated assets leaked between businesses.

---

# PHASE 7 — META CONNECTION CENTRE (P1, partially done in 1.4)

Already designed in Phase 1.4. Phase 7 polishes:

- Automatic health checks: token age, scope, page access, IG
  account access, publishing ability, insights ability, webhook
  status, last successful sync.
- One human-readable message per failure mode:
  - "Instagram needs reconnecting." (token expired)
  - "Facebook Page access revoked." (scope dropped)
  - "Webhook subscription stale." (event ingestion stopped)
- One-click reconnect from Connection Centre.

**PASS CONDITION (Phase 7):**
- `/sec-integrations` shows health per operating brand + per
  configured integration for that brand.
- Click Test Connection → ✓ for each capability.
- Click Reconnect → OAuth flow → token rotated → status green
  within 30s.

---

# PHASE 8 — CAMPAIGN MEMORY (P2)

When a campaign hits `status: completed`, write
`data/campaign-memory/<business>/<campaign_id>.json`:

```json
{
  "brand_id": "stick",
  "campaign_name": "Takomo fitting campaign",
  "products_featured": [{"product_brand": "takomo", "product_id": "takomo-101t"}],
  "what_worked": [...],
  "what_underperformed": [...],
  "strongest_hook": "...",
  "strongest_format": "...",
  "strongest_visual_pattern": "...",
  "best_audience": "...",
  "cta_performance": {...},
  "what_to_avoid_next_time": [...],
  "what_campaign_os_will_change": [...]
}
```

Next time a Stick campaign is built featuring Takomo, the
assembler pulls relevant learnings and surfaces them as
"based on what worked last time".

**PASS CONDITION (Phase 8):**
- After a campaign completes, `data/campaign-memory/<business>/`
  has a new file.
- The next Build Post for the same business surfaces
  "based on what worked: <campaign_id>" in the brief.

---

# PHASE 9 — OPPORTUNITY FINDER (P2)

`/api/opportunity-finder/<business>/biggest` returns:

```json
{
  "business": "stick",
  "biggest_opportunity": {
    "title": "Takomo putter fitting education",
    "signal": "Takomo putter saves outperforming iron content by 42% over 14 days, while fitting page traffic up 18%.",
    "recommendation": "Build a Takomo putter fitting education campaign.",
    "prepared": {
      "campaign_brief": "<id>",
      "hooks": ["<hook_id>", "<hook_id>", "<hook_id>"],
      "carousel_concept": "<id>",
      "reel_concept": "<id>",
      "caption": "<caption_id>",
      "cta": "<cta_id>"
    },
    "action": "BUILD_CAMPAIGN"
  }
}
```

The opportunity lives at the **business** level. "Takomo putter
fitting" is a Stick Golf opportunity that happens to feature
Takomo products.

**PASS CONDITION (Phase 9):**
- `/api/opportunity-finder/<business>/biggest` returns a structured
  opportunity for each operating brand, with ≥ 1 prepared asset.

---

# PHASE 10 — REBUILD HOME (P2)

Home answers 5 questions:
1. What should I do today?
2. What is working?
3. What isn't?
4. Where is the opportunity?
5. What has Campaign OS already prepared?

UI:

```
Good morning, Christelle.

Your biggest opportunity today is Takomo putter fitting education.

Stick Golf's Takomo content is gaining saves while lesson
engagement has softened.

I've prepared a 3-post Takomo fitting campaign and one Reel concept.

[Review campaign →]

Needs you            4 items
Publishing today     3
Worth knowing        2 insights
```

Note: the UI speaks **Stick Golf** throughout. "Takomo" only
appears as a product context within a Stick conversation.

**PASS CONDITION (Phase 10):**
- Home renders < 2s on production.
- All 5 questions answered.
- Action links work.

---

# PHASE 11 — DESIGN SYSTEM (P3)

Build `campaign-os/design-tokens.css`. Audit every section. Apply
the same component classes everywhere. `tools/css-audit.py` flags
hardcoded values.

**PASS CONDITION (Phase 11):**
- 0 hardcoded hex colors outside the token system.
- 0 hardcoded font sizes outside the token scale.

---

# PHASE 12 — QA GATE (P3)

Every release must pass:

- Brand QA — 0 cross-business leaks. `brand_id` always in
  {swing-shack, stick, bag-drop}. Takomo never appears as
  `brand_id`. CI runs Phase 1.1 tests.
- Routing QA — 0 dead navs, 0 undefined function refs.
- AI QA — 10 caption runs, all 5 routes, similarity < 0.7,
  brand_fit >= 70, 0 banned words.
- Asset QA — 0 broken thumbnails.
- Integration QA — Connection Centre green for each
  configured integration per business.
- UX QA — first-time user can complete "Create and schedule
  an Instagram campaign promoting fittings" with no developer
  help.

---

# Execution priority

Strict order. **No P1 starts before P0 passes. No P2 starts
before P1 passes.** No exceptions.

| Pri | Phase | Est. work |
|---|---|---|
| **P0** | 1.0 Lock the business/product-brand model | 0.5 day |
| **P0** | 1.1 Brand isolation | 2-3 days |
| **P0** | 1.2 Routing + JS errors | 1-2 days |
| **P0** | 1.3 Asset integrity | 2-3 days |
| **P0** | 1.4 Meta cron refresh + Connection Centre | 2-3 days |
| **P0** | 2 Nav consolidation | 3-4 days |
| P1 | 3.1 Brand Knowledge Store | 2 days |
| P1 | 3.2 Product catalogue completion | 1 day |
| P1 | 4 Context assembler | 3 days |
| P1 | 5 Caption intelligence | 4-5 days |
| P1 | 6 Creative Studio | 1-2 weeks |
| P1 | 7 Connection Centre polish | 2 days |
| P2 | 8 Campaign Memory | 3 days |
| P2 | 9 Opportunity Finder | 4 days |
| P2 | 10 Rebuild Home | 1 week |
| P3 | 11 Design system | 1 week |
| P3 | 12 QA gate | ongoing |

**Total P0:** 2.5-3 weeks.
**Total P1:** 4-5 weeks.
**Total P2:** 3 weeks.
**Total P3:** 2 weeks.

---

# MASTER PASS TEST (P0)

This replaces the v1 success criterion. Run after Phase 1.0
through 2.4 land.

```
1. Open /api/brands — confirm only 3 active businesses:
   swing-shack, stick, bag-drop.
   (Takomo is NOT in the switcher.)

2. Switch operating brand:
   Stick Golf → The Bag Drop → Swing Shack → Stick Golf

3. At every switch verify:
   - products / services
   - brand voice
   - Visual DNA
   - campaigns
   - drafts
   - approvals
   - analytics
   - social accounts
   - calendar

   are correctly isolated per operating brand.

4. While inside Stick Golf:
   - select Takomo as a PRODUCT BRAND
   - Takomo products appear in the catalogue
   - Stick Golf voice remains active (not Takomo voice)
   - Stick Golf Visual DNA remains active
   - Takomo product-fidelity references are added to creative
     context
   - NO Takomo Campaign OS workspace is created

5. Open Create.
   Generate:
   - a Stick Golf Takomo post
   - a Bag Drop post
   - a Swing Shack post

6. Confirm all three are unmistakably different in:
   - voice
   - CTA
   - visual treatment
   - product/service context
   - audience
   - campaign history

7. Zero cross-business leakage.
   (Takomo appears as product_brand only, never as brand_id.)

8. Zero JS errors.

9. Every visible nav destination loads.

10. Connection Centre shows health PER operating brand and
    PER configured integration for that brand. No fake green
    checks for integrations a brand doesn't have.

11. Home renders in under 2 seconds.
```

Until all 11 of those pass, P0 is not done. We keep going.

---

# What we are NOT doing

Per heidi.txt: "The product already has enough clubs in the bag.
Someone needs to stop adding wedges and fix the bloody swing."

- No new generators (Phase 5 rewrites caption, not adds another)
- No new AI toys
- No new sections (Phase 2 deletes, doesn't add)
- No P2/P3 work in the same sprint as P0 work

---

# Final north star reminder

```
BUSINESS     = Swing Shack  |  Stick Golf  |  The Bag Drop
PRODUCT BRAND = Takomo  |  L.A.B.  |  PB  |  Vice  |  Titleist  |  …
PRODUCT       = Takomo 101T  |  PB polo  |  Vice Pro Plus  |  …
CAMPAIGN      = "Takomo fitting campaign"  (owned by Stick Golf)

Campaign OS speaks Stick throughout.
```
