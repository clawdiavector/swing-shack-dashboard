# Campaign Mothership V2 — Schema & Migration Spec

**Status:** DRAFT — awaiting Christelle approval
**Date:** 2026-06-02
**Author:** Clawdia
**Commit:** pending — to be committed before migration

---

## What Is Changing

**Current model:**
```
campaign-data.json
└── campaign (single object — TrackMan Intelligence)
└── assets (flat dict, all assets together)
```

**New model:**
```
campaign-data.json
└── portfolioMetadata (name, description, lastUpdated)
└── campaigns (dict of campaign containers)
    └── [campaignId]
        ├── identity (name, goal, owner, status, platforms, healthScore)
        ├── visualDirection (palette, mood, imageReferences)
        ├── assets (dict of assets specific to this campaign)
```

---

## 1. New Campaign Data Model

### Root Level

```json
{
  "portfolioMetadata": {
    "name": "Swing Shack Campaign Portfolio",
    "description": "All active and planned marketing campaigns",
    "owner": "christelle",
    "lastUpdated": "2026-06-02T00:00:00Z",
    "version": 2
  },
  "activeCampaignId": "trackman-intelligence",
  "campaigns": {
    "[campaignId]": {
      "identity": {
        "campaignId": "string",
        "name": "string",
        "shortName": "string (e.g. 'Takomo 101T')",
        "goal": "string",
        "status": "active | paused | completed | planned",
        "owner": "string (agent handle)",
        "platforms": ["instagram", "tiktok", "gmb"],
        "createdAt": "ISO date",
        "updatedAt": "ISO date",
        "healthScore": 0-100,
        "healthState": "healthy | degraded | blocked",
        "campaignType": "product-launch | seasonal | evergreen | promotion",
        "priority": "high | medium | low"
      },
      "visualDirection": {
        "palette": {
          "primary": "#HEXCODE",
          "secondary": "#HEXCODE",
          "accent": "#HEXCODE",
          "background": "#HEXCODE",
          "text": "#HEXCODE"
        },
        "mood": "string (e.g. 'premium, clinical, data-driven')",
        "creativeDirection": "string (what this campaign looks and feels like)",
        "imageReferences": ["url or description of reference images"],
        "colorUsage": "string (which colours to use where — e.g. gold for pricing, black for premium)"),
        "typography": "string (e.g. 'bold condensed for headlines, clean sans for body')",
        "layoutStyle": "string (e.g. 'dark background, data overlay, half-screen split')",
        "contentExamples": ["examples of what good content looks like for this campaign"]
      },
      "strategy": {
        "positioningStatement": "string",
        "targetAudience": "string",
        "primaryOffer": "string (price-led)",
        "pillars": [{ "id": "string", "name": "string", "description": "string" }]
      },
      "assets": {
        "[assetId]": {
          "assetId": "string",
          "campaignId": "string",
          "name": "string",
          "assetType": "research | hook | hero-visual | carousel | video | copy",
          "status": "generated | review | published | approved | rejected | blocked",
          "platform": "instagram | tiktok | gmb",
          "owner": "string (agent handle)",
          "createdAt": "ISO date",
          "updatedAt": "ISO date",
          "qualityGateState": "pending | gate1-passed | gate2-failed | approved",
          "nextAction": "string",
          "blockedBy": ["array of assetIds"],
          "history": [{ "action": "string", "by": "string", "at": "ISO date", "reason": "string" }],
          "tags": ["array of strings"]
        }
      },
      "analytics": {
        "instagram": {},
        "google": {}
      }
    }
  }
}
```

### Key Structural Differences

| Aspect | V1 (current) | V2 (new) |
|--------|--------------|----------|
| Campaign container | `campaign` (single object) | `campaigns` (dict of containers) |
| Asset grouping | All assets in one flat `assets` dict | Assets nested inside each campaign |
| Campaign switching | Not supported | `activeCampaignId` + portfolio view |
| Visual direction | Only on TrackMan (implied) | Per-campaign, explicit |
| Write-back path | `assets[assetId]` | `campaigns[campaignId].assets[assetId]` |
| Takomo assets | Nested in TrackMan assets | Each campaign has its own assets |

