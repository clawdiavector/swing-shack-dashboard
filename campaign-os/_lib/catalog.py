"""Campaign catalog: a review pack kept in sync with a plan's post and story steps."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Callable

from _lib import campaign_plan as cp
from _lib import review_pack as rp
from _lib.jobs.brand_lanes import load_brands_registry

_INDEX_NAME = "_catalog_index.json"
_SLOT_KINDS = frozenset({"post", "story"})


class CatalogError(ValueError):
    pass


def _root() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "review-packs"


def _index_path() -> Path:
    return _root() / _INDEX_NAME


def _index_key(brand_id: str, plan_id: str) -> str:
    return f"{brand_id}:{plan_id}"


def _read_index() -> dict[str, str]:
    return json.loads(_index_path().read_text(encoding="utf-8")) if _index_path().is_file() else {}


def _write_index(data: dict[str, str]) -> None:
    p = _index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def catalog_for_plan(brand_id: str, plan_id: str) -> str | None:
    return _read_index().get(_index_key(brand_id, plan_id))


def _brand_title(brand_id: str) -> str:
    reg = load_brands_registry()
    row = (reg.get("brands") or {}).get(brand_id) or {}
    return str(row.get("display_name") or brand_id).strip()


def _plan_live(plan: dict[str, Any]) -> None:
    if plan.get("status") in (cp.PLAN_SUPERSEDED, cp.PLAN_ARCHIVED):
        raise CatalogError("This plan was replaced; open the newer one.")


def _format_when(due: str) -> str:
    try:
        d = date.fromisoformat(str(due)[:10])
    except ValueError:
        return str(due)[:120]
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def _channels(item: dict[str, Any]) -> str:
    ch = str(item.get("channel") or "").strip()
    pt = str(item.get("post_type") or "").strip()
    if ch and pt:
        return f"{ch}, {pt}"
    return ch or pt


def _caption(plan: dict[str, Any], item: dict[str, Any]) -> str:
    cap = str(item.get("caption") or "").strip()
    if cap:
        return cap[:4000]
    cid = str(item.get("calendar_id") or "").strip()
    if not cid:
        return ""
    try:
        from _lib import marketing_calendar as mc

        row = mc._newest_row(plan["brand_id"], cid)
    except Exception:
        row = None
    if not row:
        return ""
    for key in ("caption", "body", "angle", "content"):
        bit = str(row.get(key) or "").strip()
        if bit:
            return bit[:4000]
    return ""


def _slot_raw(plan: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["item_id"],
        "title": str(item.get("title") or "")[:200],
        "kind": "single",
        "caption": _caption(plan, item),
        "channels": _channels(item)[:200],
        "when": _format_when(str(item.get("due") or "")),
        "due": str(item.get("due") or "")[:10],
        "note": str(item.get("note") or "")[:600],
        "plan_item_id": item["item_id"],
    }


def _catalog_title(plan: dict[str, Any]) -> str:
    return f"{plan.get('event_name') or 'Campaign'} — {_brand_title(plan['brand_id'])}"


def _create_catalog_pack(plan: dict[str, Any]) -> dict[str, Any]:
    pack = rp.create_empty_pack(
        _catalog_title(plan),
        extra={
            "kind": "catalog",
            "plan_id": plan["plan_id"],
            "brand_id": plan["brand_id"],
            "event_name": plan.get("event_name") or "",
            "client": _brand_title(plan["brand_id"]),
        },
    )
    idx = _read_index()
    idx[_index_key(plan["brand_id"], plan["plan_id"])] = pack["id"]
    _write_index(idx)
    return pack


def ensure_for_plan(brand_id: str, plan_id: str) -> dict[str, Any]:
    plan = cp.get_plan(brand_id, plan_id)
    if not plan:
        raise CatalogError("That plan is not there.")
    _plan_live(plan)
    pack_id = catalog_for_plan(brand_id, plan_id)
    if not pack_id or rp.get_pack(pack_id) is None:
        pack = _create_catalog_pack(plan)
        pack_id = pack["id"]
    sync(brand_id, plan_id)
    return {"pack_id": pack_id}


def _visible_ids(pack: dict[str, Any]) -> set[str]:
    return {i["id"] for i in pack.get("items") or []}


def _removed_ids(pack: dict[str, Any]) -> set[str]:
    return {r["id"] for r in pack.get("removed_items") or [] if r.get("id")}


def _same_slot(item: dict[str, Any], raw: dict[str, Any]) -> bool:
    for key in ("title", "caption", "channels", "when", "due", "note"):
        if str(item.get(key) or "") != str(raw.get(key) or ""):
            return False
    return True


def sync(brand_id: str, plan_id: str) -> dict[str, int]:
    plan = cp.get_plan(brand_id, plan_id)
    if not plan:
        raise CatalogError("That plan is not there.")
    pack_id = catalog_for_plan(brand_id, plan_id)
    if not pack_id:
        raise CatalogError("This plan has no catalog yet.")
    pack = rp.get_pack(pack_id)
    if not pack:
        raise CatalogError("That catalog is not there.")

    added = removed = updated = 0
    for item in plan.get("items") or []:
        if item.get("kind") not in _SLOT_KINDS:
            continue
        iid = item["item_id"]
        raw = _slot_raw(plan, item)
        pack = rp.get_pack(pack_id) or pack
        visible = _visible_ids(pack)
        gone = _removed_ids(pack)

        if item.get("status") == "removed":
            if iid in visible:
                rp.remove_item(pack_id, iid)
                removed += 1
            continue

        if iid in gone:
            rp.restore_item(pack_id, iid)
            added += 1
            pack = rp.get_pack(pack_id) or pack
            visible = _visible_ids(pack)

        if iid not in visible:
            rp.add_item(pack_id, raw)
            added += 1
            continue

        cur = next(i for i in pack["items"] if i["id"] == iid)
        if not _same_slot(cur, raw):
            rp.update_item_fields(
                pack_id,
                iid,
                {k: raw[k] for k in ("title", "caption", "channels", "when", "due", "note")},
            )
            updated += 1

    rp.patch_pack(
        pack_id,
        event_name=plan.get("event_name") or "",
        title=_catalog_title(plan),
    )
    pics = refresh_pictures(brand_id, plan_id)
    return {
        "added": added,
        "removed": removed,
        "updated": updated,
        "pictures_added": pics.get("pictures_added", 0),
        "pictures_skipped": pics.get("pictures_skipped", 0),
    }


def _draft_caption(state: dict[str, Any]) -> str:
    for key in ("caption", "body", "angle", "content"):
        bit = str(state.get(key) or "").strip()
        if bit:
            return bit[:4000]
    return ""


def _post_state_once(brand_id: str) -> Callable[[str, str], dict[str, Any] | None]:
    """post_state_for builds the brand's whole post index per call. Build it once per
    refresh instead, so a 20-slot catalog does not rebuild it 20 times."""
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415
    from _lib.unified_inbox import build_post_index, post_state  # noqa: PLC0415

    cache: dict[str, Any] = {}

    def lookup(_brand: str, calendar_id: str) -> dict[str, Any] | None:
        if "records" not in cache:
            cache["index"] = build_post_index(brand_id=brand_id)
            cache["records"] = {
                str(r.get("calendar_id") or r.get("event_key") or ""): r
                for r in canonical_records(brand_id)
            }
        rec = cache["records"].get(calendar_id)
        return post_state(rec, index=cache["index"]) if rec else None

    return lookup


def refresh_pictures(
    brand_id: str,
    plan_id: str,
    *,
    post_state: Callable[[str, str], dict[str, Any] | None] | None = None,
    load_bytes: Callable[[str, str], bytes | None] | None = None,
) -> dict[str, int]:
    """Pull composed pictures from post state into catalog slots (feed, story, Google)."""
    from _lib.feed_vertical_renders import (
        FEED_RENDER_CHANNEL,
        fit_for_channel_png,
        fit_google_4x3,
        _load_png_for_url,
    )

    if post_state is None:
        post_state = _post_state_once(brand_id)
    if load_bytes is None:
        load_bytes = _load_png_for_url

    plan = cp.get_plan(brand_id, plan_id)
    pack_id = catalog_for_plan(brand_id, plan_id)
    if not plan or not pack_id:
        return {"pictures_added": 0, "pictures_skipped": 0}

    added = skipped = 0
    for row in plan.get("items") or []:
        if row.get("kind") not in _SLOT_KINDS:
            continue
        cid = str(row.get("calendar_id") or "").strip()
        if not cid:
            continue
        st = post_state(brand_id, cid)
        if not st:
            continue
        composed = st.get("composed") or {}
        feed_url = str(composed.get(FEED_RENDER_CHANNEL) or composed.get("instagram") or "").strip()
        if not feed_url:
            continue
        raw = load_bytes(brand_id, feed_url)
        if not raw:
            continue
        content_hash = hashlib.sha256(raw).hexdigest()[:32]
        pack = rp.get_pack(pack_id)
        if not pack:
            continue
        slot = next((i for i in pack.get("items") or [] if i["id"] == row["item_id"]), None)
        if not slot:
            continue
        already = content_hash in (slot.get("picture_hashes") or [])
        if not already:
            story_url = str(composed.get("instagram_story") or "").strip()
            if story_url:
                story_raw = load_bytes(brand_id, story_url)
                if not story_raw:
                    story_raw, _ = fit_for_channel_png(raw, "instagram_story")
            else:
                story_raw, _ = fit_for_channel_png(raw, "instagram_story")
            google_raw = None
            google_url = str(composed.get("google_business") or composed.get("gbp") or "").strip()
            if google_url:
                google_raw = load_bytes(brand_id, google_url)
            if not google_raw:
                google_raw, _ = fit_google_4x3(raw)
            out = rp.add_catalog_picture(
                pack_id,
                row["item_id"],
                raw,
                source_url=feed_url,
                content_hash=content_hash,
                story_data=story_raw,
                google_data=google_raw,
            )
            if out.get("skipped"):
                skipped += 1
            else:
                added += 1
        else:
            skipped += 1
        draft_cap = _draft_caption(st)
        if draft_cap:
            pack = rp.get_pack(pack_id) or pack
            slot = next(i for i in pack["items"] if i["id"] == row["item_id"])
            empty = not str(slot.get("caption") or "").strip()
            auto = slot.get("caption_auto", True)
            if empty or auto:
                rp.update_item_fields(pack_id, row["item_id"], {"caption": draft_cap, "caption_auto": True})
    return {"pictures_added": added, "pictures_skipped": skipped, "added": added}


def counts(pack_id: str) -> dict[str, int]:
    pack = rp.get_pack(pack_id)
    if not pack:
        return {"posts": 0, "pictures": 0, "pictures_yet": 0}
    items = pack.get("items") or []
    posts = len(items)
    pictures = sum(1 for i in items if i.get("images"))
    return {"posts": posts, "pictures": pictures, "pictures_yet": max(0, posts - pictures)}


def catalog_header(pack: dict[str, Any]) -> str:
    if pack.get("kind") != "catalog":
        return ""
    items = pack.get("items") or []
    n = len(items)
    whens = [str(i.get("when") or "").strip() for i in items if i.get("when")]
    dates = whens[0] if len(whens) == 1 else (f"{whens[0]} – {whens[-1]}" if whens else "")
    event = str(pack.get("event_name") or "").strip() or str(pack.get("title") or "").split("—")[0].strip()
    c = counts(pack["id"])
    bits = [
        f"Campaign: {event or 'this plan'}",
        f"{n} post" + ("" if n == 1 else "s"),
        f"{c['pictures']} with pictures",
    ]
    if dates:
        bits.append(dates)
    return " · ".join(bits)


CATALOG_LABELS = {"approve": "Love it", "hold": "Maybe", "reject": "No"}
HOLD_REASON = "Waiting for a remake (marked Maybe/No)"
UPLOAD_PURPOSES = frozenset({"reference", "element", "post"})
_SLOTS_NAME = "catalog_slots.json"
_AUDIT_NAME = "catalog_audit.jsonl"


def labels_for(pack: dict[str, Any]) -> dict[str, str] | None:
    if pack.get("kind") != "catalog":
        return None
    return dict(CATALOG_LABELS)


def _slots_path(pack_id: str) -> Path:
    return _root() / pack_id / _SLOTS_NAME


def slot_states(pack_id: str) -> dict[str, dict[str, Any]]:
    return json.loads(_slots_path(pack_id).read_text(encoding="utf-8")) if _slots_path(pack_id).is_file() else {}


def _write_slots(pack_id: str, data: dict[str, dict[str, Any]]) -> None:
    p = _slots_path(pack_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def mark_summary(pack_id: str) -> dict[str, Any]:
    """How many slots are marked, for the campaign-yes line on the page."""
    pack = rp.get_pack(pack_id)
    if not pack:
        return {"total": 0, "marked": 0, "approve": 0, "hold": 0, "reject": 0, "unmarked": 0, "line": "", "items": []}
    decisions = rp.view(pack_id)["decisions"]
    items = pack.get("items") or []
    counts = {"approve": 0, "hold": 0, "reject": 0, "unmarked": 0}
    rows = []
    for it in items:
        if it.get("kind") == "note":
            continue
        d = decisions.get(it["id"])
        state = d.get("state") if isinstance(d, dict) else None
        if state == "pending":
            state = None
        if state in counts:
            counts[state] += 1
        else:
            counts["unmarked"] += 1
        rows.append({"id": it["id"], "state": state or "unmarked"})
    total = len(rows)
    marked = total - counts["unmarked"]
    parts = [f"{marked} of {total} marked"]
    if counts["approve"]:
        parts.append(f"{counts['approve']} Love it")
    if counts["hold"]:
        parts.append(f"{counts['hold']} Maybe")
    if counts["reject"]:
        parts.append(f"{counts['reject']} No")
    if counts["unmarked"]:
        parts.append(f"{counts['unmarked']} not marked")
    return {**counts, "total": total, "marked": marked, "line": ". ".join(parts) + ".", "items": rows}


def is_held(brand_id: str, calendar_id: str) -> bool:
    """True when Herman held this post in the campaign catalog and it was not cleared."""
    cid = str(calendar_id or "").strip()
    if not brand_id or not cid:
        return False
    try:
        from _lib import marketing_calendar as mc

        row = mc._newest_row(brand_id, cid)
    except Exception:
        row = None
    return bool(row and row.get("catalog_hold"))


def catalog_hold_error() -> str:
    return "Herman marked this Maybe/No in the campaign catalog. Remake it or clear the hold first."


def release_blocked(brand_id: str, calendar_id: str) -> str | None:
    """Plain error when a held catalog post cannot be approved yet; None when it can."""
    return catalog_hold_error() if is_held(brand_id, calendar_id) else None


def _append_audit(pack_id: str, row: dict[str, Any]) -> None:
    p = _root() / pack_id / _AUDIT_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _slot_brand_plan(pack: dict[str, Any]) -> tuple[str, str]:
    return str(pack.get("brand_id") or ""), str(pack.get("plan_id") or "")


def _plan_item_for_slot(brand_id: str, plan_id: str, slot_id: str) -> dict[str, Any] | None:
    plan = cp.get_plan(brand_id, plan_id)
    if not plan:
        return None
    return next((i for i in plan.get("items") or [] if i["item_id"] == slot_id), None)


def _set_plan_hold(brand_id: str, plan_id: str, item_id: str, held: bool, who: str) -> None:
    cp.edit_item(brand_id, plan_id, item_id, {"catalog_hold": held}, actor=who)


def _set_calendar_hold(brand_id: str, calendar_id: str, held: bool, who: str) -> None:
    if not calendar_id:
        return
    from _lib import marketing_calendar as mc

    mc.set_fields(brand_id, calendar_id, {"catalog_hold": held}, reason=f"catalog campaign yes by {who}")


def approve_campaign(pack_id: str, who: str, uid: str | None = None) -> dict[str, Any]:
    """Record the campaign yes: slot release flags and holds on plan and calendar. Sends nothing."""
    pack = rp.get_pack(pack_id)
    if not pack or pack.get("kind") != "catalog":
        raise CatalogError("That is not a catalog pack.")
    brand_id, plan_id = _slot_brand_plan(pack)
    summary = mark_summary(pack_id)
    decisions = rp.view(pack_id)["decisions"]
    slots: dict[str, dict[str, Any]] = {}
    for it in pack.get("items") or []:
        if it.get("kind") == "note":
            continue
        iid = it["id"]
        d = decisions.get(iid)
        state = d.get("state") if isinstance(d, dict) else None
        if state == "pending":
            state = None
        love = state == "approve"
        held = not love
        slots[iid] = {
            "release_ok": love,
            "held": held,
            "hold_reason": HOLD_REASON if held else "",
        }
        plan_item = _plan_item_for_slot(brand_id, plan_id, iid)
        if plan_item:
            _set_plan_hold(brand_id, plan_id, iid, held, who)
            cid = str(plan_item.get("calendar_id") or "").strip()
            _set_calendar_hold(brand_id, cid, held, who)
    _write_slots(pack_id, slots)
    from _lib.review_pack import _now

    stamp = _now()
    approval = {
        "by": (who or "someone").strip()[:40],
        "uid": str(uid).strip()[:80] if uid else "",
        "at": stamp,
        "counts": {k: summary[k] for k in ("approve", "hold", "reject", "unmarked", "total", "marked")},
    }
    rp.patch_pack(pack_id, campaign_approval=approval)
    _append_audit(pack_id, {"at": stamp, "who": approval["by"], "uid": approval["uid"], "event": "campaign_approved", "counts": approval["counts"]})
    return {"ok": True, "campaign_approval": approval}


def clear_hold(pack_id: str, item_id: str, who: str) -> dict[str, Any]:
    """Editor clears a catalog hold so the post can be released as it is."""
    pack = rp.get_pack(pack_id)
    if not pack or pack.get("kind") != "catalog":
        raise CatalogError("That is not a catalog pack.")
    _item(pack, item_id)
    slots = slot_states(pack_id)
    row = slots.get(item_id) or {}
    from _lib.review_pack import _now

    row.update({"held": False, "release_ok": True, "hold_reason": "", "cleared_by": who, "cleared_at": _now()})
    slots[item_id] = row
    _write_slots(pack_id, slots)
    brand_id, plan_id = _slot_brand_plan(pack)
    _set_plan_hold(brand_id, plan_id, item_id, False, who)
    plan_item = _plan_item_for_slot(brand_id, plan_id, item_id)
    if plan_item:
        _set_calendar_hold(brand_id, str(plan_item.get("calendar_id") or ""), False, who)
    _append_audit(pack_id, {"at": row["cleared_at"], "who": who, "event": "clear_hold", "item_id": item_id})
    return {"ok": True, "item_id": item_id}


def _item(pack: dict[str, Any], item_id: str) -> dict[str, Any]:
    item = next((i for i in pack.get("items") or [] if i["id"] == item_id), None)
    if not item:
        raise CatalogError("That post is not in this pack.")
    return item


def list_catalog_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rp.list_packs():
        pack = rp.get_pack(row["id"])
        if not pack or pack.get("kind") != "catalog":
            continue
        c = counts(pack["id"])
        out.append(
            {
                "id": pack["id"],
                "title": pack.get("title", ""),
                "kind": "catalog",
                "plan_id": pack.get("plan_id", ""),
                "brand": pack.get("brand_id", ""),
                "counts": c,
            }
        )
    return out


# ── C6 month strip and drag ───────────────────────────────────────────────────

MARK_DOT_COLOURS = {
    "approve": "#0e7a4f",
    "hold": "#d97706",
    "reject": "#a3262f",
    "unmarked": "#9ca3af",
}

REMAKE_BATCH_LIMIT = 4
_REMAKE_DIR = "catalog-remakes"
_FEEDBACK_NAME = "catalog-feedback.jsonl"


def _mark_for_slot(pack_id: str, slot_id: str) -> str:
    d = rp.view(pack_id)["decisions"].get(slot_id)
    if not isinstance(d, dict):
        return "unmarked"
    state = d.get("state")
    if state == "pending" or not state:
        return "unmarked"
    if state in MARK_DOT_COLOURS:
        return str(state)
    return "unmarked"


def month_strip_view(pack_id: str) -> dict[str, Any]:
    """Days in this campaign with dots coloured by Love it / Maybe / No."""
    pack = rp.get_pack(pack_id)
    if not pack or pack.get("kind") != "catalog":
        return {"months": []}
    brand_id, plan_id = _slot_brand_plan(pack)
    plan = cp.get_plan(brand_id, plan_id) or {}
    by_day: dict[str, list[dict[str, Any]]] = {}
    for item in plan.get("items") or []:
        if item.get("kind") not in _SLOT_KINDS or item.get("status") == "removed":
            continue
        due = str(item.get("due") or "")[:10]
        if not due:
            continue
        mark = _mark_for_slot(pack_id, item["item_id"])
        by_day.setdefault(due, []).append(
            {"slot_id": item["item_id"], "mark": mark, "colour": MARK_DOT_COLOURS[mark]}
        )
    if not by_day:
        return {"months": []}
    days_sorted = sorted(by_day)
    months_out: list[dict[str, Any]] = []
    cur_key = ""
    cur_month: dict[str, Any] | None = None
    for iso in days_sorted:
        try:
            d = date.fromisoformat(iso)
        except ValueError:
            continue
        key = f"{d.year}-{d.month:02d}"
        if key != cur_key:
            cur_key = key
            cur_month = {
                "year": d.year,
                "month": d.month,
                "label": d.strftime("%b %Y"),
                "days": [],
            }
            months_out.append(cur_month)
        assert cur_month is not None
        cur_month["days"].append({"iso": iso, "dots": by_day[iso], "first_slot": by_day[iso][0]["slot_id"]})
    return {"months": months_out}


def staff_can_drag(*, staff: bool, session_user: dict[str, Any] | None, share_role: str | None) -> bool:
    if not staff or share_role == "approver":
        return False
    if not session_user:
        return False
    from _lib import users

    return users.can(session_user, "move")


def move_slot_day(
    pack_id: str,
    item_id: str,
    new_date: str,
    who: str,
    *,
    calendar_move: Callable[[str, dict[str, Any], str], tuple[dict[str, Any], int]] | None = None,
    plan_edit: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Move a catalog slot to another day (calendar post or plan due)."""
    pack = rp.get_pack(pack_id)
    if not pack or pack.get("kind") != "catalog":
        raise CatalogError("That is not a catalog pack.")
    brand_id, plan_id = _slot_brand_plan(pack)
    plan_item = _plan_item_for_slot(brand_id, plan_id, item_id)
    if not plan_item:
        raise CatalogError("That post is not in this plan.")
    due = str(new_date or "")[:10]
    if len(due) < 10:
        raise CatalogError("Send the new day, like 2026-11-20.")
    cid = str(plan_item.get("calendar_id") or "").strip()
    if cid:
        if calendar_move is None:
            raise CatalogError("Calendar move is not available here.")
        body = {"key": cid, "kind": "post", "date": due}
        out, _code = calendar_move(brand_id, body, who)
        if not out.get("ok"):
            raise CatalogError(str(out.get("error") or out.get("message") or "Could not move it."))
        # Keep the plan step on the same day as its calendar entry, so the slot moves too.
        edit = plan_edit or (lambda b, p, i, patch, actor="operator": cp.edit_item(b, p, i, patch, actor=actor))
        edit(brand_id, plan_id, item_id, {"due": due}, who)
    else:
        edit = plan_edit or (lambda b, p, i, patch, actor="operator": cp.edit_item(b, p, i, patch, actor=actor))
        r = edit(brand_id, plan_id, item_id, {"due": due}, who)
        if not r.get("ok"):
            raise CatalogError(str(r.get("error") or "Could not change the date."))
    sync(brand_id, plan_id)
    return {"ok": True, "item_id": item_id, "due": due}


