# Google Business drafts for review (2026-10-15)

Six written drafts for you to approve. Nothing here goes live. Each one goes into the GBP page (Publish → Google Business Profile → Drafts), where you press **Approve**. Only approved drafts reach the daily plan.

Each draft passes the same checks the Approve button runs: body present, link on the brand's own site, photo attached, and the text gate (no em dashes, no invented numbers, no wrong place names, no other brands' names).

## Stick (3 drafts, pass the checks)

Photo for all three: a real Stick photo of iron sets, `stick/images/Location/Photos of iron sets/` (DJI, 5 Oct 2026). Please pick the one you want and upload it through the app, because the photo has to be reachable from the live site to be posted.

### 1. Iron fitting in Paarl
- **Body:** Irons should be fitted before you buy them. We run TrackMan fittings on any brand, then match the shaft and head to what your swing is doing. Book a fitting and see the numbers. Better begins here.
- **CTA:** Book a fitting
- **Link:** https://stickgolf.co.za/bookings/

### 2. Fit first. Buy second.
- **Body:** Fit first. Buy second. That is how we run the shop in Paarl. Come in for a fitting before you spend on new gear, and we will tell you plainly what you need. Better begins here.
- **CTA:** Book a fitting
- **Link:** https://stickgolf.co.za/bookings/

### 3. Bring the questions you are embarrassed to ask
- **Body:** Bring the question you are embarrassed to ask. We answer it plainly, with the numbers where they help. Nobody should leave the studio feeling stupid. Better begins here.
- **CTA:** Book a session
- **Link:** https://stickgolf.co.za/bookings/

## Swing Shack (3 drafts, blocked until each has a photo)

No real Swing Shack photo is in the repo. The `oneshots` images look generated (`spoon-v1…` names), so I did not use them. Each draft shows `photo_missing` until you attach one of the club's own photos.

### 4. Real golf, indoors
- **Body:** South Africa's first and only true indoor golf club. Four TrackMan bays and a Zen Swing Stage, at Old Parktonian Sports Club in Bordeaux, Randburg.
- **CTA:** Book now
- **Link:** https://swingshack.co.za/bookings/

### 5. The ball speaks
- **Body:** The ball speaks. Data confirms. Feel seals the deal. Book a fitting at Swing Shack and see the numbers before you buy.
- **CTA:** Book a fitting
- **Link:** https://swingshack.co.za/bookings/

### 6. Membership at Swing Shack
- **Body:** Members get 4 free practice sessions a month, 25% off fittings and 15% off lessons. Have a look at the membership options on the bookings page.
- **CTA:** See membership
- **Link:** https://swingshack.co.za/bookings/

## Facts used

Every claim above comes from `knowledge.json` → `verified_facts` for each brand: the Stick fitting service, the Swing Shack setup (four bays, Zen Swing Stage), the venue address, the membership benefits and the brand promise. The three Stick drafts close with "Better begins here.", which the Stick feed uses on most captions. It is not in the brand bible, so it is worth confirming you want it here.

## Open before any of this goes live

- **Photos must be reachable from the live site.** A local file path only works on this machine. The publish step fails safely with `image_upload_failed` rather than posting text alone.
- **Swing Shack needs a Postiz GBP channel.** As of the 9 Oct audit, Swing Shack had none, so its Approve on Today cannot publish yet.
- **Test the live path once** on a single approved draft before turning on the daily job.
