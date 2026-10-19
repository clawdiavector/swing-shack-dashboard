"""Automatic meta-description publishing: the safety rules, not the happy path alone.

Policy: wiki decisions/seo-geo-automation-tiers-2026-10-19. Every test runs
against a fake WordPress; nothing here can touch a real site.
"""

import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from _lib import seo_fix_queue as q  # noqa: E402
from _lib import seo_meta_publish as p  # noqa: E402

NOW = "2026-10-20T04:00:00Z"

GOOD = (
    "<style>#thegem-heading-1 {margin: 0;}</style><h1>Membership at Swing Shack</h1>"
    "<p>Think of it less like a booking and more like a home base for your game. "
    "A place where you can practise after work, tweak your gear and learn from coaches.</p>"
)


class FakeWP:
    """Pages keyed by id. behaviour: 'accept' | 'ignore' (200 but unchanged) | 'reject_meta' (400 on meta, ok on meta_input)."""

    def __init__(self, pages, behaviour="accept"):
        self.pages = {pg["id"]: {"desc": "", "status": "publish", "link": f"https://x/{pg['slug']}/", **pg} for pg in pages}
        self.behaviour = behaviour
        self.calls = []

    def _view(self, pg):
        return {
            "id": pg["id"], "slug": pg["slug"], "status": pg["status"], "link": pg["link"],
            "content": {"rendered": pg.get("html", "")},
            "meta": {},
            "yoast_head_json": {"description": pg["desc"] or None},
        }

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.startswith("/pages?slug="):
            slug = re.search(r"slug=([^&]+)", path).group(1)
            return {"ok": True, "http": 200, "data": [self._view(pg) for pg in self.pages.values() if pg["slug"] == slug]}
        m = re.match(r"/pages/(\d+)", path)
        pg = self.pages.get(int(m.group(1))) if m else None
        if pg is None:
            return {"ok": False, "http": 404, "data": {}}
        if method == "GET":
            return {"ok": True, "http": 200, "data": self._view(pg)}
        if method == "POST":
            if "meta" in payload and self.behaviour == "reject_meta":
                return {"ok": False, "http": 400, "data": {}}
            if self.behaviour != "ignore":
                key = payload.get("meta") or payload.get("meta_input") or {}
                pg["desc"] = key.get(p.META_KEY, pg["desc"])
            return {"ok": True, "http": 200, "data": self._view(pg)}
        raise AssertionError(method)

    def writes(self):
        return [c for c in self.calls if c[0] == "POST"]


class MemIO:
    def __init__(self):
        self.files = {}

    def read(self, name, allow_flat_fallback=True):
        return json.loads(json.dumps(self.files[name])) if name in self.files else None

    def write(self, name, obj):
        self.files[name] = json.loads(json.dumps(obj))
        return True


def item(ftype="missing_meta_description", page="Membership", policy=q.PUBLISH_AUTO, status="draft"):
    return {"id": f"{ftype}-{page}", "type": ftype, "page": page, "publish_policy": policy, "status": status}


def queue(*items):
    return {"brand": "swing-shack", "items": list(items)}


def site(**over):
    return FakeWP([{"id": 2255, "slug": "membership", "html": GOOD}], **over)


# ── mode ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value,expected", [(None, "off"), ("", "off"), ("on", "on"), ("ON ", "on"), ("dry-run", "dry-run"),
                                            ("true", "off"), ("1", "off"), ("yes", "off")])
