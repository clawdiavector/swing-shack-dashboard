# Campaign OS — Development module

**Authority:** product repo [`docs/dev/how-to.md`](docs/dev/how-to.md) — this file is navigation only.

## Read first

[`docs/dev/INDEX.md`](docs/dev/INDEX.md)

## Recipes (deep links)

| Task | Doc section |
|---|---|
| Add a registered job | [`how-to.md` → Add a registered job](docs/dev/how-to.md) |
| Add a Mac `cos-*` agent | [`how-to.md` → Add a Mac agent](docs/dev/how-to.md) |
| Frontend (Heroes or classic) | [`how-to.md` → Frontend change](docs/dev/how-to.md) |
| Add an API route | [`how-to.md` → Add an API route](docs/dev/how-to.md) |

## Which repo to edit

| Change | Repo |
|---|---|
| Flask, jobs, `web/`, `docs/dev/` | `swing-shack-dashboard-main` on `feat/*` → `integrate/campaign-os-brand-lanes-v1` |
| Manifests, tickets, Mac profiles | `agent-control` (foreman) |
| Ops curl recipes | This skill (`modules/api.md`, `modules/jobs.md`) |

Foreman **spawns a writer job** for product code — does not edit the product repo directly.

Branch rule: never push `main` without Kyle or Christelle approving it.
