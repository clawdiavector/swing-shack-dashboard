"""
google_drive.py — Google Drive ingestion for Campaign OS brand directory.

This module does NOT store credentials in source. It expects either:
    1. An OAuth client secret JSON at $GOOGLE_OAUTH_CLIENT_SECRET (path)
    2. A stored refresh-token JSON at $GOOGLE_DRIVE_TOKEN (path)

The token file is created by the OAuth dance in `_oauth_dance()` which can
be triggered via setup-portal (no paste-in-chat). Once the refresh token is
on disk, subsequent runs never need a browser — the API client refreshes
silently.

Usage:
    from _lib import google_drive

    # First time (one-off, needs browser):
    google_drive.setup_interactive()  # walks through the OAuth dance

    # Every time after:
    drive = google_drive.connect()
    folder_id = google_drive.find_folder(drive, "Swing Shack Brand Assets")
    files = google_drive.list_files(drive, folder_id)
    for f in files:
        google_drive.download(drive, f, "data/brand-directory/swing-shack/images/")
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

# Defaults — overridden by env if present. We try the canonical OpenClaw
# credentials location first (the one the setup-portal uses), then fall
# back to the user-supplied env var.
_DEFAULT_CREDENTIALS_DIRS = [
    Path("/Users/fivefriday/.openclaw/workspace/credentials"),
    Path("/Users/fivefriday/.openclaw-instance2/workspace/credentials"),
    Path.home() / ".openclaw" / "workspace" / "credentials",
]


def _resolve_credentials_dir() -> Path:
    env_dir = os.environ.get("OPENCLAW_CREDENTIALS_DIR")
    if env_dir:
        return Path(env_dir)
    for p in _DEFAULT_CREDENTIALS_DIRS:
        if p.exists() or p.parent.exists():
            p.mkdir(parents=True, exist_ok=True)
            return p
    # Fallback to first default
    p = _DEFAULT_CREDENTIALS_DIRS[0]
    p.mkdir(parents=True, exist_ok=True)
    return p


CREDENTIALS_DIR = _resolve_credentials_dir()
OAUTH_CLIENT_PATH = Path(
    os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    or CREDENTIALS_DIR / "google-oauth-client.json"
)
DRIVE_TOKEN_PATH = Path(
    os.environ.get("GOOGLE_DRIVE_TOKEN")
    or CREDENTIALS_DIR / "google-drive-token.json"
)

# Scope = read-only Drive. Token will only ever read.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _load_client_secrets() -> dict[str, Any] | None:
    """Load the OAuth client secrets JSON (Desktop-app credentials)."""
    if not OAUTH_CLIENT_PATH.exists():
        return None
    try:
        with OAUTH_CLIENT_PATH.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _load_stored_token() -> dict[str, Any] | None:
    """Load the persisted refresh-token JSON (if any)."""
    if not DRIVE_TOKEN_PATH.exists():
        return None
    try:
        with DRIVE_TOKEN_PATH.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _save_token(token: dict[str, Any]) -> Path:
    """Persist the refresh token to disk with 0600 perms."""
    DRIVE_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DRIVE_TOKEN_PATH.open("w") as f:
        json.dump(token, f, indent=2)
    os.chmod(DRIVE_TOKEN_PATH, 0o600)
    return DRIVE_TOKEN_PATH


def connect():
    """Return an authenticated Google Drive API client.

    Returns None if no credentials are configured. Raises on auth failure.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_data = _load_stored_token()
    if not token_data:
        return None

    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(json.loads(creds.to_json()))
    elif not creds.valid:
        return None

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_folder(drive, name: str, parent_id: str | None = None) -> str | None:
    """Find a Drive folder by name. Returns folder_id or None."""
    query_parts = [
        f"name = '{name.replace(chr(39), chr(39) + chr(39))}'",
        "mimeType = 'application/vnd.google-apps.folder'",
        "trashed = false",
    ]
    if parent_id:
        query_parts.append(f"'{parent_id}' in parents")
    query = " and ".join(query_parts)

    resp = drive.files().list(q=query, fields="files(id, name)", pageSize=10).execute()
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def list_files(drive, folder_id: str) -> list[dict[str, Any]]:
    """List all files in a Drive folder (recursive). Returns file metadata."""
    files: list[dict[str, Any]] = []
    page_token = None
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
            pageSize=100,
            pageToken=page_token,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def download(drive, file_meta: dict[str, Any], dest_dir: str | Path) -> Path | None:
    """Download a single file to dest_dir. Returns the saved path or None."""
    import io
    from googleapiclient.http import MediaIoBaseDownload

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    file_id = file_meta["id"]
    name = file_meta["name"]
    safe_name = name.replace("/", "_").replace("..", "_")
    target = dest / safe_name

    # Skip if Google Workspace file (need export, not download)
    if file_meta.get("mimeType", "").startswith("application/vnd.google-apps."):
        return None

    request = drive.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    target.write_bytes(fh.getvalue())
    return target


