# Meta App Review — Full Submission Text for Swing Shack (Heidi app)

**App:** Heidi (App ID `2484801338654661`)
**Business:** Swing Shack — Johannesburg indoor golf + custom fitting
**Contact:** Christelle (info@stickgolf.co.za)
**Test page:** Facebook Page `198859063301219`
**Test IG business account:** `17841456713897671` (@swing_shack_ig or whatever username)

---

## How to use this document

You're looking at the Meta App Review submission screen. For each permission listed in the form, Meta asks:

1. **"How will this app use [permission]?"** — paste the matching section below
2. **Screencast upload** — see the screencast script at the bottom; one recording covers all of them
3. **"Have you performed required API test calls?"** — yes, paste the curl commands from the bottom
4. **"Agree that you will comply with allowed usage"** — tick the box

The form has **dependency chains**. If a permission says "Your submission must include X", fill X first. If a permission is "granted by default" (like `public_profile`), Meta may show only the compliance checkbox — no text needed.

---

## 🟢 REQUIRED — Fill these in this order

### 1. `public_profile` (granted by default — just tick the box)
Meta shows this as: "Agree that you will comply with allowed usage"
**Action:** tick the box. No description needed.

---

### 2. `pages_show_list` — REQUIRED FIRST (others depend on it)

**"How will this app use pages_show_list?"**
> Campaign OS uses the `pages_show_list` permission to enumerate the Facebook pages that the authenticated user manages, so the application can identify and connect to the Swing Shack business Facebook Page (Page ID 198859063301219). When a user (the Swing Shack business owner or authorised social media manager) connects their Facebook account to Campaign OS, the app calls `GET /me/accounts?fields=id,name,access_token,instagram_business_account` and renders the resulting list of pages in a dropdown selector. The user then selects which page Campaign OS should read data from. The app does NOT auto-select pages, does NOT iterate through pages the user does not own or manage, and does NOT store a list of pages beyond the single connection the user has explicitly authorised. The app only stores the page ID the user actively selected (in this case, the Swing Shack page). Read-only — the app never modifies, posts to, or deletes content on any Facebook page.

**Screencast:** the dashboard connect flow showing the page picker. See script at bottom.

---

### 3. `pages_read_engagement` (depends on `pages_show_list`)

**"How will this app use pages_read_engagement?"**
> Campaign OS reads engagement metrics (reactions, comments count, shares count, post impressions, reach) on posts published to the Swing Shack Facebook Page (Page ID 198859063301219) so the business owner can review which posts are performing well and which are not. The app calls `GET /{page-id}/posts?fields=id,message,created_time,reactions.summary(true),comments.summary(true),shares,insights.metric(post_impressions,post_reach_by_action_type)` and renders the results in a "Performance" tab inside the dashboard. Engagement data is used solely for internal performance review and content planning. The app does NOT reply to, hide, delete, or react to any post or comment. Read-only — no write operations are performed using this permission.

**Screencast:** Performance tab showing recent Swing Shack Facebook posts with engagement numbers.

---

### 4. `pages_read_user_content` (needed for IG too)

**"How will this app use pages_read_user_content?"**
> Campaign OS reads user-submitted comments on posts published to the Swing Shack Facebook Page (Page ID 198859063301219) and on the Swing Shack Instagram Business account (IG ID 17841456713897671). The app calls `GET /{post-id}/comments?fields=id,message,from,created_time,like_count` and surfaces unread or recent comments in a "Comments to review" panel in the dashboard, so the business owner can triage audience feedback, answer questions, and respond to complaints from a single interface rather than opening the native Facebook and Instagram apps separately. Comments are read-only — the app never replies to, hides, deletes, or marks comments as spam. The business owner manually replies through the native Meta apps after reviewing comments in Campaign OS.

**Screencast:** the Comments panel showing user comments on a Swing Shack IG post.

---

### 5. `instagram_basic` — CRITICAL (blocks all other IG scopes)