---

## 2. Campaign Portfolio View (Level 1)

**What it shows:**
All campaigns as cards — like a command centre dashboard.

**Each card shows:**
- Campaign name + short name
- Status badge (active/paused/planned)
- Health score ring (colour-coded)
- Asset counts: complete / in-progress / blocked
- Campaign type tag
- Owner
- Primary platform icon

**Portfolio-level metrics:**
- Total campaigns: X active, Y planned
- Total assets across all campaigns
- Portfolio health score (weighted average)
- Recent activity across all campaigns

**Navigation:**
- Opens by default when Campaign OS loads
- Click any campaign card → enters Campaign Detail View
- Portfolio-level search/filter across all campaigns

**Why it matters:**
Christelle opens Campaign OS → sees the whole portfolio → clicks into the campaign she needs. No guessing about where Takomo lives or whether it's its own campaign.

---

## 3. Campaign Detail View (Level 2)

**What it shows:**
One campaign's full state — identity, visual direction, strategy, and all assets.

**Sections within Campaign Detail:**

1. **Campaign Identity Header**
   - Name, short name, campaign type
   - Status badge + owner
   - Platforms active
   - Created/updated timestamps
   - Health score ring + breakdown

2. **Visual Direction Panel** (distinct per campaign)
   - Colour palette swatches — primary, secondary, accent
   - Mood descriptor
   - Creative direction text
   - Image reference examples
   - Layout style description
   - This panel is what designers/ImageGen read to understand the campaign

3. **Strategy**
   - Positioning statement
   - Target audience
   - Primary offer
   - Content pillars

4. **All tabs filtered to this campaign:**
   - Overview (campaign-specific metrics)
   - Asset Queue (filtered by `campaigns[activeCampaignId].assets`)
   - Production (filtered by campaign)
   - Completion (filtered by campaign)
   - Gap Analysis (filtered by campaign)

5. **"Back to Portfolio"** link at top

---

## 4. Per-Campaign Visual Identity

This is the core of V2. Each campaign has its own visual personality — so any agent or designer opening it immediately understands the aesthetic.

### Visual Direction Fields (per campaign)

```json
visualDirection: {
  "palette": {
    "primary": "#HEXCODE",
    "secondary": "#HEXCODE",
    "accent": "#HEXCODE",
    "background": "#HEXCODE",
    "text": "#HEXCODE"
  },
  "mood": "string — one line, e.g. 'clinical data, premium chrome, TrackMan blue'",
  "creativeDirection": "string — 2-3 sentences describing what content looks like",
  "imageReferences": ["array — URLs or descriptions agents can reference"],
  "colorUsage": "string — specific guidance, e.g. 'Use gold (#FFD700) for pricing callouts, never use for backgrounds'",
  "typography": "string — e.g. 'Roboto Condensed Bold for headlines, Inter for body copy'",
  "layoutStyle": "string — e.g. 'Split screen: left=product shot, right=stat overlay'",
  "contentExamples": ["array — what good content looks like for this campaign"]
}
```

### ImageGen reads this before generating ANYTHING for a campaign

The visual direction is the brief. Every image, every design decision, every caption tone — it starts here.

---

## 5. Campaign Definitions — V2

### TrackMan Intelligence

**Campaign ID:** `trackman-intelligence`
**Campaign Type:** Evergreen / Data-Driven
**Platforms:** Instagram, TikTok, GMB
**Status:** Active

**Identity:**
- Name: TrackMan Intelligence
- Short name: TrackMan
- Goal: Drive fitting bookings and coaching sessions
- Owner: christelle
- Priority: High

