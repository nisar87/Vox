"""Update Vox from GitHub Releases.

Each release carries VoxSetup-<version>.exe and a .sha256 file. The updater
downloads both, refuses the installer unless its checksum matches, then runs
it silently. The installer closes the old Vox and starts the new one.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

from . import __version__

REPO = "nisar87/Vox"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": f"Vox/{__version__}"}


class UpdateError(Exception):
    pass


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3])


def installed_from_setup() -> bool:
    """True for the installed exe; false when running from source code."""
    return bool(getattr(sys, "frozen", False))


def check(client: httpx.Client | None = None) -> dict:
    """Ask GitHub for the newest release."""
    client = client or httpx.Client(timeout=15, follow_redirects=True)
    try:
        response = client.get(API, headers=HEADERS)
    except httpx.HTTPError as err:
        raise UpdateError(f"I couldn't reach GitHub to check for updates. ({type(err).__name__})")
    if response.status_code == 404:
        return {"current": __version__, "latest": __version__, "available": False,
                "message": "No releases have been published yet."}
    if response.status_code != 200:
        raise UpdateError(f"GitHub answered {response.status_code} when checking for updates.")
    release = response.json()
    latest = release.get("tag_name", "").lstrip("v")
    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    setup = next((n for n in assets if n.lower().startswith("voxsetup") and n.lower().endswith(".exe")), None)
    available = bool(latest) and version_tuple(latest) > version_tuple(__version__)
    return {
        "current": __version__,
        "latest": latest or __version__,
        "available": available,
        "notes": (release.get("body") or "").strip()[:1500],
        "page": release.get("html_url", PAGE),
        "installer": assets.get(setup) if setup else None,
        "checksum": assets.get(setup + ".sha256") if setup else None,
        "can_install": installed_from_setup() and bool(setup),
        "message": f"Version {latest} is available." if available else "You have the latest version.",
    }


def download(info: dict, on_progress=None, client: httpx.Client | None = None) -> Path:
    """Fetch the installer and verify it against the published checksum."""
    if not info.get("installer") or not info.get("checksum"):
        raise UpdateError("This release has no installer attached.")
    client = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        expected = client.get(info["checksum"], headers=HEADERS).text.split()[0].strip().lower()
        target = Path(tempfile.gettempdir()) / f"VoxSetup-{info['latest']}.exe"
        digest = hashlib.sha256()
        with client.stream("GET", info["installer"], headers=HEADERS) as response:
            if response.status_code != 200:
                raise UpdateError(f"The download failed ({response.status_code}).")
            total = int(response.headers.get("content-length") or 0)
            done = 0
            with open(target, "wb") as out:
                for chunk in response.iter_bytes(1 << 16):
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if on_progress and total:
                        on_progress(done / total)
    except (httpx.HTTPError, IndexError) as err:
        raise UpdateError(f"The download failed. ({type(err).__name__})")
    if digest.hexdigest() != expected:
        target.unlink(missing_ok=True)
        raise UpdateError("The download did not match its checksum, so I discarded it. Try again.")
    return target


def run_installer(path: Path) -> None:
    """Start the installer detached from Vox. The caller should then exit."""
    if os.name != "nt":
        raise UpdateError("Updates install on Windows only.")
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                     creationflags=flags, close_fds=True)
