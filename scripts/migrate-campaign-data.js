#!/usr/bin/env node
/**
 * CAMPAIGN MOTHERSHIP V2 — Phase 1 Migration Script
 * 
 * Converts campaign-data.json from V1 (single campaign + flat assets)
 * to V2 (portfolio + multiple campaigns + nested assets)
 * 
 * Run: node scripts/migrate-campaign-data.js
 * Rollback: cp campaign-data.v1.backup.json campaign-os/campaign-data.json
 */

const fs = require('fs');
const path = require('path');

const DATA_FILE = path.join(process.cwd(), 'campaign-os/campaign-data.json');
const BACKUP_FILE = path.join(process.cwd(), 'campaign-os/campaign-data.v1.backup.json');

// ─── CAMPAIGN DNA + MEMORY + BRIEF TEMPLATES ───────────────────────────────────

const TRACKMAN_INTELLIGENCE = {
  identity: {
    campaignId: "trackman-intelligence",
    name: "TrackMan Intelligence",
    shortName: "TrackMan",
    goal: "Drive fitting bookings and coaching sessions",
    status: "active",
    owner: "christelle",
    platforms: ["instagram", "tiktok", "gmb"],
    createdAt: "2026-03-15T00:00:00Z",
    updatedAt: new Date().toISOString(),
    healthScore: 68,
    healthState: "degraded",
    campaignType: "evergreen",
    priority: "high"
  },
  visualDirection: {
    palette: {
      primary: "#0066CC",
      secondary: "#001122",
      accent: "#00CC77",
      background: "#0A0A14",
      text: "#E8E8F0"
    },
    mood: "Clinical precision. Data权威. TrackMan blue dominance.",
    creativeDirection: "TrackMan data is the hero. Numbers, charts, launch monitor visuals. Chrome golf clubs on dark backgrounds. PGA Tour stat comparisons. Clean, scientific, premium. Think golf analytics lab meets luxury sports brand.",
    imageReferences: [
      "TrackMan launch monitor screen with ball flight data",
      "Chrome iron head with data overlay (TrackMan numbers)",
      "Golfer swing capture with split-screen stat comparison",
      "Dark background, premium equipment photography"
    ],
    colorUsage: "Use TrackMan blue (#0066CC) as dominant brand colour. Green (#00CC77) for positive metrics and CTAs. Gold for pricing. Never use for backgrounds — text only. Keep dark backgrounds consistent.",
    typography: "Roboto Condensed Bold for numbers and headlines. Inter for body. Monospace for data labels.",
    layoutStyle: "Split screen: product/club on left, TrackMan data overlay on right. Dark backgrounds throughout. Numbers should dominate the visual hierarchy.",
    contentExamples: [
      "Your drive: 217m. PGA Tour avg: 264m. TrackMan found the gap.",
      "Launch monitor screenshot showing spin rate + carry distance",
      "Before/after swing data comparison"
    ]
  },
  brief: {
    purpose: "Drive fitting bookings and coaching sessions by proving Swing Shack's TrackMan technology gives golfers data-driven insight their game has been missing.",
    audience: "Jozi golfers, 25-50, mid-high handicap. They track their fitness — they want to track their golf. Data-aware, skeptical of voodoo tips, willing to pay for evidence-based improvement.",
    bigIdea: "Your swing has a number. TrackMan measures it. That number is the shortcut to better scores.",
    successMetric: "Fitting sessions booked. Secondary: GMB posts live weekly. Tertiary: engagement rate on stat-hook content above 2.5%.",
    whatGoodLooksLike: "A hook that stops the scroll with a specific number. A visual that shows TrackMan data overlaid on a club or swing. A caption that earns the click by expanding the data story. Booking link front and centre.",
    whatBadLooksLike: "Vague transformation claims ('From confused golfer to confident striker'). Busy backgrounds without contrast. Price-led content without data justification. Anything that looks like generic golf marketing."
  },
  dna: {
    tone: "Clinical authority. Data speaks, we just translate it. No hype, no fluff — numbers are the argument. Authoritative but not cold. Expert without being gatekeeping.",
    contentMix: "70% educational (data insights, stats explainers) / 20% promotional (session offers, fitting deals) / 10% social proof (client results, before/after)",
    requiredContentTypes: ["hook-stats", "hero-visual", "gmb-post"],
    preferredVisualStyles: ["data overlay on dark background", "chrome equipment photography", "stat comparison graphics", "launch monitor screenshots"],
    forbiddenVisualStyles: ["bright neon backgrounds", "cartoon/golf mascot imagery", "heavily filtered/polarized photo edits", "text over busy backgrounds without contrast layer"],
    ctaPhilosophy: "Direct price-led with anchoring: show the value first (TrackMan data), then introduce the offer. Always include R-amount. 'From R250' works because the data has already justified the price.",
    platformStrategy: {
      instagram: "Stat-first hook stops the scroll. Data overlay on image tells the story. Caption expands with context. Link in bio drives booking.",
      tiktok: "Hook is the number/stat itself. 'Your drive: 199m' as text overlay. 3-second hook, then explain the data. Fast-cut, punchy.",
      gmb: "Trust + proof + convenience. Service highlight with one key stat. Clean, professional, no gimmicks. Call to action is always 'book now' or 'call us'."
    },
    exampleHighPerforming: [
      { assetId: "hook-a-round1", whyItWorked: "'Your golf stats don't lie' — specific, implies measurement, triggers curiosity about what the stats reveal. Stats hooks 2.5x better than transformation hooks." }
    ],
    exampleLowPerforming: [
      { assetId: "hook-b-round1", whyItFailed: "'FROM CONFUSED GOLFER TO CONFIDENT STRIKER' — vague, no data anchor. Transformation claims without proof feel empty." }
    ]
  },
  memory: {
    bestHooks: [
      { assetId: "hook-a-round1", platform: "instagram", performance: { reach: 90, likes: 4, engagementRate: 4.44 }, notes: "Stats angle consistently outperforms transformation. 'Your [metric]' format is the winner." }
    ],
    bestVisuals: [],
    bestContentTypes: ["hook-stats", "gmb-service-post"],
    failedContent: [
      { assetId: "hook-b-round1", reason: "Vague transformation claim, no data anchor", lesson: "Always lead with a number or specific stat. 'Your [X]' outperforms 'FROM [state] TO [state]'" },
      { assetId: "hook-c-round1", reason: "Convenience angle too generic", lesson: "Weather/indoor convenience is table stakes, not a hook. Stats create urgency." }
    ],
    lessonsLearned: [
      "Stats hooks consistently outperform all other angles — lead with numbers always",
      "Meters > Yards for SA market — confirmed April 2026",
      "Dark background with data overlay looks premium with TrackMan theme",
      "Caption ≠ Overlay Text — supplementary copy drives click-through, not the hook itself",
      "Hook A best performer (Round 1) was never re-published — opportunity cost"
    ]
  },
  strategy: {
    positioningStatement: "For SA golfers who suspect their swing has more potential than their scores show. Data beats guesswork.",
    targetAudience: "Jozi golfers, 25-50, mid-high handicap, data-aware. Already tracking fitness — they want to track golf too.",
    primaryOffer: "TrackMan Assessment from R900. First session R250. Bundle R1,400 (save R250)",
    pillars: [
      { id: "p1", name: "Stats", description: "Data-driven insights that reveal improvement opportunity" },
      { id: "p2", name: "Assessment", description: "TrackMan technology for precise swing analysis" },
      { id: "p3", name: "Improvement", description: "Clear path from data to better scores" }
    ]
  },
  assets: {}
};

