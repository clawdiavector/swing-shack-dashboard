# Booking Confirmation GA4 Event Wire — Spec for Dev

**Why this matters:** This single 1-2h code change upgrades 3 revenue channels from `STRONG_PROXY` to `VERIFIED_REVENUE` in the conversion truth band. That's the difference between "we think posting on Instagram drives bookings" and "we **know** post X drove Y booking worth Z".

**Current state (verified 2026-08-13):**
- 0 GA4 events for `booking_completed`, `service_selected`, or `booking_value_proxy`
- `amelia_customer_form_view` fires (4 in 30d) but is incomplete coverage
- `amelia_checkout_view` fires (1 in 30d) — but only the checkout, not the actual booking completion
- 58 booking-completion-proxy sessions detected via URL pattern `/bookings/?facilityId=&serviceId=&clientEmail=&packageRedeem=`

**Target state:**
- GA4 event `booking_completed` fires on the Amelia confirmation page after payment/booking slot reserved
- Event includes value + currency + service + UTM attribution
- Wire validates end-to-end: see the event in GA4 realtime within 60 seconds of a test booking

---

## What to instrument

### 1. The event: `booking_completed`

**Where:** The Amelia booking plugin's confirmation page — the page the user lands on after they successfully book a slot (or pay). In WordPress this is typically `wp-content/plugins/ameliabooking/src/Application/Services/Booking/BookingApplicationService.php` or a JavaScript hook.

**When:** Fire on the client-side `DOMContentLoaded` of the confirmation page, AND also on the server-side Amelia hook `amelia_after_booking_saved` for redundancy.

**Payload:**
```javascript
gtag('event', 'booking_completed', {
  // Transaction identification
  transaction_id: '<booking_uid_or_payment_id>',  // unique per booking
  value: <service_price_in_ZAR>,                    // numeric, e.g. 450
  currency: 'ZAR',
  // Service details
  service_id: '<serviceId_from_url_or_response>',   // e.g. '1' for golf lesson
  service_name: '<human readable service>',          // e.g. '30-min Golf Lesson'
  // Customer context (anonymous, not PII)
  facility_id: '<facilityId>',
  package_redeem: <true_or_false>,                  // whether it's a package use
  // Attribution - critical for joining to IG posts
  utm_source: '<from_session_storage_or_cookie>',
  utm_medium: '<from_session_storage_or_cookie>',
  utm_campaign: '<from_session_storage_or_cookie>',
  utm_content: '<from_session_storage_or_cookie>',   // this is the IG post hook_id
});
```

### 2. Stash UTM params in sessionStorage on first visit

The current bug (per `data/ga4-attribution.json`): 45 sessions from IG bio → `/bookings/` but **0 of them show IG as the source for the actual booking completion**. The user clicks the IG bio link, lands on /bookings/, fills the form, and submits — but by the time the form submits, the original UTM params are gone. The booking confirmation gets attributed to `(direct)` instead of `instagram`.

**Fix:** On every page load, capture UTM params into sessionStorage (not localStorage — sessions should clear):

```javascript
// Add to site-wide header (gtag snippet or custom JS)
(function() {
  var params = new URLSearchParams(window.location.search);
  ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content'].forEach(function(k) {
    var v = params.get(k);
    if (v && !sessionStorage.getItem(k)) {
      sessionStorage.setItem(k, v);
    }
  });
})();
```

Then read those values on the confirmation page when firing the event.

### 3. The `service_selected` event (nice-to-have, lower priority)

Fires when the user picks a service type on the form (e.g. "30-min Lesson" vs "60-min Lesson"). Currently no event tracked. Adding this would upgrade the ROI band on WEAK_PROXY channels to VERIFIED_LEAD.

```javascript
gtag('event', 'service_selected', {
  service_id: '<id>',
  service_name: '<name>',
  service_price: <number>,
});
```

---

## Acceptance test

Once the code lands on staging:

1. Open the IG bio link (or any URL with `?utm_source=instagram&utm_content=test-hook`)
2. Navigate to /bookings/
3. Fill the form with a test service
4. Submit and complete the booking flow
5. Within 60 seconds, in GA4 Realtime, confirm:
   - `booking_completed` event appears
   - `utm_source = instagram`
   - `utm_content = test-hook`
   - `value` matches the service price

---

## Files involved (likely)

- `wp-content/plugins/ameliabooking/views/frontend/booking-confirmed.blade.php` (or equivalent) — add the gtag call
- `wp-content/themes/<your-theme>/header.php` or theme options — add the UTM sessionStorage stasher
- `wp-content/plugins/ameliabooking/src/Application/Services/Booking/BookingApplicationService.php` — server-side hook for redundancy

---

## After this lands

The `weekly_report` will automatically pick it up:

1. `fetch_ga4_attribution.py` runs (already wired into the daily path)
2. `booking_completion_proxy_sessions` drops from 58 to ~0 (real `booking_completed` event replaces the URL-pattern proxy)
3. `completions_by_source` will start showing IG, Google, etc. as booking sources
4. Conversion truth band: 3 channels upgrade from STRONG_PROXY to VERIFIED_REVENUE
5. The LOOK_AT claim about missing `booking_completed` event disappears
