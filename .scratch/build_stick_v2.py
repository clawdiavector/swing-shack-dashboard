"""Update Stick brand planning with the REAL brand bibles now we have them.

Updates:
1. stick.json planning — add the canonical brand bible content
   - Brand purpose, essence, mission, vision, promise, mantra
   - Core belief (already correct: "Everything has to earn its place.")
   - 5 brand values
   - Tone rules (the real ones, not the tone-rules.md scratchpad)
   - Voice: "Sharp, confident, direct, smart, rebellious"
   - Master brand line: "Better Begins Here."
   - Strategic belief: "Everything has to earn its place."
   - Signature lines: "Fit First. Buy Second." / "Why It's Here." / "Respect the Player."
   - Canonical recurring properties:
       WHY IT'S HERE / FIT FIRST / BUILT AT STICK / ASK STICK / STYLE THAT BELONGS / PRODUCT DROP
   - Visual identity:
       Primary: Deep teal (#004d5a) + Charcoal (#1a1a1a)
       Background: Near-black (#0d0d0d) or dark charcoal (#121212)
       Accent: Amber / burnt orange (#f0a030)
       Primary font: Inter (400/600/700/900) — substitute Plus Jakarta Sans
       Secondary font: JetBrains Mono (400)
       Cards 6-8px, buttons 4px
       Dark studio environment, performance minimalism with attitude
   - Specific brands stocked: Takomo, Srixon, Titleist, Callaway, Ping, TaylorMade, Mizuno, Vice, Psycho Bunny, L.A.B Putters, LA Golf, Miura, Avoda, Fujimoto
   - Strategic ambition: "Most trusted modern golf retailer and fitting authority in the Western Cape, with national relevance"
   - Proof: 1,100+ GBP interactions Mar-Aug 2026; Fit Fact leads R20-R32 each; founding team are fitters/coaches/builders
   - Partners with brands traditional shops ignore: Takomo, Vice, Psycho Bunny

2. stick-herman-sample-month.json — update headlines/copy to match brand bible voice.
   Voice is "Sharp, confident, direct, smart, rebellious" — not the sarcastic golf-insider
   voice from the existing tone-rules.md scratchpad. That scratchpad is an internal
   campaign voice, not the master brand voice.

   Approved master lines (use verbatim):
     "Better Begins Here."
     "Everything has to earn its place."
     "Fit First. Buy Second."
     "Why It's Here."
     "Respect the Player."

   Editorial properties that headline frames should reference:
     WHY IT'S HERE — product editorial
     FIT FIRST — fitting data
     BUILT AT STICK — workshop precision
     ASK STICK — utility / education
     STYLE THAT BELONGS — apparel/lifestyle
     PRODUCT DROP — new stock

3. stock — keep my seed (Takomo 101T, Takomo Daytona, L.A.B. MEZ.1, L.A.B. DF 2.1,
   Psycho Bunny Maverick/Vance/socks/umbrella/cap, Vice Pro Plus, Titleist Pro V1, fittings)
   These all align with the brand bible's confirmed brands (Takomo, L.A.B., Psycho Bunny,
   Vice, Titleist).

4. monthly_theme "What belongs in your bag?" — keep (per Christelle's directive).
   But make sure the brand voice still speaks: the strategic belief "Everything has to
   earn its place" reinforces "what belongs in your bag?" naturally.
"""

from pathlib import Path
import json
from collections import Counter

