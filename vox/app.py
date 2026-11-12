"""Wires the pieces together: hotkey -> listen -> understand -> act -> speak."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections import deque

from . import config as config_module
from . import engine, journal, learning, llm, standby, updater, voice
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
    WAKE_HINT = WHISPER_HINT  # what the on-PC model is told to expect, for standby and teaching alike

    def __init__(self) -> None:
        self.config = config_module.Config()
        self.journal = journal.Journal()
        self.memory = learning.Memory()
        self.engine = engine.Engine(self.config, self.journal, self.memory)
        self.update: dict = {"current": updater.__version__, "available": False, "message": "", "progress": None}
        self.bus = Bus()
        self.speaker = voice.Speaker(self.config, on_problem=self.set_notice)
        self.hotkey = voice.Hotkey()
        self.history: deque[dict] = deque(maxlen=50)
        self.state = "idle"
        self.notice = ""
        self._busy = threading.Lock()
        self._release = threading.Event()
        self.dictating = False
        self.heard_log: deque[dict] = deque(maxlen=10)  # what standby heard and ignored, for diagnosis
        self.standby_state = {"mode": "off", "detail": ""}
        self.standby = standby.Standby(self)
        self.engine.ctx.hooks.update(start_dictation=self.start_dictation, stop_dictation=self.stop_dictation)

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        threading.Thread(target=apps.build_index, daemon=True).start()
        threading.Thread(target=llm.warm_up, args=(self.config,), daemon=True).start()
        self.preload_speech_model()
        self.bind_hotkey()
        self.standby.start()
        threading.Thread(target=self._warm_voice, daemon=True).start()
        if self.config["auto_update"]:
            threading.Thread(target=self.check_update, daemon=True).start()

    def _warm_voice(self) -> None:
        """Fetch the natural voice for the sentences Vox says most, so they play instantly."""
        if self.config["voice_engine"] != "natural" or not self.config["speak"] or not llm.ready(self.config):
            return
        for sentence in (self.greeting(), "Go ahead.", "Okay, cancelled.", "Dictation stopped.", "You're welcome."):
            try:
                voice.natural_audio(self.config, sentence)
            except Exception:
                return  # the first real sentence will report the problem

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
        """Load the on-PC speech model in the background (downloading it the first time)."""
        needed = self.config.stt_engine() == "local" or self.config["standby"]
        if not needed or not voice.available()["local_stt"]:
            return

        def load():
            name = self.config["local_stt_model"]
            downloading = not voice.model_downloaded(name)
            if downloading:
                self.set_notice("Downloading the speech model. This happens once and takes a minute or two.")
            try:
                voice.load_local_model(name)
                if downloading:
                    self.set_notice("")
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
        self.speaker._natural_failed = False  # a changed key or voice deserves another try
        keys = ("stt", "local_stt_model", "standby")
        if [before[k] for k in keys] != [self.config[k] for k in keys]:
            self.preload_speech_model()
        if before["standby"] and not self.config["standby"]:
            self.standby.interrupt.set()

    # ------------------------------------------------------------ state

    def set_state(self, state: str) -> None:
        self.state = state
        self.bus.publish("state", state=state)

    def set_notice(self, text: str) -> None:
        self.notice = text
        self.bus.publish("notice", text=text)

    def set_standby(self, mode: str, detail: str = "") -> None:
        state = {"mode": mode, "detail": detail}
        if state != self.standby_state:
            self.standby_state = state
            self.bus.publish("standby", standby=state)

    def busy(self) -> bool:
        return self._busy.locked()

    def level(self, value: float) -> None:
        self.bus.publish("level", level=round(value, 3))

    def hint(self) -> str:
        """Words the speech model should expect: the assistant's name and installed programs."""
        names = [n.title() for n in apps.app_names() if 3 <= len(n) <= 24][:60]
        return WHISPER_HINT + " " + ", ".join(names)

    def teach_wake(self) -> dict:
        """Listen to the user say "Hi Vox" once and remember how the on-PC model hears it."""
        if not self._busy.acquire(blocking=False):
            return {"ok": False, "message": "Vox is busy. Try again in a moment."}
        try:
            self.standby.interrupt.set()
            self.set_state("listening")
            samples = voice.record(on_level=self.level, silence=0.8)
            self.set_state("idle")
            if samples is None:
                return {"ok": False, "message": "I didn't hear anything. Try again, a little louder."}
            heard = voice.transcribe_local(self.config["local_stt_model"], samples, self.WAKE_HINT)[0]
            if standby.split_wake(heard, self.config["wake_heard"])[0]:
                self.apply_settings({"standby": True})
                return {"ok": True, "heard": heard, "message": f'Heard "{heard}". Vox already recognises that.'}
            return self.add_wake(heard)
        except Exception as err:
            self.set_state("idle")
            return {"ok": False, "message": f"That didn't work: {err}"}
        finally:
            self._busy.release()

    # ------------------------------------------------------------ standby and dictation

    def greeting(self) -> str:
        name = self.config["user_name"].strip()
        return f"Yes {name}, I'm listening." if name else "Yes, I'm listening."

    def add_wake(self, heard: str) -> dict:
        """Remember that this is how the on-PC model hears the owner say "Hi Vox"."""
        variant = standby.wake_variant(heard)
        if not variant:
            return {"ok": False, "heard": heard, "message": f'Heard "{heard}", which is too short to use. Try again.'}
        known = [v for v in self.config["wake_heard"].split("|") if v]
        # Teaching the wake phrase means the owner wants standby, so switch it on too.
        self.apply_settings({"wake_heard": "|".join(dict.fromkeys(known + [variant])), "standby": True})
        return {"ok": True, "heard": heard, "message": f'Heard "{heard}". From now on Vox treats that as "Hi Vox".'}

    def overheard(self, text: str) -> None:
        """Standby heard speech that was not the wake phrase. Shown so a miss can be corrected."""
        self.heard_log.appendleft({"at": time.time(), "text": text[:80]})
        self.bus.publish("overheard", text=text[:80])

    def wake(self, rest: str, samples=None) -> None:
        """Called by standby when someone says "Hi Vox", with anything said after it."""
        if not self._busy.acquire(blocking=False):
            return
        try:
            if len(rest) > 2:  # "Hi Vox, open notepad": no need to ask
                # The on-PC model only had to spot the wake phrase. For the command itself,
                # hear the same recording again with the accurate engine.
                if samples is not None and self.config.stt_engine() != "local":
                    try:
                        better = voice.transcribe(self.config, samples, self.hint())
                        rest = standby.split_wake(better, self.config["wake_heard"])[1] or better or rest
                    except Exception:
                        pass
                rest = self._finish_sentence(rest)
                self._answer_pending(self.run_text(rest, spoken=True))
                return
            self.speaker.say_and_wait(self.greeting())
            self._capture_and_run()
        except Exception as err:
            self.set_state("idle")
            self.set_notice(f"Listening failed: {err}")
        finally:
            self._busy.release()

    def start_dictation(self) -> dict:
        self.dictating = True
        self.bus.publish("dictation", on=True)
        return {"message": "Go ahead."}

    def stop_dictation(self) -> dict:
        was = self.dictating
        self.dictating = False
        self.standby.interrupt.set()
        self.bus.publish("dictation", on=False)
        return {"message": "Dictation stopped." if was else "Dictation is not running."}

    def dictate(self, text: str) -> None:
        """Type one spoken passage into the active window, or stop if asked to."""
        if standby.is_stop_dictation(text):
            self.speaker.say(self.stop_dictation()["message"])
            return
        from .tools import run

        result = run("type_text", {"text": text.strip() + " "}, self.engine.ctx)
        self.bus.publish("dictated", text=text.strip(), ok=result["ok"])
        if not result["ok"]:
            self.stop_dictation()
            self.set_notice(f"Dictation stopped: {result['message']}")

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
            self.standby.interrupt.set()  # standby lets go of the microphone
            self.speaker.stop()
            self._capture_and_run()
        except Exception as err:
            self.set_state("idle")
            self.set_notice(f"Listening failed: {err}")
        finally:
            self._busy.release()

    def _capture_and_run(self, depth: int = 0) -> None:
        """Record one command, transcribe it and carry it out. Caller holds the busy lock."""
        self._release.clear()
        hold = self.config["listen_mode"] == "hold" and not self.config["standby"]
        self.set_state("listening")
        samples = voice.record(on_level=self.level, stop_event=self._release if hold else None, hold=hold,
                               silence=float(self.config["patience"]))
        if samples is None:
            self.set_state("idle")
            self.set_notice("I didn't hear anything.")
            return
        self.set_state("working")
        started = time.perf_counter()
        text = voice.transcribe(self.config, samples, self.hint())
        stt_ms = round((time.perf_counter() - started) * 1000)
        if not text:
            self.set_state("idle")
            self.set_notice("I couldn't make out any words.")
            return
        if self.dictating and standby.is_stop_dictation(text):
            self.set_state("idle")
            self.speaker.say(self.stop_dictation()["message"])
            return
        text = self._finish_sentence(text)
        self._answer_pending(self.run_text(text, stt_ms=stt_ms, spoken=True), depth + 1)

    def _finish_sentence(self, text: str) -> str:
        """If the words so far stop mid-thought ("open notepad and write"), keep listening.

        People pause to think. Rather than acting on half a sentence, wait for the rest.
        """
        from . import router

        for _ in range(3):
            if not router.unfinished(text) or router.match(text) or router.answer(text):
                break
            self.bus.publish("partial", text=text)
            self.set_state("listening")
            more = voice.record(on_level=self.level, wait_for_speech=4.0, silence=float(self.config["patience"]))
            if more is None:
                break
            self.set_state("working")
            text = (text.rstrip(" .…,") + " " + voice.transcribe(self.config, more, self.hint())).strip()
        return text

    def _answer_pending(self, result: dict, depth: int = 1) -> None:
        """If Vox just asked a yes/no question, listen for the answer straight away."""
        if not result.get("pending") or depth > 2:
            return
        deadline = time.time() + 20
        while self.speaker.speaking.is_set() and time.time() < deadline:
            time.sleep(0.1)  # let Vox finish asking before the microphone opens
        self._capture_and_run(depth)

    # ------------------------------------------------------------ for the UI

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "notice": self.notice,
            "settings": self.config.public(),
            "parts": voice.available(),
            "ai_ready": llm.ready(self.config),
            "stt_engine": self.config.stt_engine(),
            "natural_voices": llm.OPENAI_VOICES if self.config["provider"] == "openai" else llm.GEMINI_VOICES,
            "pending": self.engine.pending is not None,
            "can_undo": self.journal.can_undo(),
            "history": list(self.history),
            "update": self.update,
            "standby": self.standby_state,
            "heard_log": list(self.heard_log),
            "dictating": self.dictating,
            "learned": self.memory.listing(),
        }
