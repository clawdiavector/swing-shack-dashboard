"""C4 + C5 — Love it / Maybe / No, notes, upload purpose, campaign yes (2026-11-09)."""
from __future__ import annotations

import io
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
from itsdangerous import URLSafeTimedSerializer

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import campaign_plan as cp  # noqa: E402

TODAY = date(2026, 10, 13)
TOKEN = "test-job-token-not-a-secret"
PASSWORD = "swing-shack-dev-2026"
MCM_ITEMS = [
    {"id": "first-car", "title": "Your first car, matched.", "kind": "single",
     "caption": "Tell us your budget.", "channels": "Instagram", "when": "Mon 2 Nov"},
]


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    return tmp_path


def _plan(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    brief = {"brief_id": "brf-c45", "status": "approved",
             "source_opportunity": {"name": "Black Friday", "date": "2026-12-05"}}
    out = cp.propose_plan("stick", brief, today=TODAY)
    assert out["ok"]
    return out["plan"]


def _catalog_pack(data_dir, monkeypatch):
    from _lib import catalog as cat

    plan = _plan(data_dir, monkeypatch)
    pack_id = cat.ensure_for_plan("stick", plan["plan_id"])["pack_id"]
    cat.sync("stick", plan["plan_id"])
    return plan, pack_id


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (80, 80), (200, 30, 90)).save(buf, format="PNG")
    return buf.getvalue()