# === Updated brand planning JSON ===
brand_planning = {
    "brand_id": "stick",
    "audited_at": "2026-09-07",
    "audited_by": "heidi",
    "source_of_truth": "data/brand-directory/stick (Brand Bible Draft v3 + Campaign OS Full Brand Bible Workbook 2, September 2026)",
    "big_brand_idea": {
        "name": "Better Begins Here.",
        "tagline": "Better Begins Here.",
        "belief": "Everything has to earn its place.",
    },
    "brand_essence": "Better golf for a new breed of golfer.",
    "brand_purpose": "To open the door to better golf for people who want to improve, while rejecting the outdated idea that serious golf must come wrapped in stuffy culture, legacy gatekeeping, and expensive nonsense.",
    "brand_mission": "To help golfers get better through: smart coaching · player-first fitting · properly matched equipment · modern product curation · a welcoming, high-performance environment. STICK matches equipment to the player, not the player to the equipment.",
    "brand_vision": "To become the benchmark for modern golf culture and performance retail in South Africa — credible, culturally relevant, technically sharp, accessible, distinctive.",
    "brand_promise": "Better Begins Here.",
    "brand_mantra_internal": "Modern golf. Real improvement.",
    "brand_archetype": {
        "primary": "The Rebel",
        "secondary": "The Sage",
        "combined": "The Smart Rebel",
        "rationale": "Challenges outdated golf norms with substance. Not a punk brand. Not an engineering robot. Edge and brains.",
    },
    "brand_personality": ["sharp", "modern", "confident", "informed", "energetic", "selective", "culturally awake"],
    "brand_personality_banned": ["stuffy", "snobbish", "corporate", "try-hard", "fake luxury", "old-money", "salesy"],
    "personality_shorthand": "Smart, rebellious, and serious about enjoying better golf.",
    "brand_values": [
        {"name": "Attitude", "summary": "STICK has edge. Does not ask traditional golf culture for approval. Not decoration — it's the reason for existing."},
        {"name": "Precision", "summary": "Takes golf seriously. The game is technical. Equipment, data, setup, details matter."},
        {"name": "Access", "summary": "Serious golf must be more open. Quality product, great advice, and meaningful improvement across budgets and backgrounds."},
        {"name": "Honesty", "summary": "Speaks plainly. No hype. No fake luxury theatre. No pretending expensive means better."},
        {"name": "Progress", "summary": "Obsessed with improvement. Golfers improve. Game evolves. Brands evolve. Culture evolves."},
    ],
    "positioning": {
        "category": "Modern golf performance retailer and culture brand",
        "statement": "STICK is where modern golfers come to thrive.",
        "intersection": ["golf improvement", "product expertise", "modern culture", "curated retail"],
    },
    "differentiation": [
        "The attitude is real",
        "Player-first (product matches player, not vice-versa)",
        "Quality across price points (Takomo, Vice alongside premium OEM)",
        "Curation is different (Takomo, Vice, Psycho Bunny — brands traditional shops ignore)",
        "Environment matters (dark matte, wood, stone — modern studio, not pro-shop)",
        "Culture is changing and STICK reflects that",
    ],
    "voice": {
        "five_words": "Sharp, confident, direct, smart, rebellious",
        "tone_rules": [
            "Direct: Get to the point.",
            "Smart: Use expertise without showing off.",
            "Unpretentious: Serious without being pompous.",
            "Modern: No stale golf phrases. No fake heritage voice.",
            "Human: Never robotic. Never over-polished.",
        ],
        "do": ["speak plainly", "make strong statements", "explain simply", "sound current", "respect audience's intelligence"],
        "dont": ["use bloated marketing language", "sound country-club formal", "oversell", "posture", "sound bitter or hostile"],
        "punctuations": "Sentence case for headlines. No full stops where brevity serves. No exclamation marks except genuine excitement. Comma-tight.",
        "humour_level": "Wry, confident — never clownish. Edge comes from attitude, not punchlines.",
        "emoji_policy": "Rare. Only when tone genuinely needs it. Never as substitute for personality.",
        "profanity_policy": "None. The attitude makes profanity unnecessary.",
        "south_african_cues": "Light. Occasional local reference (Winelands, Paarl, Cape Town). Never braai-ad. Feels SA through place and product truth.",
    },
    "master_brand_line": "Better Begins Here.",
    "supporting_lines_verbatim": [
        "Everything has to earn its place.",
        "Fit First. Buy Second.",
        "Why It's Here.",
        "Respect the Player.",
        "This is why we stock it.",
        "Your driver is telling you something.",
        "Why this shaft? Because your current one is costing you 15 metres.",
    ],
    "cta_set": {
        "fitting": "Book a fitting",
        "product_inquiry": "Enquire",
        "fitting_entry": "Find your fit",
        "shop_actions": ["View product", "Try it on", "Visit us", "Message to order", "Ask us", "Shop the drop", "Get your spec done"],
    },
    "messaging_hierarchy": {
        "master": "STICK is where modern golfers come to get better — and everything has to earn its place.",
        "supporting": [
            "Golf without the old gatekeeping",
            "Better decisions, better golf",
            "Quality is not one-size-fits-all",
            "Modern golf is already here",
            "Style and performance belong together",
        ],
    },
    "commercial_messages": [
        {"message": "Club fitting (driver, iron, wedge, putter, shaft)", "visibility": "persistent, Mar-Nov peak"},
        {"message": "Workshop services (custom builds, loft/lie, regripping, shaft work)", "visibility": "permanent"},
        {"message": "Takomo irons / DTC brands", "visibility": "fitting-led commercial"},
        {"message": "Psycho Bunny / apparel", "visibility": "6-week campaign cycles"},
        {"message": "Bags, putters, wedges, balls", "visibility": "product drops"},
    ],
    "trust_messages": [
        "TrackMan data in every fitting — real, explainable numbers",
        "Workshop precision — Built at Stick (loft/lie, swing-weight, shaft prep)",
        "Fit First principle — match product to player, not player to product",
        "Multiple price points — Takomo, Vice alongside premium OEM. We do not push expensive by default.",
    ],
    "seasonal_campaigns": [
        {"period": "Pre-season (Jan-Mar)", "message": "Start the season fitted"},
        {"period": "Winter workshop (May-Jul)", "message": "loft/lie checks, regrips, bag refresh"},
        {"period": "Gift season (Nov-Dec)", "message": "Psycho Bunny, bags, putters as gifting"},
    ],
    "brands_stocked": ["Takomo", "Srixon", "Titleist", "Callaway", "Ping", "TaylorMade", "Mizuno", "Vice", "Psycho Bunny", "L.A.B Putters", "LA Golf", "Miura", "Avoda", "Fujimoto"],
    "proof_points": [
        "Not a traditional shop — combines fitting, coaching, workshop, retail and culture under one roof with editorial curation.",
        "Real attitude — does not ask traditional golf culture for permission.",
        "Fitting data and workshop evidence are real: TrackMan, build sheets, specs.",
        "Multiple price points — Takomo, Vice alongside premium OEM.",
        "Partners with brands traditional shops ignore (Takomo, Vice, Psycho Bunny).",
        "Physical environment deliberately modern: dark matte surfaces, wood, stone.",
        "Founding team are fitters, coaches and builders — in-house expertise.",
        "GBP generates real local interactions (1,100+ Mar-Aug 2026).",
        "Fit Fact campaigns produced leads at R20-R32 each — education model works commercially.",
    ],
    "primary_location": "Paarl, Western Cape, South Africa",
    "website": "stickgolf.co.za",
    "owners": ["Hermanus Kriel", "Dave Lamprecht"],
    "version": "September 2026 (Brand Bible Draft v3 + Campaign OS Full Brand Bible Workbook 2)",
    "visual_identity": {
        "primary_colours": ["Deep teal #004d5a", "Charcoal #1a1a1a"],
        "secondary_colours": ["Warm grey #8a8a8a", "Off-white #f5f5f0"],
        "background_colours": ["Near-black #0d0d0d", "Dark charcoal #121212"],
        "accent_colours": ["Amber / burnt orange #f0a030"],
        "primary_font": "Inter (400/600/700/900) — substitute: Plus Jakarta Sans",
        "secondary_font": "JetBrains Mono (400)",
        "card_radius": "6-8px",
        "button_radius": "4px",
        "border_style": "1px thin borders in charcoal or muted grey",
        "icon_style": "Line icons 1.5-2px stroke, rounded terminals, no filled/duotone",
        "look_feel": "Performance minimalism with attitude. Dark indoor studio. Diffused key light, controlled shadows. Product as hero. Slight desaturation.",
    },
    "recurring_properties": [
        {"id": "why-its-here", "name": "Why It's Here.", "purpose": "Explain why Stick chose to stock a product or partner brand. Editorial reason behind every priority item.", "visual_rules": "Product name lock-up + 'Why It's Here' title frame. Clean product shot. One-line reason. Use case. Stick verdict.", "min_run": "6 weeks per priority brand, 8+ executions across 3+ formats"},
        {"id": "fit-first", "name": "Fit First.", "purpose": "Demonstrate that clubs/shafts/putters are chosen through fitting, not guesswork.", "visual_rules": "Problem/baseline club first. TrackMan data overlay. Before→After comparison where possible.", "min_run": "Continuous — every performance product should have a Fit First angle available"},
        {"id": "built-at-stick", "name": "Built At Stick.", "purpose": "Show workshop precision: custom builds, loft/lie, regripping, shaft work. Turn craft into content.", "visual_rules": "Workshop detail shot. Job title overlay. Finished spec card. Before/after where visual.", "min_run": "Weekly minimum. Permanent content lane."},
        {"id": "ask-stick", "name": "Ask Stick.", "purpose": "Utility/education. One golfer question gets one clear answer. Myth-busting, doubts, buying advice.", "visual_rules": "One question headline. One answer. No filler. Product or fitting detail if relevant. Simple typography.", "min_run": "2-3x per month minimum"},
        {"id": "style-that-belongs", "name": "Style That Belongs.", "purpose": "Apparel and lifestyle. Show that style and performance belong together. Psycho Bunny.", "visual_rules": "On-golfer shot or flat lay. Fabric close-up. Outfit context. Brand + Stick lock-up.", "min_run": "6-week minimum per campaign cycle. Rotate seasonally."},
        {"id": "product-drop", "name": "Product Drop.", "purpose": "New stock or limited availability. Timely product reveal.", "visual_rules": "Fast reveal / product-first. 'Product Drop' title. Availability + message route. No generic 'new in'.", "min_run": "As stock arrives. Minimum 3 executions per drop."},
    ],
    "audience": {
        "primary": "The 'Any Golfer' — wants to improve, curious about equipment, values expertise over brand prestige, open to modern brands, sees golf as part sport/part identity/part culture.",
        "secondary": "The Culturally Curious Golfer — drawn to modern golf style, new brands, welcoming environment, less intimidating entry point.",
        "excluded": "Golfers who only care about old-school brand prestige, want the same tired pro-shop experience, equate seriousness with formality, or treat golf as a social costume.",
    },
    "internal_brand_standard": [
        "Does this help golfers get better?",
        "Does this feel like the future of golf rather than the past?",
        "Does this respect the player?",
        "Does this avoid empty golf snobbery?",
        "Does this feel sharp, confident, and credible?",
        "Does this support 'Better Begins Here'?",
    ],
    "lane_system": [
        {"lane": "product", "name": "Why It's Here", "description": "Real product features from Stick's curated catalogue. Each product earns its place on the rack."},
        {"lane": "fitting", "name": "Fit First", "description": "The fitting process + outcomes. A fitting is the start, not the sale."},
        {"lane": "coaching", "name": "Ask Stick / Better Begins Here", "description": "Coaching + education content. Questions, myth-busting, technique."},
        {"lane": "workshop", "name": "Built At Stick", "description": "Workshop events, club building, custom work, on-site experiences."},
        {"lane": "apparel", "name": "Style That Belongs", "description": "Apparel + lifestyle. How you look on the course / at the range."},
        {"lane": "commercial", "name": "Product Drop / Book / Enquire", "description": "Direct-response: drop launches, fitting bookings, retail enquiries."},
        {"lane": "human", "name": "Human / Trust", "description": "Staff, fitters, real moments. The people behind the standard."},
        {"lane": "paid", "name": "Paid Media", "description": "Boosted posts + retargeting. Always in service of one of the above lanes."},
        {"lane": "search", "name": "Search / SEO", "description": "Owned content that compounds: articles, FAQs, comparison guides."},
        {"lane": "crm", "name": "CRM / Lifecycle", "description": "Email + WhatsApp to existing customers. Repeat purchase, retention, loyalty."},
    ],
    "active_campaigns": [
        {"id": "spring-at-stick", "name": "Spring at Stick", "phase": "live", "lanes": ["apparel", "workshop", "human"]},
        {"id": "psycho-bunny-launch", "name": "Psycho Bunny Launch", "phase": "launching", "lanes": ["apparel", "product"]},
    ],
}

