"""mail_intake.py — mail from Herman, filed as a Do now or an Idea.

Herman writes to the agent inbox in English or Afrikaans. A message from an
allowed sender is sorted into one of two piles and Christelle gets a short
notice:

  do_now  something to act on (a request, a fix, a deadline). When unsure it
          goes here, so nothing is buried.
  idea    a suggestion. With a brand and a future date it goes straight onto
          the calendar as a faded suggestion, ready for Approve. Without,
          it waits on the Today page for someone to pick the brand and date.

The sort is by plain rules, not a model: an explicit "DO:" or "IDEA:" tag wins,
otherwise the words used decide. Mail text is data. It is trimmed, stored and
shown as text; nothing in it is ever run or followed.

Store: <DATA_DIR>/mail-intake/items.json. The AgentMail calls are injected so
the logic is testable; `run_intake_live` wires the real ones from env.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

BRANDS = ("swing-shack", "stick", "bag-drop")
KINDS = ("do_now", "idea")
STATUSES = ("open", "done", "dismissed")
SUMMARY_MAX = 600
AGENTMAIL_API = "https://api.agentmail.to/v0"

_DO_TAG = re.compile(r"^\s*(?:do|do now|now|must|must do|doen|moet|dringend|urgent)\s*[:\-–]", re.I)
_IDEA_TAG = re.compile(r"^\s*(?:idea|ideas|idee|idees|voorstel|suggestion)\s*[:\-–]", re.I)

_IDEA_WORDS = (
    "idea", "ideas", "idee", "idees", "what if", "wat as", "we could", "ons kan",
    "suggest", "suggestion", "voorstel", "stel voor", "thought", "maybe", "miskien",
    "consider", "brainstorm", "would be cool", "sal cool wees", "imagine",
)
_DO_WORDS = (
    "please", "asseblief", "urgent", "dringend", "asap", "today", "vandag", "now",
    "nou", "need", "moet", "must", "fix", "change", "verander", "can you", "kan jy",
    "could you", "reply", "antwoord", "deadline", "by tomorrow",
)

_MONTHS = {
    "jan": 1, "january": 1, "januarie": 1, "feb": 2, "february": 2, "februarie": 2,
    "mar": 3, "march": 3, "maart": 3, "apr": 4, "april": 4, "may": 5, "mei": 5,
    "jun": 6, "june": 6, "junie": 6, "jul": 7, "july": 7, "julie": 7,
    "aug": 8, "august": 8, "augustus": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "okt": 10, "october": 10, "oktober": 10, "nov": 11, "november": 11,
    "dec": 12, "des": 12, "december": 12, "desember": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_RE})\b(?:,?\s+(20\d\d))?", re.I)
_MONTH_DAY = re.compile(rf"\b({_MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(20\d\d))?", re.I)


# ── pure sorting ──────────────────────────────────────────────────────

def _words(text: str, words) -> int:
    low = f" {text.lower()} "
    return sum(1 for w in words if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low))


def classify(subject: str, body: str) -> tuple[str, str]:
    """(kind, reason). An explicit tag wins; otherwise the words decide; a tie is do_now."""
    first_line = (body or "").strip().splitlines()[0] if (body or "").strip() else ""
    for line in (subject or "", first_line):
        if _IDEA_TAG.match(line):
            return "idea", "tagged as an idea"
        if _DO_TAG.match(line):
            return "do_now", "tagged as something to do"
    text = f"{subject}\n{body}"
    idea, do = _words(text, _IDEA_WORDS), _words(text, _DO_WORDS)
    if idea > do:
        return "idea", "reads like a suggestion"
    if do:
        return "do_now", "reads like a request"
    return "do_now", "not clear, so kept where it will be seen"


def detect_brand(text: str) -> Optional[str]:
    """The one brand a message names, or None. Never a default: two brands or none means ask."""
    found = set()
    if re.search(r"\bStick\b", text) or re.search(r"\bstick\s+(?:golf|paarl)\b", text, re.I):
        found.add("stick")
    if re.search(r"\bswing\s*shack\b", text, re.I):
        found.add("swing-shack")
    if re.search(r"\bbag\s*drop\b", text, re.I):
        found.add("bag-drop")
    return found.pop() if len(found) == 1 else None


def extract_date(text: str, today: date) -> Optional[date]:
    """The earliest date in the text that is today or later. No year means the next one coming."""
    found: List[date] = []

    def add(y: Optional[int], m: int, d: int) -> None:
        try:
            if y is None:
                c = date(today.year, m, d)
                if c < today:
                    c = date(today.year + 1, m, d)
            else:
                c = date(y, m, d)
        except ValueError:
            return
        if c >= today:
            found.append(c)

    for m in _ISO.finditer(text or ""):
        add(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    for m in _DAY_MONTH.finditer(text or ""):
        add(int(m.group(3)) if m.group(3) else None, _MONTHS[m.group(2).lower()], int(m.group(1)))
    for m in _MONTH_DAY.finditer(text or ""):
        add(int(m.group(3)) if m.group(3) else None, _MONTHS[m.group(1).lower()], int(m.group(2)))
    return min(found) if found else None


def sender_address(from_field: Any) -> str:
    s = str(from_field or "")
    m = re.search(r"<([^>]+)>", s)
    return (m.group(1) if m else s).strip().lower()


def _contacts_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "..", "plugins", "campaign-os", "skills",
                        "campaign-os-mail", "contacts.json")


def allowed_senders() -> set:
    """Herman's addresses. MAIL_INTAKE_SENDERS (comma separated) overrides the shared contacts file."""
    env = os.environ.get("MAIL_INTAKE_SENDERS", "").strip()
    if env:
        return {a.strip().lower() for a in env.split(",") if a.strip()}
    try:
        with open(_contacts_path(), encoding="utf-8") as f:
            c = (json.load(f).get("contacts") or {}).get("herman") or {}
    except (OSError, ValueError):
        return set()
    return {str(c.get(k)).strip().lower() for k in ("email", "notify_email") if c.get(k)}


