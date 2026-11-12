"""Spoken commands end to end, with no microphone.

Windows' own voice speaks each command into a sound file, the on-PC speech
model transcribes it, and the instant router must pick the right action.
This is how the cloud build checks hearing accuracy.
"""

import os
import wave

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="needs Windows speech")

# (what is spoken, expected skill, a fragment that must appear in its arguments)
SPOKEN = [
    ("Open Notepad.", "open_app", "notepad"),
    ("Close Notepad.", "close_app", "notepad"),
    ("Open YouTube and search for python tutorial.", "web_search", "python tutorial"),
    ("Search for cat videos on YouTube.", "web_search", "cat videos"),
    ("Google weather in Lahore.", "web_search", "weather in lahore"),
    ("Open Google Chrome and search for cheap flights to Dubai.", "web_search", "cheap flights to dubai"),
    ("Open my downloads folder.", "open_path", "downloads"),
    ("Set volume to 40 percent.", "set_volume", "40"),
    ("Volume up.", "set_volume", "10"),
    ("Take a screenshot.", "take_screenshot", ""),
    ("Lock my computer.", "power", "lock"),
    ("Undo that.", "undo_last", ""),
    ("Pause the music.", "media_key", "play_pause"),
    ("Open Gmail.", "open_website", "gmail"),
    ("I want to see Pakistan versus Sri Lanka match highlights on YouTube.", "web_search", "match highlights"),
    ("Open Notepad and write hello world.", "open_app", "notepad"),
    ("Start dictation.", "start_dictation", ""),
]
WAKE = ["Hi Vox.", "Hi Vox, open Notepad.", "Hey Vox, take a screenshot."]
NOT_WAKE = ["Open Notepad.", "Good morning everyone, let us start the meeting."]
REQUIRED_ACCURACY = 0.85


def speak_to_file(text, path):
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Format.Type = 18  # 16 kHz, 16-bit, mono
    stream.Open(str(path), 3)
    voice.AudioOutputStream = stream
    voice.Speak(text)
    stream.Close()


def load(path):
    import numpy as np

    with wave.open(str(path), "rb") as wav:
        assert wav.getframerate() == 16000 and wav.getnchannels() == 1
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype="int16").astype("float32") / 32768.0


def test_spoken_commands_are_understood(vox, tmp_path):
    pytest.importorskip("faster_whisper")
    from vox import app, router, voice

    config = {"stt": "local", "local_stt_model": "base.en"}
    rows, correct = [], 0
    for index, (said, tool, fragment) in enumerate(SPOKEN):
        path = tmp_path / f"{index}.wav"
        try:
            speak_to_file(said, path)
        except Exception as err:
            pytest.skip(f"Windows speech is unavailable here: {err}")
        heard = voice.transcribe(config, load(path), app.WHISPER_HINT)
        calls = router.match(heard) or []
        ok = bool(calls) and calls[0][0] == tool and fragment in str(calls[0][1]).lower()
        correct += ok
        rows.append(f"{'ok  ' if ok else 'MISS'} said {said!r} -> heard {heard!r} -> {calls}")
    report = "\n".join(rows)
    print(report)
    accuracy = correct / len(SPOKEN)
    assert accuracy >= REQUIRED_ACCURACY, f"only {correct}/{len(SPOKEN)} understood:\n{report}"


def test_wake_phrase_is_heard(vox, tmp_path):
    pytest.importorskip("faster_whisper")
    from vox import app, standby, voice

    def hear(index, said):
        path = tmp_path / f"wake{index}.wav"
        try:
            speak_to_file(said, path)
        except Exception as err:
            pytest.skip(f"Windows speech is unavailable here: {err}")
        return voice.transcribe_local("base.en", load(path), app.WHISPER_HINT)[0]

    rows, woken = [], 0
    for index, said in enumerate(WAKE):
        heard = hear(index, said)
        woke, rest = standby.split_wake(heard)
        woken += woke
        rows.append(f"{'ok  ' if woke else 'MISS'} said {said!r} -> heard {heard!r} -> rest {rest!r}")
    for index, said in enumerate(NOT_WAKE):
        heard = hear(100 + index, said)
        assert standby.split_wake(heard) == (False, ""), f"woke on ordinary speech: {heard!r}"
    report = "\n".join(rows)
    print(report)
    assert woken >= 2, f"wake phrase missed too often:\n{report}"
