"""Ears and mouth: microphone capture, speech-to-text and spoken replies.

Every heavy import is deferred so the rest of Vox (typing commands in the
window) still works if a microphone library is missing.
"""

from __future__ import annotations

import io
import queue
import threading
import time
import wave

from . import llm

RATE = 16000
BLOCK = 480  # 30 ms
SILENCE_AFTER_SPEECH = 0.7  # seconds of quiet that end a command
WAIT_FOR_SPEECH = 5.0
MAX_SECONDS = 20.0


def available() -> dict:
    """Which optional parts are installed, for the Settings page."""
    found = {}
    for name, module in (("microphone", "sounddevice"), ("local_stt", "faster_whisper"),
                         ("hotkey", "keyboard"), ("speech", "win32com.client")):
        try:
            __import__(module)
            found[name] = True
        except Exception:
            found[name] = False
    return found


# ---------------------------------------------------------------- recording

def record(on_level=None, stop_event: threading.Event | None = None, hold: bool = False):
    """Record one spoken command and return 16 kHz mono samples (float32), or None.

    Tap mode ends by itself after a short silence. Hold mode ends when
    stop_event is set (the hotkey was released).
    """
    import numpy as np
    import sounddevice as sd

    blocks: queue.Queue = queue.Queue()
    stream = sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK,
                            callback=lambda data, frames, t, status: blocks.put(data.copy()))
    captured, noise, started = [], [], time.time()
    spoke_at = quiet_since = None
    with stream:
        while True:
            now = time.time()
            if stop_event is not None and stop_event.is_set():
                break
            if now - started > MAX_SECONDS:
                break
            try:
                block = blocks.get(timeout=0.2)
            except queue.Empty:
                continue
            level = float(np.sqrt(np.mean(block.astype("float32") ** 2)))
            if on_level:
                on_level(min(1.0, level / 4000))
            captured.append(block)
            if hold:
                continue
            if len(noise) < 8:  # first quarter second calibrates the room
                noise.append(level)
                continue
            threshold = max(350.0, 3.0 * (sum(noise) / len(noise)))
            if level > threshold:
                spoke_at, quiet_since = spoke_at or now, None
            elif spoke_at:
                quiet_since = quiet_since or now
                if now - quiet_since > SILENCE_AFTER_SPEECH:
                    break
            elif now - started > WAIT_FOR_SPEECH:
                return None
    if not captured or (not hold and not spoke_at):
        return None
    return np.concatenate(captured).flatten().astype("float32") / 32768.0


def to_wav(samples) -> bytes:
    import numpy as np

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((np.clip(samples, -1, 1) * 32767).astype("int16").tobytes())
    return buffer.getvalue()


# ---------------------------------------------------------------- speech to text

_whisper = None
_whisper_name = None
_whisper_lock = threading.Lock()


def load_local_model(name: str):
    """Load the on-PC speech model once; it stays in memory for instant reuse."""
    global _whisper, _whisper_name
    with _whisper_lock:
        if _whisper is None or _whisper_name != name:
            from faster_whisper import WhisperModel

            _whisper = WhisperModel(name, device="cpu", compute_type="int8")
            _whisper_name = name
        return _whisper


def transcribe(config, samples, hint: str = "") -> str:
    engine = config["stt"]
    if engine == "openai":
        return llm.transcribe_openai(config, to_wav(samples))
    if engine == "gemini":
        return llm.transcribe_gemini(config, to_wav(samples))
    model = load_local_model(config["local_stt_model"])
    segments, _ = model.transcribe(samples, language="en", beam_size=1, vad_filter=False,
                                   condition_on_previous_text=False, initial_prompt=hint or None)
    return " ".join(segment.text.strip() for segment in segments).strip()


# ---------------------------------------------------------------- text to speech

class Speaker:
    """Windows' built-in voice, on its own thread so speaking never blocks a command."""

    def __init__(self, config) -> None:
        self.config = config
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def say(self, text: str) -> None:
        if self.config["speak"] and text:
            self._queue.put(text)

    def stop(self) -> None:
        self._queue.put(None)

    def voices(self) -> list[str]:
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            return [v.GetDescription() for v in voice.GetVoices()]
        except Exception:
            return []

    def _loop(self) -> None:
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            voice = win32com.client.Dispatch("SAPI.SpVoice")
        except Exception:
            voice = None
        while True:
            text = self._queue.get()
            if voice is None:
                continue
            try:
                wanted = self.config["voice"]
                if wanted:
                    for candidate in voice.GetVoices():
                        if candidate.GetDescription() == wanted:
                            voice.Voice = candidate
                            break
                voice.Rate = int(self.config["speech_rate"])
                # 1 = don't wait, 2 = cut off whatever was being said
                voice.Speak(text or "", 3)
            except Exception:
                pass


# ---------------------------------------------------------------- hotkey

class Hotkey:
    def __init__(self) -> None:
        self._handles: list = []

    def bind(self, combo: str, on_press, on_release=None) -> str | None:
        """Register the global hotkey. Returns an error message or None."""
        try:
            import keyboard
        except Exception:
            return "The hotkey library isn't installed, so only the window's Listen button works."
        self.unbind()
        try:
            self._handles.append(("hotkey", keyboard.add_hotkey(combo, on_press, suppress=False)))
            if on_release:
                last = combo.split("+")[-1].strip()
                self._handles.append(("hook", keyboard.on_release_key(last, lambda event: on_release())))
        except Exception as err:
            return f"That hotkey could not be registered: {err}"
        return None

    def unbind(self) -> None:
        try:
            import keyboard

            for kind, handle in self._handles:
                keyboard.remove_hotkey(handle) if kind == "hotkey" else keyboard.unhook(handle)
        except Exception:
            pass
        self._handles = []
