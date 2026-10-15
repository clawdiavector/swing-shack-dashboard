# The Bag Drop: Brand Bible

Built from `_system/BRAND-BIBLE-TEMPLATE.md`. Part 1 (the Language Standard) and Part 3
(the Gate) live in the template and apply to The Bag Drop in full. This file is The Bag
Drop's Part 2 and Part 4.

**Written 2026-10-13 from:** the workbook's Bag Drop section, which records the owners'
"bag drop brand and sales strategy 2026 to 2028 v2" (`swing-shack/workbook-source.txt`);
the live store at `thebagdrop.co.za` (home page, refund policy, product pages and the
public product list, all read on 2026-10-13); and all 33 posts on the Instagram account
`the_bagdrop_za` (5 June to 9 August 2026), pulled on 2026-10-13 through the Graph API's
public-account lookup with no insights. The old repo files (`README.md`, `voice/`,
`copy/`, `knowledge.json`, `bible-visual.json`) were read and are treated as evidence of
what the repo believes, not as sources. Every count below was run on 2026-10-13.

**Status:** `DRAFT`. Nothing here is `CONFIRMED` unless a source is named beside it. The
approver has not signed it.

---

## Read this first: the repo describes a different business

1. **The repo's Bag Drop files describe something that is not this store.** They say Bag
   Drop is a service where members leave their golf bag at Swing Shack, runs a Thursday
   member social, is a "sub-brand of Swing Shack" whose bookings "route through Swing
   Shack", and speaks in a warm community voice. Their calls to action are `Drop your bag
   with us → swingshack.co.za` and `Member social every Thursday. Join us`. The owners'
   strategy and the live site describe an **online store for demo and pre-owned golf
   gear**, at `thebagdrop.co.za`, with national shipping, curated drops, condition grades
   and a 30-day return policy. Not one of the 33 Instagram captions mentions a Thursday,
   a member, a social, or dropping a bag. The workbook warns about a related trap: the
   domain `bagdrop.co.za` is "a Cape Town luggage storage company". Anything the system
   writes from the old files sends customers to the wrong website and talks about a
   service this store does not offer. I found no evidence that a bag-storage service
   exists. The owners should confirm that, and if one does, it needs its own name.
   `knowledge.json` records the Thursday social as "promoted from" the same README and CTA
   files, so it has no independent source.
2. **Colours and fonts have three different answers, and none of them is confirmed.** The
   repo says warm orange `#F4A261` and deep teal-navy `#264653`. The workbook says
   charcoal `#121212`, off-white, lime `#C9EF62` and amber `#F2A541`, with Inter, and says
   "not warm/fuzzy". The live site is a light page with navy and sage-green type, in
   Montserrat. Section 11.
3. **The strategy's "trust layer" is only partly in place.** Condition grades exist on 71
   of the 144 products as a dropdown (A on 53, B on 19, New on 3). The median product has
   one photo, 15 have none, and the strategy promises 4 to 6 angles for every item. The
   home page shows no Drop Alerts sign-up, and no caption mentions a sold item. Captions
   use "Demo" and "mint" as conditions, which are not on the site's scale.
4. **The feed is two months quiet and the store is not.** Last post 9 August 2026 (65
   days ago). The store changed its catalogue this morning. The account has 183 followers
   and 33 posts. Only 4 of 33 captions state a product price, while the strategy says
   "Never make the customer DM to ask", and 11 of the 16 June captions end on a version of
   "Message us for current stock".
5. **Bag Drop cannot publish on its own yet.** `data/integrations/bag-drop/instagram.json`
   says `configured: false` with no account id. The wiki records that no Postiz key
   exists for Bag Drop, so a Bag Drop post would go out through Stick's channel.

---

## Decisions needed before this can be marked CONFIRMED

| # | Decision | Recommendation | Evidence |
|---|---|---|---|
| 1 | **Replace the repo's Bag Drop identity.** Confirm no bag-storage service exists, then retire the old README, `voice/`, `copy/`, `knowledge.json` and `bible-visual.json` in favour of this bible. | Yes. Until then, do not generate Bag Drop copy from the old files. | Finding 1 above |
| 2 | **The name.** | `The Bag Drop` in full at first mention, `Bag Drop` after. `BagDrop` and `Bagdrop` only in the web address. | Workbook A: "Bag Drop". Refund policy and Instagram name: "The Bag Drop". Site title and hero: "BagDrop", "Bagdrop". Logo: "BAGDROP" |
| 3 | **The master line.** Four are in use. | Pick one. Recommendation: `Good gear doesn't need to be new.` as the belief, and the bio line `Demo clubs, used golf gear and the essentials worth carrying. Quality kit. Better value.` as the description. | Workbook B: belief "Good gear doesn't need to be new", promise "Great golf gear, ready for another round". Home page: "Club upgrades don't need to cost an arm and a leg". Workbook S asks for one line |
| 4 | **Colours, fonts and logo.** | Take the designer's files, or decide that the live site is the source of truth. Do not recolour from any table here. | Section 11 |
| 5 | **The condition scale.** | The site's `A`, `B`, `New`. Retire `Demo` and `mint` as conditions. The owners must write what A and B mean. | Site option values; feed uses `Demo`, `New`, `B`, "mint condition" |
| 6 | **Price format.** | `R6,500` in captions. The site shows `R 6,500.00`, which is a Shopify default and could be changed. | Feed: `R8 500`, `R5000`, `R7500`, `R5999`, `R500` |
| 7 | **"Second-hand".** | Retire it. Use `pre-owned` and `demo`. Allow `used` only where the site or policy already says it. | Workbook D lists "second-hand" as avoid. 8 captions use it. 0 use `pre-owned` |
| 8 | **Promoting Swing Shack and Stick.** `R500 off a fitting` is a real cross-offer. | Allowed when the approver says yes, with the offer's terms, and with the names written as `Swing Shack` and `Stick`. | 22 and 25 June, 30 July. The old README bans cross-brand mentions. The captions write `SwingShack or Stick.paarl` |
| 9 | **Offers and shipping.** | Record each offer's terms in the Proof bank before it runs. Shipping rates are not on any page. | "Free shipping until 30 July" and "Free delivery... while the specials last" |
| 10 | **Trade-ins.** | Do not mention until the owners confirm the service and its terms. | 8 August: "aggressively taking trade-ins". No page mentions it |
| 11 | **Drop Alerts.** | Do not use as a call to action until a sign-up exists. | The strategy calls it "the recurring relationship engine". No sign-up on the home page |
| 12 | **SOLD proof.** | Show it only for real sales, with the customer's consent if a person or parcel label is visible. | Strategy: "OUT THE DOOR". No captions show it |
| 13 | **Which voice.** | The first week's dry voice. Retire the August hype voice. | Section 16 |
| 14 | **Handles.** | Record `the_bagdrop_za`, the Facebook page `The Bag Drop` and TikTok `@the.bag.drop.southafrica`. | Workbook O guessed `@bagdrop` or `@thebagdrop`. Both are wrong |
| 15 | **The returns address.** | Do not print it in captions. | Section 1 |
| 16 | **Approver and who runs the account.** | Hermanus Kriel approves. Name one person for the account. | Workbook A |
| 17 | **Block auto-release for Bag Drop** until it has its own Postiz key and a configured account. | Yes | Section 17 and the wiki publish-path page |

