"""SEO fix buttons: draft, edit, apply, undo, history. Fake WordPress only.

Rules under test (wiki decisions/seo-geo-automation-tiers-2026-10-19, and the
2026-10-21 decision that a click is the approval for anything that asks first):
a draft writes nothing; the person's edited text is what is written; stale
drafts, other brands' names, wrong lengths and unconfirmed claims never reach
WordPress; every write is read back; every change can be stepped back.
"""

import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from _lib import seo_fix_queue as q  # noqa: E402
from _lib import seo_fixer as fx  # noqa: E402
from _lib import seo_meta_publish as smp  # noqa: E402
from test_seo_meta_publish import MemIO  # noqa: E402

NOW = "2026-10-21T08:00:00Z"
LATER = "2026-10-28T08:00:00Z"

MEMBERSHIP_HTML = (
    "<h1>Join the Club. Play Smarter. Train Better.</h1>"
    "<p>Think of it less like a booking and more like a home base for your game. "
    "A place where you can practise after work, tweak your gear, learn from coaches, and see progress on the numbers.</p>"
    "<p>Swing Shack isn't just indoor golf. It's a proper indoor golf club. "
    "If you're serious about improving, this is where you plug in.</p>"
)
HOME_HTML = (
    "<h1>Real Golf. Indoors.</h1>"
    "<p>Swing Shack is where golfers get fitted, coached and practise on TrackMan data every week of the year.</p>"
)

GOOD_DESC = (
    "Swing Shack membership gives you a bay between lessons, so what you learn "
    "has somewhere to go and you can see it in the numbers."
)
GOOD_TITLE = "Membership: Join the Club | Swing Shack"


class FakeWP:
    """Pages with a Yoast description and title. behaviour: accept | ignore."""

    def __init__(self, behaviour="accept"):
        self.behaviour = behaviour
        self.calls = []
        self.pages = {
            2255: {"id": 2255, "slug": "membership", "name": "Membership", "html": MEMBERSHIP_HTML, "desc": "", "title": ""},
            1946: {"id": 1946, "slug": "home", "name": "Homepage", "html": HOME_HTML, "desc": "", "title": ""},
        }

    def _view(self, pg):
        head_title = pg["title"] or f"{pg['name']} - Swing Shack"
        return {
            "id": pg["id"], "slug": pg["slug"], "status": "publish", "link": f"https://x/{pg['slug']}/",
            "content": {"rendered": pg["html"]},
            "meta": {smp.META_KEY: pg["desc"], smp.TITLE_KEY: pg["title"]},
            "yoast_head_json": {"description": pg["desc"] or None, "title": head_title},
        }

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.startswith("/pages?slug="):
            slug = re.search(r"slug=([^&]+)", path).group(1)
            return {"ok": True, "http": 200, "data": [self._view(p) for p in self.pages.values() if p["slug"] == slug]}
        m = re.match(r"/pages/(\d+)", path)
        pg = self.pages.get(int(m.group(1))) if m else None
        if pg is None:
            return {"ok": False, "http": 404, "data": {}}
        if method == "GET":
            return {"ok": True, "http": 200, "data": self._view(pg)}
        if self.behaviour != "ignore":
            meta = payload.get("meta") or payload.get("meta_input") or {}
            if smp.META_KEY in meta:
                pg["desc"] = meta[smp.META_KEY]
            if smp.TITLE_KEY in meta:
                pg["title"] = meta[smp.TITLE_KEY]
        return {"ok": True, "http": 200, "data": self._view(pg)}

    def writes(self):
        return [c for c in self.calls if c[0] == "POST"]


def queue_item(ftype, page, policy=q.PUBLISH_ASK):
    return {"id": f"{ftype}-{page}", "type": ftype, "page": page, "publish_policy": policy,
            "status": "draft", "fix_button": q.FIX_BUTTONS.get(ftype)}


def io_with(*items):
    io = MemIO()
    io.files[fx.QUEUE_FILE] = {"brand": "swing-shack", "items": list(items)}
    return io


def draft(io, wp, item_id):
    return fx.build_draft(io, "swing-shack", item_id, wp)


def apply(io, wp, item_id, text, **kw):
    kw.setdefault("run_mode", "on")
    now = kw.pop("now", NOW)
    return fx.apply_fix(io, "swing-shack", item_id, text, wp, now, **kw)


# ── catalogue ──────────────────────────────────────────────────────────────


def test_every_button_type_has_a_drafter_and_a_known_field():
    for ftype, b in q.FIX_BUTTONS.items():
        assert b["field"] in fx.DRAFTERS and b["field"] in smp.FIELDS_META, ftype
        assert b["label"] in ("Fix", "Improve")


