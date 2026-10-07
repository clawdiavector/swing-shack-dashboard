"""POST /api/posts/lodge — a finished post from anywhere onto the shelf (2026-10-07).

The flow under test is the one an operator runs from Claude Code with only a
COS_JOB_TOKEN: send an image, caption and date; the post appears on This week
and on the shelf as `scheduled`, one Release click from going out.
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
TOKEN = "test-job-token-not-a-secret"
BRAND = "swing-shack"


def _image(w: int = 1024, h: int = 1024, fmt: str = "JPEG", colour=(20, 90, 60)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, format=fmt)
    return buf.getvalue()


def _day(offset: int = 2) -> str:
    return (datetime.now(ZoneInfo("Africa/Johannesburg")).date() + timedelta(days=offset)).isoformat()


class PostLodgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-post-lodge-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_SANDBOX_DIR", "COS_JOB_TOKEN")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        os.environ["COS_JOB_TOKEN"] = TOKEN
        sys.path.insert(0, str(CAMPAIGN_OS))
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
        os.environ["PUBLISH_SANDBOX_DIR"] = str(self.tmpdir / "publish-sandbox")
        self.app_module.DATA_DIR = str(self.tmpdir)
        self.app_module.COS_JOB_TOKEN = TOKEN
        for child in self.tmpdir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        (self.tmpdir / "campaign-data.json").write_text(json.dumps({"campaigns": {}}))
        for name in list(sys.modules):
            if name.startswith("_lib.") and name != "_lib":
                del sys.modules[name]
        from _lib import marketing_calendar, publish_sandbox

        publish_sandbox.ensure_sandbox_layout()
        # The purge above re-imports marketing_calendar without app.py's V2.6
        # write-gate. Put the gate back over the fresh module so these tests
        # meet the same refusal production does.
        app = self.app_module
        self._gate_orig = app._v26_mc_orig_upsert_event
        app._v26_mc_orig_upsert_event = marketing_calendar.upsert_event
        marketing_calendar.upsert_event = app._v26_wrapped_upsert_event
        # Bearer only — no session cookie — so this is what a laptop sees.
        self.client = app.app.test_client(cos_anon=True)
        self.auth = {"Authorization": f"Bearer {TOKEN}",
                     "X-Actor-Display-Name": "christelle"}

    def tearDown(self):
        self.app_module._v26_mc_orig_upsert_event = self._gate_orig

    def _named(self):
        """A request context the calendar gate accepts, for direct upserts."""
        return self.app_module.app.test_request_context(
            headers={"X-Actor-Display-Name": "test"})

    def _lodge(self, **overrides):
        body = {
            "brand": BRAND,
            "slug": "spoon-wrong-clubs",
            "date": _day(),
            "caption": "You wouldn't dig with a spoon.\n\nSo why play the wrong clubs?",
            "image_base64": base64.b64encode(_image()).decode(),
            "created_by": "christelle",
        }
        body.update(overrides)
        body = {k: v for k, v in body.items() if v is not None}
        return self.client.post("/api/posts/lodge", json=body, headers=self.auth)

    # ── the main flow ────────────────────────────────────────────────

    def test_image_lands_on_shelf_and_week_then_releases(self):
        self.assertEqual(
            self.client.post("/api/posts/lodge", json={}).status_code, 401,
            "no token must be refused")

        r = self._lodge()
        self.assertEqual(r.status_code, 200, r.get_json())
        doc = r.get_json()
        self.assertEqual(doc["state"], "scheduled")
        self.assertEqual(doc["next_action"], "On the shelf")
        self.assertEqual(sorted(doc["images"]), ["facebook", "instagram"])
        self.assertEqual(doc["publish_queue_rows"], 2)
        self.assertTrue(doc["links"]["shelf"].endswith("/app/shelf"))

        from PIL import Image

        out_dir = self.tmpdir / "draft-assets" / "images" / BRAND
        for ch in ("instagram", "facebook"):
            png = out_dir / f"composed-spoon-wrong-clubs-{ch}.png"
            self.assertTrue(png.is_file())
            self.assertTrue((out_dir / f"composed-spoon-wrong-clubs-{ch}-publish.jpg").is_file())
            with Image.open(png) as im:
                self.assertEqual(im.size, (1080, 1080), "a square stays square")
        uploads = list((self.tmpdir / "operator-uploads" / BRAND).iterdir())
        self.assertEqual(len(uploads), 1)

        from _lib import unified_inbox

        week = unified_inbox.week_board(brand_id=BRAND)
        posts = [p for d in week["days_list"] for p in d["posts"]]
        mine = [p for p in posts if p.get("asset_id") == "swing-shack-spoon-wrong-clubs"]
        self.assertEqual(len(mine), 1, "the post must join its moment on This week")
        self.assertEqual(mine[0]["state"], "scheduled")
        self.assertEqual(mine[0]["go_live_date"], _day())

        shelf = unified_inbox.shelf_board(brand_id=BRAND)
        self.assertEqual(shelf["counts"]["scheduled"], 1)

        from _lib.publish_sandbox import release_moment

        rel = release_moment(brand_id=BRAND, calendar_id=doc["calendar_id"],
                             editor="christelle", dispatch=False)
        self.assertTrue(rel.get("ok"), rel)
        self.assertEqual(unified_inbox.post_state_for(BRAND, doc["calendar_id"])["state"], "released")

        again = self._lodge(caption="Changed after release")
        self.assertEqual(again.status_code, 409, "a released post must not be silently edited")

    def test_relodge_is_idempotent_and_edits_rerender(self):
        first = self._lodge().get_json()
        same = self._lodge()
        self.assertEqual(same.status_code, 200)
        self.assertFalse(same.get_json()["rendered"], "an identical lodge renders nothing")
        self.assertEqual(same.get_json()["state"], "scheduled")

        edited = self._lodge(caption="Fit first. Hit second.").get_json()
        self.assertTrue(edited["rendered"])
        self.assertEqual(edited["state"], "scheduled", "an edit is re-approved onto the shelf")
        data = json.loads((self.tmpdir / "campaign-data.json").read_text())
        asset = data["campaigns"]["swing-shack-calendar"]["assets"]["swing-shack-spoon-wrong-clubs"]
        self.assertEqual(asset["caption"], "Fit first. Hit second.")
        self.assertEqual(asset["renderMode"], "operator-image")

        from _lib.publish_sandbox import queue_rows_for_brand

        rows = [r for r in queue_rows_for_brand(BRAND)
                if "swing-shack-spoon-wrong-clubs" in str(r.get("idempotency_key"))]
        self.assertEqual(len(rows), 2, "re-approving must not duplicate queue rows")
        self.assertEqual(first["calendar_id"] != "", True)

    def test_approve_false_stops_in_review(self):
        doc = self._lodge(approve=False).get_json()
        self.assertEqual(doc["state"], "draft_ready")
        self.assertEqual(doc["next_action"], "Ready to review")
        from _lib import unified_inbox

        pending = unified_inbox.list_items(brand=BRAND, status="pending")
        ids = {i.get("id") for i in pending.get("items") or []}
        self.assertIn("draft_asset:swing-shack-calendar:swing-shack-spoon-wrong-clubs", ids,
                      "the brand's Review list must show it")

    def test_multipart_upload(self):
        r = self.client.post(
            "/api/posts/lodge",
            data={
                "brand": BRAND, "slug": "multipart-post", "date": _day(3),
                "caption": "From a form", "channels": "instagram",
                "image": (io.BytesIO(_image(fmt="PNG")), "art.png"),
            },
            content_type="multipart/form-data",
            headers=self.auth,
        )
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(list(r.get_json()["images"]), ["instagram"])
        self.assertEqual(r.get_json()["upload"]["format"], "PNG")

    def test_tall_image_is_cropped_and_says_so(self):
        doc = self._lodge(image_base64=base64.b64encode(_image(1080, 1920)).decode()).get_json()
        self.assertEqual(doc["state"], "scheduled")
        self.assertTrue(any("cropped" in n for n in doc["notes"]), doc["notes"])
        from PIL import Image

        png = self.tmpdir / "draft-assets" / "images" / BRAND / "composed-spoon-wrong-clubs-instagram.png"
        with Image.open(png) as im:
            self.assertEqual(im.size, (1080, 1350), "taller than 4:5 is cut to 4:5")

    def test_archetype_mode_still_composes(self):
        doc = self._lodge(
            image_base64=None, slug="fitting-template", archetype="ss-fitting-headline",
            fields={"caption_hook": "YOU WOULDN'T DIG WITH A SPOON.",
                    "service_lockup": "WHY PLAY THE WRONG CLUBS?"},
        )
        self.assertEqual(doc.status_code, 200, doc.get_json())
        self.assertEqual(doc.get_json()["state"], "scheduled")

    # ── refusals ────────────────────────────────────────────────────

    def test_name_is_required_by_the_calendar_gate(self):
        r = self.client.post(
            "/api/posts/lodge", headers={"Authorization": f"Bearer {TOKEN}"},
            json={"brand": BRAND, "slug": "nameless", "date": _day(), "caption": "x",
                  "image_base64": base64.b64encode(_image()).decode()})
        self.assertEqual(r.status_code, 400)
        self.assertIn("X-Actor-Display-Name", r.get_json()["error"])

    def test_validation_refusals(self):
        cases = {
            "bad brand": dict(brand="nike"),
            "bad slug": dict(slug="Spoon Post!"),
            "past date": dict(date="2020-01-01"),
            "no caption": dict(caption="  "),
            "both modes": dict(archetype="ss-fitting-headline"),
            "neither mode": dict(image_base64=None),
            "not an image": dict(image_base64=base64.b64encode(b"hello").decode()),
            "bad base64": dict(image_base64="%%%not-base64%%%"),
        }
        for name, override in cases.items():
            with self.subTest(name):
                r = self._lodge(**override)
                self.assertEqual(r.status_code, 400, (name, r.get_json()))
                self.assertFalse(r.get_json()["ok"])

    def test_render_spec_image_cannot_escape_uploads(self):
        from _lib.jobs.layer5 import render_batch
        from _lib.marketing_calendar import upsert_event

        with self._named():
            upsert_event(BRAND, {
                "event_key": f"{BRAND}:escape", "type": "moment", "status": "approved",
                "title": "x", "event_date": _day(), "event_start": _day(),
                "source_origin": "internal_strategy",
                "render_spec": {"slug": "escape", "caption": "x",
                                "image": "../../campaign-data.json"},
            })
        out = render_batch.run(BRAND, event_key=f"{BRAND}:escape")
        self.assertEqual(out["rendered"], 0)
        self.assertIn("inside operator-uploads", " ".join(out["problems"]))

    def test_sidecar_follows_a_new_revision(self):
        doc = self._lodge().get_json()
        from _lib.jobs.layer5 import render_batch
        from _lib.marketing_calendar import canonical_records, upsert_event
        from _lib import unified_inbox

        rec = next(r for r in canonical_records(BRAND) if r["event_key"] == doc["event_key"])
        edited = {k: v for k, v in rec.items()
                  if k not in ("calendar_id", "revision", "supersedes_calendar_id")}
        edited["event_date"] = edited["event_start"] = edited["event_end"] = _day(4)
        with self._named():
            upsert_event(BRAND, edited)
        new_cal = next(r for r in canonical_records(BRAND)
                       if r["event_key"] == doc["event_key"])["calendar_id"]
        self.assertNotEqual(new_cal, doc["calendar_id"], "an edit is a new revision id")

        out = render_batch.run(BRAND)
        self.assertEqual(out["rendered"], 0, "the render_spec did not change")
        self.assertEqual(out["rejoined"], [doc["event_key"]])
        self.assertEqual(unified_inbox.post_state_for(BRAND, new_cal)["asset_id"],
                         "swing-shack-spoon-wrong-clubs")


if __name__ == "__main__":
    unittest.main()
