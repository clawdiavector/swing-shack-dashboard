"""Resume a paused campaign from the dashboard, logged, with a way back (pause it again).

The lead campaign of a brand can be paused on its own, so resuming its ad set alone does nothing."""
import pytest

from _lib import ads_actions as aa

ACCT = "act_1"


class Meta:
    def __init__(self, status="PAUSED", account="1", name="stick_leads_fitting_may26"):
        self.camp = {"id": "555", "name": name, "status": status, "account_id": account}
        self.posts = []

    def __call__(self, method, path, token, params=None):
        if method == "GET":
            return dict(self.camp)
        self.posts.append((path, params))
        self.camp["status"] = params["status"]
        return {"success": True}


class Store:
    def __init__(self):
        self.data = {}

    def read(self, rel):
        return self.data.get(rel)

    def write(self, rel, obj):
        self.data[rel] = obj


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("ADS_WRITES_ENABLED", "1")


def _resume(meta, store, brand="stick"):
    return aa.resume_campaign(brand, "555", graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)


def test_resumes_a_paused_campaign_and_logs_it():
    meta, store = Meta(), Store()
    e = _resume(meta, store)
    assert meta.posts == [("555", {"status": "ACTIVE"})]
    assert e["kind"] == "resume_campaign" and e["ad_id"] == "555" and e["before"] == "PAUSED" and e["after"] == "ACTIVE"
    assert aa.load_log("stick", store.read)[-1]["id"] == e["id"]


def test_undo_pauses_it_again():
    meta, store = Meta(), Store()
    e = _resume(meta, store)
    out = aa.undo("stick", e["id"], graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    assert meta.camp["status"] == "PAUSED" and out["undone_at"]


def test_refuses_when_writes_are_off(monkeypatch):
    monkeypatch.setenv("ADS_WRITES_ENABLED", "0")
    with pytest.raises(aa.ActionRefused):
        _resume(Meta(), Store())


def test_refuses_another_brands_campaign():
    with pytest.raises(aa.ActionRefused) as e:
        _resume(Meta(account="2"), Store())
    assert e.value.status == 403


def test_refuses_a_campaign_that_is_not_paused():
    meta = Meta(status="ACTIVE")
    with pytest.raises(aa.ActionRefused) as e:
        _resume(meta, Store())
    assert e.value.status == 409 and meta.posts == []


def test_undo_refuses_when_someone_else_changed_it():
    meta, store = Meta(), Store()
    e = _resume(meta, store)
    meta.camp["status"] = "ARCHIVED"
    with pytest.raises(aa.ActionRefused):
        aa.undo("stick", e["id"], graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