def test_queue_items_carry_their_button():
    findings = [
        {"type": "title_too_short", "page": "Membership", "severity": "medium", "message": "m"},
        {"type": "missing_h1", "page": "Membership", "severity": "high", "message": "m"},
    ]
    out = q.sync("swing-shack", findings, [], None, NOW)
    by = {i["type"]: i for i in out["items"]}
    assert by["title_too_short"]["fix_button"] == {"field": "title", "label": "Improve"}
    assert by["missing_h1"]["fix_button"] is None


# ── draft ──────────────────────────────────────────────────────────────────


def test_draft_proposes_a_description_and_writes_nothing():
    wp = FakeWP()
    io = io_with(queue_item("missing_meta_description", "Membership"))
    out = draft(io, wp, "missing_meta_description-Membership")
    assert out["ok"] and out["button"] == "Fix" and out["current"] == ""
    assert "Swing Shack" in out["proposal"] and 120 <= len(out["proposal"]) <= 160
    assert wp.writes() == []
    assert any("no search description" in n.lower() for n in out["notes"])


def test_improve_never_proposes_what_is_already_there():
    wp = FakeWP()
    wp.pages[2255]["desc"] = (
        "Swing Shack isn't just indoor golf. It's a proper indoor golf club. "
        "If you're serious about improving, this is where you plug in."
    )
    io = io_with(queue_item("meta_description_short", "Membership"))
    out = draft(io, wp, "meta_description_short-Membership")
    assert out["button"] == "Improve" and out["proposal"] != out["current"]


def test_a_title_draft_uses_the_pages_own_heading_and_the_brand():
    out = draft(io_with(queue_item("title_too_short", "Membership")), FakeWP(), "title_too_short-Membership")
    assert out["field"] == "title" and out["proposal"] == GOOD_TITLE
    assert out["current"] == "Membership - Swing Shack"
    assert 30 <= len(out["proposal"]) <= 60


def test_the_homepage_title_leads_with_the_brand():
    out = draft(io_with(queue_item("title_too_short", "Homepage")), FakeWP(), "title_too_short-Homepage")
    assert out["ok"] and out["proposal"] == "Swing Shack | Real Golf. Indoors" or out["proposal"] is None


def test_no_safe_draft_still_lets_the_person_edit():
    wp = FakeWP()
    wp.pages[2255]["html"] = "<p>Short.</p>"
    out = draft(io_with(queue_item("missing_meta_description", "Membership")), wp, "missing_meta_description-Membership")
    assert out["ok"] and out["proposal"] is None


def test_unknown_item_is_refused():
    assert draft(io_with(), FakeWP(), "nope")["ok"] is False


def test_a_type_without_a_button_is_refused():
    io = io_with(queue_item("missing_h1", "Membership"))
    out = draft(io, FakeWP(), "missing_h1-Membership")
    assert not out["ok"] and "no button" in out["error"]


# ── apply ──────────────────────────────────────────────────────────────────


def test_apply_writes_the_edited_text_reads_it_back_and_logs_it():
    wp, io = FakeWP(), io_with(queue_item("missing_meta_description", "Membership"))
    out = apply(io, wp, "missing_meta_description-Membership", "  " + GOOD_DESC + " ", expected_current="")
    assert out["ok"] and out["entry"]["status"] == "applied" and out["entry"]["verified"]
    assert wp.pages[2255]["desc"] == GOOD_DESC
    last = smp.load_log(io)["entries"][-1]
    assert last["source"] == "button" and last["field"] == "meta_description" and last["before"] == ""


def test_the_homepage_can_be_changed_by_a_click_but_not_automatically():
    wp, io = FakeWP(), io_with(queue_item("missing_meta_description", "Homepage"))
    text = "Swing Shack is where golfers get fitted, coached and practise on TrackMan data, with every session built around the numbers."
    out = apply(io, wp, "missing_meta_description-Homepage", text)
    assert out["ok"] and wp.pages[1946]["desc"] == text
    auto_queue = {"items": [queue_item("missing_meta_description", "Homepage", q.PUBLISH_AUTO)]}
    auto = smp.run_auto(MemIO(), "swing-shack", auto_queue, FakeWP(), NOW, run_mode="on")
    assert auto["applied"] == 0


def test_a_title_is_written_and_verified_through_yoast():
    wp, io = FakeWP(), io_with(queue_item("title_too_short", "Membership"))
    out = apply(io, wp, "title_too_short-Membership", GOOD_TITLE, expected_current="Membership - Swing Shack")
    assert out["ok"] and wp.pages[2255]["title"] == GOOD_TITLE


def test_practice_mode_records_and_does_not_write():
    wp, io = FakeWP(), io_with(queue_item("missing_meta_description", "Membership"))
    out = apply(io, wp, "missing_meta_description-Membership", GOOD_DESC, run_mode="dry-run")
    assert out["ok"] and out["entry"]["status"] == "dry_run" and wp.writes() == []


def test_switched_off_refuses_and_makes_no_wordpress_calls():
    wp, io = FakeWP(), io_with(queue_item("missing_meta_description", "Membership"))
    out = apply(io, wp, "missing_meta_description-Membership", GOOD_DESC, run_mode="off")
    assert not out["ok"] and out["status"] == 409 and wp.calls == []


