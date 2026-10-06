# Campaign OS — Agent mail module

Email for reports, digests, ticket notifications. **Auto-send off by default.**

Canonical doc: `agent-control/context/agent-mail.md`

## Live setup (2026-09-21)

| Item | Value |
|---|---|
| Provider | AgentMail |
| Inbox | `campaign-os-foreman@agentmail.to` |
| Secrets | `~/.config/agent-control/agent-mail.env` |
| Auto-send | `mail_enabled: false` |
| Verify | OTP required for non-Kyle recipients |

## Commands

```bash
python3 bin/agent-mail.py status
python3 bin/agent-mail.py provision
python3 bin/agent-mail.py send --send --to user@example.com --subject "…" --body "…"
```

## Agent pattern

```python
import agent_mail_lib as mail
mail.send_mail(subject="Digest", body=report)  # no-op until mail_enabled=true
```

## Providers

| `mail_provider` | Use |
|---|---|
| `agentmail` | Default — agent inboxes, API |
| `smtp` | M365 `@fivefriday.com` |

Not zsdmail (brand client mail only).

## Before enabling auto-send

1. AgentMail verified (OTP)
2. Test `--send` to target recipient
3. Set `mail_default_to`
4. `mail_enabled: true`
5. Wire caller (`desk_report`, digest, ticket_notify)
