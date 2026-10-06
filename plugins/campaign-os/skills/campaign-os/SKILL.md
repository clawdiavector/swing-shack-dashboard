---
name: campaign-os
description: >
  Campaign OS operations hub — Layer 1 jobs, prod health, host routing, JSON
  output inspection. Use when Kyle mentions Campaign OS, swing-shack-dashboard,
  marketing cockpit, Gate P1, job crons, /ops/jobs, COS_JOB_TOKEN, or job verdicts.
---

# Campaign OS (hub skill)

Modular skill for the **swing-shack-dashboard** marketing OS. Load this first;
then open the module that matches the task.

## Modules

| Module | When |
|---|---|
| [modules/layers.md](modules/layers.md) | L1–L8 stack, sequencing, key gates |
| [modules/agents.md](modules/agents.md) | Mac fleet roster, heartbeat, queue, crons |
| [modules/api.md](modules/api.md) | Bearer curl recipes for ops + scout |
| [modules/operator-post.md](modules/operator-post.md) | Lodge one dated post → calendar + Create queue (not Review) |
| [modules/ops-ui.md](modules/ops-ui.md) | `/ops` ribbon tabs and deep links |
| [modules/jobs.md](modules/jobs.md) | Run jobs, check verdicts, read output JSON |
| [modules/hosts.md](modules/hosts.md) | Where things run (Railway / Mac / Linux) |
| [modules/mac-build-deploy.md](modules/mac-build-deploy.md) | Vite preview + emergency Mac Railway (prod still GitHub→Docker) |
| [modules/agent-mail.md](modules/agent-mail.md) | Agent SMTP mail (disabled by default) |
| [modules/dev.md](modules/dev.md) | Implement recipes — add a job, agent, UI, API |

**Also load when needed:** `agent-control-mac-bridge` for Mac-only shell/Railway CLI;
`campaign-os-template` when Kyle gives example posts to turn into a compose template.

**Building / extending:** `${CLAUDE_PROJECT_DIR}/docs/dev/INDEX.md`

## Quick facts

| Item | Value |
|---|---|
| Prod | https://swing-shack-dashboard-production.up.railway.app |
| Dashboard (campaigner UI) | `/app/daily` (Campaign Heroes) · classic `/` still live |
| Jobs UI | `/ops/jobs` (session login) |
| Product repo | `${CLAUDE_PROJECT_DIR}` |
| Foreman repo *(Kyle’s desk only — not on a fresh machine)* | `~/finder-workspace/repos/work/agent-control` |
| Job bearer | `COS_JOB_TOKEN` in Railway + `~/.hermes/.env` + GitHub secret |
| Dev library | `docs/dev/INDEX.md` in the product repo — read before changing product code |

## Foreman rules

- **Lodge a post / load a post for a date** — `modules/operator-post.md`. Ask **brand** if omitted. Calendar **and** caption+image queue. Do not run Create unless Kyle says run now. Do not point at Review until the pair is complete. `event_key` must be `{brand}:…`.
- **Prod checks** — bearer or session; never print token values
- **App code** — spawn a writer job; foreman edits agent-control only
- **Mac-only** — `bin/mac-bridge-client.py dispatch --wait`
- **Protected branches** — feature branch + PR; Kyle approves `main` push

## Entry handoffs

- Gate P1: `agent-control/handoffs/campaign-os-gate-p1-slice-handoff-20260916.md`
- Host map: `agent-control/context/campaign-os-hosts.md`
