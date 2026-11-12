"""Live conversation: talk to Vox the way you talk to a person.

Instead of record -> transcribe -> think -> speak, the microphone is streamed
to Gemini's Live API over one WebSocket for the whole conversation. The model
hears the voice itself (no separate transcription step, so accents and names
are understood far better), decides when the speaker has finished, can be
interrupted mid-sentence, calls Vox's skills, and answers in a natural voice.

Wire protocol: https://ai.google.dev/api/live  (BidiGenerateContent).
"""

from __future__ import annotations

import base64
import contextlib
import json
import queue
import threading
import time

from . import llm

URL = ("wss://generativelanguage.googleapis.com/ws/"
       "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent")
IN_RATE, OUT_RATE = 16000, 24000
CHUNK = 1600  # 100 ms of microphone audio per message
IDLE_SECONDS = 40.0  # quiet this long and the conversation ends by itself
MAX_SECONDS = 9 * 60  # the service closes connections at about ten minutes


class LiveError(Exception):
    """A problem worth showing to the user in plain words."""


def declarations(schemas: list[dict], confirmable: set[str]) -> list[dict]:
    """Vox skills in the form the Live API wants."""
    out = []
    for spec in schemas:
        props = {k: v for k, v in spec["parameters"]["properties"].items() if k != "more_steps"}
        if spec["name"] in confirmable:
            props["confirmed"] = {"type": "boolean",
                                  "description": "Set true only after the user has said yes to this exact action."}
        decl = {"name": spec["name"], "description": spec["description"], "behavior": "NON_BLOCKING"}
        if props:
            decl["parameters"] = llm._gemini_schema(
                {"type": "object", "properties": props, "required": spec["parameters"].get("required", [])})
        out.append(decl)
    out.append({"name": "end_conversation", "behavior": "NON_BLOCKING",
                "description": "End the conversation. Call when the user says goodbye, that's all, "
                               "stop listening, or clearly has nothing more to ask."})
    return out


def setup_message(config, system: str, tools: list[dict], overrides: dict | None = None) -> dict:
    patience_ms = int(min(3000, max(500, float(config["patience"]) * 750)))
    setup = {
        "model": f"models/{config['live_model']}",
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": config["natural_voice"] or "Kore"}}},
        },
        "systemInstruction": {"parts": [{"text": system}]},
        "tools": [{"functionDeclarations": tools}],
        "realtimeInputConfig": {"automaticActivityDetection": {
            # Be slow to decide the speaker has finished: people pause to think.
            "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
            "silenceDurationMs": patience_ms,
        }},
        # Say which language to expect; left to guess, it took accented English for German.
        "inputAudioTranscription": {"languageCodes": ["en-IN", "en-US"]},
        "outputAudioTranscription": {},
    }
    for key, value in (overrides or {}).items():
        if value is None:
            setup.pop(key, None)
        else:
            setup[key] = value
    return {"setup": setup}


class Player:
    """Plays the model's speech as it arrives and can be cut off instantly."""

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._flush = False
        self.playing = threading.Event()
        self.error: str | None = None
        self.played_bytes = 0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def put(self, pcm: bytes) -> None:
        self._queue.put(pcm)

    def clear(self) -> None:
        """The user started talking over Vox: drop everything still waiting to be said."""
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        self._flush = True

    def close(self) -> None:
        self._stop.set()
        self._queue.put(b"")

    def _loop(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd

            from . import voice

            native = int(sd.query_devices(kind="output")["default_samplerate"]) or OUT_RATE
            stream = sd.OutputStream(samplerate=native, channels=2, dtype="int16")
            stream.start()
        except Exception as err:  # no speakers: carry on without sound
            self.error = f"{type(err).__name__}: {err}"
            while not self._stop.is_set():
                self._queue.get()
            return
        step = native // 25  # 40 ms pieces so an interruption takes effect at once
        try:
            while not self._stop.is_set():
                try:
                    pcm = self._queue.get(timeout=0.25)
                except queue.Empty:
                    self.playing.clear()
                    continue
                if not pcm:
                    continue
                self._flush = False
                self.playing.set()
                samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="int16")
                frames = voice.to_device_format(samples, OUT_RATE, native)
                for start in range(0, len(frames), step):
                    if self._flush or self._stop.is_set():
                        break
                    stream.write(frames[start:start + step])
                self.played_bytes += len(pcm)
        finally:
            self.playing.clear()
            stream.stop()
            stream.close()