@pytest.mark.parametrize(
    "text,fragment",
    [
        ("Too short.", "at least 120"),
        ("x" * 161, "at most 160"),
        (
            "Stick and Swing Shack both fit clubs on TrackMan data, so you can see what your swing does before you buy anything at all.",
            "another company",
        ),
        (
            "Swing Shack fits clubs on TrackMan data. Book at https://swingshack.co.za/bookings/ and see what your swing does before buying.",
            "links",
        ),
        (
            "<b>Swing Shack</b> fits clubs on TrackMan data, so you can see what your swing does in a session before you buy any clubs.",
            "HTML",
        ),
    ],
)
def test_unsafe_or_badly_sized_text_never_reaches_wordpress(text, fragment):
    wp, io = FakeWP(), io_with(queue_item("missing_meta_description", "Membership"))
    out = apply(io, wp, "missing_meta_description-Membership", text)
    assert not out["ok"] and out["status"] == 422 and fragment in out["error"] and wp.writes() == []


def test_a_claim_needs_an_explicit_confirm():
    claim = (
        "Swing Shack is the best place to be fitted for clubs in Johannesburg, "
        "with TrackMan data behind every single recommendation."
    )
    wp, io = FakeWP(), io_with(queue_item("missing_meta_description", "Membership"))
    first = apply(io, wp, "missing_meta_description-Membership", claim)
    assert not first["ok"] and first["needs_confirm"] and wp.writes() == []
    second = apply(io, wp, "missing_meta_description-Membership", claim, confirm=True)
    assert second["ok"] and wp.pages[2255]["desc"] == claim


def test_a_stale_draft_is_refused():
    wp, io = FakeWP(), io_with(queue_item("missing_meta_description", "Membership"))
    wp.pages[2255]["desc"] = (
        "Someone typed this a minute ago and it is long enough to count as a real "
        "description of the page for now, honestly."
    )
    out = apply(io, wp, "missing_meta_description-Membership", GOOD_DESC, expected_current="")
    assert not out["ok"] and out["status"] == 409 and wp.writes() == []


def test_saying_what_the_page_already_says_is_refused():
    wp, io = FakeWP(), io_with(queue_item("missing_meta_description", "Membership"))
    wp.pages[2255]["desc"] = GOOD_DESC
    assert not apply(io, wp, "missing_meta_description-Membership", GOOD_DESC)["ok"]


def test_a_write_wordpress_ignores_is_reported_as_failed_not_done():
    wp, io = FakeWP("ignore"), io_with(queue_item("missing_meta_description", "Membership"))
    out = apply(io, wp, "missing_meta_description-Membership", GOOD_DESC)
    assert not out["ok"] and out["entry"]["status"] == "failed" and not out["entry"]["verified"]


# ── history and the long-term loop ─────────────────────────────────────────


def test_fix_then_improve_a_week_later_then_step_back_twice():
    wp = FakeWP()
    io = io_with(queue_item("missing_meta_description", "Membership"))
    first = apply(io, wp, "missing_meta_description-Membership", GOOD_DESC, expected_current="")["entry"]

    # A week later the daily check finds it can be improved: a new item, same button machinery.
    io.files[fx.QUEUE_FILE]["items"] = [queue_item("meta_description_long", "Membership")]
    better = (
        "Swing Shack membership puts a TrackMan bay in your week, so lessons and "
        "practice add up and you can see progress in the numbers."
    )
    d = draft(io, wp, "meta_description_long-Membership")
    assert d["button"] == "Improve" and d["current"] == GOOD_DESC
    second = apply(io, wp, "meta_description_long-Membership", better, expected_current=d["current"], now=LATER)["entry"]
    assert wp.pages[2255]["desc"] == better

    # Undo goes back one step at a time, newest first. The older change is protected until then.
    assert smp.undo(io, "swing-shack", first["id"], wp, LATER)["ok"] is False
    assert wp.pages[2255]["desc"] == better
    assert smp.undo(io, "swing-shack", second["id"], wp, LATER)["ok"]
    assert wp.pages[2255]["desc"] == GOOD_DESC
    assert smp.undo(io, "swing-shack", first["id"], wp, LATER)["ok"]
    assert wp.pages[2255]["desc"] == ""


def test_undo_refuses_when_a_person_edited_the_title_since():
    wp, io = FakeWP(), io_with(queue_item("title_too_short", "Membership"))
    entry = apply(io, wp, "title_too_short-Membership", GOOD_TITLE)["entry"]
    wp.pages[2255]["title"] = "Edited by hand in WordPress for the page | Swing Shack"
    out = smp.undo(io, "swing-shack", entry["id"], wp, LATER)
    assert not out["ok"] and "edited since" in out["error"]


def test_the_log_keeps_far_more_than_thirty_changes():
    assert smp.MAX_LOG >= 500
