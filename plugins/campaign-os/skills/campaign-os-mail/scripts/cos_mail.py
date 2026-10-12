#!/usr/bin/env python3
"""Campaign OS agent mail: email a teammate from your own AgentMail inbox.

Stdlib only (Windows/macOS/Linux). Dry-run unless --send.

  cos_mail.py status
  cos_mail.py contacts
  cos_mail.py set-email <id> <address>
  cos_mail.py inbox [--unread] [--limit N] [--read MESSAGE_ID]
  cos_mail.py tell <id> --subject S --message M [--kind K] [--link URL] [--how-to TEXT] [--send]

Config (never committed), first file found wins for each key:
  ~/.config/campaign-os/agent-mail.env   (or %USERPROFILE%\\.config\\campaign-os\\agent-mail.env)
  ~/.config/agent-control/agent-mail.env (Kyle's desk)
Keys:
  AGENTMAIL_API_KEY   from agentmail.to (console) or `agentmail agent sign-up`
  AGENTMAIL_INBOX     your sender address, e.g. christelle-agent@agentmail.to
  AGENTMAIL_REPLY_TO  optional; defaults to your own inbox so replies come back to your agent
  AGENTMAIL_FROM_NAME your name, used in the signature (optional)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.agentmail.to/v0"
REGISTRY = Path(__file__).resolve().parent.parent / "contacts.json"
ENV_FILES = [
    Path.home() / ".config/campaign-os/agent-mail.env",
    Path.home() / ".config/agent-control/agent-mail.env",
]
KINDS = ["update", "review", "skill", "package", "template", "framework", "question"]


def load_env() -> None:
    for f in ENV_FILES:
        if not f.is_file():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def read_registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def inbox() -> str:
    return os.environ.get("AGENTMAIL_INBOX", "").strip()


def cmd_status(_a) -> int:
    key = bool(os.environ.get("AGENTMAIL_API_KEY", "").strip())
    box = inbox()
    print(f"api key set : {key}")
    print(f"sender inbox: {box or '(missing AGENTMAIL_INBOX)'}")
    print(f"reply-to    : {os.environ.get('AGENTMAIL_REPLY_TO') or inbox() or '(your inbox)'}")
    print(f"registry    : {REGISTRY}")
    print("env files   : " + ", ".join(f"{f} ({'found' if f.is_file() else 'missing'})" for f in ENV_FILES))
    ok = key and bool(box)
    print("READY" if ok else "NOT READY: see skills/campaign-os-mail/SETUP.md")
    return 0 if ok else 1


def cmd_contacts(_a) -> int:
    for cid, c in read_registry()["contacts"].items():
        print(f"{cid:<11} {c.get('name',''):<10} {c.get('email') or '(blank - add yours)':<32} {c.get('role','')}")
    return 0


def cmd_set_email(a) -> int:
    reg = read_registry()
    if a.id not in reg["contacts"]:
        sys.exit(f"unknown contact '{a.id}'. Known: {', '.join(reg['contacts'])}")
    if "@" not in a.address:
        sys.exit("that does not look like an email address")
    reg["contacts"][a.id]["email"] = a.address
    REGISTRY.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
    print(f"{a.id} -> {a.address}. Commit and push contacts.json so everyone's Claude sees it.")
    return 0


def api_get(path: str) -> dict:
    req = urllib.request.Request(
        f"{API}{path}", headers={"Authorization": f"Bearer {os.environ['AGENTMAIL_API_KEY']}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"AgentMail HTTP {e.code}: {e.read().decode(errors='replace')}")


def cmd_inbox(a) -> int:
    if not (os.environ.get("AGENTMAIL_API_KEY") and inbox()):
        sys.exit("not set up: run status, then follow SETUP.md")
    box = urllib.parse.quote(inbox(), safe="@")
    if a.read:
        m = api_get(f"/inboxes/{box}/messages/{urllib.parse.quote(a.read, safe='')}")
        print(f"From: {m.get('from')}\nDate: {m.get('timestamp')}\nSubject: {m.get('subject')}\n\n{m.get('text') or m.get('preview') or ''}")
        return 0
    msgs = api_get(f"/inboxes/{box}/messages?limit={a.limit}").get("messages", [])
    shown = 0
    for m in msgs:
        unread = "unread" in (m.get("labels") or [])
        if a.unread and not unread:
            continue
        shown += 1
        print(f"{'*' if unread else ' '} {m.get('timestamp','')[:16]}  {str(m.get('from'))[:38]:<38}  {m.get('subject')}\n    id: {m.get('message_id')}")
    if not shown:
        print("(no messages)")
    return 0


def send(to: str, subject: str, text: str, reply_to: str | None) -> dict:
    payload = {"to": to, "subject": subject, "text": text}
    if reply_to:
        payload["reply_to"] = reply_to
    req = urllib.request.Request(
        f"{API}/inboxes/{inbox()}/messages/send",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {os.environ['AGENTMAIL_API_KEY']}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"AgentMail HTTP {e.code}: {e.read().decode(errors='replace')}")


def cmd_tell(a) -> int:
    contacts = read_registry()["contacts"]
    c = contacts.get(a.id.lower())
    if not c:
        sys.exit(f"unknown contact '{a.id}'. Known: {', '.join(contacts)}")
    if not c.get("email"):
        sys.exit(f"{c['name']} has no email yet. Run: cos_mail.py set-email {a.id} <address>")
    sender = os.environ.get("AGENTMAIL_FROM_NAME", "a teammate")
    lines = [f"Hi {c['name']},", "", a.message.strip()]
    if a.link:
        lines += ["", f"Link: {a.link}"]
    if a.how_to:
        lines += ["", f"What to do: {a.how_to}"]
    lines += ["", "-- ", f"Sent by {sender}'s Claude via Campaign OS agent mail. Reply goes to {sender}'s agent inbox."]
    body, subject = "\n".join(lines), f"[{a.kind}] {a.subject}"
    if not a.send:
        print(f"DRY RUN  to {c['name']} <{c['email']}>\nSubject: {subject}\n\n{body}\n\n(add --send to send)")
        return 0
    if not (os.environ.get("AGENTMAIL_API_KEY") and inbox()):
        sys.exit("not set up: run status, then follow SETUP.md")
    res = send(c["email"], subject, body, os.environ.get("AGENTMAIL_REPLY_TO") or inbox())
    print(f"SENT to {c['email']} from {inbox()} id={res.get('message_id') or res.get('id')}")
    return 0


def main() -> int:
    load_env()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("status").set_defaults(f=cmd_status)
    s.add_parser("contacts").set_defaults(f=cmd_contacts)
    se = s.add_parser("set-email"); se.add_argument("id"); se.add_argument("address"); se.set_defaults(f=cmd_set_email)
    ib = s.add_parser("inbox"); ib.add_argument("--unread", action="store_true")
    ib.add_argument("--limit", type=int, default=15); ib.add_argument("--read", metavar="MESSAGE_ID"); ib.set_defaults(f=cmd_inbox)
    t = s.add_parser("tell"); t.add_argument("id")
    t.add_argument("--kind", default="update", choices=KINDS)
    t.add_argument("--subject", required=True); t.add_argument("--message", required=True)
    t.add_argument("--link"); t.add_argument("--how-to"); t.add_argument("--send", action="store_true")
    t.set_defaults(f=cmd_tell)
    a = p.parse_args()
    return a.f(a)


if __name__ == "__main__":
    raise SystemExit(main())
