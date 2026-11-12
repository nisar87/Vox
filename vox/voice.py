"""Ears and mouth: microphone capture, speech-to-text and spoken replies.

Every heavy import is deferred so the rest of Vox (typing commands in the
window) still works if a microphone library is missing.
"""

from __future__ import annotations

import hashlib
import io
import queue
import shutil
import threading
import time
import wave

from . import config as config_module
from . import llm

RATE = 16000
BLOCK = 480  # 30 ms
SILENCE_AFTER_SPEECH = 1.4  # seconds of quiet that end a command (Settings: patience)
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

class Recorder:
    """Keeps the microphone open for a whole conversation turn.

    While Vox is busy transcribing, the microphone keeps filling a buffer, so
    anything said in the meantime is still there afterwards. Time is counted in
    audio received, not on the clock, so buffered audio is judged exactly as
    live audio would be.
    """

    STEP = BLOCK / RATE  # seconds per block

    def __init__(self, on_level=None, floor: list | None = None) -> None:
        self.on_level = on_level
        self.noise = floor if floor is not None else []
        self.blocks: queue.Queue = queue.Queue()
        self.last: dict = {}
        self._stream = None

    def __enter__(self):
        import sounddevice as sd

        self._stream = sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK,
                                      callback=lambda data, frames, t, status: self.blocks.put(data.copy()))
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()

    def buffered(self) -> float:
        """Seconds of audio waiting to be looked at."""
        return self.blocks.qsize() * self.STEP

    def segment(self, wait: float = WAIT_FOR_SPEECH, silence: float = SILENCE_AFTER_SPEECH,
                stop_event: threading.Event | None = None, hold: bool = False):
        """One stretch of speech as 16 kHz mono float32 samples, or None if nobody spoke.

        Ends after 'silence' seconds of quiet following speech. Gives up after
        'wait' seconds with no speech. In hold mode it ends when stop_event is
        set; otherwise a set stop_event abandons the recording.
        """
        import numpy as np

        captured, spoke, quiet, waited, total, peak, threshold = [], False, 0.0, 0.0, 0.0, 0.0, 0.0
        ended = "silence"
        while True:
            if stop_event is not None and stop_event.is_set():
                if hold:
                    ended = "released"
                    break
                return None
            try:
                block = self.blocks.get(timeout=0.2)
            except queue.Empty:
                continue
            level = float(np.sqrt(np.mean(block.astype("float32") ** 2)))
            if self.on_level:
                self.on_level(min(1.0, level / 4000))
            captured.append(block)
            total += self.STEP
            if total > MAX_SECONDS:
                ended = "too long"
                break
            if hold:
                continue
            if len(self.noise) < 8:  # first quarter second calibrates the room
                self.noise.append(level)
                continue
            threshold = max(350.0, 3.0 * (sum(self.noise) / len(self.noise)))
            if level > threshold:
                spoke, quiet, peak = True, 0.0, max(peak, level)
            elif spoke:
                quiet += self.STEP
                if quiet > silence:
                    break
            else:
                waited += self.STEP
                if waited > wait:
                    self.last = {"seconds": 0.0, "ended": "no speech", "threshold": round(threshold)}
                    return None
                # Quiet moment: let the noise level follow the room, and keep only a
                # short lead-in so the recording starts just before the first word.
                self.noise.append(level)
                del self.noise[:-8]
                del captured[:-10]
        if not captured or (not hold and not spoke):
            return None
        self.last = {"seconds": round(len(captured) * self.STEP, 1), "ended": ended,
                     "peak": round(peak), "threshold": round(threshold)}
        return np.concatenate(captured).flatten().astype("float32") / 32768.0


def record(on_level=None, stop_event: threading.Event | None = None, hold: bool = False,
           wait_for_speech: float = WAIT_FOR_SPEECH, floor: list | None = None,
           silence: float = SILENCE_AFTER_SPEECH):
    """Record one stretch of speech (see Recorder.segment). Opens and closes the microphone."""
    with Recorder(on_level, floor) as recorder:
        return recorder.segment(wait_for_speech, silence, stop_event, hold)


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


def model_folder(name: str):
    return config_module.data_dir() / "models" / name


def model_downloaded(name: str) -> bool:
    return (model_folder(name) / "model.bin").exists()


def _open_model(name: str):
    from faster_whisper import WhisperModel, download_model

    folder = model_folder(name)
    if not model_downloaded(name):
        folder.mkdir(parents=True, exist_ok=True)
        download_model(name, output_dir=str(folder))
    return WhisperModel(str(folder), device="cpu", compute_type="int8")


def load_local_model(name: str):
    """Load the on-PC speech model once; it stays in memory for instant reuse.

    The model lives in Vox's own folder as ordinary files. If it is damaged
    (an interrupted download, a file removed by security software) it is
    deleted and downloaded again, once.
    """
    global _whisper, _whisper_name
    with _whisper_lock:
        if _whisper is None or _whisper_name != name:
            try:
                _whisper = _open_model(name)
            except Exception:
                shutil.rmtree(model_folder(name), ignore_errors=True)
                _whisper = _open_model(name)
            _whisper_name = name
        return _whisper


def transcribe_local(model_name: str, samples, hint: str = "") -> tuple[str, float]:
    """Transcribe on this PC. Returns (text, probability that it was not speech)."""
    model = load_local_model(model_name)
    options = dict(language="en", beam_size=5, vad_filter=False, condition_on_previous_text=False,
                   initial_prompt=hint or None)
    try:
        segments, _ = model.transcribe(samples, hotwords="Vox", **options)  # nudges the rare name "Vox"
    except TypeError:
        segments, _ = model.transcribe(samples, **options)
    segments = list(segments)
    text = " ".join(segment.text.strip() for segment in segments).strip()
    no_speech = max((segment.no_speech_prob for segment in segments), default=1.0)
    return text, no_speech


