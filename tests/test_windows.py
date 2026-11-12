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
