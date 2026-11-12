"""Standby: listen in the background for "Hi Vox", and take dictation.

Everything here runs on the PC. Speech heard in standby is transcribed by the
on-PC model and thrown away unless it starts with the wake phrase, so nothing
said in the room is sent anywhere.

Standby goes quiet while another program is using the microphone (a Teams,
WhatsApp, Zoom or browser call), so Vox never reacts to, or talks over, a call.
"""

from __future__ import annotations

import difflib
import os
import re
import sys
import threading
import time

from . import voice

# What the speech model tends to write when it hears "Vox".
_NAME = r"(?:vox|vocs|voks|vax|vaux|wox|vocks|box|fox|fax|bucks|folks|walks|volks|vogue|pox|vocs)"
_GREETING = r"(?:hi|hey|hello|high|hay|hai|okay|ok|yo)"
# A greeting plus the name, or the exact name on its own, at the start of what was said.
WAKE = re.compile(rf"^\W*(?:{_GREETING}\W+{_NAME}|vox)\b[\s,.!?:;-]*", re.I)
STOP_DICTATION = re.compile(
    r"^\W*(?:(?:hi|hey|ok|okay)\W+)?(?:vox\W+)?(?:stop|end|finish|quit)\s+(?:the\s+)?(?:dictation|dictating|writing|typing)\W*$"
    r"|^\W*(?:hi|hey|ok|okay)?\W*vox\W+(?:stop|that's all|that is all|enough)\W*$", re.I)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def wake_variant(heard: str) -> str | None:
    """Reduce what the speech model heard for "Hi Vox" to a storable variant, if it is usable."""
    words = _words(heard)[:3]
    variant = " ".join(words)
    plain_greeting = re.fullmatch(_GREETING, variant or "", re.I)
    return variant if len(variant.replace(" ", "")) >= 4 and not plain_greeting else None


def split_wake(text: str, learned: str = "") -> tuple[bool, str]:
    """('Hi Vox, open notepad') -> (True, 'open notepad'). Not addressed to Vox -> (False, '').

    'learned' holds "|"-separated variants of how the speech model hears this
    particular user say the wake phrase (taught in Settings).
    """
    match = WAKE.match(text or "")
    if match:
        return True, text[match.end():].strip()
    words = _words(text)
    for variant in filter(None, (v.strip() for v in learned.split("|"))):
        target = variant.replace(" ", "")
        # The speech model words it a little differently each time, so compare loosely,
        # trying the first one, two and three words of what was heard.
        for count in (len(variant.split()), 1, 2, 3):
            lead = "".join(words[:count])
            if lead and difflib.SequenceMatcher(None, lead, target).ratio() >= 0.75:
                rest = re.sub(r"^\W*" + r"\W+".join(re.escape(w) for w in words[:count]) + r"\b[\s,.!?:;-]*", "",
                              text, count=1, flags=re.I)
                return True, rest.strip()
    return False, ""


def is_stop_dictation(text: str) -> bool:
    return bool(STOP_DICTATION.match(text or ""))


# ---------------------------------------------------------------- calls

_MIC_KEY = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
_STALE_AFTER = 12 * 3600  # ignore "in use" records older than this (left by a crashed app)


def _registry_mic_records():
    """Yield (app key, last start, last stop) for every app Windows has let use the microphone."""
    import winreg

    def walk(path):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                index = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, index)
                    except OSError:
                        break
                    index += 1
                    if name == "NonPackaged":
                        yield from walk(path + "\\" + name)
                        continue
                    try:
                        with winreg.OpenKey(key, name) as app:
                            start = winreg.QueryValueEx(app, "LastUsedTimeStart")[0]
                            stop = winreg.QueryValueEx(app, "LastUsedTimeStop")[0]
                        yield name, int(start), int(stop)
                    except OSError:
                        continue
        except OSError:
            return

    yield from walk(_MIC_KEY)


def _friendly(app_key: str) -> str:
    name = app_key.split("#")[-1]  # desktop apps are stored as a path with # for \
    name = re.sub(r"\.exe$", "", name, flags=re.I)
    name = name.split("_")[0].split(".")[-1]  # store apps: Publisher.App_hash
    return {"ms-teams": "Teams", "MSTeams": "Teams", "WhatsAppDesktop": "WhatsApp", "msedge": "Edge",
            "chrome": "Chrome"}.get(name, name)


def mic_users(records=None, own_exe: str | None = None, now: float | None = None) -> list[str]:
    """Names of other programs using the microphone right now (Windows only)."""
    if records is None:
        if os.name != "nt":
            return []
        records = _registry_mic_records()
    own = (own_exe or sys.executable).replace("\\", "#").lower()
    now = now or time.time()
    users = []
    for key, start, stop in records:
        if stop != 0 or start == 0 or key.lower() == own:
            continue
        started = start / 10_000_000 - 11_644_473_600  # Windows file time -> Unix time
        if now - started > _STALE_AFTER:
            continue
        users.append(_friendly(key))
    return users


# ---------------------------------------------------------------- the loop

class Standby:
    """Background listener. Owns the microphone only while Vox is otherwise idle."""

    def __init__(self, app) -> None:
        self.app = app
        self.interrupt = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._calls_checked, self._callers = 0.0, []

    def start(self) -> None:
        self._thread.start()

    def _on_call(self) -> list[str]:
        if not self.app.config["pause_on_calls"]:
            return []
        if time.time() - self._calls_checked > 2:
            self._calls_checked = time.time()
            try:
                self._callers = mic_users()
            except Exception:
                self._callers = []
        return self._callers

    def _loop(self) -> None:
        app, floor = self.app, []
        parts = None
        while True:
            try:
                wanted = app.config["standby"] or app.dictating
                if not wanted:
                    app.set_standby("off")
                    time.sleep(0.4)
                    continue
                parts = parts or voice.available()
                if not (parts["microphone"] and parts["local_stt"]):
                    app.set_standby("unavailable", "The microphone or on-PC speech model is missing.")
                    time.sleep(3)
                    continue
                if app.busy() or app.speaker.speaking.is_set():
                    time.sleep(0.1)
                    continue
                callers = self._on_call()
                if callers:
                    app.set_standby("call", callers[0])
                    time.sleep(1)
                    continue
                app.set_standby("dictating" if app.dictating else "ready")

                self.interrupt.clear()
                began = time.time()
                samples = voice.record(stop_event=self.interrupt, wait_for_speech=4.0, floor=floor,
                                       on_level=app.level if app.dictating else None,
                                       silence=float(app.config["patience"]))
                if samples is None or app.busy() or self.interrupt.is_set():
                    continue
                if app.speaker.last_spoke > began or self._on_call():
                    continue  # that was Vox's own voice, or a call just started
                # Same model and settings as "Teach Vox my Hi Vox", so taught variants match.
                text, no_speech = voice.transcribe_local(app.config["local_stt_model"], samples, app.WAKE_HINT)
                if not text or no_speech > 0.9:
                    continue
                if app.dictating:
                    app.dictate(text)
                    continue
                woke, rest = split_wake(text, app.config["wake_heard"])
                if woke:
                    app.wake(rest, samples)
                else:
                    app.overheard(text)
            except Exception as err:
                app.set_standby("unavailable", f"Standby stopped: {err}")
                time.sleep(5)
