# Frontend surfaces

Three user-facing surfaces share one Flask app and one `$DATA_DIR`.

## Campaign Heroes — `/app` (integrate)

- Source: **`web/`** — Vite + React + Tailwind.
- Product intent: `web/PRODUCT.md`. Visual vocabulary: **`web/DESIGN.md`** (do not fork tokens in docs).
- Docker: Node stage builds `web/dist`; Flask serves under `/app` and aliases (`/daily`, `/review`, `/create`, `/calendar`, `/publish`, `/results`, `/other`).
- Desk routing, tools, brand switch: see `web/src/` and in-flight Heroes tickets in [`state-of-play.md`](state-of-play.md).

**Branch note:** `web/` is on **`integrate/campaign-os-brand-lanes-v1`**; verify on `origin/main` before assuming Heroes is in prod.

## Classic cockpit — `/`

- **`campaign-os/campaign-os.html`** — monolithic SPA, session auth.
- Section / nav inventory: [`WORKSPACE_MAP.md`](../../WORKSPACE_MAP.md) — count there; do not freeze section counts in new docs.
- **Never delete** leftover classic HTML or routes while Heroes is partial.

## Ops — `/ops` and `/ops/jobs`

- Session-only HTML for job verdicts, run now, diagnostics drawer.
- Deep link: `/ops/jobs?job=<name>`.
- Skill detail: `~/.agents/skills/campaign-os/modules/ops-ui.md`.

## Iframe tools pattern

Classic and Heroes both host embedded tools via `/tool/:slug` → `ToolFrame` iframe pattern where applicable. Prefer native Heroes pages when the ticket scope is `web/` only.

## Local dev

Port from agent job `runtime.ports.web` — never hardcode 8765/8080. Scratch `DATA_DIR` + non-empty `COS_JOB_TOKEN`. See [`how-to.md`](how-to.md).