const TAKOMO_101T = {
  identity: {
    campaignId: "takomo-101t",
    name: "Takomo 101T",
    shortName: "Takomo",
    goal: "Drive Takomo 101T iron fittings and showcase value proposition",
    status: "active",
    owner: "christelle",
    platforms: ["instagram", "tiktok"],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    healthScore: 50,
    healthState: "degraded",
    campaignType: "product-launch",
    priority: "high"
  },
  visualDirection: {
    palette: {
      primary: "#C0C0C0",
      secondary: "#1A1A1A",
      accent: "#FFD700",
      background: "#0D0D0F",
      text: "#F5F5F5"
    },
    mood: "Premium hollow-body iron. Chrome silver. Understated power. Value-driven but not cheap.",
    creativeDirection: "Takomo 101T chrome iron on dark backgrounds. Price transparency is a hook — show the value. Sleek, blade-like aesthetics. Target: serious golfers who do research before buying. Clean product shots with minimal data. The iron should look desirable on its own merits, not needing TrackMan to sell it.",
    imageReferences: [
      "Real Takomo 101T iron head — chrome/silver against black background (real product photography)",
      "Irons laid out in bag — clean product photography",
      "Swing Shack fitting session with Takomo irons (real photo)"
    ],
    colorUsage: "Chrome/silver primary (#C0C0C0) — the product itself. Gold accent (#FFD700) for price callouts and value messaging only. Black backgrounds (#0D0D0F) for product shots. White text for contrast on dark.",
    typography: "Helvetica Neue Bold for headlines. Clean sans for body. Price callouts in gold, bold.",
    layoutStyle: "Product hero: full iron head on pure black. Price callout overlaid in gold. Tagline below. No TrackMan data on product shots — keep it pure product photography.",
    contentExamples: [
      "Takomo 101T: Less than $600 for a full set. We put it on TrackMan.",
      "Chrome hollow-body iron. Sub-$600. PGA Tour feel.",
      "Takomo 101T — the iron that divides serious golfers"
    ]
  },
  brief: {
    purpose: "Establish Takomo 101T as the smart golfer's iron of choice in SA — premium hollow-body technology at a price that challenges the big brands.",
    audience: "Serious golfers, 25-50, mid-to-low handicap. They do their research. They want Tour-level performance without Tour-level prices. They read reviews, compare specs, and buy based on data not branding.",
    bigIdea: "Takomo 101T: the iron that gets serious golfers arguing — and fitting sessions that settle the argument.",
    successMetric: "Takomo fitting sessions booked. Secondary: engagement on Takomo content above TrackMan benchmark. Tertiary: Takomo mentions in bio link clicks.",
    whatGoodLooksLike: "A real Takomo iron head on pure black — no AI, no stock photos. A price callout in gold that creates urgency without discounting. A hook that poses a question serious golfers want answered. Copy that respects the reader's intelligence.",
    whatBadLooksLike: "AI-generated club heads that look fake. Broken/garbled text. Price claims without the 'under $600' anchor. Generic golf content that could be any iron. Anything that talks down to the audience."
  },
  dna: {
    tone: "Confident, curious, slightly provocative. The kind of content that makes serious golfers stop and think — then book a fitting to settle the argument. Sharp without being aggressive.",
    contentMix: "50% product education (what makes Takomo different) / 30% controversy/question angle / 20% value proof (price-to-performance)",
    requiredContentTypes: ["hero-visual", "hook-question", "gmb-service-post"],
    preferredVisualStyles: ["real product photography of Takomo iron head on black", "clean product cutout on dark background", "gold price callout overlaid on chrome", "sleek blade-like aesthetic shots"],
    forbiddenVisualStyles: [
      "AI-generated club/product heads (Christelle rule) — real product photography only",
      "busy backgrounds with text overlay without contrast layer",
      "stock golf photos without product context",
      "any image with broken/garbled text"
    ],
    ctaPhilosophy: "Price transparency as hook: lead with 'less than $600' or 'from R250' because the value is the argument. CTAs are always 'Book Takomo Fitting' with R-amount anchored.",
    platformStrategy: {
      instagram: "Product-first: the iron head IS the hero. Price callout in gold. Caption earns the click with the controversy/question angle. Link to booking.",
      tiktok: "Hook is the price question: 'Is Takomo 101T worth it? We put it on TrackMan.' Product visual first, data second.",
      gmb: "Takomo fitting service highlight. Price-led. Trust signal: 'Swing Shack is authorized Takomo fitter.'"
    },
    exampleHighPerforming: [],
    exampleLowPerforming: [
      { assetId: "takomo-101t-visual-a", whyItFailed: "AI-generated club head looked fake. Text broken/garbled. Pricing callout wrong. Product credibility too low. Real product photography required per Christelle gate rule." }
    ]
  },
  memory: {
    bestHooks: [],
    bestVisuals: [],
    bestContentTypes: ["hook-question", "hero-visual-product"],
    failedContent: [
      { assetId: "takomo-101t-visual-a", reason: "AI product imagery looks fake. Broken text. Wrong pricing. Product credibility too low.", lesson: "Golf club/physical product campaigns require real product photography. AI may only do background/layout/text treatment. No AI product heads." }
    ],
    lessonsLearned: [
      "For golf clubs and physical products: requiresRealProductImage = true always",
      "AI-generated club heads fail Gate 2 by default",
      "Text must be added as separate design layer — never embedded in generated image",
      "Broken text = automatic quality gate failure"
    ]
  },
  strategy: {
    positioningStatement: "For SA golfers who want Tour-level iron performance without Tour-level pricing. Takomo 101T is the research-backed upgrade.",
    targetAudience: "Mid-to-low handicap golfers, 25-50, who compare specs before buying. They read Plugged In Golf, Golfalot, Pitchmarks. They want evidence, not marketing.",
    primaryOffer: "Takomo 101T Fitting — from R900 (full bag). First session R250.",
    pillars: [
      { id: "t1", name: "Value", description: "Sub-$600 for full set — exceptional price-to-performance" },
      { id: "t2", name: "Technology", description: "Hollow-body, 1028 carbon steel, 360 unsupported face" },
      { id: "t3", name: "Feel", description: "Better sound than predecessor 101, blade-like aesthetics" }
    ]
  },
  assets: {}
};

