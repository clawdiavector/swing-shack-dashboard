"""T9 verifier follow-ups C1, C4, C5 (2026-10-28)."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import outside_posts_sync as ops  # noqa: E402


def _empty_index():
    return ops.MatchIndex(postiz_ids=set(), media_ids=set(), timed_captions=[])


def test_c1_postiz_readback_matches_meta_post_by_link():
    index = _empty_index()
    postiz = ops.ObservedPost(platform="postiz", kind="feed", external_id="pz-9",
                              published_at="2026-10-27T07:00:00Z", caption="Different text",
                              permalink="https://www.instagram.com/p/ABC123/", thumbnail_url="",
                              postiz_post_id="pz-9")
    ops.add_postiz_observations(index, [postiz])
    meta = ops.ObservedPost(platform="instagram", kind="feed", external_id="ig-1",
                            published_at="2026-10-27T12:00:00Z", caption="Unrelated",
                            permalink="https://www.instagram.com/p/ABC123?igsh=x", thumbnail_url="")
    assert ops.matches_campaign_os(meta, index)


def test_c1_postiz_readback_matches_by_caption_and_time():
    index = _empty_index()
    ops.add_postiz_observations(index, [ops.ObservedPost(
        platform="postiz", kind="feed", external_id="pz-1", published_at="2026-10-27T07:00:00Z",
        caption="New Odyssey putters in store!", permalink="", thumbnail_url="", postiz_post_id="pz-1")])
    meta = ops.ObservedPost(platform="instagram", kind="feed", external_id="ig-2",
                            published_at="2026-10-27T07:10:00Z", caption="New Odyssey putters in store",
                            permalink="", thumbnail_url="")
    assert ops.matches_campaign_os(meta, index)
    other = ops.ObservedPost(platform="instagram", kind="feed", external_id="ig-3",
                             published_at="2026-10-27T07:10:00Z", caption="Something else",
                             permalink="", thumbnail_url="")
    assert not ops.matches_campaign_os(other, index)


def test_c4_facebook_stories_are_observed():
    now = dt.datetime(2026, 10, 28, 8, 0, tzinfo=dt.timezone.utc)
    stories = [
        {"post_id": "fbs-1", "status": "PUBLISHED", "creation_time": "2026-10-27T09:00:00+0000",
         "media_type": "photo", "url": "https://www.facebook.com/stories/1"},
        {"post_id": "fbs-2", "status": "ARCHIVED", "creation_time": "2026-10-27T09:00:00+0000"},
    ]
    with mock.patch.object(ops, "_ig_media_rows", return_value=[]), \
         mock.patch.object(ops, "_ig_story_rows", return_value=[]), \
         mock.patch.object(ops, "_fb_post_rows", return_value=[]), \
         mock.patch.object(ops, "_fb_story_rows", return_value=stories), \
         mock.patch.object(ops, "_postiz_rows", return_value=[]):
        observed = ops.fetch_observed_posts("swing-shack", now=now)
    assert [(o.platform, o.kind, o.external_id) for o in observed] == [("facebook", "story", "fbs-1")]


def test_c5_token_goes_in_header_not_url():
    seen = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"data": [{"id": "1"}]}).encode()

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return _Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        rows = ops._fb_get("123", "posts", "id,message", "SECRET-TOKEN")
    assert rows == [{"id": "1"}]
    assert "SECRET-TOKEN" not in seen["url"]
    assert seen["auth"] == "Bearer SECRET-TOKEN"
