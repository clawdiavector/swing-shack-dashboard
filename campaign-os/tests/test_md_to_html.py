"""Markdown articles must reach WordPress as HTML, with the approved body untouched.

Found 2026-10-22 while staging the first Swing Shack blog draft: Publish V1 sent
raw markdown, so a draft would have shown literal ## and ** and dead links.
Fake WordPress only.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from _lib import publish_v1, wp_publisher  # noqa: E402
from _lib.md_to_html import base_from_api, looks_like_html, markdown_to_html  # noqa: E402

BASE = "https://swingshack.co.za"

SAMPLE = """# Golf Lessons in Johannesburg

A good first lesson answers one question. See the [bookings page](/bookings/).

## What the coach looks at first

- **Club path and face angle.** These explain most slices.
- Attack angle

1. **You book a session.** Sessions are 30 or 60 minutes.
2. You hit some shots.

*Swing Shack* is in [Randburg](https://swingshack.co.za/membership/).
"""


def test_headings_paragraphs_lists_bold_and_links_become_html():
    out = markdown_to_html(SAMPLE, BASE)
    assert "<h2>What the coach looks at first</h2>" in out
    assert "<p>A good first lesson answers one question. See the " in out
    assert '<a href="https://swingshack.co.za/bookings/">bookings page</a>' in out
    assert "<ul><li><strong>Club path and face angle.</strong> These explain most slices.</li><li>Attack angle</li></ul>" in out
    assert "<ol><li><strong>You book a session.</strong>" in out
    assert "<em>Swing Shack</em>" in out
    assert "##" not in out and "**" not in out


def test_the_leading_title_is_dropped_because_wordpress_shows_the_post_title():
    out = markdown_to_html(SAMPLE, BASE)
    assert "<h1>" not in out and "Golf Lessons in Johannesburg" not in out


def test_a_later_h1_is_kept_as_an_h2_not_a_second_page_title():
    out = markdown_to_html("Intro text here.\n\n# A later title\n\nMore.", BASE)
    assert "<h2>A later title</h2>" in out and "<h1>" not in out


def test_raw_html_and_scripts_are_escaped_not_passed_through():
    out = markdown_to_html("Hello <script>alert(1)</script> and <b>bold</b>.", BASE)
    assert "<script>" not in out and "&lt;script&gt;" in out and "<b>" not in out


def test_unsafe_link_schemes_lose_the_link_but_keep_the_words():
    out = markdown_to_html("Click [here](javascript:alert(1)) now.", BASE)
    assert "javascript" not in out and "here" in out and "<a " not in out


def test_relative_links_are_made_absolute_from_the_publishing_target():
    assert base_from_api("https://swingshack.co.za/wp-json/wp/v2") == BASE
    assert 'href="https://swingshack.co.za/club-fitting/"' in markdown_to_html("[fit](/club-fitting/)", BASE)


def test_html_bodies_are_recognised_and_left_alone():
    assert looks_like_html("<p>Already html</p>") and not looks_like_html("## Heading\n\nText with 2 < 3.")


def _staged_payload(monkeypatch, tmp_path, body):
    sent = {}
    target = {"wp_api_base": "https://swingshack.co.za/wp-json/wp/v2", "default_status_on_stage": "draft", "default_post_type": "post"}
    monkeypatch.setattr(publish_v1, "load_publishing_target", lambda brand: target)
    monkeypatch.setattr(publish_v1, "verify_revision_lock", lambda rec, content: (True, ""))
    monkeypatch.setattr(publish_v1, "check_internal_links", lambda rec: {"passed": True, "blocked": []})
    monkeypatch.setattr(publish_v1, "check_stock_price", lambda rec: {"passed": True, "blockers": []})
    monkeypatch.setattr(publish_v1, "update_status", lambda rec, new, **k: rec.__setitem__("status", new))
    monkeypatch.setattr(publish_v1, "_record_path", lambda brand, pid: tmp_path / f"{pid}.json")

    def fake_send(brand, payload, existing_post_id=None):
        sent.update(payload)
        return {"ok": True, "cms_post_id": 9, "slug": "x", "preview_url": "p", "edit_url": "e"}

    monkeypatch.setattr(wp_publisher, "send_to_cms", fake_send)
    rec = {"status": publish_v1.STATUS_READY_TO_STAGE, "brand_id": "swing-shack", "brief_id": "seo-brief-x",
           "publish_id": "p1", "article_title": "A title", "article_body": body, "checks": {}}
    out = publish_v1.stage_to_cms(rec)
    return out, rec, sent


def test_staging_sends_html_but_the_approved_body_is_unchanged(monkeypatch, tmp_path):
    out, rec, sent = _staged_payload(monkeypatch, tmp_path, SAMPLE)
    assert out["ok"], out
    assert sent["status"] == "draft" and sent["title"] == "A title"
    assert "<h2>" in sent["content"] and "##" not in sent["content"]
    assert rec["article_body"] == SAMPLE, "the revision lock hashes this, it must not change"


def test_staging_leaves_an_html_body_alone(monkeypatch, tmp_path):
    html = "<p>Already <strong>html</strong>.</p>"
    out, rec, sent = _staged_payload(monkeypatch, tmp_path, html)
    assert out["ok"] and sent["content"] == html
