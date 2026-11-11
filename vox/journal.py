"""Record what Vox changed on disk so the last action can be undone."""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

from . import config

MAX_BATCHES = 50


class Journal:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.path = config.home() / "journal.json"
        self.batches: list[dict] = []
        self._open: dict | None = None
        if self.path.exists():
            try:
                self.batches = json.loads(self.path.read_text("utf-8"))
            except (OSError, ValueError):
                self.batches = []

    # A batch groups everything one spoken command did.
    def begin(self, label: str) -> None:
        self._open = {"label": label, "ops": []}

    def record(self, op: str, **fields) -> None:
        if self._open is None:
            self.begin("action")
        self._open["ops"].append({"op": op, **fields})

    def commit(self) -> None:
        with self._lock:
            if self._open and self._open["ops"]:
                self.batches.append(self._open)
                self.batches = self.batches[-MAX_BATCHES:]
                self._save()
            self._open = None

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.batches), "utf-8")

    def can_undo(self) -> bool:
        return bool(self.batches)

    def undo(self) -> dict:
        with self._lock:
            if not self.batches:
                return {"ok": False, "message": "There is nothing to undo."}
            batch = self.batches.pop()
            restored, problems = 0, []
            for op in reversed(batch["ops"]):
                try:
                    if op["op"] == "move":
                        src, dst = Path(op["src"]), Path(op["dst"])
                        if not dst.exists():
                            problems.append(f"{dst.name} is no longer where I put it")
                        elif src.exists():
                            problems.append(f"{src.name} already exists in its old place")
                        else:
                            src.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(dst), str(src))
                            restored += 1
                    elif op["op"] == "mkdir":
                        folder = Path(op["path"])
                        if folder.is_dir() and not any(folder.iterdir()):
                            folder.rmdir()
                except OSError as err:
                    problems.append(str(err))
            self._save()
        message = f"Undone: {batch['label']}."
        if restored:
            message = f"Undone. I put {restored} item{'s' if restored != 1 else ''} back."
        if problems:
            message += f" {len(problems)} could not be restored: {problems[0]}."
        return {"ok": not problems, "message": message}
