# Campaign OS — developer library (start here)

Campaign OS is a Flask marketing cockpit on Railway: registered batch **jobs** (L1), ops **layers** L1–L8, a classic HTML SPA at `/`, Campaign Heroes React desk at **`/app`** (on integrate), and Mac Hermes **agents** for L3 interpret work. Runtime truth is **`$DATA_DIR`**; repo `data/` is seed-only.

**Before any product change:** read this index, then the linked topic file. Hub skill: `~/.agents/skills/campaign-os/SKILL.md`. Deploy runbook: [`RAILWAY.md`](../../RAILWAY.md). Agent standing rules: [`AGENTS.md`](../../AGENTS.md). Nav inventory: [`WORKSPACE_MAP.md`](../../WORKSPACE_MAP.md). Foreman host map: `agent-control/context/campaign-os-hosts.md`.

## I want to…

| Task | Read |
|---|---|
| Add a registered job | [`how-to.md`](how-to.md) → Add a job · [`jobs.md`](jobs.md) |
| Add or change a Mac `cos-*` agent | [`how-to.md`](how-to.md) → Add a Mac agent · [`layers-and-agents.md`](layers-and-agents.md) |
| Change Campaign Heroes (`/app`, `web/`) | [`frontend.md`](frontend.md) · `web/DESIGN.md`, `web/PRODUCT.md` |
| Change classic `/` or `/ops` | [`frontend.md`](frontend.md) · `campaign-os/campaign-os.html` |
| Understand L1–L8 and agents | [`layers-and-agents.md`](layers-and-agents.md) |
| Understand hosts, deploy, cron | [`architecture.md`](architecture.md) · [`RAILWAY.md`](../../RAILWAY.md) |
| Branch rules, secrets, tests | [`conventions.md`](conventions.md) |
| What is shipped vs in-flight | [`state-of-play.md`](state-of-play.md) |

## Topic files

| File | Contents |
|---|---|
| [`architecture.md`](architecture.md) | Flask + SPAs, `$DATA_DIR`, auth, cron-host ruling |
| [`layers-and-agents.md`](layers-and-agents.md) | Ribbon, North Star mapping, queue, mark-done |
| [`frontend.md`](frontend.md) | `/app`, `/`, `/ops` |
| [`jobs.md`](jobs.md) | JobSpec, registry, verdicts, workflows |
| [`how-to.md`](how-to.md) | Implement recipes |
| [`state-of-play.md`](state-of-play.md) | Branch snapshot (not a roadmap) |
| [`conventions.md`](conventions.md) | Branches, secrets, tests, land |

## History — not implement contracts

Do not implement from these; use `docs/dev/` and live code instead.

- `campaign-os/SPEC.md`, `CAMPAIGN-OS-FULL-SPEC.md`, `V2-*-SPEC.md` — May–Jun 2026 specs
- `docs/MARKETING_OS_NORTH_STAR.md` — product vision (see mapping in [`layers-and-agents.md`](layers-and-agents.md))
- `docs/CAMPAIGN-MOTHERSHIP-V2.md` — draft product doc
- `campaign-os/docs/ASSET_STATE_ENGINE.md`, `CAMPAIGN_STATE_ENGINE.md` — pre–t33 engine notes
- `docs/PRODUCTION_READINESS_GUIDE.md`, `docs/HEIDI_MAIN_WORKFLOW.md` — stale ops guides
- `campaign-os/docs/nightshift-log.md` — append-only log

## Not covered here

`campaign-os/meta-app-review/`, `tiktok-marketing/`, `research/`, `strategy/`, `outreach/` — marketing research and ops collateral, not developer architecture.
