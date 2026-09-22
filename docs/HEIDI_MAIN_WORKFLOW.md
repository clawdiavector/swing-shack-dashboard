# Heidi — main-branch workflow (skill pointer)

> **Historical deploy note (2026-09-22).** Program land uses `integrate/campaign-os-brand-lanes-v1` → Kyle → `main`; see [`docs/dev/conventions.md`](dev/conventions.md).

Hermes skill (authoritative): `~/.hermes/profiles/heidi/skills/swing-shack-main-workflow/SKILL.md`

Load **`swing-shack-main-workflow`** at the start of every Campaign OS session.

Production: https://swing-shack-dashboard-production.up.railway.app  
Deploy trigger: merge to `main` → Railway auto-deploy (~3 min)

Working clone: `~/.openclaw-instance2/workspace/swing-shack-dashboard` (not instance3)

Pre-push gate: `bash tests/smoke_boot.sh` must print `PASS` before any PR is "ready to merge."
