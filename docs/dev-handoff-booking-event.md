# Swing Shack — GA4 Booking Confirmation Event
## Developer Handoff Pack

**Prepared by:** Clawdia (Marketing AI)
**Date:** 2026-04-23
**Status:** READY FOR INSTALL
**Priority:** CRITICAL — This is the single highest-value unlock in the marketing stack.

---

## What You Are Installing

A single Google Analytics 4 event that fires when a customer successfully completes a booking on the Swing Shack website.

**Event name:** `booking_confirmation`

**Trigger:** Page view on `/book/confirmed` (or equivalent confirmation page URL)

---

## Why This Matters

Without this event, all revenue data in the marketing dashboard is estimated (sessions × 1% conversion × avg basket). With it, the system moves from "clever guesses" to "verified revenue." Every marketing decision — what to post, where to spend, which hook works — becomes accountable.

---

## Implementation

### Option A: gtag.js (Recommended — simplest)

Add to the `/book/confirmed` page, after the gtag script loads:

```html
<!-- GA4 Booking Confirmation Event -->
<script>
window.dataLayer = window.dataLayer || [];
dataLayer.push({
  'event': 'booking_confirmation',
  'service': 'FULL_BAG_FITTING',           // or: 'COACHING', 'PRACTICE', 'SOCIAL_PLAY', 'MEMBERSHIP'
  'booking_value_proxy': 1800,             // rand value — use actual price from booking
  'utm_source': '{{UTM_SOURCE}}',          // pull from URL params
  'utm_medium': '{{UTM_MEDIUM}}',          // pull from URL params
  'utm_campaign': '{{UTM_CAMPAIGN}}',      // pull from URL params
  'hook_id': '{{HOOK_ID}}',                // pull from URL params
  'recommendation_id': '{{REC_ID}}'        // pull from URL params — may be blank, OK
});
</script>
```

### Option B: Google Tag Manager (GTM)

Create a **Custom HTML Tag** trigger on the `/book/confirmed` page URL:
- Tag type: Custom HTML
- Trigger: Page View on `/book/confirmed`
- Code: paste the script above

Create **URL variables** for each UTM parameter:
- Variable name: `UTM Source` → URL → Component → Query → `utm_source`
- Repeat for: `utm_medium`, `utm_campaign`, `utm_content` (hook_id), `utm_term` (recommendation_id)

---

## Parameter Reference

| Parameter | Type | Required | Source | Notes |
|-----------|------|----------|--------|-------|
| `event` | string | **Yes** | Fixed | Must be exactly `booking_confirmation` |
| `service` | string | **Yes** | Booking form | Values: `FULL_BAG_FITTING`, `IRON_FITTING`, `DRIVER_FITTING`, `PUTTER_FITTING`, `WEDGE_FITTING`, `TPI_ASSESSMENT`, `COACHING`, `BIRDIE_HUNTER`, `I_AM_GOLF`, `PRACTICE`, `SOCIAL_PLAY`, `MEMBERSHIP`, `SOCIAL_PLAY_2PLAYERS`, `SOCIAL_PLAY_3_4PLAYERS` |
| `booking_value_proxy` | integer | **Yes** | Booking form | Rand value of the booking. Use actual price. |
| `utm_source` | string | Yes | URL param | e.g. `instagram`, `google`, `facebook` |
| `utm_medium` | string | Yes | URL param | e.g. `social`, `organic`, `cpc` |
| `utm_campaign` | string | No | URL param | e.g. `fitting-full-bag`, `coaching-lessons` |
| `hook_id` | string | No | URL param | Marketing hook identifier. May be blank. |
| `recommendation_id` | string | No | URL param | Recommendation that drove the booking. May be blank. |

---

## Getting UTM Parameters from the URL

In JavaScript on the confirmation page:

```javascript
function getUrlParam(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name) || '';
}

const service = getUrlParam('service');         // e.g. 'FULL_BAG_FITTING'
const utmSource = getUrlParam('utm_source');   // e.g. 'instagram'
const utmMedium = getUrlParam('utm_medium');   // e.g. 'social'
const utmCampaign = getUrlParam('utm_campaign'); // e.g. 'fitting-full-bag'
const hookId = getUrlParam('utm_content');      // e.g. 'hook-a'
const recId = getUrlParam('utm_term');          // may be blank
```

**Note:** The UTM parameters must already be in the URL when the customer lands on `/book/confirmed`. This means the booking page must pass them through from the landing page. If they are not in the URL, leave them blank — blank is OK.

---

## Confirmation URL Format

The `/book/confirmed` page URL should look like:

```
https://swingshack.co.za/book/confirmed?service=FULL_BAG_FITTING&booking_value=1800&utm_source=instagram&utm_medium=social&utm_campaign=fitting-full-bag&utm_content=hook-a
```

Or with Meta parameters:

```
https://swingshack.co.za/book/confirmed?service=COACHING&booking_value=850&utm_source=instagram&utm_medium=social&utm_campaign=coaching-lessons
```

---

## QA Checklist

After install, verify each of these:

- [ ] Event `booking_confirmation` appears in GA4 DebugView when you complete a test booking
- [ ] `service` parameter is populated (not blank) in the event
- [ ] `booking_value_proxy` is populated with a number (not 0 or blank)
- [ ] `utm_source` is populated (if the customer clicked a tracked link)
- [ ] `utm_medium` is populated
- [ ] `utm_campaign` is populated (may be blank if organic)
- [ ] `hook_id` is populated or blank (both are acceptable)
- [ ] `recommendation_id` is populated or blank (both are acceptable)
- [ ] Event appears under Events in GA4 Realtime dashboard
- [ ] Event appears in GA4 Reports → Engagement → Events (within 24-48h)

---

## Test URL

To test manually:

1. Clear GA4 cookies/local storage
2. Visit: `https://swingshack.co.za/?utm_source=test&utm_medium=social&utm_campaign=qa-test&utm_content=hook-test`
3. Navigate through booking flow to `/book/confirmed`
4. Check GA4 DebugView — `booking_confirmation` should appear within seconds

---

## Fallback Behaviour

If some parameters are blank:
- **service** — if blank, set to `'UNKNOWN'`
- **booking_value_proxy** — if blank, set to `0` (still fire the event)
- **UTM params** — if blank, leave as empty string `''` — do not omit the field
- **hook_id** — if blank, set to `'none'`
- **recommendation_id** — if blank, set to `'none'`

**The event must fire regardless of which params are present.** A partial event is better than no event.

---

## What Happens When This Is Live

When `booking_confirmation` fires correctly:
1. GA4 begins recording actual booking conversions
2. Marketing dashboard upgrades from MODELLED revenue to VERIFIED REVENUE
3. UTM data links posts to actual sessions and bookings
4. Hook-level attribution becomes possible (which hook drove the booking)
5. Service-level ROI becomes measurable

---

## Who to Contact

**Technical contact:** Swing Shack developer
**Marketing system:** Clawdia (AI agent managing the marketing dashboard)
**Dashboard:** `swing-shack-dashboard/index.html` (auto-updates from GA4)

---

*This pack was generated by Clawdia — Marketing AI for Swing Shack*
