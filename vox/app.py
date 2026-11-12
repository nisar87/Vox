"""Wires the pieces together: hotkey -> listen -> understand -> act -> speak."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections import deque

from . import config as config_module
from . import engine, journal, learning, live, llm, paths, standby, updater, voice
from .tools import TOOLS, apps, schemas
from .tools import run as run_tool

LIVE_SYSTEM = """You are Vox, a voice assistant that operates {name}'s Windows 11 PC by calling tools. This is a live spoken conversation.

Listening:
- {name} lives in Pakistan and English is not their first language. Listen for the meaning, not the grammar or the accent. When a word is unclear, choose the reading that makes sense as a request to a PC assistant or that names an installed program. They may mix in Urdu words; reply in English unless they speak to you in Urdu.
- Let them finish. A pause in the middle of a sentence is thinking, not the end. Never answer half a sentence.
- You are woken with "Hi Vox". If that is all they say, answer "Yes {name}?" and wait.
- If what you hear is clearly not meant for you (other people talking, a video), stay silent.

Acting:
- Do it, then confirm in a few words ("Done.", "Written in Notepad++."). Do not announce what you are about to do, and do not repeat the request back.
- Do every part of the request. "Open X and write ..." is ONE call to write_in_app with the finished text; if they described what to write, compose it yourself. "In a new tab/sheet/file" means new_document=true.
- If something essential is missing, ask one short question, then act on the answer.
- If a tool result says needs_confirmation, ask the user that question and wait. Only after they say yes, call the tool again with confirmed=true.
- If a tool result has ok=false, that step did not happen. Say so plainly.
- Never delete anything unless clearly asked. "Not opened in N days" means the unused_days filter.
- When they are finished ("that's all", "thanks", "bye", "stop listening"), say a two-word goodbye and call end_conversation.

Speaking: short, plain, warm. No lists, no file paths, no technical identifiers.

