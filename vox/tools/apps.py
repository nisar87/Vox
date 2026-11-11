"""Open and close programs by the name a person would say."""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import threading

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
    shell_open(target)
    return {"message": f"Opening {app.title()}."}


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
    matches = set()
    for proc in psutil.process_iter(["name"]):
        base = (proc.info["name"] or "").lower().removesuffix(".exe")
        if base and any(base == w or (len(w) > 3 and w in base) for w in wanted):
            matches.add(proc.info["name"])
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
