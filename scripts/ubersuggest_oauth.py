#!/usr/bin/env python3
"""
ubersuggest_oauth.py — Ubersuggest MCP OAuth dance.

Run this script on the operator's Mac to authorize Campaign OS to read
SEO data from Ubersuggest. The flow is:

    1. Spin up an HTTP listener on 127.0.0.1:<port> (loopback).
    2. Spin up a Cloudflare quick tunnel that fronts that port (so
       Christelle can open the URL from her phone, not just the Mac).
    3. Build the /authorize URL with PKCE (S256) + state + scopes.
    4. Open the user's browser to that URL.
    5. Ubersuggest redirects back to /?code=...&state=...
    6. We exchange the code + verifier at /token → access_token + refresh_token.
    7. We save the bundle to
       /Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/ubersuggest-api.json
       (chmod 600, OUTSIDE the repo, sibling to other credentials).
    8. Verify the token works by calling /mcp tools/call auth_status.
    9. Print the green Path and exit.

This is a one-time dance. After it succeeds, scripts/fetch_ubersuggest.py
+ scripts/ubersuggest_refresh_token.py can run unattended; the wrapper
auto-refreshes on 401.

Usage:
    python3 scripts/ubersuggest_oauth.py [options]

Options:
    --port PORT       Local loopback port for the callback listener (default 9999).
    --scopes SCOPES   Space-separated OAuth scopes (default all 9).
    --no-browser      Print the /authorize URL instead of opening the browser
                      (use if running headless via SSH).
    --verify-only     Don't run the dance; just confirm the saved token still works.
    --status          Just print the current token status (configured/expires/tier).
    --timeout SECONDS How long to wait for the OAuth callback (default 300 = 5 min).

No flags = run the full dance.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import platform
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Optional

# Default values (overridden by the wrapper module or env vars)
CRED_DIR = Path(
    "/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials"
)
CRED_FILE = CRED_DIR / "ubersuggest-api.json"

AUTHORIZE_URL = "https://ubersuggest-mcp.neilpatelapi.com/authorize"
TOKEN_URL = "https://ubersuggest-mcp.neilpatelapi.com/token"
MCP_URL = "https://ubersuggest-mcp.neilpatelapi.com/mcp"
DISCOVERY_URL = "https://ubersuggest-mcp.neilpatelapi.com/.well-known/oauth-authorization-server"
DEFAULT_CLIENT_ID = "ubersuggest-mcp"
DEFAULT_SCOPES = (
    "profile domain keywords serp backlinks site_audit content projects utility"
)
DEFAULT_PORT = 9999
DEFAULT_TIMEOUT = 300  # 5 minutes to log in


# ─── Helpers ────────────────────────────────────────────────────────────

def _b64url_nopad(raw: bytes) -> str:
    """Base64url-encode `raw` and strip padding (RFC 7636 §4)."""
    import base64
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_pkce() -> tuple[str, str]:
    """RFC 7636 PKCE pair. Returns (verifier, S256(challenge))."""
    import base64, hashlib
    # 32 random bytes → 43-char base64url — well within 43-128 char RFC range.
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def generate_state() -> str:
    """Random base64url string used to bind the request to the callback (CSRF)."""
    return _b64url_nopad(secrets.token_bytes(16))


def free_port_hint(preferred: int) -> int:
    """Return `preferred` if free, else scan 9990-10099 for a free one."""
    def _is_free(p: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", p))
                return True
            except OSError:
                return False

    if _is_free(preferred):
        return preferred
    for p in range(9990, 10100):
        if _is_free(p):
            return p
    raise RuntimeError("no free port found in 9990-10099")


# ─── Cloudflare quick tunnel ────────────────────────────────────────────

def start_cloudflared_tunnel(local_port: int, log_path: str = "/tmp/cf-ubersuggest.log") -> tuple[subprocess.Popen, str]:
    """Spin up `cloudflared tunnel --url http://127.0.0.1:<port>`.

    Returns (Popen handle, https_url). Caller is responsible for terminating
    the process on exit.

    The URL appears in the log 5-10 seconds after startup — see pitfall #1
    in the public-ingress-tunnel-choice skill. Grep for it.
    """
    log_fh = open(log_path, "w")
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{local_port}", "--no-autoupdate"],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    # Poll for the URL up to 30 seconds.
    url = None
    for _ in range(60):
        time.sleep(0.5)
        try:
            content = Path(log_path).read_text()
        except OSError:
            continue
        import re
        m = re.search(r"(https://[a-z0-9-]+\.trycloudflare\.com)", content)
        if m:
            url = m.group(1)
            break
    if not url:
        proc.terminate()
        raise RuntimeError(
            f"cloudflared didn't print a trycloudflare.com URL within 30s — "
            f"check {log_path}"
        )
    return proc, url


# ─── Loopback callback server ───────────────────────────────────────────

class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """One-shot GET /  → captures ?code=…&state=… → replies with a friendly page
    → keeps the server alive for the rest of the flow."""

    def log_message(self, *_args, **_kwargs):
        pass  # silence stderr noise

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler contract)
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        state = qs.get("state", [None])[0]
        err = qs.get("error", [None])[0]
        err_desc = qs.get("error_description", [None])[0]

        if err:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(
                f"Ubersuggest returned an OAuth error: {err}\n"
                f"{err_desc or ''}\n\n"
                f"You can close this tab and re-run the script.".encode()
            )
            _OAUTH_RESULT["code"] = f"ERROR:{err}"
            return

        # CSRF check
        if not state or state != _OAUTH_RESULT["state_expected"]:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(
                "State mismatch (possible CSRF). Closing tab.\n".encode()
            )
            _OAUTH_RESULT["code"] = "ERROR:state_mismatch"
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            (
                "<!doctype html>\n"
                "<meta charset=utf-8>\n"
                "<title>Ubersuggest OAuth — token captured</title>\n"
                "<body style=\"font-family:system-ui;padding:2rem;max-width:36rem;margin:2rem auto\">\n"
                "  <h1 style=\"color:#1a7f37\">✓ Token captured</h1>\n"
                "  <p>Campaign OS now has access to your Ubersuggest account.</p>\n"
                "  <p>You can close this tab and return to the chat.</p>\n"
                "  <p style=\"color:#666;font-size:13px\">Saved to "
                "<code>~/.openclaw-instance2/workspace/clients/swing-shack/credentials/"
                "ubersuggest-api.json</code> with chmod 600.</p>\n"
                "</body>\n"
            ).encode()
        )
        _OAUTH_RESULT["code"] = code
        _OAUTH_RESULT["state"] = state


# Module-level mutable state for the callback server. One dance at a time.
_OAUTH_RESULT: dict = {"state_expected": None, "code": None, "state": None}


def instantiate_callback_server(port: int, state_expected: str) -> http.server.HTTPServer:
    """Start the loopback listener. Returns the HTTPServer (already serving)."""
    _OAUTH_RESULT["state_expected"] = state_expected
    _OAUTH_RESULT["code"] = None
    _OAUTH_RESULT["state"] = None
    server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# ─── Token exchange + save ──────────────────────────────────────────────

def exchange_code(code: str, code_verifier: str, redirect_uri: str) -> dict:
    """POST /token. Returns parsed JSON. Raises RuntimeError on failure."""
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    body = urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": DEFAULT_CLIENT_ID,
        "code_verifier": code_verifier,
    }).encode("utf-8")
    req = Request(
        TOKEN_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "campaign-os/ubersuggest-oauth/1.0",
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"error": str(e), "code": e.code}
        raise RuntimeError(f"token exchange failed ({e.code}): {err}") from e
    except URLError as e:
        raise RuntimeError(f"network error during token exchange: {e}") from e


def write_token_file(payload: dict) -> Path:
    """Atomic write of the credential file with chmod 600."""
    import tempfile
    CRED_DIR.mkdir(parents=True, exist_ok=True)

    now = int(time.time())
    expires_in = payload.get("expires_in")
    body = {
        "access_token": payload["access_token"],
        "token_type": payload.get("token_type", "Bearer"),
        "refresh_token": payload.get("refresh_token", ""),
        "scope": payload.get("scope", ""),
        "obtained_at": now,
    }
    if expires_in is not None:
        body["expires_in"] = int(expires_in)
        body["expires_at"] = now + int(expires_in)
    if "refresh_token" in payload:
        body["refresh_token"] = payload["refresh_token"]

    # Atomic rename-write pattern
    fd, tmp = tempfile.mkstemp(prefix=".ubersuggest-", suffix=".json", dir=str(CRED_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, CRED_FILE)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise
    return CRED_FILE


def verify_token_via_auth_status() -> str:
    """Call /mcp auth_status to confirm the freshly-saved token works.
    Returns a 1-line human-readable summary.
    """
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    if not CRED_FILE.exists():
        return "no token file saved yet"
    tok = json.loads(CRED_FILE.read_text()).get("access_token", "")
    if not tok:
        return "token file empty"
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "tools/call",
        "params": {"name": "auth_status", "arguments": {}},
    }).encode()
    req = Request(
        MCP_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {tok}",
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return f"authenticated OK · {json.dumps(data.get('result', data))[:120]}"
    except HTTPError as e:
        try:
            err = json.loads(e.read().decode())
        except Exception:
            err = {"error": str(e)}
        return f"HTTP {e.code} — {err}"


# ─── Browser opener (cross-platform) ────────────────────────────────────

def open_browser(url: str) -> None:
    """Open `url` in the user's default browser. macOS / linux / win supported."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", url])
        elif system == "Linux":
            # xdg-open is on every modern Linux; try common fallbacks otherwise.
            for cmd in (["xdg-open", url], ["gio", "open", url], ["wslview", url]):
                try:
                    subprocess.Popen(cmd)
                    return
                except FileNotFoundError:
                    continue
        elif system == "Windows":
            os.startfile(url)  # type: ignore[attr-defined]
    except Exception as e:
        print(f"[warn] could not auto-open browser: {e}\n  Open it manually:\n  {url}")