def ingest_brand_folder(drive, folder_name: str, brand_id: str,
                       images_subdir: str = "images/originals") -> dict[str, Any]:
    """Ingest a brand's Drive folder into the brand-directory.

    Walks the folder, downloads image files into
    data/brand-directory/<brand_id>/<images_subdir>/, returns a manifest dict.

    Skips non-image files (logs them). Idempotent — won't re-download existing files.
    """
    folder_id = find_folder(drive, folder_name)
    if not folder_id:
        return {"ok": False, "error": f"folder not found: {folder_name}",
                "brand_id": brand_id, "downloaded": []}

    files = list_files(drive, folder_id)
    image_mimes = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}

    dest = Path(f"data/brand-directory/{brand_id}/{images_subdir}")
    dest.mkdir(parents=True, exist_ok=True)

    downloaded: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for f in files:
        if f.get("mimeType") not in image_mimes:
            skipped.append({"name": f["name"], "reason": "not an image",
                            "mime": f.get("mimeType")})
            continue
        safe_name = f["name"].replace("/", "_").replace("..", "_")
        target = dest / safe_name
        if target.exists() and target.stat().st_size == int(f.get("size", 0)):
            skipped.append({"name": f["name"], "reason": "already downloaded"})
            continue
        try:
            path = download(drive, f, dest)
            if path:
                downloaded.append({"name": f["name"], "path": str(path),
                                   "size": path.stat().st_size})
        except Exception as e:
            skipped.append({"name": f["name"], "reason": f"download failed: {e}"})

    return {
        "ok": True,
        "brand_id": brand_id,
        "folder_name": folder_name,
        "folder_id": folder_id,
        "total_files": len(files),
        "downloaded": downloaded,
        "skipped": skipped,
    }


# ─── OAuth dance helpers ──────────────────────────────────────────────
def oauth_instructions() -> str:
    """Plain-text steps the user follows to set up Drive access.

    Used by setup-portal. Returns nothing to do programmatically — the user
    has to touch Google Cloud Console once.
    """
    return """
Google Drive setup — one-time steps

1. Go to https://console.cloud.google.com
2. Sign in as clawdiavector@gmail.com (the account that owns the brand folders)
3. Create a project (or use existing) — name it e.g. 'campaign-os-drive'
4. APIs & Services → Library → search 'Google Drive API' → Enable
5. OAuth consent screen → External → app name 'Campaign OS' →
   scopes: drive.readonly → add clawdiavector@gmail.com as test user → Save
6. Credentials → Create Credentials → OAuth client ID → type 'Desktop app' →
   name 'Campaign OS Local' → Create
7. Download the JSON (the file will look like client_secret_XXXXX.json)
8. Upload it via the setup portal — NOT in chat
   (the portal URL is provided when you say "ready to set up Drive")

The setup portal will then walk you through Google sign-in.
The resulting refresh token is stored at:
   ~/.openclaw/workspace/credentials/google-drive-token.json
You only do the dance once. After that, the API refreshes silently.
""".strip()


def setup_interactive(port: int = 8765) -> dict[str, Any]:
    """Run the OAuth flow in a local browser, save the refresh token.

    This is the one-off setup. Opens a browser on http://localhost:<port>,
    redirects through Google's OAuth screen, saves the resulting token to
    DRIVE_TOKEN_PATH, and closes.

    Run this locally — don't expose the callback port publicly.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    client = _load_client_secrets()
    if not client:
        return {"ok": False, "error": f"client secrets not found at {OAUTH_CLIENT_PATH}",
                "instructions": oauth_instructions()}

    # InstalledAppFlow expects 'installed' or 'web' key
    if "installed" not in client and "web" not in client:
        return {"ok": False,
                "error": "client JSON is not 'installed' or 'web' type — did you download the right file?",
                "instructions": oauth_instructions()}

    flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_CLIENT_PATH), SCOPES)
    # run_local_server opens a browser on localhost:<port> for the redirect
    creds = flow.run_local_server(port=port, open_browser=True,
                                   prompt="consent", access_type="offline")
    saved = _save_token(json.loads(creds.to_json()))
    return {"ok": True, "token_saved": str(saved), "scopes": list(creds.scopes or [])}


def status() -> dict[str, Any]:
    """Return current Drive auth status — for the dashboard Brand surface."""
    has_client = OAUTH_CLIENT_PATH.exists()
    has_token = DRIVE_TOKEN_PATH.exists()
    drive = connect() if has_token else None
    return {
        "has_oauth_client": has_client,
        "has_token": has_token,
        "client_path": str(OAUTH_CLIENT_PATH),
        "token_path": str(DRIVE_TOKEN_PATH),
        "connected": drive is not None,
        "instructions": oauth_instructions(),
    }
