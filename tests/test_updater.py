import hashlib

import httpx
import pytest

from vox import updater


def github(release, files=None):
    files = files or {}

    def handler(request):
        url = str(request.url)
        if url == updater.API:
            return httpx.Response(200, json=release) if release else httpx.Response(404)
        return httpx.Response(200, content=files[url]) if url in files else httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def release(version, base="https://example.test/"):
    name = f"VoxSetup-{version}.exe"
    return {"tag_name": f"v{version}", "body": "What changed", "html_url": "https://example.test/r",
            "assets": [{"name": name, "browser_download_url": base + name},
                       {"name": name + ".sha256", "browser_download_url": base + name + ".sha256"}]}


def test_newer_release_is_offered(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "0.2.0")
    info = updater.check(github(release("0.10.1")))
    assert info["available"] and info["latest"] == "0.10.1"  # 0.10 is newer than 0.2
    assert info["installer"].endswith("VoxSetup-0.10.1.exe")


def test_same_or_older_release_is_not(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "0.2.0")
    assert not updater.check(github(release("0.2.0")))["available"]
    assert not updater.check(github(release("0.1.9")))["available"]
    assert not updater.check(github(None))["available"]  # no releases yet


def test_download_checks_the_checksum(monkeypatch, tmp_path):
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(updater, "__version__", "0.2.0")
    payload = b"installer bytes" * 1000
    rel = release("0.3.0")
    exe, sha = (a["browser_download_url"] for a in rel["assets"])

    good = github(rel, {exe: payload, sha: (hashlib.sha256(payload).hexdigest() + "  VoxSetup-0.3.0.exe\n").encode()})
    seen = []
    path = updater.download(updater.check(good), seen.append, good)
    assert path.read_bytes() == payload and seen[-1] == 1.0

    bad = github(rel, {exe: payload + b"tampered", sha: hashlib.sha256(payload).hexdigest().encode()})
    with pytest.raises(updater.UpdateError, match="checksum"):
        updater.download(updater.check(bad), None, bad)
    assert not (tmp_path / "VoxSetup-0.3.0.exe").exists()
