Copy everything below the line into Claude Code on your PC.

---

I want to set up Campaign OS agent mail so my Claude can email Kyle (and he can email me) when a PR needs review or he adds a skill, template or framework.

1. Update the campaign-os plugin to the latest version (1.3.0 or newer): `claude plugin marketplace update campaign-os` then `claude plugin update campaign-os@campaign-os`, and tell me to restart Claude Code if needed. Then load the `campaign-os-mail` skill and read its SKILL.md and SETUP.md.
2. Run `cos_mail.py status` from that skill. I am on a PC, so the key file Kyle uses does not exist here. I need my own AgentMail API key (it is an API key, not a PAT) and my own sender inbox. Walk me through SETUP.md one step at a time: signing up at agentmail.to, making the API key and an inbox, and the email address I want replies to. Ask me which email I want to use before you continue.
3. Create the config file `.config/campaign-os/agent-mail.env` in my home folder yourself, but I will paste the key into that file directly. Do not ask me to type the key into this chat and do not echo it back. Keep it out of git.
4. Run `cos_mail.py set-email christelle <my email>` so I am in the contact list, show me the diff to `contacts.json`, and ask before committing and pushing it.
5. Run `status` until it says READY, then dry-run a test email to me and ask before sending it with `--send`.
6. From now on, when I say "email Kyle" (or "let Kyle know"), use the `campaign-os-mail` skill: dry-run first, then send once I say so. Kyle is the developer (KyleM@fivefriday.com); I am marketing.

Do the steps in order and stop to ask whenever you need something from me.