p = Path('/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data/brand-planning')
with open(p / 'stick.json', 'w') as f:
    json.dump(brand_planning, f, indent=2)
print(f'✓ stick.json: {p.stat().st_size:,} bytes')
print(f'  recurring_properties: {len(brand_planning["recurring_properties"])}')
print(f'  brands_stocked: {len(brand_planning["brands_stocked"])}')
print(f'  supporting_lines: {len(brand_planning["supporting_lines_verbatim"])}')

# === Updated Stick October 2026 Herman sample month ===
def h(tone, text):
    return {"tone": tone, "text": text}

items = []

# WEEK 1: Oct 5-9 (Mon-Fri)
items.extend([
    {"id": "w1-mon-product", "date": "2026-10-05", "day": "Mon",
     "lane": "product", "title": "Takomo 101T — Why It's Here",
     "subtitle": "Mallet face-balance. R7,899.",
     "stock_refs": ["takomo-101t"],
     "headline": h("confident", "Takomo earns its place on the rack."),
     "cta": "Book a fitting",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "why-its-here",
     "purpose": "Keeps real stock visible. Why It's Here editorial property."},

    {"id": "w1-mon-paid", "date": "2026-10-05", "day": "Mon",
     "lane": "paid", "title": "Fitting retargeting (week start)",
     "subtitle": "Audience: cart abandoners + page visitors",
     "headline": None, "cta": None,
     "channel": "meta_ads",
     "status": "LIVE", "is_demo": True, "is_paid_supported": True,
     "purpose": "Always-on retargeting for fitting bookings."},

    {"id": "w1-tue-product", "date": "2026-10-06", "day": "Tue",
     "lane": "product", "title": "Vice Pro Plus — Why It's Here",
     "subtitle": "Cast urethane. R549/dozen.",
     "stock_refs": ["vice-golf-ball"],
     "headline": h("confident", "Vice earns its place because the ball tells the truth."),
     "cta": "Shop the drop",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "why-its-here",
     "purpose": "Keeps retail ball stock visible."},

    {"id": "w1-tue-search", "date": "2026-10-06", "day": "Tue",
     "lane": "search", "title": "Takomo 101T — page update",
     "subtitle": "Internal link from fitting landing",
     "headline": None, "cta": None,
     "channel": "website_owned",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "purpose": "Owned-content action. Compounds SEO."},

    {"id": "w1-wed-product", "date": "2026-10-07", "day": "Wed",
     "lane": "product", "title": "Psycho Bunny Maverick Pant — Style That Belongs",
     "subtitle": "R2,199.",
     "stock_refs": ["pb-maverick-pant"],
     "headline": h("confident", "Style and performance belong together."),
     "cta": "Try it on",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "property": "style-that-belongs",
     "purpose": "Psycho Bunny launch airtime — Style That Belongs property."},

    {"id": "w1-wed-fitting", "date": "2026-10-07", "day": "Wed",
     "lane": "fitting", "title": "Iron fitting — Fit First",
     "subtitle": "TrackMan data + club build walk-through",
     "stock_refs": ["fitting-iron"],
     "headline": h("confident", "Your driver is telling you something."),
     "cta": "Find your fit",
     "channel": "instagram_reel",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "property": "fit-first",
     "purpose": "Builds demand for custom iron fitting."},

    {"id": "w1-wed-human", "date": "2026-10-07", "day": "Wed",
     "lane": "human", "title": "Jason explains shaft weight",
     "subtitle": "Why flex matters more than you think",
     "headline": None, "cta": None,
     "channel": "instagram_reel",
     "status": "NEEDS_CAPTURE", "is_demo": True, "is_paid_supported": False,
     "purpose": "Shows the real people behind Stick."},

    {"id": "w1-wed-campaign", "date": "2026-10-07", "day": "Wed",
     "lane": "campaign", "title": "Psycho Bunny launch — week 1",
     "subtitle": "Spring at Stick campaign arc",
     "headline": h("confident", "Psycho Bunny. Now at Stick."),
     "cta": "Visit us",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "purpose": "Campaign arc — Spring at Stick."},

    {"id": "w1-thu-product", "date": "2026-10-08", "day": "Thu",
     "lane": "product", "title": "Takomo Daytona — Why It's Here",
     "subtitle": "Blade. R6,899.",
     "stock_refs": ["takomo-daytona"],
     "headline": h("confident", "This is why we stock it."),
     "cta": "Enquire",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "why-its-here",
     "purpose": "Takomo putter visibility (depth editorial)."},

    {"id": "w1-thu-workshop", "date": "2026-10-08", "day": "Thu",
     "lane": "workshop", "title": "Built At Stick — workshop behind the scenes",
     "subtitle": "Loft & lie, grips, spec — what we actually do",
     "headline": None, "cta": "Get your spec done",
     "channel": "instagram_reel",
     "status": "NEEDS_CAPTURE", "is_demo": True, "is_paid_supported": False,
     "property": "built-at-stick",
     "purpose": "Proves technical capability — Built At Stick property."},

    {"id": "w1-thu-coaching", "date": "2026-10-08", "day": "Thu",
     "lane": "coaching", "title": "Ask Stick — Better Begins Here",
     "subtitle": "Swing plane: what changes when you fix it",
     "headline": h("direct", "Better decisions, better golf."),
     "cta": "Ask us",
     "channel": "instagram_reel",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "ask-stick",
     "purpose": "Shows expertise — Ask Stick utility property."},

    {"id": "w1-fri-product", "date": "2026-10-09", "day": "Fri",
     "lane": "product", "title": "Psycho Bunny Vance Polo — Style That Belongs",
     "subtitle": "R1,299.",
     "stock_refs": ["pb-vance-polo"],
     "headline": h("confident", "Polos that earn their place."),
     "cta": "Try it on",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "style-that-belongs",
     "purpose": "Psycho Bunny apparel airtime."},

    {"id": "w1-fri-commercial", "date": "2026-10-09", "day": "Fri",
     "lane": "commercial", "title": "Book a fitting — week-end push",
     "subtitle": "Direct-response CTA",
     "headline": h("direct", "Fit First. Buy Second."),
     "cta": "Book a fitting",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "purpose": "Direct-response commercial CTA."},

    {"id": "w1-fri-apparel", "date": "2026-10-09", "day": "Fri",
     "lane": "apparel", "title": "PB umbrella + cap — Style That Belongs",
     "subtitle": "R999 + R749.",
     "stock_refs": ["pb-golf-umbrella", "pb-cap"],
     "headline": None, "cta": "Try it on",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "style-that-belongs",
     "purpose": "Apparel airtime + accessory cross-sell."},

    {"id": "w1-sat-apparel", "date": "2026-10-10", "day": "Sat",
     "lane": "apparel", "title": "PB socks 3-pack — Style That Belongs",
     "subtitle": "R449.",
     "stock_refs": ["pb-socks"],
     "headline": None, "cta": "Try it on",
     "channel": "instagram_story",
     "status": "NEEDS_CAPTURE", "is_demo": True, "is_paid_supported": False,
     "property": "style-that-belongs",
     "purpose": "Apparel cross-sell at low price point."},
])

