"""Naming rule, UTM template, and the rename and tag changes (preview, approve, undo). Meta is faked."""
import datetime as dt
import json

import pytest
from itsdangerous import URLSafeTimedSerializer

from _lib import ads_actions as aa
from _lib import ads_naming as an
from _lib import ads_tracking as at

TODAY = dt.date(2026, 10, 21)
ACCT = "act_111"


def _ad(i="555", name="New Traffic Ad with recommended settings", obj="OUTCOME_TRAFFIC", media="video",
        body="Get fitted with TrackMan at Swing Shack", camp="Putter Traffic Campaign"):
    return {"ad_id": i, "ad_name": name, "effective_status": "ADSET_PAUSED",
            "campaign": {"id": "c1", "name": camp, "objective": obj},
            "adset": {"id": "s1", "name": "New Traffic Ad set", "start_time": "2026-09-10T09:18:48+0200"},
            "creative": {"media_type": media, "body": body, "title": None},
            "destination": {"status": "RESOLVED", "url": "https://swingshack.co.za/"},
            "current": {"spend": 100, "link_clicks": 10, "landing_page_views": 8}}


# ── naming rule ──────────────────────────────────────────────────────────────────────────────
def test_the_standard_names_and_tags():
    p = an.proposed(_ad(), "swing-shack", TODAY)
    assert p["campaign_name"] == "ss_traffic_fitting_sep26"      # started in September
    assert p["adset_name"] == "ss_traffic_fitting_sep26_set"
    assert p["ad_name"] == "fitting_video_v1"
    assert p["url_tags"] == ("utm_source=meta&utm_medium=paid_social&utm_campaign=ss_traffic_fitting_sep26"
                             "&utm_content=fitting_video_v1&utm_id=555")


def test_subject_objective_and_format_come_from_the_ad():
    lead = an.proposed(_ad(obj="OUTCOME_LEADS", media="image", body="Book a coaching lesson", name="x"), "stick", TODAY)
    assert lead["campaign_name"].startswith("stick_leads_coaching_") and lead["ad_name"] == "coaching_image_v1"
    assert an.proposed(_ad(body="hello", name="x", camp="x"), "stick", TODAY)["ad_name"] == "general_video_v1"


def test_names_and_tags_are_validated():
    assert an.valid_name("  fitting   video v1 ") == "fitting video v1"
    for bad in ("", "x" * 101, "a\x00b"):
        with pytest.raises(ValueError):
            an.valid_name(bad)
    assert an.valid_tags("?utm_source=meta&utm_medium=paid_social&utm_campaign=c") .startswith("utm_source")
    for bad in ("https://x.co/?utm_source=a", "utm_source=meta", "utm_source=meta&utm_medium=m&utm_campaign=has space", ""):
        with pytest.raises(ValueError):
            an.valid_tags(bad)


def test_tracking_rows_carry_ids_current_names_and_a_proposal_even_when_paused():
    out = at.build("swing-shack", [_ad("1"), _ad("2")], {}, [], today=TODAY)
    assert [r["ad_id"] for r in out["ads"]] == ["1", "2"]          # paused by the guard, still listed
    r = out["ads"][0]
    assert r["ids"] == {"campaign": "c1", "adset": "s1"} and r["names"]["ad"].startswith("New Traffic")
    assert [x["proposal"]["ad_name"] for x in out["ads"]] == ["fitting_video_v1", "fitting_video_v2"]


# ── fakes ──────────────────────────────────────────────────────────────────────────────────────
class Store:
    def __init__(self):
        self.data = {}

    def read(self, rel):
        return self.data.get(rel)

    def write(self, rel, obj):
        self.data[rel] = obj
        return True


class FakeMeta:
    def __init__(self, account="111", creative=None):
        self.objs = {"555": {"id": "555", "name": "Old ad", "account_id": account},
                     "777": {"id": "777", "name": "Old set", "account_id": account},
                     "999": {"id": "999", "name": "Old campaign", "account_id": account}}
        self.creative = creative or {"id": "c-old", "name": "old", "url_tags": "", "object_story_id": "111_222"}
        self.posts = []

    def __call__(self, method, path, token, params=None):
        if method == "GET":
            if path == "555" and "creative" in (params or {}).get("fields", ""):
                return dict(self.objs["555"], creative=dict(self.creative))
            return dict(self.objs[path])
        self.posts.append((path, dict(params)))
        if path.endswith("/adcreatives"):
            self.creative_made = params
            return {"id": "c-new"}
        if "name" in params:
            self.objs[path]["name"] = params["name"]
        if "creative" in params:
            self.creative = {"id": json.loads(params["creative"])["creative_id"], "url_tags": "applied",
                             "object_story_id": "111_222"}
        return {"success": True}


@pytest.fixture
def signer():
    return URLSafeTimedSerializer("s3cret", salt=aa.TICKET_SALT)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("ADS_WRITES_ENABLED", "1")


# ── rename ─────────────────────────────────────────────────────────────────────────────────────
def test_rename_previews_without_changing_and_refuses_bad_input(signer):
    meta = FakeMeta()
    p = aa.preview_rename("stick", "ad", "555", "fitting_video_v1", graph=meta, token="t", account_id=ACCT, signer=signer)
    assert (p["before"], p["after"], p["kind"]) == ("Old ad", "fitting_video_v1", "rename_ad") and meta.posts == []
    for kind, oid, name in (("nope", "555", "x"), ("ad", "555", "Old ad"), ("ad", "555", "")):
        with pytest.raises(aa.ActionRefused):
            aa.preview_rename("stick", kind, oid, name, graph=meta, token="t", account_id=ACCT, signer=signer)
    with pytest.raises(aa.ActionRefused):
        aa.preview_rename("stick", "ad", "555", "x", graph=FakeMeta(account="999"), token="t", account_id=ACCT, signer=signer)


