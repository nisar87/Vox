"""Checks that only mean something on a real Windows machine (run in the cloud build)."""

import os
import time

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows only")


def test_real_user_folders_resolve():
    from vox import paths

    desktop = paths._windows_folder(paths._GUIDS["desktop"])
    downloads = paths._windows_folder(paths._GUIDS["downloads"])
    assert desktop is not None and downloads is not None
    assert "downloads" in str(downloads).lower()


def test_start_menu_index_finds_real_programs():
    from vox.tools import apps

    apps.build_index()
    assert len(apps._index) > 5
    assert apps.find_app("notepad") is not None


def test_open_and_close_a_real_program():
    import psutil

    from vox.tools import Context, apps, run

    apps.build_index()
    ctx = Context({"browser": "default"}, None)

    def running():
        return any((p.info["name"] or "").lower() == "notepad.exe" for p in psutil.process_iter(["name"]))

    assert run("open_app", {"name": "notepad"}, ctx)["ok"]
    deadline = time.time() + 15
    while not running() and time.time() < deadline:
        time.sleep(0.3)
    assert running(), "Notepad did not start"
    assert run("close_app", {"name": "notepad"}, ctx)["ok"]
    deadline = time.time() + 10
    while running() and time.time() < deadline:
        time.sleep(0.3)
    assert not running(), "Notepad did not close"


def test_system_status_reads_this_pc():
    from vox.tools import Context, run

    status = run("system_status", {}, Context({}, None))
    assert status["ok"] and status["disks"] and status["memory_free_gb"] > 0


def test_powershell_skill_runs():
    from vox.tools import Context, run

    result = run("run_powershell", {"command": "Write-Output (2+3)"}, Context({"confirm_shell": True}, None))
    assert result["ok"] and result["output"] == "5"


def test_write_into_a_real_program_and_read_it_back():
    """Open Notepad, bring it forward, write text, then copy it back out to prove it landed there."""
    import psutil
    import win32clipboard as clip

    from vox.tools import Context, apps, run

    apps.build_index()
    ctx = Context({"browser": "default"}, None)
    text = "Education opens doors. Reading every day builds knowledge, and practice turns knowledge into skill."
    try:
        result = run("write_in_app", {"app": "notepad", "text": text, "new_document": False}, ctx)
        assert result["ok"], result
        assert apps.foreground_window() == apps.find_window("notepad"), "Notepad is not the active window"

        import keyboard

        time.sleep(0.5)
        keyboard.send("ctrl+a")
        time.sleep(0.2)
        keyboard.send("ctrl+c")
        time.sleep(0.5)
        clip.OpenClipboard()
        try:
            copied = clip.GetClipboardData(clip.CF_UNICODETEXT)
        finally:
            clip.CloseClipboard()
        assert text in copied, f"Notepad contains {copied!r}"
    finally:
        for proc in psutil.process_iter(["name"]):
            if (proc.info["name"] or "").lower() == "notepad.exe":
                proc.kill()


def test_close_waits_for_a_program_that_was_just_opened():
    """'Open X and then close it' used to fail because X had not started yet."""
    import psutil

    from vox.tools import Context, apps, run

    apps.build_index()
    ctx = Context({"browser": "default"}, None)
    assert run("open_app", {"name": "notepad"}, ctx)["ok"]
    closed = run("close_app", {"name": "notepad"}, ctx)  # immediately, no waiting in the test
    assert closed["ok"], closed
    deadline = time.time() + 10
    alive = lambda: any((p.info["name"] or "").lower() == "notepad.exe" for p in psutil.process_iter(["name"]))
    while alive() and time.time() < deadline:
        time.sleep(0.3)
    assert not alive(), "Notepad is still open"