# WEEK 2 — FEATURED WEEK (Oct 12-16)
items.extend([
    {"id": "w2-mon-product", "date": "2026-10-12", "day": "Mon",
     "lane": "product", "title": "L.A.B. MEZ.1 — Why It's Here",
     "subtitle": "R11,999. Lie-angle-balanced.",
     "stock_refs": ["lab-golf-mez"],
     "headline": h("confident", "Your stroke doesn't fight this putter."),
     "cta": "Book a fitting",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "property": "why-its-here",
     "purpose": "L.A.B. putter visibility + fitting push."},

    {"id": "w2-mon-human", "date": "2026-10-12", "day": "Mon",
     "lane": "human", "title": "Inside the bay — Jason on lie-angle balance",
     "subtitle": "What changes when the lie matches your stroke",
     "headline": None, "cta": None,
     "channel": "instagram_reel",
     "status": "NEEDS_CAPTURE", "is_demo": True, "is_paid_supported": False,
     "purpose": "Human + technical credibility."},

    {"id": "w2-mon-campaign", "date": "2026-10-12", "day": "Mon",
     "lane": "campaign", "title": "Spring at Stick — Week 2 hero",
     "subtitle": "Psycho Bunny + Takomo + L.A.B. together",
     "headline": h("confident", "Three brands. One standard."),
     "cta": "Visit us",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "purpose": "Spring at Stick campaign week 2 hero."},

    {"id": "w2-mon-paid", "date": "2026-10-12", "day": "Mon",
     "lane": "paid", "title": "L.A.B. awareness — week start",
     "subtitle": "Audience: TrackMan visitors + fitting page",
     "headline": None, "cta": None,
     "channel": "meta_ads",
     "status": "LIVE", "is_demo": True, "is_paid_supported": True,
     "purpose": "L.A.B. awareness — supports L.A.B. / fitting."},

    {"id": "w2-tue-product", "date": "2026-10-13", "day": "Tue",
     "lane": "product", "title": "Psycho Bunny Maverick Pant — Style That Belongs",
     "subtitle": "R2,199.",
     "stock_refs": ["pb-maverick-pant"],
     "headline": h("confident", "Style that belongs on and off the course."),
     "cta": "Try it on",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "style-that-belongs",
     "purpose": "PB airtime — week 2 second push."},

    {"id": "w2-tue-search", "date": "2026-10-13", "day": "Tue",
     "lane": "search", "title": "Fitting landing page — L.A.B. update",
     "subtitle": "Add L.A.B. testimonials + TrackMan data",
     "headline": None, "cta": None,
     "channel": "website_owned",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "purpose": "Owned-content action — compounds traffic from paid."},

    {"id": "w2-tue-campaign", "date": "2026-10-13", "day": "Tue",
     "lane": "campaign", "title": "Spring at Stick — Reel day 2",
     "subtitle": "Behind-the-scenes: rack shot + fitting bay",
     "headline": None, "cta": None,
     "channel": "instagram_reel",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "purpose": "Campaign arc mid-week energy."},

    {"id": "w2-wed-product", "date": "2026-10-14", "day": "Wed",
     "lane": "product", "title": "Titleist Pro V1 — Why It's Here",
     "subtitle": "Cast urethane. R749/dozen.",
     "stock_refs": ["titleist-pro-v1"],
     "headline": h("confident", "Titleist earns its place because the ball is the truth."),
     "cta": "Shop the drop",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "why-its-here",
     "purpose": "Ball stock visibility."},

    {"id": "w2-wed-fitting", "date": "2026-10-14", "day": "Wed",
     "lane": "fitting", "title": "Putter fitting — Fit First",
     "subtitle": "Why your stroke needs lie-angle balance",
     "stock_refs": ["fitting-putter"],
     "headline": h("confident", "Fit First. Buy Second."),
     "cta": "Find your fit",
     "channel": "instagram_reel",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "property": "fit-first",
     "purpose": "Builds demand for putter fitting."},

    {"id": "w2-wed-human", "date": "2026-10-14", "day": "Wed",
     "lane": "human", "title": "Jason explains shaft weight",
     "subtitle": "Why flex matters more than you think",
     "headline": None, "cta": None,
     "channel": "instagram_reel",
     "status": "NEEDS_CAPTURE", "is_demo": True, "is_paid_supported": False,
     "purpose": "Human trust content."},

    {"id": "w2-wed-coaching", "date": "2026-10-14", "day": "Wed",
     "lane": "coaching", "title": "Wedge gapping — Ask Stick",
     "subtitle": "Why your yardages might have gaps",
     "stock_refs": ["fitting-wedge"],
     "headline": h("direct", "Better decisions, better golf."),
     "cta": "Ask us",
     "channel": "instagram_reel",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "ask-stick",
     "purpose": "Coaching — Ask Stick property. Connects to wedge fitting bookings."},

    {"id": "w2-wed-campaign", "date": "2026-10-14", "day": "Wed",
     "lane": "campaign", "title": "Spring at Stick — mid-week push",
     "subtitle": "Cross-category: ball + fitting + apparel",
     "headline": h("confident", "Three lanes. One machine."),
     "cta": "Visit us",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "purpose": "Campaign arc mid-week energy."},

    {"id": "w2-wed-paid", "date": "2026-10-14", "day": "Wed",
     "lane": "paid", "title": "Fitting retargeting — boost putter page",
     "subtitle": "Audience: visitors to /putter-fitting",
     "headline": None, "cta": None,
     "channel": "meta_ads",
     "status": "LIVE", "is_demo": True, "is_paid_supported": True,
     "purpose": "Always-on fitting retargeting."},

    {"id": "w2-thu-product", "date": "2026-10-15", "day": "Thu",
     "lane": "product", "title": "L.A.B. DF 2.1 — Why It's Here",
     "subtitle": "R12,999.",
     "stock_refs": ["lab-golf-df"],
     "headline": h("confident", "L.A.B. earns its place. Stroke geometry agrees."),
     "cta": "Enquire",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "why-its-here",
     "purpose": "L.A.B. depth — fitting push."},

    {"id": "w2-thu-workshop", "date": "2026-10-15", "day": "Thu",
     "lane": "workshop", "title": "Built At Stick — loft & lie session",
     "subtitle": "Workshop behind the scenes",
     "headline": None, "cta": "Get your spec done",
     "channel": "instagram_reel",
     "status": "NEEDS_CAPTURE", "is_demo": True, "is_paid_supported": False,
     "property": "built-at-stick",
     "purpose": "Workshop credibility."},

    {"id": "w2-thu-coaching", "date": "2026-10-15", "day": "Thu",
     "lane": "coaching", "title": "Attack angle — Ask Stick",
     "subtitle": "TrackMan data + practical takeaway",
     "headline": h("direct", "Your driver is telling you something."),
     "cta": "Find your fit",
     "channel": "instagram_reel",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "ask-stick",
     "purpose": "Coaching + fitting push."},

    {"id": "w2-thu-apparel", "date": "2026-10-15", "day": "Thu",
     "lane": "apparel", "title": "PB sock 3-pack — Style That Belongs",
     "subtitle": "R449.",
     "stock_refs": ["pb-socks"],
     "headline": None, "cta": "Try it on",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "style-that-belongs",
     "purpose": "Apparel cross-sell at entry price."},

    {"id": "w2-fri-product", "date": "2026-10-16", "day": "Fri",
     "lane": "product", "title": "Takomo 101T — featured (week 2)",
     "subtitle": "R7,899.",
     "stock_refs": ["takomo-101t"],
     "headline": h("confident", "Takomo earns its place. Twice in two weeks."),
     "cta": "Book a fitting",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "property": "why-its-here",
     "purpose": "Takomo 101T — second-week depth push."},

    {"id": "w2-fri-commercial", "date": "2026-10-16", "day": "Fri",
     "lane": "commercial", "title": "Book a fitting — week-end push",
     "subtitle": "Direct-response CTA",
     "headline": h("direct", "Better Begins Here."),
     "cta": "Book a fitting",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "purpose": "Direct-response commercial CTA."},

    {"id": "w2-fri-apparel", "date": "2026-10-16", "day": "Fri",
     "lane": "apparel", "title": "PB Vance Polo — second push",
     "subtitle": "R1,299.",
     "stock_refs": ["pb-vance-polo"],
     "headline": h("confident", "Polos. Style that belongs."),
     "cta": "Try it on",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "style-that-belongs",
     "purpose": "PB airtime — second push."},

    {"id": "w2-sat-campaign", "date": "2026-10-17", "day": "Sat",
     "lane": "campaign", "title": "Spring at Stick — Reel week-end",
     "subtitle": "Saturday content push",
     "headline": None, "cta": None,
     "channel": "instagram_reel",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "purpose": "Saturday campaign energy."},
])

