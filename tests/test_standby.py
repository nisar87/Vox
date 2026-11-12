import sys
import time
import types

import pytest

from vox import router, standby

ADDRESSED = [
    ("Hi Vox.", ""),
    ("Hi, Vox!", ""),
    ("Hey Vox, open Notepad.", "open Notepad."),
    ("Hi Vox open YouTube and search for lofi beats", "open YouTube and search for lofi beats"),
    ("Hi box, what time is it?", "what time is it?"),   # how the speech model often hears it
    ("Hey Fox. Volume up.", "Volume up."),
    ("Vox, lock my PC", "lock my PC"),
    ("hello vocs", ""),
]
NOT_ADDRESSED = [
    "Open notepad.",
    "The box is on the table.",
    "Fox news is on.",
    "I said hi to him yesterday.",
    "We should ask Vox later.",       # the name is not at the start
    "Hi everyone, welcome to the call.",
    "",
]


@pytest.mark.parametrize("heard,rest", ADDRESSED)
def test_wake_phrase(heard, rest):
    assert standby.split_wake(heard) == (True, rest)


@pytest.mark.parametrize("heard", NOT_ADDRESSED)
def test_ordinary_speech_does_not_wake(heard):
    assert standby.split_wake(heard) == (False, "")


def test_stop_dictation_phrases():
    for said in ("Stop dictation.", "stop writing", "Vox, stop dictation", "Hey Vox stop.", "Finish typing"):
        assert standby.is_stop_dictation(said), said
    for said in ("We should stop writing so many emails to them", "stop", "the dictation went well"):
        assert not standby.is_stop_dictation(said), said


def filetime(unix):
    return int((unix + 11_644_473_600) * 10_000_000)


def test_calls_are_detected_from_microphone_use():
    now = time.time()
    records = [
        ("MSTeams_8wekyb3d8bbwe", filetime(now - 600), 0),                              # in a call now
        ("5319275A.WhatsAppDesktop_cv1g1gvanyjgm", filetime(now - 9000), filetime(now - 8000)),  # finished
        ("C:#Program Files#Google#Chrome#Application#chrome.exe", filetime(now - 30), 0),        # browser call
        ("C:#Users#Nisar Ahmad#AppData#Local#Programs#Vox#Vox.exe", filetime(now - 5), 0),       # Vox itself
        ("C:#Old#crashed.exe", filetime(now - 5 * 86400), 0),                           # stale record
    ]
    own = r"C:\Users\Nisar Ahmad\AppData\Local\Programs\Vox\Vox.exe"
    assert standby.mic_users(records, own, now) == ["Teams", "Chrome"]
    assert standby.mic_users(records[1:2] + records[3:], own, now) == []


NEW_COMMANDS = [
    ("I want to see Pakistan vs Sri Lanka match highlights on YouTube.",
     [("web_search", {"query": "pakistan vs sri lanka match highlights", "site": "youtube"})]),
    ("show me funny cat videos on youtube", [("web_search", {"query": "funny cat videos", "site": "youtube"})]),
    ("I'd like to watch the news on YouTube", [("web_search", {"query": "the news", "site": "youtube"})]),
    ("Open Notepad and type hello world", [("open_app", {"name": "notepad"}), ("type_text", {"text": "Hello world"})]),
    ("open the notepad and keep writing what I will say without interrupting",
     [("open_app", {"name": "notepad"}), ("start_dictation", {})]),
    ("Open Word and take dictation", [("open_app", {"name": "word"}), ("start_dictation", {})]),
    ("start dictation", [("start_dictation", {})]),
    ("write down what I say", [("start_dictation", {})]),
    ("stop dictation", [("stop_dictation", {})]),
]


@pytest.mark.parametrize("said,expected", NEW_COMMANDS)
def test_new_instant_commands(vox, said, expected):
    assert router.match(said) == expected, said


@pytest.mark.parametrize("said", [
    "open notepad and write an email to my manager asking for leave",  # must be composed by the AI
    "open notepad and write a poem about rain",
    "open notepad and write few lines related to education",           # the request that failed in 0.3.0
    "open notepad and write hello world",                              # 'write' always lets the AI decide
    "open notepad++ and write hello",                                   # not installed in this test PC
    "I want to see my downloads",
])
def test_these_still_go_to_the_ai(vox, said):
    assert router.match(said) is None, said


def test_dictation_types_until_told_to_stop(vox, monkeypatch):
    from vox import app as app_module

    typed = []
    fake_keyboard = types.SimpleNamespace(write=lambda text, delay=0: typed.append(text), send=lambda keys: None)
    monkeypatch.setitem(sys.modules, "keyboard", fake_keyboard)
    state = app_module.VoxApp()
    state.config.update({"speak": False})

    result = state.run_text("start dictation")
    assert result["ok"] and state.dictating and result["reply"] == "Go ahead."
    state.dictate("Dear team,")
    state.dictate("the meeting is moved to Friday.")
    assert typed == ["Dear team, ", "the meeting is moved to Friday. "]
    state.dictate("Stop dictation.")
    assert not state.dictating and len(typed) == 2  # the stop phrase itself is not typed


