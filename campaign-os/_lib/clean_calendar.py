"""The clean calendar: three views anyone can read, and a no-login link for Herman.

Christelle's ask (2026-10-29): one view for what is scheduled, one for what
needs a yes, one for ideas. Every entry says in plain words what it is, why it
is there, where and when it goes, and shows the real image. She shares a link;
Herman opens it without logging in and approves, comments or rejects.

Approving here goes through the same paths as the rest of the app:
  - a ready post: unified_inbox.approve_item (it is then scheduled to send)
  - an idea: the calendar-suggestions approve, then the post-making jobs
This module only reads, words and renders; app.py does the approving.
"""
from __future__ import annotations

import html
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

SHARE_SCOPE = "calendar_share"
SHARE_MAX_AGE = 14 * 24 * 60 * 60

BRAND_NAMES = {"swing-shack": "Swing Shack", "stick": "Stick", "bag-drop": "Bag Drop"}

_SCHEDULED = frozenset({"scheduled", "released", "posted", "partly_posted", "send_failed"})
_MAKING = frozenset({"booked", "drafting", "needs_fix", "gap"})

_CHANNEL_NAMES = {
    "instagram": "Instagram", "facebook": "Facebook", "gbp": "Google",
    "tiktok": "TikTok", "linkedin": "LinkedIn", "twitter": "X",
}

_STATUS = {
    "draft_ready": "Waiting for a yes",
    "released": "Sending now",
    "posted": "Posted",
    "partly_posted": "Posted on some channels only",
    "send_failed": "Did not send. Christelle is checking it.",
}
_MAKING_STATUS = "Being made. It comes back here for a yes."

# What a post is, from its template or post type. First match wins.
_WHAT = (
    ("story", "An Instagram story"),
    ("product", "A post showing a product we sell"),
    ("fitting", "A post about club fitting"),
    ("coach", "A post about coaching"),
    ("lesson", "A post about coaching"),
    ("price", "A post with our prices"),
    ("offer", "A post with an offer"),
    ("sale", "A post with an offer"),
    ("discount", "A post with an offer"),
    ("service", "A post about one of our services"),
    ("venue", "A post about the venue"),
    ("location", "A post about the venue"),
    ("did-you-know", "A golf tip"),
)

_IDEA_WHAT = {
    "stock": "Idea: a post about a product on this week's stock list",
    "date": "Idea: a post for this date",
}
IDEA_NEXT = "Approve it and the post gets made. It then comes back under Needs your OK for a final yes."


def _brand(brand_id: str) -> str:
    if brand_id not in BRAND_NAMES:
        raise ValueError(f"'{brand_id}' is not one of our brands")
    return brand_id


# ── share links ─────────────────────────────────────────────────────────────


def mint_share_token(serializer: Any, brand_id: str, who: str = "Herman") -> str:
    """A signed link for one brand's calendar, named for the person it is for."""
    who = (who or "").strip()[:40] or "Herman"
    return serializer.dumps({"scope": SHARE_SCOPE, "brand": _brand(brand_id), "who": who, "v": 1})


def read_share_token(serializer: Any, token: str, *, max_age: int = SHARE_MAX_AGE) -> dict[str, str] | None:
    """{"brand", "who"} for a good link; None for anything else."""
    from itsdangerous import BadSignature, SignatureExpired

    if not token:
        return None
    try:
        payload = serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict) or payload.get("scope") != SHARE_SCOPE:
        return None
    brand = payload.get("brand")
    if brand not in BRAND_NAMES:
        return None
    return {"brand": brand, "who": str(payload.get("who") or "Herman")}


# ── wording ─────────────────────────────────────────────────────────────────


def bucket_for_state(state: str) -> str | None:
    if state in _SCHEDULED:
        return "scheduled"
    if state == "draft_ready":
        return "approval"
    if state in _MAKING:
        return "making"
    return None


def _when(iso: str | None) -> str:
    try:
        d = date.fromisoformat(str(iso or "")[:10])
    except ValueError:
        return "No date yet"
    return f"{d:%a} {d.day} {d:%b}"


def _where(channels: list[str] | None) -> str:
    names = [_CHANNEL_NAMES.get(c, c.title()) for c in (channels or []) if c]
    if not names:
        return "Instagram"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _what(post_type: str | None) -> str:
    t = str(post_type or "").lower()
    for needle, words in _WHAT:
        if needle in t:
            return words
    return "A feed post"


