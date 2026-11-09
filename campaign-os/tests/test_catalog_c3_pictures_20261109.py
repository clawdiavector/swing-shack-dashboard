"""C3 — catalog slots pull composed pictures in every size (2026-11-09)."""
from __future__ import annotations

import hashlib
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

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import campaign_plan as cp  # noqa: E402

TODAY = date(2026, 10, 13)
TOKEN = "test-job-token-not-a-secret"
PASSWORD = "swing-shack-dev-2026"
BRAND = "stick"


def brief(status="approved", d="2026-12-05", bid="brf-c3pic001"):
    return {"brief_id": bid, "status": status, "source_opportunity": {"name": "Black Friday", "date": d}}


def _plan(data_dir, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    out = cp.propose_plan(BRAND, brief(), today=TODAY)
    assert out["ok"]
    return out["plan"]


def _feed_png(w: int = 800, h: int = 1000, center=(200, 80, 40)) -> bytes:
    from PIL import Image

    im = Image.new("RGB", (w, h), (240, 240, 240))
    band = max(4, h // 20)
    y0 = h // 2 - band // 2
    for y in range(y0, y0 + band):
        for x in range(w):
            im.putpixel((x, y), center)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _brand_image(data_dir: Path, name: str, data: bytes) -> str:
    rel = f"/brand-images/{BRAND}/{name}"
    dest = data_dir / "draft-assets" / "images" / BRAND
    dest.mkdir(parents=True, exist_ok=True)
    (dest / name).write_bytes(data)
    return rel


def _attach_calendar(plan, item_id: str, calendar_id: str) -> None:
    path = Path(cp._plan_path(BRAND, plan["plan_id"]))
    doc = json.loads(path.read_text(encoding="utf-8"))
    for it in doc["items"]:
        if it["item_id"] == item_id:
            it["calendar_id"] = calendar_id
            break
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _catalog_setup(data_dir, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    from _lib import catalog as cat

    plan = _plan(data_dir, monkeypatch)
    post = next(i for i in plan["items"] if i["kind"] == "post")
    _attach_calendar(plan, post["item_id"], "cal-c3-test-001")
    pack_id = cat.ensure_for_plan(BRAND, plan["plan_id"])["pack_id"]
    return plan, post, pack_id


def _fake_state(url: str, caption: str = "Draft caption from the lodge.", *, story_url: str = ""):
    composed = {"instagram": url}
    if story_url:
        composed["instagram_story"] = story_url
    return {"composed": composed, "caption": caption, "body": caption}


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    return tmp_path


def test_refresh_adds_composed_picture_as_new_version(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, post, pack_id = _catalog_setup(data_dir, monkeypatch)
    png = _feed_png()
    url = _brand_image(data_dir, "feed-v1.png", png)

    def fake_state(_brand, _cal):
        return _fake_state(url)

    out = cat.refresh_pictures(BRAND, plan["plan_id"], post_state=fake_state, load_bytes=lambda _b, _u: png)
    assert out["added"] >= 1
    item = next(i for i in rp.get_pack(pack_id)["items"] if i["id"] == post["item_id"])
    assert item.get("version", 1) >= 2
    assert item["images"]
    assert item.get("picture_hashes")


def test_refresh_is_idempotent(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, post, pack_id = _catalog_setup(data_dir, monkeypatch)
    png = _feed_png()
    url = _brand_image(data_dir, "feed-idem.png", png)

    def fake_state(_brand, _cal):
        return _fake_state(url)

    kw = {"post_state": fake_state, "load_bytes": lambda _b, _u: png}
    cat.refresh_pictures(BRAND, plan["plan_id"], **kw)
    cat.refresh_pictures(BRAND, plan["plan_id"], **kw)
    item = next(i for i in rp.get_pack(pack_id)["items"] if i["id"] == post["item_id"])
    assert len(item.get("picture_hashes") or []) == 1
    assert len(item["images"]) == 1


def test_new_version_resets_only_that_slot_decision(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, post, pack_id = _catalog_setup(data_dir, monkeypatch)
    story = next(i for i in plan["items"] if i["kind"] == "story")
    rp.record_decision(pack_id, post["item_id"], "approve", "Herman")
    rp.record_decision(pack_id, story["item_id"], "approve", "Herman")

    png = _feed_png()
    url = _brand_image(data_dir, "feed-dec.png", png)

    cat.refresh_pictures(
        BRAND,
        plan["plan_id"],
        post_state=lambda _b, cal: _fake_state(url) if cal == "cal-c3-test-001" else None,
        load_bytes=lambda _b, _u: png,
    )
    d = rp.view(pack_id)["decisions"]
    assert post["item_id"] not in d
    assert d[story["item_id"]]["state"] == "approve"


def test_caption_filled_from_draft_but_never_overwrites_edited(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, post, pack_id = _catalog_setup(data_dir, monkeypatch)
    rp.update_item_fields(pack_id, post["item_id"], {"caption": "Christelle rewrote this.", "caption_auto": False})
    png = _feed_png()
    url = _brand_image(data_dir, "feed-cap.png", png)
    cat.refresh_pictures(
        BRAND,
        plan["plan_id"],
        post_state=lambda _b, _c: _fake_state(url, "Auto caption from draft."),
        load_bytes=lambda _b, _u: png,
    )
    item = next(i for i in rp.get_pack(pack_id)["items"] if i["id"] == post["item_id"])
    assert item["caption"] == "Christelle rewrote this."

    rp.update_item_fields(pack_id, post["item_id"], {"caption": "", "caption_auto": True})
    cat.refresh_pictures(
        BRAND,
        plan["plan_id"],
        post_state=lambda _b, _c: _fake_state(url, "Auto caption from draft."),
        load_bytes=lambda _b, _u: png,
    )
    item = next(i for i in rp.get_pack(pack_id)["items"] if i["id"] == post["item_id"])
    assert "Auto caption" in item["caption"]


def test_google_crop_is_4x3_no_stretch():
    from _lib.feed_vertical_renders import fit_google_4x3
    from PIL import Image

    tall = _feed_png(600, 1200, center=(10, 200, 10))
    jpg, _ = fit_google_4x3(tall)
    with Image.open(io.BytesIO(jpg)) as im:
        assert im.size == (1200, 900)
        px = im.getpixel((600, 450))
        assert px[1] > px[0], "centre band survives"
        top = im.getpixel((600, 3))
        assert min(top) > 200, "the top edge of the picture is kept (a headline is never cut off)"
        side = im.getpixel((20, 450))
        assert max(side) < 200, "the sides are the darkened blur fill"

    wide = _feed_png(1600, 600, center=(40, 40, 200))
    jpg2, _ = fit_google_4x3(wide)
    with Image.open(io.BytesIO(jpg2)) as im:
        assert im.size == (1200, 900)
        # 1600x600 fits as 1200x450 in the middle; the 30px band becomes ~22px.
        # Stretched to 900 tall it would be ~45px and still cover y=470.
        mid = im.getpixel((600, 450))
        assert mid[2] > mid[0] + 60, "the picture's centre band survives"
        below = im.getpixel((600, 472))
        assert not (below[2] > below[0] + 60), "the picture is not stretched taller"


def test_story_render_is_9x16():
    from _lib.feed_vertical_renders import fit_for_channel_png
    from PIL import Image

    png, _ = fit_for_channel_png(_feed_png(), "instagram_story")
    with Image.open(io.BytesIO(png)) as im:
        assert im.size == (1080, 1920)


class SizeImageRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-c3-size-route-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_SANDBOX_DIR", "COS_JOB_TOKEN", "BUNDLED_DATA_DIR")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["BUNDLED_DATA_DIR"] = str(REPO_ROOT / "data")
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        os.environ["COS_JOB_TOKEN"] = TOKEN
        import app as app_module

        cls.app_module = app_module
        cls.rp = app_module  # lazy

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
        from _lib import review_pack as rp

        self.rp = rp
        self.pack = rp.create_pack("Size route", [{"id": "slot-a", "title": "A", "kind": "single"}])
        self.token = self.rp.mint_token(self.app_module._serializer, self.pack["id"])
        self.base = f"/review-pack/{self.token}"
        data = _feed_png()
        self.rp.add_catalog_picture(
            self.pack["id"],
            "slot-a",
            data,
            source_url="/brand-images/stick/x.png",
            content_hash=hashlib.sha256(data).hexdigest()[:16],
            story_data=data,
            google_data=fit_google_stub(data),
        )
        self.anon = self.app_module.app.test_client(cos_anon=True)

    def test_size_image_route_needs_token(self):
        ok = self.anon.get(self.base + "/image/slot-a/0?size=story")
        self.assertEqual(ok.status_code, 200)
        bad = self.anon.get(f"/review-pack/{self.token}x/image/slot-a/0?size=google")
        self.assertEqual(bad.status_code, 404)


def fit_google_stub(feed_png: bytes) -> bytes:
    from _lib.feed_vertical_renders import fit_google_4x3

    jpg, _ = fit_google_4x3(feed_png)
    return jpg


def test_review_page_has_feed_story_google_tabs(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp
    from itsdangerous import URLSafeTimedSerializer

    plan, post, pack_id = _catalog_setup(data_dir, monkeypatch)
    png = _feed_png()
    url = _brand_image(data_dir, "feed-tabs.png", png)
    cat.refresh_pictures(
        BRAND,
        plan["plan_id"],
        post_state=lambda _b, _c: _fake_state(url),
        load_bytes=lambda _b, _u: png,
    )
    ser = URLSafeTimedSerializer("dev")
    token = rp.mint_token(ser, pack_id, who="Herman")
    page = rp.render_page(rp.public_view(pack_id, token), token=token)
    assert "Feed" in page and "Story" in page and "Google" in page
    assert "size-tabs" in page or 'data-size-tab' in page


def test_catalog_header_counts_with_pictures(data_dir, monkeypatch):
    from _lib import catalog as cat
    from _lib import review_pack as rp

    plan, post, pack_id = _catalog_setup(data_dir, monkeypatch)
    pack = rp.get_pack(pack_id)
    before = cat.catalog_header(pack)
    assert "with pictures" in before
    png = _feed_png()
    url = _brand_image(data_dir, "feed-hdr.png", png)
    cat.refresh_pictures(
        BRAND,
        plan["plan_id"],
        post_state=lambda _b, _c: _fake_state(url),
        load_bytes=lambda _b, _u: png,
    )
    pack = rp.get_pack(pack_id)
    line = cat.catalog_header(pack)
    assert re.search(r"\d+ with pictures", line)