def test_only_exact_values_switch_publishing_on(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv(p.ENV_MODE, raising=False)
    else:
        monkeypatch.setenv(p.ENV_MODE, value)
    assert p.mode() == expected


def test_off_makes_no_wordpress_calls_at_all():
    wp = site()
    out = p.run_auto(MemIO(), "swing-shack", queue(item()), wp, NOW, run_mode="off")
    assert wp.calls == [] and out["applied"] == 0


# ── wording ─────────────────────────────────────────────────────────────────


def test_proposal_uses_the_pages_own_whole_sentences_and_ignores_css():
    text = p.propose(GOOD)
    assert text and p.DESC_MIN <= len(text) <= p.DESC_MAX
    assert text.endswith(".") and "thegem" not in text and "{" not in text
    assert text.startswith("Think of it less like a booking")


@pytest.mark.parametrize(
    "sentence",
    [
        "Memberships start from R500 a month and include unlimited access to every simulator bay we have on site, seven days a week.",
        "Join today and save 20% on every lesson you book with one of our certified coaching staff here at the club in Johannesburg.",
        "This is the best indoor golf experience in Johannesburg for players of every level who want to improve their game quickly.",
        "Our friends at Stick in Paarl fit clubs too, and so do we, for golfers of every level who want better results on the course.",
        "Call us on 011 123 4567 to book a session with one of our coaches at the Swing Shack, any day of the week, morning or evening.",
    ],
)
def test_claims_prices_other_brands_and_contact_details_are_never_used(sentence, monkeypatch):
    html = f"<p>{sentence}</p>"
    # Control: the sentence is the right length, so only the rejection rule keeps it out.
    assert p.DESC_MIN <= len(sentence) <= p.DESC_MAX
    with monkeypatch.context() as m:
        m.setattr(p, "_REJECT", re.compile(r"(?!x)x"))
        assert p.propose(html) == sentence
    assert p.propose(html) is None


def test_no_safe_text_means_no_proposal():
    assert p.propose("<h1>Book now</h1><p>Short line.</p>") is None
    assert p.propose("") is None


# ── dry run and apply ───────────────────────────────────────────────────────


def test_dry_run_records_a_proposal_and_writes_nothing():
    wp, io = site(), MemIO()
    out = p.run_auto(io, "swing-shack", queue(item()), wp, NOW, run_mode="dry-run")
    assert out["dry_run"] == 1 and wp.writes() == []
    entry = io.files[p.LOG_FILE]["entries"][0]
    assert entry["status"] == "dry_run" and entry["before"] == "" and entry["after"].startswith("Think of it")
    # A second run proposes nothing new.
    again = p.run_auto(io, "swing-shack", queue(item()), wp, "2026-10-21T04:00:00Z", run_mode="dry-run")
    assert again["dry_run"] == 0 and len(io.files[p.LOG_FILE]["entries"]) == 1


def test_on_writes_verifies_and_logs():
    wp, io = site(), MemIO()
    out = p.run_auto(io, "swing-shack", queue(item()), wp, NOW, run_mode="on")
    assert out["applied"] == 1 and out["failed"] == []
    assert wp.pages[2255]["desc"].startswith("Think of it")
    entry = io.files[p.LOG_FILE]["entries"][0]
    assert entry["status"] == "applied" and entry["verified"] is True and entry["page_id"] == 2255
    # Running again does not write again.
    n = len(wp.writes())
    p.run_auto(io, "swing-shack", queue(item()), wp, "2026-10-21T04:00:00Z", run_mode="on")
    assert len(wp.writes()) == n


def test_a_description_a_person_wrote_is_never_touched():
    wp = site()
    wp.pages[2255]["desc"] = "Hand written by Christelle."
    out = p.run_auto(MemIO(), "swing-shack", queue(item()), wp, NOW, run_mode="on")
    assert wp.writes() == [] and wp.pages[2255]["desc"] == "Hand written by Christelle."
    assert "written by a person" in out["skipped"][0]["why"]


@pytest.mark.parametrize(
    "bad",
    [
        item(page="Homepage"),
        item(policy=q.PUBLISH_ASK),
        item(ftype="images_missing_alt"),
        item(status="dismissed"),
        item(page="Pricing"),
    ],
)
def test_only_eligible_queue_items_are_published(bad):
    wp = site()
    p.run_auto(MemIO(), "swing-shack", queue(bad), wp, NOW, run_mode="on")
    assert wp.writes() == []


def test_other_brands_are_refused():
    wp = site()
    out = p.run_auto(MemIO(), "stick", queue(item()), wp, NOW, run_mode="on")
    assert wp.calls == [] and out["applied"] == 0


def test_the_per_run_cap_is_enforced(monkeypatch):
    pages = [{"id": 100 + i, "slug": s, "html": GOOD} for i, s in enumerate(["membership", "coaching", "club-fitting"])]
    wp = FakeWP(pages)
    items = [item(page=n) for n in ["Membership", "Coaching", "Club Fitting"]]
    monkeypatch.setattr(p, "MAX_PER_RUN", 2)
    out = p.run_auto(MemIO(), "swing-shack", queue(*items), wp, NOW, run_mode="on")
    assert out["applied"] == 2
    assert sum(1 for pg in wp.pages.values() if pg["desc"]) == 2


def test_a_missing_page_is_skipped_not_fatal():
    wp = FakeWP([])
    out = p.run_auto(MemIO(), "swing-shack", queue(item(page="Coaching")), wp, NOW, run_mode="on")
    assert out["skipped"][0]["why"] == "page not found on the site" and wp.writes() == []


# ── write failures ──────────────────────────────────────────────────────────


def test_a_write_wordpress_silently_ignores_is_reported_as_failed():
    wp, io = site(behaviour="ignore"), MemIO()
    out = p.run_auto(io, "swing-shack", queue(item()), wp, NOW, run_mode="on")
    assert out["applied"] == 0 and len(out["failed"]) == 1
    entry = io.files[p.LOG_FILE]["entries"][0]
    assert entry["status"] == "failed" and entry["verified"] is False
    assert wp.pages[2255]["desc"] == ""


def test_falls_back_to_meta_input_when_meta_is_rejected():
    wp = site(behaviour="reject_meta")
    out = p.run_auto(MemIO(), "swing-shack", queue(item()), wp, NOW, run_mode="on")
    assert out["applied"] == 1 and wp.pages[2255]["desc"]


def test_an_unexpected_value_after_a_write_is_put_back():
    class Weird(FakeWP):
        def __call__(self, method, path, payload=None):
            r = super().__call__(method, path, payload)
            if method == "POST" and payload and "meta" in payload and payload["meta"][p.META_KEY]:
                self.pages[2255]["desc"] = "Something else entirely"
            return r

    wp = Weird([{"id": 2255, "slug": "membership", "html": GOOD}])
    out = p.run_auto(MemIO(), "swing-shack", queue(item()), wp, NOW, run_mode="on")
    assert out["applied"] == 0 and wp.pages[2255]["desc"] == ""


# ── undo ────────────────────────────────────────────────────────────────────


def applied(wp=None, io=None):
    wp, io = wp or site(), io or MemIO()
    p.run_auto(io, "swing-shack", queue(item()), wp, NOW, run_mode="on")
    return wp, io, io.files[p.LOG_FILE]["entries"][0]["id"]


def test_undo_restores_the_previous_value():
    wp, io, eid = applied()
    out = p.undo(io, "swing-shack", eid, wp, "2026-10-20T09:00:00Z")
    assert out["ok"] and wp.pages[2255]["desc"] == ""
    entry = io.files[p.LOG_FILE]["entries"][0]
    assert entry["status"] == "undone" and entry["undone_at"] == "2026-10-20T09:00:00Z"
    # Undoing twice is refused.
    assert not p.undo(io, "swing-shack", eid, wp, NOW)["ok"]


def test_undo_refuses_when_someone_edited_the_description_since():
    wp, io, eid = applied()
    wp.pages[2255]["desc"] = "Edited by a person after we published."
    out = p.undo(io, "swing-shack", eid, wp, NOW)
    assert not out["ok"] and "edited since" in out["error"]
    assert wp.pages[2255]["desc"] == "Edited by a person after we published."
    assert io.files[p.LOG_FILE]["entries"][0]["status"] == "applied"


def test_a_failed_undo_never_puts_the_automatic_text_back():
    wp, io, eid = applied()
    wp.behaviour = "ignore"
    out = p.undo(io, "swing-shack", eid, wp, NOW)
    assert not out["ok"]
    assert io.files[p.LOG_FILE]["entries"][0]["status"] == "applied"


@pytest.mark.parametrize("entry_id,brand", [("nope", "swing-shack"), ("x", "stick")])
def test_undo_unknown_change_or_brand(entry_id, brand):
    wp, io, _ = applied()
    assert not p.undo(io, brand, entry_id, wp, NOW)["ok"]


# ── site_audit hook ─────────────────────────────────────────────────────────


def test_site_audit_never_touches_wordpress_while_the_switch_is_off(monkeypatch, tmp_path):
    from unittest.mock import patch
    from _lib.jobs.layer1 import site_audit

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv(p.ENV_MODE, raising=False)

    def boom(*a, **k):
        raise AssertionError("WordPress must not be called while off")

    monkeypatch.setattr(p, "default_wp", boom)
    with patch.object(site_audit, "_fetch_page", return_value="<html><head><title>x</title></head><body>hi</body></html>"):
        assert site_audit.run(brand="swing-shack")["ok"]


def test_a_publish_failure_never_fails_the_audit(monkeypatch, tmp_path):
    from unittest.mock import patch
    from _lib.jobs.layer1 import site_audit

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv(p.ENV_MODE, "on")
    monkeypatch.setattr(p, "default_wp", lambda brand: (_ for _ in ()).throw(RuntimeError("boom")))
    with patch.object(site_audit, "_fetch_page", return_value="<html><head><title>x</title></head><body>hi</body></html>"):
        assert site_audit.run(brand="swing-shack")["ok"]