# WEEK 3 (Oct 19-23)
items.extend([
    {"id": "w3-mon-product", "date": "2026-10-19", "day": "Mon",
     "lane": "product", "title": "Vice Pro Plus — second push",
     "subtitle": "R549/dozen.",
     "stock_refs": ["vice-golf-ball"],
     "headline": h("confident", "Vice earns its place — three pushes later."),
     "cta": "Shop the drop",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "why-its-here",
     "purpose": "Ball stock — second-week push."},

    {"id": "w3-mon-campaign", "date": "2026-10-19", "day": "Mon",
     "lane": "campaign", "title": "Spring at Stick — Week 3 hero",
     "subtitle": "Cross-category hero post",
     "headline": h("confident", "Three brands. One standard."),
     "cta": "Visit us",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "purpose": "Campaign arc week 3."},

    {"id": "w3-tue-product", "date": "2026-10-20", "day": "Tue",
     "lane": "product", "title": "PB Golf Umbrella — Style That Belongs",
     "subtitle": "R999.",
     "stock_refs": ["pb-golf-umbrella"],
     "headline": None, "cta": "Try it on",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "style-that-belongs",
     "purpose": "Apparel — weather-driven cross-sell."},

    {"id": "w3-tue-search", "date": "2026-10-20", "day": "Tue",
     "lane": "search", "title": "Takomo brand article — publish",
     "subtitle": "Why Takomo earns its place",
     "headline": None, "cta": None,
     "channel": "website_owned",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "purpose": "Owned-content action — brand article."},

    {"id": "w3-wed-product", "date": "2026-10-21", "day": "Wed",
     "lane": "product", "title": "L.A.B. MEZ.1 — second push",
     "subtitle": "R11,999.",
     "stock_refs": ["lab-golf-mez"],
     "headline": h("confident", "L.A.B. earns its place on the rack twice."),
     "cta": "Book a fitting",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "property": "why-its-here",
     "purpose": "L.A.B. — second push."},

    {"id": "w3-wed-fitting", "date": "2026-10-21", "day": "Wed",
     "lane": "fitting", "title": "Iron fitting — Fit First",
     "subtitle": "Why off-rack costs you strokes",
     "stock_refs": ["fitting-iron"],
     "headline": h("confident", "Fit First. Buy Second."),
     "cta": "Find your fit",
     "channel": "instagram_reel",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "property": "fit-first",
     "purpose": "Fitting push — second instance."},

    {"id": "w3-thu-product", "date": "2026-10-22", "day": "Thu",
     "lane": "product", "title": "Takomo Daytona — second push",
     "subtitle": "R6,899.",
     "stock_refs": ["takomo-daytona"],
     "headline": h("confident", "Daytona earns its place. Twice."),
     "cta": "Enquire",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "why-its-here",
     "purpose": "Takomo Daytona — second push."},

    {"id": "w3-thu-coaching", "date": "2026-10-22", "day": "Thu",
     "lane": "coaching", "title": "Ask Stick — Better Begins Here",
     "subtitle": "Setup: ball position changes your strike",
     "headline": h("direct", "Better Begins Here."),
     "cta": "Ask us",
     "channel": "instagram_reel",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "ask-stick",
     "purpose": "Coaching — second instance."},

    {"id": "w3-fri-product", "date": "2026-10-23", "day": "Fri",
     "lane": "product", "title": "PB Cap — Style That Belongs",
     "subtitle": "R749.",
     "stock_refs": ["pb-cap"],
     "headline": None, "cta": "Try it on",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "style-that-belongs",
     "purpose": "PB cross-sell."},

    {"id": "w3-fri-campaign", "date": "2026-10-23", "day": "Fri",
     "lane": "campaign", "title": "Spring at Stick — week-end recap",
     "subtitle": "Hero product recap Reel",
     "headline": None, "cta": None,
     "channel": "instagram_reel",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "purpose": "Campaign week 3 recap."},
])