const WINTER_GOLF = {
  identity: {
    campaignId: "winter-golf",
    name: "Winter Golf",
    shortName: "Winter Golf",
    goal: "Drive indoor golf sessions during SA winter season",
    status: "planned",
    owner: "christelle",
    platforms: ["instagram", "tiktok", "gmb"],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    healthScore: 0,
    healthState: "healthy",
    campaignType: "seasonal",
    priority: "medium"
  },
  visualDirection: {
    palette: {
      primary: "#4A90D9",
      secondary: "#1E3A5F",
      accent: "#D4A574",
      background: "#0F1620",
      text: "#E0F0FF"
    },
    mood: "Cozy indoor warmth vs cold outside. Jozi winter contrast. Indoor golf paradise.",
    creativeDirection: "Cold outside, warm inside. The contrast between grey Jo'burg winter and the warmth, green satisfaction of indoor golf. Pizzas, beers, premium simulators. Social golf atmosphere. NOT about technique or data — about the experience and enjoyment. Think: pub golf meets luxury simulator.",
    imageReferences: [
      "Simulator screen showing lush course in winter grey context",
      "Cozy indoor setup with warm lighting",
      "Post-round drinks at Swing Shack bar",
      "Rain on window outside, golfer smiling inside"
    ],
    colorUsage: "Cool blues for winter theme (#4A90D9). Warm accent for indoor coziness (#D4A574 or warm amber). Never clinical — keep it inviting and social.",
    typography: "Warm, approachable. Bold for contrast headlines. Friendly sans-serif.",
    layoutStyle: "Split mood: grey/cold outside vs warm/green inside. Social proof. Food and beverage welcome. Not data-heavy.",
    contentExamples: [
      "It's 8°C outside. 22°C inside. Your game never stops.",
      "Rain check? How about a round.",
      "Winter doesn't exist in here."
    ]
  },
  brief: {
    purpose: "Keep Swing Shack bookings steady through SA winter by positioning indoor golf as the obvious choice when outdoor courses go cold.",
    audience: "Regular Jo'burg golfers who stop playing in winter because their home course gets cold or they travel less. They already have clubs — they just need a reason to keep playing.",
    bigIdea: "Winter doesn't exist in here. (It's always 22°C, there's food and drinks, and the simulator never closes.)",
    successMetric: "Winter session bookings vs prior year. Secondary: winter package upsells. Tertiary: social engagement on contrast-style content.",
    whatGoodLooksLike: "A visual that makes you want to be inside — warm lights, green fairways on screen, something cold and grey outside the window. A hook that names the weather or the day. Content that feels like a friend saying 'actually, this is good.'",
    whatBadLooksLike: "Clinical data overlays. Golf swing technique photos. Anything that makes indoor golf sound like a chore or a substitute. Content that positions winter as a problem rather than Swing Shack as the answer."
  },
  dna: {
    tone: "Warm, inviting, slightly cheeky. The tone of a friend who knows the best spot in Jo'burg. Not trying to be premium or clinical — just genuinely fun. Think: 'you know what this weather needs? A round.'",
    contentMix: "40% social proof (look how good it is inside) / 30% contrast/humor (cold vs warm) / 20% practical (sessions available, deals) / 10% lifestyle (food, drinks, atmosphere)",
    requiredContentTypes: ["hook-contrast", "lifestyle-visual", "gmb-event-post"],
    preferredVisualStyles: ["warm indoor lighting on simulator", "cozy bar/food setup at Swing Shack", "contrast: grey sky outside vs green simulator inside", "smiling golfers, social atmosphere"],
    forbiddenVisualStyles: ["clinical/data-heavy graphics", "golf swing technique photos", "cold blue colour grading on indoor content", "anything that makes indoor golf look like a chore"],
    ctaPhilosophy: "Casual and low-friction: 'Book a session' not 'Book now — limited slots.' Make it feel like a no-brainer, not a sales push.",
    platformStrategy: {
      instagram: "Lifestyle-first: food, drinks, simulators, social vibe. Contrast hooks work well. Carousels showing 'inside vs outside' perform.",
      tiktok: "'It's [X]°C outside. This is what we did instead.' Fast, relatable, shareable. Show the vibe, not the data.",
      gmb: "Seasonal/event posts. 'Winter sessions available.' Warm imagery, social proof. 'Book your winter round.'"
    },
    exampleHighPerforming: [],
    exampleLowPerforming: []
  },
  memory: {
    bestHooks: [],
    bestVisuals: [],
    bestContentTypes: [],
    failedContent: [],
    lessonsLearned: []
  },
  strategy: {
    positioningStatement: "When the courses go cold, the simulator doesn't.",
    targetAudience: "Regular Jo'burg golfers who play less in winter. They love golf but the weather stops them.",
    primaryOffer: "Winter sessions from R250. Winter package deals available.",
    pillars: [
      { id: "w1", name: "Warmth", description: "22°C inside, always" },
      { id: "w2", name: "Convenience", description: "No booking required, walk-ins welcome" },
      { id: "w3", name: "Social", description: "Food, drinks, company — make it a round" }
    ]
  },
  assets: {}
};

