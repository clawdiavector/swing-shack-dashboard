"""C6 + C7 — catalog month strip, drag move, remake from notes (2026-11-09)."""
from __future__ import annotations

import hashlib
import io
import json
import os
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
BRAND = "stick"


def _png(color=(200, 30, 90)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (80, 80), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    return tmp_path


def _plan(data_dir, monkeypatch, *, event_date="2026-12-05", bid="brf-c67"):
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    brief = {"brief_id": bid, "status": "approved", "source_opportunity": {"name": "Black Friday", "date": event_date}}
    out = cp.propose_plan(BRAND, brief, today=TODAY)
    assert out["ok"]
    return out["plan"]


def _catalog(data_dir, monkeypatch, plan=None):
    from _lib import catalog as cat

    plan = plan or _plan(data_dir, monkeypatch)
    pack_id = cat.ensure_for_plan(BRAND, plan["plan_id"])["pack_id"]
    cat.sync(BRAND, plan["plan_id"])
    return plan, pack_id


def test_month_strip_days_and_mark_colours(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, pack_id = _catalog(data_dir, monkeypatch)
    posts = [i for i in plan["items"] if i["kind"] in ("post", "story")]
    if len(posts) >= 1:
        rp.record_decision(pack_id, posts[0]["item_id"], "approve", "Herman")
    if len(posts) >= 2:
        rp.record_decision(pack_id, posts[1]["item_id"], "hold", "Herman")
    if len(posts) >= 3:
        rp.record_decision(pack_id, posts[2]["item_id"], "reject", "Herman")

    view = cat.month_strip_view(pack_id)
    assert view.get("months"), view
    all_dots = [d for m in view["months"] for day in m["days"] for d in day.get("dots", [])]
    assert all_dots, "expected at least one day dot"
    marks = {d["mark"] for d in all_dots}
    assert "approve" in marks or "hold" in marks or "reject" in marks or "unmarked" in marks
    for d in all_dots:
        assert d["colour"] in cat.MARK_DOT_COLOURS.values()


def test_drag_placed_step_uses_clean_calendar_move(data_dir, monkeypatch):
    from _lib import catalog as cat

    plan, pack_id = _catalog(data_dir, monkeypatch)
    post = next(i for i in plan["items"] if i["kind"] == "post")
    post["calendar_id"] = "cal-c67-move"
    cp._write_plan(plan)

    calls = []

    def fake_move(brand, body, who):
        calls.append((brand, body, who))
        return {"ok": True, "message": "Moved to Fri 28 Nov."}, 200

    out = cat.move_slot_day(
        pack_id,
        post["item_id"],
        "2026-11-28",
        "Christelle",
        calendar_move=fake_move,
    )
    assert out["ok"], out
    assert calls
    assert calls[0][0] == BRAND
    assert calls[0][1]["key"] == "cal-c67-move"
    assert calls[0][1]["date"] == "2026-11-28"


def test_drag_unplaced_step_edits_plan_date(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, pack_id = _catalog(data_dir, monkeypatch)
    post = next(i for i in plan["items"] if i["kind"] == "post")
    assert not post.get("calendar_id")

    out = cat.move_slot_day(pack_id, post["item_id"], "2026-11-18", "Christelle")
    assert out["ok"], out
    plan2 = cp.get_plan(BRAND, plan["plan_id"])
    row = next(i for i in plan2["items"] if i["item_id"] == post["item_id"])
    assert row["due"] == "2026-11-18"
    cat.sync(BRAND, plan["plan_id"])
    slot = next(i for i in rp.get_pack(pack_id)["items"] if i["id"] == post["item_id"])
    assert "18" in slot["when"] or "Nov" in slot["when"]


class CatalogDragAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-c67-drag-"))
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
                child.unlink(missing_ok=True)
        for name in list(sys.modules):
            if name.startswith("_lib."):
                del sys.modules[name]
        from _lib import catalog as cat
        from _lib import review_pack as rp

        self.cat = cat
        self.rp = rp
        self.anon = self.app_module.app.test_client(cos_anon=True)
        self.client = self.app_module.app.test_client()
        brief = {"brief_id": "brf-c67drag", "status": "approved", "source_opportunity": {"name": "Sale", "date": "2026-12-05"}}
        out = cp.propose_plan(BRAND, brief, today=TODAY)
        self.plan = out["plan"]
        self.pack_id = cat.ensure_for_plan(BRAND, self.plan["plan_id"])["pack_id"]
        cat.sync(BRAND, self.plan["plan_id"])
        self.post = next(i for i in self.plan["items"] if i["kind"] == "post")
        self.token = rp.mint_token(self.app_module._serializer, self.pack_id, who="Herman")
        self.approver_token = rp.mint_token(self.app_module._serializer, self.pack_id, who="Herman", role="approver")
        self.base = f"/review-pack/{self.token}"
        self.ap_base = f"/review-pack/{self.approver_token}"

    def test_guest_links_cannot_drag_but_any_login_can(self):
        for base in (self.base, self.ap_base):
            r = self.anon.post(base + "/move-slot", json={"item": self.post["item_id"], "date": "2026-11-20"})
            self.assertIn(r.status_code, (403, 401), r.get_json())
        from _lib import users

        users.create_user("Herman", "herm-drag@test.example", "approver", ["stick"], "herm-pass-1")
        self.client.post("/login", data={"email": "herm-drag@test.example", "password": "herm-pass-1"})
        r = self.client.post(
            f"/review-pack/{self.token}/move-slot",
            json={"item": self.post["item_id"], "date": "2026-11-20"},
        )
        self.assertEqual(r.status_code, 200, r.get_json())


def test_remake_only_touches_maybe_and_no(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, pack_id = _catalog(data_dir, monkeypatch)
    posts = [i for i in plan["items"] if i["kind"] == "post"][:3]
    assert len(posts) >= 2
    love, maybe = posts[0], posts[1]
    for slot_id, st in ((love["item_id"], "approve"), (maybe["item_id"], "hold")):
        rp.record_decision(pack_id, slot_id, st, "Herman")
        rp.add_comment(pack_id, slot_id, "Herman", "Note for remake.", role="client")
        png = _png((10, 10, slot_id.__hash__() % 200))
        rp.add_catalog_picture(
            pack_id,
            slot_id,
            png,
            source_url="/x.png",
            content_hash=hashlib.sha256(png).hexdigest()[:32],
            story_data=png,
            google_data=png,
        )
    love_path = rp.image_path(pack_id, love["item_id"], 0)
    love_bytes = love_path.read_bytes() if love_path else b""

    enqueued = []

    def fake_draft(brand, pid, iid, actor="operator", enqueue=None):
        enqueued.append(iid)
        return {"ok": True, "queued": ["draft_caption"]}

    out = cat.remake_from_notes(pack_id, "Christelle", request_draft=fake_draft, limit=4)
    assert out["ok"]
    assert love["item_id"] not in enqueued
    assert maybe["item_id"] in enqueued
    path = rp.image_path(pack_id, love["item_id"], 0)
    assert path and path.read_bytes() == love_bytes


def test_remake_brief_contains_note_loved_look_and_reference_uploads(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, pack_id = _catalog(data_dir, monkeypatch)
    posts = [i for i in plan["items"] if i["kind"] == "post"]
    love, target = posts[0], posts[1]
    rp.record_decision(pack_id, love["item_id"], "approve", "Herman")
    rp.record_decision(pack_id, target["item_id"], "reject", "Herman")
    rp.add_comment(pack_id, target["item_id"], "Herman", "Make it bolder.", role="client")
    png = _png()
    rp.add_catalog_picture(
        pack_id,
        love["item_id"],
        png,
        source_url="/feed.png",
        content_hash=hashlib.sha256(png).hexdigest()[:32],
        story_data=png,
        google_data=png,
    )
    rp.save_upload(
        pack_id,
        target["item_id"],
        _png((1, 2, 3)),
        original_name="ref.png",
        source="Michelle",
        rights=True,
        who="Herman",
        purpose="reference",
        text="Use this palette.",
    )
    brief = cat.build_remake_brief(pack_id, target["item_id"], token="tok")
    blob = json.dumps(brief)
    assert "Make it bolder" in blob
    assert "match this look" in blob.lower() or "Love it" in blob or love["item_id"] in blob
    assert "Use this palette" in blob


def test_remake_queues_at_most_four(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, pack_id = _catalog(data_dir, monkeypatch)
    posts = [i for i in plan["items"] if i["kind"] == "post"]
    for p in posts[:6]:
        rp.record_decision(pack_id, p["item_id"], "hold", "Herman")
        rp.add_comment(pack_id, p["item_id"], "Herman", "Redo", role="client")
        p["calendar_id"] = f"cal-{p['item_id']}"
    cp._write_plan(plan)
    n = []

    def fake_draft(brand, pid, iid, actor="operator", enqueue=None):
        n.append(iid)
        return {"ok": True, "queued": ["draft_caption"]}

    out = cat.remake_from_notes(pack_id, "Kyle", request_draft=fake_draft, limit=4)
    assert out["ok"]
    assert len(n) <= 4
    if len(posts) >= 5:
        assert out.get("more_waiting") or "Press again" in (out.get("message") or "")


def test_remake_hidden_from_client_until_show_to_herman(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, pack_id = _catalog(data_dir, monkeypatch)
    post = next(i for i in plan["items"] if i["kind"] == "post")
    png1, png2 = _png((1, 1, 1)), _png((2, 2, 2))
    rp.add_catalog_picture(
        pack_id,
        post["item_id"],
        png1,
        source_url="/v1.png",
        content_hash=hashlib.sha256(png1).hexdigest()[:32],
        story_data=png1,
        google_data=png1,
    )
    rp.add_catalog_picture(
        pack_id,
        post["item_id"],
        png2,
        source_url="/v2.png",
        content_hash=hashlib.sha256(png2).hexdigest()[:32],
        story_data=png2,
        google_data=png2,
        remake=True,
        shown_to_client=False,
    )
    token = rp.mint_token(URLSafeTimedSerializer("c67-secret"), pack_id, who="Herman")
    guest = rp.public_view(pack_id, token, who="Herman", staff=False)
    item = guest["pack"]["items"][0]
    assert "/image/" in item["images"][0]
    staff = rp.public_view(pack_id, token, who="Christelle", staff=True)
    assert len(staff["pack"]["items"][0]["images"]) >= len(item["images"])
    cat.show_remake_to_client(pack_id, post["item_id"], "Christelle")
    after = rp.public_view(pack_id, token, who="Herman", staff=False)
    assert len(after["pack"]["items"][0]["images"]) == len(staff["pack"]["items"][0]["images"])


def test_feedback_log_appends_mark_and_note(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, pack_id = _catalog(data_dir, monkeypatch)
    post = next(i for i in plan["items"] if i["kind"] == "post")
    cat.log_catalog_feedback(
        BRAND,
        pack_id,
        plan["plan_id"],
        post["item_id"],
        "Herman",
        "hold",
        "Warmer colours please.",
        "/review-pack/x/image/" + post["item_id"] + "/0",
    )
    path = data_dir / "brands" / BRAND / "catalog-feedback.jsonl"
    assert path.is_file()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["mark"] == "hold"
    assert "Warmer" in rows[-1]["note"]
    assert rows[-1]["item_id"] == post["item_id"]
