import os
import time

import pytest


@pytest.fixture
def vox(tmp_path, monkeypatch):
    """A Vox engine pointed at a throwaway home folder, with launches captured."""
    monkeypatch.setenv("VOX_HOME", str(tmp_path / "voxhome"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    from vox import config, engine, journal, paths
    from vox.tools import apps, web

    paths.reset_cache()
    for name in paths.KNOWN:
        (tmp_path / name.capitalize()).mkdir()

    opened = []
    monkeypatch.setattr(web, "launch_url", lambda url, browser="default": opened.append((url, browser)))
    monkeypatch.setattr(apps, "shell_open", lambda target: opened.append(("app", target)))
    apps._index = {"google chrome": "Chrome", "notepad": "Notepad", "visual studio code": "Code",
                   "visual studio 2022": "VS", "word": "Word", "spotify": "Spotify"}
    apps._index_ready.set()

    eng = engine.Engine(config.Config(), journal.Journal())
    eng.opened = opened
    eng.home = tmp_path
    return eng


def make_file(path, days_old=0):
    path.write_text("x")
    stamp = time.time() - days_old * 86400
    os.utime(path, (stamp, stamp))
    return path