// ─── MIGRATION ────────────────────────────────────────────────────────────────

console.log('=== Campaign Mothership V2 — Phase 1 Migration ===\n');

// 1. Load V1 data
const raw = fs.readFileSync(DATA_FILE, 'utf8');
const V1 = JSON.parse(raw);

console.log('✓ Loaded campaign-data.json (V1)');
console.log(`  Assets found: ${Object.keys(V1.assets || {}).join(', ')}`);

// 2. Create backup
fs.writeFileSync(BACKUP_FILE, raw);
console.log(`\n✓ Backup created: campaign-data.v1.backup.json`);

// 3. Build V2 structure
const V2 = {
  portfolioMetadata: {
    name: "Swing Shack Campaign Portfolio",
    description: "All active and planned marketing campaigns",
    owner: "christelle",
    lastUpdated: new Date().toISOString(),
    version: 2
  },
  activeCampaignId: "trackman-intelligence",
  campaigns: {
    "trackman-intelligence": JSON.parse(JSON.stringify(TRACKMAN_INTELLIGENCE)),
    "takomo-101t": JSON.parse(JSON.stringify(TAKOMO_101T)),
    "winter-golf": JSON.parse(JSON.stringify(WINTER_GOLF))
  }
};

// 4. Migrate assets
const v1Assets = V1.assets || {};
const takomoAssetIds = ['takomo-101t-research', 'takomo-101t-hook-a', 'takomo-101t-visual-a', 'takomo-101t-production'];

