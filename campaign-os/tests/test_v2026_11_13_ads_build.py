"""One-click build: a suggestion becomes a switched-off ad in Meta, after a preview and a yes, with undo. Fake Meta."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_11_13_ad_suggestions as t  # noqa: E402
import test_v2026_11_13_ad_suggestions_types as ty  # noqa: E402
from _lib import ads_actions, ads_build  # noqa: E402

ACCOUNT = "act_123"
IDENTITY = {"page_id": "555", "ig_user_id": "777"}


class Signer:
    def dumps(self, obj):
        return json.dumps(obj)

    def loads(self, s, max_age=None):
        return json.loads(s)


class FakeMeta:
    def __init__(self, fail_on=None, ad_status="PAUSED"):
        self.calls, self.n, self.fail_on, self.ad_status, self.deleted = [], 100, fail_on, ad_status, []

    def __call__(self, method, path, token, params=None):
        self.calls.append((method, path, dict(params or {}), token))
        if method == "GET" and path.endswith("/promote_pages"):
            return {"data": [{"id": "555", "name": "Stick"}]}
        if method == "GET" and path == "555":
            return {"id": "555", "instagram_business_account": {"id": "777"}, "access_token": "page-tok"}
        if method == "GET":
            return {"id": path, "status": self.ad_status, "effective_status": self.ad_status}
        if method == "DELETE":
            self.deleted.append(path)
            return {"success": True}
        if self.fail_on and path.endswith(self.fail_on):
            raise ads_actions.ActionRefused("Meta said: no", 502)
        if method == "POST" and path.isdigit():  # an update, e.g. archiving a form
            return {"success": True}
        self.n += 1
        return {"id": str(self.n)}


class Store:
    def __init__(self):
        self.files = {}

    def read(self, rel):
        return self.files.get(rel)

    def write(self, rel, obj):
        self.files[rel] = json.loads(json.dumps(obj))


def _suggestion(post=t.FITTING_REEL, brand="stick"):
    return t._by_post(t._build([post], brand=brand))[post["_media"]["id"]]


def _posts(calls, suffix):
    return [c for c in calls if c[0] == "POST" and c[1].endswith(suffix)]


def test_a_lead_ad_plan_is_all_switched_off_with_a_higher_intent_form():
    calls = ads_build.plan_calls(_suggestion(), brand_id="stick", account_id=ACCOUNT, identity=IDENTITY)
    steps = [c["step"] for c in calls]
    assert steps == ["form", "campaign", "adset", "creative", "ad"]
    by = {c["step"]: c for c in calls}
    assert by["form"]["path"] == "555/leadgen_forms" and by["form"]["token"] == "page"
    form = by["form"]["params"]
    assert json.loads(form["questions"])[0]["type"] == "FULL_NAME"
    assert form["is_optimized_for_quality"] == "true"
    assert json.loads(form["privacy_policy"])["url"].startswith("https://stickgolf.co.za/")
    for step in ("campaign", "adset", "ad"):
        assert by[step]["params"]["status"] == "PAUSED"
    assert by["campaign"]["params"]["objective"] == "OUTCOME_LEADS"
    assert by["adset"]["params"]["daily_budget"] == "3000"  # R30 in cents
    assert by["adset"]["params"]["optimization_goal"] == "LEAD_GENERATION"
    assert by["adset"]["params"]["destination_type"] == "ON_AD"
    creative = by["creative"]["params"]
    assert creative["source_instagram_media_id"] == "f1"
    assert json.loads(creative["call_to_action"])["value"]["lead_gen_form_id"] == "{form_id}"
    assert "utm_source=meta" in creative["url_tags"]


def test_each_type_gets_its_own_goal_and_destination():
    goals = {}
    for post, brand in ((ty.DM_SERVICE_REEL, "stick"), (ty.WEBSITE_REEL, "swing-shack")):
        s = _suggestion(post, brand)
        calls = {c["step"]: c for c in ads_build.plan_calls(s, brand_id=brand, account_id=ACCOUNT, identity=IDENTITY)}
        goals[s["ad_type"]] = (calls["adset"]["params"]["optimization_goal"],
                               calls["adset"]["params"].get("destination_type"), "form" in calls)
    assert goals["messages"] == ("CONVERSATIONS", "MESSAGING_INSTAGRAM_DIRECT_MESSENGER", False)
    assert goals["traffic"] == ("LANDING_PAGE_VIEWS", "WEBSITE", False)


def test_preview_reads_only_and_finds_the_page_and_instagram_account():
    meta = FakeMeta()
    out = ads_build.preview("stick", _suggestion(), graph=meta, token="tok", account_id=ACCOUNT, signer=Signer())
    assert all(c[0] == "GET" for c in meta.calls)
    assert out["identity"] == IDENTITY and out["ticket"]
    assert [c["step"] for c in out["calls"]][0] == "form"


def test_nothing_is_created_while_writes_are_switched_off(monkeypatch):
    monkeypatch.delenv("ADS_WRITES_ENABLED", raising=False)
    meta, store = FakeMeta(), Store()
    ticket = ads_build.preview("stick", _suggestion(), graph=meta, token="tok", account_id=ACCOUNT,
                               signer=Signer())["ticket"]
    with pytest.raises(ads_actions.ActionRefused):
        ads_build.apply("stick", ticket, graph=meta, token="tok", account_id=ACCOUNT, signer=Signer(),
                        read=store.read, write=store.write)
    assert not [c for c in meta.calls if c[0] == "POST"]


def _apply(meta, store, monkeypatch):
    monkeypatch.setenv("ADS_WRITES_ENABLED", "1")
    ticket = ads_build.preview("stick", _suggestion(), graph=meta, token="tok", account_id=ACCOUNT,
                               signer=Signer())["ticket"]
    return ads_build.apply("stick", ticket, graph=meta, token="tok", account_id=ACCOUNT, signer=Signer(),
                           read=store.read, write=store.write)


def test_apply_builds_in_order_passing_ids_on_and_logs_it_with_undo(monkeypatch):
    meta, store = FakeMeta(), Store()
    entry = _apply(meta, store, monkeypatch)
    adset = _posts(meta.calls, "/adsets")[0][2]
    assert adset["campaign_id"] == "102"  # form 101, campaign 102
    creative = _posts(meta.calls, "/adcreatives")[0][2]
    assert json.loads(creative["call_to_action"])["value"]["lead_gen_form_id"] == "101"
    assert _posts(meta.calls, "/leadgen_forms")[0][3] == "page-tok"
    assert entry["kind"] == "build_ad" and entry["created"]["ad"] == "105"
    log = store.files["brands/stick/ads-actions/log.json"]["entries"]
    assert log[-1]["id"] == entry["id"]


def test_a_failure_halfway_removes_what_was_made(monkeypatch):
    meta, store = FakeMeta(fail_on="/adcreatives"), Store()
    with pytest.raises(ads_actions.ActionRefused) as e:
        _apply(meta, store, monkeypatch)
    assert "removed" in str(e.value).lower()
    assert meta.deleted == ["103", "102"]  # ad set, then campaign
    assert "brands/stick/ads-actions/log.json" not in store.files


def test_undo_removes_a_build_that_was_never_switched_on(monkeypatch):
    meta, store = FakeMeta(), Store()
    entry = _apply(meta, store, monkeypatch)
    out = ads_actions.undo("stick", entry["id"], graph=meta, token="tok", account_id=ACCOUNT,
                           read=store.read, write=store.write)
    assert out["undone_at"]
    assert meta.deleted == ["105", "104", "103", "102"]


def test_undo_refuses_once_someone_switched_it_on(monkeypatch):
    meta, store = FakeMeta(), Store()
    entry = _apply(meta, store, monkeypatch)
    meta.ad_status = "ACTIVE"
    with pytest.raises(ads_actions.ActionRefused):
        ads_actions.undo("stick", entry["id"], graph=meta, token="tok", account_id=ACCOUNT,
                         read=store.read, write=store.write)
    assert meta.deleted == []