# WEEK 4 (Oct 26-30 + 31 Sat)
items.extend([
    {"id": "w4-mon-product", "date": "2026-10-26", "day": "Mon",
     "lane": "product", "title": "Titleist Pro V1 — second push",
     "subtitle": "R749/dozen.",
     "stock_refs": ["titleist-pro-v1"],
     "headline": h("confident", "Titleist earns its place. Twice in one month."),
     "cta": "Shop the drop",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "why-its-here",
     "purpose": "Titleist — second push."},

    {"id": "w4-mon-paid", "date": "2026-10-26", "day": "Mon",
     "lane": "paid", "title": "Spring at Stick — week 4 push",
     "subtitle": "Audience: cold + warm",
     "headline": None, "cta": None,
     "channel": "meta_ads",
     "status": "LIVE", "is_demo": True, "is_paid_supported": True,
     "purpose": "Campaign boost — week 4."},

    {"id": "w4-tue-product", "date": "2026-10-27", "day": "Tue",
     "lane": "product", "title": "PB Maverick Pant — third push",
     "subtitle": "R2,199.",
     "stock_refs": ["pb-maverick-pant"],
     "headline": h("confident", "Maverick earns its place. Three pushes later."),
     "cta": "Try it on",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "style-that-belongs",
     "purpose": "PB airtime — third push."},

    {"id": "w4-wed-product", "date": "2026-10-28", "day": "Wed",
     "lane": "product", "title": "Takomo 101T — final featured (week 4)",
     "subtitle": "R7,899.",
     "stock_refs": ["takomo-101t"],
     "headline": h("confident", "101T earns its place. The standard."),
     "cta": "Book a fitting",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "property": "why-its-here",
     "purpose": "Takomo 101T — month-end featured push."},

    {"id": "w4-wed-human", "date": "2026-10-28", "day": "Wed",
     "lane": "human", "title": "Saturday fitter introduction",
     "subtitle": "Meet the team behind the standard",
     "headline": None, "cta": None,
     "channel": "instagram_reel",
     "status": "NEEDS_CAPTURE", "is_demo": True, "is_paid_supported": False,
     "purpose": "Human trust content — month-end close."},

    {"id": "w4-thu-product", "date": "2026-10-29", "day": "Thu",
     "lane": "product", "title": "PB Vance Polo — third push",
     "subtitle": "R1,299.",
     "stock_refs": ["pb-vance-polo"],
     "headline": h("confident", "Vance earns its place. Three pushes later."),
     "cta": "Try it on",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "style-that-belongs",
     "purpose": "PB airtime — third push."},

    {"id": "w4-thu-search", "date": "2026-10-29", "day": "Thu",
     "lane": "search", "title": "Fitting landing page — month-end update",
     "subtitle": "Add month testimonials",
     "headline": None, "cta": None,
     "channel": "website_owned",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "purpose": "Owned-content action — month-end SEO update."},

    {"id": "w4-fri-product", "date": "2026-10-30", "day": "Fri",
     "lane": "product", "title": "L.A.B. DF 2.1 — final featured",
     "subtitle": "R12,999.",
     "stock_refs": ["lab-golf-df"],
     "headline": h("confident", "L.A.B. earns its place. The standard."),
     "cta": "Enquire",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "property": "why-its-here",
     "purpose": "L.A.B. DF — month-end featured push."},

    {"id": "w4-fri-campaign", "date": "2026-10-30", "day": "Fri",
     "lane": "campaign", "title": "Spring at Stick — month recap",
     "subtitle": "Cross-category month recap",
     "headline": None, "cta": None,
     "channel": "instagram_reel",
     "status": "READY", "is_demo": True, "is_paid_supported": True,
     "purpose": "Campaign month-end recap."},

    {"id": "w4-sat-apparel", "date": "2026-10-31", "day": "Sat",
     "lane": "apparel", "title": "Halloween Saturday — full kit",
     "subtitle": "PB + umbrella + cap + socks",
     "stock_refs": ["pb-vance-polo", "pb-golf-umbrella", "pb-cap", "pb-socks"],
     "headline": None, "cta": "Try it on",
     "channel": "instagram_post",
     "status": "READY", "is_demo": True, "is_paid_supported": False,
     "property": "style-that-belongs",
     "purpose": "Halloween Saturday apparel cross-sell."},
])

