import time

from conftest import make_file
from vox import llm


def test_instant_search_uses_no_ai(vox):
    result = vox.handle("Open YouTube in Chrome and search for lofi beats")
    assert result["path"] == "instant" and result["ok"]
    assert result["timings"]["think_ms"] == 0
    url, browser = vox.opened[0]
    assert url == "https://www.youtube.com/results?search_query=lofi+beats" and browser == "chrome"


def test_default_browser_comes_from_settings(vox):
    vox.config.update({"browser": "edge"})
    vox.handle("google weather in lahore")
    assert vox.opened[0][1] == "edge"


def test_without_a_key_it_says_what_is_missing(vox):
    result = vox.handle("organise my desktop")
    assert not result["ok"] and "API key" in result["reply"]


class FakeSession:
    """Stands in for Gemini/OpenAI: replays scripted turns and records results."""

    def __init__(self, turns):
        self.turns, self.results, self.user = list(turns), [], []

    def add_user(self, text):
        self.user.append(text)

    def step(self):
        return self.turns.pop(0)

    def add_results(self, pairs):
        self.results.append(pairs)


def use_ai(vox, monkeypatch, turns):
    fake = FakeSession(turns)
    monkeypatch.setattr(llm, "session", lambda config, system, tools: fake)
    monkeypatch.setattr(llm, "ready", lambda config: True)
    return fake


def call(name, **args):
    return {"id": "c1", "name": name, "args": args}


def test_move_stale_desktop_items_in_one_ai_round(vox, monkeypatch):
    desktop = vox.home / "Desktop"
    make_file(desktop / "old report.pdf", 40)
    make_file(desktop / "ancient.txt", 25)
    make_file(desktop / "today.txt", 1)
    (desktop / "Old folder").mkdir()
    fake = use_ai(vox, monkeypatch, [
        ("", [call("move_matching", folder="desktop", destination="Unused", unused_days=20, include_folders=False)]),
    ])
    result = vox.handle("create a directory on desktop and move all my desktop items not opened in 20 days")
    assert result["ok"] and result["path"] == "ai"
    assert sorted(p.name for p in (desktop / "Unused").iterdir()) == ["ancient.txt", "old report.pdf"]
    assert (desktop / "today.txt").exists()
    assert fake.results == []  # one request to the AI, no second round trip
    assert "Moved 2 items into Unused" in result["reply"]

    undone = vox.handle("undo that")
    assert undone["path"] == "instant" and (desktop / "old report.pdf").exists()
    assert not (desktop / "Unused").exists()


def test_organise_asks_first_then_acts_and_undoes(vox, monkeypatch):
    desktop = vox.home / "Desktop"
    for name in ("a.pdf", "b.docx", "photo.jpg", "setup.exe", "mystery.xyz", "Chrome.lnk"):
        make_file(desktop / name)
    use_ai(vox, monkeypatch, [("", [call("organize_folder", folder="desktop")])])

    asked = vox.handle("organise my desktop")
    assert asked["pending"] and "5 files" in asked["reply"]
    assert (desktop / "a.pdf").exists()  # nothing moved before the yes

    done = vox.handle("yes go ahead")
    assert done["ok"] and not done["pending"]
    assert (desktop / "Documents" / "a.pdf").exists() and (desktop / "Images" / "photo.jpg").exists()
    assert (desktop / "Other" / "mystery.xyz").exists() and (desktop / "Chrome.lnk").exists()

    vox.undo()
    assert (desktop / "a.pdf").exists() and not (desktop / "Documents").exists()


def test_saying_no_cancels(vox, monkeypatch):
    make_file(vox.home / "Desktop" / "a.pdf")
    use_ai(vox, monkeypatch, [("", [call("organize_folder", folder="desktop")])])
    vox.handle("tidy the desktop")
    result = vox.handle("no, leave it")
    assert result["reply"] == "Okay, cancelled." and (vox.home / "Desktop" / "a.pdf").exists()


def test_info_tools_go_back_to_the_ai_for_the_answer(vox, monkeypatch):
    make_file(vox.home / "Downloads" / "x.zip")
    fake = use_ai(vox, monkeypatch, [
        ("", [call("list_folder", folder="downloads")]),
        ("You have one file in Downloads, x.zip.", []),
    ])
    result = vox.handle("what is in my downloads")
    assert result["reply"].startswith("You have one file")
    assert fake.results[0][0][1]["items"][0]["name"] == "x.zip"


def test_failed_instant_command_falls_back_to_ai(vox, monkeypatch):
    use_ai(vox, monkeypatch, [("Notepad isn't running right now.", [])])
    result = vox.handle("close notepad")
    assert result["path"] == "ai" and "isn't running" in result["reply"]


def test_name_collisions_never_overwrite(vox, monkeypatch):
    desktop = vox.home / "Desktop"
    (desktop / "Keep").mkdir()
    make_file(desktop / "Keep" / "note.txt")
    make_file(desktop / "note.txt", 30)
    use_ai(vox, monkeypatch, [("", [call("move_matching", folder="desktop", destination="Keep", unused_days=20)])])
    vox.handle("move old things into keep")
    assert sorted(p.name for p in (desktop / "Keep").iterdir()) == ["note (2).txt", "note.txt"]


def test_instant_path_is_fast(vox):
    started = time.perf_counter()
    for _ in range(200):
        vox.handle("search for cat videos on youtube")
    assert (time.perf_counter() - started) / 200 < 0.025  # a few milliseconds each
