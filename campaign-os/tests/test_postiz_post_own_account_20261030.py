"""A Postiz post is labelled with its own account, not the one it was listed under (2026-10-30).

Postiz's /posts answers every post for the brand whatever integrationId is asked for, so
on prod five Stick Google posts and one Instagram post were saved as TikToks.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import outside_posts_sync as ops  # noqa: E402


def post(pid, provider, when="2026-10-29T08:00:00.000Z"):
    return {"id": pid, "state": "PUBLISHED", "publishDate": when, "content": "<p>Psycho Bunny</p>",
            "integration": {"id": f"int-{provider}", "providerIdentifier": provider}}


def test_the_posts_own_account_wins_over_the_one_it_was_listed_under():
    row = {**post("pz-1", "gmb"), "_postiz_provider": "tiktok-business"}
    assert ops._observed_from_postiz(row).target == "gbp"
    row = {**post("pz-2", "instagram-standalone"), "_postiz_provider": "tiktok-business"}
    assert ops._observed_from_postiz(row).target == "instagram"


def test_a_post_with_no_account_of_its_own_uses_the_listing():
    row = {"id": "pz-3", "publishDate": "2026-10-29T08:00:00Z", "_postiz_provider": "tiktok-business"}
    assert ops._observed_from_postiz(row).target == "tiktok"


def test_postiz_answering_every_post_for_each_account_labels_each_post_once_and_right():
    everything = [post("pz-g", "gmb"), post("pz-i", "instagram-standalone"), post("pz-t", "tiktok-business")]
    accounts = [{"id": "int-tiktok-business", "providerIdentifier": "tiktok-business"},
                {"id": "int-gmb", "providerIdentifier": "gmb"},
                {"id": "int-instagram-standalone", "providerIdentifier": "instagram-standalone"}]
    from _lib import postiz_client as pz

    with mock.patch.object(pz, "list_integrations", return_value=(accounts, None)), \
            mock.patch.object(pz, "list_posts", return_value=(everything, None)), \
            mock.patch.object(ops, "_ig_media_rows", return_value=[]), \
            mock.patch.object(ops, "_ig_story_rows", return_value=[]), \
            mock.patch.object(ops, "_fb_post_rows", return_value=[]), \
            mock.patch.object(ops, "_fb_story_rows", return_value=[]):
        observed = ops.fetch_observed_posts("stick", now=dt.datetime(2026, 10, 30, 10, tzinfo=dt.timezone.utc))
    got = sorted((o.external_id, o.target) for o in observed if o.platform == "postiz")
    assert got == [("pz-g", "gbp"), ("pz-i", "instagram"), ("pz-t", "tiktok")]
