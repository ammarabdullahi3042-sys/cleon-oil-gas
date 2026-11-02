"""Build the public static site and optionally configure its API base URL."""

import html
import os
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "website-build"
PAGES = (
    "index.html",
    "login.html",
    "dashboard.html",
    "reports.html",
    "profile.html",
    "pump-session.html",
    "fuel-receipt.html",
    "account-activity.html",
    "tank-dip.html",
)
META_PATTERN = re.compile(
    r'(<meta\s+name=["\']cleon-api-url["\']\s+content=["\'])'
    r'[^"\']*(["\'])',
    re.IGNORECASE,
)


def main():
    api_url = os.environ.get("CLEON_WEBSITE_API_URL", "").strip().rstrip("/")
    if api_url:
        parsed = urlparse(api_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/", "/functions/v1/cleon-portal")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "CLEON_WEBSITE_API_URL must be an HTTPS Supabase API origin or "
                "the /functions/v1/cleon-portal endpoint, without a query or fragment."
            )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    for page_name in PAGES:
        source_path = ROOT / page_name
        if not source_path.is_file():
            raise FileNotFoundError(f"Website page is missing: {source_path}.")
        source = source_path.read_text(encoding="utf-8")
        built, replacements = META_PATTERN.subn(
            lambda match: (
                match.group(1) + html.escape(api_url, quote=True) + match.group(2)
            ),
            source,
        )
        if replacements > 1:
            raise ValueError(
                f"Expected at most one cleon-api-url meta tag in {source_path.name}."
            )
        (OUTPUT / source_path.name).write_text(built, encoding="utf-8")
    for asset in ("portal.css", "portal.js"):
        shutil.copyfile(ROOT / asset, OUTPUT / asset)
    print(
        f"Built {len(PAGES)} website page(s); API URL "
        f"{'configured' if api_url else 'not configured'}."
    )


if __name__ == "__main__":
    main()
