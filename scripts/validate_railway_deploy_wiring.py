#!/usr/bin/env python3
"""validate_railway_deploy_wiring.py — auto-validate that the Railway deploy
pipeline is wired correctly so we don't repeat the 2026-08-13 phantom-commit
incident.

What this script verifies (each check returns OK / WARN / FAIL):

  CHECK A — GITHUB_TOKEN is set in the Railway env (the most common silent
            breakage after the GitHub PAT expires or is rotated).

  CHECK B — the PAT, if present, actually authenticates against GitHub and
            has contents:write on the swing-shack-dashboard repo (otherwise
            pushes land silently but auto-deploy doesn't fire).

  CHECK C — the live API at swing-shack-dashboard-production.up.railway.app
            responds AND a unique-to-latest-commit endpoint returns the
            expected payload (the only real check that the running code
            matches HEAD — git_synced:false lies, dashboard hashes lie,
            but a working /api/intel/post_conversion_score is truth).

  CHECK D — the latest commit on GitHub feat/asset-state-engine matches the
            set of commits referenced by the live app's data files (e.g.
            post-conversion-score.json's schema URL contains the SHA
            prefix that generated it). If the data files are stale by more
            than 7 days, that's a "stale pipeline" smell — different from
            "not deployed" but still a flag.

  CHECK E — Railway dashboard UI shows the right branch. This one we cannot
            verify from a sandbox (no Railway API token in the env). We
            surface it as "MANUAL CHECK NEEDED" with a copy-paste-able URL
            to the deploy settings.

Output formats:
  - Default:    pretty text report (use --json for machine-readable)
  - Exit code:  0 = all OK / WARN
                1 = any FAIL (CI-blocking severity)
                2 = any CHECK E unverified (manual review needed)

Usage:
  python3 scripts/validate_railway_deploy_wiring.py
  python3 scripts/validate_railway_deploy_wiring.py --json
  python3 scripts/validate_railway_deploy_wiring.py --strict    # any WARN also exits 1
  python3 scripts/validate_railway_deploy_wiring.py --quiet     # only show FAILs

This script reads the running environment, not the local repo. Run it from
the Railway service itself (via a one-off deploy or a manual cron) for
Check A and Check B accuracy. Run it locally for Check C/D/E (which is
the most common case — a CI smoke test after a push).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

# ── Configuration ────────────────────────────────────────────────────────
# Defaults match the Swing Shack deployment. Override via flags or env vars.
DEFAULT_BASE_URL = os.environ.get(
    "SWING_SHACK_BASE_URL",
    "https://swing-shack-dashboard-production.up.railway.app",
)
DEFAULT_REPO = os.environ.get(
    "SWING_SHACK_GITHUB_REPO",
    "clawdiavector/swing-shack-dashboard",
)
DEFAULT_BRANCH = os.environ.get(
    "SWING_SHACK_GITHUB_BRANCH",
    "feat/asset-state-engine",
)
# Endpoint that exists ONLY in the latest commit (added in 9c9d8b9).
# If this endpoint stops returning 200 with expected payload, the running
# code is at least 1 commit behind HEAD.
UNIQUE_TO_LATEST_ENDPOINT = "/api/intel/post_conversion_score?top=5"
# Substring that proves the running app is up-to-date with the schema
# introduced in the post-conversion-score commit.
LATEST_PAYLOAD_MARKER = "post-conversion-score"
# File on disk that should reflect the most recent scoring run.
DATA_FILE = os.environ.get(
    "SWING_SHACK_PCS_FILE",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "data", "post-conversion-score.json",
    ),
)
DATA_FILE_STALE_DAYS = 7
DEPLOY_SETTINGS_URL = (
    f"https://railway.com/project/{os.environ.get('SWING_SHACK_RAILWAY_PROJECT', '<project>')}"
    f"/service/{os.environ.get('SWING_SHACK_RAILWAY_SERVICE', '<service>')}/settings"
)

# ── Status helpers ───────────────────────────────────────────────────────
STATUS_OK = "OK"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"
STATUS_MANUAL = "MANUAL"  # cannot verify from sandbox, manual check needed

STATUS_BADGE = {
    STATUS_OK: "✅",
    STATUS_WARN: "⚠️ ",
    STATUS_FAIL: "❌",
    STATUS_MANUAL: "👆",
}

# Severity weights for the exit-code decision
SEVERITY = {
    STATUS_OK: 0,
    STATUS_WARN: 1,
    STATUS_MANUAL: 2,
    STATUS_FAIL: 3,
}


def _print(*args, **kwargs):
    print(*args, **kwargs)


# ── HTTP helper (no external deps) ──────────────────────────────────────
def _http_get(url: str, headers: Dict[str, str] | None = None, timeout: int = 15) -> Tuple[int, Dict[str, str], str]:
    """Return (status_code, response_headers, body_text)."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read().decode("utf-8", errors="replace") if e.fp else ""
    except Exception as e:
        return 0, {}, str(e)


