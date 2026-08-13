# 📋 Bookings Tracking — Hand to Your Dev

> **One small code change. 1–2 hours of work. Moves 3 revenue channels from "we think" to "we know."**

---

## 🎯 Why this matters (TL;DR)

Right now, Campaign OS can see **how many people visit /bookings/** from Instagram, but it **cannot see how many of them actually book**. The booking confirmation page isn't telling GA4 anything.

This means: **when a post drives 11 bookings, we currently can't prove it.** We see the traffic spike, but the connection between "saw this post" → "clicked bio link" → "filled form" → "completed booking" is broken because the UTM data gets lost when the user moves between pages.

**The fix is two small snippets of JavaScript** that your dev drops into the right files. After that:
- ✅ Booking completions show up in GA4 in real-time
- ✅ We can finally prove which IG posts drive bookings (and how much revenue each brings in)
- ✅ Google / direct / ClubLab / Yoco all get clean attribution
- ✅ Campaign OS reports "VERIFIED REVENUE" instead of "STRONG PROXY" for these channels

---

## 🛠️ What needs to change

Two snippets of code. That's it.

### Change #1 — Save the UTM params when someone arrives

**Problem we're fixing:**
User clicks IG bio link with `?utm_source=instagram&utm_content=trackman-authority-961989`. Lands on /bookings/. Fills the form. Submits. **The UTM params are now lost.** The booking is attributed to `(direct)` instead of `instagram`.

**Fix:** Capture UTM params into browser sessionStorage the moment someone lands, so they survive across pages.

**Where to add it:** Your site's main header file, or in your existing Google Tag (gtag) snippet. Anywhere that runs on every page load.

**Code to paste:**

```html
<!-- Paste this RIGHT AFTER your existing gtag.js snippet -->
<script>
(function() {
  // Capture UTM params from the URL into sessionStorage on first visit.
  // Session-only (cleared when browser closes) — not localStorage.
  var params = new URLSearchParams(window.location.search);
  ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'].forEach(function(k) {
    var v = params.get(k);
    // Only set if URL has it AND we don't already have it (don't overwrite a real referrer source)
    if (v && !sessionStorage.getItem(k)) {
      sessionStorage.setItem(k, v);
    }
  });
})();
</script>
```

**What this does (in plain English):**
- User arrives with `?utm_source=instagram` in the URL → that gets saved in their browser
- User navigates to /bookings/ → URL no longer has UTM, but sessionStorage still has it
- User submits the form → we can still read the original UTM and use it in the booking event

---

### Change #2 — Tell GA4 when someone completes a booking

**Problem we're fixing:**
The Amelia booking confirmation page (the one users land on after they successfully book) doesn't tell GA4 anything happened. So GA4 has no idea a conversion occurred.

**Fix:** Fire a custom GA4 event on the confirmation page that says "a booking just happened, and here's the context."

**Where to add it:** The Amelia booking confirmation page template. Usually called something like:
- `wp-content/plugins/ameliabooking/views/frontend/booking-confirmed.blade.php`
- Or search the amelia plugin folder for files containing "Booking confirmed" or "Thank you"

**Code to paste (one option — pick whichever fits your stack):**

#### Option A: If you use Amelia's PHP filters (recommended — more reliable)

Add to your theme's `functions.php` or a custom plugin:

```php
<?php
/**
 * Fire GA4 booking_completed event after Amelia saves a booking.
 * Hooks into amelia's server-side booking-saved action.
 */
add_action('amelia_after_booking_saved', 'swing_shack_fire_booking_event', 10, 3);

