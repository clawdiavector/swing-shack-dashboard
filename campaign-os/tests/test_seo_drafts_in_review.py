"""The three Swing Shack blog drafts must load into the real Review layer.

Review V1 reads Writer artifacts (data/writer-artifacts/<brand>/<slug>.json).
These tests copy the shipped artifacts into a temp DATA_DIR the way the boot
patch does and open them with review.create_or_get_review. Nothing is published.
"""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

ROOT = Path(HERE).parents[1]
ART_DIR = ROOT / "data" / "writer-artifacts" / "swing-shack"
SLUGS = [
    "indoor-golf-johannesburg-what-to-expect",
    "golf-lessons-johannesburg-first-session",
    "trackman-numbers-explained",
]


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    dest = tmp_path / "writer" / "swing-shack"
    dest.mkdir(parents=True)
    for slug in SLUGS:
        shutil.copy2(ART_DIR / f"{slug}.json", dest / f"{slug}.json")
    return tmp_path


@pytest.mark.parametrize("slug", SLUGS)
def test_each_draft_opens_in_review_with_sections_to_approve(data_dir, slug):
    from _lib import review

    out = review.create_or_get_review("swing-shack", f"seo-brief-{slug}", "christelle")
    assert out["ok"] and out["created"]
    rec = out["review"]
    assert rec["status"] == review.STATUS_DRAFT_FOR_REVIEW
    assert len(rec["sections"]) >= 4
    assert all(not s["approved"] for s in rec["sections"])
    assert rec["writer_artifact"]["publishing"] == "NONE"
    assert rec["writer_artifact"]["live_site_changes"] == "NONE"
    assert rec["writer_artifact"]["title"]


@pytest.mark.parametrize("slug", SLUGS)
def test_nothing_is_approved_or_published_by_loading(data_dir, slug):
    from _lib import review

    review.create_or_get_review("swing-shack", f"seo-brief-{slug}", "christelle")
    blockers = review._compute_approval_blockers(review._load_review("swing-shack", f"r_seo-brief-{slug}"))
    assert blockers["blocking"] and blockers["unapproved_sections"]
    assert blockers["evidence_needed"] == []


def test_the_review_queue_lists_all_three_for_swing_shack_only(data_dir):
    from _lib import review

    for slug in SLUGS:
        review.create_or_get_review("swing-shack", f"seo-brief-{slug}", "christelle")
    queue = review.get_review_queue("swing-shack")
    assert {q["brief_id"] for q in queue} == {f"seo-brief-{s}" for s in SLUGS}
    assert review.get_review_queue("stick") == []


@pytest.mark.parametrize("slug", SLUGS)
def test_artifacts_follow_the_house_rules(slug):
    art = json.loads((ART_DIR / f"{slug}.json").read_text(encoding="utf-8"))
    text = art["human_facing_article_draft"]
    assert "—" not in text and "–" not in text  # no em or en dashes
    for banned in ("Stick", "Bag Drop", "world-class", "unlock your potential"):
        assert banned.lower() not in text.lower()
    assert art["operating_brand"] == "swing-shack"
    assert art["review_flags"], "every draft says what still needs a person"


def test_no_draft_has_an_open_confirm_marker():
    marked = [s for s in SLUGS if "[CONFIRM" in json.loads((ART_DIR / f"{s}.json").read_text(encoding="utf-8"))["human_facing_article_draft"]]
    assert marked == []


def test_converter_is_repeatable(tmp_path):
    import seo_draft_to_writer_artifact as conv

    md = ROOT / "docs" / "seo" / "blog-drafts" / "03-trackman-numbers-explained.md"
    assert conv.main([str(md), "--brand", "swing-shack", "--out", str(tmp_path)]) == 0
    again = json.loads((tmp_path / "swing-shack" / "trackman-numbers-explained.json").read_text(encoding="utf-8"))
    shipped = json.loads((ART_DIR / "trackman-numbers-explained.json").read_text(encoding="utf-8"))
    assert again == shipped, "shipped artifact is stale: rerun the converter"