# ─── Subcommand: --status (just print current state) ───────────────────

def print_status() -> int:
    if not CRED_FILE.exists():
        print(f"NOT CONFIGURED — no token file at {CRED_FILE}")
        return 1
    data = json.loads(CRED_FILE.read_text())
    now = int(time.time())
    expires_at = data.get("expires_at", 0)
    remaining = expires_at - now if expires_at else None
    print("Ubersuggest credential status")
    print(f"  file:           {CRED_FILE}")
    print(f"  refreshed_at:   {data.get('refreshed_at')} ({_ago(data.get('refreshed_at', 0))})")
    print(f"  expires_at:     {expires_at} ({_ago(expires_at) if expires_at else 'n/a'})")
    if remaining is None:
        print(f"  remaining:      unknown")
    elif remaining < 0:
        print(f"  remaining:      EXPIRED {-remaining}s ago")
    else:
        print(f"  remaining:      {remaining}s")
    print(f"  scope:          {data.get('scope', '?')}")
    print(f"  has refresh:    {bool(data.get('refresh_token'))}")
    print()
    print("  auth_status probe:")
    print(f"    {verify_token_via_auth_status()}")
    return 0


def _ago(epoch: int) -> str:
    """Human-readable relative time. -1 = 'never'."""
    if not epoch:
        return "never"
    delta = int(time.time()) - epoch
    if delta < 0:
        return f"in {-delta}s"
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