**Visual Direction:**
```json
{
  "palette": {
    "primary": "#0066CC",
    "secondary": "#001122",
    "accent": "#00CC77",
    "background": "#0A0A14",
    "text": "#E8E8F0"
  },
  "mood": "Clinical precision. Data权威. TrackMan blue dominance.",
  "creativeDirection": "TrackMan data is the hero. Numbers, charts, launch monitor visuals. Chrome golf clubs on dark backgrounds. PGA Tour stat comparisons. Clean, scientific, premium. Think golf analytics lab meets luxury sports brand.",
  "imageReferences": [
    "TrackMan launch monitor screen with ball flight data",
    "Chrome iron head with data overlay (TrackMan numbers)",
    "Golfer swing capture with split-screen stat comparison",
    "Dark background, premium equipment photography"
  ],
  "colorUsage": "Use TrackMan blue (#0066CC) as dominant brand colour. Green (#00CC77) for positive metrics and CTAs. Gold for pricing. Never use for backgrounds — text only. Keep dark backgrounds consistent.",
  "typography": "Roboto Condensed Bold for numbers and headlines. Inter for body. Monospace for data labels.",
  "layoutStyle": "Split screen: product/club on left, TrackMan data overlay on right. Dark backgrounds throughout. Numbers should dominate the visual hierarchy.",
  "contentExamples": [
    "Your drive: 217m. PGA Tour avg: 264m. TrackMan found the gap.",
    "Launch monitor screenshot showing spin rate + carry distance",
    "Before/after swing data comparison"
  ]
}
```

**Assets currently in system:** (migrated from V1 `assets` that have `campaignId: trackman-intelligence`)

---

### Takomo 101T

**Campaign ID:** `takomo-101t`
**Campaign Type:** Product Launch
**Platforms:** Instagram, TikTok
**Status:** Active (planned to launch with Takomo campaign)

**Identity:**
- Name: Takomo 101T
- Short name: Takomo
- Goal: Drive Takomo 101T iron fittings and showcase value proposition
- Owner: christelle
- Priority: High

**Visual Direction:**
```json
{
  "palette": {
    "primary": "#C0C0C0",
    "secondary": "#1A1A1A",
    "accent": "#FFD700",
    "background": "#0D0D0F",
    "text": "#F5F5F5"
  },
  "mood": "Premium hollow-body iron. Chrome silver. Understated power. Value-driven but not cheap.",
  "creativeDirection": "Takomo 101T chrome iron on dark backgrounds. Price transparency is a hook — show the value. Sleek, blade-like aesthetics. Target: serious golfers who do research before buying. Clean product shots with minimal data. The iron should look desirable on its own merits, not needing TrackMan to sell it.",
  "imageReferences": [
    "Takomo 101T iron head — chrome/silver against black background",
    "Irons laid out in bag — clean product photography",
    "Swing Shack fitting session with Takomo irons",
    "Golf magazine review photo (with permission)"
  ],
  "colorUsage": "Chrome/silver primary (#C0C0C0) — the product itself. Gold accent (#FFD700) for price callouts and value messaging only. Black backgrounds (#0D0D0F) for product shots. White text for contrast on dark.",
  "typography": "Helvetica Neue Bold for headlines. Clean sans for body. Price callouts in gold, bold.",
  "layoutStyle": "Product hero: full iron head on pure black. Price callout overlaid in gold. Tagline below. No TrackMan data on product shots — keep it pure product photography.",
  "contentExamples": [
    "Takomo 101T: Less than $600 for a full set. We put it on TrackMan.",
    "Chrome hollow-body iron. Sub-$600. PGA Tour feel.",
    "Takomo 101T — the iron that divides serious golfers"
  ]
}
```

**Migration note:** V1 assets `takomo-101t-research`, `takomo-101t-hook-a`, `takomo-101t-visual-a`, `takomo-101t-production` all move here. `campaignId` updates from `trackman-intelligence` to `takomo-101t`.

---

### Winter Golf (Placeholder)

**Campaign ID:** `winter-golf`
**Campaign Type:** Seasonal
**Platforms:** Instagram, TikTok, GMB
**Status:** Planned

**Identity:**
- Name: Winter Golf
- Short name: Winter Golf
- Goal: Drive indoor golf sessions during SA winter season
- Owner: christelle
- Priority: Medium