This PC:
- Now: {now}
- Folders: {folders}
- Preferred browser: {browser}
- Installed programs: {apps}
"""

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
        self.in_conversation = False
        self._conv_stop = threading.Event()
        self._live_failed = False
        self._live_turns = 0
        self._live_asked: dict = {}
        self.heard_log: deque[dict] = deque(maxlen=10)  # what standby heard and ignored, for diagnosis
        self.voice_log: deque[dict] = deque(maxlen=12)  # how each spoken request was captured
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
        threading.Thread(target=updater.clean_old_installers, daemon=True).start()
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
            if updater.installed_from_setup():
                updater.check_space()
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
        self._live_failed = False
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
        """Words the speech model should expect.

        Only the assistant's name. A list of installed programs used to be included, and on
        a noisy recording the speech model would "hear" one of them: on the owner's PC a
        faint noise came back as "7-Zip Help" and that program was opened.
        """
        return "Vox, Notepad++"

    def loopback(self, text: str) -> dict:
        """Speak a sentence with the AI voice and feed it straight back into the hearing
        path, without microphone or speakers. Proves the live speech services work."""
        import numpy as np

        started = time.perf_counter()
        pcm, rate = llm.speak(self.config, text)
        tts_ms = round((time.perf_counter() - started) * 1000)
        samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="int16").astype("float32") / 32768.0
        positions = np.linspace(0, len(samples) - 1, int(len(samples) * voice.RATE / rate))
        samples = np.interp(positions, np.arange(len(samples)), samples).astype("float32")
        started = time.perf_counter()
        heard = voice.transcribe(self.config, samples, self.hint())
        return {"said": text, "heard": heard, "engine": self.config.stt_engine(), "tts_ms": tts_ms,
                "stt_ms": round((time.perf_counter() - started) * 1000), "seconds": round(len(samples) / voice.RATE, 1)}

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
            # Live: hand the recording of "Hi Vox ..." to the conversation and carry on from there.
            if self.live_available() and samples is not None and self._conversation(prefix=samples):
                return
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
        """Hotkey or the window's button: start listening, or end a conversation in progress."""
        if self.in_conversation:
            self._conv_stop.set()
            return
        if not self._busy.acquire(blocking=False):
            return
        threading.Thread(target=self._voice_turn, daemon=True).start()

    # ------------------------------------------------------------ live conversation

    def live_available(self) -> bool:
        return (self.config["conversation"] == "live" and self.config["provider"] == "gemini"
                and bool(self.config["gemini_key"]) and not self._live_failed and voice.available()["microphone"])

    def live_system(self) -> str:
        import datetime

        return LIVE_SYSTEM.format(
            name=self.config["user_name"].strip() or "the user",
            now=datetime.datetime.now().strftime("%A %d %B %Y, %H:%M"),
            folders=", ".join(f"{n} = {paths.known_folder(n)}" for n in paths.KNOWN),
            browser=self.config["browser"],
            apps=", ".join(apps.app_names()[:150]) or "unknown")

    def live_tools(self) -> list[dict]:
        confirmable = {name for name, spec in TOOLS.items() if spec.confirm}
        return live.declarations(schemas(), confirmable)

    def _live_tool(self, name: str, args: dict, heard: str) -> dict:
        """Run a skill the live model asked for. Risky ones need a spoken yes first."""
        spec = TOOLS.get(name)
        if spec is None:
            return {"ok": False, "message": f"There is no skill called {name}."}
        args = dict(args)
        confirmed = bool(args.pop("confirmed", False))
        ctx = self.engine.ctx
        if spec.needs_confirmation(args, ctx):
            key = name + json.dumps(args, sort_keys=True, default=str)
            # A yes only counts if Vox asked about this exact action and the user has spoken since.
            asked = self._live_asked
            if not (confirmed and asked.get("key") == key and self._live_turns > asked.get("turn", 10**9)):
                self._live_asked = {"key": key, "turn": self._live_turns}
                question = spec.preview(args, ctx) if spec.preview else "Shall I go ahead?"
                return {"ok": False, "needs_confirmation": True,
                        "message": f"Not done yet. Ask the user exactly this and wait for the answer: {question} "
                                   f"If they say yes, call {name} again with the same arguments and confirmed=true. "
                                   "If they say no, do nothing."}
            self._live_asked = {}
        ctx.journal.begin((heard or name)[:80])
        try:
            result = run_tool(name, args, ctx)
        finally:
            ctx.journal.commit()
        if name == "start_dictation" and result.get("ok"):
            self._conv_stop.set()  # dictation takes over the microphone
        return result

    def _live_event(self, kind: str, **data) -> None:
        if kind == "hearing":
            self.bus.publish("hearing", text=data["text"][-200:])
        elif kind == "error":
            self.set_notice(data["message"])
        elif kind == "turn":
            self._live_turns += 1
            steps = data["steps"]
            reply = data["reply"] or " ".join(dict.fromkeys(s["message"] for s in steps))
            result = {"heard": data["heard"] or "(spoken)", "reply": reply, "ok": all(s["ok"] for s in steps),
                      "path": "live", "steps": steps, "pending": False, "can_undo": self.journal.can_undo(),
                      "timings": {"stt_ms": 0, "think_ms": data["reply_ms"], "act_ms": 0, "total_ms": data["reply_ms"]},
                      "spoken": True, "at": time.time()}
            self.engine.recent.append(f"User: {result['heard']}\nVox: {reply}")
            self.history.appendleft(result)
            self.bus.publish("result", result=result)

    def _conversation(self, prefix=None) -> bool:
        """Hold a live conversation until it ends. Caller holds the busy lock.

        Returns False if the live service could not be reached, so the caller can
        fall back to the classic one-command path.
        """
        self.standby.interrupt.set()
        self.speaker.stop()
        self._conv_stop.clear()
        self._live_turns, self._live_asked = 0, {}
        session = live.LiveSession(self.config, self.live_system(), self.live_tools(), self._live_tool,
                                   self._live_event, speak=bool(self.config["speak"]))

        def hang_up_for_calls():  # another program took the microphone: a call has started
            while not self._conv_stop.wait(2.0) and self.in_conversation:
                try:
                    if self.config["pause_on_calls"] and standby.mic_users():
                        self._conv_stop.set()
                except Exception:
                    return

        self.in_conversation = True
        self.set_state("conversation")
        threading.Thread(target=hang_up_for_calls, daemon=True).start()
        try:
            session.run(stop_event=self._conv_stop, prefix=prefix, on_level=self.level)
            return True
        except live.LiveError as err:
            self._live_failed = True  # use the classic path until settings change
            self.set_notice(f"{err} Using one-command-at-a-time listening instead.")
            return False
        except Exception as err:
            self.set_notice(f"The conversation stopped: {type(err).__name__}: {err}")
            return True
        finally:
            self._conv_stop.set()
            self.in_conversation = False
            self.set_state("idle")

    def live_probe(self, text: str, overrides: dict | None = None) -> dict:
        """Self-test of the live path without microphone or speakers: the sentence is spoken
        by the AI voice, streamed into a live session, and what came back is reported.
        Skills are not run; each call is recorded and answered with a stand-in result."""
        import numpy as np

        pcm, rate = llm.speak(self.config, text)
        samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="int16").astype("float32")
        positions = np.linspace(0, len(samples) - 1, int(len(samples) * live.IN_RATE / rate))
        audio = np.interp(positions, np.arange(len(samples)), samples).astype("int16").tobytes()
        chunks = [audio[i:i + live.CHUNK * 2] for i in range(0, len(audio), live.CHUNK * 2)]
        calls, turns, stop = [], [], threading.Event()

        def fake_tool(name, args, heard):
            calls.append({"name": name, "args": args})
            return {"ok": True, "message": "Done."}

        def on_event(kind, **data):
            if kind == "turn":
                turns.append({k: data[k] for k in ("heard", "reply", "reply_ms")})
                threading.Timer(1.0, stop.set).start()
            elif kind == "error":
                turns.append({"error": data["message"]})

        session = live.LiveSession(self.config, self.live_system(), self.live_tools(), fake_tool, on_event,
                                   speak=False, overrides=overrides)
        threading.Timer(40, stop.set).start()
        started = time.time()
        try:
            session.run(stop_event=stop, feed=chunks)
        except live.LiveError as err:
            return {"said": text, "error": str(err)}
        return {"said": text, "turns": turns, "calls": calls, "ended": session.ended_by,
                "seconds": round(time.time() - started, 1), "trace": session.trace[:60]}

    def _voice_turn(self) -> None:
        try:
            self.standby.interrupt.set()  # standby lets go of the microphone
            self.speaker.stop()
            if self.live_available() and self._conversation():
                return
            self._capture_and_run()
        except Exception as err:
            self.set_state("idle")
            self.set_notice(f"Listening failed: {err}")
        finally:
            self._busy.release()

    def _capture_and_run(self, depth: int = 0) -> None:
        """Listen to one request, however it is phrased and paced, then carry it out.

        The microphone stays open the whole time. After each stretch of speech Vox
        transcribes it, then looks at what was said meanwhile: if the speaker carried
        on, or the words so far stop mid-thought, it keeps listening and hears the
        whole thing again together. Caller holds the busy lock.
        """
        import numpy as np

        from . import router

        self._release.clear()
        hold = self.config["listen_mode"] == "hold" and not self.config["standby"] and depth == 0
        patience = float(self.config["patience"])
        entry = {"at": time.time(), "engine": self.config.stt_engine(), "rounds": []}
        self.voice_log.appendleft(entry)
        self.set_state("listening")
        text, stt_ms = "", 0
        with voice.Recorder(on_level=self.level) as mic:
            audio = mic.segment(wait=7.0 if depth else voice.WAIT_FOR_SPEECH, silence=patience,
                                stop_event=self._release if hold else None, hold=hold)
            if audio is None:
                entry["rounds"].append(mic.last or {"ended": "no speech"})
                self.set_state("idle")
                self.set_notice("I didn't hear anything.")
                return
            for _ in range(5):
                self.set_state("working")
                started = time.perf_counter()
                text = voice.transcribe(self.config, audio, self.hint())
                took = round((time.perf_counter() - started) * 1000)
                stt_ms += took
                entry["rounds"].append({**mic.last, "heard": text, "stt_ms": took})
                if hold or not text:
                    break
                complete = not router.unfinished(text) or router.match(text) or router.answer(text)
                if not complete:
                    self.bus.publish("partial", text=text)
                    self.set_state("listening")
                # Audio that arrived while transcribing is waiting in the buffer. A complete
                # sentence gets only that; an unfinished one gets four more seconds.
                more = mic.segment(wait=mic.buffered() + (0.0 if complete else 4.0), silence=patience)
                if more is None:
                    break
                audio = np.concatenate([audio, more])
        if not text:
            self.set_state("idle")
            self.set_notice("I couldn't make out any words.")
            return
        if self.dictating and standby.is_stop_dictation(text):
            self.set_state("idle")
            self.speaker.say(self.stop_dictation()["message"])
            return
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
        """If Vox just asked something, listen for the answer straight away, like a person would."""
        asked = result.get("pending") or result.get("reply", "").rstrip().endswith("?")
        if not asked or depth > 3:
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
            "voice_log": list(self.voice_log),
            "dictating": self.dictating,
            "in_conversation": self.in_conversation,
            "live": self.live_available(),
            "learned": self.memory.listing(),
        }
