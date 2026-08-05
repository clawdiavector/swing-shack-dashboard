# Nightshift Report — 2026-08-05T15:40Z

## ✅ Done
Em-dash sweep in 6 user-facing `data-help` tooltip bodies (standing-rule consistency fix). All 6 had `—` characters in tooltip popover copy; swapped for `·` to match the 109 tooltips shipped since the rule landed (dce75d3, 2026-08-04T15:52Z).

Surfaces: Calendar nav, Meme Lord nav, GBP nav, GMB body textarea, View brand directory button, Campaign work-view h3.

## 🎯 Verified (Playwright LIVE, cookie auth, Railway URL)
- Cache-busted bundle probe: **6/6 new middle-dot needles found in served HTML**, **0/6 old em-dash needles remain**.
- DOM count via Playwright selectors: calendar/memes/gbp nav = 1/1/1; gmb body textarea (after openGmbEdit()) = 1; brand directory view btn = 4 (one per brand).
- Calendar tooltip popover text: `"Content calendar · month grid of every planned post across all brands."` — middle dot renders verbatim.
- 0 PAGEERROR. 0 CONSOLE.error (only 2 pre-existing 503s on cos_session re-validation, unrelated).
- /api/health green.

## 📁 Commit
`af32180` on `feat/asset-state-engine`, 1 file (`campaign-os/campaign-os.html`), +6/-6 single-character replacements, pushed. Railway auto-deployed in ~90s.

## 📸 Screenshots (LIVE)
- `/tmp/co-nightshift/walkthrough_2026-08-05T1540_emdash_sweep_calendar_tooltip.png` — Calendar nav tooltip popped, body shows middle dot.
- `/tmp/co-nightshift/walkthrough_2026-08-05T1540_emdash_sweep_fullpage.png` — full SPA after fix.

## 🎯 Next
Em-dash sweep in remaining surfaces (description lines, app.py server-side error strings) — OR audit other HTML files for the same pattern.

## 🧠 Learned
- Prior 15:52Z tick swept `<title>` + privacy/terms body but did NOT include `data-help=` attribute bodies. The 06:24Z-onwards tooltip ticks all used middle dots, but these 6 pre-existing tooltips (from before the rule landed) were missed. Single-shot em-dash probe should be expanded to cover `data-help` and `data-help-title` attributes too.
- The Calendar / Meme Lord / GBP nav rows live in `#all-tools-section` which is `hidden` by default — Playwright probes need to `removeAttribute('hidden')` first, or click `#all-tools-toggle`.

## 🚨 Asks
None.