---

## 0. Document control

| Field | Value | Status |
|---|---|---|
| Brand | The Bag Drop | CONFIRMED (workbook A, site) |
| Bible version | Template v1, Bag Drop draft 1, 2026-10-13 | DRAFT |
| Owner (writes and maintains) | Christelle (marketing) | DRAFT |
| Approver (signs changes) | Hermanus Kriel (Stick Golf Group) | CONFIRMED as brand owner (workbook A); approval role DRAFT |
| Next review | 2027-01-13, and after any rebrand | DRAFT |
| Sources | See header | CONFIRMED |

Section status: 0 to 3 DRAFT · 4 CONFIRMED (from the workbook's record of the strategy) · 5 DRAFT · 6 DRAFT · 7 mixed, row by row · 8 DRAFT · 9 DRAFT · 10 DRAFT · 11 DRAFT, nothing confirmed · 12 and 13 CONFIRMED (workbook G, H) · 14 DRAFT · 15 DRAFT · 16 CONFIRMED (counted) · 17 DRAFT.

## 1. Snapshot

| Field | Value | Status |
|---|---|---|
| Trading name | The Bag Drop | DRAFT (decision 2) |
| Website | thebagdrop.co.za (a Shopify store). **Not** bagdrop.co.za, which is an unrelated luggage storage company | CONFIRMED (workbook S; store observed 2026-10-13) |
| What it is, literally | A curated South African golf gear store: demo heads, pre-owned clubs, putters, shafts and the essentials (balls, gloves, grips, towels). "Not a marketplace; an edited drop." | CONFIRMED (workbook A, site) |
| What it is not | Not a bargain bin. Not a giant marketplace. Not Facebook Marketplace. Not a lifestyle brand. Not a bag-storage service | CONFIRMED (workbook C, G); last item see decision 1 |
| Market | South Africa, online, national shipping. Audience is national: Johannesburg, Cape Town, Pretoria, Durban | CONFIRMED (workbook B) |
| Returns address | Olivewood Estate, 50 Christo Avenue, Olivedale, Randburg, 2188. This is where returns are sent. It is not a shop to visit | CONFIRMED (refund policy). Do not publish (decision 15) |
| Email | hello@thebagdrop.co.za | CONFIRMED (refund policy, 2026-10-13) |
| Phone, WhatsApp, opening hours | | UNKNOWN. The strategy mentions WhatsApp for alerts. Nothing on the site |
| Customer actions | Shop. Enquire. Check before buying new. Join Drop Alerts | CONFIRMED (workbook A). Drop Alerts: decision 11 |
| Instagram | `the_bagdrop_za`, 183 followers, 33 posts | CONFIRMED (Graph lookup, 2026-10-13) |
| Facebook | Page "The Bag Drop" (`facebook.com/people/The-Bag-Drop/61590637170718/`) | CONFIRMED (site footer) |
| TikTok | `@the.bag.drop.southafrica`. Not a priority (workbook O) | CONFIRMED (site footer) |
| Owner | Hermanus Kriel, Stick Golf Group | CONFIRMED (workbook A) |
| Relationship to Swing Shack and Stick | Part of the same group's fitting ecosystem. Stands on its own identity (workbook S asks for the independence to be clarified) | CONFIRMED (strategy) |

## 2. Language settings

| Setting | Decision | Feed evidence | Status |
|---|---|---|---|
| Language variant (L1.1) | South African English, British spelling | All 33 captions | DRAFT |
| Serial comma (L2.7) | No | | DRAFT |
| Quotation marks | Double, curly | | DRAFT |
| Apostrophes (L2.3) | Curly | 7 captions curly, 0 straight | DRAFT |
| Exclamation marks (L2.4) | 0 in headlines. Max 1 per post | 3 of 33 captions, all in August | DRAFT |
| Em and en dashes (L2.2) | Never | 0 | CONFIRMED rule |
| Ellipsis (L2.5) | Never | 0 | CONFIRMED |
| Number style (L3.1) | Numerals for data, specs and money | | DRAFT |
| Currency (L3.2) | `R6,500`. Always the R and the comma. Never `R5000`, `R8 500` | Feed uses four formats | DRAFT (decision 6) |
| Price shown | Always, on every product post (workbook K). A price is the point of a drop | 4 of 33 captions show a price | DRAFT |
| Specs | `Loft: 11°. Condition: B. Price: R5,000.` Each on its own, with a degree sign and full stops | Feed runs them together: `Loft: 11 Condition: Demo Price: R5000` | DRAFT |
| Units (L3.3) | Metres for distance, degrees for loft | | DRAFT |
| Dates (L3.4) | `30 July`. No ordinals | | DRAFT |
| Hook maximum (L5.1) | 80 characters | Median first line not measured (captions run 10 to 44 words) | DRAFT |
| Hashtags (L5.8) | 0 to 3, last, CamelCase | 0 of 33 captions use any | DRAFT |
| Allowed hashtags | `#TheBagDrop` `#DemoGolf` `#PreOwnedGolf` `#GolfGearSA` | New | DRAFT |
| Emoji (L5.9) | Max 1, with a job: `📦` on OUT THE DOOR, `🔍` on CONDITION CHECK, `⛳` on THE DROP. A space before it | 0 in June. 13 of 13 July and 4 of 4 August captions use them, one after almost every line, and often with no space (`DM⛳️`) | DRAFT. Workbook D: "Selective and intentional... Never gratuitous" |
| Caps | Sentence case. Headlines on images: no full stop | | DRAFT |
| Sign-off (L5.7) | None | | DRAFT |
| Links in captions | `Link in bio`. Instagram captions cannot carry a live link, so a pasted `www.` address is not clickable | 6 captions paste the address, 2 say "link in bio" | DRAFT |
| Contact line | One CTA line, section 6 | | DRAFT |

## 3. Name registry

| Name | Write it as | Known wrong forms (seen in the feed or workbook) | Notes |
|---|---|---|---|
| This brand | `The Bag Drop`, then `Bag Drop` | `Bagdrop`, `BagDrop` (except in the web address), `Bag drop` | The logo and site title read "BagDrop" (decision 2) |
| Web address | `thebagdrop.co.za` | `bagdrop.co.za` (a different company), `www.thebagdrop.co.za` pasted into captions | A wrong domain is a hard fail |
| Instagram handle | `@the_bagdrop_za` | `@bagdrop`, `@thebagdrop` | |
| Sister brands | `Swing Shack`, `Stick` | `SwingShack`, `Stick.paarl` used as a name | Only with approver sign-off (decision 8) |
| Hero products | Callaway Ai Smoke (Triple Diamond, Max D), Srixon ZX 5, Mizuno (STZ, STX, STG, ST Max), TaylorMade (Qi35, Qi10, TP-Soto 1, TP-Reserve B11), Odyssey Ai-One, Ping (Anser 2D, DS72), Scotty Cameron Square Back 2, Titleist (Vokey SM 10, T250U, U505), Cleveland RTX 6, Cobra | | Copy the model name from the product page exactly. `Ai-ONE` and `Ai-One`, `Tiple` and `Triple` appear |
| Shafts and grips | MCA (Vanquish, Eldio), KBS, HZRDUS, Fujikura, Accra, GripDrip, Golf Pride, Zen Swing Grip | | Spell as the listing does |
| Other makers on the store | Titleist, Callaway, Cobra, TaylorMade, Srixon, Mizuno, Odyssey, Ping, Cleveland, FootJoy, Pure | `Taylormade` (also on the site) | Check a listing before naming a brand |
| Terms | `demo head`, `demo club`, `pre-owned`, `full club`, `head only`, `the drop`, `condition grade` | `second-hand`, `pre-loved`, `used` (except policy), `bargain` | One term per thing |
| Properties | `THE DROP`, `CONDITION CHECK`, `WHO THIS SUITS`, `OUT THE DOOR`, `SMALL WINS`, `WANTED` | | Section 8. As on-image titles, not in captions |

## 4. Strategy core

All `CONFIRMED` from the workbook's record of the strategy v2, unless noted.

- **Purpose.** To change how South African golfers think about pre-owned and demo gear, and to make "check Bag Drop before buying new" a habit, by removing the embarrassment, uncertainty and risk around second-hand equipment.
- **Core belief.** Good gear doesn't need to be new.
- **Promise.** Great golf gear, ready for another round.
- **Mental availability goal.** "Before I buy golf gear, I check Bag Drop."
- **Positioning.** A curated South African golf gear store: demo, pre-owned and useful equipment, edited for quality and value. Honest condition grading, limited-stock drops, real SOLD proof. Every product has a reason to be there.
- **Enemy.** The assumption that buying new is always right. The embarrassment around "used". The uncertainty about condition, trust and fit. The friction of Facebook Marketplace.
- **Personality.** Sharp, honest, confident, curated, clever.
- **Primary audience.** South African golfers who know what they want and do not want to pay new prices. They know brands and specs, are comfortable shopping online, and are tired of Marketplace. Equipment nerds, club hoppers, returning golfers rebuilding a bag, value-conscious serious golfers, fitters looking for demo heads, juniors on budgets.
- **Secondary.** Golfers new to the sport or returning, and gift buyers. They need more education.
- **They already know:** demo and pre-owned gear exists, the big brands are good, new clubs are expensive. Do not explain what a demo club is.
- **They worry that:** "demo" means beaten up, the condition will not match the photos, the spec will be wrong, returns will be painful, shipping will cost more than they save, "curated" means overpriced, the club will sell before they decide.
- **Never make them feel:** they are buying someone else's junk, ashamed of buying pre-owned, sold to, confused about condition, that the deal is too good to be true.
- **Commercial lanes.** Hero finds (demo drivers, woods, putters), smart upgrades (wedges, shafts, single clubs), easy first purchase (balls, gloves, grips, towels), bag builders (bundles).
- **Seasonal.** Pre-season (January to March): "New season, smart start." Winter (May to August): wedge refresh, grips, balls. Gift season (November to December): putters, balls, gloves. Year-round: a drop every week.
- **Group link.** Sits inside the Stick Golf Group's fitting ecosystem (Swing Shack fitting, Stick workshop).

## 5. Voice

### 5.1 Character

- **Voice in five words:** sharp, honest, confident, curated, clever. `CONFIRMED` (workbook D).
- **How that sounds when it works:** dry and plain. The humour is the satisfaction of a good find, never slapstick and never self-deprecating.
- **If The Bag Drop were a person:** the friend who knows exactly which shelf the good stuff is on, tells you honestly what condition it is in, and does not oversell it.
- **Point of view:** a good club does not stop being good because someone has hit it before.
- **We are, but not:**
  - honest, but not blunt: we show the wear, we do not apologise for it.
  - curated, but not precious: edited, not exclusive.
  - confident, but not loud: "Available now" over "ACT NOW".
  - dry, but not sarcastic: the reader is in on it.
  - good value, never "cheap".

### 5.2 Voice dials

| Dial | Setting | The rule that follows |
|---|---|---|
| Formality | 2 of 5 | Plain and direct. No text-speak |
| Humour | 3 of 5 | One dry line per post at most. Never about the reader's gear or money |
| Boldness | 3 of 5 | Say what it is and what it costs. No hype |
| Technicality | 3 of 5 | Loft, flex, length, condition grade, with the number set in the spec line. Light on accessories |
| Warmth | 3 of 5 | Friendly, not gushing |
| Energy | 2 of 5 | Calm. No exclamation marks. No shouting |
| Local flavour | 3 of 5 | The rand, South African places and idiom, used lightly ("priced in rand. You know what that means") |

### 5.3 Tone shifts by situation

| Situation | Tone | Length | Humour? | Example opening line (* marks an illustration, not a feed line) |
|---|---|---|---|---|
| THE DROP (new stock) | Product-first, price and condition lead | 15 to 30 words | A dry line if it earns it | `Callaway Ai Smoke Triple Diamond driver head.`* |
| CONDITION CHECK | Plain, evidence-led, show the wear | 20 to 40 words | None | `Face, sole, crown. This is the actual head.`* |
| WHO THIS SUITS | Problem first | 25 to 45 words | Yes | `The hardest club to fit in your bag is the 3-wood.` |
| SMALL WINS | Problem first, useful | 15 to 30 words | Yes | `Old balls do old-ball things.` |
| OUT THE DOOR | Short proof | 10 to 20 words | Light | `Gone. Packed. On its way to Pretoria.`* |
| WANTED | Invitation | 15 to 30 words | Light | `Looking for a driver under R5,000? Tell us.`* |
| Offer | Understated, complete | 15 to 30 words | None | What, who, until when, how |
| Bad news (out of stock, delay) | Plain, quick | 10 to 25 words | None | `That one has sold. Here is what is similar.`* |
| Reply to a question | Specific, quick | 5 to 30 words | Match theirs | Answer first, then the price, then the link |
| Reply to a complaint | Calm, specific, private | 15 to 40 words | None | `Sorry about that. Can you email hello@thebagdrop.co.za with your order number so we can sort it?`* |

### 5.4 Humour, slang and sensitive ground

- **Humour that works (from the feed and site):** "the days when the water hazard starts collecting rent" · "Old balls do old-ball things" · "No fuss. No mystery listings. No overpaying for the sake of it." · and from the refund policy: "Golf clubs do not enjoy being treated like loose biltong in a box."
- **Never:** hype ("looking absolutely lethal", "murdered-out", "Don't sleep on this one", "Grab it before it's gone!"), violent idiom, "aggressively", engagement bait ("Drop what you've got in the comments"), false scarcity.
- **Slang allowed (workbook D):** `stripe it`, `gapping`, `setup`, `drop`, `score`, `find`. **Never:** `G.O.A.T.`, `beast`, `lit`.
- **Profanity:** none.
- **Never joke about:** a customer's budget, a golfer's ability or the golfer for buying pre-owned. "Dusty gear" is borderline. Prefer "clubs you no longer swing".

## 6. Lexicon

### Signature lines

| Line | Where it goes |
|---|---|
| `Good gear doesn't need to be new.` | The belief. Education and brand posts |
| `Great golf gear, ready for another round.` | The consumer promise (strategy). Bio, site, brand pieces |
| `Already been hit. Still got it.` | Strategy line for pre-owned posts |
| `This just dropped.` | THE DROP |
| `Missed the last one? Here's the next.` | After a sold-out drop |
| `Actual item. Actual condition.` | CONDITION CHECK |
| `Shop the drop.` | Bio and CTA |

### Approved calls to action (L5.6)

One per caption. The "how" is part of the CTA.

| CTA | Use for | Status |
|---|---|---|
| `Shop the drop. Link in bio.` | THE DROP | DRAFT |
| `View the product. Link in bio.` | A single product | DRAFT |
| `Message us to order.` | One-off or limited items | DRAFT (workbook list) |
| `Tell us what you are after.` | WANTED | DRAFT |
| `Shop putters. Link in bio.` | A category (also `Shop balls. Link in bio.` and so on) | DRAFT |
| `Join Drop Alerts.` | Only once a sign-up exists | UNKNOWN (decision 11) |
| `Email hello@thebagdrop.co.za.` | Returns and order questions | CONFIRMED |

### Banned for The Bag Drop (adds to L7)

| Phrase | Why |
|---|---|
| `second-hand`, `pre-loved`, `bargain`, `steal`, `cheap`, `as-is` | Workbook D lists each as devaluing or vague |
| `Like new condition`, `mint condition` | "Prove it, don't claim it." Use a grade with evidence (workbook D) |
| `inspected`, `tested` | Process claims with no recorded process (Proof bank) |
| `DM for price`, `Message us for current stock` as the whole CTA | Hides the value. Workbook K: never make the customer ask |
| `Don't sleep on this one`, `Grab it before it's gone`, `Stock moves fast`, `Good clubs move quickly` | Hype and unproven scarcity |
| `lethal`, `murdered-out`, `stealth mode`, `aggressively` | Hype, violent idiom |
| `Score the deal of a lifetime` | Hype (workbook D) |
| `Drop what you've got in the comments` | Engagement bait |
| `One careful owner`, `non-smoker`, `always garaged`, `lady golfer` | Car-sales language, patronising (workbook D) |
| `bagdrop.co.za` | The wrong domain |
| `Thursday social`, `member social`, `drop your bag`, `Join the family` | The old repo description, not this store (decision 1) |

### Watch words (max one per caption)

`premium`, `proper`, `clean`, `serious`, `sharp`, `smart`.

### Say this, not that

| Say this | Not that | Why |
|---|---|---|
| `Callaway Ai Smoke Triple Diamond driver head. Loft: 11°. Condition: B. Price: R5,000.` (an illustration, the grade is a placeholder) | `Demo driver head Loft: 11 Condition: Demo Price: R5000` | Complete, correct, readable |
| `Condition: A. Face wear is light. Photos below.` | `Mint condition` | Evidence, not a claim |
| `Pre-owned and demo clubs.` | `Second-hand finds` | Workbook D |
| `Shop the drop. Link in bio.` | `Message us for current stock.` | Tells the reader where to go |
| `Demo heads, in stock now.` | `Stock moves fast.` | True without implying pressure |
| `R6,500` | `R 6,500.00`, `R6500`, `R 6 500` | One format |

## 7. Messaging and the Proof bank

### Master message

Bag Drop is where South African golfers check before buying new, because good gear doesn't need to be new, and a good find is worth coming back for. `CONFIRMED` (workbook E).

### Supporting messages, ranked

1. Good gear doesn't need to be new.
2. Honest condition: transparent grading, real photography, what you see is what you get.
3. Curated, not endless: someone decided every product is worth listing.
4. Stock changes: the drop gives a reason to check back. If it is gone, it is gone.
5. Connected to real golf: inside the Stick Golf Group with fitters and coaches.

### Proof bank

`CONFIRMED` rows can be used. `DRAFT` rows need a check on the day. `UNKNOWN` means silence.

| Fact (as it may be written) | Value | Source | Verified | Expires | Status |
|---|---|---|---|---|---|
| Web address | thebagdrop.co.za | Site | 2026-10-13 | never | CONFIRMED |
| Return window | 30 days after receiving the item | Refund policy | 2026-10-13 | re-check quarterly | CONFIRMED |
| Return conditions | Unused, in the condition received, with tags, packaging, headcovers and accessories. Proof of purchase. Email hello@thebagdrop.co.za first | Refund policy | 2026-10-13 | quarterly | CONFIRMED |
| Return shipping | Paid by the customer unless the item is faulty, damaged or incorrect | Refund policy | 2026-10-13 | quarterly | CONFIRMED |
| Refunds | To the original payment method within 10 business days of approval | Refund policy | 2026-10-13 | quarterly | CONFIRMED |
| Not returnable | Custom-built clubs, special orders, personalised items, installed used grips, items damaged by misuse, gift cards, clearance or final-sale items | Refund policy | 2026-10-13 | quarterly | CONFIRMED |
| Pre-owned and demo wear | "Normal wear, cosmetic marks, bag chatter, small scratches or other disclosed condition notes are not considered defects" | Refund policy | 2026-10-13 | quarterly | CONFIRMED |
| Products listed | 144 products. Condition option on 71 (A 53, B 19, New 3). True Loft and Specs on 62 | Store product list | 2026-10-13 | daily | CONFIRMED on that date. Never quote the count later |
| Price range | R90 to R9,999.99 | Store product list | 2026-10-13 | daily | CONFIRMED on that date |
| Categories | Full clubs, demo heads, demo clubs, drivers, fairway woods, hybrids, putters, wedges, shafts, grips, balls, gloves, towels | Site | 2026-10-13 | monthly | CONFIRMED |
| A specific product and price | e.g. Callaway Ai Smoke Triple Diamond driver, full club, R6,500 (home page, 2026-10-13) | Site | | per post | DRAFT. Check the listing on the day |
| Condition grades A and B | Defined as | | | | UNKNOWN. The owners must write the definitions |
| "Inspected, tested, listed in the condition we promise" | | Feed 18 Jul | | | UNKNOWN. No process is recorded |
| "Mint condition" on demo heads | | Feed 15 and 21 Jul | | | UNKNOWN. Not on the grade scale |
| Shipping rates and times | | | | | UNKNOWN. No page. "National shipping" is in the strategy |
| Free shipping until 30 July 2026 | | Feed 22 Jun | | expired | EXPIRED |
| `R500 off a fitting` at Swing Shack or Stick when you buy from The Bag Drop | | Feed 22 and 25 Jun, 30 Jul | | | UNKNOWN. No end date, limits or claim process (decision 9) |
| Trade-ins | | Feed 8 Aug | | | UNKNOWN (decision 10) |
| Drop Alerts (email or WhatsApp) | | Strategy | | | UNKNOWN (decision 11) |
| Followers and posts | 183 and 33 | Graph lookup | 2026-10-13 | daily | CONFIRMED on that date. Internal |
| Opening hours, phone | | | | | UNKNOWN |
| Performance numbers in the strategy (GA4 sessions, cost per click, landing-page views) | | Strategy | | | Internal. Never in public copy |

**Banned fabrications** (workbook H): never invent pricing, specs (loft, lie, length, flex), model names, logos, condition grades, products that do not exist, SOLD proof that has not happened, or customer testimonials.

### Offer register

| Offer | What | Who | Ends | How to claim | Approved wording | Status |
|---|---|---|---|---|---|---|
| Fitting credit | R500 off a fitting at Swing Shack or Stick when you buy from The Bag Drop | | UNKNOWN | UNKNOWN | | UNKNOWN |
| Shipping | Free delivery | | UNKNOWN (30 July was the last stated date) | | | UNKNOWN |

Offers feel understated (workbook K): "Better price" over "Bargain", "Available now" over "ACT NOW". No "was and now" theatre. Scarcity only when true: "One available", "Last one". If there are several, say "stock available".

## 8. Caption lanes

The six lanes come from the strategy (workbook J). The feed has used only the first three in any recognisable form, so lane counts are from a keyword pass over 33 captions and are approximate.

```
LANE: THE DROP
Purpose:            The recurring stock moment: preview, live, still available, gone
Anatomy:            Product line / spec line (loft, condition, price) / one dry line / CTA
Length:             15 to 30 words (the feed's four single-product posts run 23 to 28)
Hook patterns:      "[Brand model]." / "This just dropped." / "[Category], in stock now."
CTA:                Shop the drop. Link in bio.
On-image text:      DROP stamp, price lock-up, condition badge (deterministic overlay)
Cadence:            Weekly (workbook J). Primary content engine
Approved example:   See section 15, golden 3
Rejected example:   "The Mizuno STG driver head is seriously underrated..." (hype, no price)
Notes:              Price in every drop. One spec line. Never "DM for price"

LANE: CONDITION CHECK
Purpose:            Trust: actual item, actual condition
Anatomy:            Item / grade / what wear is visible / what is included / CTA
Length:             20 to 40 words
CTA:                View the product. Link in bio.
Cadence:            At least one per drop, and every listing
Notes:              Needs 4 to 6 real photos (face, sole, crown, shaft, grip). The store's median product has 1. Photography is the blocker, not the writing

LANE: WHO THIS SUITS
Purpose:            Connect one product to one golfer's problem
Anatomy:            The problem / the product / who it suits / CTA
Length:             25 to 45 words
CTA:                View the product. Link in bio.
Approved example:   7 Aug "The hardest club to fit in your bag is the 3-wood." (trim the emoji)
Cadence:            At least one per drop cycle

LANE: SMALL WINS
Purpose:            Low-friction entry: grips, balls, gloves, towels
Anatomy:            A true small problem / the fix / price / CTA
Length:             15 to 30 words
Approved example:   16 and 17 July "Old wedges cost shots", "Old balls do old-ball things"
Cadence:            Weekly. The feed already does this well

LANE: OUT THE DOOR
Purpose:            Proof that stock moves
Anatomy:            What went / "Missed it?" / CTA
Length:             10 to 20 words
CTA:                Join Drop Alerts (when it exists), or Shop similar. Link in bio.
Cadence:            Every sale that can be photographed
Notes:              The feed has none. Real sales only. Consent for any person or label shown

LANE: WANTED
Purpose:            Demand capture and sourcing
Anatomy:            "Looking for [category] under R[x]?" / how to tell us
Length:             15 to 30 words
Cadence:            Twice a month

LANE: Stock overview and category (the feed's main lane in June)
Purpose:            Say what the store sells
Notes:              16 June captions did this: "Bag Drop stocks demo clubs, second-hand clubs and useful essentials..." with "Message us for current stock". Too generic (workbook: "looks like any golf gear resale account"). Fold into THE DROP, with a product and a price

LANE: Offers (cross-offer, shipping)
Notes:              Section 7. Terms complete before it runs
```

## 9. Channel rules

Workbook L. `DRAFT`.

| Channel | Role | Formats | Length | Hashtags | CTA | Avoid |
|---|---|---|---|---|---|---|
| Instagram feed | Product showcase and trust. Home of THE DROP, CONDITION CHECK, WHO THIS SUITS | Carousel (product detail), static hero shot, Reel cross-posts | Per lane | 0 to 3 | Shop, View product, Enquire | Catalogue posts with no reason to care. Low-quality product photos |
| Instagram Stories | Fast texture: drops, SOLD alerts, polls ("What should we source?") | Stories-native | 1 to 2 lines | None | DM, Shop, Join alerts | Clutter. More than 5 slides per topic |
| Reels | Engagement and proof: condition close-ups, OUT THE DOOR, drop reveals | 9:16. Fast cuts for reveals, slow close-ups for condition | Caption per lane | 0 to 3 | Shop, View product | No branded frame. Talking head with no product. Silent with no text overlay |
| Facebook | Product drops and retargeting. Audience skews older, more purchase-ready | Feed, Reel cross-posts | Per lane | None | Shop, Message | Cross-posts with no context |
| Paid ads | Conversion engine | Product sales, category sales, retargeting, Drop Alert sign-up, SMALL WINS | Per brief | None | Shop, View product | Celebrating cheap clicks with no purchase measure. Note: Christelle's rule is that ad creative is real human video (project memory); the exception is an animated still of a retail product |
| Website | Conversion and trust destination | Product pages with grade, multi-angle photos, returns cues, Who this suits copy | Per page | n/a | Add to cart, Enquire | Pages with no condition grade, no UTM tracking, no similar items when a product sells |
| Google Business Profile | Low priority: online-first | Posts, photos of recent stock | 1 to 3 sentences | None | Visit, Call, Message | Inconsistent posting |
| TikTok | Not a priority | | | | | |

## 10. Customer conversation

- **Who replies:** UNKNOWN. Name one person.
- **Speed:** within a working day. `DRAFT`.
- **Price questions:** answer with the price and the link in the first line. Never "DM for price".
- **Condition questions:** answer with the grade, the wear and a photo. If there is no photo, say it will be added.
- **Returns and order issues:** point to hello@thebagdrop.co.za with the order number. State the 30-day policy plainly.
- **Complaints:** acknowledge, take it to email, fix it, never argue in public.
- **Escalate to the owner:** a dispute over condition, a refund refused, a legal threat, press, an injury, anything about a named person.
- **Reply examples:** section 5.3.

## 11. Visual identity

**Colours and fonts are unconfirmed and three sources disagree. Do not recolour from this table.** See `CampaignOS/decisions/everything-runs-through-brand-bibles-2026-10-12.md` in the wiki. Workbook S itself says "TO CONFIRM: colour HEX values are inferred".

| Element | Repo files say | Workbook F says | The live site shows (2026-10-13) |
|---|---|---|---|
| Primary | Warm orange `#F4A261`, deep teal-navy `#264653` | Charcoal `#121212`, off-white `#F5F3ED` | A light page. White `#FFFFFF`, a warm off-white hero. Body text sage green `#607055`. Navy headings and logo. The theme also defines navy `#002B5B`, gold `#FFD700`, cream `#F5F0D6`, burgundy `#3D000A` colour schemes, and a primary of `#253F59` |
| Accent | | Lime `#C9EF62` (sale markers), amber `#F2A541` (SOLD, CTAs) | Sage green buttons |
| Fonts | Not pinned | Inter, JetBrains Mono for grades and specs | Montserrat. Headings at weight 900, body at 400 |
| Logo | `bag-drop/logo.png` (not checked) | "Upload actual logo assets" | A "BD" mark with the wordmark "BAGDROP", in the site header, as an SVG |
| Feel | "Warm", "community", "candid member moments" | "Clean, sharp, minimal. Not warm/fuzzy" | Light, clean, uncluttered |

The strategy and the live site agree on "clean, uncluttered". They disagree on dark against light. Decision 4.

- **Layout (workbook F):** product-centred, 60 to 70% of frame. Logo top-left on feed, top-right on Stories. DROP stamp or SOLD overlay in the top or bottom third, never covering the product face. Text outside the product frame.
- **Devices (workbook F):** THE DROP stamp, a diagonal SOLD overlay, a condition grade badge, a price lock-up, an OUT THE DOOR frame (parcel, text, "Missed it? Join Drop Alerts").

## 12. Photography and imagery

`CONFIRMED` from workbook G, N and Q.

- **Look:** clean, sharp, honest. High-contrast product photography on a dark or neutral background. Lighting makes condition visible. Neutral colour temperature. No warm or golden cast. Accuracy over mood.
- **Product first.** Most content has no people. When a person appears: hands holding a club for scale, the next customer, a fitter pointing out condition. No stock-model smiles.
- **Location:** a clean photography space. Never a golf course, a country club, outdoor grass, a cluttered workshop, or fake luxury (marble, satin, gold).
- **Condition must be visible.** Face wear, sole marks and shaft rub are shown, not hidden or retouched. A graded item is never made to look better than it is.
- **Real over generated:** never render a product, a venue or a SOLD proof. The workbook's acceptance test rejects any image where the product does not match the real item, the condition is hidden, text is generated, or the background is a course.
- **Today:** 89 of 144 products have one photo and 15 have none (2026-10-13).

## 13. Product and asset fidelity

`CONFIRMED` (workbook H). Preserved exactly: model markings, sole branding, finish, cavity geometry, weighting ports, shaft graphics and flex marking, grip pattern, putter neck style, handedness, packaging, and the real wear. The model may change only the background, the lighting direction, the crop and the shadow. It may never invent specs, colours, model names, prices, logos, grades, products that do not exist, SOLD proof or testimonials.

## 14. Templates and deterministic layers

- **No measured templates exist for The Bag Drop.** There is no `templates/` folder, so `/render-post` cannot render it. `visual-spec/archetypes.json` and `palette/brand.json` exist but describe the old orange identity and should not be trusted.
- **No brand images are ingested.** The repo holds none for Bag Drop. The product photography lives in the store.
- **Needed first:** a DROP product post, a CONDITION CHECK carousel frame, a SOLD overlay and an OUT THE DOOR frame, each measured from real reference posts with `campaign-os-template`.
- Logo, price, product name, CTA and SOLD stamps are added by the deterministic layer, never typed by an image model (workbook I).
- Write copy under a template's declared limit, not at it.

## 15. Reference library

### Golden examples

Real captions, with the fixes needed to bring them into line noted.

| # | Date, lane | Caption | Why it works | Fix needed |
|---|---|---|---|---|
| 1 | 17 Jul, Small wins | `Old balls do old-ball things. / Scuffs, damaged covers and tired dimples can cost distance, spin and feel.` | A dry hook and a true, useful reason | Remove the emoji, add a price and a link |
| 2 | 16 Jul, Small wins | `Old wedges cost shots. / Fresh grooves give you more control where it matters most. / Check the current wedge stock.` | Problem first, one idea | Add a price and a link |
| 3 | 22 Jul, The Drop | `Callaway Ai Smoke Triple Diamond demo driver head. / Loft: 11 Condition: Demo Price: R5000 / Low-spin driver head.` | The right ingredients: model, loft, condition, price | Rewrite: `Callaway Ai Smoke Triple Diamond driver head. / Loft: 11°. Condition: [grade]. Price: R5,000. / Low-spin. / Shop the drop. Link in bio.` |
| 4 | 6 Jun, Category | `Running low on golf balls? / Bag Drop stocks balls for the range, the course and the days when the water hazard starts collecting rent.` | A line only a golf store could write | Add a price range and a link |
| 5 | 24 Jun, Category | `Putters are personal. / Shop putters on The Bag Drop.` | Four words of belief, one CTA | Add `Link in bio` |
| 6 | 7 Aug, Who this suits | `The hardest club to fit in your bag is the 3-wood. Buying off the rack rarely works. Stop guessing and fix your gaps with our demo fairway metals and hybrid heads.` | Problem first, specific | Trim the emoji, add a price, say "link in bio". Note: close to lines on Swing Shack's and Stick's feeds about "off the rack" (section 17) |
| 7 | Refund policy | `Golf clubs do not enjoy being treated like loose biltong in a box.` | The voice on its home page: dry, local, useful | None. It is the tone to copy |

### Rejected examples

| # | Date | Caption (shortened) | Rules broken | The fix |
|---|---|---|---|---|
| 1 | 6 Aug | `The Mizuno STG driver head is seriously underrated and packs a massive punch 💥 Maximum adjustability and pure ball speed. Don't sleep on this one. Grab it before it's gone! 🚀 Link in bio.` | Hype (L7), false scarcity (L4), emoji, no price, no condition, unverified claim | `Mizuno STG driver head. Loft: [x]°. Condition: [grade]. Price: [R]. Shop the drop. Link in bio.` |
| 2 | 8 Aug | `Still holding onto clubs you haven't swung in two years? Let's chat 💬 We are aggressively taking trade-ins ... Drop what you've got in the comments! 👇` | A service with no terms (decision 10), engagement bait, "aggressively", emoji | Do not run until trade-ins are confirmed |
| 3 | 9 Aug | `Stealth mode activated 🥷 The all-black Ping Anser 2D is looking absolutely lethal. ... murdered-out finish. Sitting in the vault ... Hit the link in our bio to make it yours!` | Violent idiom, hype, no price, no condition | `Ping Anser 2D, black finish. Condition: [grade]. Price: R5,999. Shop the drop. Link in bio.` |
| 4 | 15 Jul | `Demo head does not mean damaged 💥 These heads are inspected, checked and in mint condition before they go up for sale.` | "Mint" claim and an unrecorded process (L4.1), emoji. The hook is good | `Demo head does not mean damaged. Every head is graded A or B, with photos of the face, sole and crown.` (only if true) |
| 5 | 5 Jun | `Bag Drop stocks demo clubs, second-hand clubs and useful golf essentials at better price points. Smart gear. Better value. Ready to play. Message us to check what's available.` | `second-hand` (decision 7), no product, no price, a DM CTA, generic. It passes the swap test for any golf resale account (workbook M) | Lead with one product and its price |
| 6 | 22 Jun | `Buy from The Bag Drop and get R500 off a fitting at SwingShack or Stick.paarl / Shop now: www.thebagdrop.co.za` | Offer terms missing (L4.3), names misspelt (L1.2), a pasted address that cannot be clicked, cross-brand mention without sign-off | Section 7 offer register, then plain wording |
| 7 | 20 and 22 Jul | `Odyssey Ai-ONE Seven T putter. Condition: New Price: R8 500` · `Loft: 11 Condition: Demo Price: R5000` | Fields run together, price format (L3.2), "New" in a pre-owned store, "Demo" is not a grade, no degree sign | Section 6 say-this table |
| 8 | 30 Jul | `Specials @ Bagdrop 🏷️ Free delivery & R500 off a fitting at our partner facilities 🏌️‍♂️ Take advantage while the specials last ⛳️` | No end date or terms (L4.3), "while the specials last" is false urgency, `&` in prose, three emoji, wrong name spelling | State the offer and its end date |
| 9 | 14 Jul | `Bag Drop is live ⛳️ ... Stock moves fast. Visit the online store or DM 🏌️‍♂️` | A second "we are live" after `The Bag Drop is live` on 23 June, "moves fast" is unproven | Say what is new this week |
| 10 | 5 to 8 Jun | Eleven captions that end on `Message us for current stock` or `Message us to check what's available` | A CTA that gives no information. The strategy: "Never make the customer DM to ask" | A product, a price and a link |

## 16. Feed truth and reconciliation

Counted 2026-10-13 from `feedback/instagram-audit.json`: 33 posts (20 videos, 13 images), 5 June to 9 August 2026, 183 followers. Collected from the public account, so there are no insights (reach, saves, shares). Likes average 4.5 (maximum 13). 6 comments in total.

| Question | The strategy says | The feed shows | Decision |
|---|---|---|---|
| What the brand is | An online store for demo and pre-owned gear | Matches. No caption mentions a Thursday social, members or dropping a bag | The repo files are wrong (decision 1) |
| Voice | Sharp, honest, confident, curated, clever. Dry | The first week (5 to 8 June) is dry and plain. July adds an emoji to nearly every line. August turns to hype ("lethal", "Don't sleep on this one") | The June voice (decision 13) |
| Emoji | "Selective and intentional" | 0 in June, then 17 of 33 captions overall, almost all in July and August | Section 2 |
| Price | "Always visible. Never DM to ask" | 4 of 33 captions state a product price. 11 of 16 June captions say "Message us" | Show price on every drop |
| Condition | A/B grade with photos of face, sole, crown, shaft, grip | Captions use `Demo`, `New`, `B` and "mint". The site has A 53, B 19, New 3. Median 1 photo | Decision 5 |
| Word choice | "Pre-owned" and "demo", never "second-hand" | `second-hand` in 8 captions, `pre-owned` in 0, `demo` in 16 | Decision 7 |
| Properties | THE DROP, CONDITION CHECK, WHO THIS SUITS, OUT THE DOOR, SMALL WINS, WANTED | None is named. "Shop the drop" appears in 1 caption (23 June) and "Shop now" in 2 (22 June). No SOLD or OUT THE DOOR content | Section 8 |
| Call to action | Shop the drop, View product, Add to cart, Join Drop Alerts, Message to order | Message us (11), DM (13), Visit the online store (12), Link in bio (2), a pasted address (6) | Section 6 |
| Hashtags | | 0 of 33 | Keep to 0 to 3 |
| Scarcity | "Never create false scarcity" | "Good clubs move quickly", "Stock moves fast", "before it's gone". No SOLD proof is shown anywhere | Retire |
| Cross-promotion | Part of the group's fitting ecosystem | 3 captions offer R500 off a fitting at Swing Shack or Stick | Decision 8 |
| Contradictions inside the old files | | README: "sub-brand of Swing Shack", `knowledge.json`: "operated by swing-shack". Workbook: "Bag Drop's independence vs group branding should be clarified". `tone-rules.md`: "community-first". Workbook: "sharp". README colours: warm orange. Workbook: "not warm/fuzzy" | This bible supersedes the old files once confirmed |
| Cadence | A drop every week | 33 posts in 9 weeks, then nothing since 9 August | Decide who runs it |
| Name spelling | `Bag Drop` | `The Bag Drop` in 4 captions, `Bagdrop` in 1, `SwingShack`, `Stick.paarl` | Section 3 |

**The feed's three phases.** 5 to 8 June: eleven near-identical product-category statements, each ending "Message us". 22 to 30 June: two offers and the first videos. 14 to 30 July: videos with an emoji after almost every line, a few good problem-first captions, and the first captions with a price. 6 to 9 August: a hype voice.

## 17. Governance

- **Change process:** propose in the wiki or a pull request, the approver says yes in the current message, the change is logged below.
- **Who may publish without review:** SMALL WINS and THE DROP posts that pass the Gate with no hard fails and 12 or more of 16, where the price, the grade and every spec are `CONFIRMED` against the live listing on the day. Offers, trade-ins, cross-brand mentions and anything naming a person need approver review.
- **Publishing readiness:** the account is not configured in the repo and has no Postiz key. Until it has both, Bag Drop should be excluded from auto-release. The wiki page `publish-path-timing-and-risks-2026-10-12.md` explains why a post could otherwise go out through Stick's channel.
- **Across the three brands:** the Gate's swap test is run three ways: a competitor's name, and each sister brand's. Swing Shack and Stick already shared product copy in May to August 2026, and the Bag Drop caption "Buying off the rack rarely works" echoes lines used by both. Product lines never repeat across brands within 90 days.
- **Where this is the source of truth:** copy rules, names, facts and lanes. Where it disagrees with `README.md`, `voice/`, `copy/`, `knowledge.json` or `bible-visual.json`, this wins once confirmed, and those files should be regenerated from it.
- **Upstream sources:** the owners' strategy v2 and the live store. If they change, this file changes. The store's catalogue changes daily, so no count or price in this file is a fact tomorrow.

**Change log**

| Date | Section | Change | Approved by |
|---|---|---|---|
| 2026-10-13 | all | First draft from the template. First Bag Drop feed audit. The repo's description found to be a different business | pending |

**Open questions**

| Question | Owner | By |
|---|---|---|
| Decisions 1 to 17 at the top | Christelle, then Hermanus Kriel | |
| Does any bag-storage service exist, and where did the old description come from? | Hermanus Kriel, Kyle | |
| Colours, fonts, logo files | Christelle, designer | |
| What do condition grades A and B mean? | Owners | |
| Shipping rates, trade-ins, the R500 fitting credit, Drop Alerts | Owners | |
| Who runs the Instagram account, and when does it restart? | Christelle | |
| Photography: 4 to 6 real photos per product | Owners | |
| Phone, WhatsApp, hours | Christelle | |

---

# PART 4. MACHINE RULES

```yaml
brand: bag-drop
language: en-ZA
serial_comma: false
quotes: double-curly
apostrophe: curly
exclamation_max_per_post: 1
exclamation_max_in_headline: 0
hook_max_chars: 80
hashtags_max: 3
hashtags_camelcase: true
hashtags_allowed: [TheBagDrop, DemoGolf, PreOwnedGolf, GolfGearSA]
emoji_max_per_post: 1
emoji_allowed: ["📦", "🔍", "⛳"]
emoji_requires_space_before: true
unicode_styled_letters: forbidden
all_caps_line_max_words: 0
currency_format: "R6,500"
price_required_on_product_posts: true
spec_line_format: "Loft: {n}°. Condition: {grade}. Price: {price}."
condition_grades_allowed: [A, B, New]
unit_system: metres
date_format: "D MMMM"
signoff: ""
signoff_required: false
links_in_caption: forbidden               # use "Link in bio"
ctas_allowed:                  # "*" matches any words
  - "Shop *. Link in bio."
  - "View the product. Link in bio."
  - "Message us to order."
  - "Tell us what you are after."
  - "Email hello@thebagdrop.co.za."
cta_max: 1
banned_universal: ref:L7
banned_brand:
  - "second-hand"
  - "second hand"
  - "pre-loved"
  - "bargain"
  - "steal"
  - "cheap"
  - "as-is"
  - "like new"
  - "mint condition"
  - "inspected"
  - "tested"
  - "DM for price"
  - "Message us for current stock"
  - "Don't sleep on"
  - "Grab it before"
  - "Stock moves fast"
  - "moves quickly"
  - "lethal"
  - "murdered"
  - "stealth mode"
  - "aggressively"
  - "deal of a lifetime"
  - "careful owner"
  - "lady golfer"
  - "bagdrop.co.za"
  - "Thursday social"
  - "member social"
  - "drop your bag"
  - "Join the family"
  - "SwingShack"
  - "Stick.paarl"
watch_words_max_one: [premium, proper, clean, serious, sharp, smart]
names_exact:
  - "The Bag Drop"
  - "Bag Drop"
  - "thebagdrop.co.za"
  - "@the_bagdrop_za"
  - "Swing Shack"
  - "Stick"
names_wrong:
  - "Bagdrop"
  - "BagDrop"
  - "Bag drop"
  - "@bagdrop"
  - "@thebagdrop"
  - "Tiple"
numbers_require_proof_row: true           # any price, loft or count must match the live listing on the day
stock_claims_require_proof_row: true      # "in stock", "one available", "SOLD" need a Proof bank row
cross_brand_mention_requires_approval: true
sister_brand_line_overlap_days: 90
lanes:
  the-drop:         {min_words: 15, max_words: 30, cta_required: true,  signoff_required: false}
  condition-check:  {min_words: 20, max_words: 40, cta_required: true,  signoff_required: false}
  who-this-suits:   {min_words: 25, max_words: 45, cta_required: true,  signoff_required: false}
  small-wins:       {min_words: 15, max_words: 30, cta_required: true,  signoff_required: false}
  out-the-door:     {min_words: 10, max_words: 20, cta_required: true,  signoff_required: false}
  wanted:           {min_words: 15, max_words: 30, cta_required: true,  signoff_required: false}
```
