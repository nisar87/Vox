"""Volume, power, screenshots, keyboard, PC status and the PowerShell escape hatch."""

from __future__ import annotations

import datetime
import os
import subprocess

from .. import paths
from . import apps
from .base import tool

NO_WINDOW = 0x08000000


def _keyboard():
    import keyboard

    return keyboard


def _endpoint_volume():
    import comtypes
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    comtypes.CoInitialize()
    speakers = AudioUtilities.GetSpeakers()
    if hasattr(speakers, "EndpointVolume"):
        return speakers.EndpointVolume
    iface = speakers.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
    return iface.QueryInterface(IAudioEndpointVolume)


@tool("set_volume", "Set, raise or lower the speaker volume, or mute it.",
      {"level": {"type": "number", "description": "Exact volume, 0 to 100."},
       "change": {"type": "number", "description": "Relative change, e.g. 10 or -10."},
       "mute": {"type": "boolean"}})
def set_volume(ctx, level=None, change=None, mute=None):
    try:
        volume = _endpoint_volume()
        if mute is not None:
            volume.SetMute(1 if mute else 0, None)
            return {"message": "Muted." if mute else "Unmuted."}
        current = volume.GetMasterVolumeLevelScalar() * 100
        target = max(0, min(100, level if level is not None else current + (change or 0)))
        volume.SetMasterVolumeLevelScalar(target / 100, None)
        volume.SetMute(0, None)
        return {"message": f"Volume is at {round(target)} percent."}
    except Exception:
        # No audio library: press the volume keys instead (each press is 2%).
        kb = _keyboard()
        if mute is not None:
            kb.send("volume mute")
            return {"message": "Toggled mute."}
        if level is not None:
            for _ in range(50):
                kb.send("volume down")
            for _ in range(round(level / 2)):
                kb.send("volume up")
            return {"message": f"Volume is at about {round(level)} percent."}
        steps = round((change or 10) / 2)
        for _ in range(abs(steps)):
            kb.send("volume up" if steps > 0 else "volume down")
        return {"message": "Volume up." if steps > 0 else "Volume down."}


@tool("media_key", "Play/pause or skip whatever media is playing.",
      {"action": {"type": "string", "enum": ["play_pause", "next", "previous"]}}, ("action",))
def media_key(ctx, action):
    key = {"play_pause": "play/pause media", "next": "next track", "previous": "previous track"}[action]
    _keyboard().send(key)
    return {"message": {"play_pause": "Done.", "next": "Next track.", "previous": "Previous track."}[action]}


_RISKY_POWER = {"shutdown", "restart", "sign_out"}


def _power_preview(args, ctx) -> str:
    return {"shutdown": "Shut down the PC?", "restart": "Restart the PC?",
            "sign_out": "Sign you out of Windows?"}.get(args.get("action"), "Go ahead?")


@tool("power", "Lock, sleep, shut down, restart or sign out; or cancel a pending shutdown.",
      {"action": {"type": "string",
                  "enum": ["lock", "sleep", "shutdown", "restart", "sign_out", "cancel_shutdown"]}},
      ("action",), confirm=lambda a, c: a.get("action") in _RISKY_POWER, preview=_power_preview)
def power(ctx, action):
    if os.name != "nt":
        return {"ok": False, "message": "Power control only works on Windows."}
    commands = {
        "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
        "shutdown": ["shutdown", "/s", "/t", "20"],
        "restart": ["shutdown", "/r", "/t", "20"],
        "sign_out": ["shutdown", "/l"],
        "cancel_shutdown": ["shutdown", "/a"],
    }
    subprocess.Popen(commands[action], creationflags=NO_WINDOW)
    spoken = {
        "lock": "Locked.", "sleep": "Going to sleep.",
        "shutdown": "Shutting down in 20 seconds. Say cancel shutdown to stop it.",
        "restart": "Restarting in 20 seconds. Say cancel shutdown to stop it.",
        "sign_out": "Signing out.", "cancel_shutdown": "Shutdown cancelled.",
    }
    return {"message": spoken[action]}


