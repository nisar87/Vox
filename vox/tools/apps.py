"""Open and close programs by the name a person would say."""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import threading
import time

from .base import tool

# Spoken name -> name as it appears in the Start menu.
ALIASES = {
    "chrome": "google chrome",
    "edge": "microsoft edge",
    "vs code": "visual studio code",
    "vscode": "visual studio code",
    "code": "visual studio code",
    "explorer": "file explorer",
    "files": "file explorer",
    "cmd": "command prompt",
    "calc": "calculator",
    "word": "word",
    "excel": "excel",
    "powerpoint": "powerpoint",
    "terminal": "terminal",
}
# Fallback commands that work even when the Start menu index has no entry.
COMMANDS = {
    "google chrome": "chrome", "microsoft edge": "msedge", "firefox": "firefox",
    "notepad": "notepad", "calculator": "calc", "paint": "mspaint",
    "file explorer": "explorer", "command prompt": "cmd", "powershell": "powershell",
    "task manager": "taskmgr", "settings": "ms-settings:", "control panel": "control",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "terminal": "wt", "snipping tool": "snippingtool", "visual studio code": "code",
}

_index: dict[str, str] = {}  # lowercase Start-menu name -> AppID
_index_ready = threading.Event()


def _clean(name: str) -> str:
    name = re.sub(r"\b(the|app|application|program)\b", " ", name.lower())
    name = re.sub(r"\s*\bplus\s+plus\b", "++", name)  # "notepad plus plus"
    return re.sub(r"\s+", " ", name).strip(" .")


def build_index() -> None:
    """Read the Start menu once (about a second) so later lookups are instant."""
    global _index
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=20, creationflags=0x08000000,
            ).stdout
            rows = json.loads(out or "[]")
            rows = [rows] if isinstance(rows, dict) else rows
            _index = {r["Name"].lower(): r["AppID"] for r in rows if r.get("Name") and r.get("AppID")}
    except Exception:
        _index = {}
    finally:
        _index_ready.set()


def app_names() -> list[str]:
    return sorted(set(_index) | set(COMMANDS))


def find_app(spoken: str) -> tuple[str, str, bool] | None:
    """Return (name, launch target, confident) or None.

    'confident' is true for exact, alias and clear prefix matches; the instant
    router only acts on confident matches and lets the AI handle the rest.
    """
    _index_ready.wait(timeout=3)
    name = _clean(spoken)
    if not name:
        return None
    name = ALIASES.get(name, name)

    def target(found: str) -> str:
        return ("appid:" + _index[found]) if found in _index else ("cmd:" + COMMANDS[found])

    names = app_names()
    if name in names:
        return name, target(name), True
    words = [n for n in names if name in n.split() or n.startswith(name + " ") or n.endswith(" " + name)]
    if len(words) == 1:
        return words[0], target(words[0]), True
    if words:
        best = min(words, key=len)
        return best, target(best), False
    close = difflib.get_close_matches(name, names, n=1, cutoff=0.8)
    if close:
        return close[0], target(close[0]), False
    return None


def foreground_window() -> int:
    try:
        import ctypes

        return int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return 0


def _top_windows() -> list[tuple[int, int, str]]:
    """(window handle, process id, title) for every visible titled window."""
    import ctypes

    user32, found = ctypes.windll.user32, []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(ctypes.c_void_p(hwnd), title, 512)
            found.append((int(hwnd), pid.value, title.value))
        return True

    user32.EnumWindows(visit, 0)
    return found


def find_window(name: str) -> int:
    """Handle of an open window belonging to the named program, or 0."""
    if os.name != "nt":
        return 0
    import psutil

    wanted = _process_names(name)
    spoken = ALIASES.get(_clean(name), _clean(name))
    by_title = 0
    for hwnd, pid, title in _top_windows():
        try:
            exe = psutil.Process(pid).name().lower().removesuffix(".exe")
        except Exception:
            continue
        if any(exe == w or (len(w) > 3 and w in exe) for w in wanted):
            return hwnd
        if not by_title and spoken and spoken in title.lower() and exe not in ("vox", "msedge", "chrome", "firefox"):
            by_title = hwnd  # store apps run inside a shared host process; go by the title
    return by_title