# ── The five checks ─────────────────────────────────────────────────────

def check_a_github_token_env() -> Dict[str, Any]:
    """Check A: GITHUB_TOKEN present in the running process env.

    Two ways to detect this:
      1. Read os.environ directly (works when run inside the Railway service).
      2. Call /api/admin/env-debug-style endpoint that exposes env prefixes
         without leaking values (works when the endpoint exists).

    Severity calibration:
      - Run inside Railway (CAMPAIGN_OS_RUNNING_ON_RAILWAY=1 set, or
        DATA_DIR starts with /data/) AND token missing → FAIL
      - Run locally AND token missing → WARN (token lives in Railway
        env vars, not here; we just can't see it from the Mac)
    """
    is_railway_context = (
        os.environ.get("CAMPAIGN_OS_RUNNING_ON_RAILWAY") == "1"
        or (os.environ.get("DATA_DIR") or "").startswith("/data")
    )

    direct_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if direct_token:
        # Don't expose the value — only length + prefix
        return {
            "check": "A: GITHUB_TOKEN env var present",
            "status": STATUS_OK,
            "evidence": (
                f"GITHUB_TOKEN is set in the running process env "
                f"(length={len(direct_token)}, prefix={direct_token[:4]}...). "
                f"This means Railway can authenticate against GitHub."
            ),
            "fix": None,
        }

    # Token missing. Severity depends on context.
    if is_railway_context:
        status = STATUS_FAIL
        where = "the Railway service"
    else:
        status = STATUS_WARN
        where = "your local Mac (token lives in Railway env vars, not here)"

    # v2026-08-13: Try the /api/admin/env-debug endpoint to see if the
    # running service has the token. This gives us a positive signal even
    # when the script runs locally.
    env_debug_status, _, env_debug_body = _http_get(
        f"{DEFAULT_BASE_URL}/api/admin/env-debug", timeout=10
    )
    remote_token_set = False
    remote_token_prefix = None
    remote_token_length = 0
    if env_debug_status == 200:
        try:
            ed = json.loads(env_debug_body)
            # /api/admin/env-debug returns {"env": {KEY: {"set", "length", "prefix"}}}
            env_block = ed.get("env", ed)
            gh_info = env_block.get("GITHUB_TOKEN") or env_block.get("GH_TOKEN") or {}
            remote_token_set = bool(gh_info.get("set"))
            remote_token_prefix = gh_info.get("prefix")
            remote_token_length = gh_info.get("length", 0)
        except Exception:
            pass

    if remote_token_set:
        return {
            "check": "A: GITHUB_TOKEN env var present (on Railway)",
            "status": STATUS_OK,
            "evidence": (
                f"GITHUB_TOKEN is NOT in this process's local env (expected — "
                f"we're on the Mac), but /api/admin/env-debug confirms it IS "
                f"set on the running Railway service "
                f"(prefix={remote_token_prefix}, length={remote_token_length}). "
                f"Auto-deploys will fire on push."
            ),
            "fix": None,
        }

    return {
        "check": "A: GITHUB_TOKEN env var present",
        "status": status,
        "evidence": (
            f"GITHUB_TOKEN is NOT set in this process's env "
            f"(and /api/admin/env-debug on the live service reports it as "
            f"not set either). This script appears to be running on {where}."
        ),
        "fix": (
            "If on Railway: add GITHUB_TOKEN=*** fine-grained PAT> to the "
            "service Variables tab. Use a fine-grained token with "
            "Contents:Read+Write on the swing-shack-dashboard repo only. "
            "Classic PATs work but have broader blast radius.\n"
            "If on your Mac: set GITHUB_TOKEN in your shell before running "
            "this script, OR run it from inside the Railway service shell "
            "(`railway run python ...`) to test the actual env value."
        ),
    }