# Build the full sample month with real brand bible content
sample_month = {
    "brand_id": "stick",
    "month": "2026-10",
    "month_name": "October 2026",
    "is_demo": True,
    "demo_label": "Brand-bible-driven demo month. Built from the real Stick Brand Bible Draft v3 + Campaign OS Brand Bible Workbook 2 (Sept 2026). Replace with real planning before pilot.",
    "source_of_truth": "data/brand-directory/stick (Brand Bible Draft v3 + Campaign OS Workbook 2)",
    "big_brand_idea": "Better Begins Here.",
    "master_brand_line": "Better Begins Here.",
    "strategic_belief": "Everything has to earn its place.",
    "brand_essence": "Better golf for a new breed of golfer.",
    "voice_summary": "Sharp, confident, direct, smart, rebellious",
    "monthly_theme": "What belongs in your bag?",
    "monthly_theme_alignment": "Reinforces the strategic belief — every club must earn its place.",
    "monthly_theme_summary": [
        "Keep retail stock consistently visible",
        "Build trust in fitting and coaching expertise",
        "Support product and service sales with clearer structure",
    ],
    "active_commercial_focuses": [
        "Psycho Bunny promotion",
        "Fitting bookings",
        "Takomo awareness",
        "L.A.B. / putter interest",
        "Apparel / in-store product visibility",
    ],
    "active_campaigns": [
        {"id": "spring-at-stick", "name": "Spring at Stick", "phase": "live",
         "lanes": ["product", "apparel", "workshop", "human"]},
        {"id": "psycho-bunny-launch", "name": "Psycho Bunny Launch", "phase": "launching",
         "lanes": ["apparel", "product"]},
    ],
    "kpi_focus_strip": [
        {"lane": "product", "status": "active"},
        {"lane": "fitting", "status": "active"},
        {"lane": "coaching", "status": "active"},
        {"lane": "human", "status": "active"},
        {"lane": "paid", "status": "active"},
    ],
    "lane_purpose_labels": {
        "product": "Keeps real stock visible and sellable",
        "fitting": "Builds demand for custom fitting",
        "coaching": "Shows expertise and makes improvement feel possible",
        "human": "Shows the real people behind Stick",
        "workshop": "Proves technical capability and detail",
        "apparel": "Keeps clothing and in-store style visible",
        "campaign": "Supports bigger seasonal or sales pushes",
        "paid": "Shows where active media support is running",
        "search": "Shows owned-content and website actions",
        "crm": "Supports follow-up and sales movement",
    },
    "properties_used": ["why-its-here", "fit-first", "built-at-stick", "ask-stick", "style-that-belongs", "product-drop"],
    "featured_week": "2026-10-12 (Week of Oct 12-16) — heaviest parallel execution",
    "items": items,
}

