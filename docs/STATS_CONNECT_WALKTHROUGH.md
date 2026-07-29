# How to connect Meta + GA4 — so Heidi can see posts, stats, feed and interactions

**Last updated:** 2026-07-29
**Owner:** Christelle
**Backend author:** Heidi (Hermes)

---

## TL;DR — what this gives you

Once Meta is wired:

| You ask                       | I can now answer                                                |
|-------------------------------|------------------------------------------------------------------|
| "Show me our top posts this month"           | Sorted by engagement rate, with impressions, reach, saves, shares, comments |
| "Why did this post do well?"                 | Correlation with hook type, format, time, pillar, product tag |
| "What's our IG caption for the fitting offer?" | Full caption text from the published post (read-only) |
| "Show me our recent interaction patterns"    | Comments per post, save-rate, share-rate trends               |
| "Which product gets the most engagement?"    | Cross-reference with Visual DNA tags (Takomo, GTS, Vessel, etc.)|
| "What's our Facebook reach this week?"      | Page-level impressions and engagement (separate from IG)       |

GA4 adds the **website** story: which pages of swingshack.co.za people land on, where they drop off, and what converts them to book a fitting.

---

## The data model (honest version)

The Performance tab is fed by three cron-pulled sources:

```
data/truth.json  ←  written by  ←  campaign-os/truth_collector.py
                  ←              ←  (runs hourly via nightshift cron)
                  │
                  ├── source: "meta"     (Instagram + Facebook posts)
                  │   fields per record:
                  │     impressions, reach, likes, comments, shares, saved,
                  │     engagementRate, _request_id, raw.asset_id, raw.channel
                  │
                  └── source: "ga4"     (swingshack.co.za web traffic)
                      fields per record:
                        sessions, engagement_rate, path, etc.
```

`truth_collector.py` reads env-vars for credentials, calls Meta Graph API v18
and Google Analytics Data API v1, and writes engagement records into `data/truth.json`.
The SPA's Performance tab reads from `truth.json` summary.

**The single hardest problem:** `truth_collector.fetch_meta_engagement()` needs a
**per-post `platform_media_id`** — the numeric Instagram media ID (e.g.
`17990000000000001`). Without this, the function returns all-`null` fields.
Postiz **already writes this ID** back into the publishing artifact as
`platformMediaId`. So the **back-mapping problem** is mostly already solved
for any post that went through Postiz.

For posts that didn't go through Postiz (manual IG uploads), the back-map will
stay blank until we add a "force resolve by hashtag/date" pass.

---

## STEP 0 — Decide what you actually want first

| Goal                                                  | Minimum you need to give me              |
|-------------------------------------------------------|------------------------------------------|
| Read every published post + its engagement            | Meta app + long-lived user access token + IG business account ID |
| Tell me how posts rank against each other              | Same as above                            |
| See comments / interactions                           | Same as above (Graph API exposes these)  |
| Which posts are about specific products               | Same as above + back-mapped Postiz IDs   |
| See website traffic on swingshack.co.za              | GA4 service-account JSON                 |

You said yes-to-all-above. So we'll wire both Meta + GA4 in one push.

---

## STEP 1 — Create a Meta app (15 min, you do this in browser)

I'll mirror the Google Drive setup we already did. One-time, in Facebook
developer console.

### 1.1 — Go to https://developers.facebook.com/apps/

If you don't already have one (you probably do — Swing Shack is a business
account), click **Create App** → **Business** type.

### 1.2 — Add "Instagram" product to the app

Left sidebar → **Add Product** → find **Instagram** → **Set Up**.

For Facebook page access: also add **Facebook Login for Business** if not there.

### 1.3 — Required permissions (these are scopes, not roles)

In **App Review → Permissions and Features** ensure these are granted
(or testable in dev mode for your own account):

- `instagram_basic`             — read IG profile + media list
- `instagram_manage_insights`   — read media insights (impressions, reach, saves)
- `pages_show_list`             — list the FB pages you manage
- `pages_read_engagement`       — read page-level engagement
- `pages_read_user_content`     — read posts + comments on the page
- `business_management`         — required to look up the IG business account

**For dev mode:** you can grant these only to your own account + test users.
That's fine — the data is yours anyway.

### 1.4 — Get a long-lived access token

This is the part that changes most. Two paths:

**Path A — System User access token (preferred, no expiry):**