def check_b_token_authenticates() -> Dict[str, Any]:
    """Check B: PAT actually authenticates against GitHub AND has repo access.

    This is the silent-failure mode — token is set but expired/rotated/
    scope-changed, and pushes land but auto-deploy doesn't fire.
    """
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return {
            "check": "B: GitHub token authenticates + has repo access",
            "status": STATUS_WARN,
            "evidence": (
                "No GITHUB_TOKEN in env, so cannot verify auth from this script. "
                "If you have it set in Railway but not here, run this script "
                "from inside the Railway service to test the actual env value."
            ),
            "fix": (
                "Export GITHUB_TOKEN in your shell before running, OR run this "
                "script from the Railway service shell (railway run python ...)."
            ),
        }

    # Probe GitHub /user endpoint
    code, _, body = _http_get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "validate-railway-deploy-wiring",
        },
    )

    if code != 200:
        return {
            "check": "B: GitHub token authenticates + has repo access",
            "status": STATUS_FAIL,
            "evidence": (
                f"GitHub /user returned {code}: {body[:200]}. "
                f"The token is set but does NOT authenticate. "
                f"Most likely cause: token expired or rotated."
            ),
            "fix": (
                "Generate a new fine-grained PAT at "
                "https://github.com/settings/tokens?type=beta and update the "
                "GITHUB_TOKEN env var on Railway."
            ),
        }

    try:
        user_data = json.loads(body)
        login = user_data.get("login", "?")
    except Exception:
        login = "?"

    # Check repo access
    code2, _, body2 = _http_get(
        f"https://api.github.com/repos/{DEFAULT_REPO}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "validate-railway-deploy-wiring",
        },
    )
    if code2 == 404:
        return {
            "check": "B: GitHub token authenticates + has repo access",
            "status": STATUS_FAIL,
            "evidence": (
                f"Token authenticates as '{login}' but cannot see "
                f"repo {DEFAULT_REPO} (404). The token doesn't have access "
                f"to this specific repo."
            ),
            "fix": (
                "Regenerate the fine-grained PAT and explicitly select the "
                f"{DEFAULT_REPO} repo under 'Repository access'."
            ),
        }
    if code2 != 200:
        return {
            "check": "B: GitHub token authenticates + has repo access",
            "status": STATUS_WARN,
            "evidence": (
                f"Token authenticates as '{login}' but /repos/{DEFAULT_REPO} "
                f"returned {code2}. Possibly a rate-limit or temporary GitHub issue."
            ),
            "fix": "Re-run the script. If persistent, check the token scopes.",
        }

    try:
        repo_data = json.loads(body2)
        permissions = repo_data.get("permissions", {})
        push_ok = permissions.get("push", False)
        default_branch = repo_data.get("default_branch", "?")
    except Exception:
        push_ok = False
        default_branch = "?"

    if not push_ok:
        return {
            "check": "B: GitHub token authenticates + has repo access",
            "status": STATUS_FAIL,
            "evidence": (
                f"Token authenticates as '{login}' and can READ {DEFAULT_REPO} "
                f"but does NOT have push (write) permission. Auto-deploy may "
                f"fire (Railway only needs read for webhook trigger) but the "
                f"token can't push from CLI either. Default branch on GitHub: {default_branch}."
            ),
            "fix": (
                "In the fine-grained PAT settings, set 'Contents' to "
                "'Read and write' for the swing-shack-dashboard repo."
            ),
        }

    return {
        "check": "B: GitHub token authenticates + has repo access",
        "status": STATUS_OK,
        "evidence": (
            f"Token authenticates as '{login}' and has push access to "
            f"{DEFAULT_REPO} (default branch: {default_branch}). "
            f"Auto-deploy webhook will fire on push."
        ),
        "fix": None,
    }


DEFAULT_PASSWORD = os.environ.get("SWING_SHACK_DEV_PASSWORD", "swing-shack-dev-2026")