def post_entry(row: dict[str, Any], brand_id: str, *, caption: str = "",
               comments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One calendar post in words Herman can read cold."""
    state = str(row.get("state") or "")
    bucket = bucket_for_state(state)
    making = bucket == "making"
    if state == "scheduled":
        status = f"Goes out {_when(row.get('go_live_date'))}"
    else:
        status = _MAKING_STATUS if making else _STATUS.get(state, state.replace("_", " ").capitalize())
    channels = row.get("channels_picked") or ([row["primary_channel"]] if row.get("primary_channel") else [])
    return {
        "key": str(row.get("calendar_id") or ""),
        "kind": "post",
        "view": "approval" if making else (bucket or "scheduled"),
        "making": making,
        "state": state,
        "date": str(row.get("go_live_date") or "")[:10],
        "when": _when(row.get("go_live_date")),
        "where": _where(channels),
        "brand_name": BRAND_NAMES.get(brand_id, brand_id),
        "title": str(row.get("title") or "Untitled post"),
        "what": _what(row.get("post_type") or row.get("template_id")),
        "why": str(row.get("angle") or "").strip(),
        "caption": caption or "",
        "status": status,
        "has_image": bool(row.get("image_url") or row.get("image_path")),
        "actions": ["approve", "comment", "reject"] if state == "draft_ready" else ["comment"],
        "comments": list(comments or []),
    }


def idea_entry(item: dict[str, Any], brand_id: str, *,
               comments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One suggestion from the month grid, as an idea to approve or turn down."""
    return {
        "key": str(item.get("key") or ""),
        "kind": "idea",
        "view": "ideas",
        "making": False,
        "state": "idea",
        "date": str(item.get("date") or "")[:10],
        "when": _when(item.get("date")),
        "where": "Instagram",
        "brand_name": BRAND_NAMES.get(brand_id, brand_id),
        "title": str(item.get("title") or "Untitled idea"),
        "what": _IDEA_WHAT.get(str(item.get("source") or ""), "Idea: a post for this moment"),
        "why": str(item.get("why") or "").strip(),
        "caption": "",
        "status": "Idea. Not made yet.",
        "next": IDEA_NEXT,
        "has_image": False,
        "image": None,
        "actions": ["approve", "comment", "reject"],
        "comments": list(comments or []),
    }


# ── the month ───────────────────────────────────────────────────────────────


def month_bounds(month: str) -> tuple[date, date]:
    try:
        y, m = (int(p) for p in month.split("-", 1))
        first = date(y, m, 1)
    except (ValueError, AttributeError):
        raise ValueError("month must look like 2026-11") from None
    last = date(y + (m == 12), m % 12 + 1, 1)
    return first, date.fromordinal(last.toordinal() - 1)


def post_rows(brand_id: str, month: str) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """(row, draft) for every dated post in the month, the same rows This week uses."""
    from _lib import unified_inbox as ui  # noqa: PLC0415
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    first, last = month_bounds(month)
    index = ui.build_post_index(brand_id=brand_id)
    now = datetime.now(timezone.utc)
    out = []
    for record in canonical_records(brand_id):
        if str(record.get("status") or "") not in ui._WEEK_MOMENT_STATUSES:
            continue
        go_live = ui._moment_go_live_date(record)
        try:
            d = date.fromisoformat(str(go_live or ""))
        except ValueError:
            continue
        if not first <= d <= last:
            continue
        row = ui._post_row_from_record(record, index=index, now=now)
        if "holiday" in (row.get("flags") or []) or bucket_for_state(str(row.get("state") or "")) is None:
            continue
        out.append((row, index.drafts.get(str(row.get("calendar_id") or ""))))
    return dedupe_rows(out)


# How far along a post is; the higher one wins when a post is on the calendar twice.
_PROGRESS = {"booked": 1, "drafting": 2, "gap": 2, "needs_fix": 3, "draft_ready": 4, "scheduled": 5,
             "released": 6, "partly_posted": 6, "send_failed": 6, "posted": 7}


def dedupe_rows(rows: list[tuple[dict[str, Any], Any]]) -> list[tuple[dict[str, Any], Any]]:
    """One entry per post. Approving a suggestion leaves its own record and a
    booked event beside it, same title and day; keep the one furthest along."""
    best: dict[tuple[str, str], int] = {}
    out: list[tuple[dict[str, Any], Any]] = []
    for pair in rows:
        row = pair[0]
        key = (" ".join(str(row.get("title") or "").lower().split()), str(row.get("go_live_date") or ""))
        if key not in best:
            best[key] = len(out)
            out.append(pair)
        elif _PROGRESS.get(str(row.get("state")), 0) > _PROGRESS.get(str(out[best[key]][0].get("state")), 0):
            out[best[key]] = pair
    return out


def find_post(brand_id: str, key: str) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
    """The row and draft for one calendar id, whatever its month."""
    from _lib import unified_inbox as ui  # noqa: PLC0415
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    if not key:
        return None
    index = ui.build_post_index(brand_id=brand_id)
    for record in canonical_records(brand_id):
        if str(record.get("calendar_id") or record.get("event_key") or "") == key:
            row = ui._post_row_from_record(record, index=index, now=datetime.now(timezone.utc))
            return row, index.drafts.get(key)
    return None


def month_view(brand_id: str, month: str, ideas: list[dict[str, Any]]) -> dict[str, Any]:
    _brand(brand_id)
    first, _ = month_bounds(month)
    notes = comments_by_key(brand_id)
    entries = [
        post_entry(row, brand_id, caption=str((draft or {}).get("caption") or ""),
                   comments=notes.get(str(row.get("calendar_id") or "")))
        for row, draft in post_rows(brand_id, month)
    ]
    for e in entries:
        e["image"] = f"/api/clean-calendar/{brand_id}/image/{e['key']}" if e["has_image"] else None
    entries += [idea_entry(i, brand_id, comments=notes.get(str(i.get("key") or ""))) for i in ideas]
    entries.sort(key=lambda e: (e["date"], e["view"], e["title"]))
    counts = {"scheduled": 0, "approval": 0, "ideas": 0}
    for e in entries:
        if not e["making"]:
            counts[e["view"]] += 1
    return {
        "ok": True,
        "brand": brand_id,
        "brand_name": BRAND_NAMES[brand_id],
        "month": f"{first:%Y-%m}",
        "month_label": f"{first:%B %Y}",
        "counts": counts,
        "entries": entries,
    }


def image_target(row: dict[str, Any], draft: dict[str, Any] | None) -> tuple[str, str] | None:
    """("file", path) when the image is a file here, ("app", path) when one of
    the app's own image routes serves it, ("url", url) when it is elsewhere,
    None when there is no image."""
    from _lib import unified_inbox as ui  # noqa: PLC0415

    src = {"image_path": (draft or {}).get("image_path") or row.get("image_path"),
           "image_url": (draft or {}).get("image_url") or row.get("image_url")}
    path = ui._resolve_image_path(src)
    if path is not None:
        return "file", str(path)
    url = str(src.get("image_url") or "")
    if url.startswith("https://"):
        return "url", url
    if url.startswith("/") and not url.startswith("//"):
        return "app", url.split("?", 1)[0]
    return None


# ── comments ────────────────────────────────────────────────────────────────


def _comments_path() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "calendar-comments.jsonl"


def add_comment(brand_id: str, key: str, who: str, text: str, *, action: str = "comment") -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("write something first")
    row = {
        "brand": _brand(brand_id), "key": key, "who": (who or "someone").strip()[:40],
        "text": text[:2000], "action": action,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    path = _comments_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def comments_by_key(brand_id: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    path = _comments_path()
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("brand") == brand_id and row.get("key"):
            out.setdefault(str(row["key"]), []).append(row)
    return out


# ── Herman's page ───────────────────────────────────────────────────────────

_VIEWS = (
    ("approval", "Needs your OK", "Ready posts waiting for a yes. Read it, look at the picture, then choose."),
    ("ideas", "Ideas", "Ideas only, nothing made yet. Approve one and the post gets made, then comes back under Needs your OK."),
    ("scheduled", "Scheduled", "Already approved and set to go out on these days. Comment if something should change."),
)

_LABELS = {"approve": "Approve", "comment": "Comment", "reject": "Reject"}

_PAGE_CSS = """
:root{--bg:#f6f4ef;--card:#fff;--tx:#1d1d1b;--tx2:#5f5e5a;--bd:#e3e0d8;--ok:#1d7a4f;--okbg:#e6f4ec;
--wait:#8a5a00;--waitbg:#fff4dc;--no:#a32d2d;--accent:#0c447c}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1f1f1d;--tx:#f1efe8;--tx2:#b4b2a9;--bd:#3a3936;
--ok:#7fd3a6;--okbg:#1c3327;--wait:#f0c46a;--waitbg:#3a2e14;--no:#f09595;--accent:#85b7eb}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:24px;margin:0 0 4px}p.sub{color:var(--tx2);margin:0 0 20px}
.tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:8px}
.tab{border:1px solid var(--bd);background:var(--card);border-radius:12px;padding:12px;text-align:left;cursor:pointer;color:var(--tx);font:inherit}
.tab b{display:block;font-size:26px;font-weight:600}.tab span{color:var(--tx2);font-size:14px}
.tab[aria-selected=true]{border:2px solid var(--accent)}
.hint{color:var(--tx2);font-size:14px;margin:12px 0 16px}
.card{display:flex;gap:16px;background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:16px;margin-bottom:12px}
.pic{width:180px;flex-shrink:0}.pic img{width:100%;border-radius:8px;display:block}
.pic .none{aspect-ratio:4/5;border-radius:8px;border:1px dashed var(--bd);display:flex;align-items:center;justify-content:center;color:var(--tx2);font-size:13px;text-align:center;padding:8px}
.body{min-width:0;flex:1}.meta{font-size:13px;color:var(--tx2)}h2{font-size:18px;margin:4px 0 10px}
.row{font-size:15px;margin:0 0 6px}.row b{font-weight:600}
.cap{white-space:pre-wrap;background:var(--bg);border-radius:8px;padding:10px;font-size:14px;margin:8px 0}
.pill{display:inline-block;font-size:12px;font-weight:600;border-radius:99px;padding:2px 10px;background:var(--waitbg);color:var(--wait)}
.pill.ok{background:var(--okbg);color:var(--ok)}
.btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
button.act{font:inherit;font-size:15px;border-radius:8px;padding:8px 16px;border:1px solid var(--bd);background:var(--card);color:var(--tx);cursor:pointer}
button.act[data-action=approve]{background:var(--ok);border-color:var(--ok);color:#fff}
button.act[data-action=reject]{color:var(--no)}
textarea{width:100%;font:inherit;font-size:15px;border:1px solid var(--bd);border-radius:8px;padding:8px;background:var(--card);color:var(--tx);margin-top:10px;display:none}
.note{font-size:14px;margin-top:8px}.err{color:var(--no)}.done{color:var(--ok);font-weight:600}
.said{font-size:14px;color:var(--tx2);border-left:3px solid var(--bd);padding-left:8px;margin:6px 0}
.empty{color:var(--tx2);text-align:center;padding:32px 0}
nav.months{display:flex;justify-content:space-between;margin:16px 0}nav.months a{color:var(--accent)}
@media (max-width:600px){.card{flex-direction:column}.pic{width:100%;max-width:320px}}
"""

_PAGE_JS = """
const tabs=[...document.querySelectorAll('.tab')];
function show(v){tabs.forEach(t=>t.setAttribute('aria-selected',t.dataset.view===v));
document.querySelectorAll('section[data-view]').forEach(s=>s.hidden=s.dataset.view!==v);}
tabs.forEach(t=>t.onclick=()=>show(t.dataset.view));
document.querySelectorAll('button.act').forEach(b=>b.onclick=async()=>{
 const card=b.closest('.card'),box=card.querySelector('textarea'),note=card.querySelector('.note');
 const action=b.dataset.action,need=action!=='approve';
 if(need&&box.style.display!=='block'){box.style.display='block';box.placeholder=action==='reject'?'What should change? (needed)':'Your comment';box.dataset.for=action;box.focus();return;}
 const text=box.value.trim();
 if(need&&!text){note.className='note err';note.textContent=action==='reject'?'Say what should change first.':'Write a comment first.';return;}
 card.querySelectorAll('button').forEach(x=>x.disabled=true);note.className='note';note.textContent='Saving…';
 try{const r=await fetch(location.pathname.replace(/\\/$/,'')+'/act',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({key:b.dataset.key,kind:b.dataset.kind,action,text,month:document.body.dataset.month})});
  const j=await r.json().catch(()=>({}));
  if(!r.ok||!j.ok){throw new Error(j.error||'That did not save.');}
  note.className='note done';note.textContent=j.message||'Saved.';box.style.display='none';
  if(action==='comment'){card.querySelectorAll('button').forEach(x=>x.disabled=false);box.value='';}
 }catch(e){note.className='note err';note.textContent=e.message+' Try again.';card.querySelectorAll('button').forEach(x=>x.disabled=false);}
});
show(document.body.dataset.start);
"""


def _esc(s: Any) -> str:
    return html.escape(str(s or ""), quote=True)


def _card(e: dict[str, Any], token: str) -> str:
    key = _esc(e["key"])
    if e["has_image"]:
        pic = f'<img src="/share/calendar/{_esc(token)}/image/{key}" alt="The post image" loading="lazy">'
    elif e["kind"] == "idea":
        pic = '<div class="none">No picture yet. It gets made after you approve.</div>'
    elif e["making"]:
        pic = '<div class="none">Picture being made</div>'
    else:
        pic = '<div class="none">No picture</div>'
    pill = "pill ok" if e["view"] == "scheduled" else "pill"
    rows = [f'<p class="row"><b>What it is:</b> {_esc(e["what"])}</p>']
    if e["why"]:
        rows.append(f'<p class="row"><b>Why:</b> {_esc(e["why"])}</p>')
    if e.get("next"):
        rows.append(f'<p class="row"><b>If you approve:</b> {_esc(e["next"])}</p>')
    cap = f'<div class="cap">{_esc(e["caption"])}</div>' if e["caption"] else ""
    said = "".join(
        f'<p class="said"><b>{_esc(c.get("who"))}:</b> {_esc(c.get("text"))}</p>' for c in e["comments"][-3:]
    )
    btns = "".join(
        f'<button class="act" type="button" data-key="{key}" data-kind="{_esc(e["kind"])}" '
        f'data-action="{a}">{_LABELS[a]}</button>'
        for a in e["actions"]
    )
    return (
        f'<article class="card"><div class="pic">{pic}</div><div class="body">'
        f'<p class="meta">{_esc(e["brand_name"])} · {_esc(e["where"])} · {_esc(e["when"])}</p>'
        f'<h2>{_esc(e["title"])}</h2><p><span class="{pill}">{_esc(e["status"])}</span></p>'
        f'{"".join(rows)}{cap}{said}<div class="btns">{btns}</div>'
        f'<textarea rows="3" aria-label="Your note"></textarea><p class="note" role="status"></p>'
        f"</div></article>"
    )


def _shift(month: str, step: int) -> str:
    first, _ = month_bounds(month)
    m = first.month - 1 + step
    return f"{first.year + m // 12:04d}-{m % 12 + 1:02d}"


def render_share_page(view: dict[str, Any], *, token: str, who: str) -> str:
    """The page behind Herman's link: three tabs, one card per entry, no login."""
    counts = view["counts"]
    start = next((v for v, *_ in _VIEWS if counts.get(v)), "approval")
    tabs, sections = [], []
    for v, label, hint in _VIEWS:
        tabs.append(f'<button class="tab" type="button" role="tab" data-view="{v}">'
                    f'<b>{counts.get(v, 0)}</b><span>{label}</span></button>')
        cards = [_card(e, token) for e in view["entries"] if e["view"] == v]
        body = "".join(cards) or '<p class="empty">Nothing here this month.</p>'
        sections.append(f'<section data-view="{v}"><p class="hint">{hint}</p>{body}</section>')
    base = f"/share/calendar/{_esc(token)}"
    prev_m, next_m = _shift(view["month"], -1), _shift(view["month"], 1)
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"robots\" content=\"noindex\">"
        f"<title>{_esc(view['brand_name'])} posts</title><style>{_PAGE_CSS}</style></head>"
        f'<body data-month="{_esc(view["month"])}" data-start="{start}"><main>'
        f"<h1>{_esc(view['brand_name'])} posts, {_esc(view['month_label'])}</h1>"
        f'<p class="sub">Hi {_esc(who)}. Here is what is planned. Tap a box to see that list.</p>'
        f'<div class="tabs" role="tablist">{"".join(tabs)}</div>{"".join(sections)}'
        f'<nav class="months"><a href="{base}?month={prev_m}">← Earlier month</a>'
        f'<a href="{base}?month={next_m}">Next month →</a></nav>'
        f"</main><script>{_PAGE_JS}</script></body></html>"
    )


def render_bad_link_page() -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Link expired</title>"
        f"<style>{_PAGE_CSS}</style></head><body><main><h1>This link has expired or is not right</h1>"
        "<p class=\"sub\">Ask Christelle for a new link.</p></main></body></html>"
    )