def transcribe(config, samples, hint: str = "") -> str:
    """Speech to text with the engine chosen in Settings.

    The cloud engines understand accents and names far better than the small
    on-PC model. If the cloud call fails, the on-PC model is used instead so a
    command is never lost to a network hiccup.
    """
    engine = config.stt_engine() if hasattr(config, "stt_engine") else config["stt"]
    if engine in ("openai", "gemini"):
        try:
            if engine == "openai":
                return llm.transcribe_openai(config, to_wav(samples))
            return llm.transcribe_gemini(config, to_wav(samples), hint)
        except llm.LLMError:
            if not available()["local_stt"]:
                raise
    return transcribe_local(config["local_stt_model"], samples, hint)[0]


# ---------------------------------------------------------------- text to speech

class Speaker:
    """Windows' built-in voice, on its own thread so speaking never blocks a command."""

    def __init__(self, config, on_problem=None) -> None:
        self.config = config
        self.on_problem = on_problem  # called once with a sentence when the natural voice fails
        self._natural_failed = False
        self.speaking = threading.Event()  # set while Vox is talking, so standby ignores its own voice
        self.last_spoke = 0.0
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def say(self, text: str, done: threading.Event | None = None) -> None:
        if self.config["speak"] and text:
            self.speaking.set()
            self._queue.put((text, done))
        elif done:
            done.set()

    def say_and_wait(self, text: str, timeout: float = 8.0) -> None:
        """Speak and return when finished, so the microphone does not record Vox itself."""
        done = threading.Event()
        self.say(text, done)
        done.wait(timeout)

    def stop(self) -> None:
        self._queue.put(("", None))

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
            text, done = self._queue.get()
            try:
                if text and self._natural(text):
                    pass  # spoken with the AI voice
                elif voice is not None:
                    wanted = self.config["voice"]
                    if wanted:
                        for candidate in voice.GetVoices():
                            if candidate.GetDescription() == wanted:
                                voice.Voice = candidate
                                break
                    voice.Rate = int(self.config["speech_rate"])
                    voice.Speak(text, 3)  # 1 = don't wait, 2 = cut off whatever was being said
                    while not voice.WaitUntilDone(60):
                        if not self._queue.empty():
                            break  # something newer to say (or a stop): it will cut this off
            except Exception:
                pass
            finally:
                self.last_spoke = time.time()
                if self._queue.empty():
                    self.speaking.clear()
                if done:
                    done.set()


def _cache_file(config, text: str):
    key = f"{config['provider']}|{config['natural_voice']}|{text}"
    folder = config_module.data_dir() / "voice_cache"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (hashlib.sha1(key.encode()).hexdigest() + ".pcm")


def natural_audio(config, text: str) -> tuple[bytes, int]:
    """Speech for a sentence from the AI voice, remembered on disk so repeats are instant."""
    path = _cache_file(config, text)
    if path.exists():
        raw = path.read_bytes()
        return raw[4:], int.from_bytes(raw[:4], "little")
    pcm, rate = llm.speak(config, text)
    if len(text) <= 200:  # short confirmations repeat; long answers do not
        path.write_bytes(rate.to_bytes(4, "little") + pcm)
    return pcm, rate


def finish_cleanly(samples, rate: int):
    """Fade the last few milliseconds and add a short silence so speech ends without a click or buzz."""
    import numpy as np

    samples = samples.astype("float32")
    fade = min(len(samples), rate // 50)  # 20 ms
    if fade:
        samples[-fade:] *= np.linspace(1.0, 0.0, fade, dtype="float32")
    return np.concatenate([samples, np.zeros(rate // 4, dtype="float32")]).astype("int16")


def to_device_format(samples, rate: int, native: int):
    """Mono speech at the provider's rate -> stereo frames at the sound card's rate."""
    import numpy as np

    if native != rate and len(samples):
        positions = np.linspace(0, len(samples) - 1, int(len(samples) * native / rate))
        samples = np.interp(positions, np.arange(len(samples)), samples.astype("float32")).astype("int16")
    return np.ascontiguousarray(np.column_stack([samples, samples]))


def _speaker_natural(self, text: str) -> bool:
    """Say it with the AI voice. False means: use the Windows voice instead."""
    if self.config["voice_engine"] != "natural" or self._natural_failed:
        return False
    if not self.config[f"{self.config['provider']}_key"]:
        return False
    try:
        import numpy as np
        import sounddevice as sd

        pcm, rate = natural_audio(self.config, text)
        samples = finish_cleanly(np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="int16"), rate)
        # Play in the sound card's own format (its sample rate, stereo). Some devices,
        # USB headsets especially, refuse anything else while the microphone is in use.
        native = int(sd.query_devices(kind="output")["default_samplerate"]) or rate
        frames = to_device_format(samples, rate, native)
        step = native // 20  # 50 ms pieces, so a newer sentence can cut in quickly
        # Written piece by piece and closed properly: letting the device run dry made it buzz.
        with sd.OutputStream(samplerate=native, channels=2, dtype="int16") as out:
            for start in range(0, len(frames), step):
                if not self._queue.empty():
                    break  # something newer to say, or a stop
                out.write(frames[start:start + step])
        self._natural_errors = 0
        return True
    except Exception as err:
        # One hiccup falls back to the Windows voice for this sentence only; three in a
        # row switch the natural voice off until settings change.
        self._natural_errors = getattr(self, "_natural_errors", 0) + 1
        if self._natural_errors >= 3:
            self._natural_failed = True
            if self.on_problem:
                self.on_problem(f"The natural voice is unavailable, so I'm using the Windows voice. ({err})")
        return False


Speaker._natural = _speaker_natural


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
