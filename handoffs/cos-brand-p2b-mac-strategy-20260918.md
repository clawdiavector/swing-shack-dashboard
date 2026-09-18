# P2b Mac STRATEGY_BRAND cron wiring — 2026-09-18

**Job:** `job-20260918-cos-brand-p2b-mac-strategy-implement`  
**Branch:** `feat/cos-brand-p2b-mac-strategy`  
**Verdict:** PASS (Mac crons + script fix)

## Summary

Stick has a **distinct domain** (`stickgolf.co.za` vs `swingshack.co.za` per `campaign-os/_lib/reporting_intelligence.py` `BRAND_CONFIG`). Two Heidi strategy crons were duplicated on the Mac with `STRATEGY_BRAND=stick`. `fetch_ubersuggest.py` now refuses to silently default to `swingshack.co.za` when a non-default brand is set without `BRAND_DOMAIN_<BRAND>`.

**Not in scope:** cos-scout / K9 writer jobs — untouched.

## Mac cron file

**Path:** `/Users/fivefriday/.hermes/profiles/heidi/cron/jobs.json`  
**Count:** 8 → 10 jobs (2026-09-18)

Hermes cron jobs carry shell commands inside the `prompt` field (no separate `env` object).

### Swing Shack (existing — unchanged)

| Cron id | Name | Schedule | Env / shell |
|---|---|---|---|
| `6d7801e447bb` | Strategy Monday brief | `0 4 * * 1` | *(default)* `STRATEGY_BRAND=swing-shack` via script default |
| `6eb3d1256b38` | Monthly strategy audit + kill meeting | `0 4 1-7 * 1` | *(default)* `STRATEGY_BRAND=swing-shack` via script default |

**Shell (embedded in prompt):**

```bash
cd /Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard && python3 scripts/weekly_strategy_brief.py
```

```bash
cd /Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard && python3 scripts/monthly_kill_meeting.py
```

### Stick (new — 2026-09-18 via mac-bridge)

| Cron id | Name | Schedule | Env / shell |
|---|---|---|---|
| `acc8246590df` | Stick — Strategy Monday brief | `0 4 * * 1` | `STRATEGY_BRAND=stick` |
| `7ab766f06788` | Stick — Monthly strategy audit + kill meeting | `0 4 1-7 * 1` | `STRATEGY_BRAND=stick` |

**Shell (embedded in prompt):**

```bash
cd /Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard && STRATEGY_BRAND=stick python3 scripts/weekly_strategy_brief.py
```

```bash
cd /Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard && STRATEGY_BRAND=stick python3 scripts/monthly_kill_meeting.py
```

Both stick jobs: `enabled: true`, same Discord origin/deliver/skills as parents, run history reset.

## Script changes (repo)

| Script | Change |
|---|---|
| `scripts/weekly_strategy_brief.py` | Already reads `STRATEGY_BRAND` (default `swing-shack`) — no edit |
| `scripts/monthly_kill_meeting.py` | Already reads `STRATEGY_BRAND` — no edit |
| `scripts/fetch_ubersuggest.py` | Domain resolution: `--domain` > `BRAND_DOMAIN_<BRAND>` > `SWING_SHACK_DOMAIN`; non-default `STRATEGY_BRAND` without `BRAND_DOMAIN_*` exits with error |

### fetch_ubersuggest env blocks (reference)

**Swing Shack (default):**

```bash
STRATEGY_BRAND=swing-shack          # optional — default
SWING_SHACK_DOMAIN=swingshack.co.za # optional — default
python3 scripts/fetch_ubersuggest.py
# or: python3 scripts/fetch_ubersuggest.py --domain swingshack.co.za
```

**Stick (when a Mac/GHA cron is added later):**

```bash
STRATEGY_BRAND=stick
BRAND_DOMAIN_STICK=stickgolf.co.za
python3 scripts/fetch_ubersuggest.py
# or: python3 scripts/fetch_ubersuggest.py --domain stickgolf.co.za
```

**Note:** No `fetch_ubersuggest` Heidi cron exists today. Railway/GHA `seo_rankings` job already passes `--domain` via `resolve_brand_domain()` in `campaign-os/_lib/jobs/layer1/seo_rankings.py`.

## Domain decision

| Brand | Domain | Source |
|---|---|---|
| swing-shack | `swingshack.co.za` | `BRAND_CONFIG`, `SWING_SHACK_DOMAIN` |
| stick | `stickgolf.co.za` | `BRAND_CONFIG`, `data/brand-planning/stick.json` |

Stick duplicates **warranted** — distinct site and GA4 property (`532174688`).

## Mac-bridge dispatches

| Bridge job id | Purpose | Result |
|---|---|---|
| `15416f8f-662f-49f4-9077-fd6504557d90` | Read-only inspect `jobs.json` | done |
| `d23e48c0-13fe-44a7-b8d9-d7a6018c0f28` | Read full job JSON schema | done |
| `717caa20-2a82-48df-88b6-203c52bd0721` | Add stick strategy cron duplicates | done |

## Kyle gates (unchanged)

- Deploy `integrate/campaign-os-brand-lanes-v1` before prod stick lane runs
- Railway stick vars (`META_PAGE_ID_STICK`, etc.) when stick jobs should not SKIPPED
- K9 scout writer — separate ticket; not enabled here
