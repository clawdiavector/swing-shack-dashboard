"""C1 + C2 together: a named login opens the catalog and its marks carry that person (2026-11-09)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from tests.test_catalog_c2_catalog_20261109 import CatalogRouteTests as _Base  # noqa: E402


class CatalogWithLoginsTests(_Base):
    def _named(self, name, role, email):
        from _lib import users

        users.create_user(name, email, role, ["*"], "pw-" + role)
        c = self.app.test_client()
        r = c.post("/login", data={"email": email, "password": "pw-" + role})
        self.assertEqual(r.status_code, 200, r.get_json())
        return c, users.authenticate(email, "pw-" + role)

    def test_named_login_catalog_token_carries_name_and_uid(self):
        plan = self._live_plan()
        herman, user = self._named("Herman", "approver", "herman@example.test")
        from _lib import catalog as cat
        from _lib import review_pack as rp

        pack_id = cat.ensure_for_plan("stick", plan["plan_id"])["pack_id"]
        # A header naming someone else must lose to the login.
        hop = herman.get(f"/catalog/{pack_id}", headers={"X-Actor-Display-Name": "Not Herman"},
                         follow_redirects=False)
        self.assertEqual(hop.status_code, 302)
        token = re.search(r"/review-pack/([^/?]+)", hop.headers["Location"]).group(1)
        share = rp.read_token(self.app_module._serializer, token)
        self.assertEqual(share["who"], "Herman")
        self.assertEqual(share.get("uid"), user["id"])
        post = next(i for i in plan["items"] if i["kind"] == "post")
        act = herman.post(f"/review-pack/{token}/act", json={"item": post["item_id"], "state": "approve"})
        self.assertEqual(act.status_code, 200, act.get_json())
        self.assertEqual(rp.view(pack_id)["decisions"][post["item_id"]]["by"], "Herman")

    def test_any_login_can_mint_guest_link_signed_out_cannot(self):
        plan = self._live_plan()
        jason, _ = self._named("Jason", "contributor", "jason@example.test")
        from _lib import catalog as cat

        pack_id = cat.ensure_for_plan("stick", plan["plan_id"])["pack_id"]
        r = jason.post(f"/api/review-packs/{pack_id}/share", json={"who": "Guest"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.anon.post(f"/api/review-packs/{pack_id}/share", json={"who": "Me"}).status_code, 401)

    def test_editor_can_mint_guest_link(self):
        plan = self._live_plan()
        christelle, _ = self._named("Christelle", "editor", "christelle@example.test")
        from _lib import catalog as cat

        pack_id = cat.ensure_for_plan("stick", plan["plan_id"])["pack_id"]
        r = christelle.post(f"/api/review-packs/{pack_id}/share", json={"who": "Yolanda"})
        self.assertEqual(r.status_code, 200, r.get_json())


def test_refresh_builds_post_index_once(monkeypatch):
    """A catalog with many slots must not rebuild the brand's post index per slot."""
    from _lib import catalog, unified_inbox, marketing_calendar

    calls = {"index": 0}

    def fake_index(*, brand_id):
        calls["index"] += 1
        return object()

    monkeypatch.setattr(unified_inbox, "build_post_index", fake_index)
    monkeypatch.setattr(marketing_calendar, "canonical_records",
                        lambda b: [{"calendar_id": f"c{i}"} for i in range(20)])
    monkeypatch.setattr(unified_inbox, "post_state", lambda rec, index=None: {"composed": {}})
    look = catalog._post_state_once("stick")
    for i in range(20):
        assert look("stick", f"c{i}") == {"composed": {}}
    assert look("stick", "missing") is None
    assert calls["index"] == 1


def test_release_moment_refuses_catalog_hold(monkeypatch):
    """The Release button (Scheduled -> Released) respects Herman's hold too."""
    from _lib import catalog, publish_sandbox

    monkeypatch.setattr(catalog, "is_held", lambda b, c: c == "cal-held")
    out = publish_sandbox.release_moment(brand_id="stick", calendar_id="cal-held", dispatch=False)
    assert out["ok"] is False and out["code"] == "catalog_hold"
    assert "Maybe/No" in out["error"]


def test_calendar_move_also_moves_the_catalog_slot(tmp_path, monkeypatch):
    """Moving a placed post on the catalog moves its calendar entry AND the slot's day."""
    from tests.test_catalog_c67_calendar_remake_20261109 import _catalog, BRAND, cp
    from _lib import catalog as cat
    from _lib import review_pack as rp

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    plan, pack_id = _catalog(tmp_path, monkeypatch)
    post = next(i for i in plan["items"] if i["kind"] == "post")
    post["calendar_id"] = "cal-int-move"
    cp._write_plan(plan)
    out = cat.move_slot_day(pack_id, post["item_id"], "2026-11-28", "Christelle",
                            calendar_move=lambda b, body, who: ({"ok": True}, 200))
    assert out["ok"]
    moved = next(i for i in cp.get_plan(BRAND, plan["plan_id"])["items"] if i["item_id"] == post["item_id"])
    assert moved["due"] == "2026-11-28"
    slot = next(i for i in rp.get_pack(pack_id)["items"] if i["id"] == post["item_id"])
    assert slot["when"] == "Sat 28 Nov"



