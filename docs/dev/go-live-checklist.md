# Campaign OS go-live checklist (L6 publish gates)

This documents the **environment switches** that keep posts from reaching Postiz,
Google Business Profile, or the public feed until Kyle deliberately turns live
publish on. None of these are changed by application code in a normal deploy;
they are Railway (or local) env vars plus Postiz channel verification.

## Quick map

| Gate | Default | What it blocks | Kyle changes |
|------|---------|----------------|--------------|
| `PUBLISH_MODE` | `sandbox` | Outbound Postiz/GBP HTTP from `publish_dispatch` and live publish adapters | Set `PUBLISH_MODE=live` on Railway after Postiz + channels are verified |
| `CAMPAIGN_OS_AUTO_RELEASE` | off | `auto_release` job moving **scheduled** calendar moments to released queue rows on go-live day (SAST) | Set `CAMPAIGN_OS_AUTO_RELEASE=1` when daily release should run without manual release |
| `CAMPAIGN_OS_POSTIZ_ON_APPROVE` | off | Creating a **scheduled Postiz post** when a queue row is human-approved (live mode only) | Set `CAMPAIGN_OS_POSTIZ_ON_APPROVE=1` to schedule on approve instead of only via `publish_dispatch` |

Layer label in ops UI: **L6 Publish** (`_lib/ops_layers.py`).

---

## `PUBLISH_MODE` (sandbox vs live)

**Read in**

- `_lib/publish_mode.py` — `get_publish_mode()`, `is_sandbox_mode()`, `is_live_mode()`. Unset or invalid values → **`sandbox`**.
- `_lib/jobs/publish_dispatch.py` — sandbox calls `publish_sandbox.dispatch_pending()`; live calls `publish_live.dispatch_pending()`.
- `_lib/publish_live.py` — Postiz create/upload only when mode is live (imported from live path).
- `_lib/postiz_on_approve.py` — `schedule_row_on_approve()` returns immediately unless `is_live_mode()`.
- `_lib/ops_layers.py` — L6 status line references sandbox vs live.
- `_lib/connected_accounts_catalog.py` — documents default sandbox on Railway.
- `app.py` — `GET /api/publish/mode` exposes current mode (session or `COS_JOB_TOKEN`).

**What it blocks in sandbox**

- No real Postiz or GBP publish HTTP from the dispatch job; sandbox writes **receipts** and queue state under `$DATA_DIR` instead.
- Schedule-on-approve and live delete-on-unapprove paths are no-ops for outbound Postiz.

**What Kyle changes**

1. Confirm Postiz integrations per brand (`POSTIZ_*` keys, channel list in cockpit).
2. On Railway (prod): set `PUBLISH_MODE=live` (only after verification — see `connected_accounts_catalog` hint).
3. Re-run or wait for `publish_dispatch` (cron / manual `POST /api/jobs/run/publish_dispatch`).

**Verify**

```bash
curl -s -H "Authorization: Bearer $COS_JOB_TOKEN" \
  "$PROD_URL/api/publish/mode"
```

Expect `"mode": "live"` when intentionally live.

---

## `CAMPAIGN_OS_AUTO_RELEASE`

**Read in**

- `_lib/jobs/auto_release.py` — `_auto_release_enabled()`, `run()`.
- `app.py` — included in `GET /api/publish/mode` as `auto_release`, `auto_release_hour`, `auto_release_source`.
- `_lib/jobs/descriptions.py` — job description for operators.

**What it blocks when off (default)**

- The job still **lists** candidates (scheduled moments whose go-live date is today SAST, after per-brand release hour) but returns `gated: true`, `released: 0`.
- No call to `publish_sandbox.release_moment()` for those candidates.

**Optional tuning**

- `CAMPAIGN_OS_AUTO_RELEASE_HOUR` — default `0` (SAST hour, 0–23).
- Per-brand override: `calendar_preferences.release_time_sast` in brand marketing calendar config.

**What Kyle changes**

1. Set `CAMPAIGN_OS_AUTO_RELEASE=1` on the host that runs jobs (Railway for prod).
2. Optionally set hour env or brand calendar release time.
3. Ensure moments are in **scheduled** state with `go_live_date` set.

**Verify**

```bash
curl -s -H "Authorization: Bearer $COS_JOB_TOKEN" \
  "$PROD_URL/api/jobs/run/auto_release?reason=manual"
```

When gated, response includes `"gated": true` and `"reason"` explaining unset env.

---

## `CAMPAIGN_OS_POSTIZ_ON_APPROVE` (PR #217)

**Read in**

- `_lib/postiz_on_approve.py` — `is_enabled()`, `schedule_row_on_approve()`, `clear_postiz_on_unapprove()`.
- `_lib/publish_sandbox.py` — hooks on approve / unapprove of queue rows.
- `_lib/unified_inbox.py` — clear Postiz on unapprove when applicable.

**What it blocks when off (default)**

- Approving a queue row does **not** call Postiz `create_post`, even in live mode.
- Publish still flows through `publish_dispatch` (and manual ops) when live.

**What it blocks when on but still sandbox**

- `schedule_row_on_approve()` requires **both** `PUBLISH_MODE=live` and `CAMPAIGN_OS_POSTIZ_ON_APPROVE=1`.

**Requirements when enabled (live)**

- Row: `human_approved`, `idempotency_key`, resolvable `would_publish_at` or `event_date`.
- Brand Postiz API key (`has_brand_key(brand_id)`).
- Non-empty caption (from draft / preview); image or preflight pass.
- Postiz integration for row `platform`.

**What Kyle changes**

1. Set `PUBLISH_MODE=live` (above).
2. Set `CAMPAIGN_OS_POSTIZ_ON_APPROVE=1` if schedule-on-approve is desired.
3. Ensure queue rows have schedule fields and captions before approve.

**Un-approve**

- Future Postiz schedules may be deleted (`clear_postiz_on_unapprove`); posts inside ~2 minutes of send time refuse un-approve.

---

## End-to-end “post goes live” path (reference)

1. **L5 Create** — `draft_assets` / compose / QC produce drafts (not gated by publish mode).
2. **Human approve** — queue row `human_approved`; optional Postiz schedule if live + `CAMPAIGN_OS_POSTIZ_ON_APPROVE`.
3. **Release** — manual or `auto_release` when `CAMPAIGN_OS_AUTO_RELEASE=1`.
4. **L6** — `publish_dispatch` with `PUBLISH_MODE=live` sends to Postiz/GBP.

Caption pipeline failures (e.g. Swing Shack `draft_assets` with no survivors) are **upstream of L6** — fix brand voice / brief fidelity / LLM, not publish env vars.

---

## Do not change in code for go-live

- Railway secrets and `PUBLISH_MODE` on prod without Kyle or Christelle approval in-session (`AGENTS.md`).
- No agent writes to `data/` or production `$DATA_DIR` campaign files.
