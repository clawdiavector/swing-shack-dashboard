# Set up your own agent mail (about 5 minutes)

You need two things: an **AgentMail API key** and a **sender inbox**. It is an API key, not a PAT. Keys are per person and are never committed or shared. The key on Kyle's machine does not exist on yours, so you make your own.

## Steps
1. Go to https://agentmail.to and sign up with your real email (or run `npm install -g agentmail-cli` then `agentmail agent sign-up --human-email <you@example.com> --username <name>-agent --source campaign-os --format json`). Verify the one-time code sent to you.
2. In the AgentMail console create an **API key** and copy it. Create (or reuse) an **inbox**, e.g. `christelle-agent@agentmail.to`. Free tier is plenty.
3. Create the file `.config/campaign-os/agent-mail.env` in your home folder (Windows: `C:\Users\<you>\.config\campaign-os\agent-mail.env`) containing:
   ```
   AGENTMAIL_API_KEY=am_xxxxxxxx
   AGENTMAIL_INBOX=christelle-agent@agentmail.to
   AGENTMAIL_REPLY_TO=your-real-email@example.com
   AGENTMAIL_FROM_NAME=Christelle
   ```
   Never paste the key into chat, a commit, or the wiki.
4. Put your real email in the contact list: `python cos_mail.py set-email christelle your-real-email@example.com`, then commit and push `contacts.json`.
5. Check: `python cos_mail.py status` -> `READY`. Then send yourself a test:
   `python cos_mail.py tell christelle --subject "test" --message "hello" --send`
   (New AgentMail accounts may only deliver to your verified address at first; that is fine for the test.)

## Prompt to give your Claude
See `PROMPT-FOR-CHRISTELLE.md` in this folder.
