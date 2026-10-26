# Foreman morning summary (07:00 SAST)

Delivers a short operational digest: **posts scheduled for today**, **drafts awaiting approval**, and **open failing jobs**. Parallel to the plan-calendar `GET /api/jobs/morning-message` and the end-of-day `evening-message` report (PR #216).

## HTTP (read-only)

```http
GET /api/jobs/morning-summary?brand=all
Authorization: Bearer $COS_JOB_TOKEN
```

`brand` may be `stick`, `swing-shack`, `bag-drop`, or `all`. Response includes `text` (Telegram-ready), counts, and per-brand `sections`. The route **does not** send Telegram itself.

## Scheduled job

| Job | Schedule | Scheduler |
|-----|----------|-----------|
| `foreman_morning_summary` | 07:00 Africa/Johannesburg | `.github/workflows/layer1-daily-cron.yml` |

Manual run:

```bash
curl -sf -X POST "$BASE/api/jobs/run/foreman_morning_summary" \
  -H "Authorization: Bearer $COS_JOB_TOKEN"
```

## Telegram (off by default)

Telegram delivery happens **only inside the job**, and only when explicitly enabled.

| Variable | Required | Role |
|----------|----------|------|
| `FOREMAN_MORNING_SUMMARY_TELEGRAM` | to send | Set to `on` to post `text` after the job builds it. Default unset = build only, no send. |
| `TELEGRAM_BOT_TOKEN` | when sending | Bot token from @BotFather (Railway secret). |
| `TELEGRAM_CHAT_ID` | when sending | Target chat or group id. |

When the flag is off or credentials are missing, the job still returns `ok: true` with `telegram.skipped` and a reason — same pattern as `MAIL_INTAKE_NOTIFY_TO` for Herman mail.

Optional: `CAMPAIGN_OS_PUBLIC_URL` — base URL for “Approve drafts” links (defaults to production Railway URL).

## Mac Hermes (optional)

You can also curl `morning-summary` from a Mac cron and pipe `text` into an existing Hermes Telegram shim. The Railway job is enough when the three env vars above are set on Railway.