# ─── Main ───────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description="Ubersuggest MCP OAuth dance (PKCE, public client).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help=f"loopback port (default {DEFAULT_PORT}, falls back to 9990-10099)")
    p.add_argument("--scopes", type=str, default=DEFAULT_SCOPES,
                   help="space-separated OAuth scopes")
    p.add_argument("--no-browser", action="store_true",
                   help="don't auto-open the browser (headless / SSH)")
    p.add_argument("--verify-only", action="store_true",
                   help="don't run the dance; just verify the saved token works")
    p.add_argument("--status", action="store_true",
                   help="print credential status + tier check + exit")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                   help=f"seconds to wait for OAuth callback (default {DEFAULT_TIMEOUT})")
    args = p.parse_args()

    print(f"Ubersuggest MCP OAuth dance")
    print(f"  client_id:  {DEFAULT_CLIENT_ID}")
    print(f"  issuer:     https://ubersuggest-mcp.neilpatelapi.com/")
    print(f"  token file: {CRED_FILE}")
    print(f"  PKCE:       S256 (RFC 7636)")
    print(f"  scopes:     {args.scopes}")
    print()

    if args.status:
        return print_status()

    if args.verify_only:
        print("[--verify-only] checking saved token…")
        msg = verify_token_via_auth_status()
        print(f"  {msg}")
        return 0 if "OK" in msg else 1

    # 1. Pick a free port
    port = free_port_hint(args.port)
    print(f"[1/8] loopback listener on 127.0.0.1:{port}")

    # 2. PKCE + state
    verifier, challenge = generate_pkce()
    state = generate_state()
    print(f"[2/8] PKCE verifier generated (43 chars); state = {state[:8]}…")

    # 3. Start loopback callback server
    server = instantiate_callback_server(port, state)
    loopback = f"http://127.0.0.1:{port}"
    print(f"[3/8] callback server up at {loopback}/")

    # 4. Start Cloudflare quick tunnel → public URL
    cf_proc = None
    public_url: Optional[str] = None
    try:
        try:
            cf_proc, public_url = start_cloudflared_tunnel(port)
            print(f"[4/8] Cloudflare quick tunnel: {public_url}/")
            redirect_uri = f"{public_url}/"
        except (FileNotFoundError, RuntimeError) as e:
            print(f"[4/8] cloudflared unavailable ({e}). Falling back to loopback.")
            print(f"      NOTE: URL only works if you can reach this Mac's 127.0.0.1:{port}.")
            redirect_uri = loopback + "/"
    finally:
        # 5. Build /authorize URL
        authorize_url = (
            f"{AUTHORIZE_URL}"
            f"?client_id={DEFAULT_CLIENT_ID}"
            f"&response_type=code"
            f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
            f"&state={urllib.parse.quote(state)}"
            f"&scope={urllib.parse.quote(args.scopes)}"
            f"&code_challenge={challenge}"
            f"&code_challenge_method=S256"
        )
        print()
        print(f"[5/8] AUTHORIZE URL (paste in browser if --no-browser):")
        print(f"      {authorize_url}")
        print()
        if not args.no_browser:
            print("[6/8] opening browser…")
            open_browser(authorize_url)

    # 7. Wait for callback
    print(f"[6/8] waiting up to {args.timeout}s for the /callback (browser will hit it after login)...")
    deadline = time.time() + args.timeout
    _OAUTH_RESULT["code"] = None
    while time.time() < deadline:
        if _OAUTH_RESULT.get("code"):
            break
        time.sleep(0.3)
    code = _OAUTH_RESULT.get("code")
    if not code:
        print("[ERROR] timed out waiting for /callback")
        return 2
    if code.startswith("ERROR:"):
        print(f"[ERROR] OAuth callback returned an error: {code}")
        return 3
    print(f"[7/8] got authorization code ({code[:12]}…)")

    # 8. Exchange code for tokens
    try:
        token_resp = exchange_code(code, verifier, redirect_uri)
    except Exception as e:
        print(f"[ERROR] token exchange failed: {e}")
        return 4
    if "access_token" not in token_resp:
        print(f"[ERROR] token response missing access_token: {token_resp}")
        return 5

    saved = write_token_file(token_resp)
    print(f"[8/8] token + refresh_token saved to {saved} (chmod 600)")

    # 9. Verify
    print()
    print("[verify] calling auth_status with the new token…")
    msg = verify_token_via_auth_status()
    print(f"  {msg}")

    # 10. Cleanup
    server.shutdown()
    if cf_proc:
        try:
            cf_proc.terminate()
        except Exception:
            pass

    print()
    print("DONE.")
    print("Next steps:")
    print("  • scripts/fetch_ubersuggest.py        — daily rank pull (after install-launchd step)")
    print("  • scripts/ubersuggest_refresh_token.py — weekly refresh")
    print("  • The /api/intel/ubersuggest endpoint on Railway will start returning live data.")
    print("  • The weekly_report will gain a 'SEO movers' claim once a rank pull lands.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[interrupted]")
        sys.exit(130)
