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

    def test_contributor_cannot_mint_guest_link(self):
        plan = self._live_plan()
        jason, _ = self._named("Jason", "contributor", "jason@example.test")
        from _lib import catalog as cat

        pack_id = cat.ensure_for_plan("stick", plan["plan_id"])["pack_id"]
        r = jason.post(f"/api/review-packs/{pack_id}/share", json={"who": "Guest"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("cannot share", r.get_json()["error"])

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
