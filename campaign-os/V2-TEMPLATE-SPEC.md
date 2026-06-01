# Campaign OS v2 — Template Schema
**Version:** 1.0-draft
**Date:** 2026-06-01
**Status:** DRAFT — awaiting ImageGen visual asset skeleton
**Owner:** Clawdia
**Reference:** V2-FOUNDATION-SPEC.md

---

## Purpose

A Campaign Template is a proven campaign configuration that can be instantiated to generate a complete campaign package from a brief, without starting from scratch each time.

Templates sit above the Campaign Factory in the generation hierarchy:
- Templates define what a campaign type needs
- Factory uses templates to generate campaign configurations
- Agents execute against the configured campaign

---

## Template Schema

Each template defines:

```json
{
  "templateId": "string",
  "name": "string",
  "goal": "enum[awareness|consideration|conversion|retention]",
  "duration": "enum[14 days|30 days|60 days|90 days]",
  "targetAudience": "string",
  "positioningStatement": "string",
  "pillars": ["pillarId"],
  "contentMix": {
    "conversion": "number (%)",
    "educational": "number (%)",
    "testimonial": "number (%)",
    "entertainment": "number (%)",
    "product": "number (%)"
  },
  "platformPriority": ["platform"],
  "assetTypes": ["assetTypeId"],
  "copyAngles": ["copyAngleId"],
  "cadence": {
    "instagram": "string",
    "tiktok": "string",
    "gmb": "string"
  },
  "offers": ["offerId"],
  "visualAssets": {
    "heroVisual": "assetSpec",
    "comparisonGraphics": "assetSpec",
    "dataVisualizations": "assetSpec",
    "ctaVisuals": "assetSpec",
    "lifestyleIntegration": "assetSpec",
    "platformFormats": {
      "instagram": ["format"],
      "tiktok": ["format"],
      "gmb": ["format"]
    }
  }
}
```

---

## 5 Campaign Template Types

### 1. Club Fitting Campaign

```json
{
  "templateId": "club-fitting",
  "name": "Club Fitting Campaign",
  "goal": "conversion",
  "targetAudience": "Mid-to-low handicap golfers, 25-50, who want data-driven equipment decisions. Jozi/Nelson Mandela Bay metro.",
  "positioningStatement": "For golfers who want their equipment to match their ambition. TrackMan takes the guesswork out of club fitting.",
  "pillars": [
    "assessment-risk-removal",
    "data-improvement",
    "social-proof"
  ],
  "contentMix": {
    "conversion": 40,
    "educational": 25,
    "testimonial": 20,
    "entertainment": 10,
    "product": 5
  },
  "platformPriority": ["instagram", "tiktok", "gmb"],
  "assetTypes": [
    "hero-visual",
    "comparison-graphic",
    "data-viz",
    "cta-visual",
    "testimonial-card",
    "gmb-post"
  ],
  "copyAngles": [
    "assessment-risk-removal",
    "data-comparison",
    "transformation",
    "social-proof"
  ],
  "cadence": {
    "instagram": "3x per week",
    "tiktok": "2x per week",
    "gmb": "1x per week"
  },
  "offers": [
    "iron-fitting-r900",
    "full-bag-fitting-r1800",
    "driver-fitting-r900",
    "fitting-bundle-r1400"
  ],
  "visualAssets": {
    "heroVisual": {
      "type": "product-hero",
      "description": "TrackMan screen showing real golfer data overlaid on club/equipment image. Background: #0D0D0D to #1A1A1A. Data overlay: real TrackMan metrics (carry, club speed, spin). Product must match campaign product. Dark background. Premium feel.",
      "visualQualityTier": "hero",
      "examples": ["TrackMan screenshot with swing data", "Club head speed + ball flight overlay"]
    },
    "comparisonGraphics": {
      "type": "before-after-data",
      "description": "Side-by-side data comparison: before fitting vs after fitting numbers. TrackMan branded.",
      "examples": ["Carry distance comparison", "Club speed improvement metrics"]
    },
    "dataVisualizations": {
      "type": "stat-graphic",
      "description": "Single-stat hook images with TrackMan data. Dark background. Bold numbers.",
      "examples": ["YOUR CLUB HEAD SPEED: 89 MPH", "BACKSPIN: 3,200 RPM"]
    },
    "ctaVisuals": {
      "type": "conversion-cta",
      "description": "Offer-focused visuals with clear pricing. R900 fitting assessment. Bundle deal. Price must be prominent visual element - R900 fitting assessment, bundle pricing. Dark background with high-contrast price.",
      "visualQualityTier": "supporting",
      "examples": ["R900 fitting assessment", "Save R250 on bundle"]
    },
    "platformFormats": {
      "instagram": ["hero-visual (1080x1080)", "carousel (1080x1080x5)", "story (1080x1920)", "reel (1080x1920)"],
      "tiktok": ["vertical video (1080x1920)", "slideshow (1080x1920)"],
      "gmb": ["landscape hero (1200x628)", "square post (1080x1080)"]
    }
  }
}
```