**"How will this app use instagram_basic?"**
> Campaign OS reads the Instagram Business Account's basic profile fields (id, username, profile_picture_url, media_count, followers_count, follows_count, biography) for the Swing Shack Instagram Business account (IG ID 17841456713897671). The app calls `GET /{ig-id}?fields=id,username,profile_picture_url,media_count,followers_count,follows_count,biography` and displays the account details in a header strip at the top of the dashboard, so the business owner can confirm at a glance that the correct account is connected and live. The data is read-only — the app never modifies the Instagram profile, never posts, never changes the bio or profile picture, and never alters any profile field. The app only reads.

**Screencast:** dashboard header showing the Swing Shack IG profile.

---

### 6. `instagram_manage_insights` (depends on `instagram_basic`)

**"How will this app use instagram_manage_insights?"**
> Campaign OS reads per-post Instagram insights (impressions, reach, saved, profile_visits, follows, likes, comments, shares, engagement rate) for posts published to the Swing Shack Instagram Business account (IG ID 17841456713897671). The app calls `GET /{ig-media-id}/insights?metric=impressions,reach,saved,profile_visits,follows,likes,comments,shares` for each post and renders the results in a sortable Performance table inside the dashboard. The data is used by the business owner to evaluate which hooks, captions, and visual styles drive engagement on each post, and to inform future content planning. The app is read-only — it never modifies posts, never deletes insights data, never alters any metric, and never uses insights data for ad targeting or retargeting.

**Screencast:** Performance table showing recent Swing Shack IG posts with per-post impressions/reach/saves.

---

### 7. `instagram_manage_comments` (depends on `instagram_basic`) — OPTIONAL

You can SKIP this one. We use `pages_read_user_content` for comments instead, which gives us the same data without a separate permission. If Meta forces you to fill it:

**"How will this app use instagram_manage_comments?"**
> Campaign OS reads user comments on Instagram media published to the Swing Shack Instagram Business account (IG ID 17841456713897671). The app calls `GET /{ig-media-id}/comments?fields=id,text,username,timestamp,like_count,replies` and surfaces comments in a review panel. The app is read-only — it never replies to, hides, deletes, or moderates comments. Business owner replies manually through the Instagram app after reviewing in Campaign OS.

---

### 8. `instagram_manage_engagement` (depends on `pages_read_user_content`) — OPTIONAL, SKIP

You don't need this — we're read-only. The current token doesn't have it and Campaign OS doesn't request it. Skip if Meta lets you.

---

### 9. `business_management` — REQUIRED (some scopes depend on it)

**"How will this app use business_management?"**
> Campaign OS uses `business_management` to read the Business Asset Group structure (Business ID 637613695233232) that connects the Swing Shack Facebook Page (198859063301219) to its linked Instagram Business account (17841456713897671). The app calls `GET /{business-id}/owned_pages` and `GET /{page-id}?fields=instagram_business_account` to resolve the IG business account from a selected FB page, so the dashboard can populate the IG-side data feeds. The app is read-only — it never modifies the Business Asset Group, never reassigns ownership, never grants or revokes roles, and never alters any business-level configuration.

**Screencast:** dashboard connect flow showing the FB page → IG business link resolving automatically.

---

### 10. `read_insights` — REQUIRED

**"How will this app use read_insights?"**
> Campaign OS reads aggregated page-level insights (page impressions, page views, page fans, page fans by country, page engagements by day) for the Swing Shack Facebook Page (Page ID 198859063301219) and the Swing Shack Instagram Business account (IG ID 17841456713897671). The app calls `GET /{page-id}/insights?metric=page_impressions,page_views,page_fans,page_engaged_users` and `GET /{ig-id}/insights?metric=reach,profile_views,follower_count,website_clicks` and renders the results in aggregate trend charts in the dashboard's "Page Insights" panel. The data is used to monitor overall audience growth and engagement trends over time. The app is read-only — it never modifies insights data and never uses insights for ad targeting.

**Screencast:** the page-level insights chart in the dashboard.

---

## 🟡 SKIP — Don't need to fill these

