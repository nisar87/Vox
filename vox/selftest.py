"""Check that this copy of Vox is complete and its skills work on this PC.

Run with:  Vox.exe --self-test report.json   (or  python -m vox --self-test report.json)
Used by the cloud build to prove the installer works before it is released.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
from pathlib import Path


def _imports(*modules):
    def check():
        for module in modules:
            __import__(module)
        return "loaded"
    return check


def _ui():
    from . import server

    size = server.UI.stat().st_size
    return f"window file present ({size} bytes)"


def _settings_folder():
    from . import config

    probe = config.home() / "selftest.tmp"
    probe.write_text("ok", "utf-8")
    probe.unlink()
    return str(config.home())


def _user_folders():
    from . import paths

    desktop, documents = paths.known_folder("desktop"), paths.known_folder("documents")
    if not (desktop.is_dir() or documents.is_dir()):
        raise RuntimeError(f"neither {desktop} nor {documents} exists")
    return f"desktop = {desktop}"


def _start_menu():
    from .tools import apps

    apps.build_index()
    if os.name == "nt" and not apps._index:
        raise RuntimeError("the Start menu returned no programs")
    found = apps.find_app("notepad")
    return f"{len(apps._index)} programs indexed; notepad -> {found[0] if found else 'not found'}"


def _file_skills():
    from . import journal
    from .tools import Context, files, run

    files.USE_CREATED_TIME = False  # the test file is seconds old; judge it by its back-dated times
    try:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old, new = root / "old.txt", root / "new.txt"
            old.write_text("x")
            new.write_text("x")
            stamp = time.time() - 40 * 86400
            os.utime(old, (stamp, stamp))
            ctx = Context({"browser": "default", "confirm_shell": True}, journal.Journal())
            ctx.journal.begin("self-test")
            result = run("move_matching", {"folder": str(root), "destination": "Stale", "unused_days": 20}, ctx)
            ctx.journal.commit()
            if not ((root / "Stale" / "old.txt").exists() and new.exists()):
                raise RuntimeError(f"move did not happen: {result}")
            undone = ctx.journal.undo()
            if not old.exists() or (root / "Stale").exists():
                raise RuntimeError(f"undo did not restore the file: {undone}")
    finally:
        files.USE_CREATED_TIME = True
    return "move and undo work"


def _instant_commands():
    from . import config, engine, journal, learning
    from .tools import web

    opened = []
    original, web.launch_url = web.launch_url, lambda url, browser="default": opened.append(url)
    try:
        eng = engine.Engine(config.Config(), journal.Journal(), learning.Memory())
        result = eng.handle("open youtube in chrome and search for self test")
    finally:
        web.launch_url = original
    if result["path"] != "instant" or not opened or "search_query=self+test" not in opened[0]:
        raise RuntimeError(f"unexpected result: {result}")
    return f"handled in {result['timings']['total_ms']} ms without AI"


def _server():
    import httpx
    import uvicorn

    from . import app as app_module
    from . import server

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    api = server.create(app_module.VoxApp())
    web = uvicorn.Server(uvicorn.Config(api, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=web.run, daemon=True).start()
    try:
        deadline = time.time() + 15
        while True:
            try:
                page = httpx.get(f"http://127.0.0.1:{port}/", timeout=2)
                break
            except httpx.HTTPError:
                if time.time() > deadline:
                    raise
                time.sleep(0.2)
        state = httpx.get(f"http://127.0.0.1:{port}/api/state", headers={"X-Vox-Token": api.state.token}, timeout=5)
        if page.status_code != 200 or state.status_code != 200 or "settings" not in state.json():
            raise RuntimeError(f"page {page.status_code}, state {state.status_code}")
    finally:
        web.should_exit = True
    return "window and API answer"


def _voices():
    from . import voice

    names = voice.Speaker({"speak": False, "voice": "", "speech_rate": 0}).voices()
    if not names:
        raise RuntimeError("Windows reported no voices")
    return f"{len(names)} voices: {names[0]}"


def _open_close_program():
    import psutil

    from .tools import Context, run

    ctx = Context({"browser": "default"}, None)

    def running():
        return any((p.info["name"] or "").lower() == "notepad.exe" for p in psutil.process_iter(["name"]))

    opened = run("open_app", {"name": "notepad"}, ctx)
    deadline = time.time() + 10
    while not running() and time.time() < deadline:
        time.sleep(0.3)
    if not running():
        raise RuntimeError(f"notepad did not start: {opened}")
    run("close_app", {"name": "notepad"}, ctx)
    deadline = time.time() + 8
    while running() and time.time() < deadline:
        time.sleep(0.3)
    return "opened Notepad" + (" and closed it" if not running() else " (it did not close in time)")


def _update_check():
    from . import updater

    info = updater.check()
    return f"current {info['current']}, latest {info['latest']}"


# (name, function, required)
CHECKS = [
    ("Window files", _ui, True),
    ("Settings folder", _settings_folder, True),
    ("Web server parts", _imports("fastapi", "uvicorn", "websockets", "httpx"), True),
    ("Window and API", _server, True),
    ("Instant commands", _instant_commands, True),
    ("File skills and undo", _file_skills, True),
    ("Start menu index", _start_menu, True),
    ("User folders", _user_folders, False),
    ("Speech recognition engine", _imports("faster_whisper", "ctranslate2", "numpy"), True),
    ("Microphone library", _imports("sounddevice"), True),
    ("Hotkey library", _imports("keyboard"), True),
    ("Volume control library", _imports("pycaw.pycaw", "comtypes"), True),
    ("Tray icon parts", _imports("pystray", "PIL.Image"), True),
    ("Recycle Bin support", _imports("send2trash"), True),
    ("Windows speech and COM parts", _imports("win32com.client", "pythoncom"), True),
    ("Windows voices", _voices, False),
    ("Open and close a program", _open_close_program, False),
    ("Update check", _update_check, False),
]


def run_all(report_path: str | None = None) -> int:
    from . import __version__

    # Work in a scratch folder so a self-test never touches real settings or memory.
    os.environ["VOX_HOME"] = tempfile.mkdtemp(prefix="vox-selftest-")
    results = []
    for name, check, required in CHECKS:
        started = time.perf_counter()
        try:
            detail, ok = str(check()), True
        except BaseException as err:  # includes import failures inside a frozen exe
            detail, ok = f"{type(err).__name__}: {err}", False
        results.append({"check": name, "ok": ok, "required": required, "detail": detail,
                        "ms": round((time.perf_counter() - started) * 1000)})
    failed = [r for r in results if r["required"] and not r["ok"]]
    report = {"version": __version__, "passed": not failed, "results": results}
    text = json.dumps(report, indent=2)
    if report_path:
        Path(report_path).write_text(text, "utf-8")
    else:
        print(text)
    return 1 if failed else 0