@tool("system_status", "CPU, memory, disk space, battery and the heaviest programs right now.", kind="info")
def system_status(ctx):
    import psutil

    memory = psutil.virtual_memory()
    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        disks.append({"drive": part.mountpoint, "free_gb": round(usage.free / 2**30, 1),
                      "total_gb": round(usage.total / 2**30, 1)})
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    heavy = sorted(psutil.process_iter(["name", "memory_info"]),
                   key=lambda p: -(p.info["memory_info"].rss if p.info["memory_info"] else 0))[:5]
    return {
        "message": "Here is the PC status.",
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_used_percent": memory.percent,
        "memory_free_gb": round(memory.available / 2**30, 1),
        "disks": disks,
        "battery_percent": battery.percent if battery else None,
        "plugged_in": battery.power_plugged if battery else None,
        "heaviest": [{"name": p.info["name"], "memory_mb": round(p.info["memory_info"].rss / 2**20)}
                     for p in heavy if p.info["memory_info"]],
    }


@tool("take_screenshot", "Save a screenshot of the screen to Pictures/Screenshots.")
def take_screenshot(ctx):
    from PIL import ImageGrab

    folder = paths.known_folder("pictures") / "Screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"Vox {datetime.datetime.now():%Y-%m-%d %H-%M-%S}.png"
    ImageGrab.grab(all_screens=True).save(target)
    return {"message": "Screenshot saved to Pictures, Screenshots.", "path": str(target)}


@tool("type_text", "Type text into whatever window is active.", {"text": {"type": "string"}}, ("text",))
def type_text(ctx, text):
    apps.wait_for_new_window(ctx)
    _keyboard().write(text, delay=0.005)
    return {"message": "Typed."}


@tool("start_dictation",
      "Start writing everything the user says into the active window until they say 'stop dictation'. "
      "To dictate into a program, call open_app first, then this.")
def start_dictation(ctx):
    start = ctx.hooks.get("start_dictation")
    if not start:
        return {"ok": False, "message": "Dictation needs the microphone, which isn't available here."}
    apps.wait_for_new_window(ctx)
    return start()


@tool("stop_dictation", "Stop writing what the user says.")
def stop_dictation(ctx):
    stop = ctx.hooks.get("stop_dictation")
    return stop() if stop else {"message": "Dictation is not running."}


@tool("press_keys", "Press a key or shortcut in the active window, e.g. 'ctrl+s', 'alt+tab', 'enter'.",
      {"keys": {"type": "string"}}, ("keys",))
def press_keys(ctx, keys):
    apps.wait_for_new_window(ctx)
    _keyboard().send(keys)
    return {"message": f"Pressed {keys}."}


def _shell_preview(args, ctx) -> str:
    return f"This needs a PowerShell command: {args.get('command', '')[:160]} Run it?"


@tool("run_powershell",
      "Run a PowerShell command and return its output. Use only when no other skill fits "
      "(settings, network, services, anything else Windows can do). Never use it to delete files.",
      {"command": {"type": "string"}}, ("command",), kind="info",
      confirm=lambda a, c: bool(c.config["confirm_shell"]), preview=_shell_preview)
def run_powershell(ctx, command):
    if os.name != "nt":
        return {"ok": False, "message": "PowerShell skills only work on Windows."}
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                          capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW)
    output = (done.stdout or "").strip()[:4000]
    error = (done.stderr or "").strip()[:1000]
    return {"ok": done.returncode == 0, "message": "Command finished." if done.returncode == 0 else "Command failed.",
            "output": output, "error": error}


@tool("undo_last", "Undo the last thing Vox changed on disk (moves, renames, new folders).")
def undo_last(ctx):
    return ctx.journal.undo()
