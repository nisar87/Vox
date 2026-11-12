"""Self-learning: remember what the AI planned so the next time needs no AI.

Two kinds of memory, both stored as plain JSON on this PC:

* Phrases. The exact sentence (after tidying) maps to the plan the AI made.
  Usable straight away.
* Patterns. Values that appear in the sentence become blanks, so
  "move desktop files older than 20 days into archive" also answers
  "move desktop files older than 45 days into backup". A pattern is only
  trusted after the AI has produced the same shape twice.

Only plans made purely of action skills are learned. Anything that needed the
AI to read a result (questions, searches through files) always goes back to
the AI. A learned plan that fails, or that the user undoes, is forgotten.
"""

from __future__ import annotations

import json
import re
import threading
import time

from . import config, router
from .tools import TOOLS

TRUST_AFTER = 2  # times the AI must produce a pattern before it is used
# Composed text should be written fresh each time, so writing skills are never replayed.
NEVER_LEARN = {"undo_last", "run_powershell", "type_text", "press_keys", "write_in_app"}
MIN_LITERAL_WORDS = 2


def _slot_value(kind: str, text: str):
    if kind == "n":
        number = float(text)
        return int(number) if number.is_integer() else number
    return text.strip()


class Memory:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.path = config.home() / "learned.json"
        self.data = {"phrases": {}, "patterns": {}, "saved": 0}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text("utf-8"))
                self.data.update({k: loaded[k] for k in self.data if k in loaded})
            except (OSError, ValueError):
                pass
        self._compiled: dict[str, re.Pattern] = {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=1), "utf-8")

    # ------------------------------------------------------------ learning

    @staticmethod
    def learnable(calls: list[dict]) -> bool:
        if not calls:
            return False
        for call in calls:
            spec = TOOLS.get(call["name"])
            if spec is None or spec.kind != "action" or call["name"] in NEVER_LEARN:
                return False
            if call["args"].get("more_steps"):
                return False
        return True

    def learn(self, text: str, calls: list[dict]) -> list[str]:
        """Store a plan the AI just carried out successfully. Returns memory ids."""
        if not self.learnable(calls):
            return []
        phrase = router.normalize(text)
        plan = [[c["name"], {k: v for k, v in c["args"].items() if k != "more_steps"}] for c in calls]
        ids = []
        with self._lock:
            self.data["phrases"][phrase] = {"plan": plan, "uses": 0, "learned": time.time()}
            ids.append("phrase:" + phrase)
            template = self._template(phrase, plan)
            if template:
                regex, shape, slotted = template
                key = regex + "|" + json.dumps(slotted, sort_keys=True)
                entry = self.data["patterns"].setdefault(
                    key, {"regex": regex, "shape": shape, "plan": slotted, "seen": 0, "uses": 0,
                          "examples": []})
                if phrase not in entry["examples"]:
                    entry["seen"] += 1
                    entry["examples"] = (entry["examples"] + [phrase])[-3:]
                ids.append("pattern:" + key)
            self._save()
        return ids

    @staticmethod
    def _template(phrase: str, plan: list):
        """Turn values that appear in the phrase into blanks."""
        found = []  # (start, end, kind, call index, arg name)
        for index, (name, args) in enumerate(plan):
            params = TOOLS[name].params
            for arg, value in args.items():
                if "enum" in params.get(arg, {}) or isinstance(value, (bool, list, dict)) or value is None:
                    continue
                if isinstance(value, (int, float)):
                    needle = str(int(value)) if float(value).is_integer() else str(value)
                    hits = [m for m in re.finditer(rf"(?<![\w.]){re.escape(needle)}(?![\w.])", phrase)]
                    kind = "n"
                else:
                    needle = str(value).lower().strip()
                    if len(needle) < 2:
                        continue
                    hits = [m for m in re.finditer(rf"(?<!\w){re.escape(needle)}(?!\w)", phrase)]
                    kind = "s"
                if len(hits) == 1:  # ambiguous or absent values stay fixed
                    found.append((hits[0].start(), hits[0].end(), kind, index, arg))
        found.sort()
        slots, last_end = [], 0
        for slot in found:
            if slot[0] >= last_end:  # drop overlaps
                slots.append(slot)
                last_end = slot[1]
        if not slots:
            return None
        literal = "".join(phrase[a:b] for a, b in zip([0] + [s[1] for s in slots], [s[0] for s in slots] + [len(phrase)]))
        if len(re.findall(r"[a-z]{2,}", literal)) < MIN_LITERAL_WORDS:
            return None
        regex, shape, cursor = "^", "", 0
        slotted = json.loads(json.dumps(plan))
        for number, (start, end, kind, index, arg) in enumerate(slots):
            regex += re.escape(phrase[cursor:start])
            regex += rf"(?P<{kind}{number}>\d+(?:\.\d+)?)" if kind == "n" else rf"(?P<{kind}{number}>.+?)"
            shape += phrase[cursor:start] + ("[number]" if kind == "n" else "[…]")
            original = plan[index][1][arg]
            slotted[index][1][arg] = {"$slot": f"{kind}{number}",
                                      "$cap": isinstance(original, str) and original[:1].isupper()}
            cursor = end
        regex += re.escape(phrase[cursor:]) + "$"
        shape += phrase[cursor:]
        return regex, shape, slotted

    # ------------------------------------------------------------ recall

    def recall(self, text: str):
        """Return (memory id, calls) for a sentence Vox already knows, else None."""
        phrase = router.normalize(text)
        with self._lock:
            entry = self.data["phrases"].get(phrase)
            if entry:
                return "phrase:" + phrase, [(name, dict(args)) for name, args in entry["plan"]]
            for key, entry in self.data["patterns"].items():
                if entry["seen"] < TRUST_AFTER:
                    continue
                pattern = self._compiled.get(key) or self._compiled.setdefault(key, re.compile(entry["regex"]))
                match = pattern.match(phrase)
                if not match:
                    continue
                calls = []
                for name, args in entry["plan"]:
                    filled = {}
                    for arg, value in args.items():
                        if isinstance(value, dict) and "$slot" in value:
                            slot = value["$slot"]
                            got = _slot_value(slot[0], match.group(slot))
                            if value.get("$cap") and isinstance(got, str):
                                got = got[:1].upper() + got[1:]
                            filled[arg] = got
                        else:
                            filled[arg] = value
                    calls.append((name, filled))
                return "pattern:" + key, calls
        return None

    def used(self, memory_id: str) -> None:
        with self._lock:
            entry = self._entry(memory_id)
            if entry:
                entry["uses"] += 1
                self.data["saved"] += 1
                self._save()

    def failed(self, memory_id: str) -> None:
        """A remembered plan did not work. Phrases go at once; patterns get three chances."""
        with self._lock:
            entry = self._entry(memory_id)
            if not entry:
                return
            entry["fails"] = entry.get("fails", 0) + 1
            doomed = memory_id.startswith("phrase:") or entry["fails"] >= 3
            self._save()
        if doomed:
            self.forget(memory_id)

    # ------------------------------------------------------------ forgetting

    def _entry(self, memory_id: str):
        kind, _, key = memory_id.partition(":")
        return self.data["phrases" if kind == "phrase" else "patterns"].get(key)

    def forget(self, memory_id: str) -> bool:
        kind, _, key = memory_id.partition(":")
        with self._lock:
            removed = self.data["phrases" if kind == "phrase" else "patterns"].pop(key, None)
            self._compiled.pop(key, None)
            self._save()
        return removed is not None

    def clear(self) -> None:
        with self._lock:
            self.data["phrases"], self.data["patterns"] = {}, {}
            self._compiled = {}
            self._save()

    # ------------------------------------------------------------ for the UI

    def listing(self) -> dict:
        def describe(plan):
            return ", then ".join(name.replace("_", " ") for name, _ in plan)

        with self._lock:
            items = [{"id": "phrase:" + phrase, "kind": "phrase", "text": phrase, "does": describe(e["plan"]),
                      "uses": e["uses"], "active": True} for phrase, e in self.data["phrases"].items()]
            items += [{"id": "pattern:" + key, "kind": "pattern", "text": e["shape"], "does": describe(e["plan"]),
                       "uses": e["uses"], "active": e["seen"] >= TRUST_AFTER}
                      for key, e in self.data["patterns"].items()]
            return {"items": sorted(items, key=lambda i: -i["uses"]), "saved": self.data["saved"]}