def test_ready_made_google_version_wins(tmp_path, monkeypatch):
    """When the draft pipeline already made a Google version, the catalog uses it, not a crop."""
    from tests.test_catalog_c67_calendar_remake_20261109 import _catalog, BRAND, cp
    from tests.test_catalog_c3_pictures_20261109 import _feed_png
    from _lib import catalog as cat
    from _lib import review_pack as rp

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    plan, pack_id = _catalog(tmp_path, monkeypatch)
    post = next(i for i in plan["items"] if i["kind"] == "post")
    post["calendar_id"] = "cal-gbp"
    cp._write_plan(plan)
    feed, gbp = _feed_png(800, 1000), _feed_png(1200, 900, center=(1, 2, 250))
    files = {"proof://feed": feed, "proof://gbp": gbp}
    cat.refresh_pictures(BRAND, plan["plan_id"],
                         post_state=lambda b, c: {"composed": {"instagram": "proof://feed", "gbp": "proof://gbp"}} if c == "cal-gbp" else None,
                         load_bytes=lambda b, u: files.get(u))
    path = rp.image_path(pack_id, post["item_id"], 0, size="google")
    assert path is not None and path.read_bytes() == gbp


def test_page_has_cards_per_row_and_full_size_view():
    """Kyle 9 Nov: cards side by side with a per-row setting, and a full-size view of every picture."""
    from _lib import review_pack as rp

    html = rp.render_page({"pack": {"title": "T", "items": []}, "decisions": {}, "comments": [],
                           "uploads": [], "done": [], "staff": False}, token="tok")
    assert "Cards per row" in html
    for v in ('"auto","Auto"', '["1","1"]', '["4","4"]'):
        assert v in html
    assert "View full size" in html
    assert 'D.catalog_upload?"auto":"1"' in html  # catalogs start side by side; other packs as before


def test_link_signed_with_another_key_is_refused():
    """No fallback key: a link signed with anything but the app's own secret opens nothing."""
    from itsdangerous import URLSafeTimedSerializer
    import app as app_module

    forged = URLSafeTimedSerializer("not-a-real-secret").dumps(
        {"scope": "review_pack", "pack": "any-pack", "who": "Herman", "role": "approver"})
    with app_module.app.test_request_context("/"):
        assert app_module._rp_share(forged) is None
        assert app_module._rp_token_ok(forged) is False


def test_feedback_log_holds_no_signed_link(tmp_path, monkeypatch):
    from tests.test_catalog_c67_calendar_remake_20261109 import _catalog
    from _lib import catalog as cat
    from _lib import review_pack as rp

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    plan, pack_id = _catalog(tmp_path, monkeypatch)
    slot = rp.get_pack(pack_id)["items"][0]["id"]
    cat.feedback_from_mark(pack_id, slot, "reject", "Herman", token="SECRET-TOKEN-abc", note="Too busy")
    logs = list((tmp_path / "brands").rglob("catalog-feedback.jsonl"))
    text = logs[0].read_text()
    assert "SECRET-TOKEN" not in text and "/review-pack/" not in text
    assert "Too busy" in text


def test_remade_picture_is_hidden_until_shown(tmp_path, monkeypatch):
    """Remake from notes -> the next picture for that slot is a remake Herman cannot see yet."""
    from tests.test_catalog_c67_calendar_remake_20261109 import _catalog, BRAND, cp
    from tests.test_catalog_c3_pictures_20261109 import _feed_png
    from _lib import catalog as cat
    from _lib import review_pack as rp

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    plan, pack_id = _catalog(tmp_path, monkeypatch)
    post = next(i for i in plan["items"] if i["kind"] == "post")
    post["calendar_id"] = "cal-remake"
    cp._write_plan(plan)
    files = {"u1": _feed_png(800, 1000), "u2": _feed_png(800, 1000, center=(9, 9, 240))}
    cur = {"u": "u1"}
    ps = lambda b, c: {"composed": {"instagram": cur["u"]}} if c == "cal-remake" else None
    lb = lambda b, u: files.get(u)
    cat.refresh_pictures(BRAND, plan["plan_id"], post_state=ps, load_bytes=lb)
    rp.record_decision(pack_id, post["item_id"], "reject", "Herman")
    out = cat.remake_from_notes(pack_id, "Christelle", request_draft=lambda *a, **k: {"ok": True})
    assert post["item_id"] in out["queued"]
    cur["u"] = "u2"
    cat.refresh_pictures(BRAND, plan["plan_id"], post_state=ps, load_bytes=lb)
    item = next(i for i in rp.get_pack(pack_id)["items"] if i["id"] == post["item_id"])
    assert item["picture_meta"][-1]["remake"] is True
    assert item["picture_meta"][-1]["shown_to_client"] is False
    assert cat.client_picture_index(item, staff=False) == 0  # Herman still sees the first one
    cat.show_remake_to_client(pack_id, post["item_id"], "Christelle")
    item = next(i for i in rp.get_pack(pack_id)["items"] if i["id"] == post["item_id"])
    assert cat.client_picture_index(item, staff=False) == 1


def test_unchanged_picture_is_not_read_again(tmp_path, monkeypatch):
    from tests.test_catalog_c67_calendar_remake_20261109 import _catalog, BRAND, cp
    from tests.test_catalog_c3_pictures_20261109 import _feed_png
    from _lib import catalog as cat

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    plan, pack_id = _catalog(tmp_path, monkeypatch)
    post = next(i for i in plan["items"] if i["kind"] == "post")
    post["calendar_id"] = "cal-same"
    cp._write_plan(plan)
    reads = []
    ps = lambda b, c: {"composed": {"instagram": "u1"}} if c == "cal-same" else None
    def lb(b, u):
        reads.append(u)
        return _feed_png(800, 1000)
    cat.refresh_pictures(BRAND, plan["plan_id"], post_state=ps, load_bytes=lb)
    cat.refresh_pictures(BRAND, plan["plan_id"], post_state=ps, load_bytes=lb)
    assert reads == ["u1"]


def test_shared_password_session_can_drag_and_approve_campaign():
    from _lib import catalog as cat

    assert cat.staff_can_drag(staff=True, session_user=None, share_role=None) is True
    assert cat.staff_can_drag(staff=False, session_user=None, share_role="approver") is False