### 2. Coaching Campaign

```json
{
  "templateId": "coaching",
  "name": "Coaching Campaign",
  "goal": "conversion",
  "targetAudience": "Amateur golfers, 25-55, who want to improve their scores. Frustrated with inconsistent play. Willing to invest in coaching.",
  "positioningStatement": "Certified golf coaching that uses TrackMan data to show you exactly what's costing you strokes.",
  "pillars": [
    "data-improvement",
    "transformation",
    "coaching-credentials"
  ],
  "contentMix": {
    "conversion": 35,
    "educational": 35,
    "testimonial": 20,
    "entertainment": 10,
    "product": 0
  },
  "platformPriority": ["instagram", "tiktok", "gmb"],
  "assetTypes": [
    "technique-visual",
    "swing-sequence",
    "tip-graphic",
    "transformation-card",
    "instructor-profile",
    "gmb-post"
  ],
  "copyAngles": [
    "data-improvement",
    "transformation",
    "credibility",
    "urgency"
  ],
  "cadence": {
    "instagram": "3x per week",
    "tiktok": "3x per week",
    "gmb": "1x per week"
  },
  "offers": [
    "tpi-assessment-r1250",
    "lesson-package-3-r1500",
    "lesson-package-5-r2400",
    "lesson-package-10-r4700",
    "birdie-hunter-r2300",
    "i-am-golf-r2850"
  ],
  "visualAssets": {
    "heroVisual": {
      "type": "instructor-hero",
      "description": "Certified instructor with TrackMan data overlay. Professional, trustworthy. Show instructor + data.",
      "requiresRealPhotography": true,
      "realPhotographyNote": "Instructor must be real Swing Shack staff - face must be real photograph, not AI-generated. Frame and data overlay can be generated; the instructor face cannot.",
      "examples": ["Catherine/dave swing screenshot", "Instructor with student data"]
    },
    "techniqueVisuals": {
      "type": "tip-graphic",
      "description": "Single tip per post. Visual instruction. Before/after swing positions. TrackMan data optional.",
      "examples": ["Grip pressure tip", "Weight transfer visual", "Follow-through check"]
    },
    "transformationCards": {
      "type": "transformation",
      "description": "Golfer transformation story. Score improvement or distance gain. Testimonial style.",
      "photoSource": "real golfer testimonials where available; AI-generated only as fallback",
      "examples": ["Handicap improvement story", "Distance gain testimonial"]
    },
    "platformFormats": {
      "instagram": ["tip-graphic (1080x1080)", "carousel (1080x1080x3-5)", "story (1080x1920)", "reel (1080x1920)"],
      "tiktok": ["tip-video (1080x1920)", "swing breakdown (1080x1920)"],
      "gmb": ["lesson offer post (1080x1080)", "instructor feature (1200x628)"]
    }
  }
}
```

### 3. Event Campaign