**Visual Direction:**
```json
{
  "palette": {
    "primary": "#4A90D9",
    "secondary": "#1E3A5F",
    "accent": "#87CEEB",
    "background": "#0F1620",
    "text": "#E0F0FF"
  },
  "mood": "Cozy indoor warmth vs cold outside. Jozi winter contrast. Indoor golf paradise.",
  "creativeDirection": "Cold outside, warm inside. The contrast between grey Jo'burg winter and the warmth, green satisfaction of indoor golf. Pizzas, beers, premium simulators. Social golf atmosphere. NOT about technique or data — about the experience and enjoyment. Think: pub golf meets luxury simulator.",
  "imageReferences": [
    "Simulator screen showing lush course in winter grey context",
    "Cozy indoor setup with warm lighting",
    "Post-round drinks at Swing Shack bar",
    "Rain on window outside, golfer smiling inside"
  ],
  "colorUsage": "Cool blues for winter theme (#4A90D9). Warm accent for indoor coziness (#D4A574 or warm amber). Never clinical — keep it inviting and social.",
  "typography": "Warm, approachable. Bold for contrast headlines. Friendly sans-serif.",
  "layoutStyle": "Split mood: grey/cold outside vs warm/green inside. Social proof. Food and beverage welcome. Not data-heavy.",
  "contentExamples": [
    "It's 8°C outside. 22°C inside. Your game never stops.",
    "Rain check? How about a round.",
    "Winter doesn't exist in here."
  ]
}
```

**No assets yet — placeholder only. Created as empty campaign container.**

---

## 6. Write-Back Path Changes

### Agent Write-Back Updates

| Agent | V1 Path | V2 Path |
|-------|---------|---------|
| Scout | `assets[assetId]` | `campaigns[activeCampaignId].assets[assetId]` |
| Copywriter | `assets[assetId]` | `campaigns[activeCampaignId].assets[assetId]` |
| ImageGen | `assets[assetId]` | `campaigns[activeCampaignId].assets[assetId]` |
| Publisher | `assets[assetId]` | `campaigns[activeCampaignId].assets[assetId]` |
| Clawfix | Read `assets` | Read `campaigns[campaignId].assets` |
| All agents | — | Must read `campaignId` from asset to know which campaign to write to |

### Key Changes for Agents

1. Every asset write must specify `campaignId`
2. Agents must read the active campaign's `visualDirection` before generating content
3. Campaign switching changes `activeCampaignId` in the data file
4. All agent prompts need to include the current campaign's `visualDirection` as context

### For the UI / Cockpit

- Portfolio View reads: `Object.keys(campaigns)` → list all campaign IDs
- Campaign Detail reads: `campaigns[activeCampaignId]`
- Asset tabs read: `campaigns[activeCampaignId].assets`
- Completion counts: filtered by `campaigns[activeCampaignId].assets`

---

## 7. Migration Plan

### Phase 1 — Schema Migration (no code changes to agents yet)

1. **Backup:** Copy current `campaign-data.json` as `campaign-data.v1.backup.json`
2. **Create new structure:** Add `portfolioMetadata`, `activeCampaignId`, `campaigns` dict
3. **Migrate TrackMan Intelligence:** Move V1 `campaign` object into `campaigns.trackman-intelligence`, keep existing strategy/assets
4. **Migrate Takomo 101T:** Move V1 `assets[takomo-*]` entries into `campaigns.takomo-101t.assets`, update `campaignId` on each
5. **Create Winter Golf:** Empty campaign container with `status: planned`
6. **Validate:** Clawfix reads the new structure, confirms all asset IDs present, counts match

### Phase 2 — Code Migration (agents + cockpit)

1. **Update `regenerate-cockpit.py`:** Iterate `campaigns` dict, generate portfolio view + campaign views
2. **Update `patch-cockpit.js`:** Target `campaigns[activeCampaignId].assets` not flat `assets`
3. **Update all agent write-back scripts:** Update JSON path in each agent
4. **Update cockpit HTML:** Add campaign selector, portfolio view, campaign detail view
5. **Verify:** Clawfix runs end-to-end verification on all campaigns

### Phase 3 — UI Layer

1. **Portfolio View page:** `campaign-os/portfolio.html` (or tab in existing cockpit)
2. **Campaign selector dropdown:** At top of every view
3. **Visual direction panel:** Visible in Campaign Detail View
4. **Filter all tabs by `activeCampaignId`**

### Migration Order

