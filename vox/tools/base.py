"""Registry of the things Vox can do on the PC ("skills")."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

MORE_STEPS = {
    "type": "boolean",
    "description": "Set true only if you must see this result before deciding the next step.",
}


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable
    params: dict = field(default_factory=dict)
    required: tuple = ()
    kind: str = "action"  # "action" changes something; "info" returns facts to reason over
    confirm: object = False  # bool, or callable(args, ctx) -> bool
    preview: Callable | None = None  # callable(args, ctx) -> question to ask the user

    def needs_confirmation(self, args: dict, ctx) -> bool:
        return self.confirm(args, ctx) if callable(self.confirm) else bool(self.confirm)

    def schema(self) -> dict:
        props = dict(self.params)
        if self.kind == "action":
            props["more_steps"] = MORE_STEPS
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": props, "required": list(self.required)},
        }


TOOLS: dict[str, Tool] = {}


def tool(name, description, params=None, required=(), kind="action", confirm=False, preview=None):
    def register(fn):
        TOOLS[name] = Tool(name, description, fn, params or {}, tuple(required), kind, confirm, preview)
        return fn

    return register


@dataclass
class Context:
    config: object
    journal: object
    hooks: dict = field(default_factory=dict)  # callbacks into the running app (dictation)
    launch: tuple | None = None  # (time, window that was in front) of the last program opened


def schemas() -> list[dict]:
    return [t.schema() for t in TOOLS.values()]


def run(name: str, args: dict, ctx: Context) -> dict:
    """Run one skill. Never raises: failures come back as ok=False."""
    spec = TOOLS.get(name)
    if spec is None:
        return {"ok": False, "message": f"I don't have a skill called {name}."}
    args = {k: v for k, v in (args or {}).items() if k != "more_steps" and k in spec.params}
    missing = [p for p in spec.required if args.get(p) in (None, "")]
    if missing:
        return {"ok": False, "message": f"{name} needs: {', '.join(missing)}."}
    try:
        result = spec.fn(ctx, **args)
    except PermissionError as err:
        return {"ok": False, "message": f"Windows refused access: {err}"}
    except Exception as err:  # a skill bug must not take the assistant down
        return {"ok": False, "message": f"{name} failed: {err}"}
    result.setdefault("ok", True)
    result.setdefault("message", "Done.")
    return result
