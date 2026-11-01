"""Publish dashboard and Report Centre snapshots to the configured website API."""

import json
import mimetypes
import os
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from tkinter import TclError, messagebox
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


PUBLIC_WEBSITE_URL = "https://ammarabdullahi3042-sys.github.io/cleon-oil-gas"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_0sjd4-0ktuqR-lCY6j8fdA_qFCqBsJn"


def open_public_website(parent):
    try:
        opened = webbrowser.open(PUBLIC_WEBSITE_URL, new=2)
    except (OSError, webbrowser.Error) as error:
        messagebox.showerror(
            "Website Error", f"Could not open the CLEON website:\n{error}",
            parent=parent,
        )
        return
    if not opened:
        messagebox.showerror(
            "Website Error",
            "Could not open the CLEON website in a browser.",
            parent=parent,
        )


def _setting(name):
    """Read the current Windows user setting, even if the parent app is stale."""
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _kind = winreg.QueryValueEx(key, name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        except (ImportError, OSError):
            pass
    return os.environ.get(name, "").strip()


def configuration_error():
    base_url = _setting("CLEON_WEBSITE_API_URL").rstrip("/")
    token = _setting("CLEON_WEBSITE_PUBLISH_TOKEN")
    if not base_url or not token:
        return (
            "Website sync not configured (set CLEON_WEBSITE_API_URL and "
            "CLEON_WEBSITE_PUBLISH_TOKEN)."
        )
    parsed_url = urlparse(base_url)
    if (
        parsed_url.scheme not in ("https", "http")
        or not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
        or parsed_url.query
        or parsed_url.fragment
    ):
        return "Website sync requires a valid API base URL."
    if parsed_url.scheme != "https" and parsed_url.hostname not in (
        "localhost", "127.0.0.1", "::1"
    ):
        return "Website sync requires HTTPS except when using localhost."
    return None


def _publisher_request(path, data=None, headers=None, method=None, timeout=30):
    error = configuration_error()
    if error:
        raise ValueError(error)
    base_url = _setting("CLEON_WEBSITE_API_URL").rstrip("/")
    token = _setting("CLEON_WEBSITE_PUBLISH_TOKEN")
    request_headers = {
        "X-CLEON-Publish-Token": token,
        "apikey": SUPABASE_PUBLISHABLE_KEY,
    }
    if headers:
        request_headers.update(headers)
    request = Request(
        f"{base_url}{path}", data=data, headers=request_headers, method=method
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read(), response.headers
    except HTTPError as error:
        try:
            details = json.loads(error.read()).get("error")
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            details = None
        message = details or f"Website API returned HTTP {error.code}."
        raise RuntimeError(message) from error
    except (URLError, OSError, TimeoutError) as error:
        raise RuntimeError(
            f"Could not contact the website API: {error}") from error


def list_published_documents():
    last_error = None
    for attempt in range(2):
        try:
            body, _headers = _publisher_request(
                "/api/v1/documents", timeout=60
            )
            break
        except RuntimeError as error:
            last_error = error
            if attempt or "timed out" not in str(error).casefold():
                raise
            time.sleep(1)
    else:
        raise last_error
    try:
        result = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError(
            "Website API returned an invalid document list.") from error
    documents = result.get("documents")
    if not isinstance(documents, list):
        raise RuntimeError("Website API returned an invalid document list.")
    return documents


def upload_published_document(file_path):
    path = Path(file_path)
    filename = path.name
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("Choose a document smaller than 10 MB.")
    data = path.read_bytes()
    if not data:
        raise ValueError("Choose a non-empty document.")
    content_type = mimetypes.guess_type(filename)[0]
    if not content_type:
        raise ValueError("Choose a PDF, image, or Office document.")
    _body, _headers = _publisher_request(
        "/api/v1/documents",
        data=data,
        headers={
            "Content-Type": content_type,
            "X-Document-Name": quote(filename, safe=""),
        },
        method="POST",
    )


def download_published_document(document_id):
    body, _headers = _publisher_request(
        f"/api/v1/documents/{quote(document_id, safe='')}?download=1"
    )
    return body


def list_pending_station_entries():
    """Read routine entries submitted through the assigned-user portal."""
    body, _headers = _publisher_request("/api/v1/entries/pending", timeout=30)
    try:
        result = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError("Website API returned an invalid entry queue.") from error
    entries = result.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError("Website API returned an invalid entry queue.")
    return entries


def update_station_entry_result(entry_id, status, note=""):
    if status not in ("accepted", "rejected"):
        raise ValueError("Station entry result must be accepted or rejected.")
    body = json.dumps({"status": status, "note": str(note or "")[:500]}).encode("utf-8")
    _publisher_request(
        f"/api/v1/entries/{quote(str(entry_id), safe='')}/result",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
        timeout=30,
    )


def publish_snapshot(master, section, payload, on_result):
    """Publish a snapshot in the background and report its result on the UI thread."""
    error = configuration_error()
    if error:
        master.after(0, on_result, error, False)
        return
    base_url = _setting("CLEON_WEBSITE_API_URL").rstrip("/")
    token = _setting("CLEON_WEBSITE_PUBLISH_TOKEN")
    if section not in ("dashboard", "reports"):
        raise ValueError(f"Unsupported website snapshot section: {section}")
    snapshot = dict(payload)
    snapshot["published_at"] = datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    )
    try:
        body = json.dumps(
            snapshot, ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        master.after(
            0, on_result,
            f"Could not prepare {section} data for website sync: {error}",
            False,
        )
        return

    def send():
        request = Request(
            f"{base_url}/api/v1/publish/{section}",
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "X-CLEON-Publish-Token": token,
                "apikey": SUPABASE_PUBLISHABLE_KEY,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            print(f"Publishing {section}")
            print(f"URL: {base_url}/api/v1/publish/{section}")
            print(repr(body.decode("utf-8")[:500]))
            with urlopen(request, timeout=15) as response:
                if response.status not in (200, 201):
                    raise OSError(
                        f"Website API returned HTTP {response.status}."
                    )
                message = f"{section.title()} published to website."
                success = True
        except HTTPError as error:
            try:
                response_text = error.read().decode("utf-8")
                print("HTTP ERROR:", response_text)
            except Exception:
                pass

            message = (
                f"Website API rejected the {section} update "
                f"(HTTP {error.code})."
            )
            success = False
        except (URLError, OSError, TimeoutError) as error:
            message = f"Could not publish {section} to website: {error}"
            success = False

        try:
            master.after(0, on_result, message, success)
        except (RuntimeError, TclError):
            pass

    threading.Thread(target=send, daemon=True).start()