1. Business Settings → Users → System Users → Create
2. Role: Admin
3. App: pick your new app
4. Generate token with the scopes above marked "Available"
5. Token is permanent. ✓

**Path B — Long-lived user token (60-day expiry, refreshable):**

1. Graph API Explorer → pick your app → check scopes → Get Token
2. Take the short-lived token from the response → call
   `https://graph.facebook.com/v18.0/oauth/access_token?grant_type=fb_exchange_token&client_id=...&client_secret=...&fb_exchange_token=...`
3. Returns a 60-day token. Refresh every 50 days.

### 1.5 — Note down these four values

```
META_APP_ID                    = <numeric app id>
META_APP_SECRET                = <app secret (under Settings → Basic)>
META_ACCESS_TOKEN              = <token from step 1.4>
META_INSTAGRAM_BUSINESS_ACCOUNT_ID   = <numeric ig business account id>
META_PAGE_ID                   = <numeric page id (fb.com/swing_shack_jhb → "About" → Page ID)>
```

To get the **IG business account ID**:

```bash
curl -s "https://graph.facebook.com/v18.0/me/accounts?fields=instagram_business_account&access_token=$TOKEN" \
  | jq '.data[].instagram_business_account.id'
```

To get the **page ID** you already own:

```bash
curl -s "https://graph.facebook.com/v18.0/me/accounts?access_token=$TOKEN" \
  | jq '.data[] | {name, id}'
```

---

## STEP 2 — Spin up the Meta OAuth portal (I do this, 5 min)

Just like the Drive portal we already did:

1. Tell Heidi "spin up setup-portal at /meta"
2. Heidi starts setup-portal + cloudflared quick tunnel
3. You visit the URL on your phone
4. Drag-drop the four values (App ID + App Secret + Token + IG business ID + Page ID) into the form, or paste as JSON
5. Server stores them at `~/.openclaw/workspace/credentials/meta-app.json` and `meta-token.json` (chmod 600)
6. Heidi confirms by calling `meta_credentials_present()` from truth_collector

What the form looks like:

```jsonc
{
  "app_id": "123456789012345",
  "app_secret": "abcdef0123456789abcdef0123456789",
  "page_id": "987654321098765",
  "instagram_business_account_id": "17841401234567890"
}
```
Plus separately:
```
Long-lived token: EAAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx...
```

---

## STEP 3 — Verifying auth locally (Heidi does this, 1 min)

Heidi runs:

```bash
.venv/bin/python -c "
from campaign-os.truth_collector import meta_credentials_present, fetch_meta_engagement
print('present:', meta_credentials_present())
print('probe:', fetch_meta_engagement('__probe__', 'instagram', '2026-07-29T00:00:00Z', platform_media_id='17841401234567890'))
"
```

Expect:
```
present: True
probe: {'impressions': ..., 'reach': ..., 'likes': ..., ...}
```

If `present: False`, check:
- `meta-token.json` has `"access_token"` field, not just `"token"`
- All 5 env vars resolve
- Token wasn't pasted twice

If `400 Invalid OAuth access token` — token expired or wrong scopes. Re-do
step 1.4.

If `100 missing permissions` — request the missing scope in App Review.

---

## STEP 4 — Back-mapping Postiz posts → IG media IDs (Heidi does this, 30 min)

For any post that was published through Postiz, the `references.platformMediaId`
field is already populated. So the truth_collector should be able to read it.

I'll write a one-shot script:

```bash
.venv/bin/python scripts/back_map_postiz_to_ig.py
```

It walks every published post artifact in `data/postiz-published/`, extracts
the `platformMediaId`, and writes a `data/meta-post-index.json` keyed by
`asset_id → media_id`. Then `truth_collector.py` can resolve any post without
guessing.

For posts that **didn't** go through Postiz (rare, manual IG uploads), we add a
"fallback by date window" pass that lists IG media from the last 90 days and
matches by approximate publish date in `data/campaign-data.json`. This is
best-effort.

---

## STEP 5 — First real stats run (Heidi does this, 5 min)

Heidi triggers a one-shot `truth_collector.py` run with all assets:

```bash
DATA_DIR=./data .venv/bin/python -m campaign-os.truth_collector --once
```

Result lands in `data/truth.json`. Open the dashboard → Performance tab →
wait, the empty-state CTA will be **gone** and you'll see:

- IG posts counter (real number)
- Top Instagram posts card (real posts, real ER)
- SEO rising/falling (this was already populated)
- Insights strip (real patterns)

---

## STEP 6 — Hourly cron (already done, no action)

The nightshift cron (`d8ff00190932`) already runs every 60 min. It calls
`truth_collector.py` with the cron-budget cap. So once Step 5 succeeds,
**stats stay fresh automatically**. No new cron needed.

The weekly Drive scrape cron (`20fddcd1b508`) is separate and unrelated.

---

## STEP 7 — Read captions + interactions in the SPA (Heidi does this, 30 min)

Once Meta is verified, Heidi adds a new endpoint:

```
GET /api/meta/posts?limit=10
  → returns [{ id, caption, permalink, timestamp, likes, comments, ... }]

GET /api/meta/posts/<media_id>/comments
  → returns [{ id, username, text, timestamp }]

GET /api/meta/posts/<media_id>/insights
  → returns { impressions, reach, saved, shares, engagement_rate }
```

The SPA's existing top-posts card gets an expand-to-see-caption behaviour,
and a new "💬 Recent comments" card shows the latest IG comments per post.

For me (Heidi) to **read captions** — yes, I can. Once the index is built,
when you ask "show me our IG caption for the fitting offer" I'll fetch from
the same endpoint, in the same session, and quote it back to you verbatim
(not invented, not paraphrased — the actual caption text).

---

## STEP 8 — Same pattern for GA4 (parallel to Meta, 10 min)

GA4 only needs a service-account JSON, not OAuth.

1. Go to https://console.cloud.google.com/iam-admin/serviceaccounts
2. Create service account → grant "GA4 Read" role
3. Create key (JSON) → download
4. Share the GA4 property with the service-account email (Settings → Property Access Management in GA4)
5. Send Heidi the JSON via setup-portal at `/ga4`
6. Heidi runs `ga4_credentials_present()` to verify, then a probe against `/v1beta/properties/<property_id>/metadata`
7. Same cron pulls on the hour

GA4 will give you:
- `/swingshack.co.za/services/club-fitting` sessions, ER, scroll depth
- Goal conversions (form submissions, calendar clicks)
- Top landing pages by source (Instagram bio vs Google search vs direct)

---

## STEP 9 — What you'll see tomorrow morning

Open the SPA at `https://swing-shack-dashboard-production.up.railway.app` → click **Performance**:

- Stats tab is no longer empty-state
- Top-left card: real IG post count (probably 80-150)
- Top-right: GA4 sessions this month
- Middle card: top 8 posts by engagement with captions visible
- Bottom card: insights driven by the cross-reference (which hook formats ER > 3% etc.)

---

## Time budget

| Step                                       | Who     | Time   |
|--------------------------------------------|---------|--------|
| 1. Create Meta app + get token             | Christelle | 15 min |
| 2. Spin up setup-portal /meta              | Heidi   | 2 min  |
| 3. Paste JSON + token                      | Christelle | 5 min |
| 4. Verify auth                            | Heidi   | 1 min  |
| 5. Back-map Postiz posts                   | Heidi   | 30 min |
| 6. First real stats run                    | Heidi   | 5 min  |
| 7. SPA endpoints for captions/comments     | Heidi   | 30 min |
| 8. GA4 in parallel                         | both    | 20 min |
| 9. Daily view                             | Christelle | daily  |

**Total to first real stats on dashboard: ~30 min active + 30 min build.**
**Total to "show me our caption for X" working: ~90 min.**

---

## What does NOT get built

For honesty:
- I cannot read DMs (Meta doesn't expose via API for non-business apps in
  many regions)
- I cannot see Instagram Stories viewers list
- I cannot see who unfollowed
- I can read comments but not reply (the SPA won't have a reply endpoint
  by design — replies should go through IG natively)
- Historical stats before the day we connect are not retroactively filled
  beyond what Postiz + the post index can recover

For all of those: ask in the morning, and I'll tell you if I can or can't,
and why, instead of guessing.

---

## Need help now?

Just say:
- "spin up /meta portal" — I'll start Step 2
- "what's our IG caption for the latest fitting offer?" — I'll answer as
  soon as Step 5 completes. Before then, I'll honestly say "meta not
  connected yet, want me to start the dance?"
- "show me what we'd see tomorrow" — I'll render a mockup of the populated
  Performance tab so you can sign off on the layout before committing

— Heidi