class LiveSession:
    """One conversation. Create, call run(), and it returns when the conversation ends."""

    def __init__(self, config, system: str, tools: list[dict], run_tool, on_event,
                 speak: bool = True, overrides: dict | None = None) -> None:
        self.config, self.system, self.tools = config, system, tools
        self.run_tool, self.on_event = run_tool, on_event
        self.speak, self.overrides = speak, overrides
        self.ended_by = ""
        self.trace: list[str] = []  # the kinds of message received, for diagnosis
        self._ws = None
        self._done = threading.Event()
        self._last_activity = time.time()
        self._send_lock = threading.Lock()

    # ------------------------------------------------------------ plumbing

    def _send(self, message: dict) -> None:
        with self._send_lock:
            self._ws.send(json.dumps(message))

    def _connect(self) -> None:
        from websockets.exceptions import WebSocketException
        from websockets.sync.client import connect

        if not self.config["gemini_key"]:
            raise LiveError("Live conversation needs a Gemini API key in Settings.")
        try:
            self._stack = contextlib.ExitStack()
            self._ws = self._stack.enter_context(
                connect(f"{URL}?key={self.config['gemini_key']}", max_size=None, open_timeout=12))
            self._send(setup_message(self.config, self.system, self.tools, self.overrides))
            first = self._ws.recv(timeout=15)
        except (WebSocketException, OSError, TimeoutError) as err:
            reason = getattr(getattr(err, "rcvd", None), "reason", "") or str(err)
            raise LiveError(f"Live conversation could not start: {reason[:300] or type(err).__name__}")
        message = json.loads(first if isinstance(first, str) else first.decode("utf-8"))
        if "setupComplete" not in message:
            raise LiveError(f"Live conversation was refused: {json.dumps(message)[:300]}")

    def stop(self, why: str = "stopped") -> None:
        if not self._done.is_set():
            self.ended_by = self.ended_by or why
            self._done.set()
            try:
                self._ws.close()
            except Exception:
                pass

    # ------------------------------------------------------------ sending audio

    def _send_audio(self, pcm: bytes) -> None:
        self._send({"realtimeInput": {"audio": {"data": base64.b64encode(pcm).decode(),
                                                "mimeType": f"audio/pcm;rate={IN_RATE}"}}})

    def _pump(self, prefix, feed, stop_event, on_level) -> None:
        """Send audio until the conversation ends: any recorded lead-in first, then the
        live microphone (or, for self-tests, a scripted feed followed by silence)."""
        import numpy as np

        try:
            if prefix is not None and len(prefix):
                lead = (np.clip(prefix, -1, 1) * 32767).astype("int16").tobytes()
                for start in range(0, len(lead), CHUNK * 2):
                    self._send_audio(lead[start:start + CHUNK * 2])
            if feed is not None:
                for chunk in feed:
                    if self._done.is_set():
                        return
                    self._send_audio(chunk)
                    time.sleep(len(chunk) / 2 / IN_RATE)  # real-time pacing, like a microphone
                silence = b"\x00" * (CHUNK * 2)
                while not self._done.is_set():
                    self._send_audio(silence)
                    time.sleep(CHUNK / IN_RATE)
                    self._watch(stop_event)
                return
            import sounddevice as sd

            blocks: queue.Queue = queue.Queue()
            with sd.InputStream(samplerate=IN_RATE, channels=1, dtype="int16", blocksize=CHUNK,
                                callback=lambda data, frames, t, status: blocks.put(data.copy())):
                while not self._done.is_set():
                    try:
                        block = blocks.get(timeout=0.3)
                    except queue.Empty:
                        continue
                    if on_level:
                        on_level(min(1.0, float(np.sqrt(np.mean(block.astype("float32") ** 2))) / 4000))
                    self._send_audio(block.tobytes())
                    self._watch(stop_event)
        except Exception as err:
            if not self._done.is_set():
                self.on_event("error", message=f"The microphone stream stopped: {err}")
                self.stop("error")

    def _watch(self, stop_event) -> None:
        now = time.time()
        if self._player is not None and self._player.playing.is_set():
            self._last_activity = now
        if stop_event is not None and stop_event.is_set():
            self.stop("stopped")
        elif now - self._last_activity > IDLE_SECONDS:
            self.stop("quiet")
        elif now - self._started > MAX_SECONDS:
            self.stop("time limit")

    # ------------------------------------------------------------ receiving

    def run(self, stop_event=None, prefix=None, feed=None, on_level=None) -> None:
        self._connect()
        self._started = self._last_activity = time.time()
        self._player = Player() if self.speak else None
        self.on_event("started")
        heard, said, steps, turn_started, first_reply = "", "", [], None, None
        pump = threading.Thread(target=self._pump, args=(prefix, feed, stop_event, on_level), daemon=True)
        pump.start()
        try:
            while not self._done.is_set():
                try:
                    raw = self._ws.recv(timeout=1.0)
                except TimeoutError:
                    continue
                except Exception as err:
                    if not self._done.is_set():
                        reason = getattr(getattr(err, "rcvd", None), "reason", "") or type(err).__name__
                        self.ended_by = f"closed: {reason[:200]}"
                    break
                message = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
                self.trace += [k for k in message if k != "usageMetadata"][:1]

                if "toolCall" in message:
                    self._last_activity = time.time()
                    responses = []
                    for call in message["toolCall"].get("functionCalls", []):
                        if call["name"] == "end_conversation":
                            result = {"ok": True, "message": "Conversation ended."}
                            self.ended_by = "goodbye"
                        else:
                            result = self.run_tool(call["name"], call.get("args") or {}, heard)
                            steps.append({"tool": call["name"], "args": call.get("args") or {},
                                          "ok": bool(result.get("ok", True)), "message": result.get("message", "")})
                        responses.append({"id": call.get("id"), "name": call["name"], "response": result})
                    self._send({"toolResponse": {"functionResponses": responses}})
                    continue
                if "goAway" in message:
                    self.ended_by = self.ended_by or "time limit"
                    continue

                content = message.get("serverContent")
                if not content:
                    continue
                if content.get("inputTranscription", {}).get("text"):
                    if not heard:
                        turn_started = time.time()
                    heard += content["inputTranscription"]["text"]
                    self._last_activity = time.time()
                    self.on_event("hearing", text=heard.strip())
                if content.get("outputTranscription", {}).get("text"):
                    said += content["outputTranscription"]["text"]
                for part in content.get("modelTurn", {}).get("parts", []):
                    data = part.get("inlineData", {}).get("data")
                    if data:
                        self._last_activity = time.time()
                        first_reply = first_reply or time.time()
                        if self._player is not None:
                            self._player.put(base64.b64decode(data))
                if content.get("interrupted"):
                    if self._player is not None:
                        self._player.clear()
                    self.on_event("interrupted")
                if content.get("turnComplete"):
                    # After a skill runs, the spoken confirmation arrives as a turn of its own.
                    # Keep the request and its steps until then, so they are reported together.
                    awaiting_confirmation = bool(steps) and not said.strip() and not self.ended_by
                    if not awaiting_confirmation and (heard.strip() or said.strip() or steps):
                        waited = round((first_reply - turn_started) * 1000) if first_reply and turn_started else 0
                        self.on_event("turn", heard=heard.strip(), reply=said.strip(), steps=steps, reply_ms=waited)
                        heard, said, steps, turn_started, first_reply = "", "", [], None, None
                    if self.ended_by:
                        self._finish_speaking()
                        break
        finally:
            if heard.strip() or said.strip() or steps:  # a turn that was still open when the line closed
                self.on_event("turn", heard=heard.strip(), reply=said.strip(), steps=steps, reply_ms=0)
            self.ended_by = self.ended_by or "closed"
            self._done.set()
            try:
                self._ws.close()
            except Exception:
                pass
            pump.join(timeout=2)
            if self._player is not None:
                self._player.close()
            self.on_event("ended", why=self.ended_by)

    def _finish_speaking(self) -> None:
        """Let Vox finish its goodbye before hanging up."""
        if self._player is None:
            return
        deadline = time.time() + 8
        time.sleep(0.4)
        while self._player.playing.is_set() and time.time() < deadline:
            time.sleep(0.1)
