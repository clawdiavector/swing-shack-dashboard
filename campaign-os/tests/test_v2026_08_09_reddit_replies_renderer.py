"""
Regression test for the Reddit Outreach Replies renderer fix.

Bug (caught by the 2026-08-09 nightshift walk):
The `renderReddit()` Replies card on the Reddit Outreach tab dumped raw JSON
syntax into the DOM for every reply row. The renderer only looked at
`it.text || it.reply || it.title || JSON.stringify(it).slice(0,80)`, and
the actual API payload uses `reply_draft` (body) + `angle` (hook) +
`sentiment` (high_trust / medium_trust / low_trust) + a 4-key
`safety_check` object. None of those matched the fallback chain so every
row fell through to `JSON.stringify(...)`. Result on the live URL: the
Replies card showed a string of nested `{"angle":...{"angle":...` braces
instead of the actual drafted Reddit replies.

Fix: rewrite the inner renderer to surface `angle` as the title,
`reply_draft` as the 2-line preview, and render the sentiment + safety
flags as colour-coded pills so the brand can pick which threads are safe
to post to at a glance. Same `.li / .li-title / .li-preview / .li-meta`
structure every other list in the app uses.

This is a read-only regression test — it loads campaign-os.html as text
and asserts structural markers.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML = REPO / "campaign-os" / "campaign-os.html"


def _read() -> str:
    assert HTML.exists(), f"campaign-os.html missing at {HTML}"
    return HTML.read_text(encoding="utf-8")


def _renderReddit_body() -> str:
    """Extract everything belonging to the Reddit renderer block: the
    REDDIT_SENTIMENT_PILL constant + the renderReddit() function body.
    We slice from `REDDIT_SENTIMENT_PILL` (or `renderReddit()` if the
    constant is missing) up to the FAQ section header."""
    src = _read()
    # Anchor on the section divider above renderReddit (the REDDIT comment
    # block) and slice to the FAQ divider.
    m = re.search(
        r"// ─── REDDIT ──[\s\S]*?(?:const REDDIT_SENTIMENT_PILL|async function renderReddit)\b[\s\S]*?(?=\n// ─── FAQS)",
        src,
    )
    assert m, "Could not isolate the Reddit renderer block (REDDIT_SENTIMENT_PILL + renderReddit)"
    return m.group(0)


class RedditReplyRendererTests(unittest.TestCase):
    """Guard tests for the Reddit Outreach Replies renderer fix."""

    def test_no_json_stringify_leakage(self):
        """renderReddit() must NOT call JSON.stringify inside the per-row
        template anymore — that was the bug. Replies should fall back to
        a clean empty-state message instead."""
        body = _renderReddit_body()
        # Must not contain JSON.stringify in the Replies innerHTML.
        # (We allow it in other parts of the file, just not here.)
        # Match occurrences of JSON.stringify between 'reddit-replies'
        # and the closing `}` of the .map(...).join('') call.
        replies_section = re.search(
            r"#reddit-replies'\)\.innerHTML\s*=.*?\.join\(''\)\s*\|\|",
            body,
            re.DOTALL,
        )
        assert replies_section, "Could not isolate the #reddit-replies innerHTML block"
        block = replies_section.group(0)
        assert "JSON.stringify" not in block, (
            "renderReddit() Replies innerHTML must not call JSON.stringify — "
            "that was the bug. Use real fields (angle, reply_draft) with an "
            "empty-state fallback instead."
        )

    def test_angle_used_as_title(self):
        """renderReddit() must extract `rr.angle` (the hook) as the title."""
        body = _renderReddit_body()
        # We accept either `rr.angle` or `it.angle`; the fix uses `rr`.
        assert re.search(r"\b(rr|it)\.angle\b", body), (
            "renderReddit() must read `angle` (or `rr.angle`) from the reply "
            "object to surface the hook as the title. Without it, every "
            "reply falls through to a fallback and the card looks broken."
        )

    def test_reply_draft_used_as_preview(self):
        """renderReddit() must extract `rr.reply_draft` as the body / preview."""
        body = _renderReddit_body()
        assert "reply_draft" in body, (
            "renderReddit() must read `reply_draft` from the reply object. "
            "That's where the actual drafted Reddit reply lives."
        )

    def test_sentiment_pill_mapping(self):
        """renderReddit() must define a mapping from sentiment → pill class
        (high_trust / medium_trust / low_trust) so the brand can tell at
        a glance which threads are safe to post to."""
        body = _renderReddit_body()
        # Expect a REDDIT_SENTIMENT_PILL object literal with all 3 keys.
        assert "REDDIT_SENTIMENT_PILL" in body, (
            "renderReddit() must declare a sentiment→pill mapping constant."
        )
        for sentiment in ("high_trust", "medium_trust", "low_trust"):
            assert sentiment in body, (
                f"REDDIT_SENTIMENT_PILL must cover `{sentiment}` (the API "
                f"returns one of three sentiment tags and every one needs a "
                f"colour-coded pill)."
            )

    def test_safety_check_rendered(self):
        """renderReddit() must surface the safety_check flags (no_direct_link,
        native_tone, no_salesy_language, adds_value_first) so the brand sees
        the safety audit on every reply at a glance."""
        body = _renderReddit_body()
        for key in ("no_direct_link", "native_tone", "no_salesy_language", "adds_value_first"):
            assert key in body, (
                f"renderReddit() must read the safety_check field `{key}` "
                f"to surface it as a pill. Each is a distinct safety audit "
                f"the agent ran on the drafted reply."
            )

    def test_subreddit_and_upvotes_in_meta(self):
        """renderReddit() must surface the subreddit (e.g. r/golf) and
        upvote count for each reply so the brand can rank threads by
        traction."""
        body = _renderReddit_body()
        assert "subreddit" in body, "renderReddit() must read rr.subreddit for the meta row"
        assert "upvotes" in body, "renderReddit() must read rr.upvotes for the meta row"

    def test_pill_class_uses_existing_tokens(self):
        """renderReddit() must only reference existing .pill colour tokens
        (on / warn / blocked) so the new pills render correctly in dark +
        light themes without new CSS."""
        body = _renderReddit_body()
        # Greedy extract up to the first closing `};` after the assignment
        m = re.search(r"REDDIT_SENTIMENT_PILL\s*=\s*\{(.*?)\};", body, re.DOTALL)
        assert m, "REDDIT_SENTIMENT_PILL must be a literal object"
        literal = m.group(1)
        for token in ("on", "warn", "blocked"):
            assert re.search(rf":\s*['\"]{token}['\"]", literal), (
                f"REDDIT_SENTIMENT_PILL must use existing pill token `{token}`. "
                f"Adding a new pill colour would require new CSS."
            )

    def test_uses_li_li_title_li_preview_li_meta(self):
        """renderReddit() must use the standard `.li / .li-title /
        .li-preview / .li-meta` structure so it visually matches every
        other list in the app."""
        body = _renderReddit_body()
        for cls in ("li-title", "li-preview", "li-meta"):
            assert cls in body, (
                f"renderReddit() must use `{cls}` so the Replies card "
                f"matches every other list in Campaign OS."
            )

    def test_empty_state_message(self):
        """renderReddit() must still render an empty-state fallback when
        the API returns no replies."""
        body = _renderReddit_body()
        assert "No replies yet" in body, (
            "renderReddit() must keep the 'No replies yet' empty-state "
            "fallback when the API returns an empty replies array."
        )

    def test_no_em_dash_in_renderReddit(self):
        """Standing rule: no em-dash in shipped copy. The new renderReddit
        block must use pipes / commas / colons only."""
        body = _renderReddit_body()
        # Match literal em-dash (U+2014)
        assert "\u2014" not in body, (
            "renderReddit() must not contain an em-dash (U+2014). Use "
            "pipes / commas / colons. Standing rule for published copy."
        )


if __name__ == "__main__":
    unittest.main()