function swing_shack_fire_booking_event($booking, $reservation, $context) {
    // Bail if gtag isn't available yet (rare)
    if (empty($booking) || empty($reservation)) {
        return;
    }

    // Build the value (price) from the reservation object
    $service_price = isset($reservation['price']) ? (float) $reservation['price'] : 0;
    $service_id    = isset($reservation['serviceId']) ? (string) $reservation['serviceId'] : '';
    $service_name  = isset($reservation['service']['name']) ? $reservation['service']['name'] : '';

    // Generate a unique transaction ID so this booking isn't double-counted
    $transaction_id = method_exists($booking, 'getId') ? (string) $booking->getId() : uniqid('bk_', true);

    // Read UTM from sessionStorage on the client side (handled by the JS below)
    // The PHP-side code just provides the data layer; the actual gtag call happens on the next page load
    ?>
    <script>
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({
      'event': 'booking_completed',
      'transaction_id': '<?php echo esc_js($transaction_id); ?>',
      'value': <?php echo json_encode($service_price); ?>,
      'currency': 'ZAR',
      'service_id': '<?php echo esc_js($service_id); ?>',
      'service_name': '<?php echo esc_js($service_name); ?>',
      'facility_id': '<?php echo esc_js(isset($reservation['locationId']) ? $reservation['locationId'] : ''); ?>',
      'package_redeem': <?php echo !empty($reservation['package']) ? 'true' : 'false'; ?>
    });

    // After pushing to dataLayer, fire the actual gtag event using saved UTM params
    (function() {
      var utmSource   = sessionStorage.getItem('utm_source')   || '(direct)';
      var utmMedium   = sessionStorage.getItem('utm_medium')   || '(none)';
      var utmCampaign = sessionStorage.getItem('utm_campaign') || '(none)';
      var utmContent  = sessionStorage.getItem('utm_content')  || '(none)';

      gtag('event', 'booking_completed', {
        'transaction_id': '<?php echo esc_js($transaction_id); ?>',
        'value': <?php echo json_encode($service_price); ?>,
        'currency': 'ZAR',
        'service_id': '<?php echo esc_js($service_id); ?>',
        'service_name': '<?php echo esc_js($service_name); ?>',
        'facility_id': '<?php echo esc_js(isset($reservation['locationId']) ? $reservation['locationId'] : ''); ?>',
        'package_redeem': <?php echo !empty($reservation['package']) ? 'true' : 'false'; ?>,
        'utm_source': utmSource,
        'utm_medium': utmMedium,
        'utm_campaign': utmCampaign,
        'utm_content': utmContent
      });
    })();
    </script>
    <?php
}
```

#### Option B: If Amelia's PHP hook is awkward, use plain JS on the confirmation page

Drop this into the Amelia confirmation template file directly:

```html
<script>
(function() {
  // Wait for the confirmation page to be fully rendered, then fire the event.
  // We grab the booking ID and service info from the visible page (Amelia renders them).

  // Try to read booking details from the confirmation page DOM
  var bookingIdEl    = document.querySelector('[data-booking-id], .am-booking-id');
  var serviceNameEl  = document.querySelector('.am-service-name, .am-booking-service');
  var servicePriceEl = document.querySelector('.am-service-price, .am-booking-price');

  var transactionId = bookingIdEl ? bookingIdEl.textContent.trim() : 'bk_' + Date.now();
  var serviceName   = serviceNameEl ? serviceNameEl.textContent.trim() : 'Unknown Service';
  var servicePrice  = 0;
  if (servicePriceEl) {
    var priceText = servicePriceEl.textContent.replace(/[^0-9.]/g, '');
    servicePrice = parseFloat(priceText) || 0;
  }

  // Read UTM from sessionStorage (saved by the snippet in Change #1)
  var utmSource   = sessionStorage.getItem('utm_source')   || '(direct)';
  var utmMedium   = sessionStorage.getItem('utm_medium')   || '(none)';
  var utmCampaign = sessionStorage.getItem('utm_campaign') || '(none)';
  var utmContent  = sessionStorage.getItem('utm_content')  || '(none)';

  gtag('event', 'booking_completed', {
    'transaction_id': transactionId,
    'value': servicePrice,
    'currency': 'ZAR',
    'service_name': serviceName,
    'utm_source': utmSource,
    'utm_medium': utmMedium,
    'utm_campaign': utmCampaign,
    'utm_content': utmContent
  });
})();
</script>
```

---

## ✅ Acceptance test (run after deploy)

Tell your dev to do this on staging once the code lands:

**Step 1:** Open this URL in an incognito window (so sessionStorage is empty):
```
https://swingshack.co.za/bookings/?utm_source=instagram&utm_medium=social&utm_campaign=test-tracking&utm_content=hook-acceptance-test
```

**Step 2:** Fill in the form with any test service. Complete the booking flow.

**Step 3:** Within 60 seconds, open GA4 → Reports → Realtime → Event count by Event name.

**Expected:**
- ✅ You see `booking_completed` appear
- ✅ Click the event → Event parameters show:
  - `utm_source = instagram`
  - `utm_content = hook-acceptance-test`
  - `value = <the actual service price>`

**If you see the event but UTM is `(direct)` or `(none)`:** the sessionStorage snippet didn't load. Check that Change #1 is in the right place.

**If you don't see the event at all:** check the browser console for JS errors. Most likely the gtag snippet hasn't loaded yet, or the confirmation page template path is wrong.

---

## 📁 Files involved

Your dev will probably touch 1-2 of these (most teams need only 1):

| File | Purpose |
|---|---|
| `wp-content/themes/<your-theme>/header.php` (or theme options custom JS area) | Add Change #1 (UTM stasher) |
| `wp-content/plugins/ameliabooking/views/frontend/booking-confirmed.blade.php` | Add Option B JS (confirmation page event) |
| `wp-content/themes/<your-theme>/functions.php` (or a custom plugin) | Add Option A PHP filter (server-side event) |

---

## 🔍 What happens after this ships

Once `booking_completed` events start flowing:

| Metric | Before | After |
|---|---|---|
| Booking completions we can attribute | 0 (we only see URL patterns) | Every booking has UTM + value attached |
| Revenue attribution | "We think IG drives bookings" | "Post X drove R4,500 in bookings last week" |
| Conversion truth band for IG | STRONG_PROXY | **VERIFIED_REVENUE** |
| Conversion truth band for Google | STRONG_PROXY | **VERIFIED_REVENUE** |
| Conversion truth band for Direct | STRONG_PROXY | **VERIFIED_REVENUE** |
| Weekly report LOOK_AT claim about missing `booking_completed` event | ✅ Present | ❌ Removed (problem solved) |

The CMO brain inside Campaign OS automatically picks up the new data — no other code changes needed on our side.

---

## 🆘 Common dev pitfalls (5 min fixes)

| Symptom | Cause | Fix |
|---|---|---|
| Event fires but UTM is `(direct)` | Change #1 didn't load before user landed on form | Move Change #1 higher in `<head>`, before the gtag snippet |
| Event fires multiple times per booking | dataLayer push + gtag('event') duplication | Use ONLY one method, not both |
| Event fires with wrong currency | `currency: 'ZAR'` missing | Add it (we use ZAR throughout — no USD) |
| Event fires but `value: 0` | Amelia renders price in a non-standard format | Update the regex in the JS to match your actual price HTML |
| GA4 sees the event but Custom Definitions don't | You didn't create a custom definition for `service_name` etc. | In GA4 admin → Custom definitions → create one for each new parameter |

---

## 📞 Questions?

If anything in this spec is unclear, ping Heidi with:
1. Which Amelia version is on swingshack.co.za (check `wp-content/plugins/ameliabooking/changelog.txt`)
2. Whether the confirmation page is the standard Amelia template or a custom override
3. Where your existing gtag snippet lives (theme header? GTM? plugin?)

That's enough context to unblock implementation.
