// Stick Golf — generate_lead tracking
// Drop-in JS for stickgolf.co.za
//
// Fires `gtag('event', 'generate_lead', { lead_type, cta_location,
// service, form_id })` ONLY when Contact Form 7 confirms a successful
// email submission via the `wpcf7mailsent` DOM CustomEvent.
//
// Negative cases (validation failure, network error, abandoned form,
// submit-button click) do NOT trigger the event.
//
// WIRE-UP:
//   1. Save this file as /assets/js/stick-generate-lead.js in the
//      TheGem child theme (or load via elementor's custom JS widget
//      on each conversion page).
//   2. Replace <PASTE_SNIPPET> below with the actual snippet — see
//      sniff-and-paste instructions in the operator runbook.
//
// DELETE the wpcf7:invalid + wpcf7:submit listeners only if you need
// to debug — production should NOT need them.
//
// NO PII is sent to GA4:
//   - the form input fields your-name / your-email / your-phone /
//     the message textarea are NOT read
//   - the message body is NOT read
//   - only static parameters (lead_type, cta_location, service,
//     form_id) are sent
//
// Tested with: Contact Form 7 v6.1.6 (confirmed in production
// 2026-09-15).
//
// GENERATE_LEAD SENT ONLY ON `wpcf7mailsent`:
//   - native CF7 DOM CustomEvent
//   - documented at https://contactform7.com/dom-events/
//   - fires AFTER the email is successfully sent
//   - does NOT fire on validation failure, spam detection, send
//     failure, or abandonment.

(function () {
  'use strict';

  // Default parameters read from data-* attributes on the form.
  // Each page should set: data-stick-lead-type, data-stick-cta-location,
  // data-stick-service (optional). Fallback values match the most
  // generic form context.
  function pickLeadType(form) {
    return (
      form.getAttribute('data-stick-lead-type') ||
      form.getAttribute('data-lead-type') ||
      'general'
    );
  }
  function pickCtaLocation(form) {
    return (
      form.getAttribute('data-stick-cta-location') ||
      form.getAttribute('data-cta-location') ||
      'unknown'
    );
  }
  function pickService(form) {
    return (
      form.getAttribute('data-stick-service') ||
      form.getAttribute('data-service') ||
      ''
    );
  }

  function fireGenerateLead(form, detail) {
    if (!window.gtag || typeof window.gtag !== 'function') {
      console.warn('[stick-generate-lead] gtag not available; skipping event');
      return;
    }

    // --- form_id guarantee (brief §III-Stage-3C operator note) ---
    // Only fire on the canonical Stick CF7 unit ID (3039).
    // Any other CF7 form on the site cannot accidentally fire
    // generate_lead even if the snippet loads there (e.g. a generic
    // contact form).
    var formId = form.getAttribute('data-wpcf7-id') || '';
    if (formId !== '3039') {
      console.info(
        '[stick-generate-lead] ignored — form is not CF7 unit 3039 (got: ' +
        (formId || 'unknown') + ')'
      );
      return;
    }

    // --- detail.contactFormId safety net ---
    // The wpcf7mailsent CustomEvent includes an event.detail object
    // with contactFormId. If the event fires on a different form
    // (eg. CF7 unit 3077 because someone left the data-wpcf7-id
    // attribute off), we want to refuse to fire.
    if (detail && typeof detail === 'object') {
      var detailId = String(detail.contactFormId || '');
      if (detailId && detailId !== '3039') {
        console.info(
          '[stick-generate-lead] ignored — event.detail.contactFormId=' +
          detailId + ' (not 3039)'
        );
        return;
      }
    }

    var lead_type = pickLeadType(form);
    var cta_location = pickCtaLocation(form);
    var service = pickService(form);

    var params = {
      lead_type: lead_type,
      cta_location: cta_location,
      form_id: '3039'
    };
    if (service) {
      params.service = service;
    }
    // GA4 recommended event payload has a strict reserved-name list.
    // We pass brand-safe, GA-4-event-parameter-validation-friendly
    // string values only; numbers/bools would require a different
    // gate. Keep them lowercase + underscores.
    window.gtag('event', 'generate_lead', params);
  }

  function bind() {
    var forms = document.querySelectorAll('form.wpcf7-form');
    if (!forms.length) return;
    forms.forEach(function (form) {
      // Guard: ensure we only bind once per form, even if the script
      // is loaded twice.
      if (form.__stickGenerateLeadBound) return;
      form.__stickGenerateLeadBound = true;

      // POSITIVE — fire ONLY on the canonical CF7 success event.
      // wpcf7mailsent is dispatched by CF7's Ajax submission flow
      // *only after the email is confirmed sent*. It does NOT fire
      // on validation failure (wpcf7invalid), spam detection
      // (wpcf7:spam), send failure (wpcf7:mailfailed), or
      // abandonment. We do NOT register listeners for those events.
      //
      // IMPORTANT: CF7 confirms wpcf7mailsent fires specifically in
      // its Ajax submission flow. If Stick's forms run in
      // non-Ajax (page-reload) mode, this event will not fire and
      // generate_lead will never be sent — that is exactly the
      // operator's intent: no false positives.
      //
      // The event handler receives a CustomEvent whose
      // event.detail has shape:
      //   { contactFormId: "...", inputs: [...], ... }
      // We pass it through to fireGenerateLead so the
      // detail.contactFormId safety-net check is enforced.
      form.addEventListener('wpcf7mailsent', function (ev) {
        fireGenerateLead(form, ev ? ev.detail : null);
      });

      // NEGATIVE — we DO NOT listen on submit-button click,
      // wpcf7:submit, wpcf7:invalid, wpcf7:spam, or
      // wpcf7:mailfailed. CF7 only dispatches wpcf7mailsent on
      // confirmed success (in its Ajax flow). Listening on any
      // other event would be a false-positive risk.
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
