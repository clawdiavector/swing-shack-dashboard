"""Layer 1 hooks job — ports analyse_hooks.js + extract_youtube_signals.js."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ._io import (
    as_dict,
    empty_hook_bank,
    empty_youtube_hook_signals,
    io_for_job,
    parse_float,
    parse_int,
    slug_id,
    utc_now_iso,
)

JOB_NAME = "insights_hooks"

TOPIC_KEYWORDS = {
    "driver": ["driver", "drive", "driving", "tee", "off the tee"],
    "slice_fix": ["slice", "hook", "ball flight", "aim", "club path", "straight"],
    "senior": ["senior", "older", "50+", "aging"],
    "beginner": ["beginner", "new to", "start", "basics", "first time", "learn"],
    "irons": ["iron", "irons", "fairway", "approach shot"],
    "short_game": ["chip", "pitch", "putt", "putting", "green", "bunker"],
    "simulator": ["simulator", "indoor", "launch monitor", "trackman", "rain"],
    "lessons": ["lesson", "pro", "coach", "professional", "instruction", "golf pro"],
    "swing": ["swing", "swinging", "swing speed", "club head"],
    "fitness": ["fitness", "flexibility", "mobility", "core", "strength"],
    "distance": ["distance", "further", "yards", "meters", "longer", "gain"],
    "consistency": ["consistent", "consistently", "repeat"],
}

YT_TOPIC_PATTERNS = {
    "driver": ["driver", "drive", "driving", "tee shot"],
    "slice_fix": ["slice", "hook", "ball flight", "aim", "club path"],
    "senior": ["senior", "older", "50+"],
    "beginner": ["beginner", "new to golf", "start", "basics", "first time"],
    "irons": ["iron", "irons", "fairway", "approach"],
    "short_game": ["chip", "pitch", "putt", "putting", "around the green", "bunker"],
    "simulator": ["simulator", "indoor", "launch monitor", "trackman"],
    "lessons": ["lesson", "pro", "coach", "professional", "instruction", "tips from"],
    "swing": ["swing", "swinging", "swing speed"],
    "fitness": ["fitness", "flexibility", "mobility", "core", "strength"],
    "distance": ["distance", "further", "yards", "meters", "longer"],
    "consistency": ["consistent", "consistently", "repeatable", "repeat"],
}

FORMAT_MAP = {
    "how to...": ["how to"],
    '"best" superlative': ["best"],
    '"easy" simplicity': ["easy"],
    '"simple" promise': ["simple"],
    "question hook": ["?"],
    '"stop" command': ["stop"],
    "mistake framing": ["mistake"],
    "contrast hook": ["?"],
    '"honest" credibility': ["honest"],
    "experience claim": ["years"],
    "guarantee language": ["guarantee"],
}

EVIDENCE_TOPIC_KW = {
    "driver": ["driver", "drive"],
    "slice_fix": ["slice", "hook"],
    "senior": ["senior"],
    "beginner": ["beginner", "learn"],
    "simulator": ["simulator", "indoor"],
    "lessons": ["lesson", "pro", "coach"],
}


def _tokenize(text: str | None) -> list[str]:
    if not text:
        return []
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return [w for w in cleaned.split() if len(w) > 2]


def _bigrams(words: list[str]) -> list[str]:
    return [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]


def extract_youtube_signals(videos: list[dict]) -> dict | None:
    if not videos:
        return None

    titles = [v.get("title") or "" for v in videos]
    title_text = " ".join(titles)
    all_text = " ".join(
        f"{v.get('title') or ''} {v.get('description') or ''}" for v in videos
    )

    title_bigrams: list[str] = []
    for title in titles:
        title_bigrams.extend(_bigrams(_tokenize(title)))
    bg_counts = Counter(title_bigrams)
    recurring_phrases = [
        {
            "phrase": phrase,
            "count": count,
            "examples": [t for t in titles if phrase in t.lower()][:2],
        }
        for phrase, count in bg_counts.most_common()
        if count >= 2
    ][:20]

    topic_matches: dict[str, int] = {}
    lower_title_text = title_text.lower()
    for topic, patterns in YT_TOPIC_PATTERNS.items():
        if any(p in lower_title_text for p in patterns):
            topic_matches[topic] = sum(
                1
                for v in videos
                if any(
                    p in f"{v.get('title') or ''}{v.get('description') or ''}".lower()
                    for p in patterns
                )
            )

    format_patterns_def = [
        (re.compile(r"how to\s", re.I), "How to...", "How to hit driver"),
        (re.compile(r"\d+\s+(steps?|tips?|secrets?|mistakes?|signs?)", re.I), "Numbered list", "5 Tips to fix your slice"),
        (re.compile(r"best\s", re.I), '"Best" superlative', "Best driver tip ever"),
        (re.compile(r"easy\s", re.I), '"Easy" simplicity', "Easy steps for better golf"),
        (re.compile(r"simple\s", re.I), '"Simple" promise', "Simple golf swing"),
        (re.compile(r"(\?|how do|what if|should i)", re.I), "Question hook", "How do pro players..."),
        (re.compile(r"stop\s", re.I), '"Stop" command', "Stop slicing"),
        (re.compile(r"mistake", re.I), "Mistake framing", "Biggest mistake amateur golfers make"),
        (re.compile(r"(\?|—|--)", re.I), "Contrast hook", "Struggling with X? Here's the fix"),
        (re.compile(r"honest\s", re.I), '"Honest" credibility', "My honest review after 5 years"),
        (re.compile(r"years?\s", re.I), "Experience claim", "After 5 years of practice"),
        (re.compile(r"guarantee", re.I), "Guarantee language", "We guarantee you'll improve"),
    ]
    format_matches = []
    for pattern, label, example in format_patterns_def:
        if pattern.search(title_text):
            matched_example = next((t for t in titles if pattern.search(t)), example)
            format_matches.append({"label": label, "example": matched_example})

    urgency_patterns = [
        ("stop", 3),
        ("how to", 2),
        ("learn", 2),
        ("fix", 3),
        ("secret", 2),
        ("mistake", 3),
        ("right now", 3),
        ("today", 2),
        ("finally", 2),
        ("prove", 2),
    ]
    lower_titles = title_text.lower()
    urgency_score = 0
    for word, strength in urgency_patterns:
        urgency_score += len(re.findall(re.escape(word), lower_titles)) * strength
    urgency_language = [word for word, _ in urgency_patterns if word in lower_titles]

    before_after_pattern = re.compile(
        r"struggling|want to|hitting|failing|can't|problem|issue", re.I
    )
    has_before_after = bool(before_after_pattern.search(title_text))
    before_after_examples = (
        [t for t in titles if before_after_pattern.search(t)][:3]
        if has_before_after
        else []
    )

    mistake_fix_pattern = re.compile(
        r"mistake|fix|solution|wrong|error|instead|actually|here's what", re.I
    )
    has_mistake_fix = bool(mistake_fix_pattern.search(title_text))
    mistake_fix_examples = (
        [t for t in titles if mistake_fix_pattern.search(t)][:3]
        if has_mistake_fix
        else []
    )

    channels: Counter[str] = Counter()
    for video in videos:
        channel = video.get("channelTitle") or ""
        if channel:
            channels[channel] += 1
    top_channels = channels.most_common(5)

    templates = [
        {
            "template": "How to [skill] — [specific benefit]",
            "source": "how-to-format",
            "count": sum(1 for t in titles if re.search(r"how to\s", t, re.I)),
        },
        {
            "template": "[Number] Tips for [outcome]",
            "source": "numbered-list",
            "count": sum(1 for t in titles if re.search(r"\d+\s+(tips?|steps?)", t, re.I)),
        },
        {
            "template": "The Truth About [common_mistake]",
            "source": "mistake-reveal",
            "count": sum(1 for t in titles if re.search(r"mistake|truth|secret", t, re.I)),
        },
        {
            "template": "[Problem]? Here's the Fix",
            "source": "problem-fix",
            "count": sum(1 for t in titles if re.search(r"\?|here's the", t, re.I)),
        },
        {
            "template": "[Player Type]: [advice]",
            "source": "player-specific",
            "count": sum(1 for t in titles if re.search(r"senior|beginner|amateur", t, re.I)),
        },
    ]
    hook_templates = [t for t in templates if t["count"] > 0]

    dominant_topics = [
        topic
        for topic, _ in sorted(topic_matches.items(), key=lambda item: item[1], reverse=True)[:3]
    ]
    top_template = None
    if hook_templates:
        top_template = sorted(hook_templates, key=lambda item: item["count"], reverse=True)[0]["template"]

    return {
        "fetched_at": utc_now_iso(),
        "source_file": "youtube-trends.json",
        "videos_analyzed": len(videos),
        "top_videos": videos[:10],
        "signals": {
            "recurring_phrases": recurring_phrases,
            "topic_clusters": topic_matches,
            "format_patterns": format_matches,
            "urgency_score": urgency_score,
            "urgency_language": urgency_language,
            "has_before_after": has_before_after,
            "before_after_examples": before_after_examples,
            "has_mistake_fix": has_mistake_fix,
            "mistake_fix_examples": mistake_fix_examples,
            "top_channels": [[name, count] for name, count in top_channels],
            "hook_templates": hook_templates,
        },
        "summary": {
            "dominant_topics": dominant_topics,
            "dominant_formats": [f["label"] for f in format_matches],
            "top_template": top_template,
        },
    }


def _ig_score(post: dict) -> float:
    eng = parse_float(post.get("engagementRate"))
    saves = parse_float(post.get("saveRate"))
    shares = parse_float(post.get("shareRate"))
    reach = parse_int(post.get("reach"))
    raw = (eng * 2) + (saves * 3) + (shares * 5) + min(reach / 100, 3)
    return min(10.0, max(0.0, raw))


def _extract_formula(hook_text: str) -> str:
    if not hook_text:
        return "unknown"
    if re.search(r"YOUR|THIS IS|THE\s+\w+:\s*\d", hook_text, re.I):
        return "stat-demand"
    if re.search(r"\?|WHAT IF", hook_text, re.I):
        return "question"
    if re.search(r"slice|hook|problem|fix|wrong|issue", hook_text, re.I):
        return "pain-point"
    if re.search(r"pros average|trackman shows|benchmark", hook_text, re.I):
        return "proof-led"
    if re.search(r"from r\d", hook_text, re.I):
        return "price-led"
    if re.search(r"stop\s|don't\s", hook_text, re.I):
        return "command"
    if re.search(r"secret|truth|mistake", hook_text, re.I):
        return "reveal"
    return "general"


def _youtube_alignment_score(hook_text: str, yt_signals: dict | None) -> dict[str, Any]:
    if not yt_signals or not as_dict(yt_signals.get("signals")):
        return {
            "score": 0,
            "matched_topics": [],
            "matched_formats": [],
            "phrase_matches": [],
            "evidence_titles": [],
        }

    signals = as_dict(yt_signals.get("signals"))
    text = (hook_text or "").lower()
    format_patterns = signals.get("format_patterns") or []
    format_labels = [str(f.get("label", "")).lower() for f in format_patterns if isinstance(f, dict)]

    matched_topics: list[str] = []
    topic_score = 0
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched_topics.append(topic)
            topic_score += 3

    matched_formats: list[str] = []
    format_score = 0
    for label, triggers in FORMAT_MAP.items():
        if label.lower() in format_labels and any(t in text for t in triggers):
            matched_formats.append(label)
            format_score += 2

    phrase_score = 0
    matched_phrases: list[str] = []
    for item in (signals.get("recurring_phrases") or [])[:10]:
        if not isinstance(item, dict):
            continue
        phrase = str(item.get("phrase") or "")
        if len(phrase) > 4 and phrase[:15] in text:
            matched_phrases.append(phrase)
            phrase_score += 1

    raw = topic_score + format_score + phrase_score
    return {
        "score": min(10, raw),
        "matched_topics": matched_topics,
        "matched_formats": matched_formats,
        "phrase_matches": matched_phrases,
        "evidence_titles": [],
    }


def _reddit_score(hook_text: str, reddit: dict | None) -> int:
    if not reddit or not hook_text:
        return 0
    trends = reddit.get("trends") or reddit.get("hot_pain_points") or []
    if not isinstance(trends, list) or not trends:
        return 0

    text = hook_text.lower()
    hits = 0
    for trend in trends:
        if not isinstance(trend, dict):
            continue
        ttext = " ".join(
            str(trend.get(key) or "")
            for key in ("title", "topic", "description")
        ).lower()
        words = [w for w in ttext.split() if len(w) > 3]
        match_count = sum(1 for w in words if w in text)
        if match_count >= 2:
            hits += 1
    return min(5, hits * 2)


def _cross_signal_score(ig: float, reddit: float, yt: float) -> float | int:
    """Match JS Math.round(raw*100)/10 — whole numbers become ints via js_number()."""
    ig_norm = ig / 10
    yt_norm = yt / 10
    rd_norm = min(reddit / 5, 1)
    raw = (ig_norm * 0.6) + (rd_norm * 0.2) + (yt_norm * 0.2)
    return min(10, round(raw * 10 * 10) / 10)


def _classify_bucket(ig: float, yt_score: float, _cross: float) -> str:
    proven_ig = ig >= 4
    strong_yt = yt_score >= 4
    test_ig = 2 <= ig < 4

    if proven_ig and strong_yt:
        return "proven_and_trending"
    if proven_ig:
        return "proven_only"
    if test_ig and strong_yt:
        return "trending_to_test"
    if ig < 2 and yt_score >= 4:
        return "trending_to_test"
    if ig == 0 and yt_score > 0:
        return "trending_to_test"
    if proven_ig and yt_score < 2:
        return "proven_only"
    if ig < 2 and yt_score < 2:
        return "retire"
    return "proven_only"


def _analyse_hooks(
    ig: dict | None,
    ab: dict | None,
    yt_signals: dict | None,
    reddit: dict | None,
) -> dict:
    ig_data = as_dict(ig)
    posts = ig_data.get("posts") or []
    if not isinstance(posts, list):
        posts = []

    yt_videos = parse_int((yt_signals or {}).get("videos_analyzed"))

    scored: list[dict] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        hook_text = post.get("hook_text") or post.get("captionPreview") or ""
        ig_val = _ig_score(post)
        yt = _youtube_alignment_score(hook_text, yt_signals)
        rd = _reddit_score(hook_text, reddit)
        cross = _cross_signal_score(ig_val, rd, yt["score"])
        bucket = _classify_bucket(ig_val, yt["score"], cross)

        evidence_titles: list[str] = []
        if yt_signals and yt["matched_topics"]:
            for video in (yt_signals.get("top_videos") or [])[:10]:
                if not isinstance(video, dict):
                    continue
                vtext = f"{video.get('title') or ''} {video.get('description') or ''}".lower()
                has_topic = False
                for topic in yt["matched_topics"]:
                    topic_kw = EVIDENCE_TOPIC_KW.get(topic, [topic])
                    if any(k in vtext for k in topic_kw):
                        has_topic = True
                        break
                if has_topic and len(evidence_titles) < 2:
                    title = video.get("title")
                    if title:
                        evidence_titles.append(title)

        scored.append(
            {
                "hook_text": hook_text,
                "hook_id": post.get("hook_id")
                or slug_id(hook_text),
                "ig_proof_score": ig_val,
                "youtube_alignment_score": yt["score"],
                "reddit_relevance_score": rd,
                "cross_signal_score": cross,
                "youtube_topic_match": yt["matched_topics"],
                "youtube_format_match": yt["matched_formats"],
                "youtube_evidence_titles": evidence_titles,
                "engagementRate": post.get("engagementRate") or "0",
                "saveRate": post.get("saveRate") or "0",
                "shareRate": post.get("shareRate") or "0",
                "reach": post.get("reach") or 0,
                "topic_cluster": post.get("topic_cluster") or "general",
                "format_type": post.get("format_type") or "static",
                "formula_type": _extract_formula(hook_text),
                "signal_bucket": bucket,
                "post_id": post.get("postId") or post.get("id"),
            }
        )

    scored.sort(key=lambda item: item["cross_signal_score"], reverse=True)

    proven_and_trending = [h for h in scored if h["signal_bucket"] == "proven_and_trending"]
    proven_only = [h for h in scored if h["signal_bucket"] == "proven_only"]
    trending_to_test = [h for h in scored if h["signal_bucket"] == "trending_to_test"]
    retire = [h for h in scored if h["signal_bucket"] == "retire"]

    formula_buckets: dict[str, list[dict]] = {}
    for hook in scored:
        formula_buckets.setdefault(hook["formula_type"], []).append(hook)

    hook_formulas = []
    for formula, hooks in formula_buckets.items():
        best = sorted(hooks, key=lambda item: item["cross_signal_score"], reverse=True)
        hook_formulas.append(
            {
                "formula": formula,
                "count": len(hooks),
                "best_example": best[0]["hook_text"] if best else "",
                "avg_cross_score": f"{sum(h['cross_signal_score'] for h in hooks) / len(hooks):.1f}",
            }
        )

    reddit_data = as_dict(reddit)
    reddit_trends = reddit_data.get("trends") or reddit_data.get("hot_pain_points") or []
    reddit_count = len(reddit_trends) if isinstance(reddit_trends, list) else 0

    ab_data = as_dict(ab)
    ab_winners = [
        {
            "winner": t.get("winner"),
            "eng": t.get("engagement") or t.get("engagementRate") or "?",
            "next_action": t.get("next_action") or "reuse formula",
        }
        for t in (ab_data.get("tests") or [])
        if isinstance(t, dict) and t.get("winner")
    ]

    return {
        "updated": utc_now_iso(),
        "total_hooks": len(scored),
        "cross_signal_sources": {
            "ig_weight": "60%",
            "youtube_weight": "20%",
            "reddit_weight": "20%",
            "youtube_videos_analyzed": yt_videos,
            "reddit_trends_available": reddit_count,
        },
        "output_buckets": {
            "proven_and_trending": proven_and_trending[:10],
            "proven_only": proven_only[:10],
            "trending_to_test": trending_to_test[:10],
            "retire": retire[:5],
        },
        "watched_and_worked": proven_and_trending[:5],
        "hook_formulas": hook_formulas,
        "ab_winners": ab_winners,
        "youtube_signals_summary": (
            {
                "dominant_topics": (yt_signals.get("summary") or {}).get("dominant_topics") or [],
                "dominant_formats": (yt_signals.get("summary") or {}).get("dominant_formats") or [],
                "top_template": (yt_signals.get("summary") or {}).get("top_template"),
            }
            if yt_signals
            else None
        ),
    }


def run(*, brand: str | None = None) -> dict:
    io = io_for_job(JOB_NAME, brand)
    """Match legacy insight_analyst order: analyse_hooks then extract_youtube_signals.

    analyse_hooks.js reads the *prior* youtube-hook-signals.json; extract then
    refreshes that file from youtube-trends.json. Extract-first would change
    hook-bank cross-signal scores vs the JS baseline (Class A fail).
    """
    try:
        io.read("golf-news.json")
        io.read("hook-bank.json")

        # Prior signals (may be missing on first run) — same as analyse_hooks.js
        prior_signals = io.read("youtube-hook-signals.json")
        if not isinstance(prior_signals, dict):
            prior_signals = None

        hook_bank = _analyse_hooks(
            io.read("ig-analytics.json"),
            io.read("ab-tests.json"),
            prior_signals,
            io.read("reddit-trends.json"),
        )

        yt_trends = as_dict(io.read("youtube-trends.json"))
        videos = yt_trends.get("top_videos") or []
        if not isinstance(videos, list):
            videos = []

        if videos:
            yt_signals = extract_youtube_signals(videos) or empty_youtube_hook_signals()
        else:
            # JS extract_youtube_signals exits 1 with no write; we still emit a
            # schema-valid empty file so the job contract stays stable.
            yt_signals = empty_youtube_hook_signals()

        if hook_bank["total_hooks"] == 0 and not videos and not prior_signals:
            hook_bank = empty_hook_bank()
            hook_bank["updated"] = utc_now_iso()

        io.write("hook-bank.json", hook_bank)
        io.write("youtube-hook-signals.json", yt_signals)

        signal_rows = len((yt_signals.get("signals") or {}).get("recurring_phrases") or [])
        rows = hook_bank["total_hooks"] + signal_rows
        return {"ok": True, "rows": rows}
    except Exception:
        empty_signals = empty_youtube_hook_signals()
        empty_bank = empty_hook_bank()
        io.write("youtube-hook-signals.json", empty_signals)
        io.write("hook-bank.json", empty_bank)
        return {"ok": False, "rows": 0}
