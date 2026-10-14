# Music intelligence — audit, capability matrix, plan

Branch `feat/music-intelligence`. Phase 2 (data foundation) is built; nothing else is.

## Audit (2026-10-14)
- No audio/music code exists in `campaign-os/_lib` (checked: audio, music, soundtrack, bpm).
- Storage convention is per-brand JSON under `data/brand-directory/<brand>/…`, not a database.
  So this extends that: `data/brand-directory/<brand>/music/*.json` (brand isolation by path).
- Real post data: `feedback/instagram-audit.json`. Stick has 130 reels; **none carries an audio
  id**, and reel insights are absent (the known `audit_social.py` reels bug).
- Reusable: `meta_api.py` (post insights), `social_history.py` (post store), `ads_history.py`
  (weekly paid numbers), job pattern in `_lib/jobs`.
- Swing Shack has no Instagram audit file yet, so it has zero reels to analyse.

## Source capability matrix
**Not verified against live docs this session.** Statuses below are conservative: anything not
confirmed from official documentation is `REQUIRES ACCESS` / `UNVERIFIED`. Confirm before building adapters.

| Source | Own post metrics | Audio identity of own posts | Trending audio | Status |
|---|---|---|---|---|
| Instagram Graph API | yes, account-authorised (`meta_api.py`) | not known to be exposed — UNVERIFIED | no public endpoint known | PARTIAL |
| Facebook Pages API | yes, account-authorised | UNVERIFIED | none known | PARTIAL |
| TikTok Display/Business API | needs approved app + user auth | UNVERIFIED | Creative Center is a web UI, no API known | REQUIRES ACCESS |
| TikTok Commercial Music Library | licence reference only | n/a | n/a | REQUIRES ACCESS (manual check) |
| YouTube Data/Analytics API | yes, channel-authorised | Shorts audio attribution UNVERIFIED | none | PARTIAL |
| Audio ID / metadata providers (e.g. fingerprinting, BPM) | n/a | needs the audio file or a licence | n/a | REQUIRES ACCESS |

Compliant fallback for every UNVERIFIED cell: a person fills the worksheet
(`scripts/music_intel.py <brand> worksheet`), then `import`. Links are tagged `source: manual`.

## Built (phase 2) — `_lib/music_intel.py`
Audio identity (nulls stay null, spelling variants dedupe, conflicting values recorded not overwritten);
licensing as a hard filter (`commercially_usable`: default refuse, VERIFIED needs evidence,
checked per platform, country, organic/paid, business account, expiry); idempotent manual
post→audio import; raw metric snapshots at 1h/24h/72h/7d/30d with per-platform metric names;
reach relative to the account's own earlier posts (refuses under 5 baseline posts, no look-ahead);
`health()` that says when comparison is not yet possible.
Tests: `tests/test_v2026_10_14_music_intel.py` (10, incl. brand isolation and the real Stick feed).

## Not built
Adapters, trend detection, recommendation/scoring, statistics, experiments, dashboard, reports.
Each depends on audio links existing; today there are 0 of 130.
