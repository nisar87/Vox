"""Wires the pieces together: hotkey -> listen -> understand -> act -> speak."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections import deque

from . import config as config_module
from . import engine, journal, learning, llm, updater, voice
from .tools import apps

WHISPER_HINT = "Vox, open Chrome, search YouTube, Notepad, desktop, downloads folder, volume up."


class Bus:
    """Pushes live events from worker threads to every open window."""

    def __init__(self) -> None:
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self._lock = threading.Lock()

    def subscribe(self, loop, q) -> None:
        with self._lock:
            self._subscribers.add((loop, q))

    def unsubscribe(self, loop, q) -> None:
        with self._lock:
            self._subscribers.discard((loop, q))

    def publish(self, kind: str, **data) -> None:
        event = {"type": kind, **data}
        with self._lock:
            targets = list(self._subscribers)
        for loop, q in targets:
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:
                pass  # that window's loop has closed


class VoxApp:
    def __init__(self) -> None:
        self.config = config_module.Config()
        self.journal = journal.Journal()
        self.memory = learning.Memory()
        self.engine = engine.Engine(self.config, self.journal, self.memory)
        self.update: dict = {"current": updater.__version__, "available": False, "message": "", "progress": None}
        self.bus = Bus()
        self.speaker = voice.Speaker(self.config)
        self.hotkey = voice.Hotkey()
        self.history: deque[dict] = deque(maxlen=50)
        self.state = "idle"
        self.notice = ""
        self._busy = threading.Lock()
        self._release = threading.Event()

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        threading.Thread(target=apps.build_index, daemon=True).start()
        threading.Thread(target=llm.warm_up, args=(self.config,), daemon=True).start()
        self.preload_speech_model()
        self.bind_hotkey()
        if self.config["auto_update"]:
            threading.Thread(target=self.check_update, daemon=True).start()

    # ------------------------------------------------------------ updates

    def check_update(self) -> dict:
        try:
            self.update = {**updater.check(), "progress": None}
        except updater.UpdateError as err:
            self.update = {**self.update, "available": False, "message": str(err)}
        self.bus.publish("update", update=self.update)
        return self.update

    def install_update(self) -> dict:
        """Download, verify and launch the installer, then close this copy of Vox."""
        info = self.update if self.update.get("available") else self.check_update()
        if not info.get("available"):
            return {"ok": False, "message": info.get("message") or "You have the latest version."}
        if not info.get("can_install"):
            return {"ok": False, "message": "This copy runs from source code. Update it with: git pull"}

        def progress(fraction: float) -> None:
            self.update["progress"] = round(fraction, 2)
            self.bus.publish("update", update=self.update)

        try:
            installer = updater.download(info, progress)
            updater.run_installer(installer)
        except updater.UpdateError as err:
            self.update["progress"] = None
            return {"ok": False, "message": str(err)}
        threading.Timer(1.0, lambda: os._exit(0)).start()
        return {"ok": True, "message": "Installing the update. Vox will restart in a moment."}

    def preload_speech_model(self) -> None:
        if self.config["stt"] != "local" or not voice.available()["local_stt"]:
            return

        def load():
            try:
                voice.load_local_model(self.config["local_stt_model"])
            except Exception as err:
                self.set_notice(f"The on-PC speech model could not load: {err}")

        threading.Thread(target=load, daemon=True).start()

    def bind_hotkey(self) -> None:
        hold = self.config["listen_mode"] == "hold"
        error = self.hotkey.bind(self.config["hotkey"], self.listen, self._release.set if hold else None)
        if error:
            self.set_notice(error)

    def apply_settings(self, changes: dict) -> None:
        before = dict(self.config.data)
        self.config.update(changes)
        if (before["hotkey"], before["listen_mode"]) != (self.config["hotkey"], self.config["listen_mode"]):
            self.bind_hotkey()
        if (before["stt"], before["local_stt_model"]) != (self.config["stt"], self.config["local_stt_model"]):
            self.preload_speech_model()

    # ------------------------------------------------------------ state

    def set_state(self, state: str) -> None:
        self.state = state
        self.bus.publish("state", state=state)

    def set_notice(self, text: str) -> None:
        self.notice = text
        self.bus.publish("notice", text=text)

    # ------------------------------------------------------------ commands

    def run_text(self, text: str, stt_ms: int = 0, spoken: bool = False) -> dict:
        self.set_state("working")
        try:
            result = self.engine.handle(text)
        finally:
            self.set_state("idle")
        result["timings"]["stt_ms"] = stt_ms
        result["timings"]["total_ms"] += stt_ms
        result["spoken"] = spoken
        result["at"] = time.time()
        self.history.appendleft(result)
        self.bus.publish("result", result=result)
        self.speaker.say(result["reply"])
        return result

    def undo(self) -> dict:
        result = self.engine.undo()
        self.bus.publish("undone", message=result["message"], can_undo=self.journal.can_undo())
        self.speaker.say(result["message"])
        return result

    def listen(self) -> None:
        """Start one voice turn (hotkey or the window's button). Ignored while busy."""
        if not self._busy.acquire(blocking=False):
            return
        threading.Thread(target=self._voice_turn, daemon=True).start()

    def _voice_turn(self) -> None:
        try:
            self.speaker.stop()
            self._release.clear()
            hold = self.config["listen_mode"] == "hold"
            self.set_state("listening")
            samples = voice.record(
                on_level=lambda level: self.bus.publish("level", level=round(level, 3)),
                stop_event=self._release if hold else None, hold=hold)
            if samples is None:
                self.set_state("idle")
                self.set_notice("I didn't hear anything. Press the hotkey and speak.")
                return
            self.set_state("working")
            started = time.perf_counter()
            text = voice.transcribe(self.config, samples, WHISPER_HINT)
            stt_ms = round((time.perf_counter() - started) * 1000)
            if not text:
                self.set_state("idle")
                self.set_notice("I couldn't make out any words.")
                return
            self.run_text(text, stt_ms=stt_ms, spoken=True)
        except Exception as err:
            self.set_state("idle")
            self.set_notice(f"Listening failed: {err}")
        finally:
            self._busy.release()

    # ------------------------------------------------------------ for the UI

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "notice": self.notice,
            "settings": self.config.public(),
            "parts": voice.available(),
            "ai_ready": llm.ready(self.config),
            "pending": self.engine.pending is not None,
            "can_undo": self.journal.can_undo(),
            "history": list(self.history),
            "update": self.update,
            "learned": self.memory.listing(),
        }