| Permission | Why skip |
|---|---|
| `instagram_business_basic` | Duplicate of `instagram_basic` (legacy vs newer split) |
| `instagram_business_manage_insights` | Same data as `instagram_manage_insights` — pick one |
| `instagram_business_manage_messages` | DM access — you don't need DMs |
| `instagram_content_publish` | We use Postiz to publish, not Campaign OS |
| `instagram_business_content_publish` | Same |
| `ads_read`, `ads_management` | You don't run paid ads via the API |
| `Marketing API Access Tier` | Ad campaign management only |

If Meta's UI auto-shows these as "must complete", paste this generic answer:

**Generic placeholder:**
> This permission is requested for future functionality and is not currently exercised by any production code path. The app does not currently make API calls using this permission. Requesting advanced access to align the app's requested permission set with its roadmap; the permission will be exercised only after this review is approved and the corresponding feature is enabled.

---

## 🟠 The 6 boxes at the top of the form

Before the per-permission text, Meta asks 6 setup questions. Answer each:

1. **"What data access level does your app need?"** → Standard (default for read-only analytics — do NOT pick Business if you're not a Tech Provider)
2. **"What is your app's primary category?"** → Business or Productivity (we're a marketing/ops tool)
3. **"Will your app be used by other businesses' Pages?"** → **NO** — Swing Shack is the only business using this app currently; future expansion (Stick, Bag Drop) will happen under separate apps OR under the same app with separate Page-level scopes
4. **"Provide a privacy policy URL"** → use a placeholder if you don't have one: `https://swing-shack-dashboard-production.up.railway.app/privacy`
5. **"Provide a terms of service URL"** → `https://swing-shack-dashboard-production.up.railway.app/terms`
6. **"App Icon and use case details"** → use the Heidi app icon already set; use case is "Marketing analytics for our own business"

If you don't have privacy/terms pages yet, paste this into a `privacy.html` and `terms.html` and ship them to Railway:

```html
<!-- privacy.html -->
<h1>Privacy Policy</h1>
<p>Campaign OS (the "App") accesses Facebook Page and Instagram Business account data for the sole purpose of displaying marketing analytics to the account owner. Data is not shared with third parties, not sold, and not used for advertising targeting. All data is stored on infrastructure controlled by the app owner. To request data deletion, contact info@stickgolf.co.za.</p>

<!-- terms.html -->
<h1>Terms of Service</h1>
<p>Campaign OS is provided as-is. Use at your own risk. The app accesses only data you explicitly authorise. You may revoke access at any time via Facebook Settings → Business Integrations.</p>
```

---

## 🎬 Screencast script (one 60-sec recording covers everything)

Record this in Loom or QuickTime. Total time: 60 seconds. Covers all required permissions.

```
[0:00-0:10] OPEN: swing-shack-dashboard-production.up.railway.app
            Show the dashboard loading, header strip visible.
            NARRATE: "This is Campaign OS, the marketing dashboard for Swing Shack."

[0:10-0:20] CLICK: Performance tab
            Show the FB page selector dropdown with "Swing Shack" page listed.
            NARRATE: "When the user connects their Facebook account,
            the app lists pages they manage via pages_show_list."

[0:20-0:30] SHOW: Performance table with 3-5 recent posts and engagement numbers
            NARRATE: "Here we see recent posts with engagement metrics —
            impressions, reach, likes, comments, shares — read via
            pages_read_engagement and pages_read_user_content."

[0:30-0:40] CLICK: Comments panel
            Show 2-3 user comments rendered from an IG post.
            NARRATE: "User comments on Swing Shack Instagram posts are
            surfaced here for review — read-only access, no replies sent
            through the dashboard."

[0:40-0:50] SHOW: Instagram header strip
            Show IG profile pic, username, follower count.
            NARRATE: "The Instagram business account's basic profile is
            loaded via instagram_basic, used for confirmation only."

[0:50-1:00] SHOW: Per-post IG insights chart
            NARRATE: "Per-post insights — impressions, reach, saves —
            are read via instagram_manage_insights for performance review."
```

Save the recording as `campaign-os-meta-app-review.webm` (under 100MB, 720p minimum).

---

## 🧪 API test calls (for the "Have you performed required API test calls?" checkbox)

Meta's UI sometimes asks "show me you actually called the API". Paste these as evidence in the "Notes" field:

```bash
# 1. List pages (pages_show_list)
curl "https://graph.facebook.com/v25.0/me/accounts?fields=id,name&access_token=YOUR_TOKEN"
# → returns [{ "id": "198859063301219", "name": "Swing Shack" }]

# 2. Read page engagement (pages_read_engagement)
curl "https://graph.facebook.com/v25.0/198859063301219/posts?fields=id,message,reactions.summary(true),comments.summary(true),shares&limit=5&access_token=YOUR_TOKEN"

# 3. Read page comments (pages_read_user_content)
curl "https://graph.facebook.com/v25.0/198859063301219/posts?fields=id,message,comments{text,from}&limit=2&access_token=YOUR_TOKEN"

# 4. Read IG basic profile (instagram_basic)
curl "https://graph.facebook.com/v25.0/17841456713897671?fields=id,username,media_count,followers_count&access_token=YOUR_TOKEN"

# 5. Read IG post insights (instagram_manage_insights)
curl "https://graph.facebook.com/v25.0/{ig-media-id}/insights?metric=impressions,reach,saved&access_token=YOUR_TOKEN"

# 6. Read page insights (read_insights)
curl "https://graph.facebook.com/v25.0/198859063301219/insights?metric=page_impressions,page_engaged_users&period=day&access_token=YOUR_TOKEN"

# 7. Business asset group (business_management)
curl "https://graph.facebook.com/v25.0/637613695233232/owned_pages?fields=id,name,instagram_business_account&access_token=YOUR_TOKEN"
```

Replace `YOUR_TOKEN` with the token you generated in Graph API Explorer. The calls are part of Campaign OS's actual code path — they're not fake.

---

## ✅ Submission order checklist

Click these in order. Meta's UI auto-advances when each is complete.

- [ ] `public_profile` — tick compliance box, no text needed
- [ ] `pages_show_list` — paste text, upload screencast, tick compliance
- [ ] `pages_read_engagement` — paste text, upload screencast, tick compliance
- [ ] `pages_read_user_content` — paste text, upload screencast, tick compliance
- [ ] `instagram_basic` — paste text, upload screencast, tick compliance
- [ ] `instagram_manage_insights` — paste text, upload screencast, tick compliance
- [ ] `business_management` — paste text, upload screencast, tick compliance
- [ ] `read_insights` — paste text, upload screencast, tick compliance
- [ ] Skip: `instagram_manage_comments`, `instagram_manage_engagement`, all `instagram_business_*`, `instagram_content_publish`, `ads_*`, `Marketing API Access Tier` (unless Meta forces them — use generic answer if so)
- [ ] Click **Submit for Review**

**After submit:** Meta reviews in 3-7 business days. You'll get an email and a notification in the App Review dashboard. Once approved, those scopes appear in Graph API Explorer's dropdown → re-generate token → paste into `https://yummy-nights-turn.loca.lt/meta-portal` → done.

---

## Quick reference — the one-paragraph elevator pitch

If Meta's UI has any "Tell us more about your app" or "App description" field, paste this:

> Campaign OS is a marketing analytics dashboard built and used by Swing Shack, an indoor golf and custom-fitting facility in Johannesburg, South Africa. The app reads engagement metrics, post insights, and audience comments from Swing Shack's Facebook Page (198859063301219) and Instagram Business account (17841456713897671), and surfaces them in a single internal dashboard so the business owner can evaluate content performance and plan future posts. The app is read-only — it never publishes content, never replies to comments, never modifies any page or profile setting, and never shares data with third parties. The app is operated solely by the Swing Shack business owner for the Swing Shack business; it is not offered as a commercial product to other businesses.
