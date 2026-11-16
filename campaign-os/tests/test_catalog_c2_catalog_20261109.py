"""Catalog: one review pack per campaign plan (slice c2-catalog, 2026-11-09)."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import campaign_plan as cp  # noqa: E402

TODAY = date(2026, 10, 13)
TOKEN = "test-job-token-not-a-secret"
PASSWORD = "swing-shack-dev-2026"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    return tmp_path


def brief(status="approved", d="2026-12-05", bid="brf-catalog001"):
    return {"brief_id": bid, "status": status, "source_opportunity": {"name": "Black Friday", "date": d}}


def _plan(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    out = cp.propose_plan("stick", brief(), today=TODAY)
    assert out["ok"]
    return out["plan"]


# ── catalog module (unit) ────────────────────────────────────────────────────


def test_catalog_created_once_per_plan(data_dir, monkeypatch):
    from _lib import catalog as cat

    plan = _plan(data_dir, monkeypatch)
    a = cat.ensure_for_plan("stick", plan["plan_id"])
    b = cat.ensure_for_plan("stick", plan["plan_id"])
    assert a["pack_id"] == b["pack_id"]
    assert cat.catalog_for_plan("stick", plan["plan_id"]) == a["pack_id"]


def test_catalog_has_one_slot_per_post_and_story_step(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan = _plan(data_dir, monkeypatch)
    cat.ensure_for_plan("stick", plan["plan_id"])
    cat.sync("stick", plan["plan_id"])
    pack = rp.get_pack(cat.catalog_for_plan("stick", plan["plan_id"]))
    slots = {i["id"] for i in pack["items"]}
    expected = {i["item_id"] for i in plan["items"] if i["kind"] in ("post", "story")}
    assert slots == expected
    assert not any(i["kind"] in ("shoot", "boost") for i in plan["items"] if i["item_id"] in slots)


def test_catalog_sync_adds_new_step(data_dir, monkeypatch):
    from _lib import catalog as cat

    plan = _plan(data_dir, monkeypatch)
    cat.ensure_for_plan("stick", plan["plan_id"])
    cat.sync("stick", plan["plan_id"])
    add = cp.add_item("stick", plan["plan_id"], {"title": "Extra post", "due": "2026-11-30", "kind": "post"})
    assert add["ok"]
    out = cat.sync("stick", plan["plan_id"])
    assert out["added"] >= 1


def test_catalog_sync_hides_removed_step_and_restores(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan = _plan(data_dir, monkeypatch)
    pid = plan["plan_id"]
    cat.ensure_for_plan("stick", pid)
    cat.sync("stick", pid)
    post = next(i for i in plan["items"] if i["kind"] == "post")
    cp.edit_item("stick", pid, post["item_id"], {"status": "removed"})
    hid = cat.sync("stick", pid)
    assert hid["removed"] >= 1
    pack_id = cat.catalog_for_plan("stick", pid)
    assert post["item_id"] not in {i["id"] for i in rp.get_pack(pack_id)["items"]}
    cp.edit_item("stick", pid, post["item_id"], {"status": "kept"})
    back = cat.sync("stick", pid)
    assert back["added"] >= 1 or back.get("updated", 0) >= 0
    assert post["item_id"] in {i["id"] for i in rp.get_pack(pack_id)["items"]}


def test_catalog_sync_updates_redated_step(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan = _plan(data_dir, monkeypatch)
    pid = plan["plan_id"]
    pack_id = cat.ensure_for_plan("stick", pid)["pack_id"]
    cat.sync("stick", pid)
    post = next(i for i in plan["items"] if i["kind"] == "post")
    cp.edit_item("stick", pid, post["item_id"], {"due": "2026-11-21"})
    out = cat.sync("stick", pid)
    assert out["updated"] >= 1
    item = next(i for i in rp.get_pack(pack_id)["items"] if i["id"] == post["item_id"])
    assert "21" in item["when"] or "Nov" in item["when"]


def test_catalog_sync_keeps_decisions_and_comments(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan = _plan(data_dir, monkeypatch)
    pack_id = cat.ensure_for_plan("stick", plan["plan_id"])["pack_id"]
    cat.sync("stick", plan["plan_id"])
    post = next(i for i in plan["items"] if i["kind"] == "post")
    rp.record_decision(pack_id, post["item_id"], "approve", "Kyle")
    rp.add_comment(pack_id, post["item_id"], "Kyle", "Looks good", role="us")
    cat.sync("stick", plan["plan_id"])
    v = rp.view(pack_id)
    assert v["decisions"][post["item_id"]]["state"] == "approve"
    assert v["comments"][post["item_id"]][0]["text"] == "Looks good"


def test_superseded_plan_has_no_catalog(data_dir, monkeypatch):
    from _lib import catalog as cat

    plan = _plan(data_dir, monkeypatch)
    cat.ensure_for_plan("stick", plan["plan_id"])
    cp.propose_plan("stick", brief(), today=TODAY, force=True)
    with pytest.raises(ValueError, match="replaced"):
        cat.ensure_for_plan("stick", plan["plan_id"])


def test_empty_slot_renders_picture_to_come(data_dir, monkeypatch):
    from _lib import review_pack as rp
    from itsdangerous import URLSafeTimedSerializer

    pack = rp.create_pack(
        "Test catalog",
        [{"id": "only-one", "title": "A post", "kind": "single"}],
    )
    page = rp.render_page(rp.public_view(pack["id"], "tok"), token="tok")
    assert "Picture to come" in page


# ── routes ───────────────────────────────────────────────────────────────────


class CatalogRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-catalog-routes-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_SANDBOX_DIR", "COS_JOB_TOKEN", "BUNDLED_DATA_DIR")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["BUNDLED_DATA_DIR"] = str(REPO_ROOT / "data")
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        os.environ["COS_JOB_TOKEN"] = TOKEN
        import app as app_module

        cls.app_module = app_module

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        os.environ["DATA_DIR"] = str(self.tmpdir)
        self.app_module.DATA_DIR = str(self.tmpdir)
        self.app_module.COS_JOB_TOKEN = TOKEN
        for child in self.tmpdir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        for name in list(sys.modules):
            if name in ("_lib.catalog", "_lib.review_pack", "_lib.campaign_plan"):
                del sys.modules[name]
        self.app = self.app_module.app
        self.anon = self.app.test_client(cos_anon=True)
        self.client = self.app.test_client()
        self.client.post("/login", data={"password": PASSWORD})

    def _live_plan(self):
        from _lib import campaign_plan as plan_mod

        out = plan_mod.propose_plan("stick", brief(), today=TODAY)
        self.assertTrue(out["ok"], out)
        return out["plan"]

    def test_catalog_route_requires_login(self):
        plan = self._live_plan()
        from _lib import catalog as cat

        pack_id = cat.ensure_for_plan("stick", plan["plan_id"])["pack_id"]
        r = self.anon.get(f"/catalog/{pack_id}", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers.get("Location", ""))

    def test_catalog_route_mints_token_for_signed_in_name(self):
        plan = self._live_plan()
        headers = {"X-Actor-Display-Name": "Christelle"}
        r = self.client.post(
            f"/api/plan/v1/stick/{plan['plan_id']}/catalog",
            headers=headers,
            json={},
        )
        self.assertEqual(r.status_code, 200, r.get_json())
        pack_id = r.get_json()["pack_id"]
        hop = self.client.get(f"/catalog/{pack_id}", headers=headers, follow_redirects=False)
        self.assertEqual(hop.status_code, 302)
        loc = hop.headers.get("Location", "")
        m = re.search(r"/review-pack/([^/?]+)", loc)
        self.assertIsNotNone(m, loc)
        token = m.group(1)
        from _lib import review_pack as rp

        post = next(i for i in plan["items"] if i["kind"] == "post")
        act = self.client.post(
            f"/review-pack/{token}/act",
            headers=headers,
            json={"item": post["item_id"], "state": "approve"},
        )
        self.assertEqual(act.status_code, 200, act.get_json())
        d = rp.view(pack_id)["decisions"][post["item_id"]]
        self.assertEqual(d["by"], "Christelle")

    def test_guest_share_route_session_only(self):
        plan = self._live_plan()
        from _lib import catalog as cat

        pack_id = cat.ensure_for_plan("stick", plan["plan_id"])["pack_id"]
        bad = self.anon.post(f"/api/review-packs/{pack_id}/share", json={"who": "Guest"})
        self.assertEqual(bad.status_code, 401)
        ok = self.client.post(f"/api/review-packs/{pack_id}/share", json={"who": "Sam"})
        self.assertEqual(ok.status_code, 200, ok.get_json())
        self.assertIn("/review-pack/", ok.get_json().get("share_url", ""))
