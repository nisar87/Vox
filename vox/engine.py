"""Turn one sentence into actions.

Order of attempts, fastest first:
  1. a pending yes/no question
  2. answers that need nothing (the time)
  3. the instant router (no AI, a few milliseconds)
  4. the AI model, which plans with the skills in vox.tools
"""

from __future__ import annotations

import datetime
import threading
import time
from collections import deque

from . import llm, paths, router
from .tools import TOOLS, Context, apps, run, schemas

MAX_ROUNDS = 6

SYSTEM = """You are Vox, a voice assistant that operates this Windows 11 PC by calling tools.

How to work:
- Act instead of explaining. Call every tool the request needs in ONE turn, in the order they should run.
- Results come back to you only for information tools, failures, or calls where you set more_steps=true. Otherwise the user hears each tool's own confirmation and you are not asked again, so do not set more_steps unless the next step depends on the result.
- Prefer a specific tool over run_powershell. Use run_powershell for anything Windows can do that no tool covers.
- Never delete anything unless the user clearly asked to delete. To clear things away, move them.
- "Not opened / not used in N days" means the unused_days filter.
- If the request is unclear or you would have to guess a file or folder, ask one short question instead.
- Your words are spoken aloud: one or two short plain sentences, no lists, no markdown, no file paths unless asked.

This PC:
- Now: {now}
- Folders: {folders}
- Browser the user prefers: {browser}
- Installed programs: {apps}
{recent}"""


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


class Engine:
    def __init__(self, config, journal) -> None:
        self.config = config
        self.ctx = Context(config, journal)
        self.pending: dict | None = None
        self.recent: deque[str] = deque(maxlen=6)
        self._lock = threading.Lock()

    # ------------------------------------------------------------ public

    def handle(self, text: str) -> dict:
        """Run one command and report what happened, with timings."""
        with self._lock:
            start = time.perf_counter()
            self._think = self._act = 0
            self._steps: list[dict] = []
            text = (text or "").strip()
            if not text:
                return self._result("", "I didn't catch that.", "none", start, ok=False)
            self.ctx.journal.begin(text[:80])
            try:
                reply, path, ok = self._dispatch(text)
            except llm.LLMError as err:
                reply, path, ok = str(err), "ai", False
            finally:
                self.ctx.journal.commit()
            self.recent.append(f"User: {text}\nVox: {reply}")
            return self._result(text, reply, path, start, ok)

    def undo(self) -> dict:
        with self._lock:
            return self.ctx.journal.undo()

    def cancel_pending(self) -> None:
        self.pending = None

    # ------------------------------------------------------------ routing

    def _dispatch(self, text: str) -> tuple[str, str, bool]:
        if self.pending:
            decision = router.yes_no(text)
            pending, self.pending = self.pending, None
            if decision is False:
                return "Okay, cancelled.", "confirm", True
            if decision is True:
                reply, ok = self._run(pending["session"], pending["calls"], pending["pairs"], confirmed=True)
                return reply, "confirm", ok
            # Anything else is a new command; the question is dropped.

        direct = router.answer(text)
        if direct:
            return direct, "instant", True

        calls = router.match(text)
        if calls:
            checkpoint = len(self._steps)
            reply, ok = self._run(None, [{"id": None, "name": n, "args": a} for n, a in calls], [])
            if ok or self.pending or not llm.ready(self.config):
                return reply, "instant", ok
            del self._steps[checkpoint:]  # the instant attempt failed: let the AI try

        session = llm.session(self.config, self._system(), schemas())
        session.add_user(text)
        reply, ok = self._run(session, None, [])
        return reply, "ai", ok

    # ------------------------------------------------------------ execution

    def _run(self, session, calls, pairs, confirmed=False) -> tuple[str, bool]:
        """Execute tool calls, looping back to the AI only when it needs results."""
        for _ in range(MAX_ROUNDS):
            if calls is None:
                started = time.perf_counter()
                reply, calls = session.step()
                self._think += _ms(started)
                pairs = []
                if not calls:
                    return reply or "Done.", True

            for index, call in enumerate(calls):
                spec = TOOLS.get(call["name"])
                if spec and not confirmed and spec.needs_confirmation(call["args"], self.ctx):
                    self.pending = {"session": session, "calls": calls[index:], "pairs": pairs}
                    question = spec.preview(call["args"], self.ctx) if spec.preview else "Shall I go ahead?"
                    return question, True
                confirmed = False  # a yes covers exactly one risky call
                started = time.perf_counter()
                result = run(call["name"], call["args"], self.ctx)
                self._act += _ms(started)
                pairs.append((call, result))
                self._steps.append({"tool": call["name"], "args": call["args"],
                                    "ok": result["ok"], "message": result["message"]})

            all_ok = all(result["ok"] for _, result in pairs)
            wants_results = any(
                call["args"].get("more_steps") or (TOOLS.get(call["name"]) and TOOLS[call["name"]].kind == "info")
                for call, _ in pairs)
            if session is None or (all_ok and not wants_results):
                said = list(dict.fromkeys(result["message"] for _, result in pairs))
                return " ".join(said), all_ok
            session.add_results(pairs)
            calls = None
        return "That needed more steps than I allow in one go, so I stopped.", False

    # ------------------------------------------------------------ helpers

    def _system(self) -> str:
        folders = ", ".join(f"{name} = {paths.known_folder(name)}" for name in paths.KNOWN)
        recent = ("\nRecent conversation (oldest first):\n" + "\n".join(self.recent)) if self.recent else ""
        return SYSTEM.format(
            now=datetime.datetime.now().strftime("%A %d %B %Y, %H:%M"),
            folders=folders,
            browser=self.config["browser"],
            apps=", ".join(apps.app_names()[:250]) or "unknown",
            recent=recent,
        )

    def _result(self, heard, reply, path, start, ok) -> dict:
        return {
            "heard": heard,
            "reply": reply,
            "ok": ok,
            "path": path,
            "steps": self._steps,
            "pending": self.pending is not None,
            "can_undo": self.ctx.journal.can_undo(),
            "timings": {"think_ms": self._think, "act_ms": self._act, "total_ms": _ms(start)},
        }
