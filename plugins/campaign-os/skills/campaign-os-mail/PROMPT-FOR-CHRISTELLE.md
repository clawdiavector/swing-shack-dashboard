Copy everything below the line into Claude Code on your PC.

---

Set me up for Campaign OS agent mail, so my Claude and Kyle's Claude can message each other (PRs to review, new skills, templates, frameworks, plugin updates) instead of us doing it by hand or in meetings.

1. Update the campaign-os plugin to 1.3.0 or newer: `claude plugin marketplace update campaign-os` then `claude plugin update campaign-os@campaign-os`. If it was not already on 1.3.0, tell me to restart Claude Code and paste this prompt again. Then read the `campaign-os-mail` skill's SKILL.md and SETUP.md.
2. Run `cos_mail.py status`. If it says READY, skip to step 5.
3. I need my own AgentMail API key (an API key, not a PAT). Tell me to go to https://agentmail.to, sign up with my email, verify the code, and create an API key. Wait for me to say I have it. Do not ask me to paste the key into this chat.
4. Find the full path of `cos_mail.py` and give me the exact command to run in a normal terminal window: `python "<full path>/cos_mail.py" setup` (use `py` or `python3` if `python` does not work). Tell me what it will ask: paste the key (hidden), pick or create an inbox (suggest `christelle-agent`), and my first name. Wait until I say it is done, then run `status` until it says READY.
5. This is agent-to-agent mail, so I go in the contact list with my agent inbox (not my personal email): run `cos_mail.py set-email christelle <my inbox>`, show me the change to contacts.json, and ask before committing and pushing it.
6. Test: dry-run an email to myself with `tell christelle ...`, ask me before sending with `--send`, then read it back with `inbox --unread`.
7. From now on: when I say "email Kyle" or "let Kyle know", use the campaign-os-mail skill (dry-run, then send once I confirm; Kyle is the developer, I am marketing). The plugin tells you at the start of each session if I have unread mail; summarise it for me. If I ask "any mail?", check my inbox.

Do the steps in order and stop to ask whenever you need something from me.