for (const assetId of takomoAssetIds) {
  if (v1Assets[assetId]) {
    const asset = v1Assets[assetId];
    // Update campaignId to takomo-101t
    asset.campaignId = "takomo-101t";
    asset.updatedAt = new Date().toISOString();
    // Add to takomo campaign assets
    V2.campaigns["takomo-101t"].assets[assetId] = asset;
    console.log(`  → Migrated: ${assetId} → campaigns.takomo-101t.assets`);
  }
}

// TrackMan campaign gets no assets from V1 (all were takomo-related)
// But we preserve the marketing metrics and health from V1 campaign
V2.campaigns["trackman-intelligence"].identity.healthScore = V1.campaign?.healthScore || 68;
V2.campaigns["trackman-intelligence"].identity.healthState = V1.campaign?.healthState || "degraded";
V2.campaigns["trackman-intelligence"].identity.updatedAt = new Date().toISOString();

console.log(`\n✓ Asset migration complete`);
console.log(`  TrackMan assets: ${Object.keys(V2.campaigns["trackman-intelligence"].assets).length}`);
console.log(`  Takomo assets: ${Object.keys(V2.campaigns["takomo-101t"].assets).length}`);
console.log(`  Winter Golf assets: ${Object.keys(V2.campaigns["winter-golf"].assets).length}`);

