"""Owner mail copies Kyle's agent. Replies stay with the sender."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTACTS = ROOT / "plugins/campaign-os/skills/campaign-os-mail/contacts.json"
SPEC = importlib.util.spec_from_file_location(
    "cos_mail_cc", ROOT / "plugins/campaign-os/skills/campaign-os-mail/scripts/cos_mail.py")
cos_mail = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cos_mail)

HERMAN = "therealclawdius@agentmail.to"
KYLE = "kyleomarchydeveloper@agentmail.to"
CHRISTELLE = "clawdia001@agentmail.to"
HERMAN_WORK = "hermank@fivefriday.com"


class _Resp:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"message_id":"m-test"}'


def _capture(monkeypatch):
    sent = []

    def fake(req, timeout=60):
        sent.append(json.loads(req.data.decode()))
        return _Resp()

    monkeypatch.setattr(cos_mail.urllib.request, "urlopen", fake)
    monkeypatch.setenv("AGENTMAIL_API_KEY", "test-not-a-secret")
    return sent


def test_herman_is_the_owner_who_copies_kyle():
    contacts = json.loads(CONTACTS.read_text(encoding="utf-8"))["contacts"]
    assert contacts["herman"]["cc_kyle"] is True
    assert contacts["herman"]["email"] == HERMAN
    assert not contacts["kyle"].get("cc_kyle")
    assert not contacts["christelle"].get("cc_kyle")
    owners = [cid for cid, c in contacts.items() if c.get("cc_kyle")]
    assert owners == ["herman"]


def test_send_to_herman_ccs_kyle_when_christelle_sends(monkeypatch):
    sent = _capture(monkeypatch)
    monkeypatch.setenv("AGENTMAIL_INBOX", CHRISTELLE)
    cos_mail.send(HERMAN, "Black Friday", "body", CHRISTELLE)
    assert len(sent) == 1
    assert sent[0]["to"] == HERMAN
    assert sent[0]["cc"] == KYLE
    assert sent[0]["reply_to"] == CHRISTELLE
    assert not sent[0]["subject"].startswith("[cc]")


def test_kyle_sending_to_herman_does_not_cc_himself(monkeypatch):
    sent = _capture(monkeypatch)
    monkeypatch.setenv("AGENTMAIL_INBOX", KYLE)
    cos_mail.send(HERMAN, "note", "body", KYLE)
    assert len(sent) == 1
    assert "cc" not in sent[0]


def test_send_to_christelle_has_no_owner_cc(monkeypatch):
    sent = _capture(monkeypatch)
    monkeypatch.setenv("AGENTMAIL_INBOX", "other-agent@agentmail.to")
    cos_mail.send(CHRISTELLE, "plugin", "body", "other-agent@agentmail.to")
    assert "cc" not in sent[0]


def test_work_notice_is_not_a_second_copy_to_kyle(monkeypatch):
    sent = _capture(monkeypatch)
    monkeypatch.setenv("AGENTMAIL_INBOX", CHRISTELLE)
    cos_mail.send(HERMAN_WORK, "You have agent mail", "notice", None)
    assert len(sent) == 1
    assert "cc" not in sent[0]
    assert "reply_to" not in sent[0]