def test_rename_apply_logs_and_undo_puts_the_old_name_back(signer, on):
    meta, store = FakeMeta(), Store()
    t = aa.preview_rename("stick", "adset", "777", "ss_set", graph=meta, token="t", account_id=ACCT, signer=signer)["ticket"]
    e = aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    assert meta.objs["777"]["name"] == "ss_set" and e["kind"] == "rename_adset"
    aa.undo("stick", e["id"], graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    assert meta.objs["777"]["name"] == "Old set"


def test_rename_refuses_when_changed_meanwhile_and_undo_refuses_when_changed_elsewhere(signer, on):
    meta, store = FakeMeta(), Store()
    t = aa.preview_rename("stick", "ad", "555", "new", graph=meta, token="t", account_id=ACCT, signer=signer)["ticket"]
    meta.objs["555"]["name"] = "someone else"
    with pytest.raises(aa.ActionRefused) as e1:
        aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    assert e1.value.status == 409
    meta.objs["555"]["name"] = "Old ad"
    t = aa.preview_rename("stick", "ad", "555", "new", graph=meta, token="t", account_id=ACCT, signer=signer)["ticket"]
    e = aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    meta.objs["555"]["name"] = "edited by hand"
    with pytest.raises(aa.ActionRefused) as e2:
        aa.undo("stick", e["id"], graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    assert e2.value.status == 409


def test_rename_is_off_by_default(signer, monkeypatch):
    monkeypatch.delenv("ADS_WRITES_ENABLED", raising=False)
    meta, store = FakeMeta(), Store()
    t = aa.preview_rename("stick", "ad", "555", "new", graph=meta, token="t", account_id=ACCT, signer=signer)["ticket"]
    with pytest.raises(aa.ActionRefused) as e:
        aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    assert e.value.status == 403 and meta.posts == []


# ── tags ───────────────────────────────────────────────────────────────────────────────────────
TAGS = "utm_source=meta&utm_medium=paid_social&utm_campaign=ss_traffic_fitting_oct26&utm_content=fitting_video_v1&utm_id=555"


def test_tags_preview_warns_and_changes_nothing(signer):
    meta = FakeMeta()
    p = aa.preview_tags("stick", "555", TAGS, graph=meta, token="t", account_id=ACCT, signer=signer)
    assert p["after"] == TAGS and "review" in p["warning"] and meta.posts == []


def test_tags_refuse_bad_tags_dynamic_creative_and_nothing_to_copy(signer):
    with pytest.raises(aa.ActionRefused):
        aa.preview_tags("stick", "555", "https://x.co/?utm_source=a", graph=FakeMeta(), token="t", account_id=ACCT, signer=signer)
    with pytest.raises(aa.ActionRefused):
        aa.preview_tags("stick", "555", TAGS, graph=FakeMeta(creative={"id": "c", "asset_feed_spec": {"x": 1}}),
                        token="t", account_id=ACCT, signer=signer)
    with pytest.raises(aa.ActionRefused):
        aa.preview_tags("stick", "555", TAGS, graph=FakeMeta(creative={"id": "c"}), token="t", account_id=ACCT, signer=signer)
    with pytest.raises(aa.ActionRefused):
        aa.preview_tags("stick", "555", TAGS, graph=FakeMeta(creative={"id": "c", "object_story_id": "1_2", "url_tags": TAGS}),
                        token="t", account_id=ACCT, signer=signer)


def test_tags_apply_copies_the_creative_with_tags_points_the_ad_at_it_and_undo_swaps_back(signer, on):
    meta, store = FakeMeta(), Store()
    t = aa.preview_tags("stick", "555", TAGS, graph=meta, token="t", account_id=ACCT, signer=signer)["ticket"]
    e = aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    made_path, made = meta.posts[0]
    assert made_path == "act_111/adcreatives" and made["url_tags"] == TAGS and made["object_story_id"] == "111_222"
    assert meta.posts[1] == ("555", {"creative": json.dumps({"creative_id": "c-new"})})
    assert (e["kind"], e["creative_before"], e["creative_after"]) == ("set_url_tags", "c-old", "c-new")
    aa.undo("stick", e["id"], graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    assert meta.posts[-1] == ("555", {"creative": json.dumps({"creative_id": "c-old"})})


def test_tags_copy_a_story_spec_creative_and_refuse_if_the_creative_changed(signer, on):
    spec = {"page_id": "9", "link_data": {"link": "https://x.co/", "message": "hi"}}
    meta, store = FakeMeta(creative={"id": "c-old", "url_tags": "", "object_story_spec": spec}), Store()
    t = aa.preview_tags("stick", "555", TAGS, graph=meta, token="t", account_id=ACCT, signer=signer)["ticket"]
    meta.creative["id"] = "someone-changed-it"
    with pytest.raises(aa.ActionRefused) as e:
        aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    assert e.value.status == 409 and meta.posts == []
    meta.creative["id"] = "c-old"
    aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    assert json.loads(meta.posts[0][1]["object_story_spec"]) == spec
