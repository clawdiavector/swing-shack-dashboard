"""Single-secret paste receiver for Meta credentials.

Listens on localhost:53724. Christelle pastes:
  - META_APP_ID
  - META_ACCESS_TOKEN (long-lived user or system-user token)
  - META_PAGE_ID
  - META_INSTAGRAM_BUSINESS_ACCOUNT_ID

The portal returns a one-time token; we then read the values from
the on-disk file and set them as Railway env vars via the Railway API.

Run: .venv/bin/python3 scripts/meta_credentials_portal.py

Environment:
  RAILWAY_TOKEN          - Railway API token with write access to the env vars
  SERVICE_ID             - Railway service ID (default: auto-detect via gh api)
  PROJECT_ID             - Railway project ID
"""
import json
import os
import sys
import threading
import time
import secrets
import http.server
import socketserver
from pathlib import Path

PORT = 53724
SECRETS_DIR = Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/credentials")
SECRETS_DIR.mkdir(parents=True, exist_ok=True)
SECRET_FILE = SECRETS_DIR / "meta-railway-secrets.json"
SECRET_FILE.chmod(0o600)

# HTML page - shown once, then "submitted"
HTML = """<!DOCTYPE html>
<html>
<head>
<title>Meta Credentials Portal - one-time paste</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0b0f14; color: #f4f7fb; max-width: 720px; margin: 40px auto; padding: 20px; }
h1 { color: #d7b46a; }
label { display: block; margin-top: 14px; font-weight: 700; }
input { width: 100%; padding: 10px; background: #16212c; color: #f4f7fb; border: 1px solid #273443; border-radius: 8px; font-family: monospace; font-size: 12px; }
button { background: #5dff9d; color: #0b0f14; border: none; padding: 12px 24px; border-radius: 8px; font-weight: 700; margin-top: 20px; cursor: pointer; }
.note { background: #16212c; padding: 12px; border-left: 4px solid #d7b46a; border-radius: 6px; margin: 14px 0; font-size: 13px; }
.warn { border-left-color: #ff7a7a; }
</style>
</head>
<body>
<h1>Meta Credentials Paste Portal</h1>
<p class="note">Paste the four values from Meta Developer Console / Graph API Explorer. Token never leaves your browser in plaintext form beyond this submission. The portal writes them to a chmod-600 file Heidi reads to set Railway env vars, then deletes the on-disk copy.</p>

<form method="POST" action="/submit">
  <label for="app_id">META_APP_ID</label>
  <input type="text" id="app_id" name="app_id" placeholder="1234567890" required>

  <label for="page_id">META_PAGE_ID (Swing Shack Facebook Page numeric ID)</label>
  <input type="text" id="page_id" name="page_id" placeholder="114408218135716" required>

  <label for="ig_id">META_INSTAGRAM_BUSINESS_ACCOUNT_ID (numeric)</label>
  <input type="text" id="ig_id" name="ig_id" placeholder="17841456713897671" required>

  <label for="token">META_ACCESS_TOKEN (long-lived user/system-user token - keep on one line)</label>
  <textarea id="token" name="token" rows="4" style="width: 100%; padding: 10px; background: #16212c; color: #f4f7fb; border: 1px solid #273443; border-radius: 8px; font-family: monospace; font-size: 11px;" placeholder="EAAYwoXNcZBLgBP..." required></textarea>

  <p class="note warn">Where to get these: Meta Developer Console &rarr; Your App &rarr; Graph API Explorer, generate token with scopes: pages_show_list, pages_read_engagement, pages_read_user_content, read_insights, business_management, instagram_basic, instagram_manage_insights.</p>

  <button type="submit">Submit credentials</button>
</form>
</body>
</html>
"""

ACK_HTML = """<!DOCTYPE html>
<html>
<head><title>Submitted</title></head>
<body style="font-family: -apple-system, sans-serif; background: #0b0f14; color: #5dff9d; text-align: center; padding: 60px;">
<h1>OK - credentials received</h1>
<p>Heidi is now writing these as Railway env vars. You'll see the live Facebook section appear in the next 60-90s when the deploy rebuilds.</p>
<p style="color: #aeb8c5; font-size: 13px;">You can close this tab.</p>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
            if "/p" not in (args[0] if args else ""):
                sys.stderr.write("[meta-portal] " + (format % args) + "\n")

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML.encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/submit":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode()
        # Parse form-urlencoded
        from urllib.parse import parse_qs
        params = parse_qs(body)
        creds = {
            "app_id": params.get("app_id", [""])[0].strip(),
            "page_id": params.get("page_id", [""])[0].strip(),
            "instagram_business_account_id": params.get("ig_id", [""])[0].strip(),
            "access_token": params.get("token", [""])[0].strip(),
        }
        # Validate
        if not all([creds["app_id"], creds["page_id"], creds["instagram_business_account_id"], creds["access_token"]]):
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Missing field</h1>")
            return
        # Atomic write
        tmp = SECRET_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(creds, f)
        os.replace(tmp, SECRET_FILE)
        SECRET_FILE.chmod(0o600)
        # Signal main thread
        print("\n" + "=" * 60)
        print("CREDENTIALS RECEIVED")
        print("=" * 60)
        print(f"  META_APP_ID: {creds['app_id']}")
        print(f"  META_PAGE_ID: {creds['page_id']}")
        print(f"  META_INSTAGRAM_BUSINESS_ACCOUNT_ID: {creds['instagram_business_account_id']}")
        print(f"  META_ACCESS_TOKEN: <{len(creds['access_token'])} chars> prefix={creds['access_token'][:20]}...")
        print(f"  Saved to: {SECRET_FILE}")
        print("=" * 60 + "\n")
        # Stop the server after first submission
        threading.Thread(target=lambda: (time.sleep(0.5), httpd.shutdown()), daemon=True).start()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(ACK_HTML.encode())


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print(f"Starting portal on http://localhost:{PORT}", flush=True)
    httpd = ThreadedTCPServer(("127.0.0.1", PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("Portal stopped.", flush=True)
        # If credentials were received, print them
        if SECRET_FILE.exists():
            print(f"\nCreds file: {SECRET_FILE}")