def test_catalog_labels_love_maybe_no_map_to_states(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    _, pack_id = _catalog_pack(data_dir, monkeypatch)
    view = rp.public_view(pack_id, "tok", who="Herman")
    assert view["labels"] == {"approve": "Love it", "hold": "Maybe", "reject": "No"}
    html = rp.render_page(view, token="tok")
    assert "Love it" in html
    assert '"Approve"' not in html.split("const LBL")[1].split(";")[0]


def test_mcm_pack_keeps_approve_labels(data_dir):
    from _lib import review_pack as rp

    pack = rp.create_pack("MCM week", MCM_ITEMS, client="Chantalle")
    view = rp.public_view(pack["id"], "tok")
    assert "labels" not in view
    html = rp.render_page(view, token="tok")
    assert "Love it" not in html
    assert "Approve" in html


class CatalogMarkNoteRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-c45-routes-"))
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
        for child in self.tmpdir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        for name in list(sys.modules):
            if name in ("_lib.catalog", "_lib.review_pack", "_lib.campaign_plan"):
                del sys.modules[name]
        from _lib import catalog as cat
        from _lib import review_pack as rp

        self.rp = rp
        self.cat = cat
        self.app = self.app_module.app
        self.anon = self.app.test_client(cos_anon=True)
        brief = {"brief_id": "brf-c45r", "status": "approved",
                 "source_opportunity": {"name": "Sale", "date": "2026-12-05"}}
        out = cp.propose_plan("stick", brief, today=TODAY)
        self.plan = out["plan"]
        self.pack_id = cat.ensure_for_plan("stick", self.plan["plan_id"])["pack_id"]
        cat.sync("stick", self.plan["plan_id"])
        self.post = next(i for i in self.plan["items"] if i["kind"] == "post")
        self.token = rp.mint_token(self.app_module._serializer, self.pack_id, who="Herman")
        self.base = f"/review-pack/{self.token}"

    def test_no_without_note_refused_on_catalog(self):
        r = self.anon.post(self.base + "/act", json={"item": self.post["item_id"], "state": "reject"})
        self.assertEqual(r.status_code, 400, r.get_json())
        self.assertIn("change", (r.get_json() or {}).get("error", "").lower())

    def test_hold_with_note_saves_comment(self):
        r = self.anon.post(
            self.base + "/act",
            json={"item": self.post["item_id"], "state": "hold", "note": "Try a warmer tone.",
                  "tag": "design edit"},
        )
        self.assertEqual(r.status_code, 200, r.get_json())
        v = self.rp.view(self.pack_id)
        self.assertEqual(v["decisions"][self.post["item_id"]]["state"], "hold")
        comments = v["comments"].get(self.post["item_id"], [])
        self.assertTrue(any(c["text"] == "Try a warmer tone." and c["tag"] == "design edit" for c in comments))


def test_upload_needs_purpose_and_text(data_dir, monkeypatch):
    import app as app_module

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    from _lib import catalog as cat
    from _lib import review_pack as rp

    _, pack_id = _catalog_pack(data_dir, monkeypatch)
    plan_posts = [i for i in _plan(data_dir, monkeypatch)["items"] if i["kind"] == "post"]
    item = plan_posts[0]["item_id"] if plan_posts else rp.get_pack(pack_id)["items"][0]["id"]
    token = rp.mint_token(URLSafeTimedSerializer("not-a-real-secret"), pack_id)
    client = app_module.app.test_client(cos_anon=True)
    bad = client.post(
        f"/review-pack/{token}/upload",
        data={"item": item, "files": [(io.BytesIO(_png()), "a.png")], "source": "Michelle", "rights": "1"},
        content_type="multipart/form-data",
    )
    assert bad.status_code == 400
    ok = client.post(
        f"/review-pack/{token}/upload",
        data={
            "item": item,
            "files": [(io.BytesIO(_png()), "a.png")],
            "source": "Michelle",
            "rights": "1",
            "purpose": "reference",
            "text": "The look I want for this post.",
        },
        content_type="multipart/form-data",
    )
    assert ok.status_code == 200, ok.get_json()
    row = rp.view(pack_id)["uploads"][0]
    assert row.get("purpose") == "reference"
    assert row.get("text") == "The look I want for this post."


def test_campaign_yes_sends_nothing(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    _, pack_id = _catalog_pack(data_dir, monkeypatch)
    first = rp.get_pack(pack_id)["items"][0]["id"]
    rp.record_decision(pack_id, first, "approve", "Herman")
    traps = (
        "_lib.campaign_plan.approve_plan",
        "_lib.campaign_plan.place_on_calendar",
        "_lib.postiz_client.schedule_post",
        "_lib.publish_sandbox.enqueue_for_intended_channels",
    )
    with mock.patch(traps[0], side_effect=AssertionError("approve_plan")), \
         mock.patch(traps[1], side_effect=AssertionError("place_on_calendar")), \
         mock.patch(traps[2], create=True, side_effect=AssertionError("postiz")), \
         mock.patch(traps[3], side_effect=AssertionError("enqueue")):
        out = cat.approve_campaign(pack_id, "Herman", "uid-h")
    assert out["ok"]
    pack = rp.get_pack(pack_id)
    assert pack.get("campaign_approval", {}).get("by") == "Herman"


def test_campaign_yes_holds_maybe_no_and_unmarked(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, pack_id = _catalog_pack(data_dir, monkeypatch)
    pack = rp.get_pack(pack_id)
    ids = [i["id"] for i in pack["items"]]
    assert len(ids) >= 2
    rp.record_decision(pack_id, ids[0], "approve", "Herman")
    rp.record_decision(pack_id, ids[1], "hold", "Herman")
    if len(ids) > 2:
        rp.record_decision(pack_id, ids[2], "reject", "Herman")
    cat.approve_campaign(pack_id, "Herman", None)
    slots = cat.slot_states(pack_id)
    assert slots[ids[0]].get("release_ok") is True
    assert slots[ids[0]].get("held") is not True
    assert slots[ids[1]].get("held") is True
    if len(ids) > 2:
        assert slots[ids[2]].get("held") is True
    if len(ids) > 3:
        assert slots[ids[3]].get("held") is True


class HeldPostRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-c45-held-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_SANDBOX_DIR", "COS_JOB_TOKEN")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
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
        (self.tmpdir / "campaign-data.json").write_text(json.dumps({"campaigns": {}}))
        for child in self.tmpdir.iterdir():
            if child.is_dir() and child.name != "campaign-data.json":
                shutil.rmtree(child)
        import _lib

        for name in list(sys.modules):
            if name.startswith("_lib."):
                del sys.modules[name]
                if name.count(".") == 1:
                    _lib.__dict__.pop(name.split(".", 1)[1], None)
        from _lib import marketing_calendar as mc

        self.mc = mc
        rec = mc.add_candidate(
            "swing-shack",
            {"type": "moment", "title": "Held post", "event_date": "2099-06-01",
             "primary_channel": "instagram", "created_by": "test"},
            initial_status="candidate",
        )
        self.cal_id = str(rec["calendar_id"])
        mc.set_fields("swing-shack", self.cal_id, {"catalog_hold": True}, reason="catalog test")
        self.client = self.app_module.app.test_client()
        self.client.post("/login", data={"password": PASSWORD})

    def test_held_post_cannot_be_released(self):
        from _lib import clean_calendar as cc

        row = {"calendar_id": self.cal_id, "state": "draft_ready", "go_live_date": "2099-06-01",
               "primary_channel": "instagram", "catalog_hold": True}
        with mock.patch.object(cc, "find_post", return_value=(row, {"inbox_item_id": "draft_asset:c1:a1"})):
            with mock.patch("_lib.unified_inbox.approve_item", side_effect=AssertionError("must not approve")):
                out, code = self.app_module._clean_cal_act(
                    "swing-shack",
                    {"key": self.cal_id, "kind": "post", "action": "approve"},
                    "Christelle",
                )
        self.assertEqual(code, 409, out)
        self.assertIn("Maybe/No", out.get("error", ""))


    def test_held_video_already_in_postiz_is_not_scheduled(self):
        """A held post that sits in Postiz as a draft must not be scheduled by Approve."""
        from unittest import mock
        from _lib import clean_calendar as cc

        row = {"calendar_id": self.cal_id, "state": "draft_ready", "go_live_date": "2099-06-01",
               "primary_channel": "instagram", "catalog_hold": True,
               "postiz_mode": "draft", "postiz_post_id": "pz-1"}
        with mock.patch.object(cc, "find_post", return_value=(row, {"inbox_item_id": "draft_asset:c1:a1"})):
            with mock.patch.object(self.app_module, "_clean_cal_postiz_approve",
                                   side_effect=AssertionError("must not schedule in Postiz")):
                out, code = self.app_module._clean_cal_act(
                    "swing-shack", {"key": self.cal_id, "kind": "post", "action": "approve"}, "Christelle")
        self.assertEqual(code, 409, out)
        self.assertIn("Maybe/No", out.get("error", ""))


class CampaignApproveAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-c45-auth-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "BUNDLED_DATA_DIR", "COS_JOB_TOKEN")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["BUNDLED_DATA_DIR"] = str(REPO_ROOT / "data")
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
        for child in self.tmpdir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        sys.modules.pop("_lib.users", None)
        sys.modules.pop("app", None)
        from _lib import catalog as cat
        from _lib import review_pack as rp
        from _lib import users

        users.create_user("Connie", "con@test.example", "contributor", ["stick"], "con-pass")
        self.cat, self.rp = cat, rp
        brief = {"brief_id": "brf-c45a", "status": "approved",
                 "source_opportunity": {"name": "Sale", "date": "2026-12-05"}}
        plan = cp.propose_plan("stick", brief, today=TODAY)["plan"]
        self.pack_id = cat.ensure_for_plan("stick", plan["plan_id"])["pack_id"]
        cat.sync("stick", plan["plan_id"])
        import app as app_module

        self.app_module = app_module
        self.app = app_module.app

    def test_any_login_can_campaign_approve_but_signed_out_cannot(self):
        anon = self.app.test_client(cos_anon=True)
        self.assertEqual(anon.post(f"/api/review-packs/{self.pack_id}/campaign-approve", json={}).status_code, 401)
        c = self.app.test_client(cos_anon=True)
        c.post("/login", data={"email": "con@test.example", "password": "con-pass"})
        r = c.post(f"/api/review-packs/{self.pack_id}/campaign-approve", json={})
        self.assertEqual(r.status_code, 200, r.get_json())

    def test_approver_guest_link_can_campaign_approve(self):
        token = self.rp.mint_token(self.app_module._serializer, self.pack_id, who="Yolanda", role="approver")
        r = self.app.test_client(cos_anon=True).post(f"/review-pack/{token}/campaign-approve", json={})
        self.assertEqual(r.status_code, 200, r.get_json())


def test_news_reports_campaign_approved(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    _, pack_id = _catalog_pack(data_dir, monkeypatch)
    since = "2020-01-01T00:00:00Z"
    cat.approve_campaign(pack_id, "Herman", "u1")
    news = rp.news(pack_id, since=since)
    assert news.get("campaign_approved", {}).get("by") == "Herman"
    assert news.get("campaign_approved", {}).get("at")
    assert not news["empty"]
    assert "campaign" in news.get("text", "").lower() or "Herman" in news.get("text", "")


class ClearHoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-c45-clear-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "BUNDLED_DATA_DIR", "COS_JOB_TOKEN")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["BUNDLED_DATA_DIR"] = str(REPO_ROOT / "data")
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
        for child in self.tmpdir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        sys.modules.pop("_lib.users", None)
        from _lib import catalog as cat
        from _lib import users

        users.create_user("Ed", "ed@test.example", "editor", ["stick"], "ed-pass")
        users.create_user("Ap", "ap@test.example", "approver", ["stick"], "ap-pass")
        brief = {"brief_id": "brf-c45c", "status": "approved",
                 "source_opportunity": {"name": "Sale", "date": "2026-12-05"}}
        plan = cp.propose_plan("stick", brief, today=TODAY)["plan"]
        self.pack_id = cat.ensure_for_plan("stick", plan["plan_id"])["pack_id"]
        cat.sync("stick", plan["plan_id"])
        from _lib import review_pack as rp

        self.item_id = rp.get_pack(self.pack_id)["items"][0]["id"]
        cat.approve_campaign(self.pack_id, "Herman", None)
        sys.modules.pop("app", None)
        import app as app_module

        self.app_module = app_module
        self.app = app_module.app

    def test_clear_hold_any_login(self):
        editor = self.app.test_client(cos_anon=True)
        editor.post("/login", data={"email": "ed@test.example", "password": "ed-pass"})
        ok = editor.post(f"/api/review-packs/{self.pack_id}/items/{self.item_id}/clear-hold", json={})
        self.assertEqual(ok.status_code, 200, ok.get_json())
        from _lib import catalog as cat

        assert cat.slot_states(self.pack_id)[self.item_id].get("held") is not True

        cat.approve_campaign(self.pack_id, "Herman", None)
        approver = self.app.test_client(cos_anon=True)
        approver.post("/login", data={"email": "ap@test.example", "password": "ap-pass"})
        again = approver.post(f"/api/review-packs/{self.pack_id}/items/{self.item_id}/clear-hold", json={})
        self.assertEqual(again.status_code, 200, again.get_json())
        anon = self.app.test_client(cos_anon=True)
        self.assertEqual(anon.post(f"/api/review-packs/{self.pack_id}/items/{self.item_id}/clear-hold", json={}).status_code, 401)