1. Schema migration + commit (this spec approved)
2. Regenerate cockpit Python updated
3. Deploy → verify Portfolio View works
4. Agent write-back paths updated (one agent at a time, verify)
5. UI campaign selector + views built

### Rollback Plan

If migration fails: revert to `campaign-data.v1.backup.json`, restore V1 structure, rollback cockpit to pre-migration version.

---

## 8. Clawfix Verification Checklist

After migration, Clawfix verifies:

### Schema Structure
- [ ] `portfolioMetadata` exists at root
- [ ] `activeCampaignId` exists at root
- [ ] `campaigns` is a dict (not an array)
- [ ] Each campaign entry has: `identity`, `visualDirection`, `assets`, `strategy`
- [ ] No orphaned assets outside `campaigns[id].assets`

### Asset Migration
- [ ] All V1 assets are present in V2 (same `assetId`, same data)
- [ ] `campaignId` updated correctly on each asset
- [ ] Takomo assets now in `campaigns.takomo-101t.assets`
- [ ] TrackMan assets now in `campaigns.trackman-intelligence.assets`
- [ ] Asset counts per campaign match expected totals

### Visual Direction
- [ ] TrackMan Intelligence has `visualDirection.palette` with all 5 colours
- [ ] Takomo 101T has `visualDirection.palette` with all 5 colours
- [ ] Winter Golf has `visualDirection.mood` and `creativeDirection`
- [ ] All three campaigns have `imageReferences` populated

### Write-Back Paths
- [ ] Scout writes to `campaigns[campaignId].assets[assetId]`
- [ ] Copywriter writes to correct campaign based on `campaignId`
- [ ] ImageGen reads `visualDirection` before generating
- [ ] Publisher reads from correct campaign
- [ ] No agent writes to flat `assets` path anymore

### Cockpit Display
- [ ] Portfolio View shows all 3 campaigns (TrackMan, Takomo, Winter Golf)
- [ ] Campaign selector dropdown populated from `Object.keys(campaigns)`
- [ ] Selecting a campaign filters all tabs to that campaign's assets
- [ ] Completion counts reflect campaign-specific assets only
- [ ] Visual direction panel shows palette swatches + mood for selected campaign

---

## 9. Acceptance Criteria

### Portfolio View
- [ ] Campaign OS opens to Portfolio View (not a single campaign)
- [ ] All campaigns visible as cards: TrackMan Intelligence, Takomo 101T, Winter Golf
- [ ] Each card shows: name, status, health score, asset counts
- [ ] Clicking a card enters Campaign Detail View

### Campaign Detail View
- [ ] Shows campaign identity (name, type, owner, status, health)
- [ ] Visual Direction panel is prominent — palette swatches + mood visible
- [ ] Strategy section (positioning, audience, offer, pillars)
- [ ] All 5 tabs (Overview, Asset Queue, Production, Completion, Gap Analysis) filtered to selected campaign
- [ ] "Back to Portfolio" link at top

### Visual Direction
- [ ] Each campaign has unique palette — Takomo ≠ TrackMan ≠ Winter Golf
- [ ] ImageGen can read `visualDirection` and understand campaign aesthetic
- [ ] Copywriter can read `visualDirection` and understand tone/mood
- [ ] Colour swatches render in Campaign Detail View

### Migration Integrity
- [ ] All existing assets present in V2 with same data
- [ ] No data loss during migration
- [ ] Rollback plan tested

### Agents
- [ ] All agents write to correct campaign's assets path
- [ ] Agents read visual direction before generating
- [ ] No broken write-backs after migration

---

## 10. Pending Christelle Approval

Before migration begins, Christelle needs to approve:

1. **Schema structure** — is the V2 model right? Any fields missing?
2. **TrackMan Intelligence visual direction** — does TrackMan blue + green + dark palette accurately represent the campaign?
3. **Takomo 101T visual direction** — chrome + gold + black — does this feel right for Takomo?
4. **Winter Golf placeholder** — is the cool blue + warm amber + cozy indoor mood correct direction?
5. **Migration plan** — any steps missing or out of order?

**Once approved:** I'll commit this spec, then begin Phase 1 migration (schema + backup + commit).

---

*Spec version 1.0 — 2026-06-02*