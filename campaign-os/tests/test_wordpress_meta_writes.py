"""WordPress meta writes: never try what WordPress will silently drop, and verify what was kept.

Found live on 2026-10-23: Yoast makes its title and description writable over REST
for posts only. On pages the write is accepted and dropped. And Publish V1 sent the
fields as `meta_input`, which the REST API ignores, so staged drafts had empty SEO
fields even though the record said "written". Fake WordPress only.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from _lib import publish_v1, seo_fix_queue as q, seo_fixer as fx  # noqa: E402
from _lib import seo_meta_publish as smp  # noqa: E402
from test_seo_fixer import FakeWP, GOOD_DESC, apply, draft, io_with, queue_item  # noqa: E402
from test_seo_meta_publish import MemIO, NOW  # noqa: E402

YOAST_KEYS = ("_yoast_wpseo_title", "_yoast_wpseo_metadesc", "_yoast_wpseo_focuskw")


class SchemaWP(FakeWP):
    """FakeWP that also answers OPTIONS /pages like WordPress does."""

    def __init__(self, page_meta_keys, **kw):
        super().__init__(**kw)
        self.page_meta_keys = page_meta_keys

    def __call__(self, method, path, payload=None):
        if method == "OPTIONS" and path == "/pages":
            self.calls.append((method, path, payload))
            props = {k: {"type": "string"} for k in self.page_meta_keys}
            return {"ok": True, "http": 200, "data": {"schema": {"properties": {"meta": {"properties": props}}}}}
        return super().__call__(method, path, payload)


NOT_YOAST = ("footnotes", "_elementor_data")


# ── the probe ──────────────────────────────────────────────────────────────


def test_probe_says_false_when_pages_do_not_register_the_yoast_field():
    assert smp.page_field_writable(SchemaWP(NOT_YOAST), "meta_description") is False
    assert smp.page_field_writable(SchemaWP(NOT_YOAST), "title") is False


def test_probe_says_true_when_the_field_is_registered_for_pages():
    wp = SchemaWP(NOT_YOAST + YOAST_KEYS)
    assert smp.page_field_writable(wp, "meta_description") is True and smp.page_field_writable(wp, "title") is True


def test_probe_says_unknown_when_wordpress_gives_no_schema():
    assert smp.page_field_writable(FakeWP(), "meta_description") is None
    assert smp.page_field_writable(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")), "title") is None


# ── automatic run ──────────────────────────────────────────────────────────


def _auto_queue():
    return {"items": [queue_item("missing_meta_description", "Membership", q.PUBLISH_AUTO)]}


def test_automatic_run_makes_no_write_when_pages_cannot_save_the_field():
    wp, io = SchemaWP(NOT_YOAST), MemIO()
    out = smp.run_auto(io, "swing-shack", _auto_queue(), wp, NOW, run_mode="on")
    assert out["applied"] == 0 and wp.writes() == []
    assert out["skipped"] and "snippet" in out["skipped"][0]["why"]


def test_automatic_run_still_writes_when_the_field_is_registered():
    wp, io = SchemaWP(NOT_YOAST + YOAST_KEYS), MemIO()
    out = smp.run_auto(io, "swing-shack", _auto_queue(), wp, NOW, run_mode="on")
    assert out["applied"] == 1 and wp.pages[2255]["desc"]


# ── buttons ────────────────────────────────────────────────────────────────


def test_draft_tells_the_page_when_wordpress_cannot_save_it():
    out = draft(io_with(queue_item("missing_meta_description", "Membership")), SchemaWP(NOT_YOAST), "missing_meta_description-Membership")
    assert out["ok"] and out["writable"] is False and "snippet" in out["unwritable_reason"]
    assert out["proposal"], "the text is still offered so it can be pasted into Yoast by hand"


def test_apply_refuses_before_writing_when_wordpress_cannot_save_it_even_in_practice_mode():
    for mode in ("on", "dry-run"):
        wp, io = SchemaWP(NOT_YOAST), io_with(queue_item("missing_meta_description", "Membership"))
        out = apply(io, wp, "missing_meta_description-Membership", GOOD_DESC, run_mode=mode)
        assert not out["ok"] and out["status"] == 409 and wp.writes() == []
        assert smp.load_log(io)["entries"] == []


def test_apply_works_when_the_field_is_registered():
    wp, io = SchemaWP(NOT_YOAST + YOAST_KEYS), io_with(queue_item("missing_meta_description", "Membership"))
    assert apply(io, wp, "missing_meta_description-Membership", GOOD_DESC)["ok"]


# ── staging posts ──────────────────────────────────────────────────────────

SEO = {"seo_title": "Golf Lessons in Johannesburg: Your First TrackMan Lesson",
       "meta_description": "Your first golf lesson at Swing Shack, explained. How TrackMan shapes the session, what a coach looks at first and what you leave with.",
       "target_query": "golf lessons johannesburg"}


def _stage(monkeypatch, tmp_path, kept):
    """Stage a post whose WordPress keeps `kept` (a dict of meta) when read back."""
    import _lib.geo_audit as geo
    import _lib.seo_meta_strategy as sms
    import _lib.wp_publisher as wpp

    sent = {}
    target = {"wp_api_base": "https://swingshack.co.za/wp-json/wp/v2", "default_status_on_stage": "draft",
              "default_post_type": "post", "seo_metadata_supported": True}
    monkeypatch.setattr(publish_v1, "load_publishing_target", lambda brand: target)
    monkeypatch.setattr(publish_v1, "verify_revision_lock", lambda rec, content: (True, ""))
    monkeypatch.setattr(publish_v1, "check_internal_links", lambda rec: {"passed": True, "blocked": []})
    monkeypatch.setattr(publish_v1, "check_stock_price", lambda rec: {"passed": True, "blockers": []})
    monkeypatch.setattr(publish_v1, "update_status", lambda rec, new, **k: rec.__setitem__("status", new))
    monkeypatch.setattr(publish_v1, "_record_path", lambda brand, pid: tmp_path / f"{pid}.json")
    monkeypatch.setattr(sms, "detect_seo_plugin", lambda brand: "yoast")
    monkeypatch.setattr(wpp, "send_to_cms", lambda brand, payload, existing_post_id=None: (sent.update(payload) or {"ok": True, "cms_post_id": 4204, "slug": "x", "preview_url": "p", "edit_url": "e"}))
    monkeypatch.setattr(geo, "_wp_request", lambda brand, method, path, payload=None: {"ok": True, "data": {"meta": kept}})
    rec = {"status": publish_v1.STATUS_READY_TO_STAGE, "brand_id": "swing-shack", "brief_id": "seo-brief-x", "publish_id": "p1",
           "article_title": "A title", "article_body": "Body text.", "checks": {}, "seo_metadata": dict(SEO)}
    return publish_v1.stage_to_cms(rec), rec, sent


def test_staging_sends_yoast_fields_as_rest_meta_not_meta_input(monkeypatch, tmp_path):
    kept = {"_yoast_wpseo_title": SEO["seo_title"], "_yoast_wpseo_metadesc": SEO["meta_description"], "_yoast_wpseo_focuskw": SEO["target_query"]}
    out, rec, sent = _stage(monkeypatch, tmp_path, kept)
    assert out["ok"]
    assert "meta_input" not in sent and sent["meta"]["_yoast_wpseo_metadesc"] == SEO["meta_description"]


def test_staging_records_fields_as_written_only_when_wordpress_kept_them(monkeypatch, tmp_path):
    kept = {"_yoast_wpseo_title": SEO["seo_title"], "_yoast_wpseo_metadesc": SEO["meta_description"], "_yoast_wpseo_focuskw": SEO["target_query"]}
    out, rec, sent = _stage(monkeypatch, tmp_path, kept)
    assert sorted(rec["checks"]["seo_metadata_written"]) == ["meta_description", "seo_title", "target_query"]
    assert rec["checks"]["seo_metadata_readback"] == "verified"


def test_staging_does_not_claim_fields_wordpress_dropped(monkeypatch, tmp_path):
    out, rec, sent = _stage(monkeypatch, tmp_path, {"_yoast_wpseo_title": SEO["seo_title"]})
    assert rec["checks"]["seo_metadata_written"] == ["seo_title"]
    assert set(rec["checks"]["seo_metadata_unsupported"]) >= {"meta_description", "target_query"}
    assert rec["checks"]["seo_metadata_readback"] == "some fields not kept"
