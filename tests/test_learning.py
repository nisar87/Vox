from conftest import make_file
from test_engine import call, use_ai


def stale_desktop(vox, names=("a.txt", "b.txt")):
    for name in names:
        make_file(vox.home / "Desktop" / name, 60)


def test_same_sentence_needs_no_ai_the_second_time(vox, monkeypatch):
    stale_desktop(vox)
    fake = use_ai(vox, monkeypatch, [
        ("", [call("move_matching", folder="desktop", destination="Archive", unused_days=20)])])
    first = vox.handle("clear out desktop things older than 20 days into archive")
    assert first["path"] == "ai"

    stale_desktop(vox, ("c.txt",))
    second = vox.handle("Clear out desktop things older than 20 days into archive, please.")
    assert second["path"] == "learned" and second["ok"] and second["timings"]["think_ms"] == 0
    assert fake.turns == []  # the AI was asked exactly once
    assert (vox.home / "Desktop" / "Archive" / "c.txt").exists()
    assert vox.memory.listing()["saved"] == 1


def test_pattern_generalises_after_two_examples(vox, monkeypatch):
    stale_desktop(vox)
    use_ai(vox, monkeypatch, [
        ("", [call("move_matching", folder="desktop", destination="Archive", unused_days=20)]),
        ("", [call("move_matching", folder="desktop", destination="Backup", unused_days=45)]),
    ])
    vox.handle("clear out desktop things older than 20 days into archive")
    # Seen once: a different number must still go to the AI.
    assert vox.handle("clear out desktop things older than 45 days into backup")["path"] == "ai"

    make_file(vox.home / "Desktop" / "z.txt", 200)
    make_file(vox.home / "Desktop" / "recent.txt", 5)
    third = vox.handle("clear out desktop things older than 90 days into Vault")
    assert third["path"] == "learned"
    assert [p.name for p in (vox.home / "Desktop" / "Vault").iterdir()] == ["z.txt"]
    assert (vox.home / "Desktop" / "recent.txt").exists()


def test_questions_are_never_learned(vox, monkeypatch):
    use_ai(vox, monkeypatch, [
        ("", [call("system_status")]), ("You have 100 GB free.", []),
        ("", [call("system_status")]), ("You have 90 GB free.", []),
    ])
    assert vox.handle("how much disk space is left")["path"] == "ai"
    assert vox.handle("how much disk space is left")["reply"] == "You have 90 GB free."
    assert vox.memory.listing()["items"] == []


def test_confirmed_plans_are_learned_and_still_ask(vox, monkeypatch):
    make_file(vox.home / "Desktop" / "a.pdf")
    use_ai(vox, monkeypatch, [("", [call("organize_folder", folder="desktop")])])
    vox.handle("tidy up the desktop")
    vox.handle("yes")
    make_file(vox.home / "Desktop" / "b.pdf")
    again = vox.handle("tidy up the desktop")
    assert again["path"] == "learned" and again["pending"]  # no AI, but it still asks first
    vox.handle("yes")
    assert (vox.home / "Desktop" / "Documents" / "b.pdf").exists()


def test_undo_forgets_a_wrong_plan(vox, monkeypatch):
    stale_desktop(vox)
    use_ai(vox, monkeypatch, [
        ("", [call("move_matching", folder="desktop", destination="Wrong", unused_days=20)]),
        ("Which folder did you mean?", []),
    ])
    vox.handle("put away the old desktop stuff")
    assert vox.memory.listing()["items"]
    vox.handle("undo that")
    assert vox.memory.listing()["items"] == []
    assert vox.handle("put away the old desktop stuff")["path"] == "ai"


def test_failing_memory_falls_back_to_ai(vox, monkeypatch):
    use_ai(vox, monkeypatch, [
        ("", [call("rename_item", path="desktop/a.txt", new_name="b.txt")]),
        ("That file isn't there any more.", []),
    ])
    make_file(vox.home / "Desktop" / "a.txt")
    vox.handle("rename the a file to b")
    result = vox.handle("rename the a file to b")  # a.txt is gone now
    assert result["path"] == "ai" and "isn't there" in result["reply"]
    assert not any(i["kind"] == "phrase" for i in vox.memory.listing()["items"])


def test_learning_can_be_switched_off(vox, monkeypatch):
    vox.config.update({"learning": False})
    stale_desktop(vox)
    use_ai(vox, monkeypatch, [
        ("", [call("create_folder", path="desktop/New")]), ("", [call("create_folder", path="desktop/New")])])
    vox.handle("make me a new folder")
    assert vox.handle("make me a new folder")["path"] == "ai"
