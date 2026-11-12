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


def test_old_installers_are_cleared_and_a_full_disk_is_explained(monkeypatch, tmp_path):
    import collections

    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    for version in ("0.3.1", "0.3.2", "0.3.3"):
        (tmp_path / f"VoxSetup-{version}.exe").write_bytes(b"x" * 10)
    (tmp_path / "something-else.exe").write_bytes(b"keep")
    assert updater.clean_old_installers() == 3
    assert [p.name for p in tmp_path.iterdir()] == ["something-else.exe"]

    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(updater.shutil, "disk_usage", lambda path: usage(500e9, 499.9e9, 100 * 1024 * 1024))
    with pytest.raises(updater.UpdateError, match="only 100 MB free"):
        updater.check_space()
    monkeypatch.setattr(updater.shutil, "disk_usage", lambda path: usage(500e9, 100e9, 400e9))
    updater.check_space()


def test_speech_is_converted_to_the_sound_cards_format():
    np = pytest.importorskip("numpy")
    from vox import voice

    mono = (np.sin(np.linspace(0, 100, 24000)) * 10000).astype("int16")  # one second at 24 kHz
    frames = voice.to_device_format(mono, 24000, 48000)
    assert frames.shape == (48000, 2) and frames.dtype == np.int16
    assert (frames[:, 0] == frames[:, 1]).all()
    assert voice.to_device_format(mono, 24000, 24000).shape == (24000, 2)