```json
{
  "templateId": "event",
  "name": "Event Campaign",
  "goal": "awareness|conversion",
  "targetAudience": "Golfers in the event's geographic market. Handicap range varies. Interested in competition and community.",
  "positioningStatement": "Enter South Africa's premier indoor golf competition. Compete on real TrackMan simulators.",
  "pillars": [
    "event-competition",
    "community",
    "social-proof"
  ],
  "contentMix": {
    "conversion": 20,
    "educational": 15,
    "testimonial": 25,
    "entertainment": 30,
    "product": 10
  },
  "platformPriority": ["instagram", "tiktok", "gmb"],
  "assetTypes": [
    "event-hero",
    "event-teaser",
    "leaderboard-graphic",
    "participant-feature",
    "recap-visual",
    "cta-poster"
  ],
  "copyAngles": [
    "competition",
    "community",
    "urgency",
    "social-proof"
  ],
  "cadence": {
    "instagram": "daily during event week",
    "tiktok": "2-3x during event",
    "gmb": "pre-event announcement"
  },
  "visualAssets": {
    "heroVisual": {
      "type": "event-poster",
      "description": "High-energy event visual. Brand Swing Shack. Event name + date + prize. Bold typography.",
      "examples": ["Tournament poster", "Competition announcement graphic"]
    },
    "teasers": {
      "type": "countdown-format",
      "description": "Pre-event countdown. 7 days / 3 days / 1 day. Building urgency.",
      "preEventOnly": true,
      "note": "Countdown/teaser assets are pre-event only. Live event needs real photography.",
      "examples": ["7 days to go", "Tomorrow!", "Today!"]
    },
    "leaderboardGraphics": {
      "type": "live-results",
      "description": "Real-time leaderboard visuals during event. Rankings + scores. Live feel.",
      "requiresRealPhotography": true,
      "realPhotographyNote": "Live leaderboard scores come from real event photography - generate the leaderboard FORMAT/FRAME only, not the content. Scores and golfer names must be real data inserted after event.",
      "preEventOnly": false,
      "examples": ["Top 10 leaderboard", "Closest to pin winner"]
    },
    "platformFormats": {
      "instagram": ["event poster (1080x1080)", "story countdown (1080x1920)", "reel (1080x1920)"],
      "tiktok": ["event highlights (1080x1920)", "winner announcement (1080x1920)"],
      "gmb": ["event announcement (1200x628)", "results post (1080x1080)"]
    }
  }
}
```

### 4. Product Campaign

```json
{
  "templateId": "product",
  "name": "Product Campaign",
  "goal": "consideration|conversion",
  "targetAudience": "Golfers browsing equipment. Mid-handicap. Research-oriented. Wants quality without premium pricing.",
  "positioningStatement": "Takomo delivers tour-quality performance at a price that makes sense. Here's the data to prove it.",
  "pillars": [
    "product-quality",
    "value",
    "data-comparison"
  ],
  "contentMix": {
    "conversion": 30,
    "educational": 30,
    "testimonial": 20,
    "entertainment": 10,
    "product": 10
  },
  "platformPriority": ["instagram", "tiktok"],
  "assetTypes": [
    "product-hero",
    "feature-graphic",
    "spec-comparison",
    "lifestyle-shot",
    "review-card"
  ],
  "copyAngles": [
    "quality-data",
    "value",
    "comparison",
    "review"
  ],
  "cadence": {
    "instagram": "2-3x per week",
    "tiktok": "1-2x per week",
    "gmb": "as needed"
  },
  "visualAssets": {
    "heroVisual": {
      "type": "product-shot",
      "description": "Clean product photography. Takomo clubs on TrackMan screen. Premium dark background.",
      "examples": ["Takomo 101T on simulator", "Iron set detail shot"]
    },
    "featureGraphics": {
      "type": "spec-callout",
      "description": "Single feature per post. Technical spec with visual. Tour-quality materials.",
      "examples": ["Forged blade construction", "Custom shaft options"]
    },
    "comparisonGraphics": {
      "type": "vs-competitor",
      "description": "Takomo vs competitors. Price + performance data. TrackMan results.",
      "examples": ["Takomo vs Callaway same spec", "Value comparison chart"]
    },
    "platformFormats": {
      "instagram": ["product hero (1080x1080)", "feature carousel (1080x1080x4)", "story (1080x1920)"],
      "tiktok": ["product demo (1080x1920)", "unboxing (1080x1920)"]
    }
  }
}
```

