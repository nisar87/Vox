"""Instant path: recognise everyday commands locally, with no AI round trip.

Anything not matched here with confidence returns None and goes to the AI
model, so this file only needs to be right, never complete.
"""

from __future__ import annotations

import datetime
import re

from .tools import apps, web

Call = tuple[str, dict]

SITE = "|".join(sorted(set(web.SITES) | set(web.SEARCH) | {"google maps"}, key=len, reverse=True))
BROWSER = r"(?:google\s+)?(?P<br>chrome|edge|firefox|brave|browser|the browser)"
# Words that mean the user is talking about their own files, not the web.
LOCAL_WORDS = re.compile(
    r"\b(files?|folders?|director(?:y|ies)|desktop|downloads?|documents|my pc|my computer|"
    r"this pc|drive|disk|recycle)\b")

_FILLER_START = re.compile(
    r"^(?:(?:hey|ok|okay|hi)\s+)?(?:vox[,\s]+)?(?:(?:please|kindly)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?(?:(?:please|kindly)\s+)?(?:i\s+want\s+you\s+to\s+)?")
_FILLER_END = re.compile(r"(?:\s+(?:please|for me|now|right now|thanks|thank you))+$")


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[‘’]", "'", text)
    text = re.sub(r"[.!?]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    text = _FILLER_START.sub("", text, count=1)
    text = _FILLER_END.sub("", text)
    return text.strip(" ,")


YES = re.compile(r"^(?:yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|go on|confirm|proceed|"
                 r"please do|yes please|absolutely|correct|affirmative)(?:\s+(?:please|do it|go ahead|sure))*$")
NO = re.compile(r"^(?:no|nope|nah|cancel|stop|don't|do not|never mind|nevermind|abort|"
                r"no thanks|no thank you|leave it)(?:\s+.*)?$")


def yes_no(text: str) -> bool | None:
    t = normalize(text).replace(",", "")
    if YES.match(t):
        return True
    if NO.match(t):
        return False
    return None


def _site(name: str) -> str:
    return "maps" if name == "google maps" else name


def _br(match) -> str | None:
    groups = match.groupdict()
    br = (groups.get("br") or groups.get("br2") or "").replace("the ", "")
    return br if br in web.BROWSER_EXE else None


def _search(match) -> list[Call] | None:
    site = _site(match.groupdict().get("site") or "google")
    query = match.group("q").strip(" ,")
    query = re.sub(rf"\s+(?:on|in)\s+(?:{SITE}|it|there)$", "", query)
    if not query or site not in web.SEARCH or LOCAL_WORDS.search(query) or query in web.BROWSER_EXE:
        return None
    args = {"query": query, "site": site}
    if _br(match):
        args["browser"] = _br(match)
    return [("web_search", args)]


def _open_site(match) -> list[Call]:
    args = {"site": _site(match.group("site"))}
    if _br(match):
        args["browser"] = _br(match)
    return [("open_website", args)]


def _open_app(match) -> list[Call] | None:
    name = match.group("app")
    if re.search(r"\b(and|then|with|in|on|to|from)\b", name):
        return None
    if apps._clean(name) in ("browser", "web browser"):
        return [("open_app", {"name": name})]
    found = apps.find_app(name)
    return [("open_app", {"name": found[0]})] if found and found[2] else None


def _close_app(match) -> list[Call] | None:
    name = match.group("app")
    if re.search(r"\b(and|then|all|everything|except|tab|window)\b", name):
        return None
    return [("close_app", {"name": name})]


def _volume_set(match) -> list[Call]:
    return [("set_volume", {"level": min(100, int(match.group("n")))})]


def _static(*calls: Call):
    return lambda match: list(calls)


_IN_BROWSER = rf"(?:\s+(?:in|on|using|with)\s+{BROWSER})?"
_JOIN = r"\s*(?:,|and then|and|then)\s+"

RULES: list[tuple[re.Pattern, object]] = [(re.compile(p), fn) for p, fn in [
    # "open youtube in chrome and search for lofi beats (in youtube)"
    (rf"^(?:open|go to|launch|start)\s+(?:up\s+)?(?P<site>{SITE}){_IN_BROWSER}{_JOIN}"
     r"(?:search|look|find|play)(?:\s+(?:it\s+)?(?:for|up))?\s+(?P<q>.+)$", _search),
    # "(open chrome and) search for cats on youtube", "play despacito on youtube"
    (rf"^(?:open\s+{BROWSER}{_JOIN})?(?:search|look up|find|play)\s+(?:for\s+)?(?P<q>.+?)\s+"
     rf"(?:on|in)\s+(?P<site>{SITE}){_IN_BROWSER.replace('<br>', '<br2>')}$", _search),
    # "search youtube for cats"
    (rf"^(?:search|look up)\s+(?:on\s+)?(?P<site>{SITE})\s+for\s+(?P<q>.+)$", _search),
    # "open (google) chrome and search for X", "google X", "search for X"
    (rf"^(?:open\s+{BROWSER}{_JOIN})?(?:search the web|search google|search online|search|google|look up)"
     r"\s+(?:for\s+)?(?P<q>.+)$", _search),
    # "open youtube", "go to gmail in chrome"
    (rf"^(?:open|go to|visit|launch|start)\s+(?:up\s+)?(?P<site>{SITE}|[\w-]+\.(?:com|org|net|io|pk|co|dev|ai|tv|gov|edu)\S*)"
     rf"{_IN_BROWSER}$", _open_site),
    # "open my downloads folder"
    (r"^(?:open|show)\s+(?:my\s+|the\s+)?(?P<f>desktop|downloads|documents|pictures|music|videos)(?:\s+folder)?$",
     lambda m: [("open_path", {"path": m.group("f")})]),
    # "open notepad"
    (r"^(?:open|launch|start|run)\s+(?:up\s+)?(?:the\s+)?(?P<app>[\w .+#-]{2,40}?)(?:\s+app(?:lication)?)?$", _open_app),
    (r"^(?:close|quit|exit|kill)\s+(?:the\s+)?(?P<app>[\w .+#-]{2,40}?)(?:\s+app(?:lication)?)?$", _close_app),
    # Volume and media
    (r"^(?:set\s+)?(?:the\s+)?volume\s+(?:to|at)\s+(?P<n>\d{1,3})(?:\s*(?:percent|%))?$", _volume_set),
    (r"^(?:(?:(?:turn|put)\s+)?(?:the\s+)?volume\s+up|(?:turn\s+up|increase|raise)\s+(?:the\s+)?volume|louder)$",
     _static(("set_volume", {"change": 10}))),
    (r"^(?:(?:(?:turn|put)\s+)?(?:the\s+)?volume\s+down|(?:turn\s+down|decrease|lower|reduce)\s+(?:the\s+)?volume|quieter)$",
     _static(("set_volume", {"change": -10}))),
    (r"^mute(?:\s+(?:the\s+)?(?:volume|sound|audio|pc|computer))?$", _static(("set_volume", {"mute": True}))),
    (r"^unmute(?:\s+(?:the\s+)?(?:volume|sound|audio|pc|computer))?$", _static(("set_volume", {"mute": False}))),
    (r"^(?:pause|resume|play)(?:\s+(?:the\s+)?(?:music|song|video|it))?$", _static(("media_key", {"action": "play_pause"}))),
    (r"^(?:next|skip)(?:\s+(?:the\s+|this\s+)?(?:track|song|video))?$", _static(("media_key", {"action": "next"}))),
    (r"^previous(?:\s+(?:track|song|video))?$", _static(("media_key", {"action": "previous"}))),
    # System
    (r"^lock(?:\s+(?:my|the))?(?:\s+(?:pc|computer|screen|laptop))?$", _static(("power", {"action": "lock"}))),
    (r"^(?:cancel|abort|stop)(?:\s+the)?\s+(?:shutdown|restart)$", _static(("power", {"action": "cancel_shutdown"}))),
    (r"^(?:shut\s?down|turn off|power off)(?:\s+(?:my|the))?(?:\s+(?:pc|computer|laptop))?$",
     _static(("power", {"action": "shutdown"}))),
    (r"^(?:restart|reboot)(?:\s+(?:my|the))?(?:\s+(?:pc|computer|laptop))?$", _static(("power", {"action": "restart"}))),
    (r"^(?:(?:take|grab|capture)\s+a\s+screenshot|screenshot)$", _static(("take_screenshot", {}))),
    (r"^undo(?:\s+(?:that|it|this|the last (?:one|thing|action)))?$", _static(("undo_last", {}))),
]]

TIME = re.compile(r"^what(?:'s| is)?\s+(?:the\s+)?time(?:\s+is it)?(?:\s+now)?$|^what time is it$")
DATE = re.compile(r"^what(?:'s| is)?\s+(?:the\s+|today's\s+)?(?:date|day)(?:\s+(?:is it|today))?$")


def answer(text: str) -> str | None:
    """Questions answerable without touching the PC or the AI."""
    t = normalize(text)
    now = datetime.datetime.now()
    if TIME.match(t):
        return "It's " + now.strftime("%I:%M %p").lstrip("0") + "."
    if DATE.match(t):
        return f"It's {now:%A}, {now.day} {now:%B %Y}."
    return None


def match(text: str) -> list[Call] | None:
    t = normalize(text)
    for pattern, build in RULES:
        found = pattern.match(t)
        if found:
            calls = build(found)
            if calls:
                return calls
    return None