// 5. Write V2 data
fs.writeFileSync(DATA_FILE, JSON.stringify(V2, null, 2));
console.log(`\n✓ V2 data written to campaign-data.json`);

// 6. Verify
const V2_CHECK = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
const campaignIds = Object.keys(V2_CHECK.campaigns);
console.log(`\n=== Verification ===`);
console.log(`Campaigns found: ${campaignIds.join(', ')}`);
for (const cid of campaignIds) {
  const c = V2_CHECK.campaigns[cid];
  const assetCount = Object.keys(c.assets || {}).length;
  const hasBrief = !!c.brief?.purpose;
  const hasDNA = !!c.dna?.tone;
  const hasMemory = Array.isArray(c.memory?.lessonsLearned);
  const hasVisualDirection = !!c.visualDirection?.palette?.primary;
  console.log(`  ${cid}: ${assetCount} assets, brief=${hasBrief}, dna=${hasDNA}, memory=${hasMemory}, visual=${hasVisualDirection}`);
}

// 7. Summary
console.log(`\n=== Migration Summary ===`);
console.log(`Backup: campaign-os/campaign-data.v1.backup.json`);
console.log(`Campaigns: ${campaignIds.join(', ')}`);
console.log(`Takomo assets migrated: ${Object.keys(V2.campaigns["takomo-101t"].assets).join(', ')}`);
console.log(`\nRollback: cp campaign-os/campaign-data.v1.backup.json campaign-os/campaign-data.json`);
console.log(`\n✅ Phase 1 complete. Proceed to Phase 2 (regenerate-cockpit.py update).`);