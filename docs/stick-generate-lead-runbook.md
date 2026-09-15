# STICK `generate_lead` TRACKING — OPERATOR RUNBOOK (Step 3C)

**Goal:** add one trustworthy primary website conversion
(generate_lead) without breaking the live /bookings/, /club-fitting-at-stick/,
/coaching-at-stick/ forms.

**Status:** JS snippet + data-attribute mapping ready. Operator
must perform 4 manual steps.

---

## A. INSTALL THE JS SNIPPET

**File location in our repo:**

```
campaign-os/docs/stick-generate-lead-snippet.js
```

**What it does:**

- Listens for Contact Form 7's `wpcf7mailsent` DOM CustomEvent
  (the canonical CF7 success notification; fires ONLY after CF7
  has confirmed the email was sent).
- Reads `data-stick-lead-type`, `data-stick-cta-location`,
  `data-stick-service` from the form element (or
  `data-lead-type` / `data-cta-location` / `data-service` as
  fallbacks).
- Calls `gtag('event', 'generate_lead', { lead_type, cta_location,
  service?, form_id })` on success.
- Does NOTHING on validation failure, network error, abandoned
  form, or submit-button click.
- Sends ZERO PII (does not read name/email/phone/text inputs).

**Where to install it (pick ONE of these options):**

The cleanest option is the **Contact Form 7 integration hook**:

```php
// In the TheGem child-theme functions.php (or a small mu-plugin)

add_action('wp_enqueue_scripts', function () {
    if (is_page(['bookings', 'club-fitting-at-stick', 'coaching-at-stick'])) {
        wp_enqueue_script(
            'stick-generate-lead',
            get_stylesheet_directory_uri() . '/js/stick-generate-lead.js',
            [],
            '1.0.0',
            true
        );
    }
});
```

Then drop `stick-generate-lead.js` into
`thegem-child/js/` (the TheGem child theme directory).

Alternatively, load it via TheGem's "Custom CSS/JS" widget or via
the Elementor custom-code section on each of the three pages — but
the mu-plugin approach is more durable.

---

## B. ADD DATA ATTRIBUTES TO EACH FORM

Each of the three pages wraps the SAME CF7 form (`wpcf7-f3039-o1`)
in different elementor containers. The page-wrapping approach is:

1. Open the page in WordPress → Elementor.
2. Find the form widget container.
3. In the **Elementor → Advanced → Attributes** section, add the
   `data-stick-lead-type` etc. attributes:

| WordPress page                | form_id          | data-stick-lead-type | data-stick-cta-location   |
|------------------------------|------------------|----------------------|---------------------------|
| /bookings/                   | wpcf7-f3039-o1   | `general`            | `bookings_page_form`      |
| /club-fitting-at-stick/      | wpcf7-f3039-o1   | `fitting`            | `club_fitting_page_form`  |
| /coaching-at-stick/          | wpcf7-f3039-o1   | `coaching`           | `coaching_page_form`      |

If you have multiple CTAs to the same form on a page (e.g. a
floating WhatsApp + the page form), the form-bound snippet will
only fire when the actual CF7 form submits. Each CTA on a page
does NOT need its own data attribute set — only the
event-deduped form does. The `cta_location` for the form is one
static per-page value.

**Elementor's Attributes for Custom HTML** (if you can't set
attributes directly on the Elementor widget):
- The simplest approach: wrap the Form widget with an HTML wrapper
  containing the `data-*` attributes, and use a small inline
  `document.querySelector('form.wpcf7-form').setAttribute(...)`
  in the same TheGem custom-JS widget. Easier than custom HTML.

---

## C. PRE-CREATE GA4 CUSTOM DIMENSIONS

**Done by Step 3C — the agent pre-creates these from the
service-account side so the operator does not have to log in.**

| Parameter     | Custom dimension name (in GA4 admin) | Scope   |
|---------------|----------------------------------------|---------|
| `lead_type`   | `lead_type`                            | event   |
| `cta_location`| `cta_location`                         | event   |
| `service`     | `service`                              | event   |

After Step 3C pushes the custom dimensions, GA4 will start
recording those as reportable dimensions in the next report
cycle (~24h).

---

## D. MARK `generate_lead` AS A GA4 KEY EVENT

**Done by Step 3C — the agent pre-creates the key event via the
GA4 Admin API so it is wired up the moment the form begins
firing.**