def bring_to_front(hwnd: int) -> bool:
    """Make a window the active one. Windows resists this from background programs, so try harder."""
    import ctypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    handle = ctypes.c_void_p(hwnd)
    if user32.IsIconic(handle):
        user32.ShowWindow(handle, 9)  # restore
    me = kernel32.GetCurrentThreadId()
    front = user32.GetWindowThreadProcessId(ctypes.c_void_p(user32.GetForegroundWindow()), None)
    target = user32.GetWindowThreadProcessId(handle, None)
    for other in {front, target} - {me, 0}:
        user32.AttachThreadInput(me, other, True)
    user32.BringWindowToTop(handle)
    user32.SetForegroundWindow(handle)
    for other in {front, target} - {me, 0}:
        user32.AttachThreadInput(me, other, False)
    if foreground_window() != hwnd:  # last resort: minimise and restore, which activates it
        user32.ShowWindow(handle, 6)
        user32.ShowWindow(handle, 9)
        time.sleep(0.2)
    return foreground_window() == hwnd


def focus_app(name: str, timeout: float = 8.0) -> bool:
    """Wait for the program's window to exist and make it active, ready for typing."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = find_window(name)
        if hwnd:
            ok = bring_to_front(hwnd)
            time.sleep(0.35)  # let it take keyboard focus
            return ok
        time.sleep(0.15)
    return False


def wait_for_new_window(ctx) -> None:
    """After open_app, make sure that program has the keyboard before anything is typed."""
    if ctx.launch and time.time() - ctx.launch[0] < 15:
        focus_app(ctx.launch[1])
    ctx.launch = None


def shell_open(target: str) -> None:
    """Launch an 'appid:' or 'cmd:' target. Replaced in tests."""
    kind, _, value = target.partition(":")
    if os.name != "nt":
        raise OSError("Opening programs only works on Windows.")
    if kind == "appid":
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{value}"])
    else:
        subprocess.Popen(["cmd", "/c", "start", "", value], creationflags=0x08000000)


@tool("open_app", "Open a program installed on this PC.",
      {"name": {"type": "string", "description": "Program name, e.g. 'chrome', 'notepad', 'excel'."}}, ("name",))
def open_app(ctx, name):
    if _clean(name) in ("browser", "web browser"):
        name = ctx.config["browser"] if ctx.config["browser"] != "default" else "edge"
    found = find_app(name)
    if not found:
        return {"ok": False, "message": f"I couldn't find a program called {name}."}
    app, target, _ = found
    ctx.launch = (time.time(), app)
    shell_open(target)
    return {"message": f"Opening {app.title()}."}


@tool("switch_to_app", "Bring an already open program's window to the front.",
      {"name": {"type": "string"}}, ("name",))
def switch_to_app(ctx, name):
    found = find_app(name)
    app = found[0] if found else name
    if not focus_app(app, timeout=1.5):
        return {"ok": False, "message": f"{app.title()} doesn't have a window open."}
    return {"message": f"Switched to {app.title()}."}


def _process_names(spoken: str) -> set[str]:
    name = _clean(spoken)
    full = ALIASES.get(name, name)
    wanted = {name.replace(" ", ""), full.replace(" ", "")}
    if full in COMMANDS:
        wanted.add(COMMANDS[full].rstrip(":"))
    return {w for w in wanted if w}


@tool("close_app", "Close a running program. It is asked to close, so unsaved work can still be saved.",
      {"name": {"type": "string"}}, ("name",))
def close_app(ctx, name):
    import psutil

    wanted = _process_names(name)

    def running() -> set:
        found = set()
        for proc in psutil.process_iter(["name"]):
            base = (proc.info["name"] or "").lower().removesuffix(".exe")
            if base and any(base == w or (len(w) > 3 and w in base) for w in wanted):
                found.add(proc.info["name"])
        return found

    matches = running()
    # "Open the calculator and then close it": give a program that was just started time to appear.
    deadline = time.time() + (6 if ctx.launch and time.time() - ctx.launch[0] < 10 else 0)
    while not matches and time.time() < deadline:
        time.sleep(0.3)
        matches = running()
    if matches and deadline:
        time.sleep(1.0)  # let it finish starting, or it ignores the request to close
    if not matches:
        return {"ok": False, "message": f"{name} doesn't seem to be running."}
    for image in matches:
        if os.name == "nt":
            subprocess.run(["taskkill", "/IM", image], capture_output=True, creationflags=0x08000000)
        else:
            subprocess.run(["pkill", "-x", image], capture_output=True)
    return {"message": f"Closing {name}."}


@tool("running_apps", "List the programs currently running, with memory use.", kind="info")
def running_apps(ctx):
    import psutil

    totals: dict[str, float] = {}
    for proc in psutil.process_iter(["name", "memory_info"]):
        if proc.info["name"] and proc.info["memory_info"]:
            totals[proc.info["name"]] = totals.get(proc.info["name"], 0) + proc.info["memory_info"].rss
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:25]
    return {"message": f"{len(totals)} programs are running.",
            "programs": [{"name": n, "memory_mb": round(m / 1048576)} for n, m in top]}
