"""
Inspiration Intelligence Slice 1 — integration tests.

Run: pytest tests/test_inspiration_intelligence.py -v
"""
import json, os, pytest, sys
from pathlib import Path

# --------------------------------------------------------------------------
# Test isolation: each test gets its own temp DATA_DIR
# --------------------------------------------------------------------------
TEST_BRANDS = ["swing-shack", "stick", "bag-drop"]


@pytest.fixture(autouse=True)
def iso_env(tmp_path, monkeypatch):
    """Clean DATA_DIR per test, seeded with brands.json and regression files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    brands = {bid: {"name": bid} for bid in TEST_BRANDS}
    (data_dir / "brands.json").write_text(json.dumps(brands))

    # Regression guard: seed files that other existing routes depend on.
    HB_SCHEMA = "https://campaign-os/hooks/v1"
    for bid in TEST_BRANDS:
        hb_dir = data_dir / "brands" / bid
        hb_dir.mkdir(parents=True, exist_ok=True)
        (hb_dir / "hook-bank.json").write_text(json.dumps({
            "schema": HB_SCHEMA,
            "brand_id": bid,
            "hooks": [],
            "updated_at": "2026-09-25T00:00:00Z"
        }))

    monkeypatch.setenv("DATA_DIR", str(data_dir))

    # Force-reload so the new DATA_DIR is picked up
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import _lib.brand_data_paths as bd
    import importlib
    importlib.reload(bd)

    yield data_dir


# --------------------------------------------------------------------------
# Helpers (work with cos_session which auto-logs in via conftest.py)
# --------------------------------------------------------------------------

def jget(c, path):
    r = c.get(path)
    assert r.status_code == 200, f"GET {path} -> {r.status_code}: {r.data[:200]}"
    return json.loads(r.data)


def jpost(c, path, body, expected_status=201):
    r = c.post(path, json=body, content_type="application/json")
    assert r.status_code == expected_status, f"POST {path} -> {r.status_code} (exp {expected_status}): {r.data[:300]}"
    return json.loads(r.data)


def jput(c, path, body, expected_status=200):
    r = c.put(path, json=body, content_type="application/json")
    assert r.status_code == expected_status, f"PUT {path} -> {r.status_code} (exp {expected_status}): {r.data[:200]}"
    return json.loads(r.data)


def jdel(c, path, expected_status=200):
    r = c.delete(path)
    assert r.status_code == expected_status, f"DELETE {path} -> {r.status_code}"
    return json.loads(r.data)


# --------------------------------------------------------------------------
# Tests — use cos_session (authenticated client from conftest.py)
# --------------------------------------------------------------------------

class TestEmptyState:
    """Empty GET must return HTTP 200 with canonical empty structure, not 404."""

    def test_empty_watchlist_returns_200(self, cos_session):
        r = cos_session.get("/api/inspiration/swing-shack/watchlist")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        body = json.loads(r.data)
        assert body.get("data", {}).get("profiles") == []

    def test_empty_posts_returns_200(self, cos_session):
        r = cos_session.get("/api/inspiration/swing-shack/posts")
        assert r.status_code == 200
        body = json.loads(r.data)
        assert body.get("data", {}).get("posts") == []


class TestWatchlistCRUD:
    """Full CRUD for the inspiration watchlist."""

    def test_watchlist_create(self, cos_session):
        r = jpost(cos_session, "/api/inspiration/swing-shack/watchlist",
            {"handle": "@golf_tip", "platform": "instagram"})
        assert r["ok"] is True
        assert r["data"]["profile_id"] is not None
        assert r["data"]["handle"] == "@golf_tip"
        assert r["data"]["platform"] == "instagram"
        assert r["data"]["created_at"] is not None

    def test_watchlist_read(self, cos_session):
        created = jpost(cos_session, "/api/inspiration/swing-shack/watchlist",
            {"handle": "@read_test", "platform": "tiktok"})
        pid = created["data"]["profile_id"]
        r = jget(cos_session, "/api/inspiration/swing-shack/watchlist")
        assert any(p["profile_id"] == pid for p in r["data"]["profiles"])

    def test_watchlist_read_single(self, cos_session):
        created = jpost(cos_session, "/api/inspiration/swing-shack/watchlist",
            {"handle": "@single_read", "platform": "youtube"})
        pid = created["data"]["profile_id"]
        r = jget(cos_session, f"/api/inspiration/swing-shack/watchlist/{pid}")
        assert r["data"]["profile_id"] == pid
        assert r["data"]["handle"] == "@single_read"

    def test_watchlist_update(self, cos_session):
        created = jpost(cos_session, "/api/inspiration/swing-shack/watchlist",
            {"handle": "@update_test", "platform": "instagram"})
        pid = created["data"]["profile_id"]
        r = jput(cos_session, f"/api/inspiration/swing-shack/watchlist/{pid}",
            {"notes": "Great swing tips", "why_tags": ["humour"]})
        assert r["data"]["notes"] == "Great swing tips"
        assert r["data"]["why_tags"] == ["humour"]
        assert r["data"]["updated_at"] is not None

    def test_watchlist_delete(self, cos_session):
        created = jpost(cos_session, "/api/inspiration/swing-shack/watchlist",
            {"handle": "@delete_test", "platform": "instagram"})
        pid = created["data"]["profile_id"]
        jdel(cos_session, f"/api/inspiration/swing-shack/watchlist/{pid}")
        r = jget(cos_session, "/api/inspiration/swing-shack/watchlist")
        assert all(p["profile_id"] != pid for p in r["data"]["profiles"])

    def test_watchlist_unknown_brand_rejected(self, cos_session):
        r = cos_session.post("/api/inspiration/fake-brand/watchlist",
            json={"handle": "@x", "platform": "instagram"},
            content_type="application/json")
        assert r.status_code == 400


class TestPostsCRUD:
    """Full CRUD for saved inspiration posts."""

    def test_posts_create(self, cos_session):
        r = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://www.tiktok.com/@user/video/123",
            "platform": "tiktok",
            "caption": "Golf swing tip",
            "why_tags": ["humour", "educational"],
            "provenance": {
                "source_type": "manual",
                "collection_method": "manual_save",
                "collected_at": "2026-09-25T10:00:00Z"
            }
        })
        assert r["ok"] is True
        assert r["data"]["post_id"] is not None
        assert r["data"]["platform"] == "tiktok"
        assert r["data"]["why_tags"] == ["humour", "educational"]
        assert r["data"]["captured_metrics"]["likes"] is None
        assert r["data"]["provenance"]["collection_method"] == "manual_save"

    def test_posts_create_youtube(self, cos_session):
        """YouTube platform must be supported (Slice 1 requirement)."""
        r = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://www.youtube.com/watch?v=abc123",
            "platform": "youtube",
            "published_at": "2026-09-01T08:00:00Z",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        assert r["data"]["platform"] == "youtube"

    def test_posts_read(self, cos_session):
        created = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/readtest",
            "platform": "instagram",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        pid = created["data"]["post_id"]
        r = jget(cos_session, "/api/inspiration/swing-shack/posts")
        assert any(p["post_id"] == pid for p in r["data"]["posts"])

    def test_posts_read_single(self, cos_session):
        created = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/singleread",
            "platform": "instagram",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        pid = created["data"]["post_id"]
        r = jget(cos_session, f"/api/inspiration/swing-shack/posts/{pid}")
        assert r["data"]["post_id"] == pid

    def test_posts_update(self, cos_session):
        created = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/updatetest",
            "platform": "instagram",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        pid = created["data"]["post_id"]
        r = jput(cos_session, f"/api/inspiration/swing-shack/posts/{pid}", {
            "caption": "Updated caption",
            "why_tags": ["educational"],
            "analysis_schema": {
                "hook_type": "question",
                "format": "reels",
                "content_type": "educational",
                "primary_emotion": ["curiosity"],
                "cta_type": "link_in_bio",
                "analysis_confidence": 0.8
            }
        })
        assert r["data"]["caption"] == "Updated caption"
        assert r["data"]["analysis_schema"]["hook_type"] == "question"
        assert r["data"]["analysis_schema"]["format"] == "reels"
        assert r["data"]["analysis_schema"]["influencer"] is None

    def test_posts_provenance_partial_update(self, cos_session):
        """Provenance fields can be updated without overwriting other fields."""
        created = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/provtest",
            "platform": "instagram",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        pid = created["data"]["post_id"]
        r = jput(cos_session, f"/api/inspiration/swing-shack/posts/{pid}", {
            "provenance": {"analysed_by": "claude-sonnet", "analysis_version": "1.0"}
        })
        assert r["data"]["provenance"]["analysed_by"] == "claude-sonnet"
        assert r["data"]["provenance"]["collection_method"] == "manual_save"

    def test_posts_delete(self, cos_session):
        created = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/deltest",
            "platform": "instagram",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        pid = created["data"]["post_id"]
        jdel(cos_session, f"/api/inspiration/swing-shack/posts/{pid}")
        r = jget(cos_session, "/api/inspiration/swing-shack/posts")
        assert all(p["post_id"] != pid for p in r["data"]["posts"])

    def test_posts_cascade_delete(self, cos_session):
        """When a watchlist profile is deleted, associated posts are also removed."""
        wp = jpost(cos_session, "/api/inspiration/swing-shack/watchlist",
            {"handle": "@cascadecreator", "platform": "instagram"})
        wpid = wp["data"]["profile_id"]
        pp = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/cascade_test",
            "platform": "instagram",
            "source_profile": {"profile_id": wpid, "handle": "@cascadecreator"},
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        cpost_id = pp["data"]["post_id"]
        jdel(cos_session, f"/api/inspiration/swing-shack/watchlist/{wpid}")
        r = jget(cos_session, "/api/inspiration/swing-shack/posts")
        assert all(p["post_id"] != cpost_id for p in r["data"]["posts"])


class TestBrandIsolation:
    """Swing Shack data must not appear in Stick Golf or Bag Drop."""

    def test_watchlist_isolation(self, cos_session):
        r = jpost(cos_session, "/api/inspiration/swing-shack/watchlist",
            {"handle": "@ss-exclusive", "platform": "instagram"})
        ss_pid = r["data"]["profile_id"]
        wl_ss = jget(cos_session, "/api/inspiration/swing-shack/watchlist")
        wl_st = jget(cos_session, "/api/inspiration/stick/watchlist")
        assert any(p["profile_id"] == ss_pid for p in wl_ss["data"]["profiles"])
        assert all(p["profile_id"] != ss_pid for p in wl_st["data"]["profiles"])

    def test_posts_isolation(self, cos_session):
        r = jpost(cos_session, "/api/inspiration/stick/posts", {
            "source_url": "https://instagram.com/p/stick123",
            "platform": "instagram",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        spid = r["data"]["post_id"]
        ps_st = jget(cos_session, "/api/inspiration/stick/posts")
        ps_ss = jget(cos_session, "/api/inspiration/swing-shack/posts")
        assert any(p["post_id"] == spid for p in ps_st["data"]["posts"])
        assert all(p["post_id"] != spid for p in ps_ss["data"]["posts"])


class TestProvenance:
    """Full provenance block must be present on every saved post."""

    def test_provenance_fields_present(self, cos_session):
        r = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/provfields",
            "platform": "instagram",
            "provenance": {
                "source_type": "manual",
                "source_url": "https://instagram.com/p/provfields",
                "collection_method": "manual_save",
                "collected_at": "2026-09-25T10:00:00Z",
                "analysed_by": None,
                "analysis_version": None
            }
        })
        p = r["data"]["provenance"]
        for f in ["source_type", "source_url", "collected_at",
                  "collection_method", "analysed_by", "analysis_version"]:
            assert f in p, f"provenance.{f} missing"

    def test_provenance_defaults_to_manual(self, cos_session):
        """When provenance body is absent, collection_method defaults to 'manual'."""
        r = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/defaults",
            "platform": "instagram"
        })
        assert r["data"]["provenance"]["collection_method"] == "manual"


class TestAnalysisSchema:
    """Full analysis_schema present on every post, all fields null or empty arrays."""

    def test_all_string_fields_null(self, cos_session):
        r = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/aschema",
            "platform": "instagram",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        s = r["data"]["analysis_schema"]
        null_str_fields = [
            "format", "content_type", "hook_type", "human_presence",
            "creator_presence", "collaboration", "influencer", "product_presence",
            "product_launch", "educational", "humour", "offer", "question",
            "audio_type", "text_overlay", "cta_type", "summary"
        ]
        for f in null_str_fields:
            assert s.get(f) is None, f"analysis.{f} should be null, got {s.get(f)!r}"

    def test_all_array_fields_empty(self, cos_session):
        r = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/arrayfields",
            "platform": "instagram",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        s = r["data"]["analysis_schema"]
        arr_fields = ["visual_style", "colour_characteristics", "editing_style",
                      "primary_emotion", "creative_mechanic", "likely_performance_drivers"]
        for f in arr_fields:
            assert s.get(f) == [], f"analysis.{f} should be [], got {s.get(f)!r}"

    def test_analysis_confidence_null(self, cos_session):
        r = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/conf",
            "platform": "instagram",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        assert r["data"]["analysis_schema"].get("analysis_confidence") is None


class TestSourceFields:
    """Basic source fields from Lab.txt spec are stored and returned."""

    def test_source_fields_preserved(self, cos_session):
        r = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://www.youtube.com/watch?v=xyz",
            "platform": "youtube",
            "source_profile": "@golfchannel",
            "external_post_id": "yt_xyz123",
            "published_at": "2026-09-01T12:00:00Z",
            "media_type": "video",
            "caption": "Amazing golf swing breakdown",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        p = r["data"]
        assert p["source_profile"]["handle"] == "@golfchannel"
        assert p["external_post_id"] == "yt_xyz123"
        assert p["published_at"] == "2026-09-01T12:00:00Z"
        assert p["media_type"] == "video"
        assert p["caption"] == "Amazing golf swing breakdown"

    def test_source_profile_dict_accepted(self, cos_session):
        """source_profile as a dict with profile_id and handle should also be accepted."""
        r = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/spdict",
            "platform": "instagram",
            "source_profile": {"profile_id": "abc123", "handle": "@pro",
                               "display_name": "Pro Account"},
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        sp = r["data"]["source_profile"]
        assert sp["profile_id"] == "abc123"
        assert sp["handle"] == "@pro"
        assert sp["display_name"] == "Pro Account"


class TestPlatformSupport:
    """Instagram, TikTok, YouTube all supported (Slice 1 minimum)."""

    @pytest.mark.parametrize("platform", ["instagram", "tiktok", "youtube"])
    def test_platform_create(self, cos_session, platform):
        r = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": f"https://{platform}.com/test",
            "platform": platform,
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        assert r["data"]["platform"] == platform


class TestNullMetrics:
    """Unavailable metrics must be null, not zero."""

    def test_captured_metrics_all_null(self, cos_session):
        r = jpost(cos_session, "/api/inspiration/swing-shack/posts", {
            "source_url": "https://instagram.com/p/nometrics",
            "platform": "instagram",
            "provenance": {"source_type": "manual", "collection_method": "manual_save",
                           "collected_at": "2026-09-25T10:00:00Z"}
        })
        m = r["data"]["captured_metrics"]
        for f in ["likes", "comments", "saves", "shares", "views", "engagement_rate"]:
            assert m.get(f) is None, f"captured_metrics.{f} should be null, got {m.get(f)!r}"


class TestBrandValidation:
    """Unknown brands are rejected with HTTP 400."""

    def test_unknown_brand_watchlist_rejected(self, cos_session):
        r = cos_session.post("/api/inspiration/totally-fake-brand/watchlist",
            json={"handle": "@x", "platform": "instagram"},
            content_type="application/json")
        assert r.status_code == 400

    def test_unknown_brand_posts_rejected(self, cos_session):
        r = cos_session.post("/api/inspiration/totally-fake-brand/posts",
            json={"source_url": "https://x.com/x/status/1", "platform": "x",
                  "provenance": {"source_type": "manual", "collection_method": "manual_save",
                                 "collected_at": "2026-09-25T10:00:00Z"}},
            content_type="application/json")
        assert r.status_code == 400


class TestRegression:
    """Existing Campaign OS routes still work after adding Inspiration routes."""

    def test_brands_json_still_readable(self, cos_session):
        """The /api/brands route (brand switcher) still works."""
        r = cos_session.get("/api/brands")
        assert r.status_code == 200
        body = json.loads(r.data)
        assert "swing-shack" in body["brands"]

    def test_inspiration_spa_route_accessible(self, cos_session):
        """The /inspiration-lab SPA route returns the HTML file."""
        r = cos_session.get("/inspiration-lab")
        assert r.status_code == 200
        assert b"<!DOCTYPE" in r.data or b"<html" in r.data