After operator installs the JS snippet + adds data attributes,
the moment a real form submission completes, `generate_lead` will
begin arriving in GA4 with `key_event=true`.

---

## E. TEST PLAN (operator-runs)

Before going live with the wire-up, follow this plan and let me
know when each step passes:

### Pre-flight

```text
[ ] JS file uploaded to /wp-content/themes/thegem-child/js/stick-generate-lead.js
[ ] wp_enqueue_scripts hook added for the 3 target pages
[ ] Elementor data-* attributes added to each form
[ ] GA4 custom dimensions lead_type/cta_location/service exist
[ ] generate_lead marked as GA4 key event
[ ] operator in another browser tab with GA4 DebugView:
    https://analytics.google.com/analytics/web/  → Admin → DebugView
    (DebugView requires a "GA4 Debug" browser extension OR the
     debug-mode URL ?_dbg=1)
```

### Test 1 — POSITIVE (Happy path)

```text
[ ] Open stickgolf.co.za/club-fitting-at-stick/
    in a fresh incognito tab
[ ] Fill in:
      Name:        "CAMPAIGN OS TRACKING TEST"
      Email:       (any plausible email, e.g. test@example.com)
      Phone:       +27 82 555 0000
      Message:     "CAMPAIGN OS TRACKING TEST — generate_lead fitting"
[ ] Click Submit

Expected (in GA4 DebugView within 5 seconds):
    event_name=generate_lead
    lead_type=fitting
    cta_location=club_fitting_page_form
    service=        (empty - not set, that's OK)
    form_id=3039
[ ] Confirm event appears
```

### Test 2 — POSITIVE (coaching)

```text
[ ] Open stickgolf.co.za/coaching-at-stick/
[ ] Fill in name "CAMPAIGN OS TRACKING TEST — coaching" + same fields
[ ] Click Submit

Expected (in GA4 DebugView):
    event_name=generate_lead
    lead_type=coaching
    cta_location=coaching_page_form
    form_id=3039
```

### Test 3 — POSITIVE (general/bookings)

```text
[ ] Open stickgolf.co.za/bookings/
[ ] Fill in "CAMPAIGN OS TRACKING TEST — bookings"
[ ] Click Submit

Expected:
    lead_type=general
    cta_location=bookings_page_form
    form_id=3039
```

### Test 4 — NEGATIVE (validation failure)

```text
[ ] Open any of the three pages
[ ] WITHOUT filling any fields, click Submit
Expected:
    Form shows "Please fill in this field" validation errors
    NO generate_lead event in DebugView
```

### Test 5 — NEGATIVE (incomplete / invalid submission — strict)

```text
[ ] Open /bookings/ in a fresh incognito tab
[ ] Fill ONLY some of the fields (e.g. name + email but NOT
    phone, OR fill with non-PII content like
    "CAMPAIGN OS TRACKING TEST" that a server-side filter
    would treat as invalid, OR clear one required field that
    the CF7 form config marks as required)
[ ] Click Submit

    Note: CF7 marks required fields with `aria-required="true"`
    and the browser should block the submit. If the browser
    blocks submission (HTML5 client-side required), no event
    will fire — PASS.
    If the browser does NOT block (CF7 is also doing server-side
    validation), then the validation error is shown by CF7 and
    `wpcf7invalid` fires (NOT `wpcf7mailsent`).
    In either case, NO `generate_lead` event is acceptable.

PASS criterion: 0 generate_lead events.
FAIL signal: any generate_lead event on incomplete / invalid
input must be investigated before declaring success.
```

**Snippet contract reminder:**

```text
The implementation listens ONLY on wpcf7mailsent.

wpcf7mailsent fires in CF7's Ajax flow only after the email
has been confirmed sent.

If CF7 invalidates the submission for any reason (validation
failure, spam filter, server-side rejection), the
`wpcf7mailsent` event will NOT fire.

Therefore: incomplete / invalid submissions produce exactly
0 generate_lead events. There is no acceptable
"0 or 1 depending on CF7 validation" outcome —
the outcome is always 0.
```

### Test 6 — DEDUPE (back-button resubmit)

```text
[ ] Complete Test 1 (positive fitting)
[ ] Click browser Back to return to the form
[ ] Click Submit again on the cached form
Expected:
    Either: 1 generate_lead event total (form blocked)
    Or: 2 generate_lead events total (browser resubmitted)
    The important check is the count; if >1, the operator should
    investigate and add a once-per-submission guard.
```