### 5. Membership Campaign

```json
{
  "templateId": "membership",
  "name": "Membership Campaign",
  "goal": "retention|conversion",
  "targetAudience": "Existing members (retention) + prospective members (conversion). Regular golfers who could benefit from unlimited practice.",
  "positioningStatement": "Serious golfers practice seriously. Membership gives you unlimited access to TrackMan-powered training.",
  "pillars": [
    "membership-value",
    "member-benefit",
    "social-proof"
  ],
  "contentMix": {
    "conversion": 20,
    "educational": 20,
    "testimonial": 30,
    "entertainment": 20,
    "product": 10
  },
  "platformPriority": ["instagram", "gmb"],
  "assetTypes": [
    "membership-hero",
    "benefits-visual",
    "tier-comparison",
    "member-feature",
    "renewal-reminder",
    "cta-poster"
  ],
  "copyAngles": [
    "value",
    "member-benefit",
    "exclusivity",
    "urgency"
  ],
  "cadence": {
    "instagram": "1-2x per week",
    "tiktok": "1x per week",
    "gmb": "monthly"
  },
  "visualAssets": {
    "heroVisual": {
      "type": "membership-cta",
      "description": "Bold membership offer visual. Benefits summary. Clear pricing. Dark premium background.",
      "examples": ["Membership from R500/month", "4 free sessions included"]
    },
    "benefitsVisuals": {
      "type": "benefit-card",
      "description": "Single benefit highlighted. Icon + value prop. Clean layout.",
      "examples": ["4 free practice sessions/month", "15% off all coaching", "25% off fittings"]
    },
    "tierComparison": {
      "type": "pricing-table",
      "description": "Membership tiers side by side. Price + benefits. Clear winner highlighted.",
      "examples": ["Individual vs Full Access vs Elite"]
    },
    "platformFormats": {
      "instagram": ["benefits card (1080x1080)", "tier comparison (1080x1350)", "story (1080x1920)"],
      "tiktok": ["member testimonial (1080x1920)", "practice session highlight (1080x1920)"],
      "gmb": ["membership offer (1200x628)", "renewal reminder (1080x1080)"]
    }
  }
}
```

---

## Takomo 101T — Template Instantiation

**Input:** Takomo 101T / Goal: Sales / Duration: 30 days

**Template:** Product Campaign (best fit for equipment sales)

**Instantiated config:**
```json
{
  "templateId": "product",
  "instantiatedFrom": "Takomo 101T",
  "goal": "conversion",
  "campaignName": "Takomo 101T — Sales Campaign",
  "duration": "30 days",
  "positioningStatement": "Tour-quality cavity back at a price that makes sense. TrackMan data proves the performance.",
  "pillars": ["product-quality", "value", "data-comparison"],
  "assetTargets": {
    "instagram": { "hero": 4, "carousel": 2, "reel": 2, "story": 3 },
    "tiktok": { "product-demo": 2, "unboxing": 1 },
    "gmb": { "product-post": 1 }
  },
  "estimatedAssets": 15,
  "campaignHook": "Takomo 101T iron set — cavity back forgiveness, tour-level performance. From R8,500."
}
```

---

## What Needs ImageGen's Input

The schema above defines the visual asset structure per template type. ImageGen needs to confirm/fill in:

1. **For each asset type** — does the description match what ImageGen can produce?
2. **Platform formats** — are the dimensions correct? Any missing formats?
3. **Visual examples** — are the listed examples good representations, or should they be different?
4. **Asset quantity** — for 30-day campaign, are the asset targets realistic?
5. **Template coverage** — are there campaign types not covered by the 5 templates?

This is the visual asset skeleton. Once ImageGen confirms, the template schema is complete and the Factory can use it to generate campaign configurations from briefs.

---

**Next:** ImageGen reviews and provides the visual asset skeleton confirmation. Then template schema is locked and can be used by Campaign Factory.