def _clean_body(text: str) -> str:
    """Drop quoted replies and signatures' tails; keep what the sender wrote."""
    out = []
    for line in str(text or "").splitlines():
        if line.startswith(">") or re.match(r"^On .+ wrote:\s*$", line):
            break
        out.append(line)
    return "\n".join(out).strip()


# ── the store ─────────────────────────────────────────────────────────

def _path() -> str:
    return os.path.join(os.environ.get("DATA_DIR", "data"), "mail-intake", "items.json")


def _read() -> List[Dict[str, Any]]:
    try:
        with open(_path(), encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, list) else []
    except (OSError, ValueError):
        return []


def _write(items: List[Dict[str, Any]]) -> None:
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def known_message_ids() -> set:
    return {i.get("message_id") for i in _read()}


def list_items(brand: Optional[str] = None, kind: Optional[str] = None,
               status: Optional[str] = "open") -> List[Dict[str, Any]]:
    """Newest first. A brand filter keeps items with no brand yet: they could be that brand's."""
    out = []
    for i in _read():
        if status and i.get("status") != status:
            continue
        if kind and i.get("kind") != kind:
            continue
        if brand and i.get("brand") not in (None, "", brand):
            continue
        out.append(i)
    out.sort(key=lambda i: i.get("received_at") or "", reverse=True)
    return out


def get_item(item_id: str) -> Optional[Dict[str, Any]]:
    return next((i for i in _read() if i.get("id") == item_id), None)