### Test 7 — DEDUPE (page refresh after success)

```text
[ ] Complete Test 1 (positive fitting)
[ ] After success-message shown, refresh the page
Expected:
    NO new generate_lead event (the form re-renders empty, not
    re-submits)
```

### Test 8 — ATTRIBUTION (paid social)

```text
[ ] In Meta Ads Manager (operator side), or via direct URL with
    UTM params, navigate to stickgolf.co.za/club-fitting-at-stick/?utm_source=instagram&utm_medium=social&utm_campaign=test
[ ] Fill "CAMPAIGN OS TRACKING TEST — attribution"
[ ] Submit
Expected (in Reports → Realtime, within 30 seconds):
    generate_lead event
    sessionSource=instagram
    sessionMedium=social
    sessionCampaignName=test
```

### Sign-off

When ALL of:
- Tests 1-3 each produce exactly 1 generate_lead event with
  correct parameters
- Tests 4-5 produce 0 events
- Tests 6-7 produce the dedupe-correct count
- Test 8 attaches the UTM-correct session attribution

…then `generate_lead` is wired correctly.

---

## F. POST-WIRE-UP VERIFICATION (operator → agent)

Once the operator runs the test plan and confirms the events
arrive in DebugView, send me the message:

```text
"Stick generate_lead live:
- Tests 1-3 PASS (events with correct parameters)
- Tests 4-5 PASS (no events on failure)
- Tests 6-7 PASS (dedupe correct)
- Test 8 PASS (attribution correct)"
```

I will then:
1. Verify the events in the production GA4 property's reporting
   API (not DebugView — that requires the debug cookie).
2. Verify the new key event is reported with the right
   parameters.
3. Verify brand isolation still holds (Stick generate_lead does
   NOT bleed into Swing Shack property).
4. Confirm custom dimensions are populated.
5. Produce the Step 3C close-out report.

---

## G. WHAT THIS DOES NOT DO

- Does NOT remove the existing 4 configured key events
  (qualify_lead, close_convert_lead, purchase, ads_conversion_Checkout_1).
  They are dormant. Their cleanup is a separate pass after 14
  days of clean generate_lead data.
- Does NOT mark form_start as a key event.
- Does NOT add booking_start / booking_complete / click_whatsapp
  events yet.
- Does NOT connect Meta.
- Does NOT modify tracking code on Swing Shack.
- Does NOT send PII to GA4 — only static, page-context
  parameters.

## H. WHAT IF A REAL FORM SUBMISSION WOULD NOTIFY STAFF?

Yes — CF7 sends an email to whatever address the WordPress admin
configured for unit 3039. **The test submissions WILL be
received by staff.** Please ensure the test messages are clearly
labelled `"CAMPAIGN OS TRACKING TEST"` in the message body so
staff can filter them out of production leads. The Step 3C
runbook tells you to do this explicitly.

---

## I. IF THE WIRE-UP FAILS

**Checklist:**

```text
1. Is the JS file loaded?
   → View page source; search for stick-generate-lead.
   → If absent: wp_enqueue_scripts block is not firing. Check
     page-template / hook order.

2. Is gtag loaded on the page?
   → View page source; search for 'G-HT1MCMX50G'.
   → If absent: this is a major regression — STOP and report.

3. Is the data attribute on the form?
   → In the DOM inspector, select the <form> element.
   → Look at attributes for data-stick-lead-type.
   → If absent: data attribute wasn't saved or attribute scope
     is wrong.

4. Is CF7 firing wpcf7mailsent?
   → In JS console: type
        document.querySelector('form.wpcf7-form')
          .addEventListener('wpcf7mailsent', () => console.log('ok'))
   → Submit the form.
   → If "ok" never logs: CF7 isn't firing the event. Either the
     AJAX is configured to use a different handler (e.g. Jetpack
     form), or there's a JS error before that listeners
     attaches.

5. Is gtag actually pushing the event?
   → In JS console: type
        window.dataLayer.push({ event: 'DEBUG_PUSH' })
   → In Tag Assistant / GA4 DebugView: confirm DEBUG_PUSH
     arrives.
   → If DEBUG_PUSH doesn't show up but wpcf7mailsent fires:
     the gtag call inside fireGenerateLead is broken — read the
     snippet console logs.
```

If you're stuck, send the result of each step + any error
messages and I'll diagnose remotely.

---

## End.

