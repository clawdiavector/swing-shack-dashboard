# Set up your own agent mail (about 3 minutes)

Mail is **agent to agent**: you send to the other person's `@agentmail.to` inbox and they read it with `inbox`. Humans are not on the list, so there is one copy per message. You need your own **AgentMail API key** (it is an API key, not a PAT; per person; never committed, never pasted in chat).

## Steps
1. Sign up at https://agentmail.to with your real email, verify the code they send, and create an **API key** in the dashboard. Copy it.
2. Open a **normal terminal** (not the Claude chat; it hides what you paste) and run the one command your Claude gives you, which looks like:
   ```
   python "<path to>/skills/campaign-os-mail/scripts/cos_mail.py" setup
   ```
   Paste the key when asked (it stays hidden), then pick an existing inbox or press Enter to create one (e.g. `christelle-agent`), and type your first name. It saves `~/.config/campaign-os/agent-mail.env` (Windows: `C:\Users\<you>\.config\campaign-os\agent-mail.env`) and checks the key.
3. Put your agent inbox in the contact list: `python cos_mail.py set-email christelle christelle-agent@agentmail.to`, then commit and push `contacts.json`.
4. Test: `python cos_mail.py status` says `READY`; then `python cos_mail.py tell christelle --subject test --message hello --send` and read it back with `python cos_mail.py inbox --unread`.

## How mail is checked
It is not automatic. Two things make sure it is not forgotten: on every Claude Code session start the plugin prints how many unread messages are waiting, and you can ask "any mail?" at any time. Sending takes seconds; the other agent sees it the next time that person opens Claude Code.
