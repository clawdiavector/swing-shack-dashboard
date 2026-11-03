"""Stick gets its own SEO checks and Fix/Improve buttons, kept apart from Swing Shack.

Found 2026-10-28: the daily site check audited Swing Shack's page list on stickgolf.co.za
(/membership is a 404 there), the fix queue and buttons were Swing Shack only, and Stick's
homepage, Club Fitting and Coaching pages all share one search description.
Fake WordPress only.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from _lib import seo_fix_queue as q  # noqa: E402
from _lib import seo_fixer as fx  # noqa: E402
from _lib import seo_meta_publish as smp  # noqa: E402
from _lib.jobs.layer1 import site_audit  # noqa: E402
from test_seo_meta_publish import MemIO  # noqa: E402

NOW = "2026-10-28T08:00:00Z"

STICK_FITTING_HTML = (
    "<h1>Club Fitting at Stick</h1>"
    "<p>Stick fits clubs on TrackMan in Paarl, so every recommendation comes from your own swing numbers. "
    "Book a session to see your numbers.</p>"
)


# ── the site check uses each brand's real pages ────────────────────────────


def test_stick_audits_its_own_pages_not_swing_shacks():
    suffixes = [p["url_suffix"] for p in site_audit.pages_for("stick")]
    assert "/club-fitting-at-stick" in suffixes and "/coaching-at-stick" in suffixes
    assert "/membership" not in suffixes


def test_swing_shack_pages_are_unchanged():
    assert site_audit.pages_for("swing-shack") == site_audit.PAGES


def test_duplicate_descriptions_are_flagged_on_every_page_that_shares_one():
    same = "Trackman fittings and golf coaching at Stick in Paarl."
    found = site_audit._duplicate_description_findings(
        {"Homepage": same, "Club Fitting": same, "Coaching": same, "Other": "A different one."}
    )
    assert sorted(f["page"] for f in found) == ["Club Fitting", "Coaching", "Homepage"]
    assert all(f["type"] == "meta_description_duplicate" for f in found)
    assert "Club Fitting" in next(f for f in found if f["page"] == "Homepage")["message"]


def test_missing_descriptions_are_not_counted_as_duplicates():
    assert site_audit._duplicate_description_findings({"A": "", "B": "", "C": None}) == []


def test_a_duplicate_description_gets_an_improve_button():
    assert q.FIX_BUTTONS["meta_description_duplicate"] == {"field": "meta_description", "label": "Improve"}


# ── queue and slugs ────────────────────────────────────────────────────────


def test_stick_has_a_fix_queue():
    assert "stick" in q.QUEUE_BRANDS
    out = q.sync("stick", [{"type": "title_too_short", "page": "Club Fitting", "severity": "medium", "message": "m"}], [], None, NOW)
    assert out["brand"] == "stick" and out["items"][0]["fix_button"]["field"] == "title"


def test_each_brand_maps_page_names_to_its_own_wordpress_slugs():
    assert smp.page_slugs("stick") == {"Club Fitting": "club-fitting-at-stick", "Coaching": "coaching-at-stick"}
    assert smp.page_slugs("swing-shack") == smp.PAGE_SLUGS
    assert fx.button_slugs("stick")["Homepage"] == "home"


# ── brand names in the text ────────────────────────────────────────────────


def test_stick_text_may_say_stick_but_never_swing_shack():
    ok = "Stick fits clubs on TrackMan in Paarl, so every recommendation comes from your own swing numbers. Book a session this week."
    assert fx.check_text("meta_description", ok, "stick")["errors"] == []
    bad = "Stick and Swing Shack both fit clubs on TrackMan, so every recommendation comes from your own swing numbers. Book now."
    assert any("another company" in e for e in fx.check_text("meta_description", bad, "stick")["errors"])


def test_swing_shack_text_still_may_not_say_stick():
    bad = "Swing Shack and Stick both fit clubs on TrackMan, so every recommendation comes from your own swing numbers. Book now."
    assert any("another company" in e for e in fx.check_text("meta_description", bad, "swing-shack")["errors"])


def test_drafting_for_stick_keeps_sentences_that_name_stick():
    out = smp.propose(STICK_FITTING_HTML, prefer=("Stick", "Club Fitting"), brand="stick")
    assert out and out.startswith("Stick fits clubs")
    assert smp.propose(STICK_FITTING_HTML) is None, "for Swing Shack a sentence naming Stick is still refused"


# ── the button works end to end on Stick's page ────────────────────────────


class StickWP:
    def __init__(self):
        self.calls = []
        self.page = {"id": 3238, "slug": "club-fitting-at-stick", "status": "publish", "link": "https://stickgolf.co.za/club-fitting-at-stick/",
                     "html": STICK_FITTING_HTML, "desc": "Trackman fittings and golf coaching at Stick in Paarl."}

    def _view(self):
        p = self.page
        return {"id": p["id"], "slug": p["slug"], "status": p["status"], "link": p["link"], "content": {"rendered": p["html"]},
                "meta": {smp.META_KEY: p["desc"]}, "yoast_head_json": {"description": p["desc"], "title": "Club Fitting at Stick - Stick Golf"}}

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.startswith("/pages?slug="):
            slug = re.search(r"slug=([^&]+)", path).group(1)
            return {"ok": True, "data": [self._view()] if slug == self.page["slug"] else []}
        if path.startswith("/pages/3238"):
            if method == "POST":
                self.page["desc"] = (payload.get("meta") or payload.get("meta_input") or {}).get(smp.META_KEY, self.page["desc"])
            return {"ok": True, "data": self._view()}
        return {"ok": False, "data": {}}


def test_improve_on_stick_reads_and_writes_the_stick_page():
    io = MemIO()
    io.files[fx.QUEUE_FILE] = {"brand": "stick", "items": [{"id": "d1", "type": "meta_description_duplicate", "page": "Club Fitting",
                                                              "publish_policy": q.PUBLISH_ASK, "status": "draft"}]}
    wp = StickWP()
    d = fx.build_draft(io, "stick", "d1", wp)
    assert d["ok"] and d["button"] == "Improve" and d["proposal"].startswith("Stick fits clubs")
    out = fx.apply_fix(io, "stick", "d1", d["proposal"], wp, NOW, expected_current=d["current"], run_mode="on")
    assert out["ok"] and wp.page["desc"] == d["proposal"]
    assert any(p.startswith("/pages?slug=club-fitting-at-stick") for _, p, _ in wp.calls)