with open(p / 'stick-herman-sample-month.json', 'w') as f:
    json.dump(sample_month, f, indent=2)

print(f'\n✓ stick-herman-sample-month.json updated')
print(f'  total items: {len(items)}')
print('  lane counts:')
for lane, n in sorted(Counter(it['lane'] for it in items).items()):
    print(f'    {lane}: {n}')
print('  property counts:')
prop_counts = Counter(it.get('property') for it in items)
for prop, n in sorted(prop_counts.items(), key=lambda x: -(x[1] or 0)):
    if prop:
        print(f'    {prop}: {n}')

# Stock coverage
stock_used = set()
for it in items:
    for s in it.get('stock_refs') or []:
        stock_used.add(s)
print(f'  stock items used: {len(stock_used)} of 14')

# Update monthly theme in brand-planning for October
with open(p / 'stick.json') as f:
    bp = json.load(f)
bp['monthly_themes'] = [
    {
        "month": "2026-10",
        "theme": "What belongs in your bag?",
        "question": "When every club in the bag has to earn its place — what's in yours, and why?",
        "supported_bet": "Fitting + curation drive conversion; brand authority over volume.",
        "what_we_prove": "Customers trust Stick to filter what's worth carrying. We curate, we don't sell.",
        "what_changes_it": "If fitting bookings drop 30% week-on-week, or product mix shifts away from curated lineup.",
        "lanes_emphasis": ["product", "fitting", "apparel", "human", "campaign"],
        "set_at": "2026-09-07T07:50:00Z",
    }
]
with open(p / 'stick.json', 'w') as f:
    json.dump(bp, f, indent=2)
print('\n✓ stick.json monthly_themes seeded')