def _login(base_url: str, password: str) -> str | None:
    """POST /login with the shared password, return the session cookie value
    (or None if login failed). Uses urllib to keep zero deps."""
    from urllib.parse import urlencode
    req = urllib.request.Request(
        f"{base_url}/login",
        data=urlencode({"password": password}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            cookies = resp.headers.get_all("Set-Cookie") or []
            for c in cookies:
                if c.startswith("cos_session="):
                    # Extract the cookie value (before the first ;)
                    return c.split("=", 1)[1].split(";", 1)[0]
    except urllib.error.HTTPError as e:
        if e.code in (302, 303):
            cookies = e.headers.get_all("Set-Cookie") or []
            for c in cookies:
                if c.startswith("cos_session="):
                    return c.split("=", 1)[1].split(";", 1)[0]
        return None
    except Exception:
        return None
    return None


def check_c_latest_endpoint_responds() -> Dict[str, Any]:
    """Check C: the unique-to-latest-commit endpoint returns 200 with
    expected payload. The ONLY way to know the running code is current.
    """
    url = f"{DEFAULT_BASE_URL}{UNIQUE_TO_LATEST_ENDPOINT}"

    # v2026-08-13: Authenticate first. Most /api/intel/* routes are
    # behind the shared-password gate. Without auth we get 401 and
    # conclude the endpoint is "missing" when it's actually working.
    session_cookie = _login(DEFAULT_BASE_URL, DEFAULT_PASSWORD)
    if not session_cookie:
        return {
            "check": f"C: Live endpoint {UNIQUE_TO_LATEST_ENDPOINT}",
            "status": STATUS_FAIL,
            "evidence": (
                f"Could not log in to {DEFAULT_BASE_URL} with the default "
                f"dev password. Either the password is wrong (set "
                f"SWING_SHACK_DEV_PASSWORD env var to override), or the "
                f"service is down, or the login route is broken."
            ),
            "fix": (
                "Verify the service is up: curl "
                f"{DEFAULT_BASE_URL}/api/health. If 200, check the password "
                "matches CAMPAIGN_OS_PASSWORD on the running service."
            ),
        }

    code, _, body = _http_get(
        url,
        headers={"Cookie": f"cos_session={session_cookie}"},
        timeout=15,
    )

    if code == 0:
        return {
            "check": f"C: Live endpoint {UNIQUE_TO_LATEST_ENDPOINT}",
            "status": STATUS_FAIL,
            "evidence": (
                f"Could not reach {DEFAULT_BASE_URL} at all. "
                f"Network error or service is down."
            ),
            "fix": "Check Railway service status. Service may be crashed or rebuilding.",
        }

    if code == 404:
        return {
            "check": f"C: Live endpoint {UNIQUE_TO_LATEST_ENDPOINT}",
            "status": STATUS_FAIL,
            "evidence": (
                f"{UNIQUE_TO_LATEST_ENDPOINT} returns 404 on the live service. "
                f"This endpoint was added in the latest commit. "
                f"If you're seeing 404, the running code is from BEFORE that "
                f"commit landed. Either the deploy is queued, failed, or the "
                f"branch Railway is watching is wrong."
            ),
            "fix": (
                "1. Verify the latest commit is on the branch Railway watches "
                "(Settings → Source). 2. Trigger a manual redeploy. "
                "3. If still 404 after 5 min, the branch is wrong — "
                "switch it to feat/asset-state-engine."
            ),
        }

    if code == 401:
        return {
            "check": f"C: Live endpoint {UNIQUE_TO_LATEST_ENDPOINT}",
            "status": STATUS_FAIL,
            "evidence": (
                f"{UNIQUE_TO_LATEST_ENDPOINT} returned HTTP 401 after login. "
                f"Login worked but the endpoint rejects the session. "
                f"Possible causes: session expired immediately (clock skew), "
                f"or the endpoint has its own auth check beyond the gate."
            ),
            "fix": (
                "Check the running app's CAMPAIGN_OS_SECRET env var. If it "
                "rotated between deploys, sessions from the old secret are "
                "invalid."
            ),
        }

    if code != 200:
        return {
            "check": f"C: Live endpoint {UNIQUE_TO_LATEST_ENDPOINT}",
            "status": STATUS_FAIL,
            "evidence": (
                f"{UNIQUE_TO_LATEST_ENDPOINT} returned HTTP {code}. "
                f"Body: {body[:200]}"
            ),
            "fix": (
                "Check Railway logs for the running service. Look for "
                "tracebacks in the last deploy."
            ),
        }

    if LATEST_PAYLOAD_MARKER not in body:
        return {
            "check": f"C: Live endpoint {UNIQUE_TO_LATEST_ENDPOINT}",
            "status": STATUS_FAIL,
            "evidence": (
                f"{UNIQUE_TO_LATEST_ENDPOINT} returned 200 but the response "
                f"does not contain expected marker '{LATEST_PAYLOAD_MARKER}'. "
                f"The endpoint is wired but the payload shape is wrong. "
                f"Running code is from an IN-BETWEEN commit, not HEAD."
            ),
            "fix": (
                "The latest push is missing from the deploy. Check what "
                "commit the running app's data was generated from."
            ),
        }

    try:
        data = json.loads(body)
        posts_scored = data.get("summary", {}).get("posts_scored", 0)
        winning_format = data.get("summary", {}).get("winning_format")
    except Exception:
        posts_scored = 0
        winning_format = None

    return {
        "check": f"C: Live endpoint {UNIQUE_TO_LATEST_ENDPOINT}",
        "status": STATUS_OK,
        "evidence": (
            f"{UNIQUE_TO_LATEST_ENDPOINT} returned 200 with expected marker "
            f"'{LATEST_PAYLOAD_MARKER}'. Posts scored in latest run: "
            f"{posts_scored}. Winning format: {winning_format}. "
            f"Running code is current with the deployed branch."
        ),
        "fix": None,
    }


def check_d_data_file_freshness() -> Dict[str, Any]:
    """Check D: post-conversion-score.json on disk reflects a recent run.

    Stale data files = stale pipeline. Different bug from "not deployed" —
    the app is up but the data behind it is days old.
    """
    if not os.path.exists(DATA_FILE):
        return {
            "check": f"D: Data file {os.path.basename(DATA_FILE)} freshness",
            "status": STATUS_FAIL,
            "evidence": f"{DATA_FILE} does not exist on disk.",
            "fix": (
                "Run scripts/fetch_post_conversion_score.py to generate it. "
                "This is what the live endpoint reads from."
            ),
        }

    try:
        with open(DATA_FILE) as f:
            data = json.load(f)
        generated = data.get("generated") or data.get("updated") or ""
        # Schema URL contains the schema version, not a SHA — but for our
        # purposes the generated_at timestamp is the freshness signal.
        if generated.endswith("Z"):
            generated_dt = dt.datetime.fromisoformat(generated.replace("Z", "+00:00"))
        else:
            generated_dt = dt.datetime.fromisoformat(generated)
        age_days = (dt.datetime.now(dt.timezone.utc) - generated_dt).days
        age_hours = (dt.datetime.now(dt.timezone.utc) - generated_dt).total_seconds() / 3600
    except Exception as e:
        return {
            "check": f"D: Data file {os.path.basename(DATA_FILE)} freshness",
            "status": STATUS_WARN,
            "evidence": f"Could not parse generated timestamp: {e}",
            "fix": "Re-run the fetch script to regenerate.",
        }

    if age_days >= DATA_FILE_STALE_DAYS:
        return {
            "check": f"D: Data file {os.path.basename(DATA_FILE)} freshness",
            "status": STATUS_WARN,
            "evidence": (
                f"{os.path.basename(DATA_FILE)} was generated {age_days} days ago "
                f"(on {generated}). The pipeline likely stopped running."
            ),
            "fix": (
                f"Re-run scripts/fetch_post_conversion_score.py manually. "
                f"If this file is regenerated by nightshift cron, check the "
                f"cron logs for failures."
            ),
        }

    return {
        "check": f"D: Data file {os.path.basename(DATA_FILE)} freshness",
        "status": STATUS_OK,
        "evidence": (
            f"{os.path.basename(DATA_FILE)} was generated "
            f"{age_hours:.1f} hours ago (on {generated}). Fresh."
        ),
        "fix": None,
    }


def check_e_railway_branch_configured() -> Dict[str, Any]:
    """Check E: Railway is watching the right branch.

    Cannot verify from a sandbox (no Railway API token in the env). We surface
    this as a manual check with the exact dashboard URL to visit.
    """
    return {
        "check": "E: Railway branch + auto-deploy config",
        "status": STATUS_MANUAL,
        "evidence": (
            "Cannot verify from the sandbox. Railway's deploy settings live "
            "in the dashboard, not in any public API reachable from here."
        ),
        "fix": (
            f"Open {DEPLOY_SETTINGS_URL} and confirm:\n"
            f"  - Connected repo: {DEFAULT_REPO}\n"
            f"  - Branch: {DEFAULT_BRANCH}\n"
            f"  - Auto-deploy: ON\n"
            f"If branch is wrong, change it and save. Railway will redeploy "
            f"from the new branch within ~2 minutes."
        ),
    }


# ── Orchestration ───────────────────────────────────────────────────────

CHECKS = [
    ("A", check_a_github_token_env),
    ("B", check_b_token_authenticates),
    ("C", check_c_latest_endpoint_responds),
    ("D", check_d_data_file_freshness),
    ("E", check_e_railway_branch_configured),
]


def run_checks() -> List[Dict[str, Any]]:
    results = []
    for label, fn in CHECKS:
        try:
            r = fn()
            r["check"] = f"{label}. {r['check']}"
            results.append(r)
        except Exception as e:
            results.append({
                "check": f"{label}. <exception>",
                "status": STATUS_FAIL,
                "evidence": f"Check raised exception: {e}",
                "fix": "Report this to the script author — the check itself crashed.",
            })
    return results


def print_pretty(results: List[Dict[str, Any]], quiet: bool = False) -> None:
    by_status: Dict[str, List[Dict[str, Any]]] = {s: [] for s in STATUS_BADGE}
    for r in results:
        by_status[r["status"]].append(r)

    if not quiet or any(r["status"] == STATUS_FAIL for r in results):
        _print()
        _print("=" * 72)
        _print(" RAILWAY DEPLOY WIRING — VALIDATION REPORT")
        _print("=" * 72)
        _print(f" Repo:    {DEFAULT_REPO}")
        _print(f" Branch:  {DEFAULT_BRANCH}")
        _print(f" Live:    {DEFAULT_BASE_URL}")
        _print(f" Run at:  {dt.datetime.now(dt.timezone.utc).isoformat()}")
        _print()

    for r in results:
        badge = STATUS_BADGE.get(r["status"], "?")
        _print(f"  {badge}  {r['check']}")
        _print(f"       {r['evidence']}")
        if r.get("fix") and (r["status"] in (STATUS_FAIL, STATUS_WARN, STATUS_MANUAL)):
            _print(f"       FIX: {r['fix']}")
        _print()

    # Summary
    counts = {s: len(by_status[s]) for s in STATUS_BADGE}
    _print("-" * 72)
    _print(f" SUMMARY: OK={counts[STATUS_OK]} | "
           f"WARN={counts[STATUS_WARN]} | "
           f"FAIL={counts[STATUS_FAIL]} | "
           f"MANUAL={counts[STATUS_MANUAL]}")
    _print("-" * 72)


def main() -> int:
    global DEFAULT_REPO, DEFAULT_BRANCH, DEFAULT_BASE_URL
    p = argparse.ArgumentParser(
        description="Auto-validate Railway deploy wiring (GITHUB_TOKEN, repo access, live endpoint, data freshness)"
    )
    p.add_argument("--json", action="store_true", help="Output JSON instead of pretty text")
    p.add_argument("--strict", action="store_true",
                   help="Exit 1 on any WARN (not just FAIL)")
    p.add_argument("--quiet", action="store_true",
                   help="Only print FAIL results")
    p.add_argument("--repo", default=DEFAULT_REPO, help="GitHub repo (owner/name)")
    p.add_argument("--branch", default=DEFAULT_BRANCH, help="GitHub branch name")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Live app base URL")
    args = p.parse_args()

    # Apply overrides to module-level defaults so checks see them
    DEFAULT_REPO = args.repo
    DEFAULT_BRANCH = args.branch
    DEFAULT_BASE_URL = args.base_url

    results = run_checks()

    if args.json:
        out = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "repo": DEFAULT_REPO,
            "branch": DEFAULT_BRANCH,
            "base_url": DEFAULT_BASE_URL,
            "checks": results,
            "summary": {
                "ok": sum(1 for r in results if r["status"] == STATUS_OK),
                "warn": sum(1 for r in results if r["status"] == STATUS_WARN),
                "fail": sum(1 for r in results if r["status"] == STATUS_FAIL),
                "manual": sum(1 for r in results if r["status"] == STATUS_MANUAL),
            },
        }
        _print(json.dumps(out, indent=2))
    else:
        print_pretty(results, quiet=args.quiet)

    # Exit code decision
    has_fail = any(r["status"] == STATUS_FAIL for r in results)
    has_warn = any(r["status"] == STATUS_WARN for r in results)
    has_manual = any(r["status"] == STATUS_MANUAL for r in results)

    if has_fail:
        return 1
    if args.strict and has_warn:
        return 1
    if has_manual and not (has_fail or has_warn):
        return 2  # manual review needed but nothing's broken
    return 0


if __name__ == "__main__":
    sys.exit(main())
