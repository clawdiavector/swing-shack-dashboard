# legacy/

Retired trees kept for evidence only. Do not run, do not cite as current architecture, do not "tidy".

## legacy/agents/

The Node "74 agents / 9 layers" tree, moved intact from `agents/` on 2026-09-11 (master plan t20).

`inputs{}` / `outputs{}` / `criticality` for the five Layer 1 manifests were salvaged to
`docs/layer1-salvage-20260911.yaml` (survives t33's deletion of this directory). Consumer: t29.
See also root `AGENTS.md` Appendix A.

Three conflicting inventories live here and are all wrong for today's product:
`legacy/agents/registry.json` (11 agents, dated 2026-04-21), `legacy/agents/README.md`,
and the 74 `manifest.json` files. Do not fix them. Do not cite them. See root `AGENTS.md`.

**Frozen until t33.** P1 side-by-side diff (t30/t32) uses this tree as the baseline.
Deletion of `legacy/agents/` is t33 only — never delete it in P0c.
