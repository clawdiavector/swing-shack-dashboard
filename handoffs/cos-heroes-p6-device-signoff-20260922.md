# P6 device sign-off — Campaign Heroes

**Date:** 2026-09-22  
**Branch:** `feat/cos-heroes-p6-cutover` @ implement  
**Port (job):** 3247 (`runtime.ports.web` in `.agent-job.json`)

Physical walk (phone / iPad / desktop) is **Kyle's gate**. This file records
implement-time triage and leaves the viewport × page matrix for Kyle to fill
after the LAN walk (`npm run dev -- --port <web> --host 0.0.0.0` + Flask on
8080 or `VITE_API_TARGET`).

## Known risks (plan §2.4) — triage at implement

| ID | Risk | Disposition |
|---|---|---|
| D1 | Bottom nav crowding at 390px (`grid-cols-8`) | **Accepted for P6** — verify on device; fix in a follow-up if labels clip |
| D2 | No iOS safe-area padding on bottom nav | **Accepted for P6** — add `viewport-fit=cover` + inset padding when Kyle confirms on iPhone |
| D3 | `html { font-size: 18px }` drives rem scale | **Documented** in `web/DESIGN.md` §Type; device walk validates overflow |
| D4 | Tooltip bubble can extend past viewport at 390 | **Accepted for P6** — bubble is `pointer-events: none`; check horizontal scroll on walk |
| D5 | `:hover` tips stick after tap on iOS | **Accepted for P6** — optional `@media (hover: hover)` gate deferred |
| D6 | Register vs code layout (272px / 1680px) | **Resolved** — register updated to match `Shell.tsx` |
| D7 | Register vs code typefaces | **Resolved** — register updated; fonts self-hosted for CSP (D8) |
| D8 | Google Fonts blocked by production CSP | **Fixed** — `@fontsource/*` imports in `web/src/index.css` |

## Viewport × page matrix (Kyle — fill PASS/FAIL)

Viewports: 390×844 · 768×1024 · 1024×768 · ≥1280.  
Pages: Daily → Ops rail order + `/app/other` (see plan §2.2).

| Viewport | Page | Result | Notes |
|---|---|---|---|
| 390×844 | _(each rail page)_ | ☐ | |
| 768×1024 | _(each rail page)_ | ☐ | |
| 1024×768 | _(each rail page)_ | ☐ | |
| ≥1280 | _(each rail page)_ | ☐ | |

Screenshots: attach under `media/p6-signoff/` when captured (32 rail shots optional).

## Build-parity pass

After device walk, re-check one viewport against `npm run build` + Flask serving
`web/dist` at `/app` (plan §2.1).
