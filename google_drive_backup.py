"""Optional Google Drive backup and restore for CLEON station databases."""

import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app_settings import backup_path, get_active_station_id


SCOPES = ["https://www.googleapis.com/auth/drive.file"]
USER_DATA_DIR = Path.home() / "AppData" / "Roaming" / "CLEON ERP"
CLIENT_FILE = USER_DATA_DIR / "google_oauth_client.json"
TOKEN_FILE = USER_DATA_DIR / "google_drive_token.json"
DRIVE_FOLDER = "CLEON ERP Backups"


class GoogleDriveSetupError(RuntimeError):
    pass


def _dependencies():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    except ImportError as error:
        raise GoogleDriveSetupError(
            "Google Drive support is not installed. Open the Version3 terminal and run: "
            "python -m pip install -r requirements.txt"
        ) from error
    return Request, Credentials, InstalledAppFlow, build, MediaFileUpload, MediaIoBaseDownload


def connect_google_drive(oauth_client_json):
    """Save the user's desktop OAuth client and authorize their Drive account."""
    Request, Credentials, InstalledAppFlow, build, _Upload, _Download = _dependencies()
    source = Path(oauth_client_json).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("Select the OAuth client JSON downloaded from Google Cloud.")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GoogleDriveSetupError("The selected OAuth JSON file is not valid JSON.") from error
    if not any(key in data for key in ("installed", "web")):
        raise GoogleDriveSetupError(
            "Use the OAuth client JSON for a Desktop app from Google Cloud Console."
        )

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, CLIENT_FILE)
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    credentials = flow.run_local_server(port=0, open_browser=True)
    TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    # Confirm Drive accepts the new token before reporting success.
    build("drive", "v3", credentials=credentials, cache_discovery=False).about().get(
        fields="user(emailAddress)"
    ).execute()
    return True


def disconnect_google_drive():
    """Remove CLEON's local OAuth token. This does not delete Drive backups."""
    TOKEN_FILE.unlink(missing_ok=True)


def _service():
    Request, Credentials, InstalledAppFlow, build, _Upload, _Download = _dependencies()
    if not TOKEN_FILE.is_file() or not CLIENT_FILE.is_file():
        raise GoogleDriveSetupError("Connect a Google Drive account first.")
    credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    if not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
        credentials = flow.run_local_server(port=0, open_browser=True)
        TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _drive_folder(service):
    rows = service.files().list(
        q=("name='CLEON ERP Backups' and "
           "mimeType='application/vnd.google-apps.folder' and trashed=false"),
        spaces="drive", fields="files(id,name)", pageSize=100,
    ).execute().get("files", [])
    if rows:
        return rows[0]["id"]
    return service.files().create(
        body={"name": DRIVE_FOLDER, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()["id"]


def _station_prefix():
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", get_active_station_id()).strip("_")
    return f"CLEON_{slug or 'station'}_"


def _make_snapshot(database):
    source_path = Path(database).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Station database not found: {source_path}")
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{_station_prefix()}{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    snapshot = USER_DATA_DIR / filename
    with sqlite3.connect(str(source_path), timeout=20) as source:
        with sqlite3.connect(str(snapshot), timeout=20) as target:
            source.backup(target)
    # The current legacy login schema stores passwords as text. Redact those
    # fields in the cloud copy; restoring preserves this computer's login table.
    with sqlite3.connect(str(snapshot), timeout=20) as safe_copy:
        has_users = safe_copy.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if has_users:
            safe_copy.execute(
                "UPDATE users SET password='[LOCAL LOGIN PASSWORD REDACTED]'"
            )
    return snapshot


def upload_station_backup(database):
    """Upload a consistent, point-in-time database copy to the user's Drive."""
    _Request, _Credentials, _Flow, build, MediaFileUpload, _Download = _dependencies()
    service = _service()
    folder_id = _drive_folder(service)
    snapshot = _make_snapshot(database)
    metadata = {"name": snapshot.name, "parents": [folder_id]}
    media = MediaFileUpload(str(snapshot), mimetype="application/x-sqlite3", resumable=True)
    request = service.files().create(
        body=metadata, media_body=media, fields="id,name,createdTime"
    )
    created = None
    while created is None:
        _status, created = request.next_chunk()
    return created


def _latest_station_backup(service):
    folder_id = _drive_folder(service)
    prefix = _station_prefix()
    results = service.files().list(
        q=f"'{folder_id}' in parents and name contains '{prefix}' and trashed=false",
        spaces="drive", orderBy="createdTime desc",
        fields="files(id,name,createdTime)", pageSize=100,
    ).execute().get("files", [])
    if not results:
        raise FileNotFoundError("No CLEON backup for this station was found in Google Drive.")
    return results[0]


def restore_latest_station_backup(database):
    """Download the newest station backup and restore it with a local safety copy."""
    _Request, _Credentials, _Flow, build, _Upload, MediaIoBaseDownload = _dependencies()
    service = _service()
    remote = _latest_station_backup(service)
    with sqlite3.connect(str(Path(database).resolve()), timeout=15) as current:
        has_users = current.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        local_users = current.execute(
            "SELECT id,username,password,role FROM users ORDER BY id"
        ).fetchall() if has_users else []
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = USER_DATA_DIR / f"download_{remote['name']}"
    request = service.files().get_media(fileId=remote["id"])
    with downloaded.open("wb") as output:
        downloader = MediaIoBaseDownload(output, request)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
    try:
        with sqlite3.connect(str(downloaded), timeout=15) as check:
            result = check.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise sqlite3.DatabaseError("The downloaded Drive backup did not pass its integrity check.")
        local_backup = backup_path(database)
        local_backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(downloaded, local_backup)
        from app_settings import restore_last_backup
        safety_copy = restore_last_backup(database)
        if local_users:
            with sqlite3.connect(str(Path(database).resolve()), timeout=15) as restored:
                restored.execute("DELETE FROM users")
                restored.executemany(
                    "INSERT INTO users(id,username,password,role) VALUES (?,?,?,?)",
                    local_users,
                )
        return remote["name"], safety_copy
    finally:
        downloaded.unlink(missing_ok=True)


def google_drive_connected():
    return TOKEN_FILE.is_file() and CLIENT_FILE.is_file()