def test_greeting_uses_the_name(vox):
    from vox import app as app_module

    state = app_module.VoxApp()
    state.config.update({"user_name": "Nisar"})
    assert state.greeting() == "Yes Nisar, I'm listening."
    state.config.data["user_name"] = ""
    assert state.greeting() == "Yes, I'm listening."


def test_damaged_speech_model_is_downloaded_again(vox, monkeypatch):
    """The 0.2 failure: a half-downloaded model.bin. Vox must replace it, not give up."""
    from vox import voice

    downloads = []

    def download_model(name, output_dir):
        downloads.append(name)
        (__import__("pathlib").Path(output_dir) / "model.bin").write_text("good")

    class WhisperModel:
        def __init__(self, path, device, compute_type):
            if (__import__("pathlib").Path(path) / "model.bin").read_text() != "good":
                raise RuntimeError("Unable to open file 'model.bin'")

    monkeypatch.setitem(sys.modules, "faster_whisper",
                        types.SimpleNamespace(WhisperModel=WhisperModel, download_model=download_model))
    monkeypatch.setattr(voice, "_whisper", None)
    folder = voice.model_folder("base.en")
    folder.mkdir(parents=True)
    (folder / "model.bin").write_text("truncated")

    assert isinstance(voice.load_local_model("base.en"), WhisperModel)
    assert downloads == ["base.en"] and (folder / "model.bin").read_text() == "good"
    assert str(folder).startswith(str(vox.home))  # Vox's own folder, not the shared cache


def test_taught_wake_variants(vox):
    # What the on-PC model actually heard when the owner said "Hi Vox" in 0.3.0.
    assert standby.split_wake("Hiles.") == (False, "")
    assert standby.wake_variant("Hiles.") == "hiles"
    assert standby.wake_variant("High books.") == "high books"
    assert standby.wake_variant("Hi.") is None            # a bare greeting would wake on everything
    learned = "hiles|high books"
    assert standby.split_wake("Hiles.", learned) == (True, "")
    assert standby.split_wake("High books, open Notepad.", learned) == (True, "open Notepad.")
    assert standby.split_wake("High street is closed.", learned) == (False, "")
    # The model words it slightly differently each time; near misses still count.
    assert standby.split_wake("Hials, open Notepad.", learned) == (True, "open Notepad.")
    assert standby.split_wake("Hi books.", learned) == (True, "")
    assert standby.split_wake("Open the high beam lights.", learned) == (False, "")


def test_greetings_need_no_ai(vox):
    vox.config.update({"user_name": "Nisar"})
    result = vox.handle("Hello!")
    assert result["path"] == "instant" and result["reply"] == "Hello Nisar. What can I do?"
    assert vox.handle("thank you")["reply"] == "You're welcome."


def test_notepad_plus_plus_is_understood_when_spoken(vox):
    from vox.tools import apps

    apps._index["notepad++"] = "NPP"
    assert apps.find_app("Notepad plus plus")[0] == "notepad++"
    assert router.match("open notepad plus plus") == [("open_app", {"name": "notepad++"})]


def test_old_settings_move_to_better_defaults(vox, tmp_path, monkeypatch):
    import json

    from vox import config

    (config.home() / "config.json").write_text(json.dumps(
        {"stt": "local", "gemini_model": "gemini-flash-latest", "gemini_key": "k", "provider": "gemini"}))
    fresh = config.Config()
    assert fresh["stt"] == "auto" and fresh.stt_engine() == "gemini"
    assert fresh["gemini_model"] == "gemini-3.5-flash-lite"
    fresh.data["gemini_key"] = ""
    assert fresh.stt_engine() == "local"  # no key: stay on the PC


@pytest.mark.parametrize("said,expected", [
    ("Open Notepad++ and write", True),          # the sentence that was cut off in 0.3.1
    ("Open notepad plus plus and write...", True),
    ("Search for", True),
    ("Open YouTube and", True),
    ("Create a folder called", True),
    ("Turn it on", False),                       # ends in a small word but is a whole request
    ("Open Notepad++ and write a few lines about education.", False),
    ("Open notepad.", False),
    ("Volume up", False),
    ("", False),
])
def test_unfinished_sentences_are_noticed(said, expected):
    assert router.unfinished(said) is expected, said


def test_vox_waits_for_the_rest_of_the_sentence(vox, monkeypatch):
    from vox import app as app_module
    from vox import voice

    state = app_module.VoxApp()
    recordings = iter(["chunk two", None])
    monkeypatch.setattr(voice, "record", lambda **kwargs: next(recordings))
    monkeypatch.setattr(voice, "transcribe", lambda config, samples, hint="": "a few lines about education.")
    assert state._finish_sentence("Open Notepad++ and write") == "Open Notepad++ and write a few lines about education."
    assert state._finish_sentence("Open Notepad.") == "Open Notepad."  # complete: no extra listening


def test_speech_ends_in_silence_not_a_buzz():
    np = pytest.importorskip("numpy")
    from vox import voice

    loud = (np.ones(24000) * 20000).astype("int16")  # one second that stops abruptly
    out = voice.finish_cleanly(loud, 24000)
    assert len(out) == 24000 + 6000                   # a quarter second of silence is appended
    assert abs(int(out[24000 - 1])) < 100             # faded down by the last sample
    assert not out[24000:].any()