def _update(item_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    items = _read()
    for i in items:
        if i.get("id") == item_id:
            i.update(fields)
            _write(items)
            return i
    return None


def _needs(item: Dict[str, Any]) -> List[str]:
    if item.get("kind") != "idea" or item.get("calendar_id"):
        return []
    return [n for n, v in (("brand", item.get("brand")), ("date", item.get("date"))) if not v]


def set_status(item_id: str, status: str) -> Optional[Dict[str, Any]]:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    return _update(item_id, status=status)


def set_kind(item_id: str, kind: str) -> Optional[Dict[str, Any]]:
    """Move it to the other pile. Herman's wording can be read wrong; this is the fix."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    cur = get_item(item_id)
    if not cur:
        return None
    cur = dict(cur, kind=kind)
    return _update(item_id, kind=kind, needs=_needs(cur))


def set_brand_date(item_id: str, brand: Optional[str], day: Optional[str]) -> Optional[Dict[str, Any]]:
    if brand is not None and brand not in BRANDS:
        raise ValueError("unknown brand")
    cur = get_item(item_id)
    if not cur:
        return None
    new = dict(cur)
    if brand is not None:
        new["brand"] = brand
    if day is not None:
        new["date"] = day
    return _update(item_id, brand=new.get("brand"), date=new.get("date"), needs=_needs(new))


def mark_on_calendar(item_id: str, calendar_id: str) -> Optional[Dict[str, Any]]:
    return _update(item_id, calendar_id=calendar_id, needs=[])


def file_message(m: Dict[str, Any], today: date) -> Optional[Dict[str, Any]]:
    """File one message. None when the sender is not allowed or it is already filed."""
    if sender_address(m.get("from")) not in allowed_senders():
        return None
    mid = str(m.get("message_id") or "")
    if not mid or mid in known_message_ids():
        return None
    subject = str(m.get("subject") or "").strip()
    body = _clean_body(m.get("text") or m.get("preview") or "")
    kind, why = classify(subject, body)
    whole = f"{subject}\n{body}"
    d = extract_date(whole, today)
    item = {
        "id": "mi-" + hashlib.sha1(mid.encode()).hexdigest()[:10],
        "message_id": mid,
        "from": sender_address(m.get("from")),
        "subject": subject[:200],
        "summary": body[:SUMMARY_MAX],
        "kind": kind,
        "reason": why,
        "brand": detect_brand(whole),
        "date": d.isoformat() if d else None,
        "status": "open",
        "calendar_id": None,
        "received_at": str(m.get("timestamp") or ""),
        "filed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    item["needs"] = _needs(item)
    items = _read()
    items.append(item)
    _write(items)
    return item


# ── the job ───────────────────────────────────────────────────────────

def _notice_text(new: List[Dict[str, Any]]) -> str:
    lines = [f"Herman sent {len(new)} message{'s' if len(new) != 1 else ''} to the agent inbox. Filed for you:", ""]
    for i in new:
        label = "Do now" if i["kind"] == "do_now" else "Idea"
        extra = ""
        if i["kind"] == "idea":
            extra = " (on the calendar, waiting for your Approve)" if i.get("calendar_id") else (
                f" (needs {' and '.join(i['needs'])} before it can go on the calendar)" if i.get("needs") else "")
        lines.append(f"- {label}: {i['subject'] or '(no subject)'}{extra}")
    lines += ["", "Open the Today page to see them."]
    return "\n".join(lines)


def run_intake(fetch: Callable[[], List[Dict[str, Any]]],
               notify: Callable[[str, str, str], Any],
               add_suggestion: Callable[[str, Dict[str, Any]], str],
               today: date) -> Dict[str, Any]:
    if not allowed_senders():
        return {"ok": False, "error": "no allowed senders: set MAIL_INTAKE_SENDERS"}
    new = []
    for m in fetch():
        it = file_message(m, today)
        if not it:
            continue
        if it["kind"] == "idea" and not it["needs"]:
            try:
                cid = add_suggestion(it["brand"], it)
                mark_on_calendar(it["id"], cid)
                it = get_item(it["id"]) or it
            except Exception as e:  # keep the item; a person can add it by hand
                _update(it["id"], calendar_error=str(e)[:200])
        new.append(it)
    out = {"ok": True, "filed": len(new),
           "do_now": sum(1 for i in new if i["kind"] == "do_now"),
           "ideas": sum(1 for i in new if i["kind"] == "idea")}
    if new:
        to = os.environ.get("MAIL_INTAKE_NOTIFY_TO", "").strip()
        if not to:
            out["notice_skipped"] = "MAIL_INTAKE_NOTIFY_TO is not set"
        else:
            try:
                notify(to, f"Herman: {out['do_now']} to do, {out['ideas']} idea{'s' if out['ideas'] != 1 else ''}",
                       _notice_text(new))
            except Exception as e:
                out["notice_failed"] = True
                out["notice_error"] = str(e)[:200]
    return out


# ── the real AgentMail and calendar calls ─────────────────────────────

def _api(method: str, path: str, payload: Optional[dict] = None) -> dict:
    req = urllib.request.Request(
        AGENTMAIL_API + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {os.environ['AGENTMAIL_API_KEY']}",
                 "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def _fetch_live() -> List[Dict[str, Any]]:
    box = urllib.parse.quote(os.environ["AGENTMAIL_INBOX"].strip(), safe="@")
    allowed, known = allowed_senders(), known_message_ids()
    out = []
    for m in _api("GET", f"/inboxes/{box}/messages?limit=50").get("messages", []):
        if sender_address(m.get("from")) not in allowed or m.get("message_id") in known:
            continue
        full = _api("GET", f"/inboxes/{box}/messages/{urllib.parse.quote(str(m['message_id']), safe='')}")
        out.append({**m, **{k: v for k, v in full.items() if v}})
    return out


def _notify_live(to: str, subject: str, text: str) -> None:
    box = urllib.parse.quote(os.environ["AGENTMAIL_INBOX"].strip(), safe="@")
    _api("POST", f"/inboxes/{box}/messages/send", {"to": to, "subject": subject, "text": text})


def idea_title(item: Dict[str, Any]) -> str:
    t = re.sub(r"^\s*(?:idea|ideas|idee|idees|voorstel|suggestion)\s*[:\-–]\s*", "",
               item.get("subject") or "", flags=re.I).strip()
    if not t:
        s = (item.get("summary") or "").strip()
        t = s.splitlines()[0] if s else ""
    return (t or "Idea from Herman")[:80]


def add_suggestion_live(brand: str, item: Dict[str, Any]) -> str:
    """File the idea as a faded suggestion on the calendar. Nothing is approved here."""
    from _lib import marketing_calendar as mc  # noqa: PLC0415
    why = (item.get("summary") or "")[:400]
    rec = mc.add_candidate(brand, {
        "type": "campaign", "title": idea_title(item),
        "event_start": item["date"], "event_end": item["date"], "public_peak": item["date"],
        "summary": why, "why_it_matters": why or "Idea from Herman",
        "source_type": "operator", "source": "OPERATOR_PROVIDED", "created_by": "operator",
        "is_suggested": True, "origin_note_id": item["id"], "pillars": [],
    }, initial_status="candidate")
    return rec.get("calendar_id") or ""


def configured() -> Dict[str, bool]:
    """What is set on this server, so the page can say plainly when nobody is watching the inbox."""
    return {
        "inbox": bool(os.environ.get("AGENTMAIL_API_KEY", "").strip() and os.environ.get("AGENTMAIL_INBOX", "").strip()),
        "senders": bool(allowed_senders()),
        "notice": bool(os.environ.get("MAIL_INTAKE_NOTIFY_TO", "").strip()),
    }


def run_intake_live(today: Optional[date] = None) -> Dict[str, Any]:
    if not (os.environ.get("AGENTMAIL_API_KEY", "").strip() and os.environ.get("AGENTMAIL_INBOX", "").strip()):
        return {"ok": False, "error": "AGENTMAIL_API_KEY and AGENTMAIL_INBOX are not set on this server"}
    if today is None:
        try:
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo("Africa/Johannesburg")).date()
        except Exception:
            today = date.today() + timedelta(0)
    try:
        return run_intake(_fetch_live, _notify_live, add_suggestion_live, today)
    except (urllib.error.URLError, OSError) as e:
        return {"ok": False, "error": f"AgentMail could not be reached: {e}"}