# ── C7 remake from notes ──────────────────────────────────────────────────────


def _remake_path(moment: str) -> Path:
    safe = hashlib.sha256(moment.encode()).hexdigest()[:24]
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / _REMAKE_DIR / f"{safe}.json"


def write_remake_brief(moment: str, brief: dict[str, Any]) -> Path:
    p = _remake_path(moment)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"moment": moment, "brief": brief, "at": rp._now()}  # noqa: SLF001
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    _append_generation_log(moment, brief)
    return p


def load_remake_brief_text(moment: str) -> str:
    p = _remake_path(moment)
    if not p.is_file():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    brief = data.get("brief") if isinstance(data, dict) else {}
    if not isinstance(brief, dict):
        return ""
    return str(brief.get("prompt_text") or "").strip()[:8000]


def _append_generation_log(moment: str, brief: dict[str, Any]) -> None:
    root = Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / _REMAKE_DIR
    root.mkdir(parents=True, exist_ok=True)
    row = {"at": rp._now(), "moment": moment, "catalog_remake": True, "brief": brief.get("prompt_text", "")[:2000]}
    with (root / "generation.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_remake_brief(pack_id: str, slot_id: str, *, token: str = "") -> dict[str, Any]:
    """Notes, Love-it lookalikes, and reference uploads for one slot."""
    pack = rp.get_pack(pack_id)
    if not pack:
        raise CatalogError("That catalog is not there.")
    v = rp.view(pack_id)
    notes = [
        c["text"]
        for c in (v["comments"].get(slot_id) or [])
        if c.get("role") == "client" and str(c.get("text") or "").strip()
    ]
    loved: list[dict[str, str]] = []
    base = f"/review-pack/{token}" if token else ""
    for it in pack.get("items") or []:
        if it.get("kind") == "note" or it["id"] == slot_id:
            continue
        dec = v["decisions"].get(it["id"])
        state = dec.get("state") if isinstance(dec, dict) else None
        if state in ("hold", "reject"):
            continue
        if state != "approve" and not (it.get("images") and state in (None, "pending")):
            continue
        urls = []
        if it.get("images") and base:
            urls.append(f"{base}/image/{it['id']}/{len(it['images']) - 1}")
        loved.append({"slot_id": it["id"], "caption": str(it.get("caption") or "")[:500], "picture_urls": urls})
    refs = [
        {"purpose": u.get("purpose"), "text": u.get("text"), "url": f"{base}/file/{u['file']}" if base and u.get("file") else ""}
        for u in v["uploads"]
        if u.get("item") == slot_id and u.get("purpose") in ("reference", "element")
    ]
    parts = []
    if notes:
        parts.append("Change requested: " + " | ".join(notes))
    if loved:
        parts.append("Match this look from Love it slots: " + json.dumps(loved, ensure_ascii=False))
    if refs:
        parts.append("Reference uploads: " + json.dumps(refs, ensure_ascii=False))
    prompt_text = "\n".join(parts)
    return {"notes": notes, "loved_look": loved, "reference_uploads": refs, "prompt_text": prompt_text}


def remake_from_notes(
    pack_id: str,
    who: str,
    *,
    request_draft: Callable[..., dict[str, Any]] | None = None,
    limit: int = REMAKE_BATCH_LIMIT,
) -> dict[str, Any]:
    """Queue remakes for Maybe/No slots. Love-it slots are not touched."""
    pack = rp.get_pack(pack_id)
    if not pack or pack.get("kind") != "catalog":
        raise CatalogError("That is not a catalog pack.")
    brand_id, plan_id = _slot_brand_plan(pack)
    draft_fn = request_draft or cp.request_draft
    injected = request_draft is not None
    decisions = rp.view(pack_id)["decisions"]
    waiting: list[dict[str, str]] = []
    queued: list[str] = []
    skipped_love: list[str] = []
    for it in pack.get("items") or []:
        if it.get("kind") == "note":
            continue
        iid = it["id"]
        dec = decisions.get(iid)
        state = dec.get("state") if isinstance(dec, dict) else None
        if state == "approve":
            skipped_love.append(iid)
            continue
        if state not in ("hold", "reject"):
            continue
        plan_item = _plan_item_for_slot(brand_id, plan_id, iid)
        if not plan_item:
            continue
        cid = str(plan_item.get("calendar_id") or "").strip()
        moment = f"calendar_candidate:{brand_id}:{cid}" if cid else f"plan_step:{brand_id}:{plan_id}:{iid}"
        if not cid:
            waiting.append({"item_id": iid, "error": "Put the plan on the calendar first, so the remake can be drafted."})
            if not injected:
                continue
        if len(queued) >= limit:
            waiting.append({"item_id": iid, "error": "Waiting for the next batch."})
            continue
        brief = build_remake_brief(pack_id, iid)
        write_remake_brief(moment, brief)
        r = draft_fn(brand_id, plan_id, iid, who)
        if r.get("ok"):
            queued.append(iid)
        else:
            err = str(r.get("error") or "Could not queue the remake.")
            if err == "only a post step can be drafted":
                err = "Stories are not drafted by the machine yet. Remake this one by hand, using the note."
            waiting.append({"item_id": iid, "error": err})
    out: dict[str, Any] = {"ok": True, "queued": queued, "skipped_love": skipped_love, "waiting": waiting}
    if waiting and queued:
        out["more_waiting"] = True
        out["message"] = f"{len(queued)} queued. Press again after you have checked them."
    elif len(queued) >= limit and any(w.get("error", "").startswith("Waiting") for w in waiting):
        out["more_waiting"] = True
        out["message"] = "4 queued. Press again after you have checked them."
    return out


def show_remake_to_client(pack_id: str, item_id: str, who: str) -> dict[str, Any]:
    """Christelle shows a remade picture to Herman; mark goes back to unmarked."""
    pack = rp.get_pack(pack_id)
    if not pack:
        raise CatalogError("That catalog is not there.")
    item = _item(pack, item_id)
    meta = list(item.get("picture_meta") or [])
    changed = False
    for row in reversed(meta):
        if row.get("remake") and row.get("shown_to_client") is False:
            row["shown_to_client"] = True
            row["shown_by"] = who
            row["shown_at"] = rp._now()  # noqa: SLF001
            changed = True
            break
    if not changed:
        raise CatalogError("There is no remake waiting to show.")
    rp.update_item_fields(pack_id, item_id, {"picture_meta": meta})
    rp.clear_decision(pack_id, item_id)
    return {"ok": True, "item_id": item_id}


def show_all_remakes_to_client(pack_id: str, who: str) -> dict[str, Any]:
    pack = rp.get_pack(pack_id)
    if not pack:
        raise CatalogError("That catalog is not there.")
    shown = 0
    for it in pack.get("items") or []:
        if it.get("kind") == "note":
            continue
        meta = it.get("picture_meta") or []
        if any(row.get("remake") and row.get("shown_to_client") is False for row in meta):
            try:
                show_remake_to_client(pack_id, it["id"], who)
                shown += 1
            except CatalogError:
                pass
    return {"ok": True, "shown": shown}


def log_catalog_feedback(
    brand_id: str,
    pack_id: str,
    plan_id: str,
    item_id: str,
    who: str,
    mark: str,
    note: str,
    picture_url: str,
) -> None:
    root = Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "brands" / brand_id
    root.mkdir(parents=True, exist_ok=True)
    row = {
        "at": rp._now(),  # noqa: SLF001
        "pack_id": pack_id,
        "plan_id": plan_id,
        "item_id": item_id,
        "who": (who or "")[:40],
        "mark": mark,
        "note": (note or "")[:2000],
        "picture_url": (picture_url or "")[:500],
    }
    with (root / _FEEDBACK_NAME).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def feedback_from_mark(pack_id: str, item_id: str, mark: str, who: str, *, token: str = "", note: str = "") -> None:
    pack = rp.get_pack(pack_id)
    if not pack or pack.get("kind") != "catalog":
        return
    brand_id, plan_id = _slot_brand_plan(pack)
    base = f"/review-pack/{token}" if token else ""
    pack_item = next((i for i in pack.get("items") or [] if i["id"] == item_id), None)
    idx = max(0, len((pack_item or {}).get("images") or []) - 1)
    url = f"{base}/image/{item_id}/{idx}" if base else ""
    log_catalog_feedback(brand_id, pack_id, plan_id, item_id, who, mark, note, url)


def client_picture_index(item: dict[str, Any], *, staff: bool) -> int:
    images = item.get("images") or []
    if not images:
        return -1
    if staff:
        return len(images) - 1
    meta = item.get("picture_meta") or []
    if meta and meta[-1].get("remake") and meta[-1].get("shown_to_client") is False and len(images) > 1:
        return len(images) - 2
    return len(images) - 1
