# Shared Agent Output Schema

**Version:** 1.0  
**Date:** 2026-04-21  
**Applies to:** All Layer 1 agents producing data files in `data/`

---

## Minimum Contract

Every agent output file must include this header:

```json
{
  "schema":     "https://clawdia.io/agents/output-schema/v1",
  "agent_id":   "hook_smith",
  "generated":  "2026-04-21T06:15:00.000Z",
  "status":     "PASS",
  "data_status": "FRESH",
  "confidence":  8,
  "priority":   "HIGH",
  "owner":      "hook_smith",
  "next_action": "Use top 3 hooks in post plan",
  "notes":      [],
  "qa_warnings": []
}
```

---

## Field Definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `schema` | string | ✅ | Fixed URI. Validates file is standard-compliant. |
| `agent_id` | string | ✅ | Agent identifier from `agents/registry.json` |
| `generated` | ISO 8601 | ✅ | When the file was generated |
| `status` | enum | ✅ | `PASS` · `PARTIAL` · `FAIL` — script/script-level result |
| `data_status` | enum | ✅ | `FRESH` · `STALE` · `SYNTHETIC` · `MISSING` — data source quality |
| `source_mode` | enum | ⚠️ | `LIVE` · `CACHED` · `SYNTHETIC` · `MOCK` — data origin |
| `confidence` | integer 0-10 | ⚠️ | How confident the agent is in this output |
| `priority` | enum | ⚠️ | `CRITICAL` · `HIGH` · `MEDIUM` · `LOW` — business priority |
| `owner` | string | ⚠️ | Who owns the decisions this output informs |
| `next_action` | string | ⚠️ | The single most important action this output recommends |
| `notes` | array | ⚠️ | Context, caveats, notable observations |
| `qa_warnings` | array | ⚠️ | Anything that could be wrong with the data |
| `stale_sources` | array | ⚠️ | List of input files that were stale/missing |
| `runtime_ms` | integer | ⚠️ | How long the script took to run (ms) |

---

## Data Status Definitions

| Value | Meaning |
|---|---|
| `FRESH` | All sources available and recent (< 24h) |
| `STALE` | One or more sources are old (> 24h) or missing |
| `SYNTHETIC` | Generated from models/heuristics, no live source |
| `MISSING` | Required source completely absent |

---

## Source Mode Definitions

| Value | Meaning |
|---|---|
| `LIVE` | Real API / scraping — actual live data |
| `CACHED` | Used a cached copy because live source failed |
| `SYNTHETIC` | AI-generated content (hook ideas, captions) |
| `MOCK` | Placeholder — only for testing |

---

## Q&A Warnings

Agents should flag:
- Missing required inputs
- Unexpected data shape
- Contradictions between sources
- Numbers that seem off
- Sources that are known-unreliable

---

## Phase-In Plan

**Already compliant** (will be patched):
- `system-health.json` → next pipeline run
- `agent-scorecards.json` → next pipeline run

**High-value first** (next sprint):
- `post-plan.json`
- `recommendation-scores.json`
- `retargeting-recommendations.json`
- `hook-bank.json`
- `anomaly-alerts.json`

**All files** (eventually):
- Every `data/*.json` output from a Layer 1 agent

---

## Enforcement

The Pulse Keeper (`generate_pulse_keeper.js`) validates schema compliance on every run and flags any file missing required fields.
